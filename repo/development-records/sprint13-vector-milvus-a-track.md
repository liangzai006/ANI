# Sprint 13 S06 - vector document insert Milvus A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：code+contract ready, LIVE PENDING

## 目标

把 Sprint 12 已落地的 vector document insert 从 Tier1 local profile 扩展到 Milvus 的真实 provider contract 代码边界。A 轨只做 adapter 代码、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 Milvus、不执行真实 collection write/search、不跑真实 live gate。

## 实现

- `pkg/adapters/vectorstore/milvus_store.go`
  - 新增 `MilvusVectorStore`，实现既有 `ports.VectorStore`。
  - `EnsureCollection` 调 Milvus REST v2 collection create contract，使用 quick-setup schema 字段并按 tenant/store 生成安全 collection name。
  - `Upsert` 调 `/v2/vectordb/entities/upsert`，把 `VectorRecord` 映射为 `id`、`vector`、`content` 与 `metadata`。
  - `Search` 调 `/v2/vectordb/entities/search`，映射 Milvus hit 为 `VectorSearchResult`；`Delete` 与 `Health` 分别使用 entities delete 与 collection describe contract。
- `pkg/bootstrap/deps.go` / `pkg/bootstrap/server.go`
  - 新增显式 `VECTOR_STORE_PROVIDER=milvus` 配置路径，构造 Milvus vector store 并注入 `VectorStoreResources`。
  - 默认配置保持 `vectorstore.NotConfigured{}` 且不注入 `VectorStoreResources`，Gateway dev/local profile 语义不变。
- `deploy/real-k8s-lab/vector-store-live-gate.yaml`
  - 新增 `SPRINT13-VECTOR-MILVUS-A` vector-store live gate contract。
- `scripts/validate_vector_store_live_gate.py`
  - 新增 contract validator，固定 Milvus readiness、Core vector store create、document insert 202、search readiness 四个 check；`--live` 保持 human-gated，不在 A 轨自动执行。

## 边界

- 未修改 `ports.VectorStore` / `ports.VectorStoreService` 签名。
- 未修改 Gateway handler。
- 未新增 `/api/v1/svc`。
- 未执行真实服务器/集群写操作。
- 未把 vector document insert 标记为 real-provider/runtime/production ready。

## 验证

已执行最终门禁：

```bash
cd repo && make test && make validate-vector-alpha validate-vector-store-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

关键输出：

```text
component import guard passed
auth gateway contract valid
PASS
TestMilvusVectorStoreEnsuresCollectionWithQuickSetupSchema PASS
TestMilvusVectorStoreUpsertPostsRecordsToEntitiesEndpoint PASS
TestMilvusVectorStoreSearchMapsHits PASS
TestNewCapabilitiesCanWireMilvusVectorStoreProvider PASS
vector alpha contract valid
SPRINT13-VECTOR-MILVUS-A contract valid; live execution is human-gated
Ran 6 tests in 0.007s
OK
validated 1 YAML files
document entrypoint boundaries valid
git diff --check passed
```

## 后续 B 轨

人工确认真实 Milvus endpoint、token、database、collection prefix、schema/index 策略和 evidence 输出路径后，执行 human-gated live gate 并归档非敏感 evidence。真实 evidence 归档前，S06 保持 Tier1 local profile / LIVE PENDING。
