# ANI · 当前冲刺上手指南

> **新开发者（人类或 AI 工具）的第一个入口文件。**
> 读完本文件，5 分钟内明确：当前做什么、怎么开始、怎么验证完成。
> 已完成批次只查 `repo/development-records/README.md`，不要把历史细节塞回本文。

---

## 当前冲刺

| 字段 | 值 |
|---|---|
| **冲刺编号** | Sprint 3 |
| **时间范围** | 2026-05-20 提前启动；计划窗口 2026-06-16 → 2026-06-30 |
| **主题** | Core API 面扩充（网络 + 存储 + 向量 + Workload Identity）+ SDK Alpha |
| **核心批次** | M1-NETWORK-A + M1-STORAGE-A + M1-VSTORE-A + M1-WKID-A + SDK-ALPHA-A + MOCK-DEV-A |
| **前置验证** | Sprint 2 已完成：Core API Alpha Freeze、VM 生产级操作、Container/GPU 深度本地 profile |

---

## 本冲刺目标

Sprint 3 的目标是在 Core API Alpha 已冻结的基础上，继续扩充 Services P0 所需的基础设施 API 面，并让 SDK/dev profile 进入可联调状态。

1. 补齐网络资源 API：VPC、子网、安全组、LB 的 Core 契约与 dev/local profile。
2. 补齐存储资源 API：volumes、filesystems、objects 的 Core 契约与 dev/local profile。
3. 补齐 vector-stores Core API，并复用既有 Milvus adapter 边界。
4. 建立 Workload Identity P0：实例生命周期绑定 scoped API key。
5. 输出 Go/Python/TypeScript/Java SDK Alpha，并完成生成/import/compile smoke test。
6. 保持 Sprint 2 冻结的 `/api/v1/instances` 不发生 breaking change。

---

## P0：M1-NETWORK-A

**状态：🔄 当前优先**

**主题：网络资源 Core API 面**

### 最小实现切片

1. 在 `api/openapi/v1.yaml` 增加 VPC、Subnet、SecurityGroup、LB 的 Alpha path/schema/RBAC scope。
2. Gateway 注册主路径，先提供 dev/local profile 或 contract-compatible mock。
3. 网络资源状态必须包含 owner tenant、state、reason、created_at、updated_at。
4. 新增合同守卫，防止网络 path/schema/RBAC scope 漂移。

### 验收方向

```bash
make test
make validate-architecture
git diff --check
# 定向测试应覆盖：
# - POST /api/v1/networks/vpcs → 201 Created
# - GET /api/v1/networks/vpcs → 返回租户隔离列表
# - 网络 API 不出现在 Services API 契约中
```

---

## P0：M1-STORAGE-A

**状态：⏳ 待开始**

**主题：存储资源 Core API 面**

### 最小实现切片

1. 增加 volumes、filesystems、objects 的 Core API Alpha 契约。
2. dev/local profile 返回与真实状态机兼容的 `pending/available/failed/deleting/deleted` 状态。
3. 与 instances 的 volume binding 字段保持兼容，不引入双写语义冲突。

### 验收方向

```bash
make test
# 定向测试应覆盖：
# - POST /api/v1/volumes → 201 Created
# - GET /api/v1/volumes/{id} → 返回容量、类型、状态、租户
```

---

## P0：M1-VSTORE-A

**状态：⏳ 待开始**

**主题：vector-stores Core API**

### 最小实现切片

1. 将 vector-stores 作为 Core 基础设施资源维护在 `api/openapi/v1.yaml`。
2. Gateway dev/local profile 支持 create/list/get/delete。
3. 访问 Milvus 必须经 `pkg/ports` / `pkg/adapters`，不允许 Services 直接 import Milvus SDK。

---

## P0：M1-WKID-A

**状态：⏳ 待开始**

**主题：Workload Identity P0**

### 最小实现切片

1. 实例创建时生成 lifecycle-bound scoped API key。
2. 实例删除时 revoke 对应 key。
3. Workload Identity 不使用长期静态 API Key。
4. operation timeline 记录 identity 绑定与撤销。

---

## P0：SDK-ALPHA-A

**状态：⏳ 待开始**

**主题：四语言 SDK Alpha**

### 最小实现切片

1. 从 `api/openapi/v1.yaml` 生成 Go/Python/TypeScript/Java Core SDK。
2. 从 `api/openapi/services/v1.yaml` 生成 Services SDK，不混入 Core 类型。
3. 每个 SDK 至少有 import/compile smoke test。

---

## P0：MOCK-DEV-A

**状态：⏳ 待开始**

**主题：Core dev profile / mock profile**

### 最小实现切片

1. dev/local profile 的状态机和错误语义与真实实现一致。
2. 不保留无 owner/date 的 `NOT_IMPLEMENTED` stub 于 Services P0 依赖路径。
3. mock success 必须能被合同测试识别，不能伪装成 real provider。

---

## 本冲刺不做

- 不进入 Phase 2 延期项。
- 不把 Services 业务逻辑写进 Core。
- 不绕过 `pkg/ports/` 直接调用 K8s/KubeVirt/MinIO/Milvus SDK。
- 不破坏 Sprint 2 已冻结的 Core API Alpha instance 契约。
- 不在没有 API 契约和测试的情况下直接生成实现代码。

---

## 代码结构 10 分钟导航

```
必读（按顺序）：
  1. CLAUDE.md
  2. ANI-DOCS-INDEX.md
  3. ANI-06-开发计划.md 的 Section 零和 Sprint 3
  4. api/openapi/v1.yaml
  5. api/core-alpha-freeze.yaml
  6. pkg/ports/
  7. pkg/adapters/

查历史：
  - repo/development-records/README.md
  - repo/development-records/spec-core-alpha-b-freeze-matrix.md
```

---

## 环境启动

```bash
cd /path/to/ANI/repo

make build
make test
make validate-architecture
make validate-core-alpha
```

---

## 完工后必做

每完成一个批次或可独立验收切片，按顺序执行：

```text
1. make test
2. make validate-architecture
3. git diff --check
4. 新建或更新 repo/development-records/{批次名}.md
5. 更新 repo/development-records/README.md
6. 更新本文件对应批次状态
7. 更新 ANI-06-开发计划.md Section 零对应批次状态
```

完整规约说明：`CLAUDE.md` → "📋 开发进度更新规约"。

---

*Sprint 3 负责人：[填入]　最后更新：2026-05-20*
