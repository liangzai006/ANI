package bootstrap

import "testing"

func TestRedisFailoverConfigParsesSentinel(t *testing.T) {
	opts, err := redisUniversalOptions(RedisConfig{
		Mode:       "sentinel",
		Addrs:      []string{"redis-sentinel-a:26379", "redis-sentinel-b:26379"},
		MasterName: "ani-redis",
		Username:   "ani",
		Password:   "secret",
		DB:         2,
	})
	if err != nil {
		t.Fatalf("redisUniversalOptions() error = %v", err)
	}
	if opts.MasterName != "ani-redis" {
		t.Fatalf("MasterName = %q, want ani-redis", opts.MasterName)
	}
	if len(opts.Addrs) != 2 || opts.Addrs[0] != "redis-sentinel-a:26379" || opts.Addrs[1] != "redis-sentinel-b:26379" {
		t.Fatalf("Addrs = %#v, want sentinel addrs", opts.Addrs)
	}
	if opts.Username != "ani" || opts.Password != "secret" || opts.DB != 2 {
		t.Fatalf("auth/db = %q/%q/%d, want ani/secret/2", opts.Username, opts.Password, opts.DB)
	}
}

func TestRedisClusterConfigParsesAddrs(t *testing.T) {
	opts, err := redisUniversalOptions(RedisConfig{
		Mode:  "cluster",
		Addrs: []string{"redis-a:6379", "redis-b:6379", "redis-c:6379"},
	})
	if err != nil {
		t.Fatalf("redisUniversalOptions() error = %v", err)
	}
	if opts.MasterName != "" {
		t.Fatalf("MasterName = %q, want empty for cluster", opts.MasterName)
	}
	if len(opts.Addrs) != 3 || opts.Addrs[2] != "redis-c:6379" {
		t.Fatalf("Addrs = %#v, want cluster addrs", opts.Addrs)
	}
}
