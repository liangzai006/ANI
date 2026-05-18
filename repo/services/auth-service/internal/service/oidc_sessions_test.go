package service

import (
	"reflect"
	"testing"
)

func TestOIDCGroupRoleMapperDefaultsToUser(t *testing.T) {
	mapper := newOIDCGroupRoleMapper("")
	got := mapper.Map([]string{"platform-admin", "tenant-admin"})
	want := []string{"user"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("roles = %v, want %v", got, want)
	}
}

func TestOIDCGroupRoleMapperUsesExplicitMappings(t *testing.T) {
	mapper := newOIDCGroupRoleMapper(`{
		"/corp/ani-admins": ["tenant-admin"],
		"CN=ANI-Auditors": ["auditor"],
		"bad": ["root"]
	}`)
	got := mapper.Map([]string{"/corp/ani-admins", "cn=ani-auditors", "bad"})
	want := []string{"auditor", "tenant-admin"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("roles = %v, want %v", got, want)
	}
}

func TestOIDCGroupRoleMapperNormalizesConfiguredRoles(t *testing.T) {
	mapper := newOIDCGroupRoleMapper(`{
		"CN=ANI-Admins": [" Tenant-Admin ", "AUDITOR", "root"]
	}`)
	got := mapper.Map([]string{"cn=ani-admins"})
	want := []string{"auditor", "tenant-admin"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("roles = %v, want %v", got, want)
	}
}
