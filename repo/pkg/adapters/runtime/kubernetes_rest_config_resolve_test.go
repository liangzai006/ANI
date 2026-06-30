package runtime

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveKubernetesRESTClientConfigPrefersExplicitEnv(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "true")
	t.Setenv("KUBECONFIG", filepath.Join(t.TempDir(), "missing.kubeconfig"))

	cfg, source, err := ResolveKubernetesRESTClientConfig(KubernetesRESTClientConfig{
		Host:        "https://explicit.example.test",
		BearerToken: "explicit-token",
	})
	if err != nil {
		t.Fatalf("ResolveKubernetesRESTClientConfig() error = %v", err)
	}
	if source != KubernetesRESTCredentialExplicitEnv {
		t.Fatalf("source = %q, want explicit_env", source)
	}
	if cfg.Host != "https://explicit.example.test" || cfg.BearerToken != "explicit-token" {
		t.Fatalf("cfg = %#v, want explicit host/token", cfg)
	}
}

func TestResolveKubernetesRESTClientConfigLoadsKubeconfig(t *testing.T) {
	kubeconfigPath := filepath.Join(t.TempDir(), "config")
	if err := os.WriteFile(kubeconfigPath, []byte(`apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://kubeconfig.example.test
    insecure-skip-tls-verify: true
  name: test
contexts:
- context:
    cluster: test
    user: test
  name: test
current-context: test
users:
- name: test
  user:
    token: kubeconfig-token
`), 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "true")
	t.Setenv("KUBECONFIG", kubeconfigPath)

	cfg, source, err := ResolveKubernetesRESTClientConfig(KubernetesRESTClientConfig{})
	if err != nil {
		t.Fatalf("ResolveKubernetesRESTClientConfig() error = %v", err)
	}
	if source != KubernetesRESTCredentialKubeconfig {
		t.Fatalf("source = %q, want kubeconfig", source)
	}
	if cfg.Host != "https://kubeconfig.example.test" {
		t.Fatalf("host = %q, want kubeconfig server", cfg.Host)
	}
	if cfg.BearerToken != "kubeconfig-token" {
		t.Fatalf("token = %q, want kubeconfig token", cfg.BearerToken)
	}
	if cfg.HTTPClient == nil {
		t.Fatal("HTTPClient = nil, want kubeconfig transport")
	}
}

func TestResolveKubernetesRESTClientConfigLoadsInClusterServiceAccount(t *testing.T) {
	tokenPath := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(tokenPath, []byte("service-account-token"), 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "true")
	t.Setenv("KUBECONFIG", filepath.Join(t.TempDir(), "missing.kubeconfig"))
	t.Setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
	t.Setenv("KUBERNETES_SERVICE_PORT", "8443")
	t.Setenv("KUBERNETES_SERVICE_ACCOUNT_TOKEN_FILE", tokenPath)

	cfg, source, err := ResolveKubernetesRESTClientConfig(KubernetesRESTClientConfig{})
	if err != nil {
		t.Fatalf("ResolveKubernetesRESTClientConfig() error = %v", err)
	}
	if source != KubernetesRESTCredentialInCluster {
		t.Fatalf("source = %q, want in_cluster", source)
	}
	if cfg.ServiceHost != "10.96.0.1" || cfg.ServicePort != "8443" {
		t.Fatalf("service host/port = %q/%q", cfg.ServiceHost, cfg.ServicePort)
	}
	if cfg.BearerTokenFile != tokenPath {
		t.Fatalf("BearerTokenFile = %q, want %q", cfg.BearerTokenFile, tokenPath)
	}
}

func TestResolveKubernetesRESTClientConfigDisabledAutoLoad(t *testing.T) {
	t.Setenv("KUBERNETES_CONFIG_AUTO_LOAD", "false")
	t.Setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")

	_, _, err := ResolveKubernetesRESTClientConfig(KubernetesRESTClientConfig{})
	if err == nil {
		t.Fatal("ResolveKubernetesRESTClientConfig() error = nil, want missing credentials error")
	}
	if !strings.Contains(err.Error(), "invalid") {
		t.Fatalf("error = %v, want invalid credentials error", err)
	}
}

func TestLoadKubernetesRESTEnvFromOSIncludesRequestTimeout(t *testing.T) {
	t.Setenv("KUBERNETES_REQUEST_TIMEOUT", "15s")
	t.Setenv("KUBERNETES_API_HOST", "https://kubernetes.example.test")

	env := LoadKubernetesRESTEnvFromOS()
	if env.APIHost != "https://kubernetes.example.test" {
		t.Fatalf("APIHost = %q, want kubernetes.example.test", env.APIHost)
	}
	if env.RequestTimeout.String() != "15s" {
		t.Fatalf("RequestTimeout = %s, want 15s", env.RequestTimeout)
	}
}
