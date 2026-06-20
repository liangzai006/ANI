package types

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// TenantCtxKey is the context key for TenantContext. Unexported to prevent collisions.
type tenantCtxKey struct{}

// TenantContext holds the authenticated identity for the current request.
// It is injected by the Auth middleware and must be present in every
// authenticated request context.
type TenantContext struct {
	TenantID uuid.UUID // always set
	UserID   uuid.UUID // zero UUID when request uses an API Key
	Roles    []string  // e.g. ["tenant-admin", "user"]
}

// WithTenant returns a new context carrying tc. Called by Auth middleware.
func WithTenant(ctx context.Context, tc *TenantContext) context.Context {
	return context.WithValue(ctx, tenantCtxKey{}, tc)
}

// FromContext extracts TenantContext from ctx.
// Panics if not present — this indicates a programming error (Auth middleware was bypassed).
func FromContext(ctx context.Context) *TenantContext {
	v := ctx.Value(tenantCtxKey{})
	if v == nil {
		panic("types.FromContext: tenant context missing — Auth middleware was not applied")
	}
	return v.(*TenantContext)
}

// TryFromContext extracts TenantContext without panicking.
// Returns (nil, false) if not present.
func TryFromContext(ctx context.Context) (*TenantContext, bool) {
	v := ctx.Value(tenantCtxKey{})
	if v == nil {
		return nil, false
	}
	return v.(*TenantContext), true
}

// SetDBTenant sets the PostgreSQL session variable required by RLS policies.
// Must be called inside every transaction before any DML.
//
// The query uses SET LOCAL so the variable is scoped to the current transaction
// and cannot leak to other connections in the PgBouncer pool.
func SetDBTenant(ctx context.Context, tx pgx.Tx) error {
	tc := FromContext(ctx)
	_, err := tx.Exec(ctx,
		"SELECT set_config('app.current_tenant_id', $1, true)",
		tc.TenantID.String(),
	)
	if err != nil {
		return fmt.Errorf("SetDBTenant: %w", err)
	}
	return nil
}

// HasRole returns true if the tenant context contains the given role.
func (tc *TenantContext) HasRole(role string) bool {
	for _, r := range tc.Roles {
		if r == role {
			return true
		}
	}
	return false
}
