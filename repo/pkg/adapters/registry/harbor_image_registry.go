package registry

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/kubercloud/ani/pkg/adapters/resilience"
	"github.com/kubercloud/ani/pkg/ports"
)

const (
	harborAPIBasePath     = "/api/v2.0"
	harborSystem          = "Harbor"
	harborDefaultPageSize = 50
	harborProviderID      = "harbor-trivy"
)

// HarborImageRegistryConfig configures the real Harbor v2.0 provider adapter.
// Credentials stay inside the adapter boundary and are never echoed back to callers.
type HarborImageRegistryConfig struct {
	Endpoint       string
	Username       string
	Password       string
	Secure         bool
	HTTPClient     *http.Client
	RequestTimeout time.Duration
	Now            func() time.Time
}

// HarborImageRegistry is a real provider adapter that talks to the Harbor v2.0 REST API.
// It implements ports.ImageRegistry without leaking Harbor types past the port boundary.
type HarborImageRegistry struct {
	endpoint     *url.URL
	registryHost string
	username     string
	password     string
	client       *http.Client
	policy       resilience.Policy
	now          func() time.Time
}

var _ ports.ImageRegistry = (*HarborImageRegistry)(nil)

func NewHarborImageRegistry(config HarborImageRegistryConfig) (*HarborImageRegistry, error) {
	endpoint, err := parseHarborEndpoint(config.Endpoint, config.Secure)
	if err != nil {
		return nil, err
	}
	username := strings.TrimSpace(config.Username)
	password := strings.TrimSpace(config.Password)
	if username == "" || password == "" {
		return nil, fmt.Errorf("%w: Harbor username and password are required", ports.ErrInvalid)
	}
	client := config.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}
	now := config.Now
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &HarborImageRegistry{
		endpoint:     endpoint,
		registryHost: endpoint.Host,
		username:     username,
		password:     password,
		client:       client,
		policy:       resilience.Policy{Timeout: config.RequestTimeout},
		now:          now,
	}, nil
}

func (r *HarborImageRegistry) EnsureProject(ctx context.Context, tenantID string) error {
	tenantID = strings.TrimSpace(tenantID)
	if tenantID == "" {
		return fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	exists, err := r.projectExists(ctx, tenantID)
	if err != nil {
		return err
	}
	if exists {
		return nil
	}
	return r.createProjectOnHarbor(ctx, tenantID, false)
}

func (r *HarborImageRegistry) CreateProject(ctx context.Context, request ports.RegistryProjectRequest) (ports.RegistryProject, error) {
	tenantID := strings.TrimSpace(request.TenantID)
	name := strings.TrimSpace(request.Name)
	if tenantID == "" {
		return ports.RegistryProject{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	if name == "" {
		return ports.RegistryProject{}, fmt.Errorf("%w: name is required", ports.ErrInvalid)
	}
	if name != tenantID {
		return ports.RegistryProject{}, fmt.Errorf("%w: project must match tenant", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.IdempotencyKey) == "" {
		return ports.RegistryProject{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	if err := r.createProjectOnHarbor(ctx, name, request.Public); err != nil {
		return ports.RegistryProject{}, err
	}
	return r.getProject(ctx, name)
}

func (r *HarborImageRegistry) ListProjects(ctx context.Context, request ports.RegistryProjectListRequest) (ports.RegistryProjectListResult, error) {
	tenantID := strings.TrimSpace(request.TenantID)
	if tenantID == "" {
		return ports.RegistryProjectListResult{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	project, err := r.getProject(ctx, tenantID)
	if err != nil {
		return ports.RegistryProjectListResult{}, err
	}
	return ports.RegistryProjectListResult{
		Items:      []ports.RegistryProject{project},
		DevProfile: harborDevProfile(),
	}, nil
}

func (r *HarborImageRegistry) ListRepositories(ctx context.Context, request ports.RegistryRepositoryListRequest) (ports.RegistryRepositoryListResult, error) {
	if err := validateTenantProject(request.TenantID, request.Project); err != nil {
		return ports.RegistryRepositoryListResult{}, err
	}
	project := strings.TrimSpace(request.Project)
	path := fmt.Sprintf("%s/projects/%s/repositories?page_size=%d", harborAPIBasePath, url.PathEscape(project), harborPageSize(request.Limit))
	var payload []harborRepository
	if err := r.doJSON(ctx, http.MethodGet, path, nil, &payload); err != nil {
		return ports.RegistryRepositoryListResult{}, err
	}
	items := make([]ports.RegistryRepository, 0, len(payload))
	for _, repo := range payload {
		items = append(items, ports.RegistryRepository{
			Project:       project,
			Name:          repositoryShortName(project, repo.Name),
			ArtifactCount: repo.ArtifactCount,
			PullCount:     repo.PullCount,
			DevProfile:    harborDevProfile(),
		})
	}
	return ports.RegistryRepositoryListResult{Items: items, DevProfile: harborDevProfile()}, nil
}

func (r *HarborImageRegistry) ListArtifacts(ctx context.Context, request ports.RegistryArtifactListRequest) (ports.RegistryArtifactListResult, error) {
	if err := validateTenantProject(request.TenantID, request.Project); err != nil {
		return ports.RegistryArtifactListResult{}, err
	}
	repository := strings.TrimSpace(request.Repository)
	if repository == "" {
		return ports.RegistryArtifactListResult{}, fmt.Errorf("%w: repository is required", ports.ErrInvalid)
	}
	project := strings.TrimSpace(request.Project)
	path := fmt.Sprintf("%s/projects/%s/repositories/%s/artifacts?with_scan_overview=true&page_size=%d",
		harborAPIBasePath, url.PathEscape(project), harborRepositoryPathSegment(repository), harborPageSize(request.Limit))
	var payload []harborArtifact
	if err := r.doJSON(ctx, http.MethodGet, path, nil, &payload); err != nil {
		return ports.RegistryArtifactListResult{}, err
	}
	items := make([]ports.RegistryArtifact, 0, len(payload))
	for _, artifact := range payload {
		items = append(items, r.artifactToPort(project, repository, artifact))
	}
	return ports.RegistryArtifactListResult{Items: items, DevProfile: harborDevProfile()}, nil
}

func (r *HarborImageRegistry) GetScanResult(ctx context.Context, request ports.RegistryScanResultRequest) (ports.RegistryScanResult, error) {
	if strings.TrimSpace(request.TenantID) == "" {
		return ports.RegistryScanResult{}, fmt.Errorf("%w: tenant_id is required", ports.ErrInvalid)
	}
	image := strings.TrimSpace(request.Image)
	if image == "" {
		return ports.RegistryScanResult{}, fmt.Errorf("%w: image is required", ports.ErrInvalid)
	}
	project, repository, reference, err := parseHarborImage(image)
	if err != nil {
		return ports.RegistryScanResult{}, err
	}
	path := fmt.Sprintf("%s/projects/%s/repositories/%s/artifacts/%s?with_scan_overview=true",
		harborAPIBasePath, url.PathEscape(project), harborRepositoryPathSegment(repository), url.PathEscape(reference))
	var artifact harborArtifact
	if err := r.doJSON(ctx, http.MethodGet, path, nil, &artifact); err != nil {
		return ports.RegistryScanResult{}, err
	}
	overview := selectScanOverview(artifact.ScanOverview)
	return ports.RegistryScanResult{
		Image:      image,
		Status:     harborScanState(overview.ScanStatus),
		Critical:   overview.Summary.Summary.Critical,
		High:       overview.Summary.Summary.High,
		Medium:     overview.Summary.Summary.Medium,
		Low:        overview.Summary.Summary.Low,
		ReportURL:  harborReportURL(overview.ReportID),
		ProviderID: harborProviderID,
		DevProfile: harborDevProfile(),
		ScannedAt:  r.now().UTC(),
	}, nil
}

func (r *HarborImageRegistry) GetProjectScanReport(ctx context.Context, request ports.RegistryProjectScanReportRequest) (ports.RegistryProjectScanReport, error) {
	if err := validateTenantProject(request.TenantID, request.Project); err != nil {
		return ports.RegistryProjectScanReport{}, err
	}
	project := strings.TrimSpace(request.Project)
	repositories, err := r.ListRepositories(ctx, ports.RegistryRepositoryListRequest{TenantID: request.TenantID, Project: project, Limit: harborDefaultPageSize})
	if err != nil {
		return ports.RegistryProjectScanReport{}, err
	}
	report := ports.RegistryProjectScanReport{
		Project:    project,
		Status:     ports.RegistryScanComplete,
		ProviderID: harborProviderID,
		DevProfile: harborDevProfile(),
		ScannedAt:  r.now().UTC(),
	}
	for _, repository := range repositories.Items {
		artifacts, err := r.ListArtifacts(ctx, ports.RegistryArtifactListRequest{
			TenantID:   request.TenantID,
			Project:    project,
			Repository: repository.Name,
			Limit:      harborDefaultPageSize,
		})
		if err != nil {
			return ports.RegistryProjectScanReport{}, err
		}
		for _, artifact := range artifacts.Items {
			report.ArtifactsTotal++
			report.Critical += artifact.ScanStatus.Critical
			report.High += artifact.ScanStatus.High
			report.Medium += artifact.ScanStatus.Medium
			report.Low += artifact.ScanStatus.Low
			if artifact.ScanStatus.Status == ports.RegistryScanComplete {
				report.ScannedArtifacts++
			}
		}
	}
	if report.ScannedArtifacts < report.ArtifactsTotal {
		report.Status = ports.RegistryScanRunning
	}
	return report, nil
}

func (r *HarborImageRegistry) SetRepositoryPermission(ctx context.Context, request ports.RegistryPermissionRequest) (ports.RegistryPermission, error) {
	if err := validateTenantProject(request.TenantID, request.Project); err != nil {
		return ports.RegistryPermission{}, err
	}
	repository := strings.TrimSpace(request.Repository)
	subject := strings.TrimSpace(request.Subject)
	if repository == "" {
		return ports.RegistryPermission{}, fmt.Errorf("%w: repository is required", ports.ErrInvalid)
	}
	if subject == "" {
		return ports.RegistryPermission{}, fmt.Errorf("%w: subject is required", ports.ErrInvalid)
	}
	if len(request.Actions) == 0 {
		return ports.RegistryPermission{}, fmt.Errorf("%w: actions are required", ports.ErrInvalid)
	}
	if strings.TrimSpace(request.IdempotencyKey) == "" {
		return ports.RegistryPermission{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	project := strings.TrimSpace(request.Project)
	state, err := r.createRobot(ctx, project, harborRobotName(subject), repository, request.Actions)
	if err != nil {
		return ports.RegistryPermission{}, err
	}
	return ports.RegistryPermission{
		Project:    project,
		Repository: repository,
		Subject:    subject,
		Actions:    append([]ports.RegistryPermissionAction(nil), request.Actions...),
		State:      state,
		DevProfile: harborDevProfile(),
		UpdatedAt:  r.now().UTC(),
	}, nil
}

func (r *HarborImageRegistry) CreatePullSecret(ctx context.Context, request ports.RegistryPullSecretRequest) (ports.RegistryPullSecret, error) {
	if err := validateTenantProject(request.TenantID, request.Project); err != nil {
		return ports.RegistryPullSecret{}, err
	}
	if strings.TrimSpace(request.IdempotencyKey) == "" {
		return ports.RegistryPullSecret{}, fmt.Errorf("%w: idempotency_key is required", ports.ErrInvalid)
	}
	name := strings.TrimSpace(request.Name)
	if name == "" {
		name = "ani-registry-pull"
	}
	project := strings.TrimSpace(request.Project)
	robotName := harborRobotName(name)
	state, err := r.createRobot(ctx, project, robotName, "*", []ports.RegistryPermissionAction{ports.RegistryPermissionPull})
	if err != nil {
		return ports.RegistryPullSecret{}, err
	}
	return ports.RegistryPullSecret{
		Project:    project,
		Name:       name,
		SecretRef:  project + "/" + name,
		Registry:   r.registryHost,
		Username:   "robot$" + project + "+" + robotName,
		Namespace:  strings.TrimSpace(request.Namespace),
		State:      state,
		DevProfile: harborDevProfile(),
		CreatedAt:  r.now().UTC(),
	}, nil
}

func (r *HarborImageRegistry) ListTags(ctx context.Context, repository string) ([]ports.ImageTag, error) {
	project, repo, _, err := parseHarborImage(repository)
	if err != nil {
		return nil, err
	}
	artifacts, err := r.ListArtifacts(ctx, ports.RegistryArtifactListRequest{TenantID: project, Project: project, Repository: repo})
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

func (r *HarborImageRegistry) GetScanStatus(ctx context.Context, ref ports.ImageRef) (ports.ImageScanStatus, error) {
	image := strings.Trim(strings.Join([]string{ref.Repository, ref.Tag}, ":"), ":")
	tenantID, _, _, err := parseHarborImage(image)
	if err != nil {
		return ports.ImageScanStatus{}, err
	}
	result, err := r.GetScanResult(ctx, ports.RegistryScanResultRequest{TenantID: tenantID, Image: image})
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

func (r *HarborImageRegistry) projectExists(ctx context.Context, name string) (bool, error) {
	path := fmt.Sprintf("%s/projects/%s", harborAPIBasePath, url.PathEscape(name))
	err := r.doJSON(ctx, http.MethodGet, path, nil, nil)
	if err == nil {
		return true, nil
	}
	if isHarborNotFound(err) {
		return false, nil
	}
	return false, err
}

func (r *HarborImageRegistry) getProject(ctx context.Context, name string) (ports.RegistryProject, error) {
	path := fmt.Sprintf("%s/projects/%s", harborAPIBasePath, url.PathEscape(name))
	var payload harborProject
	if err := r.doJSON(ctx, http.MethodGet, path, nil, &payload); err != nil {
		return ports.RegistryProject{}, err
	}
	return ports.RegistryProject{
		ID:         "harbor-" + strconv.Itoa(payload.ProjectID),
		TenantID:   name,
		Name:       payload.Name,
		Public:     strings.EqualFold(strings.TrimSpace(payload.Metadata.Public), "true"),
		DevProfile: harborDevProfile(),
		CreatedAt:  parseHarborTime(payload.CreationTime, r.now),
	}, nil
}

func (r *HarborImageRegistry) createProjectOnHarbor(ctx context.Context, name string, public bool) error {
	body := harborProjectCreate{
		ProjectName: name,
		Metadata:    harborProjectMetadata{Public: strconv.FormatBool(public)},
	}
	err := r.doJSON(ctx, http.MethodPost, harborAPIBasePath+"/projects", body, nil)
	if err == nil || isHarborConflict(err) {
		return nil
	}
	return err
}

// createRobot ensures a project-scoped Harbor robot account exists with the requested
// access. Harbor enforces uniqueness by robot name; a 409 maps to the duplicate state,
// matching the idempotent contract used by the local profile.
func (r *HarborImageRegistry) createRobot(ctx context.Context, project, robotName, repository string, actions []ports.RegistryPermissionAction) (ports.RegistryPermissionState, error) {
	access := make([]harborRobotAccess, 0, len(actions))
	for _, action := range actions {
		access = append(access, harborRobotAccess{Resource: "repository", Action: string(action)})
	}
	body := harborRobotCreate{
		Name:     robotName,
		Duration: -1,
		Level:    "project",
		Permissions: []harborRobotPermission{{
			Kind:      "project",
			Namespace: project,
			Access:    access,
		}},
	}
	err := r.doJSON(ctx, http.MethodPost, harborAPIBasePath+"/robots", body, nil)
	if err == nil {
		return ports.RegistryPermissionActive, nil
	}
	if isHarborConflict(err) {
		return ports.RegistryPermissionDuplicate, nil
	}
	return "", err
}

func (r *HarborImageRegistry) artifactToPort(project, repository string, artifact harborArtifact) ports.RegistryArtifact {
	tags := make([]string, 0, len(artifact.Tags))
	for _, tag := range artifact.Tags {
		if name := strings.TrimSpace(tag.Name); name != "" {
			tags = append(tags, name)
		}
	}
	mediaType := strings.TrimSpace(artifact.ManifestMediaType)
	if mediaType == "" {
		mediaType = strings.TrimSpace(artifact.MediaType)
	}
	overview := selectScanOverview(artifact.ScanOverview)
	pushedAt := parseHarborTime(artifact.PushTime, r.now)
	image := project + "/" + repository
	if len(tags) > 0 {
		image += ":" + tags[0]
	}
	return ports.RegistryArtifact{
		Project:    project,
		Repository: repository,
		Digest:     strings.TrimSpace(artifact.Digest),
		Tags:       tags,
		MediaType:  mediaType,
		SizeBytes:  artifact.Size,
		PushedAt:   pushedAt,
		ScanStatus: ports.RegistryScanResult{
			Image:      image,
			Status:     harborScanState(overview.ScanStatus),
			Critical:   overview.Summary.Summary.Critical,
			High:       overview.Summary.Summary.High,
			Medium:     overview.Summary.Summary.Medium,
			Low:        overview.Summary.Summary.Low,
			ReportURL:  harborReportURL(overview.ReportID),
			ProviderID: harborProviderID,
			DevProfile: harborDevProfile(),
			ScannedAt:  pushedAt,
		},
		DevProfile: harborDevProfile(),
	}
}

func (r *HarborImageRegistry) doJSON(ctx context.Context, method, path string, body any, out any) error {
	var encoded []byte
	if body != nil {
		var err error
		encoded, err = json.Marshal(body)
		if err != nil {
			return err
		}
	}
	target := *r.endpoint
	parsed, err := url.Parse(path)
	if err != nil {
		return fmt.Errorf("%w: invalid Harbor request path: %v", ports.ErrInvalid, err)
	}
	target.Path = parsed.Path
	target.RawPath = parsed.EscapedPath()
	target.RawQuery = parsed.RawQuery

	var respBody []byte
	err = resilience.Do(ctx, r.policy, func(callCtx context.Context) error {
		var reader io.Reader
		if encoded != nil {
			reader = bytes.NewReader(encoded)
		}
		req, reqErr := http.NewRequestWithContext(callCtx, method, target.String(), reader)
		if reqErr != nil {
			return reqErr
		}
		req.SetBasicAuth(r.username, r.password)
		req.Header.Set("Accept", "application/json")
		if encoded != nil {
			req.Header.Set("Content-Type", "application/json")
		}
		resp, respErr := r.client.Do(req)
		if respErr != nil {
			return respErr
		}
		defer closeHarborBody(resp.Body)
		data, _ := io.ReadAll(resp.Body)
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return resilience.NewStatusError(harborSystem, method, parsed.Path, resp.StatusCode, truncateHarborBody(data))
		}
		respBody = data
		return nil
	})
	if err != nil {
		return mapHarborError(err)
	}
	if out != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, out); err != nil {
			return fmt.Errorf("%w: invalid Harbor response: %v", ports.ErrFailedPrecondition, err)
		}
	}
	return nil
}

type harborProject struct {
	ProjectID    int                   `json:"project_id"`
	Name         string                `json:"name"`
	CreationTime string                `json:"creation_time"`
	Metadata     harborProjectMetadata `json:"metadata"`
}

type harborProjectMetadata struct {
	Public string `json:"public"`
}

type harborProjectCreate struct {
	ProjectName string                `json:"project_name"`
	Metadata    harborProjectMetadata `json:"metadata"`
}

type harborRepository struct {
	Name          string `json:"name"`
	ArtifactCount int    `json:"artifact_count"`
	PullCount     int    `json:"pull_count"`
}

type harborArtifact struct {
	Digest            string                        `json:"digest"`
	MediaType         string                        `json:"media_type"`
	ManifestMediaType string                        `json:"manifest_media_type"`
	Size              int64                         `json:"size"`
	PushTime          string                        `json:"push_time"`
	Tags              []harborArtifactTag           `json:"tags"`
	ScanOverview      map[string]harborScanOverview `json:"scan_overview"`
}

type harborArtifactTag struct {
	Name string `json:"name"`
}

type harborScanOverview struct {
	ReportID   string            `json:"report_id"`
	ScanStatus string            `json:"scan_status"`
	Severity   string            `json:"severity"`
	Summary    harborScanSummary `json:"summary"`
}

type harborScanSummary struct {
	Total   int                     `json:"total"`
	Summary harborScanSeverityCount `json:"summary"`
}

type harborScanSeverityCount struct {
	Critical int `json:"Critical"`
	High     int `json:"High"`
	Medium   int `json:"Medium"`
	Low      int `json:"Low"`
}

type harborRobotCreate struct {
	Name        string                  `json:"name"`
	Duration    int                     `json:"duration"`
	Level       string                  `json:"level"`
	Permissions []harborRobotPermission `json:"permissions"`
}

type harborRobotPermission struct {
	Kind      string              `json:"kind"`
	Namespace string              `json:"namespace"`
	Access    []harborRobotAccess `json:"access"`
}

type harborRobotAccess struct {
	Resource string `json:"resource"`
	Action   string `json:"action"`
}

func selectScanOverview(overviews map[string]harborScanOverview) harborScanOverview {
	for _, overview := range overviews {
		return overview
	}
	return harborScanOverview{}
}

func harborScanState(status string) ports.RegistryScanState {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "success", "finished", "complete":
		return ports.RegistryScanComplete
	case "running", "scanning":
		return ports.RegistryScanRunning
	case "pending", "queued":
		return ports.RegistryScanPending
	case "error", "failed":
		return ports.RegistryScanFailed
	default:
		return ports.RegistryScanNotScanned
	}
}

func harborReportURL(reportID string) string {
	reportID = strings.TrimSpace(reportID)
	if reportID == "" {
		return ""
	}
	return "harbor://scan-report/" + reportID
}

func harborDevProfile() ports.DevProfileInfo {
	return ports.DevProfileInfo{
		Mode:         "real",
		Provider:     "harbor",
		RealProvider: true,
		Reason:       "metadata is read from the Harbor v2.0 REST API over an authenticated provider connection",
	}
}

func harborPageSize(limit int) int {
	if limit <= 0 {
		return harborDefaultPageSize
	}
	return limit
}

func harborRobotName(subject string) string {
	cleaned := strings.Map(func(r rune) rune {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9', r == '-', r == '_':
			return r
		case r >= 'A' && r <= 'Z':
			return r + ('a' - 'A')
		default:
			return '-'
		}
	}, strings.TrimSpace(subject))
	cleaned = strings.Trim(cleaned, "-")
	if cleaned == "" {
		return "ani-robot"
	}
	return cleaned
}

// harborRepositoryPathSegment encodes a repository name for the Harbor path. Harbor
// expects nested separators to be double URL-encoded (a literal "/" becomes "%2F").
func harborRepositoryPathSegment(repository string) string {
	return url.PathEscape(url.PathEscape(strings.TrimSpace(repository)))
}

func repositoryShortName(project, fullName string) string {
	fullName = strings.TrimSpace(fullName)
	prefix := strings.TrimSpace(project) + "/"
	if strings.HasPrefix(fullName, prefix) {
		return strings.TrimPrefix(fullName, prefix)
	}
	return fullName
}

func parseHarborImage(image string) (project, repository, reference string, err error) {
	image = strings.TrimSpace(image)
	if image == "" {
		return "", "", "", fmt.Errorf("%w: image is required", ports.ErrInvalid)
	}
	reference = "latest"
	if at := strings.LastIndex(image, "@"); at >= 0 {
		reference = image[at+1:]
		image = image[:at]
	} else if colon := strings.LastIndex(image, ":"); colon >= 0 && !strings.Contains(image[colon+1:], "/") {
		reference = image[colon+1:]
		image = image[:colon]
	}
	slash := strings.Index(image, "/")
	if slash <= 0 || slash == len(image)-1 {
		return "", "", "", fmt.Errorf("%w: image must be project/repository[:tag]", ports.ErrInvalid)
	}
	project = image[:slash]
	repository = image[slash+1:]
	if strings.TrimSpace(reference) == "" {
		reference = "latest"
	}
	return project, repository, reference, nil
}

func parseHarborEndpoint(raw string, secure bool) (*url.URL, error) {
	endpoint := strings.TrimSpace(raw)
	if endpoint == "" {
		return nil, fmt.Errorf("%w: Harbor endpoint is required", ports.ErrInvalid)
	}
	if !strings.Contains(endpoint, "://") {
		scheme := "http"
		if secure {
			scheme = "https"
		}
		endpoint = scheme + "://" + endpoint
	}
	parsed, err := url.Parse(endpoint)
	if err != nil {
		return nil, fmt.Errorf("%w: invalid Harbor endpoint: %v", ports.ErrInvalid, err)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, fmt.Errorf("%w: Harbor endpoint scheme must be http or https", ports.ErrInvalid)
	}
	if parsed.Host == "" {
		return nil, fmt.Errorf("%w: Harbor endpoint host is required", ports.ErrInvalid)
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/")
	parsed.RawQuery = ""
	parsed.Fragment = ""
	return parsed, nil
}

func parseHarborTime(raw string, now func() time.Time) time.Time {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return now().UTC()
	}
	if parsed, err := time.Parse(time.RFC3339Nano, raw); err == nil {
		return parsed.UTC()
	}
	if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
		return parsed.UTC()
	}
	return now().UTC()
}

func mapHarborError(err error) error {
	var statusErr *resilience.StatusError
	if !errors.As(err, &statusErr) {
		return err
	}
	switch statusErr.StatusCode {
	case http.StatusNotFound:
		return ports.ErrNotFound
	case http.StatusConflict:
		return ports.ErrConflict
	case http.StatusBadRequest, http.StatusUnauthorized, http.StatusForbidden:
		return fmt.Errorf("%w: %s", ports.ErrFailedPrecondition, statusErr.Error())
	default:
		return statusErr
	}
}

func isHarborNotFound(err error) bool {
	return errors.Is(err, ports.ErrNotFound)
}

func isHarborConflict(err error) bool {
	return errors.Is(err, ports.ErrConflict)
}

func truncateHarborBody(data []byte) string {
	const limit = 256
	body := strings.TrimSpace(string(data))
	if len(body) > limit {
		return body[:limit]
	}
	return body
}

func closeHarborBody(body io.Closer) {
	if body != nil {
		_ = body.Close()
	}
}
