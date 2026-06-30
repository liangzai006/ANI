package main

import (
	"fmt"
	"strings"

	registryadapter "github.com/kubercloud/ani/pkg/adapters/registry"
	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
	"github.com/kubercloud/ani/pkg/ports"
)

func newGatewayRegistryPullSecretKubernetesApply(
	imageRegistry ports.ImageRegistry,
	secretCfg gatewaySecretRuntimeConfig,
) (ports.RegistryPullSecretKubernetesApply, error) {
	if imageRegistry == nil {
		return nil, nil
	}
	if strings.TrimSpace(secretCfg.ProviderMode) != "kubernetes_rest" {
		return nil, nil
	}
	credentialSource, ok := registryadapter.AsPullSecretCredentialSource(imageRegistry)
	if !ok {
		return nil, nil
	}
	client, err := newGatewayKubernetesRESTClient(secretCfg.KubernetesHTTPClient, secretCfg.KubernetesRequestTimeout)
	if err != nil {
		return nil, fmt.Errorf("registry pull secret kubernetes apply: %w", err)
	}
	provider := runtimeadapter.NewKubernetesSecretProviderAdapter(client)
	return runtimeadapter.NewRegistryPullSecretKubernetesApplyService(credentialSource, provider), nil
}
