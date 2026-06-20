# Sprint 13 S06 - vector document insert Milvus A-track

> 记录类型：Sprint 13 A-track completion record
> 日期：2026-06-19
> 范围：ANI Core only
> 状态：code+contract ready；后续 B 轨已通过 production-shaped live gate（历史 LIVE PENDING 阻塞已解除）

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

## 后续 B 轨结果

后续 B 轨已完成以下非敏感进展：

- 独立 namespace 临时部署 Milvus standalone + etcd + MinIO 验证栈，数据卷均为 `emptyDir`，未触碰 Rook-Ceph / CSI / 默认 StorageClass / 裸盘。
- production-shaped Gateway 已补 `VECTOR_STORE_PROVIDER=milvus` 与 `ani-vectorstore-production-shaped-runtime` SecretRef 装配，当前 Gateway 节点 binary 已更新并滚动成功，启动日志确认 Milvus provider runtime configured。
- `validate_vector_store_live_gate.py` 已补 `--live`、`--production-shaped`、`--cleanup` 和 evidence 输出；proof_items 对齐 `production_gateway`、`production_vector_store_credentials`、`production_vector_collection_lifecycle`。
- Milvus REST quick-setup schema 的 VarChar 主键要求 `params.max_length`；adapter 已补字段并用 fake transport 单测固定。
- `make validate-vector-alpha`、`make validate-vector-store-live-gate`、S06 聚焦 Go 单测与真实 `validate_vector_store_live_gate.py --live --production-shaped --cleanup` 已通过。

结果：`sprint13-vector-milvus-live-evidence.json` 已归档，`production_shape.status=passed`；live result 见 [`sprint13-vector-milvus-live-result.md`](sprint13-vector-milvus-live-result.md)。Auth/Dex bearer 通过本地-only Dex 密码文件完成 OIDC 登录，仅在进程内使用；未读取 JWT 私钥，未把 token、endpoint 或 IP 写入 evidence。
