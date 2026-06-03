package main

import (
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	runtimeadapter "github.com/kubercloud/ani/pkg/adapters/runtime"
)

const (
	providerName = "kms-sm4"
	sealedPrefix = "ANISM4GCM1"
)

type server struct {
	bearerToken string
	objectRoot  string
	aead        cipher.AEAD
}

func main() {
	listenAddr := envDefault("LISTEN_ADDR", ":9305")
	objectRoot := envDefault("OBJECTSTORE_ROOT", "/var/lib/ani/kms-sm4-live-objectstore")
	srv, err := newServer(os.Getenv("KMS_PROVIDER_BEARER_TOKEN"), objectRoot, os.Getenv("KMS_SM4_LIVE_MASTER_KEY"))
	if err != nil {
		slog.Error("configure kms sm4 live fixture", "err", err)
		os.Exit(1)
	}
	httpServer := &http.Server{
		Addr:              listenAddr,
		Handler:           srv.routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}
	slog.Info("starting kms sm4 live fixture", "addr", listenAddr, "object_root", objectRoot)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("serve kms sm4 live fixture", "err", err)
		os.Exit(1)
	}
}

func newServer(bearerToken string, objectRoot string, masterKey string) (*server, error) {
	root := strings.TrimSpace(objectRoot)
	if root == "" {
		return nil, fmt.Errorf("object root is required")
	}
	digest := sha256.Sum256([]byte(envDefaultValue(masterKey, "ani-real-k8s-lab-sm4-live-fixture")))
	block, err := runtimeadapter.NewSM4BlockCipher(digest[:16])
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &server{
		bearerToken: strings.TrimSpace(bearerToken),
		objectRoot:  root,
		aead:        aead,
	}, nil
}

func (s *server) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", s.health)
	mux.HandleFunc("/v1/keys", s.createKey)
	mux.HandleFunc("/v1/seal", s.sealObject)
	mux.HandleFunc("/v1/unseal-token", s.unsealToken)
	mux.HandleFunc("/v1/stream/seal", s.streamSeal)
	mux.HandleFunc("/v1/stream/open", s.streamOpen)
	mux.HandleFunc("/objectstore/", s.objectstore)
	return mux
}

func (s *server) health(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *server) createKey(w http.ResponseWriter, r *http.Request) {
	if !s.requirePostJSON(w, r) {
		return
	}
	var req providerKeyRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	tenantID := firstNonEmpty(req.TenantID, req.TenantIDGo)
	keyID := firstNonEmpty(req.KeyID, req.KeyIDGo)
	algorithm := firstNonEmpty(req.Algorithm, req.AlgorithmGo)
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(keyID) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "tenant_id and key_id are required"})
		return
	}
	if strings.ToUpper(strings.TrimSpace(algorithm)) != "SM4" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "algorithm must be SM4"})
		return
	}
	writeJSON(w, http.StatusOK, providerKeyResponse{
		Applied:      true,
		Provider:     providerName,
		ResourceRefs: []string{"kms://" + tenantID + "/" + keyID},
		Reason:       "real-k8s-lab-live-fixture",
		AppliedAt:    time.Now().UTC(),
	})
}

func (s *server) sealObject(w http.ResponseWriter, r *http.Request) {
	if !s.requirePostJSON(w, r) {
		return
	}
	var req providerSealRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	tenantID := firstNonEmpty(req.TenantID, req.TenantIDGo)
	keyID := firstNonEmpty(req.KeyID, req.KeyIDGo)
	objectURI := firstNonEmpty(req.ObjectURI, req.ObjectURIGo)
	idempotencyKey := firstNonEmpty(req.IdempotencyKey, req.IdempotencyKeyGo)
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(keyID) == "" || strings.TrimSpace(objectURI) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "tenant_id, key_id and object_uri are required"})
		return
	}
	digest := sha256.Sum256([]byte(tenantID + "\x00" + keyID + "\x00" + objectURI + "\x00" + idempotencyKey))
	writeJSON(w, http.StatusOK, providerSealResponse{
		SealedObjectURI: "kms+sm4://" + tenantID + "/" + keyID + "/" + hex.EncodeToString(digest[:12]),
		UnsealToken:     "utok-" + hex.EncodeToString(digest[12:24]),
		ExpiresAt:       time.Now().UTC().Add(time.Hour).Format(time.RFC3339),
		Provider:        providerName,
		ResourceRefs:    []string{"kms://" + tenantID + "/" + keyID},
	})
}

func (s *server) unsealToken(w http.ResponseWriter, r *http.Request) {
	if !s.requirePostJSON(w, r) {
		return
	}
	var req providerUnsealTokenRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	tenantID := firstNonEmpty(req.TenantID, req.TenantIDGo)
	keyID := firstNonEmpty(req.KeyID, req.KeyIDGo)
	sealedObjectURI := firstNonEmpty(req.SealedObjectURI, req.SealedObjectURIGo)
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(keyID) == "" || strings.TrimSpace(sealedObjectURI) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "tenant_id, key_id and sealed_object_uri are required"})
		return
	}
	digest := sha256.Sum256([]byte(tenantID + "\x00" + keyID + "\x00" + sealedObjectURI))
	writeJSON(w, http.StatusOK, providerUnsealTokenResponse{
		UnsealToken:  "utok-" + hex.EncodeToString(digest[:12]),
		ExpiresAt:    time.Now().UTC().Add(time.Hour).Format(time.RFC3339),
		Provider:     providerName,
		ResourceRefs: []string{"kms://" + tenantID + "/" + keyID},
	})
}

func (s *server) streamSeal(w http.ResponseWriter, r *http.Request) {
	if !s.requirePostBytes(w, r) {
		return
	}
	plaintext, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 32<<20))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "request body too large or unreadable"})
		return
	}
	nonce := make([]byte, s.aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "nonce generation failed"})
		return
	}
	sealed := append([]byte(sealedPrefix), nonce...)
	sealed = s.aead.Seal(sealed, nonce, plaintext, []byte(providerName))
	w.Header().Set("Content-Type", "application/octet-stream")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(sealed)
}

func (s *server) streamOpen(w http.ResponseWriter, r *http.Request) {
	if !s.requirePostBytes(w, r) {
		return
	}
	sealed, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 32<<20))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "request body too large or unreadable"})
		return
	}
	prefixLen := len(sealedPrefix)
	if len(sealed) <= prefixLen+s.aead.NonceSize() || string(sealed[:prefixLen]) != sealedPrefix {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid sealed content"})
		return
	}
	nonce := sealed[prefixLen : prefixLen+s.aead.NonceSize()]
	ciphertext := sealed[prefixLen+s.aead.NonceSize():]
	plaintext, err := s.aead.Open(nil, nonce, ciphertext, []byte(providerName))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "sealed content authentication failed"})
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(plaintext)
}

func (s *server) objectstore(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut && r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	path, ok := s.objectPath(strings.TrimPrefix(r.URL.Path, "/objectstore/"))
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid object path"})
		return
	}
	if r.Method == http.MethodPut {
		content, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 32<<20))
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "request body too large or unreadable"})
			return
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "object parent unavailable"})
			return
		}
		if err := os.WriteFile(path, content, 0o600); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "object write failed"})
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}
	content, err := os.ReadFile(path)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "object not found"})
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(content)
}

func (s *server) objectPath(name string) (string, bool) {
	for _, part := range strings.Split(name, "/") {
		if part == ".." {
			return "", false
		}
	}
	clean := filepath.Clean("/" + name)
	if clean == "/" {
		return "", false
	}
	return filepath.Join(s.objectRoot, strings.TrimPrefix(clean, "/")), true
}

func (s *server) requirePostJSON(w http.ResponseWriter, r *http.Request) bool {
	if !s.requireBearer(w, r) {
		return false
	}
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return false
	}
	return true
}

func (s *server) requirePostBytes(w http.ResponseWriter, r *http.Request) bool {
	if !s.requireBearer(w, r) {
		return false
	}
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return false
	}
	return true
}

func (s *server) requireBearer(w http.ResponseWriter, r *http.Request) bool {
	if s.bearerToken == "" {
		return true
	}
	if r.Header.Get("Authorization") != "Bearer "+s.bearerToken {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
		return false
	}
	return true
}

func decodeJSON(w http.ResponseWriter, r *http.Request, out any) bool {
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(out); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid json"})
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func envDefault(name string, fallback string) string {
	return envDefaultValue(os.Getenv(name), fallback)
}

func envDefaultValue(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

type providerKeyRequest struct {
	TenantID    string `json:"tenant_id"`
	TenantIDGo  string `json:"TenantID"`
	KeyID       string `json:"key_id"`
	KeyIDGo     string `json:"KeyID"`
	Name        string `json:"name"`
	NameGo      string `json:"Name"`
	Algorithm   string `json:"algorithm"`
	AlgorithmGo string `json:"Algorithm"`
}

type providerSealRequest struct {
	TenantID         string `json:"tenant_id"`
	TenantIDGo       string `json:"TenantID"`
	KeyID            string `json:"key_id"`
	KeyIDGo          string `json:"KeyID"`
	Algorithm        string `json:"algorithm"`
	AlgorithmGo      string `json:"Algorithm"`
	ObjectURI        string `json:"object_uri"`
	ObjectURIGo      string `json:"ObjectURI"`
	IdempotencyKey   string `json:"idempotency_key"`
	IdempotencyKeyGo string `json:"IdempotencyKey"`
}

type providerUnsealTokenRequest struct {
	TenantID          string `json:"tenant_id"`
	TenantIDGo        string `json:"TenantID"`
	KeyID             string `json:"key_id"`
	KeyIDGo           string `json:"KeyID"`
	Algorithm         string `json:"algorithm"`
	AlgorithmGo       string `json:"Algorithm"`
	SealedObjectURI   string `json:"sealed_object_uri"`
	SealedObjectURIGo string `json:"SealedObjectURI"`
}

type providerKeyResponse struct {
	Applied      bool      `json:"applied"`
	Provider     string    `json:"provider"`
	ResourceRefs []string  `json:"resource_refs"`
	Reason       string    `json:"reason"`
	AppliedAt    time.Time `json:"applied_at"`
}

type providerSealResponse struct {
	SealedObjectURI string   `json:"sealed_object_uri"`
	UnsealToken     string   `json:"unseal_token"`
	ExpiresAt       string   `json:"expires_at"`
	Provider        string   `json:"provider"`
	ResourceRefs    []string `json:"resource_refs"`
}

type providerUnsealTokenResponse struct {
	UnsealToken  string   `json:"unseal_token"`
	ExpiresAt    string   `json:"expires_at"`
	Provider     string   `json:"provider"`
	ResourceRefs []string `json:"resource_refs"`
}
