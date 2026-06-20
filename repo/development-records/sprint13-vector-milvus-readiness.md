# Sprint 13 切片 06 — vector document insert Milvus real provider 就绪声明

> 记录类型：Per-slice readiness（ANI-06「真实底座组件引入强制门禁」§153 的执行前声明）
> 工件归属：Sprint 13 / Core real provider 与 live gate 收敛
> 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
> 状态：**production-shaped gate passed**（Milvus 临时真实组件、production-shaped Gateway 接线、Auth/Dex bearer 登录与 vector store create / document insert / search readiness / cleanup 已跑通）。历史 `LIVE PENDING` token 仅保留作门禁兼容语境。

---

## 0. 已核对的真实事实（禁止臆测）

1. Sprint 12 已落地 vector store Core API contract：`createVectorStore`、`searchVectorStore` 与 `insertVectorStoreDocuments` 均在 `vector_store_resources.go` 经 `ports.VectorStoreService` 暴露。
2. `ports.VectorStore` 已存在 `EnsureCollection`、`Upsert`、`Search`、`Delete`、`Health` 边界；`LocalVectorStoreService.InsertDocuments` 在显式注入 backend 时会复用 `ports.VectorStore.Upsert`，并返回 202 形态的 document insert task。
3. OpenAPI 已定义 `VectorStoreDocumentInsertRequest` / `VectorStoreDocumentInsertResponse`，POST 请求保留 `idempotency_key`，RBAC scope 保持 `scope:vector-stores:write`。
4. S06 B 轨已在独立 namespace 部署临时 Milvus/etcd/MinIO 验证栈，全部使用 `emptyDir`，未触碰 Rook-Ceph、CSI、默认 StorageClass、系统盘或 ANI3 裸盘。
5. production-shaped Gateway 已通过 `VECTOR_STORE_PROVIDER=milvus` 与 SecretRef 读取 Milvus runtime 配置；当前 Gateway 节点 hostPath binary 已更新并滚动成功，Gateway 启动日志确认 Milvus provider runtime 已配置。
6. Milvus REST readiness 与 Gateway Deployment readiness 已通过只读核验；真实业务 evidence 已生成并归档到 `development-records/live-evidence/sprint13-vector-milvus-live-evidence.json`。Auth/Dex bearer 只在进程内传递，未写入 evidence 或文档。
7. Milvus REST quick-setup schema 在 VarChar 主键下要求 `params.max_length`；`MilvusVectorStore.EnsureCollection` 已补该字段并由 fake transport 单测固定。

## 1. §153 五项声明

| 项 | 内容 |
|---|---|
| **当前状态** | Milvus adapter、Gateway runtime 注入、production-shaped Deployment env、临时真实 Milvus 组件与真实业务 live gate 均已通过；S06 为 production-shaped acceptance passed。 |
| **真实组件 + 版本** | 临时验证栈使用 Milvus standalone（REST v2）、etcd 与 MinIO；组件部署在独立 namespace，数据卷为 `emptyDir`，仅用于 S06 live gate 验证，不代表长期生产部署。 |
| **live gate 命令** | 本地契约：`make validate-vector-alpha validate-vector-store-live-gate`；真实 B 轨：`python scripts/validate_vector_store_live_gate.py --live --production-shaped --cleanup --gateway-url <redacted>/api/v1 --ani-bearer-token <redacted> --milvus-url <redacted> --evidence-output development-records/live-evidence/sprint13-vector-milvus-live-evidence.json`。 |
| **evidence 输出路径** | `repo/development-records/sprint13-vector-milvus-live-result.md` + `repo/development-records/live-evidence/sprint13-vector-milvus-live-evidence.json`；不得归档 token、URL、完整连接串、IP 或敏感 payload。 |
| **失败边界（不得声称）** | 本结果不代表 full platform production ready；不得把临时 `emptyDir` Milvus 验证栈解释为长期 HA/持久化生产拓扑，不得用 local deterministic vector profile、kubectl-only evidence 或伪造 JWT token 替代真实 bearer evidence。 |

## 2. 代码边界

- A 轨新增 `pkg/adapters/vectorstore/MilvusVectorStore`，实现既有 `ports.VectorStore`，不改 port 接口签名，不改 Gateway handler，不新增 `/api/v1/svc`。
- adapter 使用标准 HTTP 调 Milvus REST v2 contract：collection create/describe、entities upsert/search/delete；fake 单测锁定请求路径、Authorization、collection naming、document metadata 和 search hit 映射。
- `pkg/bootstrap` 仅在 `VECTOR_STORE_PROVIDER=milvus` 显式配置时构造并注入 Milvus vector store；默认 dev/local profile 不变，避免把未配置 adapter 误标为 runtime ready。
- Gateway B 轨补齐 `services/ani-gateway/vector_store_runtime.go`，从 `VECTOR_STORE_PROVIDER` / `VECTOR_STORE_ENDPOINT` / `VECTOR_STORE_TOKEN` / `VECTOR_STORE_DATABASE` / `VECTOR_STORE_COLLECTION_PREFIX` 读取运行时配置并注入 `ports.VectorStoreService`。
- `scripts/validate_vector_store_live_gate.py` 已支持 `--live`、`--production-shaped`、`--cleanup` 与非敏感 evidence 输出；production-shaped 模式要求非本地 Gateway/Milvus 入口和显式 bearer token，S06 evidence 已通过该门禁。

## 3. 真实服务器安全

- 临时 Milvus 验证组件只用于 live gate，不作为长期生产存储；长期方案需另行评审 Rook-Ceph PVC / Ceph RGW / 分布式 MinIO 或 Milvus Operator 持久化拓扑。
- Auth/Dex bearer 已通过本地-only 密码文件完成 OIDC 登录，token 只在进程内使用；禁止读取真实集群 JWT 私钥自行签发 tenant-admin token。
- 凭据、token、endpoint、IP 不得写入可提交文件、evidence 或回复。

## 4. 当前已通过门禁

```bash
cd repo && make validate-vector-alpha && make validate-vector-store-live-gate
GOCACHE=/private/tmp/ani-go-build GOMODCACHE=/Users/zhangfan/ANI/repo/.cache/gomod go test ./services/ani-gateway ./services/ani-gateway/internal/router ./pkg/adapters/vectorstore ./pkg/adapters/runtime -run 'TestGatewayVectorStore|TestVectorStoreAPI|TestMilvusVectorStore|TestLocalVectorStoreService' -v
python scripts/validate_vector_store_live_gate.py --live --production-shaped --cleanup --gateway-url <redacted>/api/v1 --ani-bearer-token <redacted> --milvus-url <redacted> --evidence-output development-records/live-evidence/sprint13-vector-milvus-live-evidence.json
```

`make validate-sprint13-b-track-production-shape` 已纳入 `sprint13-vector-milvus-live-evidence.json` 与 live result 的 production-shaped proof_items 校验。

## 5. 关联文档

- Sprint 13 执行地图：[`sprint13-real-provider-readiness-plan.md`](sprint13-real-provider-readiness-plan.md)
- 当前冲刺入口：[`../CURRENT-SPRINT.md`](../CURRENT-SPRINT.md)
- S06 A 轨记录：[`sprint13-vector-milvus-a-track.md`](sprint13-vector-milvus-a-track.md)
- S06 B 轨 live result：[`sprint13-vector-milvus-live-result.md`](sprint13-vector-milvus-live-result.md)
- 代码：`pkg/ports/vector_store.go`、`pkg/adapters/vectorstore/milvus_store.go`、`pkg/bootstrap/deps.go`、`services/ani-gateway/vector_store_runtime.go`、`services/ani-gateway/internal/router/vector_store_resources.go`
