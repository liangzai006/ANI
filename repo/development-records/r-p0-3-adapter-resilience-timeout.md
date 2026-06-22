# R-P0-3 · Adapter Per-Call Timeout / Resilience Skeleton

> 日期：2026-06-23
> 分支：`feature/sprint14-core-resilience-semantics`
> 状态：Completed（local/logic verified）
> 范围：ANI Core only；不触碰 ANI Services 业务逻辑，不修改 `api/openapi/services/v1.yaml`

## 目标

为 Sprint 14 P0 建立 `pkg/adapters/resilience` 包骨架，并先实现每调用 timeout。Kubernetes REST client、MinIO object store、Milvus vector store 的每次外部 HTTP 调用都可以通过 adapter config 注入 deadline。

本批只证明 local/logic 行为：请求超过 `RequestTimeout` 会通过 request context 返回 deadline exceeded。未执行真实故障注入或 live gate，因此不声明 production ready。

## 实现

- 新增 `pkg/adapters/resilience`：
  - `Policy.Timeout`
  - `Do(ctx, policy, fn)` 的 timeout 分支
  - `Retryable(err)` 先保持 false，留给 R-P1-5 实现重试/断路器
- `pkg/adapters/runtime/kubernetes_rest_client.go`：
  - `KubernetesRESTClientConfig.RequestTimeout`
  - 在共享 `do()` 外层包 `resilience.Do`
  - network/storage/k8s/gpu/secret 等复用该 client 的路径继承同一能力
- `pkg/adapters/objectstore/minio_store.go`：
  - `MinIOObjectStoreConfig.RequestTimeout`
  - 所有实际 `client.Do` 通过 `resilience.Do` 执行
- `pkg/adapters/vectorstore/milvus_store.go`：
  - `MilvusVectorStoreConfig.RequestTimeout`
  - `doMilvus` 的 HTTP 调用通过 `resilience.Do` 执行
- `services/ani-gateway/*_runtime.go`：
  - `KUBERNETES_REQUEST_TIMEOUT`
  - `OBJECT_STORE_REQUEST_TIMEOUT`
  - `VECTOR_STORE_REQUEST_TIMEOUT`
  - 空值、非法值、非正值保持 `0`，等价旧行为
- `Makefile` 新增 `validate-adapter-resilience-timeout`。

## TDD 证据

先写失败测试并观察红灯：

```bash
GOCACHE=/private/tmp/ani-go-build GOMODCACHE=/Users/zhangfan/ANI/repo/.cache/gomod go test ./pkg/adapters/resilience ./pkg/adapters/runtime ./pkg/adapters/objectstore ./pkg/adapters/vectorstore -run 'TestDoEnforcesTimeout|TestKubernetesRESTClientEnforcesRequestTimeout|TestMinIOObjectStoreEnforcesRequestTimeout|TestMilvusVectorStoreEnforcesRequestTimeout' -v
```

红灯原因：

- `undefined: Do`
- `undefined: Policy`
- `unknown field RequestTimeout`

实现后绿灯：

```bash
make validate-adapter-resilience-timeout
```

结果：PASS。

相关包回归：

```bash
GOCACHE=/private/tmp/ani-go-build GOMODCACHE=/Users/zhangfan/ANI/repo/.cache/gomod go test ./pkg/adapters/resilience ./pkg/adapters/runtime ./pkg/adapters/objectstore ./pkg/adapters/vectorstore ./services/ani-gateway/...
```

结果：PASS。普通 sandbox 下 `httptest` 本地监听被拒绝，使用提升权限复跑同一命令通过；该失败不是代码断言失败。

## 验收

- `make validate-adapter-resilience-timeout`：PASS
- `go test ./pkg/adapters/resilience ./pkg/adapters/runtime ./pkg/adapters/objectstore ./pkg/adapters/vectorstore ./services/ani-gateway/...`：PASS

收口前还需按 Sprint 14 规则执行：

- `make test`
- `make validate-architecture`
- `make validate-doc-entrypoints`
- `git diff --check`

## 边界

- 未实现重试、退避、断路器；这些留给 R-P1-5。
- 未新增数据面 readyz；这留给 R-P0-4。
- 未执行真实 fault-injection/live gate，因此只标 local/logic verified。
