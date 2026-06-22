# R-P2-7 · Multi-Endpoint Failover Config

> 记录类型：Execution / Sprint 14 Core resilience
> 完成日期：2026-06-23
> 分支：`feature/sprint14-core-resilience-semantics`
> 状态：local/logic verified；未执行真实 primary kill / HA topology failover；不声明 failover production ready

## 范围

本批把 Sprint 14 F7 的“全线单 endpoint”推进到可配置多端点形态：

- Redis bootstrap 改为 `redis.UniversalClient`，新增 `RedisConfig`，支持：
  - 向后兼容单 `REDIS_URL`。
  - `REDIS_MODE=sentinel` + `REDIS_ADDRS` + `REDIS_MASTER_NAME`。
  - `REDIS_MODE=cluster` + 多个 `REDIS_ADDRS`。
  - gateway 侧支持 `GATEWAY_REDIS_*` 覆盖，未设置时继续使用既有默认 `REDIS_URL`。
- MinIO object-store adapter 新增 `Endpoints []string`，接受单 endpoint、endpoint list 或 LB/VIP，保持第一个可用 endpoint 作为当前请求目标。
- Milvus vector-store adapter 新增 `Endpoints []string`，接受单 endpoint、endpoint list 或 LB/VIP，保持第一个可用 endpoint 作为当前请求目标。
- `bootstrap.Config`、Gateway storage/vector runtime env 增加 `OBJECT_STORE_ENDPOINTS`、`VECTOR_STORE_ENDPOINTS` 接线。
- 新增 `make validate-ha-failover-live-gate`，当前包装本地配置解析与装配测试；命名沿用计划里的 gate 名称，但输出明确标注未执行真实 primary kill / topology failover。

## 非范围 / 未完成

- 未实现 MinIO/Milvus 请求失败后的自动端点轮换；本批只让 adapter 不再拒绝端点列表，并为后续真实 HA 拓扑留出配置入口。
- 未实现 PostgreSQL 读副本路由；现阶段 `DatabaseURL` 仍是单 URL，只能由外部 VIP / proxy 提供 HA。
- 未执行 Redis Sentinel/Cluster、MinIO、Milvus 或 PG 的真实主节点 kill / 网络分区 / failover 演练。
- 未产出 HA failover evidence JSON，因此不得标记 production failover ready。

## 验证

已通过本地/逻辑门禁：

```bash
go test ./pkg/bootstrap ./pkg/adapters/redis ./pkg/adapters/objectstore ./pkg/adapters/vectorstore ./services/ani-gateway
make validate-ha-failover-live-gate
```

批次收口还需与本分支常规门禁一起执行：

```bash
make test
make validate-architecture
make validate-doc-entrypoints
git diff --check
```
