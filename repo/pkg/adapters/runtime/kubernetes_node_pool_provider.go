package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

type KubernetesNodePoolProviderClient interface {
	ApplyManifests(ctx context.Context, manifests []ports.WorkloadManifest) ([]string, error)
}

type KubernetesNodePoolProviderAdapter struct {
	client KubernetesNodePoolProviderClient
	config KubernetesNodePoolProviderConfig
	now    func() time.Time
}

type KubernetesNodePoolProviderOption func(*KubernetesNodePoolProviderAdapter)

type KubernetesNodePoolProviderConfig struct {
	MachineVersion string

	BootstrapDataSecretNameTemplate string
	BootstrapRefAPIVersion          string
	BootstrapRefKind                string
	BootstrapRefNameTemplate        string
	BootstrapRefNamespace           string

	InfrastructureRefAPIVersion   string
	InfrastructureRefKind         string
	InfrastructureRefNameTemplate string
	InfrastructureRefNamespace    string
}

func WithKubernetesNodePoolProviderConfig(config KubernetesNodePoolProviderConfig) KubernetesNodePoolProviderOption {
	return func(adapter *KubernetesNodePoolProviderAdapter) {
		adapter.config = config.withDefaults()
	}
}

func WithKubernetesNodePoolProviderClock(now func() time.Time) KubernetesNodePoolProviderOption {
	return func(adapter *KubernetesNodePoolProviderAdapter) {
		if now != nil {
			adapter.now = now
		}
	}
}

func NewKubernetesNodePoolProviderAdapter(client KubernetesNodePoolProviderClient, options ...KubernetesNodePoolProviderOption) *KubernetesNodePoolProviderAdapter {
	adapter := &KubernetesNodePoolProviderAdapter{
		client: client,
		config: KubernetesNodePoolProviderConfig{}.withDefaults(),
		now:    time.Now,
	}
	for _, option := range options {
		option(adapter)
	}
	adapter.config = adapter.config.withDefaults()
	return adapter
}

func (a *KubernetesNodePoolProviderAdapter) ApplyK8sClusterNodePool(ctx context.Context, request ports.K8sClusterNodePoolProviderRequest) (ports.K8sClusterNodePoolProviderResult, error) {
	if err := validateK8sClusterNodePoolProviderRequest(request); err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	if a.client == nil {
		return ports.K8sClusterNodePoolProviderResult{}, fmt.Errorf("%w: Kubernetes node pool provider client is required", ports.ErrNotConfigured)
	}
	manifest, err := renderKubernetesNodePoolManifest(request, a.config, false)
	if err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	refs, err := a.client.ApplyManifests(ctx, []ports.WorkloadManifest{manifest})
	if err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	return ports.K8sClusterNodePoolProviderResult{
		Applied:      true,
		Provider:     "clusterapi",
		ResourceRefs: refs,
		Reason:       "Cluster API MachineDeployment applied",
		AppliedAt:    a.now().UTC(),
	}, nil
}

func (a *KubernetesNodePoolProviderAdapter) DeleteK8sClusterNodePool(ctx context.Context, request ports.K8sClusterNodePoolProviderRequest) (ports.K8sClusterNodePoolProviderResult, error) {
	if err := validateK8sClusterNodePoolProviderRequest(request); err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	if a.client == nil {
		return ports.K8sClusterNodePoolProviderResult{}, fmt.Errorf("%w: Kubernetes node pool provider client is required", ports.ErrNotConfigured)
	}
	manifest, err := renderKubernetesNodePoolManifest(request, a.config, true)
	if err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	refs, err := a.client.ApplyManifests(ctx, []ports.WorkloadManifest{manifest})
	if err != nil {
		return ports.K8sClusterNodePoolProviderResult{}, err
	}
	return ports.K8sClusterNodePoolProviderResult{
		Applied:      true,
		Provider:     "clusterapi",
		ResourceRefs: refs,
		Reason:       "Cluster API MachineDeployment delete intent applied",
		AppliedAt:    a.now().UTC(),
	}, nil
}

func validateK8sClusterNodePoolProviderRequest(request ports.K8sClusterNodePoolProviderRequest) error {
	if strings.TrimSpace(request.TenantID) == "" || strings.TrimSpace(request.ClusterID) == "" || strings.TrimSpace(request.ClusterName) == "" || strings.TrimSpace(request.NodePoolID) == "" || strings.TrimSpace(request.Name) == "" || strings.TrimSpace(request.InstanceType) == "" {
		return fmt.Errorf("%w: tenant_id, cluster_id, cluster_name, node_pool_id, name and instance_type are required for node pool provider", ports.ErrInvalid)
	}
	if request.NodeCount < 0 {
		return fmt.Errorf("%w: node_count cannot be negative", ports.ErrInvalid)
	}
	if request.GPU.Count < 0 {
		return fmt.Errorf("%w: gpu.count cannot be negative", ports.ErrInvalid)
	}
	return nil
}

func renderKubernetesNodePoolManifest(request ports.K8sClusterNodePoolProviderRequest, config KubernetesNodePoolProviderConfig, deleteIntent bool) (ports.WorkloadManifest, error) {
	config = config.withDefaults()
	if err := config.validate(); err != nil {
		return ports.WorkloadManifest{}, err
	}
	replicas := request.NodeCount
	if deleteIntent {
		replicas = 0
	}
	name := kubernetesNodePoolName(request)
	namespace := tenantNamespace(request.TenantID)
	labels := map[string]string{
		"app.kubernetes.io/managed-by":       "ani-core",
		"ani.kubercloud.io/tenant-id":        request.TenantID,
		"ani.kubercloud.io/k8s-cluster-id":   request.ClusterID,
		"ani.kubercloud.io/node-pool-id":     request.NodePoolID,
		"ani.kubercloud.io/node-pool-name":   request.Name,
		"cluster.x-k8s.io/cluster-name":      request.ClusterName,
		"ani.kubercloud.io/instance-type":    request.InstanceType,
		"ani.kubercloud.io/provider-intent":  "node-pool",
		"ani.kubercloud.io/provider-version": "v1",
	}
	if request.GPU.Vendor != "" {
		labels["ani.kubercloud.io/gpu-vendor"] = request.GPU.Vendor
	}
	if request.GPU.Model != "" {
		labels["ani.kubercloud.io/gpu-model"] = request.GPU.Model
	}
	annotations := map[string]string{
		"ani.kubercloud.io/operation":     operationOrDefault(request.Operation, "apply"),
		"ani.kubercloud.io/instance-type": request.InstanceType,
	}
	if request.GPU.Count > 0 {
		annotations["ani.kubercloud.io/gpu-count"] = fmt.Sprintf("%d", request.GPU.Count)
		annotations["ani.kubercloud.io/gpu-resource-name"] = request.GPU.ResourceName
	}
	if deleteIntent {
		annotations["ani.kubercloud.io/delete-intent"] = "true"
	}
	templateMetadata := map[string]any{
		"labels":      labels,
		"annotations": annotations,
	}
	machineSpec := map[string]any{
		"clusterName":       request.ClusterName,
		"bootstrap":         config.bootstrapRef(request, name, namespace),
		"infrastructureRef": config.infrastructureRef(request, name, namespace),
	}
	if strings.TrimSpace(config.MachineVersion) != "" {
		machineSpec["version"] = strings.TrimSpace(config.MachineVersion)
	}
	doc := map[string]any{
		"apiVersion": "cluster.x-k8s.io/v1beta1",
		"kind":       "MachineDeployment",
		"metadata": map[string]any{
			"name":        name,
			"namespace":   namespace,
			"labels":      labels,
			"annotations": annotations,
		},
		"spec": map[string]any{
			"clusterName": request.ClusterName,
			"replicas":    replicas,
			"selector": map[string]any{
				"matchLabels": map[string]string{
					"ani.kubercloud.io/node-pool-id": request.NodePoolID,
				},
			},
			"template": map[string]any{
				"metadata": templateMetadata,
				"spec":     machineSpec,
			},
		},
	}
	content, err := json.Marshal(doc)
	if err != nil {
		return ports.WorkloadManifest{}, err
	}
	return ports.WorkloadManifest{
		Provider: "clusterapi",
		Kind:     "MachineDeployment",
		Name:     name,
		Content:  string(content),
	}, nil
}

func (c KubernetesNodePoolProviderConfig) withDefaults() KubernetesNodePoolProviderConfig {
	if strings.TrimSpace(c.BootstrapDataSecretNameTemplate) == "" {
		c.BootstrapDataSecretNameTemplate = "{machine_deployment_name}-bootstrap"
	}
	if strings.TrimSpace(c.InfrastructureRefAPIVersion) == "" {
		c.InfrastructureRefAPIVersion = "infrastructure.cluster.x-k8s.io/v1beta1"
	}
	if strings.TrimSpace(c.InfrastructureRefKind) == "" {
		c.InfrastructureRefKind = "ANIMachineTemplate"
	}
	if strings.TrimSpace(c.InfrastructureRefNameTemplate) == "" {
		c.InfrastructureRefNameTemplate = "{machine_deployment_name}"
	}
	return c
}

func (c KubernetesNodePoolProviderConfig) validate() error {
	if strings.TrimSpace(c.BootstrapRefAPIVersion) == "" && strings.TrimSpace(c.BootstrapRefKind) == "" && strings.TrimSpace(c.BootstrapRefNameTemplate) == "" {
		return nil
	}
	if strings.TrimSpace(c.BootstrapRefAPIVersion) == "" || strings.TrimSpace(c.BootstrapRefKind) == "" || strings.TrimSpace(c.BootstrapRefNameTemplate) == "" {
		return fmt.Errorf("%w: bootstrap configRef apiVersion, kind, and name template must be configured together", ports.ErrInvalid)
	}
	return nil
}

func (c KubernetesNodePoolProviderConfig) bootstrapRef(request ports.K8sClusterNodePoolProviderRequest, machineDeploymentName string, namespace string) map[string]any {
	if strings.TrimSpace(c.BootstrapRefAPIVersion) != "" || strings.TrimSpace(c.BootstrapRefKind) != "" || strings.TrimSpace(c.BootstrapRefNameTemplate) != "" {
		ref := map[string]any{
			"apiVersion": renderKubernetesNodePoolTemplate(c.BootstrapRefAPIVersion, request, machineDeploymentName, namespace),
			"kind":       renderKubernetesNodePoolTemplate(c.BootstrapRefKind, request, machineDeploymentName, namespace),
			"name":       renderKubernetesNodePoolTemplate(firstNonEmpty(c.BootstrapRefNameTemplate, "{machine_deployment_name}"), request, machineDeploymentName, namespace),
		}
		if strings.TrimSpace(c.BootstrapRefNamespace) != "" {
			ref["namespace"] = renderKubernetesNodePoolTemplate(c.BootstrapRefNamespace, request, machineDeploymentName, namespace)
		}
		return map[string]any{"configRef": ref}
	}
	return map[string]any{
		"dataSecretName": renderKubernetesNodePoolTemplate(c.BootstrapDataSecretNameTemplate, request, machineDeploymentName, namespace),
	}
}

func (c KubernetesNodePoolProviderConfig) infrastructureRef(request ports.K8sClusterNodePoolProviderRequest, machineDeploymentName string, namespace string) map[string]any {
	ref := map[string]any{
		"apiVersion": renderKubernetesNodePoolTemplate(c.InfrastructureRefAPIVersion, request, machineDeploymentName, namespace),
		"kind":       renderKubernetesNodePoolTemplate(c.InfrastructureRefKind, request, machineDeploymentName, namespace),
		"name":       renderKubernetesNodePoolTemplate(c.InfrastructureRefNameTemplate, request, machineDeploymentName, namespace),
	}
	if strings.TrimSpace(c.InfrastructureRefNamespace) != "" {
		ref["namespace"] = renderKubernetesNodePoolTemplate(c.InfrastructureRefNamespace, request, machineDeploymentName, namespace)
	}
	return ref
}

func renderKubernetesNodePoolTemplate(template string, request ports.K8sClusterNodePoolProviderRequest, machineDeploymentName string, namespace string) string {
	replacements := map[string]string{
		"{cluster_id}":              request.ClusterID,
		"{cluster_name}":            request.ClusterName,
		"{machine_deployment_name}": machineDeploymentName,
		"{namespace}":               namespace,
		"{node_pool_id}":            request.NodePoolID,
		"{node_pool_name}":          request.Name,
		"{tenant_id}":               request.TenantID,
	}
	result := strings.TrimSpace(template)
	for token, value := range replacements {
		result = strings.ReplaceAll(result, token, value)
	}
	return result
}

func kubernetesNodePoolName(request ports.K8sClusterNodePoolProviderRequest) string {
	name := strings.ToLower(firstNonEmpty(request.Name, request.NodePoolID))
	var builder strings.Builder
	for _, r := range name {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' {
			builder.WriteRune(r)
			continue
		}
		builder.WriteByte('-')
	}
	result := strings.Trim(builder.String(), "-")
	if result == "" {
		result = "node-pool"
	}
	if len(result) > 63 {
		result = strings.TrimRight(result[:63], "-")
	}
	return result
}

func operationOrDefault(operation string, fallback string) string {
	if strings.TrimSpace(operation) == "" {
		return fallback
	}
	return strings.TrimSpace(operation)
}

var _ ports.K8sClusterNodePoolProvider = (*KubernetesNodePoolProviderAdapter)(nil)
