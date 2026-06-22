package main

import "testing"

func TestGatewayRedisConfigFromEnvParsesSentinel(t *testing.T) {
	t.Setenv("GATEWAY_REDIS_MODE", "sentinel")
	t.Setenv("GATEWAY_REDIS_ADDRS", "redis-sentinel-a:26379, redis-sentinel-b:26379")
	t.Setenv("GATEWAY_REDIS_MASTER_NAME", "ani-redis")
	t.Setenv("GATEWAY_REDIS_USERNAME", "ani")
	t.Setenv("GATEWAY_REDIS_PASSWORD", "secret")
	t.Setenv("GATEWAY_REDIS_DB", "2")

	cfg := gatewayRedisConfigFromEnv()
	if cfg.Mode != "sentinel" || cfg.MasterName != "ani-redis" {
		t.Fatalf("redis mode/master = %q/%q, want sentinel/ani-redis", cfg.Mode, cfg.MasterName)
	}
	if len(cfg.Addrs) != 2 || cfg.Addrs[0] != "redis-sentinel-a:26379" || cfg.Addrs[1] != "redis-sentinel-b:26379" {
		t.Fatalf("redis addrs = %#v, want parsed sentinel addrs", cfg.Addrs)
	}
	if cfg.Username != "ani" || cfg.Password != "secret" || cfg.DB != 2 {
		t.Fatalf("redis auth/db = %q/%q/%d, want ani/secret/2", cfg.Username, cfg.Password, cfg.DB)
	}
}
