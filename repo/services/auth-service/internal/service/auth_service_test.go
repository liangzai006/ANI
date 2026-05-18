package service

import (
	"context"
	"testing"

	"github.com/google/uuid"
	authv1 "github.com/kubercloud/ani/pkg/generated/pb/auth/v1"
)

func TestCheckPermissionHonorsAPIKeyScopes(t *testing.T) {
	svc := &AuthService{}
	tenantID := uuid.New().String()

	allowed, err := svc.CheckPermission(context.Background(), &authv1.CheckPermissionRequest{
		TenantId: tenantID,
		Roles:    []string{"service-account", "scope:instances:create"},
		Resource: "instances",
		Action:   "create",
	})
	if err != nil {
		t.Fatalf("CheckPermission allow error: %v", err)
	}
	if !allowed.GetAllowed() {
		t.Fatalf("scope should allow create, got deny: %s", allowed.GetReason())
	}

	denied, err := svc.CheckPermission(context.Background(), &authv1.CheckPermissionRequest{
		TenantId: tenantID,
		Roles:    []string{"service-account", "scope:instances:create"},
		Resource: "instances",
		Action:   "delete",
	})
	if err != nil {
		t.Fatalf("CheckPermission deny error: %v", err)
	}
	if denied.GetAllowed() {
		t.Fatal("create-only scope unexpectedly allowed delete")
	}
}

func TestCheckPermissionHonorsAPIKeyWildcardScope(t *testing.T) {
	svc := &AuthService{}
	resp, err := svc.CheckPermission(context.Background(), &authv1.CheckPermissionRequest{
		TenantId: uuid.New().String(),
		Roles:    []string{"service-account", "scope:instances:*"},
		Resource: "instances",
		Action:   "delete",
	})
	if err != nil {
		t.Fatalf("CheckPermission error: %v", err)
	}
	if !resp.GetAllowed() {
		t.Fatalf("wildcard scope should allow delete, got deny: %s", resp.GetReason())
	}
}
