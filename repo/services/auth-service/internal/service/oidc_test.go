package service

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	authv1 "github.com/kubercloud/ani/pkg/generated/pb/auth/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestBeginOIDCLoginStoresStateAndBuildsAuthorizationURL(t *testing.T) {
	cache := newMemoryCache()
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, nil, nil)

	resp, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	if resp.GetState() == "" {
		t.Fatal("expected state")
	}
	if _, err := cache.Get(context.Background(), "oidc:state:"+resp.GetState()); err != nil {
		t.Fatalf("state was not stored: %v", err)
	}

	parsed, err := url.Parse(resp.GetAuthorizationUrl())
	if err != nil {
		t.Fatalf("parse authorization url: %v", err)
	}
	query := parsed.Query()
	if query.Get("client_id") != "ani-console" {
		t.Fatalf("client_id = %q", query.Get("client_id"))
	}
	if query.Get("redirect_uri") != "https://console.example.test/callback" {
		t.Fatalf("redirect_uri = %q", query.Get("redirect_uri"))
	}
	if query.Get("state") != resp.GetState() {
		t.Fatalf("state query = %q", query.Get("state"))
	}
	if query.Get("nonce") == "" {
		t.Fatalf("nonce query is empty")
	}
	stateBytes, err := cache.Get(context.Background(), "oidc:state:"+resp.GetState())
	if err != nil {
		t.Fatalf("read state: %v", err)
	}
	stateRecord, err := decodeOIDCState(stateBytes)
	if err != nil {
		t.Fatalf("decode state: %v", err)
	}
	if stateRecord.Nonce != query.Get("nonce") {
		t.Fatalf("state nonce = %q, query nonce = %q", stateRecord.Nonce, query.Get("nonce"))
	}
}

func TestBeginOIDCLoginRejectsInvalidRedirectURI(t *testing.T) {
	manager := newOIDCLoginManager(newMemoryCache(), JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, nil, nil)

	for _, redirectURI := range []string{
		"/callback",
		"javascript:alert(1)",
		"https://console.example.test/callback#token",
	} {
		_, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
			TenantName:  "tenant-a",
			RedirectUri: redirectURI,
		})
		if status.Code(err) != codes.InvalidArgument {
			t.Fatalf("Begin redirect_uri %q error = %v, want InvalidArgument", redirectURI, err)
		}
	}
}

func TestOIDCLoginManagerUsesDexIssuerDefaults(t *testing.T) {
	manager := newOIDCLoginManager(newMemoryCache(), JWTConfig{
		OIDCIssuerURL:    "https://dex.example.test/dex/",
		OIDCClientID:     "ani-console",
		OIDCClientSecret: "ani-console-secret",
	}, nil, nil)

	if manager.authURL != "https://dex.example.test/dex/auth" {
		t.Fatalf("authURL = %q", manager.authURL)
	}
	exchanger, ok := manager.exchanger.(oidcHTTPExchanger)
	if !ok {
		t.Fatalf("exchanger = %T", manager.exchanger)
	}
	if exchanger.tokenURL != "https://dex.example.test/dex/token" {
		t.Fatalf("tokenURL = %q", exchanger.tokenURL)
	}
	if exchanger.httpClient == nil || exchanger.httpClient.Timeout != oidcHTTPTimeout {
		t.Fatalf("exchanger timeout = %s, want %s", exchanger.httpClient.Timeout, oidcHTTPTimeout)
	}
	verifier, ok := manager.verifier.(*oidcJWKSVerifier)
	if !ok {
		t.Fatalf("verifier = %T", manager.verifier)
	}
	if verifier.issuer != "https://dex.example.test/dex" || verifier.jwksURL != "https://dex.example.test/dex/keys" {
		t.Fatalf("issuer/jwks = %q/%q", verifier.issuer, verifier.jwksURL)
	}
	if verifier.httpClient == nil || verifier.httpClient.Timeout != oidcHTTPTimeout {
		t.Fatalf("verifier timeout = %s, want %s", verifier.httpClient.Timeout, oidcHTTPTimeout)
	}
}

func TestBeginOIDCLoginRejectsInvalidVerifierConfig(t *testing.T) {
	cache := newMemoryCache()
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCIssuerURL:    "https://dex.example.test/dex",
		OIDCClientID:     "ani-console",
		OIDCAuthURL:      "https://dex.example.test/dex/auth",
		OIDCPublicKeyPEM: "not-a-public-key",
	}, nil, nil)

	_, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("Begin error = %v, want FailedPrecondition", err)
	}
}

func TestOIDCLoginManagerPreservesExplicitEndpoints(t *testing.T) {
	manager := newOIDCLoginManager(newMemoryCache(), JWTConfig{
		OIDCIssuerURL: "https://issuer.example.test",
		OIDCClientID:  "ani-console",
		OIDCAuthURL:   "https://auth.example.test/login",
		OIDCTokenURL:  "https://token.example.test/exchange",
		OIDCJWKSURL:   "https://keys.example.test/jwks",
	}, nil, nil)

	if manager.authURL != "https://auth.example.test/login" {
		t.Fatalf("authURL = %q", manager.authURL)
	}
	exchanger := manager.exchanger.(oidcHTTPExchanger)
	if exchanger.tokenURL != "https://token.example.test/exchange" {
		t.Fatalf("tokenURL = %q", exchanger.tokenURL)
	}
	verifier := manager.verifier.(*oidcJWKSVerifier)
	if verifier.jwksURL != "https://keys.example.test/jwks" {
		t.Fatalf("jwksURL = %q", verifier.jwksURL)
	}
}

func TestOIDCStaticKeyVerifierTakesPrecedenceOverIssuerDefaults(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	verifier, err := newOIDCIDTokenVerifier(JWTConfig{
		OIDCIssuerURL:    "https://dex.example.test/dex",
		OIDCClientID:     "ani-console",
		OIDCPublicKeyPEM: publicKeyPEM(t, &key.PublicKey),
	})
	if err != nil {
		t.Fatalf("newOIDCIDTokenVerifier: %v", err)
	}
	if _, ok := verifier.(*oidcStaticKeyVerifier); !ok {
		t.Fatalf("verifier = %T", verifier)
	}
}

func TestOIDCJWKSVerifierAcceptsMatchingKID(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	jwksData, err := json.Marshal(map[string]any{
		"keys": []map[string]any{rsaPublicJWK("kid-1", &key.PublicKey)},
	})
	if err != nil {
		t.Fatalf("marshal jwks: %v", err)
	}

	issuedAt := time.Unix(1_700_000_000, 0)
	token := signOIDCTestJWT(t, key, "kid-1", map[string]any{
		"iss":    "https://dex.example.test",
		"sub":    "sub-1",
		"aud":    "ani-console",
		"exp":    issuedAt.Add(time.Hour).Unix(),
		"email":  "user@example.test",
		"name":   "User",
		"groups": []string{"tenant-admin"},
		"nonce":  "nonce-1",
	})
	verifier, err := newOIDCIDTokenVerifier(JWTConfig{
		OIDCIssuerURL: "https://dex.example.test",
		OIDCClientID:  "ani-console",
		OIDCJWKSURL:   "https://dex.example.test/keys",
	})
	if err != nil {
		t.Fatalf("newOIDCIDTokenVerifier: %v", err)
	}
	jwksVerifier := verifier.(*oidcJWKSVerifier)
	jwksVerifier.now = func() time.Time { return issuedAt.Add(time.Minute) }
	jwksRequests := 0
	jwksVerifier.httpClient = &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		jwksRequests++
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(string(jwksData))),
			Header:     make(http.Header),
		}, nil
	})}

	claims, err := verifier.Verify(context.Background(), token)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if claims.Subject != "sub-1" || claims.Email != "user@example.test" {
		t.Fatalf("claims = %#v", claims)
	}
	if len(claims.Groups) != 1 || claims.Groups[0] != "tenant-admin" {
		t.Fatalf("groups = %v", claims.Groups)
	}
	if claims.Nonce != "nonce-1" {
		t.Fatalf("nonce = %q", claims.Nonce)
	}
	if _, err := verifier.Verify(context.Background(), token); err != nil {
		t.Fatalf("second Verify: %v", err)
	}
	if jwksRequests != 1 {
		t.Fatalf("jwks requests = %d, want 1 cached request", jwksRequests)
	}
}

func TestParseJWKSRejectsNonSigningOrWrongAlgorithmKeys(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	signingKey := rsaPublicJWK("kid-signing", &key.PublicKey)
	encKey := rsaPublicJWK("kid-enc", &key.PublicKey)
	encKey["use"] = "enc"
	wrongAlgKey := rsaPublicJWK("kid-rs512", &key.PublicKey)
	wrongAlgKey["alg"] = "RS512"
	jwksData, err := json.Marshal(map[string]any{
		"keys": []map[string]any{encKey, wrongAlgKey, signingKey},
	})
	if err != nil {
		t.Fatalf("marshal jwks: %v", err)
	}

	keys, err := parseJWKS(jwksData)
	if err != nil {
		t.Fatalf("parseJWKS: %v", err)
	}
	if keys["kid-signing"] == nil {
		t.Fatal("expected signing RS256 key")
	}
	if keys["kid-enc"] != nil {
		t.Fatal("encryption key should be ignored")
	}
	if keys["kid-rs512"] != nil {
		t.Fatal("non-RS256 key should be ignored")
	}
}

func TestParseJWKSRejectsWeakRSAKeys(t *testing.T) {
	strongKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate strong key: %v", err)
	}
	weakKey, err := rsa.GenerateKey(rand.Reader, 1024)
	if err != nil {
		t.Fatalf("generate weak key: %v", err)
	}
	invalidExponentKey := rsaPublicJWK("kid-even-exponent", &strongKey.PublicKey)
	invalidExponentKey["e"] = base64.RawURLEncoding.EncodeToString([]byte{2})
	jwksData, err := json.Marshal(map[string]any{
		"keys": []map[string]any{
			rsaPublicJWK("kid-weak", &weakKey.PublicKey),
			invalidExponentKey,
			rsaPublicJWK("kid-strong", &strongKey.PublicKey),
		},
	})
	if err != nil {
		t.Fatalf("marshal jwks: %v", err)
	}

	keys, err := parseJWKS(jwksData)
	if err != nil {
		t.Fatalf("parseJWKS: %v", err)
	}
	if keys["kid-strong"] == nil {
		t.Fatal("expected strong RSA key")
	}
	if keys["kid-weak"] != nil {
		t.Fatal("weak RSA key should be ignored")
	}
	if keys["kid-even-exponent"] != nil {
		t.Fatal("invalid exponent key should be ignored")
	}
}

func TestOIDCIDTokenRejectsFutureTimeClaims(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	now := time.Unix(1_700_000_000, 0)
	token := signOIDCTestJWT(t, key, "kid-1", map[string]any{
		"iss":   "https://dex.example.test",
		"sub":   "sub-1",
		"aud":   "ani-console",
		"exp":   now.Add(time.Hour).Unix(),
		"iat":   now.Add(10 * time.Minute).Unix(),
		"nbf":   now.Add(10 * time.Minute).Unix(),
		"email": "user@example.test",
	})
	verifier, err := newOIDCIDTokenVerifier(JWTConfig{
		OIDCIssuerURL:    "https://dex.example.test",
		OIDCClientID:     "ani-console",
		OIDCPublicKeyPEM: publicKeyPEM(t, &key.PublicKey),
	})
	if err != nil {
		t.Fatalf("newOIDCIDTokenVerifier: %v", err)
	}
	staticVerifier := verifier.(*oidcStaticKeyVerifier)
	staticVerifier.now = func() time.Time { return now }

	if _, err := verifier.Verify(context.Background(), token); err == nil {
		t.Fatal("expected future iat/nbf token to fail")
	}
}

func TestCompleteOIDCLoginRejectsMismatchedRedirectURI(t *testing.T) {
	cache := newMemoryCache()
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, nil, nil)
	resp, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}

	if _, err := manager.Complete(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       resp.GetState(),
		Code:        "code-1",
		RedirectUri: "https://evil.example.test/callback",
	}); err == nil {
		t.Fatal("expected redirect uri mismatch to fail")
	}
}

func TestCompleteOIDCLoginIssuesTokenPair(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	cache := newMemoryCache()
	issuer, err := NewJWTIssuer(JWTConfig{PrivateKeyPEM: privateKeyPEM(t, key)})
	if err != nil {
		t.Fatalf("NewJWTIssuer: %v", err)
	}
	tenantID := uuid.New()
	userID := uuid.New()
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, fakeOIDCSessionStore{
		principal: refreshPrincipal{TenantID: tenantID, UserID: userID, Roles: []string{"user"}},
		token:     "refresh-1",
	}, issuer)
	manager.exchanger = fakeOIDCExchanger{idToken: "id-token"}
	begin, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	nonce := oidCTestNonce(t, begin.GetAuthorizationUrl())
	manager.verifier = fakeOIDCVerifier{claims: oidcClaims{
		Subject: "sub-1",
		Email:   "user@example.test",
		Groups:  []string{"user"},
		Nonce:   nonce,
	}}
	resp, err := manager.Complete(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       begin.GetState(),
		Code:        "code-1",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if resp.GetAccessToken() == "" || resp.GetRefreshToken() != "refresh-1" {
		t.Fatalf("unexpected token pair: %#v", resp)
	}
}

func TestCompleteOIDCLoginRejectsNonceMismatch(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	cache := newMemoryCache()
	issuer, err := NewJWTIssuer(JWTConfig{PrivateKeyPEM: privateKeyPEM(t, key)})
	if err != nil {
		t.Fatalf("NewJWTIssuer: %v", err)
	}
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, fakeOIDCSessionStore{}, issuer)
	manager.exchanger = fakeOIDCExchanger{idToken: "id-token"}
	manager.verifier = fakeOIDCVerifier{claims: oidcClaims{
		Subject: "sub-1",
		Email:   "user@example.test",
		Nonce:   "wrong-nonce",
	}}

	begin, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	if _, err := manager.Complete(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       begin.GetState(),
		Code:        "code-1",
		RedirectUri: "https://console.example.test/callback",
	}); err == nil {
		t.Fatal("expected nonce mismatch to fail")
	}
}

func TestCompleteOIDCLoginConsumesStateBeforeTokenValidation(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	cache := newMemoryCache()
	issuer, err := NewJWTIssuer(JWTConfig{PrivateKeyPEM: privateKeyPEM(t, key)})
	if err != nil {
		t.Fatalf("NewJWTIssuer: %v", err)
	}
	manager := newOIDCLoginManager(cache, JWTConfig{
		OIDCAuthURL:  "https://dex.example.test/auth",
		OIDCClientID: "ani-console",
	}, fakeOIDCSessionStore{}, issuer)
	manager.exchanger = fakeOIDCExchanger{idToken: "id-token"}
	manager.verifier = fakeOIDCVerifier{claims: oidcClaims{
		Subject: "sub-1",
		Email:   "user@example.test",
		Nonce:   "wrong-nonce",
	}}

	begin, err := manager.Begin(context.Background(), &authv1.BeginOIDCLoginRequest{
		TenantName:  "tenant-a",
		RedirectUri: "https://console.example.test/callback",
	})
	if err != nil {
		t.Fatalf("Begin: %v", err)
	}
	if _, err := manager.Complete(context.Background(), &authv1.CompleteOIDCLoginRequest{
		State:       begin.GetState(),
		Code:        "code-1",
		RedirectUri: "https://console.example.test/callback",
	}); err == nil {
		t.Fatal("expected nonce mismatch to fail")
	}
	if _, err := cache.Get(context.Background(), "oidc:state:"+begin.GetState()); err == nil {
		t.Fatal("expected state to be consumed after failed token validation")
	}
}

type fakeOIDCExchanger struct {
	idToken string
}

func (f fakeOIDCExchanger) Exchange(context.Context, string, string) (oidcTokenResponse, error) {
	return oidcTokenResponse{IDToken: f.idToken}, nil
}

type fakeOIDCVerifier struct {
	claims oidcClaims
}

func (f fakeOIDCVerifier) Verify(context.Context, string) (oidcClaims, error) {
	return f.claims, nil
}

type fakeOIDCSessionStore struct {
	principal refreshPrincipal
	token     string
}

func (f fakeOIDCSessionStore) CreateSession(context.Context, string, oidcClaims) (refreshPrincipal, string, error) {
	return f.principal, f.token, nil
}

func oidCTestNonce(t *testing.T, rawURL string) string {
	t.Helper()
	parsed, err := url.Parse(rawURL)
	if err != nil {
		t.Fatalf("parse authorization url: %v", err)
	}
	nonce := parsed.Query().Get("nonce")
	if nonce == "" {
		t.Fatalf("nonce is empty")
	}
	return nonce
}

func rsaPublicJWK(kid string, key *rsa.PublicKey) map[string]any {
	return map[string]any{
		"kty": "RSA",
		"use": "sig",
		"alg": "RS256",
		"kid": kid,
		"n":   base64.RawURLEncoding.EncodeToString(key.N.Bytes()),
		"e":   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(key.E)).Bytes()),
	}
}

func signOIDCTestJWT(t *testing.T, key *rsa.PrivateKey, kid string, claims map[string]any) string {
	t.Helper()
	header := encodeJSON(t, map[string]any{"alg": "RS256", "typ": "JWT", "kid": kid})
	payload := encodeJSON(t, claims)
	signingInput := header + "." + payload
	digest := sha256.Sum256([]byte(signingInput))
	sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(sig)
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}
