package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	redisadapter "github.com/kubercloud/ani/pkg/adapters/redis"
	"github.com/kubercloud/ani/pkg/ports"
	"github.com/redis/go-redis/v9"
)

type RedisConfig struct {
	URL              string
	Mode             string
	Addrs            []string
	MasterName       string
	Username         string
	Password         string
	SentinelUsername string
	SentinelPassword string
	DB               int
}

func connectRedis(redisURL string) (redis.UniversalClient, error) {
	return connectRedisWithConfig(RedisConfig{URL: redisURL})
}

func connectRedisWithConfig(config RedisConfig) (redis.UniversalClient, error) {
	opts, err := redisUniversalOptions(config)
	if err != nil {
		return nil, err
	}

	rdb := redis.NewUniversalClient(opts)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := rdb.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping failed: %w", err)
	}

	slog.Info("redis connected")
	return rdb, nil
}

func ConnectRedisCacheStore(redisURL string) (ports.CacheStore, func() error, error) {
	client, err := connectRedis(redisURL)
	if err != nil {
		return nil, nil, err
	}
	return redisadapter.NewCacheStore(client), client.Close, nil
}

func ConnectRedisCacheStoreWithConfig(config RedisConfig) (ports.CacheStore, func() error, error) {
	client, err := connectRedisWithConfig(config)
	if err != nil {
		return nil, nil, err
	}
	return redisadapter.NewCacheStore(client), client.Close, nil
}

func redisConfigFromBootstrapConfig(config Config) RedisConfig {
	return RedisConfig{
		URL:              config.RedisURL,
		Mode:             config.RedisMode,
		Addrs:            config.RedisAddrs,
		MasterName:       config.RedisMasterName,
		Username:         config.RedisUsername,
		Password:         config.RedisPassword,
		SentinelUsername: config.RedisSentinelUsername,
		SentinelPassword: config.RedisSentinelPassword,
		DB:               config.RedisDB,
	}
}

func redisUniversalOptions(config RedisConfig) (*redis.UniversalOptions, error) {
	if strings.TrimSpace(config.URL) != "" && strings.TrimSpace(config.Mode) == "" && len(trimStringList(config.Addrs)) == 0 {
		opts, err := redis.ParseURL(config.URL)
		if err != nil {
			return nil, fmt.Errorf("invalid REDIS_URL: %w", err)
		}
		return &redis.UniversalOptions{
			Addrs:    []string{opts.Addr},
			Username: opts.Username,
			Password: opts.Password,
			DB:       opts.DB,
		}, nil
	}

	addrs := trimStringList(config.Addrs)
	if len(addrs) == 0 {
		return nil, fmt.Errorf("redis addrs are required")
	}
	mode := strings.ToLower(strings.TrimSpace(config.Mode))
	opts := &redis.UniversalOptions{
		Addrs:            addrs,
		Username:         strings.TrimSpace(config.Username),
		Password:         strings.TrimSpace(config.Password),
		SentinelUsername: strings.TrimSpace(config.SentinelUsername),
		SentinelPassword: strings.TrimSpace(config.SentinelPassword),
		DB:               config.DB,
	}
	switch mode {
	case "", "standalone", "single":
		if len(addrs) != 1 {
			return nil, fmt.Errorf("redis standalone mode requires exactly one addr")
		}
	case "sentinel":
		opts.MasterName = strings.TrimSpace(config.MasterName)
		if opts.MasterName == "" {
			return nil, fmt.Errorf("redis sentinel mode requires master name")
		}
	case "cluster":
		if len(addrs) < 2 {
			return nil, fmt.Errorf("redis cluster mode requires at least two addrs")
		}
	default:
		return nil, fmt.Errorf("unsupported redis mode %q", config.Mode)
	}
	return opts, nil
}

func trimStringList(values []string) []string {
	trimmed := make([]string, 0, len(values))
	for _, value := range values {
		if item := strings.TrimSpace(value); item != "" {
			trimmed = append(trimmed, item)
		}
	}
	return trimmed
}
