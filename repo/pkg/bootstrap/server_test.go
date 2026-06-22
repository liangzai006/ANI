package bootstrap

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/kubercloud/ani/pkg/ports"
)

func TestConfigEnvironmentOverridesWorkloadReconcileController(t *testing.T) {
	t.Setenv("WORKLOAD_RECONCILE_CONTROLLER_ENABLED", "true")
	t.Setenv("WORKLOAD_RECONCILE_NORMAL_INTERVAL_SECONDS", "45")
	t.Setenv("WORKLOAD_RECONCILE_ACTIVE_INTERVAL_SECONDS", "7")
	t.Setenv("WORKLOAD_RECONCILE_STALE_THRESHOLD_SECONDS", "180")
	t.Setenv("WORKLOAD_RECONCILE_MAX_BATCH", "12")
	t.Setenv("WORKLOAD_RECONCILE_FAILURE_BACKOFF_SECONDS", "90")
	t.Setenv("WORKLOAD_RECONCILE_LEADER_ELECTION_ENABLED", "true")
	t.Setenv("WORKLOAD_RECONCILE_LEADER_IDENTITY", "worker-a")
	t.Setenv("WORKLOAD_RECONCILE_LEADER_LEASE_NAME", "workload-reconcile")
	t.Setenv("WORKLOAD_RECONCILE_LEADER_LEASE_TTL_SECONDS", "60")
	t.Setenv("WORKLOAD_RECONCILE_LEADER_RENEW_INTERVAL_SECONDS", "15")

	cfg := (Config{}).withEnvironmentOverrides()

	if !cfg.WorkloadReconcileControllerEnabled {
		t.Fatalf("WorkloadReconcileControllerEnabled = false, want true")
	}
	if cfg.WorkloadReconcileNormalInterval != 45 {
		t.Fatalf("WorkloadReconcileNormalInterval = %d, want 45", cfg.WorkloadReconcileNormalInterval)
	}
	if cfg.WorkloadReconcileActiveInterval != 7 {
		t.Fatalf("WorkloadReconcileActiveInterval = %d, want 7", cfg.WorkloadReconcileActiveInterval)
	}
	if cfg.WorkloadReconcileStaleThreshold != 180 {
		t.Fatalf("WorkloadReconcileStaleThreshold = %d, want 180", cfg.WorkloadReconcileStaleThreshold)
	}
	if cfg.WorkloadReconcileMaxBatch != 12 {
		t.Fatalf("WorkloadReconcileMaxBatch = %d, want 12", cfg.WorkloadReconcileMaxBatch)
	}
	if cfg.WorkloadReconcileFailureBackoff != 90 {
		t.Fatalf("WorkloadReconcileFailureBackoff = %d, want 90", cfg.WorkloadReconcileFailureBackoff)
	}
	if !cfg.WorkloadReconcileLeaderElectionEnabled {
		t.Fatalf("WorkloadReconcileLeaderElectionEnabled = false, want true")
	}
	if cfg.WorkloadReconcileLeaderIdentity != "worker-a" {
		t.Fatalf("WorkloadReconcileLeaderIdentity = %q, want worker-a", cfg.WorkloadReconcileLeaderIdentity)
	}
	if cfg.WorkloadReconcileLeaderLeaseName != "workload-reconcile" {
		t.Fatalf("WorkloadReconcileLeaderLeaseName = %q, want workload-reconcile", cfg.WorkloadReconcileLeaderLeaseName)
	}
	if cfg.WorkloadReconcileLeaderLeaseTTL != 60 {
		t.Fatalf("WorkloadReconcileLeaderLeaseTTL = %d, want 60", cfg.WorkloadReconcileLeaderLeaseTTL)
	}
	if cfg.WorkloadReconcileLeaderRenewInterval != 15 {
		t.Fatalf("WorkloadReconcileLeaderRenewInterval = %d, want 15", cfg.WorkloadReconcileLeaderRenewInterval)
	}
	reconcileCfg := reconcileControllerConfig(cfg)
	if reconcileCfg.FailureBackoffSeconds != 90 {
		t.Fatalf("FailureBackoffSeconds = %d, want 90", reconcileCfg.FailureBackoffSeconds)
	}
}

func TestConfigEnvironmentOverridesRedisFailover(t *testing.T) {
	t.Setenv("REDIS_MODE", "sentinel")
	t.Setenv("REDIS_ADDRS", "redis-sentinel-a:26379,redis-sentinel-b:26379")
	t.Setenv("REDIS_MASTER_NAME", "ani-redis")
	t.Setenv("REDIS_USERNAME", "ani")
	t.Setenv("REDIS_PASSWORD", "secret")
	t.Setenv("REDIS_DB", "2")

	cfg := (Config{}).withEnvironmentOverrides()

	if cfg.RedisMode != "sentinel" || cfg.RedisMasterName != "ani-redis" {
		t.Fatalf("redis mode/master = %q/%q, want sentinel/ani-redis", cfg.RedisMode, cfg.RedisMasterName)
	}
	if len(cfg.RedisAddrs) != 2 || cfg.RedisAddrs[0] != "redis-sentinel-a:26379" || cfg.RedisAddrs[1] != "redis-sentinel-b:26379" {
		t.Fatalf("redis addrs = %#v, want sentinel addrs", cfg.RedisAddrs)
	}
	if cfg.RedisUsername != "ani" || cfg.RedisPassword != "secret" || cfg.RedisDB != 2 {
		t.Fatalf("redis auth/db = %q/%q/%d, want ani/secret/2", cfg.RedisUsername, cfg.RedisPassword, cfg.RedisDB)
	}
}

func TestConfigEnvironmentOverridesNetworkProvider(t *testing.T) {
	t.Setenv("NETWORK_PROVIDER", "kubeovn_rest")
	t.Setenv("NETWORK_PROVIDER_APPLY_ENABLED", "true")
	t.Setenv("NETWORK_PROVIDER_USER_ID", "ani-core-network-provider")
	t.Setenv("NETWORK_PROVIDER_PERMISSION_PROOF", "rbac-scope:networks.write")

	cfg := (Config{}).withEnvironmentOverrides()

	if cfg.NetworkProvider != "kubeovn_rest" {
		t.Fatalf("NetworkProvider = %q, want kubeovn_rest", cfg.NetworkProvider)
	}
	if !cfg.NetworkProviderApplyEnabled {
		t.Fatalf("NetworkProviderApplyEnabled = false, want true")
	}
	if cfg.NetworkProviderUserID != "ani-core-network-provider" {
		t.Fatalf("NetworkProviderUserID = %q, want ani-core-network-provider", cfg.NetworkProviderUserID)
	}
	if cfg.NetworkProviderPermissionProof != "rbac-scope:networks.write" {
		t.Fatalf("NetworkProviderPermissionProof = %q, want rbac scope proof", cfg.NetworkProviderPermissionProof)
	}
}

func TestConfigEnvironmentOverridesStorageProvider(t *testing.T) {
	t.Setenv("STORAGE_PROVIDER", "kubernetes_rest")
	t.Setenv("STORAGE_PROVIDER_APPLY_ENABLED", "true")
	t.Setenv("STORAGE_PROVIDER_USER_ID", "ani-core-storage-provider")
	t.Setenv("STORAGE_PROVIDER_PERMISSION_PROOF", "rbac-scope:storage.write")

	cfg := (Config{}).withEnvironmentOverrides()

	if cfg.StorageProvider != "kubernetes_rest" {
		t.Fatalf("StorageProvider = %q, want kubernetes_rest", cfg.StorageProvider)
	}
	if !cfg.StorageProviderApplyEnabled {
		t.Fatalf("StorageProviderApplyEnabled = false, want true")
	}
	if cfg.StorageProviderUserID != "ani-core-storage-provider" {
		t.Fatalf("StorageProviderUserID = %q, want ani-core-storage-provider", cfg.StorageProviderUserID)
	}
	if cfg.StorageProviderPermissionProof != "rbac-scope:storage.write" {
		t.Fatalf("StorageProviderPermissionProof = %q, want storage write proof", cfg.StorageProviderPermissionProof)
	}
}

func TestConfigEnvironmentOverridesGPUInventoryProvider(t *testing.T) {
	t.Setenv("GPU_INVENTORY_PROVIDER", "kubernetes_rest")

	cfg := (Config{}).withEnvironmentOverrides()

	if cfg.GPUInventoryProvider != "kubernetes_rest" {
		t.Fatalf("GPUInventoryProvider = %q, want kubernetes_rest", cfg.GPUInventoryProvider)
	}
}

func TestConfigEnvironmentOverridesInClusterKubernetesServiceAccount(t *testing.T) {
	t.Setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
	t.Setenv("KUBERNETES_SERVICE_PORT", "443")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE", "/var/run/secrets/kubernetes.io/serviceaccount/token")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_CA_FILE", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")

	cfg := (Config{}).withEnvironmentOverrides()

	if cfg.KubernetesServiceHost != "10.96.0.1" || cfg.KubernetesServicePort != "443" {
		t.Fatalf("KubernetesServiceHost/Port = %q/%q, want in-cluster service", cfg.KubernetesServiceHost, cfg.KubernetesServicePort)
	}
	if cfg.KubernetesServiceAccountTokenFile == "" || cfg.KubernetesServiceAccountCAFile == "" {
		t.Fatalf("service account token/CA files = %q/%q, want configured files", cfg.KubernetesServiceAccountTokenFile, cfg.KubernetesServiceAccountCAFile)
	}
}

func TestStartWorkloadReconcileControllerRequiresOptIn(t *testing.T) {
	controller := &fakeWorkloadReconcileController{
		started: make(chan struct{}),
		stopped: make(chan struct{}),
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	deps := &Deps{
		Logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Ports:  Capabilities{WorkloadController: controller},
	}

	if started := startWorkloadReconcileController(ctx, deps); started {
		t.Fatalf("startWorkloadReconcileController() = true, want false when disabled")
	}

	deps.WorkloadReconcileControllerEnabled = true
	if started := startWorkloadReconcileController(ctx, deps); !started {
		t.Fatalf("startWorkloadReconcileController() = false, want true when enabled")
	}
	select {
	case <-controller.started:
	case <-time.After(time.Second):
		t.Fatalf("controller did not start before context cancelled")
	}
	cancel()
	select {
	case <-controller.stopped:
	case <-time.After(time.Second):
		t.Fatalf("controller did not stop after context cancellation")
	}
}

func TestRunWorkloadReconcileWorkerStartsControllerWithoutGRPC(t *testing.T) {
	controller := &fakeWorkloadReconcileController{
		started: make(chan struct{}),
		stopped: make(chan struct{}),
	}
	ctx, cancel := context.WithCancel(context.Background())
	deps := &Deps{
		Logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
		Ports:  Capabilities{WorkloadController: controller},
	}

	done := make(chan struct{})
	go func() {
		runWorkloadReconcileWorker(ctx, deps)
		close(done)
	}()

	select {
	case <-controller.started:
	case <-time.After(time.Second):
		t.Fatalf("worker did not start controller")
	}
	cancel()
	select {
	case <-controller.stopped:
	case <-time.After(time.Second):
		t.Fatalf("worker did not stop controller after context cancellation")
	}
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatalf("worker did not return after context cancellation")
	}
}

type fakeWorkloadReconcileController struct {
	started chan struct{}
	stopped chan struct{}
}

func (c *fakeWorkloadReconcileController) Start(ctx context.Context) error {
	close(c.started)
	<-ctx.Done()
	close(c.stopped)
	return nil
}

func (*fakeWorkloadReconcileController) ReconcileNow(context.Context, ports.ReconcileTarget) (ports.ReconcileResult, error) {
	return ports.ReconcileResult{}, nil
}

var _ ports.WorkloadReconcileController = (*fakeWorkloadReconcileController)(nil)
