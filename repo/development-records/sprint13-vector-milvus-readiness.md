# Sprint 13 切片 06 — vector document insert Milvus real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**code+contract ready, LIVE PENDING**（A 轨已完成；尚未跑通真实 live gate）。在 evidence 产出前，vector document insert 只可标 Tier1 local profile。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 vector store Core API contract：`createVectorStore`、`searchVectorStore` 与 `insertVectorStoreDocuments` 均在 `vector_store_resources.go` 经 `ports.VectorStoreService` 暴露。
2. `ports.VectorStore` 已存在 `EnsureCollection`、`Upsert`、`Search`、`Delete`、`Health` 边界；`LocalVectorStoreService.InsertDocuments` 在显式注入 backend 时会复用 `ports.VectorStore.Upsert`，并返回 202 形态的 document insert task。
3. OpenAPI 已定义 `VectorStoreDocumentInsertRequest` / `VectorStoreDocumentInsertResponse`，POST 请求保留 `idempotency_key`，RBAC scope 保持 `scope:vector-stores:write`。
4. S06 A 轨只允许新增 Milvus adapter、fake/mock 单测、契约级 live-gate 和文档闭环；不部署 Milvus，不执行真实 collection 写入/search，不跑真实 live gate。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | contract + Tier1 local profile；Gateway 默认仍使用 local vector store profile；A 轨已新增 `MilvusVectorStore` adapter，并在 `VECTOR_STORE_PROVIDER=milvus` 显式配置时可注入 `VectorStoreResources`。 |
| **真实组件 + 版本** | Milvus；具体 Milvus 版本、REST endpoint、token、database、collection schema 与 index/search readiness 策略需 B 轨执行前在真实 lab 只读确认。 |
| **live gate 命令** | 本地契约：`make validate-vector-alpha validate-vector-store-live-gate`；真实 B 轨：`python scripts/validate_vector_store_live_gate.py --live --evidence-output <path>` 的执行仍为 human-gated，需先人工确认 Milvus endpoint 与凭据来源。 |
| **evidence 输出路径** | `repo/development-records/sprint13-vector-milvus-live-result.md` + 非敏感 evidence JSON；不得归档 token、完整连接串或敏感 payload。 |
| **失败边界（不得声称）** | 若 `/vector-stores/{id}/documents` 与 search readiness 未在真实 Milvus 后端跑通并归档 evidence，不得标 real-provider / runtime ready / production ready；不得用 local deterministic vector profile 替代 Milvus evidence。 |

## 2. 代码边界

- A 轨新增 `pkg/adapters/vectorstore/MilvusVectorStore`，实现既有 `ports.VectorStore`，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- adapter 使用标准 HTTP 调 Milvus REST v2 contract：collection create/describe、entities upsert/search/delete；fake 单测锁定请求路径、Authorization、collection naming、document metadata 和 search hit 映射。
- `pkg/bootstrap` 仅在 `VECTOR_STORE_PROVIDER=milvus` 显式配置时构造并注入 Milvus vector store；默认 dev/local profile 不变，避免把未配置 adapter 误标为 runtime ready。

## 3. 真实服务器安全

- A 轨不部署 Milvus，不创建真实 collection，不写入真实向量，不执行真实 search。
- B 轨执行前必须由人工确认 Milvus endpoint、token、database、collection prefix、schema/index 策略和 evidence 输出路径；凭据不得写入可提交文件或回复。

## 4. 完成判定（A 轨）

```bash
cd repo && make test && make validate-vector-alpha validate-vector-store-live-gate && python scripts/validate_yaml.py api/openapi/v1.yaml && make validate-doc-entrypoints && git diff --check
```

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- S06 A 轨记录：[`sprint13-vector-milvus-a-track.md`](sprint13-vector-milvus-a-track.md)
- 代码：`pkg/ports/vector_store.go`、`pkg/adapters/vectorstore/milvus_store.go`、`pkg/bootstrap/deps.go`、`services/ani-gateway/internal/router/vector_store_resources.go`
