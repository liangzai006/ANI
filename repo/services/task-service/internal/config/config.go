package config

import (
	"os"
	"strconv"
	"time"

	"github.com/kubercloud/ani/pkg/bootstrap"
)

type Config struct {
	bootstrap.Config
	OutboxEnabled      bool
	OutboxPollInterval time.Duration
	OutboxBatchSize    int
}

func Load() Config {
	return Config{
		Config: bootstrap.Config{
			DatabaseURL: env("DATABASE_URL", "postgres://ani_app_user:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable"),
			NATSURL:     env("NATS_URL", "nats://127.0.0.1:4222"),
			RedisURL:    env("REDIS_URL", "redis://:ani_dev_password@127.0.0.1:6379/0"),
			GRPCPort:    envInt("GRPC_PORT", 9104),
			HealthPort:  envInt("HEALTH_PORT", 9204),
			ServiceName: "task-service",
		},
		OutboxEnabled:      envBool("OUTBOX_ENABLED", true),
		OutboxPollInterval: time.Duration(envInt("OUTBOX_POLL_INTERVAL_MS", 500)) * time.Millisecond,
		OutboxBatchSize:    envInt("OUTBOX_BATCH_SIZE", 100),
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func envBool(key string, fallback bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	switch v {
	case "1", "true", "TRUE", "yes", "YES":
		return true
	case "0", "false", "FALSE", "no", "NO":
		return false
	default:
		return fallback
	}
}
