package service

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	authv1 "github.com/kubercloud/ani/pkg/generated/pb/auth/v1"
)

func TestOIDCRefreshValidateFlow(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	issuedAt := time.Unix(1_700_000_000, 0)
	cache := newMemoryCache()
	tenantID := uuid.New()
	userID := uuid.New()
	refreshStore := newMutableRefreshStore()

	issuer, err := NewJWTIssuer(JWTConfig{
		PrivateKeyPEM: privateKeyPEM(t, key),
		Issuer:        "ani-test",
	})
	if err != nil {
		t.Fatalf("NewJWTIssuer: %v", err)
	}
	issuer.now = func() time.Time { return issuedAt }
	validator, err := NewJWTValidator(JWTConfig{
		PublicKeyPEM: publicKeyPEM(t, &key.PublicKey),
		Issuer:       "ani-test",
	}, newTokenBlocklist(nil, cache))
	if err != nil {
		t.Fatalf("NewJWTValidator: %v", err)
	}
	validator.now = func() time.Time { return issuedAt.Add(time.Minute) }

	svc := &AuthService{
		jwt:           validator,
		issuer:        issuer,
		refreshTokens: refreshStore,
		blocklist:     newTokenBlocklist(nil, cache),
		oidc: newOIDCLoginManager(cache, JWTConfig{
			OIDCAuthURL:  "https://dex.example.test/auth",
			OIDCClientID: "ani-console",
		}, fakeOIDCSessionStore{
			principal: refreshPrincipal{TenantID: tenantID, UserID: userID, Roles: []string{"tenant-admin"}},
			token:     "refresh-from-oidc",
		}, issuer),
	}
	svc.oidc.exchanger = fakeOIDCExchanger{idToken: "id-token"}
	begin, err := svc.BeginOIDCLogin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("BeginOIDCLogin: %v", err)
	}
	svc.oidc.verifier = fakeOIDCVerifier{claims: oidcClaims{
		Subject: "sub-1",
		Email:   "user@example.test",
		Groups:  []string{"ani-admins"},
		Nonce:   oidCTestNonce(t, begin.GetAuthorizationUrl()),
	}}
	pair, err := svc.CompleteOIDCLogin(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       begin.GetState(),
		Code:        "code-1",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("CompleteOIDCLogin: %v", err)
	}
	if pair.GetRefreshToken() != "refresh-from-oidc" {
		t.Fatalf("refresh token = %q", pair.GetRefreshToken())
	}
	refreshStore.tokens[pair.GetRefreshToken()] = refreshPrincipal{TenantID: tenantID, UserID: userID, Roles: []string{"tenant-admin"}}

	refreshed, err := svc.RefreshToken(context.Background(), &authv1.RefreshTokenRequest{RefreshToken: pair.GetRefreshToken()})
	if err != nil {
		t.Fatalf("RefreshToken: %v", err)
	}
	tc, err := svc.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{Token: refreshed.GetAccessToken()})
	if err != nil {
		t.Fatalf("ValidateToken: %v", err)
	}
	if tc.GetTenantId() != tenantID.String() || tc.GetUserId() != userID.String() {
		t.Fatalf("tenant/user = %s/%s", tc.GetTenantId(), tc.GetUserId())
	}
	if len(tc.GetRoles()) != 1 || tc.GetRoles()[0] != "tenant-admin" {
		t.Fatalf("roles = %v", tc.GetRoles())
	}
}

func TestOIDCLoginWithDexCompatibleTokenAndJWKS(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	jwksData, err := json.Marshal(map[string]any{
		"keys": []map[string]any{rsaPublicJWK("dex-kid-1", &key.PublicKey)},
	})
	if err != nil {
		t.Fatalf("marshal jwks: %v", err)
	}

	var issuedIDToken string
	tokenRequests := 0
	issuerURL := "https://dex.example.test/dex"
	tokenURL := issuerURL + "/token"
	jwksURL := issuerURL + "/keys"
	httpClient := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		switch r.URL.String() {
		case tokenURL:
			if r.Method != http.MethodPost {
				t.Fatalf("token method = %s", r.Method)
			}
			if err := r.ParseForm(); err != nil {
				t.Fatalf("parse token form: %v", err)
			}
			want := map[string]string{
				"grant_type":    "authorization_code",
				"code":          "dex-code-1",
				"redirect_uri":  "https://console.example.test/callback",
				"client_id":     "ani-console",
				"client_secret": "ani-console-secret",
			}
			for key, value := range want {
				if got := r.Form.Get(key); got != value {
					t.Fatalf("%s = %q, want %q", key, got, value)
				}
			}
			tokenRequests++
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader(`{"id_token":"` + issuedIDToken + `"}`)),
				Header:     http.Header{"Content-Type": []string{"application/json"}},
			}, nil
		case jwksURL:
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader(string(jwksData))),
				Header:     http.Header{"Content-Type": []string{"application/json"}},
			}, nil
		default:
			return &http.Response{
				StatusCode: http.StatusNotFound,
				Body:       io.NopCloser(strings.NewReader("not found")),
				Header:     make(http.Header),
			}, nil
		}
	})}

	issuedAt := time.Unix(1_700_000_000, 0)
	cache := newMemoryCache()
	tenantID := uuid.New()
	userID := uuid.New()
	issuer, err := NewJWTIssuer(JWTConfig{
		PrivateKeyPEM: privateKeyPEM(t, key),
		Issuer:        "ani-test",
	})
	if err != nil {
		t.Fatalf("NewJWTIssuer: %v", err)
	}
	issuer.now = func() time.Time { return issuedAt }
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:      issuerURL + "/auth",
		OIDCTokenURL:     tokenURL,
		OIDCJWKSURL:      jwksURL,
		OIDCIssuerURL:    issuerURL,
		OIDCClientID:     "ani-console",
		OIDCClientSecret: "ani-console-secret",
	}, fakeOIDCSessionStore{
		principal: refreshPrincipal{TenantID: tenantID, UserID: userID, Roles: []string{"tenant-admin"}},
		token:     "refresh-from-dex",
	}, issuer)
	exchanger, ok := manager.exchanger.(oidcHTTPExchanger)
	if !ok {
		t.Fatalf("exchanger = %T", manager.exchanger)
	}
	exchanger.httpClient = httpClient
	manager.exchanger = exchanger
	jwksVerifier, ok := manager.verifier.(*oidcJWKSVerifier)
	if !ok {
		t.Fatalf("verifier = %T", manager.verifier)
	}
	jwksVerifier.httpClient = httpClient
	jwksVerifier.now = func() time.Time { return issuedAt.Add(time.Minute) }

	begin, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	nonce := oidCTestNonce(t, begin.GetAuthorizationUrl())
	if !strings.Contains(begin.GetAuthorizationUrl(), issuerURL+"/auth") {
		t.Fatalf("authorization url = %q", begin.GetAuthorizationUrl())
	}
	issuedIDToken = signOIDCTestJWT(t, key, "dex-kid-1", map[string]any{
		"iss":    issuerURL,
		"sub":    "dex-user-1",
		"aud":    "ani-console",
		"exp":    issuedAt.Add(time.Hour).Unix(),
		"email":  "user@example.test",
		"name":   "Dex User",
		"groups": []string{"tenant-admin"},
		"nonce":  nonce,
	})

	resp, err := manager.Complete(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       begin.GetState(),
		Code:        "dex-code-1",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if resp.GetAccessToken() == "" || resp.GetRefreshToken() != "refresh-from-dex" {
		t.Fatalf("unexpected token pair: %#v", resp)
	}
	if tokenRequests != 1 {
		t.Fatalf("tokenRequests = %d", tokenRequests)
	}
}

type mutableRefreshStore struct {
	tokens map[string]refreshPrincipal
}

func newMutableRefreshStore() *mutableRefreshStore {
	return &mutableRefreshStore{tokens: map[string]refreshPrincipal{}}
}

func (s *mutableRefreshStore) Validate(_ context.Context, rawToken string) (refreshPrincipal, error) {
	principal, ok := s.tokens[rawToken]
	if !ok {
		return refreshPrincipal{}, errInvalidJWT
	}
	return principal, nil
}
