package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// Config holds connection strings. Load from environment in each service's config.Load().
type Config struct {
	DatabaseURL string
	NATSURL     string
	RedisURL    string
	GRPCPort    int
	HealthPort  int
	ServiceName string

	WorkloadProvider               string
	WorkloadProviderApplyEnabled   bool
	WorkloadLifecycleProvider      string
	WorkloadLifecycleApplyEnabled  bool
	WorkloadOpsProvider            string
	WorkloadOpsEnabled             bool
	KubernetesAPIHost              string
	KubernetesBearerToken          string
	KubernetesProviderFieldManager string
}

// MustConnect initializes all dependencies. Exits the process if any connection fails.
func MustConnect(cfg Config) *Deps {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	db, err := connectDB(cfg.DatabaseURL)
	if err != nil {
		logger.Error("failed to connect to database", "err", err)
		os.Exit(1)
	}

	nc, js, err := connectNATS(cfg.NATSURL)
	if err != nil {
		logger.Error("failed to connect to NATS", "err", err)
		os.Exit(1)
	}

	rdb, err := connectRedis(cfg.RedisURL)
	if err != nil {
		logger.Error("failed to connect to Redis", "err", err)
		os.Exit(1)
	}

	ports, err := NewCapabilitiesWithConfig(db, js, rdb, cfg.withEnvironmentOverrides())
	if err != nil {
		logger.Error("failed to initialize capability adapters", "err", err)
		os.Exit(1)
	}

	return &Deps{
		DB:          db,
		NATS:        nc,
		JS:          js,
		Redis:       rdb,
		Ports:       ports,
		Logger:      logger,
		ServiceName: cfg.ServiceName,
		HealthPort:  cfg.HealthPort,
	}
}

func (c Config) withEnvironmentOverrides() Config {
	if value := os.Getenv("WORKLOAD_PROVIDER"); value != "" {
		c.WorkloadProvider = value
	}
	if value := os.Getenv("HEALTH_PORT"); value != "" {
		c.HealthPort = parseInt(value, c.HealthPort)
	}
	if value := os.Getenv("WORKLOAD_PROVIDER_APPLY_ENABLED"); value != "" {
		c.WorkloadProviderApplyEnabled = parseBool(value)
	}
	if value := os.Getenv("WORKLOAD_LIFECYCLE_PROVIDER"); value != "" {
		c.WorkloadLifecycleProvider = value
	}
	if value := os.Getenv("WORKLOAD_LIFECYCLE_APPLY_ENABLED"); value != "" {
		c.WorkloadLifecycleApplyEnabled = parseBool(value)
	}
	if value := os.Getenv("WORKLOAD_OPS_PROVIDER"); value != "" {
		c.WorkloadOpsProvider = value
	}
	if value := os.Getenv("WORKLOAD_OPS_ENABLED"); value != "" {
		c.WorkloadOpsEnabled = parseBool(value)
	}
	if value := os.Getenv("KUBERNETES_API_HOST"); value != "" {
		c.KubernetesAPIHost = value
	}
	if value := os.Getenv("KUBERNETES_BEARER_TOKEN"); value != "" {
		c.KubernetesBearerToken = value
	}
	if value := os.Getenv("KUBERNETES_PROVIDER_FIELD_MANAGER"); value != "" {
		c.KubernetesProviderFieldManager = value
	}
	return c
}

func parseInt(value string, fallback int) int {
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func parseBool(value string) bool {
	switch value {
	case "1", "true", "TRUE", "yes", "YES", "on", "ON":
		return true
	default:
		return false
	}
}

// RunGRPC starts a gRPC server on port and blocks until SIGINT/SIGTERM.
// register is called to register all service implementations.
// Performs graceful shutdown: waits for in-flight RPCs to complete.
func RunGRPC(port int, register func(*grpc.Server), deps *Deps) {
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		deps.Logger.Error("failed to listen", "port", port, "err", err)
		os.Exit(1)
	}

	srv := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			loggingUnaryInterceptor(deps.Logger),
			recoveryUnaryInterceptor(deps.Logger),
		),
	)

	register(srv)
	reflection.Register(srv) // enables grpcurl and grpc-gateway reflection

	var probe *http.Server
	if deps.HealthPort > 0 {
		probe = &http.Server{
			Addr:              fmt.Sprintf(":%d", deps.HealthPort),
			Handler:           newProbeHandler(deps.ServiceName, dependencyProbeChecks(deps)),
			ReadHeaderTimeout: 5 * time.Second,
		}
		go func() {
			deps.Logger.Info("health probe server listening", "port", deps.HealthPort)
			if err := probe.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
				deps.Logger.Error("health probe serve error", "err", err)
				os.Exit(1)
			}
		}()
	}

	go func() {
		deps.Logger.Info("gRPC server listening", "port", port)
		if err := srv.Serve(lis); err != nil {
			deps.Logger.Error("gRPC serve error", "err", err)
		}
	}()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()

	deps.Logger.Info("shutting down gRPC server gracefully")
	if probe != nil {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := probe.Shutdown(shutdownCtx); err != nil {
			deps.Logger.Error("health probe shutdown error", "err", err)
		}
	}
	srv.GracefulStop()
	deps.Logger.Info("gRPC server stopped")
}

// loggingUnaryInterceptor logs every gRPC call with duration and status.
func loggingUnaryInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		resp, err := handler(ctx, req)
		if err != nil {
			logger.ErrorContext(ctx, "gRPC error", "method", info.FullMethod, "err", err)
		}
		return resp, err
	}
}

// recoveryUnaryInterceptor catches panics and converts them to gRPC Internal errors.
func recoveryUnaryInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
		defer func() {
			if r := recover(); r != nil {
				logger.ErrorContext(ctx, "gRPC panic recovered", "method", info.FullMethod, "panic", r)
				err = fmt.Errorf("internal error")
			}
		}()
		return handler(ctx, req)
	}
}
