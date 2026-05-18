# KuberCloud ANI · 系统架构设计

> 版本 V1.1 | 广州常青云科技有限公司 | 内部产品规划文件
> 最后更新：2026-05-19（对齐四语言 SDK 与文档真实来源）

> 当前 Core/Services 分层边界以 `ANI-02-产品功能设计.md` 和 `CLAUDE.md` 为准；当前开发阶段以 `ANI-06-开发计划.md` Section 零和 `repo/CURRENT-SPRINT.md` 为准。

---

## 一、架构核心原则

**目标：生产级平台，不是原型。**

生产级意味着：稳定性优先、横向可扩展、接口契约稳定、前后端完全解耦、任何一层可以独立演进而不影响其他层。

**五个核心约束：**

1. **API-First**：接口定义先于实现，所有能力通过同一套 API 契约对外暴露
2. **前后端物理解耦**：Web Server 层是唯一的出口，前端（Console/BOSS/APP）和调用方（SDK/CLI/第三方）全部通过它交互，后端服务不直接对前端暴露
3. **单一能力，多种消费形态**：同一个业务能力，通过 Web Server 层衍生出 REST API、SDK、CLI、运维 Skills，而不是为每种形态单独开发
4. **移动优先的接口设计**：API 设计从第一天就考虑移动端消费（分页、轻量响应体、Push 通知接口）
5. **开源组件松耦合**：除 Kubernetes API 外，MinIO、Milvus、NATS JetStream、Redis、Harbor、CloudNativePG 等均只能作为默认适配器实现，不能成为业务域模型、外部 API 或内部服务契约的不可替换边界。详细规则见 `ANI-13-开源组件松耦合适配器架构.md`。

---

## 二、整体分层架构

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 消费层（Consumers）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Console  │  │  BOSS    │  │ 移动 APP │  │  CLI     │  │  SDK     │
  │（浏览器） │  │（浏览器） │  │(iOS/And) │  │  (ani)   │  │Go/Py/TS/Java│
  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
       │              │              │              │              │
━━━━━━━┷━━━━━━━━━━━━━━┷━━━━━━━━━━━━━┷━━━━━━━━━━━━━┷━━━━━━━━━━━━━┷━━━━━━━━
 统一 Web Server 层（Go — Hertz / grpc-gateway）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ┌──────────────────────────────────────────────────────────────────────┐
  │  REST/JSON（API 契约：OpenAPI 3.1） · WebSocket/SSE（流式推理）     │
  │  gRPC-Gateway（内部协议转换）  ·  认证/限流/审计/路由                │
  │  API 契约 → SDK 自动生成  ·  CLI 自动生成  ·  运维 Skills 注册       │
  └──────────────────────────────────────────────────────────────────────┘
       │
━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 内部服务层（Go — gRPC）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ 模型管理  │  │ 知识库   │  │ 调度控制  │  │ 认证授权  │  │ 计费审计  │
  │ Service  │  │ Service  │  │ Service  │  │ Service  │  │ Service  │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
       │
━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ANI 能力接口层（Ports）与默认适配器层（Adapters）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ObjectStore · VectorStore · MessageBus · CacheStore · MetadataStore · ImageRegistry
  默认适配器：MinIO/S3 · Milvus · NATS JetStream · Redis · PostgreSQL · Harbor
       │
━━━━━━━┷━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 AI 推理层（Python）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  vLLM · Faster-Whisper · RAG Pipeline · 文档解析 · 微调服务
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Kubernetes 1.36 编排层  ·  KubeOVN 网络层  ·  HAMi GPU 调度
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 三、统一 Web Server 层（ANI Gateway）

这是整个架构最关键的一层，是所有外部消费者的唯一入口。

### 3.1 框架选型

**主框架：Hertz（CloudWeGo，字节跳动开源）**

| 对比维度 | Hertz | Gin | Echo |
|---|---|---|---|
| 性能 | 极高（基于 netpoll 异步 I/O） | 高 | 高 |
| 企业特性 | 内置服务发现、熔断、限流 | 需插件 | 需插件 |
| gRPC 支持 | 原生支持 | 需 grpc-gateway | 需 grpc-gateway |
| 国内社区 | 活跃（字节系维护） | 强 | 中 |
| 生产案例 | 字节内部日万亿级请求 | 大量开源项目 | 中量 |

**辅助：grpc-gateway**

内部服务间通信用 gRPC（Protobuf），grpc-gateway 在 Web Server 层将 REST/JSON 请求自动转译为 gRPC 调用，无需为同一接口写两套实现。

```
外部 REST 请求 → Hertz → grpc-gateway → 内部 gRPC Service
```

### 3.2 协议支持

| 协议 | 用途 | 实现方式 |
|---|---|---|
| HTTPS/REST | 标准 API 调用 | Hertz + OpenAPI 3.1 |
| WebSocket | 推理流式输出（浏览器） | Hertz WebSocket Handler |
| SSE（Server-Sent Events） | 推理流式输出（兼容性更好） | Hertz SSE |
| gRPC | 内部服务间通信 | 不对外暴露 |
| gRPC-Web | 未来浏览器直连 gRPC | 按需启用 |

**SSE vs WebSocket 选择：** 推理流式输出优先用 SSE（单向流，对 HTTP 代理和防火墙更友好，移动端兼容性更好），复杂双向交互用 WebSocket。

### 3.3 Web Server 层的横切关注点（Middleware 链）

```
请求进入
   │
   ▼
[1] TLS 终止 & 请求 ID 注入
   │
   ▼
[2] 认证（JWT 验证 / API Key 校验 / OAuth Token 解析）
   │
   ▼
[3] 授权（RBAC 策略检查，OPA 调用）
   │
   ▼
[4] 限流（令牌桶，按租户/用户/API 维度）
   │
   ▼
[5] 请求日志 & 审计打点（异步写入，不阻塞主流程）
   │
   ▼
[6] 路由分发 → 对应 gRPC Service
   │
   ▼
[7] 响应序列化 & 错误标准化
   │
   ▼
响应返回
```

### 3.4 API 设计规范（API 契约优先，OpenAPI 3.1）

**流程：先写 Spec，再生成代码，不允许代码先于 Spec。**

```
编写/更新 API 契约（OpenAPI 3.1 YAML）
        │
        ▼
    buf lint / oapi-validator 校验
        │
        ├──→ 生成 Go Server Stub（oapi-codegen）
        ├──→ 生成 Go SDK（oapi-codegen client 模式）
        ├──→ 生成 Python SDK（openapi-generator）
        ├──→ 生成 CLI 子命令骨架（自定义 generator）
        └──→ 生成 API 文档站（Redoc / Scalar）
```

**API 版本策略：**
- URL 路径版本：`/api/v1/models`、`/api/v2/models`
- 同时维护最多 2 个大版本，旧版本提前 6 个月公告废弃
- Breaking Change 必须升 major 版本，向后兼容变更在当前版本内处理

**错误响应规范（所有错误统一格式）：**
```json
{
  "code": "MODEL_NOT_FOUND",
  "message": "模型 qwen2.5-72b 不存在",
  "request_id": "req_01j8x...",
  "details": {}
}
```

---

## 四、能力消费形态

同一套业务能力，通过 Web Server 层统一暴露为以下四种形态：

### 4.1 REST API

自 API 契约提供，包含：
- 完整的 CRUD 接口（模型管理、知识库管理、任务管理等）
- OpenAI 兼容推理接口（`/v1/chat/completions`）——客户现有系统零改造接入
- Webhook 接口（任务完成、异常告警的主动推送）

### 4.2 官方 SDK

**Go SDK**
```go
client := ani.NewClient(ani.WithEndpoint("https://ani.internal"), ani.WithAPIKey("..."))
resp, err := client.Models.Deploy(ctx, &ani.DeployRequest{
    ModelName: "qwen2.5-72b",
    Replicas:  2,
    GPUType:   "A100",
})
```

**Python SDK**
```python
from ani_sdk import ANIClient
client = ANIClient(endpoint="https://ani.internal", api_key="...")
resp = client.knowledge.query("员工差旅报销标准是什么？", kb_id="kb_hr_001")
print(resp.answer, resp.sources)
```

Core SDK 目标为 Go / Python / TypeScript / Java 四种语言，均从 API 契约自动生成骨架，核心业务逻辑手工补充，版本随 API 版本同步发布。

### 4.3 CLI 工具（`ani`）

对标 `kubectl` 的设计思路，使用 **cobra + viper**（Go）开发：

```bash
# 模型管理
ani model list
ani model deploy qwen2.5-72b --replicas 2 --gpu-type A100
ani model logs qwen2.5-72b --follow

# 知识库管理
ani kb create --name "人事制度" --files ./docs/
ani kb query "差旅报销标准" --kb hr-policy

# 集群状态
ani cluster status
ani gpu status --node gpu-node-01

# 配置
ani config set endpoint https://ani.internal
ani config set api-key <your-key>
```

CLI 与 REST API 共享同一套 Go SDK，CLI 层只负责参数解析和输出格式化。

### 4.4 运维 Skills

运维 Skills 是面向平台运维人员的自动化操作单元，通过注册机制挂载到 Web Server 层，可被：
- 运维控制台（BOSS）直接触发
- 告警系统自动触发（变更驱动）
- ChatOps Bot（钉钉/企微）调用

**Skills 类型：**

| Skill 名 | 触发条件 | 执行动作 |
|---|---|---|
| `gpu.drain` | GPU 节点温度过高 | 驱逐该节点上的推理 Pod，等待降温后恢复 |
| `model.rollback` | 新版本错误率 > 阈值 | 推理流量切回上一个版本 |
| `kb.reindex` | 知识库文档更新 | 重新向量化并刷新检索索引 |
| `inference.scale` | QPS 超过水位线 | 自动扩容推理实例数 |
| `audit.export` | 定时 / 手动触发 | 导出审计日志到指定存储 |
| `tenant.quota` | 超配告警 | 限制超额租户的推理请求 |

Skills 框架：每个 Skill 是一个实现了标准接口的 Go struct，注册到 Skills Registry，Web Server 层统一暴露触发接口。

---

## 五、前端架构

### 5.1 两个独立前端应用

**Console（用户控制台）**
- 目标用户：企业 IT 管理员、业务部门用户
- 核心功能：模型部署与监控、知识库管理、AI 应用使用、用量报表
- 域名示例：`console.ani.yourcompany.com`

**BOSS（运营运维后台）**
- 目标用户：常青云内部运营、运维、客户成功团队
- 核心功能：多租户管理、资源配额分配、计费账单、平台健康看板、工单处理
- 域名示例：`boss.ani.internal`（内网访问，不对客户暴露）
- Phase 1 可以是简化版，随产品成熟逐步完善

### 5.2 前端技术栈

```
┌─────────────────────────────────────────────────────────┐
│  Console & BOSS（共享技术栈，独立部署）                   │
│                                                         │
│  React 18 + TypeScript                                  │
│  TanStack Router（类型安全路由）                         │
│  TanStack Query（服务端状态管理）                        │
│  Zustand（客户端状态，轻量）                             │
│  TDesign（腾讯开源，企业级组件库，中文友好）             │
│  ECharts / Recharts（图表）                             │
│  Vite（构建工具，热更新快）                              │
└─────────────────────────────────────────────────────────┘
```

**为什么选 TDesign 而不是 Ant Design：**
- TDesign 对 TypeScript 类型支持更完整
- 组件库更轻量，首屏加载性能更好
- 有 TDesign Mobile 版（React Native 版本），移动端复用更顺滑
- Console 和移动端可以共用同一套设计规范

**状态管理分层：**
- 服务端数据（API 响应）：TanStack Query 管理（缓存、重试、轮询）
- 客户端 UI 状态（弹窗、选中态）：Zustand
- URL 状态（筛选条件、分页）：TanStack Router

### 5.3 前后端接口规范

前端通过 API SDK（TypeScript 版，从 API 契约生成）访问后端，禁止前端直接拼接 URL 调用 API。

```typescript
// 从 API 契约自动生成的类型安全客户端
import { ANIClient } from '@kubercloud/ani-sdk'

const client = new ANIClient({ baseURL: '/api/v1' })

// 完全类型推导，编译期发现接口不匹配
const { data: models } = useQuery({
  queryKey: ['models'],
  queryFn: () => client.models.list({ page: 1, pageSize: 20 })
})
```

---

## 六、移动端策略

### 6.1 分阶段落地

**Phase 1–2（当前）：响应式 Web + PWA**
- Console 和 BOSS 前端采用响应式布局，在手机浏览器可用
- 配置 PWA Manifest，支持"添加到主屏幕"，获得近 App 体验
- 无需额外开发成本，API 设计保持移动端友好即可

**Phase 3：原生移动 App**
- 框架：**React Native**（而非 Flutter）
- 选 React Native 的理由：与 Web Console 共享业务逻辑、类型定义、API Client；TDesign 有 React Native 组件库
- iOS + Android 双端，优先 iOS（目标用户群（管理层）iPhone 比例高）

### 6.2 API 的移动端友好性设计（从第一天开始）

| 设计点 | 规范 |
|---|---|
| 分页 | 统一 cursor-based 分页（不用 offset），适合移动端无限滚动 |
| 响应体精简 | 支持 `fields` 参数按需返回字段，避免移动端流量浪费 |
| 推送通知 | 任务完成、告警事件通过 Webhook → 推送服务 → APP 通知 |
| 断点续传 | 大文件上传（模型、知识库文档）支持分片上传和断点续传 |
| 弱网容错 | API 响应包含 ETag，客户端可做条件请求减少流量 |

---

## 七、内部服务通信设计

### 7.1 服务间协议：gRPC + Protobuf

内部所有微服务之间通过 gRPC 通信，Protobuf 作为 Schema 的单一事实来源：

```
proto 文件（buf 管理）
      │
      ├──→ Go Server/Client 代码生成（protoc-gen-go + protoc-gen-go-grpc）
      ├──→ gRPC-Gateway 生成 REST 转发层
      └──→ Swagger/OpenAPI 文档生成
```

**buf 工具链：** 取代裸 `protoc`，统一 proto 依赖管理、lint 规则、breaking change 检测。

### 7.2 服务发现与负载均衡

- **Kubernetes 原生方式**：每个服务通过 K8s Service 暴露，内部 DNS 解析
- 不引入额外服务网格（Istio 等）直至 Phase 3，避免过度复杂化
- gRPC 客户端使用 `grpc.WithDefaultServiceConfig` 配置客户端负载均衡

### 7.3 异步任务队列

长时间任务（模型部署、微调、文档批量处理）不走同步 API，走异步队列：

- **消息队列：NATS JetStream**（轻量、Go 原生、适合 K8s 部署，比 Kafka 简单得多）
- 提交任务 → 返回 `task_id` → 客户端轮询或 Webhook 回调任务状态

```
POST /api/v1/models/deploy → 202 Accepted, { "task_id": "task_abc" }
GET  /api/v1/tasks/task_abc → { "status": "running", "progress": 45 }
     或 Webhook 回调 → { "event": "task.completed", "task_id": "task_abc" }
```

---

## 八、扩展性设计

### 8.1 水平扩展

- Web Server（ANI Gateway）：无状态，直接水平扩展，HPA 自动伸缩
- 内部 Go 微服务：无状态设计，K8s Deployment 水平扩展
- AI 推理服务（vLLM）：通过 K8s HPA 基于 GPU 利用率自动扩缩容
- 数据库：PostgreSQL 读写分离（CloudNativePG 管理），写主读从

### 8.2 多租户隔离

| 隔离维度 | 实现方式 |
|---|---|
| 数据隔离 | PostgreSQL Row-Level Security（RLS）+ 租户 ID 字段 |
| 网络隔离 | KubeOVN VPC，每个租户独立虚拟网络 |
| GPU 配额隔离 | HAMi + K8s ResourceQuota，按租户限制 GPU 使用量 |
| 模型隔离 | 推理服务按租户独立部署（性能敏感）或共享（资源节省） |
| 审计隔离 | 审计日志按租户 ID 分区存储，租户只能查看自己的日志 |

### 8.3 插件化扩展点

| 扩展点 | 说明 |
|---|---|
| 模型推理引擎 | 默认 vLLM，可注册其他引擎（Triton、自定义）实现相同接口 |
| 文档解析器 | 默认 Docling，可注册自定义解析器处理特殊格式（如金融报表） |
| 向量化模型 | 默认 BGE-M3，可替换为其他 Embedding 模型 |
| 运维 Skills | 通过 Skills Registry 动态注册，无需修改核心代码 |
| 认证提供商 | 默认 Dex（LDAP/SAML），可接入其他 OIDC Provider |

---

## 九、关键非功能指标（生产级基线）

| 指标 | 目标值 | 说明 |
|---|---|---|
| API 可用性 | 99.9%（月） | 允许每月约 43 分钟不可用 |
| API 响应延迟（P99） | < 200ms | 不含推理时间，纯网关开销 |
| 推理延迟首 Token（TTFT） | < 2s（7B 模型） | 取决于 GPU 型号和并发量 |
| 知识库查询延迟 | < 3s（端到端） | 含 Embedding + 向量检索 + LLM 生成 |
| 数据库连接池 | 每 Pod 最大 20 连接 | CloudNativePG + PgBouncer |
| 最大并发租户数 | 100（Phase 1 设计目标） | 单集群 |
| 审计日志保留 | 180 天 | 等保合规要求 |
