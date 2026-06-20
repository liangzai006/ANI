# Sprint 13 S06 - vector Milvus live result

> 记录类型：Sprint 13 B-track production-shaped live result
> 日期：2026-06-21
> 范围：ANI Core only
> 状态：production-shaped gate passed；不代表 full platform production ready

## 结论

S06 vector document insert Milvus B 轨已通过 production-shaped live gate。production-shaped Gateway 使用 `VECTOR_STORE_PROVIDER=milvus` 注入 Milvus-backed `ports.VectorStoreService`，经 Auth/Dex bearer 调用 Core v1 vector store API，完成 vector store create、documents insert、search readiness 与 cleanup。

非敏感 evidence 已归档：

```text
development-records/live-evidence/sprint13-vector-milvus-live-evidence.json
```

evidence 中 `production_shape.status=passed`，proof_items 为：

```text
production_gateway
production_vector_store_credentials
production_vector_collection_lifecycle
```

## 执行摘要

- 临时 Milvus standalone + etcd + MinIO 验证栈部署在独立 namespace，使用 `emptyDir`，仅用于 S06 live gate。
- Gateway live Deployment 已配置 `VECTOR_STORE_PROVIDER=milvus`，Milvus runtime 配置通过 SecretRef 注入，未写入仓库。
- Auth/Dex 使用本地-only 密码文件完成受控 OIDC 登录，bearer 只在进程内传递，未写入 evidence 或文档。
- live gate 通过 `validate_vector_store_live_gate.py --live --production-shaped --cleanup` 验证 Milvus readiness、Core vector store create、document insert 202、search readiness 和 cleanup。
- Milvus REST quick-setup schema 在 VarChar 主键下需要 `params.max_length`；adapter 已补该字段并由 fake transport 单测固定。

## 验证结果

Production-shaped gate: passed

```text
SPRINT13-VECTOR-MILVUS-A live checks passed
```

evidence 关键字段：

```text
milvus_health_status=200
vector_store_create_status=201
document_insert_status=202
search_status=200
inserted_count=1
search_hit_count=1
cleanup_enabled=true
cleanup_status=200
cleanup_api_key_status=201
cleanup_api_key_revoke_status=200
```

## 边界

本结果只证明 S06 在 Sprint 13 production-shaped acceptance 标准下通过，not production ready，不代表长期生产部署完成。临时 Milvus 栈仍是验证用途；正式生产拓扑、持久化、备份恢复、升级回滚、HA/soak、故障注入和容量规划需后续 release gate 单独验收。

历史 `LIVE PENDING` token 仅保留在入口文档和 A-track 语境中，用于兼容文档硬门禁；当前 S06 B 轨状态以本文件和 evidence 为准。
