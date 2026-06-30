package registry

import "testing"

func TestHarborProviderProjectNameMapsTenantScopedProjects(t *testing.T) {
	tenantID := "00000000-0000-0000-0000-000000000001"
	got := harborProviderProjectName(tenantID, "my-backend")
	want := "ani-00000000000000000000000000000001-my-backend"
	if got != want {
		t.Fatalf("harbor name = %q, want %q", got, want)
	}
}

func TestHarborProviderProjectNameLegacyTenantIDName(t *testing.T) {
	tenantID := "00000000-0000-0000-0000-000000000001"
	if got := harborProviderProjectName(tenantID, tenantID); got != tenantID {
		t.Fatalf("legacy harbor name = %q, want tenant id", got)
	}
}

func TestAniProjectNameFromHarborRoundTrip(t *testing.T) {
	tenantID := "tenant-a"
	aniName := "runtime"
	harborName := harborProviderProjectName(tenantID, aniName)
	got, ok := aniProjectNameFromHarbor(tenantID, harborName)
	if !ok || got != aniName {
		t.Fatalf("decoded = %q ok=%v, want %q", got, ok, aniName)
	}
}

func TestValidateRegistryProjectNameRejectsInvalid(t *testing.T) {
	cases := []string{"", "-bad", "bad..name", "has space"}
	for _, name := range cases {
		if err := validateRegistryProjectName(name); err == nil {
			t.Fatalf("validateRegistryProjectName(%q) = nil, want error", name)
		}
	}
}

func TestResolveImageProjectNamesAcceptsANIAndHarborNames(t *testing.T) {
	tenantID := "tenant-a"
	harborName, aniName, err := resolveImageProjectNames(tenantID, "my-app")
	if err != nil || aniName != "my-app" || harborName != harborProviderProjectName(tenantID, "my-app") {
		t.Fatalf("ani resolve = %q/%q err=%v", harborName, aniName, err)
	}
	harborName = harborProviderProjectName(tenantID, "my-app")
	harborName, aniName, err = resolveImageProjectNames(tenantID, harborName)
	if err != nil || aniName != "my-app" {
		t.Fatalf("harbor resolve = %q/%q err=%v", harborName, aniName, err)
	}
}
