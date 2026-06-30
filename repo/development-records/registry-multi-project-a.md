# REGISTRY-MULTI-PROJECT-A — 租户多 Registry 项目与 Harbor 映射

> 记录类型：Feature batch / Core Registry 产品语义对齐
> 完成日期：2026-06-30
> 范围：ANI Core `ImageRegistry` local + Harbor adapter；OpenAPI 描述补充；live gate 契约

## 背景

OpenAPI、`registry_projects` PG 表与 BOSS 文档均按 **一租户多项目、name 用户自定义** 建模，但 `M1-REGISTRY-A` / `SPRINT13-REGISTRY-HARBOR-A` 的 local/Harbor adapter 仍强制 `name == tenant_id`，与契约冲突，导致 Console 联调创建自定义项目名失败。

## 产品语义（本批次对齐）

| 维度 | 规则 |
|------|------|
| 作用域 | **租户级**多项目（`registry_projects.tenant_id`）；不含 `user_id`，不按用户隔离 |
| ANI 项目名 | 用户自定义，`CreateRegistryProjectRequest.name`，租户内唯一（PG `UNIQUE (tenant_id, name)`） |
| API 路径 `{project}` | 使用 **ANI 项目名**（用户可见名），不是 Harbor 内部 project 名 |
| 列表 | `GET /registry/projects` 返回该租户全部项目；有 PG 时以 `PersistingImageRegistry` 读 PG 为准 |
| 幂等 | `idempotency_key` 在租户内唯一；重试复用同一 key |

## Harbor provider 映射（共享 Harbor 实例）

ANI 不向 API 暴露 Harbor project 名。Harbor 侧使用确定性内部名，避免跨租户冲突：

```text
harbor_project = ani-{tenant_uuid_without_dashes}-{sanitized_ani_name}
```

示例：

- tenant `00000000-0000-0000-0000-000000000001`，ANI name `my-backend`
- Harbor project：`ani-000000000000000000000000000001-my-backend`
- 镜像引用（Harbor 侧）：`{registry_host}/ani-000000000000000000000000000001-my-backend/{repo}:{tag}`
- API 路径仍用：`/registry/projects/my-backend/repositories`

### ANI name 校验

- 非空，1–128 字符（与 OpenAPI 一致）
- 允许 `[a-zA-Z0-9][a-zA-Z0-9._-]*`（首字符字母数字）
- 禁止 `..`、首尾 `.`/`-`

### 兼容 Sprint13 live gate（legacy）

若 ANI `name` **等于** 完整 `tenant_id`（UUID 字符串），Harbor project 名仍使用 **裸 `tenant_id`**，与已通过的生产形态 live gate 历史行为一致。新联调应使用短名（如 `default`、`main`），不应再依赖 `name === tenant_id`。

### EnsureProject

`EnsureProject(tenantID)` 确保租户存在名为 **`default`** 的 ANI 项目（local 内存 / Harbor 按上述规则创建）。显式 `CreateProject` 可创建任意合法名称的额外项目。

## 实现要点

- `pkg/adapters/registry/registry_project_naming.go`：ANI 名校验、Harbor 名编解码
- `local_image_registry.go`：`projects` 按 `tenant_id + name` 多键存储；去掉 `name == tenant_id` 限制
- `harbor_image_registry.go`：创建/查询/仓库/制品/robot 均经 Harbor 名映射；响应 `RegistryProject.Name` 为 ANI 名
- `validateTenantProject` 改为 `validateRegistryProjectName`（格式校验）+ 子资源操作前由 provider 解析 Harbor 名（错误租户前缀无法访问他人项目）
- OpenAPI：`CreateRegistryProjectRequest` / `{project}` 参数补充描述（非破坏性）
- live gate：默认项目名改为 `default`，路径参数跟随 `project_name` 变量

## 边界

- 不改 PG schema；不新增 `user_id` 列
- 不声明 production ready；Harbor live gate 需人工复跑验证
- 不触碰 Services 冻结目录

## 验证

```bash
cd repo
go test ./pkg/adapters/registry/... -count=1
make validate-registry-harbor-live-gate
make validate-core-api-compatibility
make test
```
