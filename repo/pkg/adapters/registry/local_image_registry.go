package registry

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

type LocalImageRegistry struct {
	mu          sync.RWMutex
	now         func() time.Time
	projects    map[string]ports.RegistryProject
	pullSecrets map[string]ports.RegistryPullSecret
	permissions map[string]ports.RegistryPermission
	idempotency map[string]string
}

type LocalImageRegistryOption func(*LocalImageRegistry)

func WithRegistryClock(now func() time.Time) LocalImageRegistryOption {
	return func(registry *LocalImageRegistry) {
		if now != nil {
			registry.now = now
		}
	}
}

func NewLocalImageRegistry(options ...LocalImageRegistryOption) *LocalImageRegistry {
	registry := &LocalImageRegistry{
		now:         func() time.Time { return time.Now().UTC() },
		projects:    map[string]ports.RegistryProject{},
		pullSecrets: map[string]ports.RegistryPullSecret{},
		permissions: map[string]ports.RegistryPermission{},
		idempotency: map[string]string{},
	}
	for _, option := range options {
		option(registry)
	}
	return registry
}

func (r *LocalImageRegistry) EnsureProject(_ context.Context, tenantID string) error {
	tenantID = strings.TrimSpace(tenantID)
	if tenantID == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureProjectLocked(tenantID, registryDefaultProjectName)
	return nil
}

func (r *LocalImageRegistry) CreateProject(_ context.Context, request ports.RegistryProjectRequest) (ports.RegistryProject, error) {
	tenantID := strings.TrimSpace(request.TenantID)
	name := strings.TrimSpace(request.Name)
	if tenantID == "" {
		return ports.RegistryProject{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if err := validateRegistryProjectName(name); err != nil {
		return ports.RegistryProject{}, err
	}
	idemKey, err := registryIdempotencyKey(tenantID, request.IdempotencyKey)
	if err != nil {
		return ports.RegistryProject{}, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if storageKey, ok := r.idempotency[idemKey]; ok {
		project := r.projects[storageKey]
		project.DevProfile = registryDevProfile()
		return project, nil
	}
	project := r.ensureProjectLocked(tenantID, name)
	project.Public = request.Public
	project.DevProfile = registryDevProfile()
	storageKey := tenantProjectStorageKey(tenantID, name)
	r.projects[storageKey] = project
	r.idempotency[idemKey] = storageKey
	return project, nil
}

func (r *LocalImageRegistry) ListProjects(_ context.Context, request ports.RegistryProjectListRequest) (ports.RegistryProjectListResult, error) {
	tenantID := strings.TrimSpace(request.TenantID)
	if tenantID == "" {
		return ports.RegistryProjectListResult{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	items := make([]ports.RegistryProject, 0)
	for key, project := range r.projects {
		if !strings.HasPrefix(key, tenantID+"\x00") {
			continue
		}
		project.DevProfile = registryDevProfile()
		items = append(items, project)
	}
	return ports.RegistryProjectListResult{
		Items:      items,
		DevProfile: registryDevProfile(),
	}, nil
}

func (r *LocalImageRegistry) ListRepositories(_ context.Context, request ports.RegistryRepositoryListRequest) (ports.RegistryRepositoryListResult, error) {
	if err := validateRegistryProjectRequest(request.TenantID, request.Project); err != nil {
		return ports.RegistryRepositoryListResult{}, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureProjectLocked(strings.TrimSpace(request.TenantID), strings.TrimSpace(request.Project))
	repository := ports.RegistryRepository{
		Project:       strings.TrimSpace(request.Project),
		Name:          "runtime",
		ArtifactCount: 1,
		PullCount:     0,
		DevProfile:    registryDevProfile(),
	}
	if permission, ok := r.permissions[permissionKey(request.Project, "runtime", "svc-model")]; ok {
		cloned := cloneRegistryPermission(permission)
		repository.Permission = &cloned
	}
	return ports.RegistryRepositoryListResult{
		Items:      []ports.RegistryRepository{repository},
		DevProfile: registryDevProfile(),
	}, nil
}

func (r *LocalImageRegistry) ListArtifacts(_ context.Context, request ports.RegistryArtifactListRequest) (ports.RegistryArtifactListResult, error) {
	if err := validateRegistryProjectRequest(request.TenantID, request.Project); err != nil {
		return ports.RegistryArtifactListResult{}, err
	}
	if strings.TrimSpace(request.Repository) == "" {
		return ports.RegistryArtifactListResult{}, fmt.Errorf("%w: repository is required", ports.ErrInvalid)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureProjectLocked(strings.TrimSpace(request.TenantID), strings.TrimSpace(request.Project))
	scan := r.scanResultLocked(strings.TrimSpace(request.Project) + "/" + strings.TrimSpace(request.Repository) + ":latest")
	artifact := ports.RegistryArtifact{
		Project:    strings.TrimSpace(request.Project),
		Repository: strings.TrimSpace(request.Repository),
		Digest:     "sha256:local-runtime",
		Tags:       []string{"latest"},
		MediaType:  "application/vnd.oci.image.manifest.v1+json",
		SizeBytes:  1048576,
		PushedAt:   r.now().UTC(),
		ScanStatus: scan,
		DevProfile: registryDevProfile(),
	}
	return ports.RegistryArtifactListResult{
		Items:      []ports.RegistryArtifact{artifact},
		DevProfile: registryDevProfile(),
	}, nil
}

func (r *LocalImageRegistry) SetRepositoryPermission(_ context.Context, request ports.RegistryPermissionRequest) (ports.RegistryPermission, error) {
	if err := validateRegistryProjectRequest(request.TenantID, request.Project); err != nil {
		return ports.RegistryPermission{}, err
	}
	if strings.TrimSpace(request.Repository) == "" {
		return ports.RegistryPermission{}, fmt.Errorf("%w: repository is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.Subject) == "" {
		return ports.RegistryPermission{}, fmt.Errorf("%w: subject is required", ports.ErrInvalid)
	}
	if len(request.Actions) == 0 {
		return ports.RegistryPermission{}, fmt.Errorf("%w: actions are required", ports.ErrInvalid)
	}
	idemKey, err := registryIdempotencyKey(request.TenantID, request.IdempotencyKey)
	if err != nil {
		return ports.RegistryPermission{}, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if key, ok := r.idempotency[idemKey]; ok {
		permission := cloneRegistryPermission(r.permissions[key])
		permission.State = ports.RegistryPermissionDuplicate
		permission.DevProfile = registryDevProfile()
		return permission, nil
	}
	r.ensureProjectLocked(strings.TrimSpace(request.TenantID), strings.TrimSpace(request.Project))
	permission := ports.RegistryPermission{
		Project:    strings.TrimSpace(request.Project),
		Repository: strings.TrimSpace(request.Repository),
		Subject:    strings.TrimSpace(request.Subject),
		Actions:    append([]ports.RegistryPermissionAction(nil), request.Actions...),
		State:      ports.RegistryPermissionActive,
		DevProfile: registryDevProfile(),
		UpdatedAt:  r.now().UTC(),
	}
	key := permissionKey(permission.Project, permission.Repository, permission.Subject)
	r.permissions[key] = permission
	r.idempotency[idemKey] = key
	return permission, nil
}

func (r *LocalImageRegistry) GetScanResult(_ context.Context, request ports.RegistryScanResultRequest) (ports.RegistryScanResult, error) {
	if strings.TrimSpace(request.TenantID) == "" {
		return ports.RegistryScanResult{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.Image) == "" {
		return ports.RegistryScanResult{}, fmt.Errorf("%w: image is required", ports.ErrInvalid)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.scanResultLocked(strings.TrimSpace(request.Image)), nil
}

func (r *LocalImageRegistry) CreatePullSecret(ctx context.Context, request ports.RegistryPullSecretRequest) (ports.RegistryPullSecret, error) {
	secret, _, err := r.CreatePullSecretCredential(ctx, request)
	return secret, err
}

func (r *LocalImageRegistry) CreatePullSecretCredential(_ context.Context, request ports.RegistryPullSecretRequest) (ports.RegistryPullSecret, string, error) {
	if err := validateRegistryProjectRequest(request.TenantID, request.Project); err != nil {
		return ports.RegistryPullSecret{}, "", err
	}
	name := strings.TrimSpace(request.Name)
	if name == "" {
		name = "ani-registry-pull"
	}
	idemKey, err := registryIdempotencyKey(request.TenantID, request.IdempotencyKey)
	if err != nil {
		return ports.RegistryPullSecret{}, "", err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if key, ok := r.idempotency[idemKey]; ok {
		secret := r.pullSecrets[key]
		secret.State = ports.RegistryPermissionDuplicate
		secret.DevProfile = registryDevProfile()
		return secret, "", nil
	}
	r.ensureProjectLocked(strings.TrimSpace(request.TenantID), strings.TrimSpace(request.Project))
	secret := ports.RegistryPullSecret{
		Project:    strings.TrimSpace(request.Project),
		Name:       name,
		SecretRef:  strings.TrimSpace(request.Project) + "/" + name,
		Registry:   "registry.local",
		Username:   "robot$" + strings.TrimSpace(request.Project),
		Namespace:  strings.TrimSpace(request.Namespace),
		State:      ports.RegistryPermissionActive,
		DevProfile: registryDevProfile(),
		CreatedAt:  r.now().UTC(),
	}
	key := strings.TrimSpace(request.Project) + ":" + name
	r.pullSecrets[key] = secret
	r.idempotency[idemKey] = key
	return secret, "local-dev-pull-secret", nil
}

func (r *LocalImageRegistry) GetProjectScanReport(_ context.Context, request ports.RegistryProjectScanReportRequest) (ports.RegistryProjectScanReport, error) {
	if err := validateRegistryProjectRequest(request.TenantID, request.Project); err != nil {
		return ports.RegistryProjectScanReport{}, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ensureProjectLocked(strings.TrimSpace(request.TenantID), strings.TrimSpace(request.Project))
	return ports.RegistryProjectScanReport{
		Project:          strings.TrimSpace(request.Project),
		Status:           ports.RegistryScanComplete,
		Critical:         0,
		High:             0,
		Medium:           0,
		Low:              0,
		ArtifactsTotal:   1,
		ScannedArtifacts: 1,
		ProviderID:       "local-trivy",
		DevProfile:       registryDevProfile(),
		ScannedAt:        r.now().UTC(),
	}, nil
}

func (r *LocalImageRegistry) ListTags(ctx context.Context, repository string) ([]ports.ImageTag, error) {
	artifacts, err := r.ListArtifacts(ctx, ports.RegistryArtifactListRequest{
		TenantID:   "local",
		Project:    "local",
		Repository: repository,
	})
	if err != nil {
		return nil, err
	}
	tags := make([]ports.ImageTag, 0, len(artifacts.Items))
	for _, artifact := range artifacts.Items {
		for _, tag := range artifact.Tags {
			tags = append(tags, ports.ImageTag{Name: tag, Digest: artifact.Digest})
		}
	}
	return tags, nil
}

func (r *LocalImageRegistry) GetScanStatus(ctx context.Context, ref ports.ImageRef) (ports.ImageScanStatus, error) {
	image := strings.Trim(strings.Join([]string{ref.Repository, ref.Tag}, ":"), ":")
	result, err := r.GetScanResult(ctx, ports.RegistryScanResultRequest{TenantID: "local", Image: image})
	if err != nil {
		return ports.ImageScanStatus{}, err
	}
	return ports.ImageScanStatus{
		Status:     string(result.Status),
		Critical:   result.Critical,
		High:       result.High,
		Medium:     result.Medium,
		Low:        result.Low,
		ReportURL:  result.ReportURL,
		ProviderID: result.ProviderID,
	}, nil
}

func (r *LocalImageRegistry) ensureProjectLocked(tenantID, name string) ports.RegistryProject {
	storageKey := tenantProjectStorageKey(tenantID, name)
	if project, ok := r.projects[storageKey]; ok {
		return project
	}
	project := ports.RegistryProject{
		ID:         localRegistryProjectID(tenantID, name),
		TenantID:   tenantID,
		Name:       name,
		Public:     false,
		DevProfile: registryDevProfile(),
		CreatedAt:  r.now().UTC(),
	}
	r.projects[storageKey] = project
	return project
}

func (r *LocalImageRegistry) scanResultLocked(image string) ports.RegistryScanResult {
	return ports.RegistryScanResult{
		Image:      image,
		Status:     ports.RegistryScanComplete,
		Critical:   0,
		High:       0,
		Medium:     0,
		Low:        0,
		ReportURL:  "local://registry-scan/" + strings.ReplaceAll(image, "/", "_"),
		ProviderID: "local-trivy",
		DevProfile: registryDevProfile(),
		ScannedAt:  r.now().UTC(),
	}
}

func registryIdempotencyKey(tenantID, key string) (string, error) {
	tenantID = strings.TrimSpace(tenantID)
	key = strings.TrimSpace(key)
	if tenantID == "" {
		return "", fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if key == "" {
		return "", fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	return tenantID + ":" + key, nil
}

func permissionKey(project, repository, subject string) string {
	return strings.TrimSpace(project) + "/" + strings.TrimSpace(repository) + ":" + strings.TrimSpace(subject)
}

func cloneRegistryPermission(permission ports.RegistryPermission) ports.RegistryPermission {
	permission.Actions = append([]ports.RegistryPermissionAction(nil), permission.Actions...)
	return permission
}

func registryDevProfile() ports.DevProfileInfo {
	return ports.DevProfileInfo{
		Mode:         "local",
		Provider:     "local-image-registry",
		RealProvider: false,
		Reason:       "local profile returns deterministic registry metadata; it is not a Harbor or Trivy provider execution",
	}
}

var _ ports.ImageRegistry = (*LocalImageRegistry)(nil)
var _ ports.RegistryPullSecretCredentialSource = (*LocalImageRegistry)(nil)
