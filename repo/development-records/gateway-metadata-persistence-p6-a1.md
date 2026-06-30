# GATEWAY-METADATA-PERSISTENCE-P6-A1

> 记录类型：Feature batch / Core Gateway metadata persistence（阶段 A · A1）
> 完成日期：2026-06-30
> 范围：ANI Core / ani-gateway K8s 集群与节点池控制面元数据 PostgreSQL 持久化

## 目标

`DATABASE_URL` 启用时，K8s 集群与节点池元数据 write-through 并 List/Get 读 PG；Gateway 重启后可恢复集群/节点池列表。与既有 `k8s_cluster_proxy_targets`（proxy 凭据）互补，不持久化 kubeconfig 明文、workloads 列表或 proxy 响应体。

## 实现

- Migration `20260629_018_gateway_metadata_p6_a1.sql`：`k8s_clusters`、`k8s_cluster_node_pools` 及 RLS。
- 新增 `ports.K8sClusterResourceStore` 与 `pkg/adapters/runtime/k8s_cluster_store.go`（`MetadataK8sClusterStore`）。
- `localK8sClusterService` 增加 `WithK8sClusterResourceStore`：Create/Upgrade/Delete/NodePool 变更写 PG；List/Get 读 PG。
- `newGatewayK8sClusterBaseService`：`MetadataStore != nil` 时注入 resource store；local profile 不再走 router 纯内存 fallback。
- 同步 `deploy/postgres/gateway-metadata-schema.sql`、`deploy/postgres/ani-dev-database-init.sql` 等 dev init。
- 新增 `make validate-gateway-metadata-p6-a1`；聚合 gate 扩展为 P0–P5 + P6-A1。

## 覆盖范围

| 资源 | Create/Upsert PG | List/Get 读 PG |
|------|------------------|----------------|
| K8sCluster | ✅ | ✅ |
| K8sClusterNodePool | ✅ | ✅ |

不持久化：kubeconfig 生成结果、proxy 响应、workloads 列表（仍按 local/real provider 即时生成）。`k8s_cluster_proxy_targets` 仍由既有 proxy target store 维护。

创建幂等（`idempotency_key`）跨进程读 PG；upgrade / node pool update 幂等仍主要依赖进程内 map（与 P2–P5 同类边界）。

## 验收

```bash
cd repo
make validate-gateway-metadata-p6-a1
make validate-gateway-metadata   # 含 P6-A1
```

真实 PostgreSQL 冒烟（可选）：

```bash
export DATABASE_URL=postgres://ani:ani_dev_password@127.0.0.1:5432/ani?sslmode=disable
export ANI_AUTH_MODE=dev GATEWAY_HTTP_ADDR=:8080
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f deploy/migrations/20260629_018_gateway_metadata_p6_a1.sql
# 启动 Gateway → POST /k8s-clusters → 重启 → GET /k8s-clusters 仍在
```

## 边界

- `DATABASE_URL` 未设：保持内存模式。
- 不标 real-provider / production ready。
- 阶段 A 后续：A2 Secrets 元数据、A3 branding/logo、A4 encryption keys（延后）。
