# ANI Monorepo — 统一构建入口
# 使用方式：make <target>

.PHONY: help deps deps-down deps-status deps-clean \
        tools-proto gen-api gen-proto \
        build build-gateway build-auth-service build-model-service build-task-service \
        test test-go test-python test-cover \
        validate-infra validate-gpu-preflight validate-gpu-contracts validate-runtime-contracts validate-instance-contracts validate-instance-planner validate-instance-renderer validate-instance-admission validate-instance-audit validate-instance-provider-dry-run validate-instance-provider-apply validate-instance-status-reconcile validate-instance-orchestrator validate-instance-store validate-instance-provider-adapter validate-instance-service validate-instance-lifecycle-ops validate-m1-e2e validate-kubernetes-provider-execution validate-kubernetes-rest-client validate-kubernetes-bootstrap-wiring validate-kubernetes-lifecycle-execution validate-kubernetes-ops-execution validate-m1-real-provider-profile validate-demo-instances validate-auth-contract validate-auth-dex-smoke validate-architecture \
        lint lint-go lint-python lint-ts \
        dev-gateway dev-console \
        image image-gateway \
        clean

# ── 帮助 ──────────────────────────────────────────────────────────────────────
help:
	@echo "ANI Monorepo 构建命令"
	@echo ""
	@echo "  开发环境:"
	@echo "    make deps           启动本地依赖服务（PG/MinIO/NATS/Redis/Milvus）"
	@echo "    make deps-down      停止本地依赖服务"
	@echo "    make deps-status    查看依赖服务状态"
	@echo "    make deps-clean     停止并清除所有数据（危险）"
	@echo ""
	@echo "  代码生成:"
	@echo "    make tools-proto    安装本地 Protobuf 生成插件"
	@echo "    make gen-api        从 OpenAPI Spec 生成 Go/TS 代码"
	@echo "    make gen-proto      从 Protobuf 生成 Go gRPC 代码"
	@echo ""
	@echo "  构建:"
	@echo "    make build          构建所有 Go 服务和工具"
	@echo "    make build-gateway  仅构建 ANI Gateway"
	@echo "    make build-auth-service  仅构建 Auth Service"
	@echo "    make build-model-service  仅构建 Model Service"
	@echo "    make build-task-service   仅构建 Task Service"
	@echo ""
	@echo "  测试:"
	@echo "    make test           运行所有测试（Go + Python）"
	@echo "    make test-cover     生成测试覆盖率报告"
	@echo "    make validate-infra 校验 M1 基础设施 K8s YAML"
	@echo "    make validate-gpu-preflight 校验 M1-INFRA-F GPU 预检契约"
	@echo "    make validate-gpu-contracts 校验 M1-GPU-A 异构 GPU 契约"
	@echo "    make validate-runtime-contracts 校验 M1-RUNTIME-A 实例运行时契约"
	@echo "    make validate-instance-contracts 校验 M1-INSTANCE-A 实例对象/网络/存储契约"
	@echo "    make validate-instance-planner 校验 M1-INSTANCE-B 实例规划器契约"
	@echo "    make validate-instance-renderer 校验 M1-INSTANCE-C provider renderer 契约"
	@echo "    make validate-instance-admission 校验 M1-INSTANCE-D admission guardrail 契约"
	@echo "    make validate-instance-audit 校验 M1-INSTANCE-E audit trail 契约"
	@echo "    make validate-instance-provider-dry-run 校验 M1-INSTANCE-F provider dry-run 契约"
	@echo "    make validate-instance-provider-apply 校验 M1-INSTANCE-G provider apply gate 契约"
	@echo "    make validate-instance-status-reconcile 校验 M1-INSTANCE-H status reconcile 契约"
	@echo "    make validate-instance-orchestrator 校验 M1-INSTANCE-I instance orchestration 契约"
	@echo "    make validate-instance-store 校验 M1-INSTANCE-J instance persistence/query 契约"
	@echo "    make validate-instance-provider-adapter 校验 M1-INSTANCE-K provider adapter 契约"
	@echo "    make validate-instance-service 校验 M1-INSTANCE-L instance service API 契约"
	@echo "    make validate-instance-lifecycle-ops 校验 M1-INSTANCE-M lifecycle/ops API 契约"
	@echo "    make validate-m1-e2e 校验 M1 端到端集成剖面"
	@echo "    make validate-kubernetes-provider-execution 校验 M1-INSTANCE-N Kubernetes provider 执行剖面"
	@echo "    make validate-kubernetes-rest-client 校验 M1-INSTANCE-O Kubernetes REST client"
	@echo "    make validate-kubernetes-bootstrap-wiring 校验 M1-INSTANCE-P Kubernetes provider bootstrap wiring"
	@echo "    make validate-kubernetes-lifecycle-execution 校验 M1-INSTANCE-Q Kubernetes lifecycle execution"
	@echo "    make validate-kubernetes-ops-execution 校验 M1-INSTANCE-R Kubernetes visual ops execution"
	@echo "    make validate-m1-real-provider-profile 校验 M1-E2E-B real provider 回归剖面"
	@echo "    make validate-demo-instances 校验阶段性实例 Demo API"
	@echo "    make validate-auth-contract 校验 M2.2 Auth Gateway/API 契约一致性"
	@echo "    make validate-auth-dex-smoke 校验 M2.2 Docker Dex OIDC auth-code flow（需 Docker）"
	@echo "    make validate-architecture 校验 ports/adapters 组件边界"
	@echo ""
	@echo "  代码检查:"
	@echo "    make lint           运行所有 linter"
	@echo ""
	@echo "  本地开发:"
	@echo "    make dev-gateway    启动 ANI Gateway（热重载）"
	@echo "    make dev-console    启动 Console 前端（Vite HMR）"

# ── 依赖服务 ──────────────────────────────────────────────────────────────────
COMPOSE = docker compose -f deploy/docker/docker-compose.yml
GO_CACHE_ENV = GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod
BUF_CACHE_ENV = BUF_CACHE_DIR=$(CURDIR)/.cache/buf
GO_PACKAGES = ./pkg/... ./services/ani-gateway/... ./services/auth-service/... ./services/model-service/... ./services/task-service/...
TOOLS_BIN = $(CURDIR)/.bin

deps:
	@echo "→ 启动本地依赖服务..."
	$(COMPOSE) up -d
	@echo "→ 等待服务就绪..."
	@$(COMPOSE) exec postgres pg_isready -U ani -t 30 && echo "✅ PostgreSQL 就绪"
	@echo "✅ 所有依赖服务已启动"
	@echo ""
	@echo "  MinIO Console: http://localhost:9001  (ani-admin / ani_dev_password)"
	@echo "  NATS Monitor:  http://localhost:8222"
	@echo "  Milvus:        localhost:19530"

deps-down:
	$(COMPOSE) down

deps-status:
	$(COMPOSE) ps

deps-clean:
	@echo "⚠️  这将删除所有本地开发数据，是否确认？[y/N]" && read ans && [ $${ans:-N} = y ]
	$(COMPOSE) down -v

# ── 代码生成 ──────────────────────────────────────────────────────────────────
tools-proto:
	@echo "→ 安装 Protobuf 生成插件到 .bin..."
	@mkdir -p .bin
	@test -x "$(TOOLS_BIN)/protoc-gen-go" || GOBIN=$(TOOLS_BIN) $(GO_CACHE_ENV) go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.33.0
	@test -x "$(TOOLS_BIN)/protoc-gen-go-grpc" || GOBIN=$(TOOLS_BIN) $(GO_CACHE_ENV) go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0
	@test -x "$(TOOLS_BIN)/protoc-gen-grpc-gateway" || GOBIN=$(TOOLS_BIN) $(GO_CACHE_ENV) go install github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-grpc-gateway@v2.19.1
	@echo "✅ Protobuf 工具已安装"

gen-api:
	@echo "→ 从 OpenAPI Spec 生成 Go 代码..."
	cd services/ani-gateway && \
		go generate ./...
	@echo "→ 从 OpenAPI Spec 生成 TypeScript SDK..."
	npx openapi-typescript api/openapi/v1.yaml -o frontends/console/src/api/types.ts
	@echo "✅ API 代码生成完成"

gen-proto: tools-proto
	@echo "→ 从 Protobuf 生成 Go gRPC 代码..."
	cd api/proto && PATH="$(TOOLS_BIN):$$PATH" $(BUF_CACHE_ENV) buf generate --template buf.gen.yaml .
	@echo "✅ Protobuf 代码生成完成"

# ── 构建 ──────────────────────────────────────────────────────────────────────
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS = -X main.Version=$(VERSION) -X main.BuildTime=$(shell date -u +%Y%m%dT%H%M%SZ)

build: build-gateway build-auth-service build-model-service build-task-service

build-gateway:
	@echo "→ 构建 ANI Gateway..."
	@mkdir -p bin
	cd services/ani-gateway && \
		$(GO_CACHE_ENV) CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o ../../bin/ani-gateway .
	@echo "✅ bin/ani-gateway"

build-auth-service:
	@echo "→ 构建 Auth Service..."
	@mkdir -p bin
	cd services/auth-service && \
		$(GO_CACHE_ENV) CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o ../../bin/auth-service .
	@echo "✅ bin/auth-service"

build-model-service:
	@echo "→ 构建 Model Service..."
	@mkdir -p bin
	cd services/model-service && \
		$(GO_CACHE_ENV) CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o ../../bin/model-service .
	@echo "✅ bin/model-service"

build-task-service:
	@echo "→ 构建 Task Service..."
	@mkdir -p bin
	cd services/task-service && \
		$(GO_CACHE_ENV) CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o ../../bin/task-service .
	@echo "✅ bin/task-service"

# ── 测试 ──────────────────────────────────────────────────────────────────────
test: validate-architecture validate-auth-contract test-go test-python

test-go:
	@echo "→ 运行 Go 单元测试..."
	$(GO_CACHE_ENV) go test $(GO_PACKAGES) -v -timeout 120s

test-python:
	@echo "→ 检查 Python 服务语法（RAG）..."
	python -m compileall -q ai/rag-engine

test-cover:
	@echo "→ 生成 Go 测试覆盖率报告..."
	$(GO_CACHE_ENV) go test $(GO_PACKAGES) -coverprofile=coverage.out -covermode=atomic
	$(GO_CACHE_ENV) go tool cover -html=coverage.out -o coverage.html
	@echo "✅ coverage.html"

validate-infra:
	@echo "→ 校验 M1-INFRA-A Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-infra-a
	@echo "→ 校验 M1-INFRA-C Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-infra-c
	@echo "→ 校验 M1-INFRA-D Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-infra-d
	@echo "→ 校验 M1-INFRA-E Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-infra-e
	@echo "→ 校验 M1-INFRA-F Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-infra-f
	$(MAKE) validate-gpu-preflight
	@echo "→ 校验 M1-GPU-A Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-gpu-a
	$(MAKE) validate-gpu-contracts
	@echo "→ 校验 M1-RUNTIME-A Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-runtime-a
	$(MAKE) validate-runtime-contracts
	@echo "→ 校验 M1-INSTANCE-A Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-a
	$(MAKE) validate-instance-contracts
	@echo "→ 校验 M1-INSTANCE-B Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-b
	$(MAKE) validate-instance-planner
	@echo "→ 校验 M1-INSTANCE-C Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-c
	$(MAKE) validate-instance-renderer
	@echo "→ 校验 M1-INSTANCE-D Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-d
	$(MAKE) validate-instance-admission
	@echo "→ 校验 M1-INSTANCE-E Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-e
	$(MAKE) validate-instance-audit
	@echo "→ 校验 M1-INSTANCE-F Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-f
	$(MAKE) validate-instance-provider-dry-run
	@echo "→ 校验 M1-INSTANCE-G Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-g
	$(MAKE) validate-instance-provider-apply
	@echo "→ 校验 M1-INSTANCE-H Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-h
	$(MAKE) validate-instance-status-reconcile
	@echo "→ 校验 M1-INSTANCE-I Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-i
	$(MAKE) validate-instance-orchestrator
	@echo "→ 校验 M1-INSTANCE-J Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-j
	$(MAKE) validate-instance-store
	@echo "→ 校验 M1-INSTANCE-K Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-k
	$(MAKE) validate-instance-provider-adapter
	@echo "→ 校验 M1-INSTANCE-L Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-l
	$(MAKE) validate-instance-service
	@echo "→ 校验 M1-INSTANCE-M Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-m
	$(MAKE) validate-instance-lifecycle-ops
	@echo "→ 校验 M1-E2E Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-e2e
	$(MAKE) validate-m1-e2e
	@echo "→ 校验 M1-INSTANCE-N Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-n
	$(MAKE) validate-kubernetes-provider-execution
	@echo "→ 校验 M1-INSTANCE-O Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-o
	$(MAKE) validate-kubernetes-rest-client
	@echo "→ 校验 M1-INSTANCE-P Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-p
	$(MAKE) validate-kubernetes-bootstrap-wiring
	@echo "→ 校验 M1-INSTANCE-Q Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-q
	$(MAKE) validate-kubernetes-lifecycle-execution
	@echo "→ 校验 M1-INSTANCE-R Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-instance-r
	$(MAKE) validate-kubernetes-ops-execution
	@echo "→ 校验 M1-E2E-B Kubernetes manifests..."
	python scripts/validate_k8s_yaml.py deploy/manifests/m1-e2e-b
	$(MAKE) validate-m1-real-provider-profile
	@echo "→ 校验基础设施 YAML 配置..."
	python scripts/validate_yaml.py deploy/manifests deploy/helm
	@echo "✅ infrastructure manifests valid"

validate-gpu-preflight:
	@echo "→ 校验 M1-INFRA-F GPU preflight contract..."
	python scripts/validate_gpu_preflight_contract.py deploy/manifests/m1-infra-f
	@echo "✅ GPU preflight contract valid"

validate-gpu-contracts:
	@echo "→ 校验 M1-GPU-A heterogeneous GPU contracts..."
	python scripts/validate_gpu_contracts.py deploy/manifests/m1-gpu-a
	@echo "✅ heterogeneous GPU contracts valid"

validate-runtime-contracts:
	@echo "→ 校验 M1-RUNTIME-A workload runtime contracts..."
	python scripts/validate_runtime_contracts.py deploy/manifests/m1-runtime-a
	@echo "✅ workload runtime contracts valid"

validate-instance-contracts:
	@echo "→ 校验 M1-INSTANCE-A instance contracts..."
	python scripts/validate_instance_contracts.py deploy/manifests/m1-instance-a
	@echo "✅ instance contracts valid"

validate-instance-planner:
	@echo "→ 校验 M1-INSTANCE-B instance planner contract..."
	python scripts/validate_instance_planner.py deploy/manifests/m1-instance-b
	@echo "✅ instance planner contract valid"

validate-instance-renderer:
	@echo "→ 校验 M1-INSTANCE-C provider renderer contract..."
	python scripts/validate_instance_renderer.py deploy/manifests/m1-instance-c
	@echo "✅ instance renderer contract valid"

validate-instance-admission:
	@echo "→ 校验 M1-INSTANCE-D admission guardrail contract..."
	python scripts/validate_instance_admission.py deploy/manifests/m1-instance-d
	@echo "✅ instance admission contract valid"

validate-instance-audit:
	@echo "→ 校验 M1-INSTANCE-E audit trail contract..."
	python scripts/validate_instance_audit.py deploy/manifests/m1-instance-e deploy/migrations/20260501_001_init_schema.sql
	@echo "✅ instance audit contract valid"

validate-instance-provider-dry-run:
	@echo "→ 校验 M1-INSTANCE-F provider dry-run contract..."
	python scripts/validate_instance_provider_dry_run.py deploy/manifests/m1-instance-f
	@echo "✅ instance provider dry-run contract valid"

validate-instance-provider-apply:
	@echo "→ 校验 M1-INSTANCE-G provider apply gate contract..."
	python scripts/validate_instance_provider_apply.py deploy/manifests/m1-instance-g
	@echo "✅ instance provider apply gate contract valid"

validate-instance-status-reconcile:
	@echo "→ 校验 M1-INSTANCE-H status reconcile contract..."
	python scripts/validate_instance_status_reconcile.py deploy/manifests/m1-instance-h
	@echo "✅ instance status reconcile contract valid"

validate-instance-orchestrator:
	@echo "→ 校验 M1-INSTANCE-I instance orchestration contract..."
	python scripts/validate_instance_orchestrator.py deploy/manifests/m1-instance-i
	@echo "✅ instance orchestration contract valid"

validate-instance-store:
	@echo "→ 校验 M1-INSTANCE-J instance persistence/query contract..."
	python scripts/validate_instance_store.py deploy/manifests/m1-instance-j deploy/migrations/20260501_001_init_schema.sql
	@echo "✅ instance persistence/query contract valid"

validate-instance-provider-adapter:
	@echo "→ 校验 M1-INSTANCE-K provider adapter contract..."
	python scripts/validate_instance_provider_adapter.py deploy/manifests/m1-instance-k
	@echo "✅ instance provider adapter contract valid"

validate-instance-service:
	@echo "→ 校验 M1-INSTANCE-L instance service contract..."
	python scripts/validate_instance_service.py deploy/manifests/m1-instance-l
	@echo "✅ instance service contract valid"

validate-instance-lifecycle-ops:
	@echo "→ 校验 M1-INSTANCE-M lifecycle/ops contract..."
	python scripts/validate_instance_lifecycle_ops.py deploy/manifests/m1-instance-m
	@echo "✅ instance lifecycle/ops contract valid"

validate-m1-e2e:
	@echo "→ 校验 M1 end-to-end integration profile..."
	python scripts/validate_m1_e2e_profile.py deploy/manifests/m1-e2e
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime -run TestM1E2EProfile -v
	@echo "✅ M1 end-to-end integration profile valid"

validate-kubernetes-provider-execution:
	@echo "→ 校验 M1-INSTANCE-N Kubernetes provider execution profile..."
	python scripts/validate_kubernetes_provider_execution.py deploy/manifests/m1-instance-n
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime -run TestKubernetesProviderExecutionProfile -v
	@echo "✅ Kubernetes provider execution profile valid"

validate-kubernetes-rest-client:
	@echo "→ 校验 M1-INSTANCE-O Kubernetes REST client..."
	python scripts/validate_kubernetes_rest_client.py deploy/manifests/m1-instance-o
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime -run TestKubernetesRESTClient -v
	@echo "✅ Kubernetes REST client valid"

validate-kubernetes-bootstrap-wiring:
	@echo "→ 校验 M1-INSTANCE-P Kubernetes provider bootstrap wiring..."
	python scripts/validate_kubernetes_bootstrap_wiring.py deploy/manifests/m1-instance-p
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/bootstrap -run TestNewCapabilities -v
	@echo "✅ Kubernetes provider bootstrap wiring valid"

validate-kubernetes-lifecycle-execution:
	@echo "→ 校验 M1-INSTANCE-Q Kubernetes lifecycle execution..."
	python scripts/validate_kubernetes_lifecycle_execution.py deploy/manifests/m1-instance-q
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime ./pkg/bootstrap -run 'TestKubernetesLifecycleExecutor|TestLocalInstanceServiceLifecycleUsesProviderExecutor|TestNewCapabilitiesCanWireKubernetesRESTLifecycleProvider|TestNewCapabilitiesRejectsKubernetesRESTLifecycleWithoutHost' -v
	@echo "✅ Kubernetes lifecycle execution valid"

validate-kubernetes-ops-execution:
	@echo "→ 校验 M1-INSTANCE-R Kubernetes visual ops execution..."
	python scripts/validate_kubernetes_ops_execution.py deploy/manifests/m1-instance-r
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime ./pkg/bootstrap -run 'TestKubernetesInstanceOps|TestNewCapabilitiesCanWireKubernetesRESTOpsProvider|TestNewCapabilitiesRejectsKubernetesRESTOpsWithoutHost' -v
	@echo "✅ Kubernetes visual ops execution valid"

validate-m1-real-provider-profile:
	@echo "→ 校验 M1-E2E-B real provider integration regression profile..."
	python scripts/validate_m1_real_provider_profile.py deploy/manifests/m1-e2e-b
	GOCACHE=/private/tmp/ani-go-build GOMODCACHE=$(CURDIR)/.cache/gomod go test ./pkg/adapters/runtime -run TestM1RealProviderProfile -v
	@echo "✅ M1 real provider integration regression profile valid"

validate-demo-instances:
	@echo "→ 校验阶段性 VM/container/GPU container Demo API..."
	$(GO_CACHE_ENV) go test ./services/ani-gateway/internal/router -run TestDemoInstanceService -v
	@echo "✅ staged instance demo API valid"

validate-auth-contract:
	@echo "→ 校验 M2.2 Auth Gateway/API 契约..."
	python scripts/validate_auth_gateway_contract.py
	@echo "✅ Auth Gateway/API contract valid"

validate-auth-dex-smoke:
	@echo "→ 启动 Dex 并校验 OIDC auth-code flow..."
	$(COMPOSE) --profile auth up -d dex
	python scripts/smoke_auth_dex.py
	@echo "✅ Dex OIDC smoke passed"

validate-architecture:
	@echo "→ 校验开源组件 ports/adapters 边界..."
	python scripts/validate_component_imports.py --root .
	@echo "✅ architecture guardrails valid"

# ── 代码检查 ──────────────────────────────────────────────────────────────────
lint: lint-go lint-python lint-ts

lint-go:
	@echo "→ Go 静态分析..."
	golangci-lint run ./...
	gosec -severity high ./services/... ./operators/...

lint-python:
	@echo "→ Python 代码检查..."
	cd ai && ruff check . && mypy .

lint-ts:
	@echo "→ TypeScript 代码检查..."
	cd frontends && pnpm lint

# ── 本地开发（热重载）────────────────────────────────────────────────────────
dev-gateway:
	@echo "→ 启动 ANI Gateway（air 热重载）..."
	cd services/ani-gateway && air

dev-console:
	@echo "→ 启动 Console 前端（Vite HMR）..."
	cd frontends/console && pnpm dev

# ── 镜像构建 ──────────────────────────────────────────────────────────────────
REGISTRY ?= harbor.ani.internal/ani

image: image-gateway

image-gateway:
	docker build -t $(REGISTRY)/ani-gateway:$(VERSION) \
		-f services/ani-gateway/Dockerfile \
		services/ani-gateway

# ── 清理 ──────────────────────────────────────────────────────────────────────
clean:
	rm -rf bin/
	find . -name '*.test' -delete
	find . -name 'coverage.out' -delete
