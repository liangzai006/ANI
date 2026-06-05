# ANI Core · Tailscale / Headscale Overlay Network 设计规划

> 文档状态：设计草案（待 live lab 验证后转为实现计划）
> 创建日期：2026-06-05
> 关联 Sprint：待定（预计 Sprint 12 或后续）
> 本文是独立设计文档，**不修改** ANI-06-开发计划.md、CLAUDE.md 或 CURRENT-SPRINT.md。
> 实现启动前必须先完成第七节的 live gate 验证。

---

## 一、背景与动机

### 当前问题

ANI Core 当前的集群纳管（K8s proxy、vCluster provider）和运维访问均依赖**直连 IP**，在以下真实场景中失效：

| 场景 | 问题 |
|---|---|
| 客户集群部署在 NAT 后（企业内网、私有 AZ） | Core 无法直达 APIServer，K8s proxy 失效 |
| 多地域 / 多 AZ 分布式部署 | 跨 AZ 直连可能被网络策略阻断 |
| 运维人员不在内网 | 需要 VPN / 堡垒机，运维效率低，配置繁琐 |
| 跨集群工作负载互访（Phase 2） | 无 overlay 网络，东西向流量无法跨集群路由 |

### Tailscale 已有现状

Tailscale 已在本项目中作为**开发工具**使用（Mac/Codex → 物理 lab 服务器），但尚未作为产品能力集成到 ANI Core。

**已知地址冲突**：Tailscale 默认 CGNAT 范围 `100.64.0.0/16` 与 Kube-OVN 原 join subnet 冲突，该冲突已通过将 Kube-OVN join subnet 迁移至 `172.30.0.0/16` 解决（见 `M1-NETWORK-LIVE-C`）。

### 选型决策汇总

| 维度 | 决策 | 理由 |
|---|---|---|
| 连通场景 | 控制平面 + 运维访问 + 工作负载数据平面（分阶段） | 全覆盖，分阶段实现 |
| 协调服务器 | **Headscale 自托管** | 私有云合规，数据不出内网，WireGuard 数据平面完全私有 |
| 管理责任 | **Phase 1**：API 对接（Headscale 为外部依赖）；**Phase 2**：ANI 全权管理生命周期 | 避免过早建设，先解决连通性 |
| API 暴露 | **分层**：核心连通透明 + 管理员运维 API | 不向普通租户暴露 overlay 语义 |
| 实现优先级 | **Phase 1**：控制平面纳管 + 运维访问同步推进；**Phase 2**：工作负载数据平面 | 共享同一 Headscale 基础设施 |
| Operator 策略 | 采用 **Tailscale Kubernetes Operator**（Helm）管理被管集群侧 | 消除手工节点注册，与 vCluster Helm provider 模式对齐 |

---

## 二、核心架构：双层设计

```
┌──────────────────────────────────────────────────────────────┐
│  ANI Core（管理平面 / 中心侧）                                │
│                                                              │
│  OverlayNetworkProvider Port                                 │
│  └── HeadscaleAdapter                                        │
│       ├── 查询 tailnet 节点状态（IP、在线/离线）              │
│       ├── 生成 auth key（用于新节点注册）                     │
│       ├── 管理 ACL 策略                                       │
│       └── 管理员运维 API 数据来源                             │
│                                                              │
│  K8sClusterProxyProvider（已有，扩展）                        │
│  └── 新增 Tailscale IP fallback：                            │
│       直连失败时自动尝试 tailnet IP                           │
└──────────────────────┬───────────────────────────────────────┘
                       │ onboarding 时 Helm 安装 Operator
                       │ 生成 auth key 注入 K8s Secret
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  每个被管 K8s / vCluster（被管集群侧）                        │
│                                                              │
│  Tailscale Kubernetes Operator（Helm 安装）                  │
│  ├── 自动向 Headscale 注册节点（使用 ANI 生成的 auth key）    │
│  ├── 暴露 APIServer Service 到 tailnet（annotation 驱动）     │
│  ├── Phase 2：Connector CRD 广播 Pod/Service CIDR            │
│  └── 自动管理 WireGuard 密钥交换                             │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Headscale Server（客户内网自托管）                           │
│  ├── tailnet 协调（节点注册、peer 列表分发）                  │
│  ├── WireGuard 公钥交换                                       │
│  ├── ACL 策略管理                                             │
│  └── DERP 中继（NAT 穿透兜底，部署在客户内网）               │
└──────────────────────────────────────────────────────────────┘
```

### 双层职责分工

| 职责 | 由谁承担 |
|---|---|
| 被管集群节点注册到 Headscale | Tailscale Operator（Helm 安装到被管集群） |
| ANI Core 自身注册到 Headscale | HeadscaleAdapter 直接调用 Headscale REST API |
| WireGuard 密钥协商 | Tailscale 客户端 / Operator（自动） |
| tailnet 节点状态查询 | HeadscaleAdapter → Headscale REST API |
| auth key 生成 | HeadscaleAdapter → Headscale REST API |
| ACL 策略下发 | HeadscaleAdapter → Headscale REST API |
| APIServer Service 暴露到 tailnet | Tailscale Operator annotation 驱动 |
| Phase 2 子网路由广播 | Tailscale Operator `Connector` CRD |
| Headscale 自身生命周期（Phase 1） | 外部管理员手动部署，ANI 不介入 |
| Headscale 自身生命周期（Phase 2 目标） | ANI Core 全权管理（演进目标） |

---

## 三、ANI Core ports/adapters 设计

### 3.1 新增 Port：`OverlayNetworkProvider`

**文件**：`pkg/ports/overlay_network.go`

```go
// OverlayNetworkProvider 表达 ANI 对 overlay 网络协调层的产品意图。
// 底层可由 Headscale 或未来其他实现承载。
// 遵循 ANI-13 开源组件松耦合适配器架构：ANI Core 不直接 import Headscale SDK，
// 只通过此 port 表达意图，由 HeadscaleAdapter 实现。
type OverlayNetworkProvider interface {
    // GenerateAuthKey 为新节点生成一次性注册 key。
    // reusable=false 时 key 只能注册一次（推荐）；
    // ephemeral=true 时节点离线后自动从 tailnet 移除。
    GenerateAuthKey(ctx context.Context, req AuthKeyRequest) (*AuthKey, error)

    // RevokeAuthKey 撤销未使用的注册 key。
    RevokeAuthKey(ctx context.Context, keyID string) error

    // GetNodeByName 按节点名查询 tailnet 节点状态。
    GetNodeByName(ctx context.Context, tailnet, nodeName string) (*OverlayNode, error)

    // ListNodes 列出 tailnet 内所有节点。
    ListNodes(ctx context.Context, tailnet string) ([]*OverlayNode, error)

    // GetNodeAddress 返回节点的 Tailscale IP（100.x.x.x），用于 proxy 目标解析。
    GetNodeAddress(ctx context.Context, tailnet, nodeName string) (string, error)

    // ApplyACLPolicy 更新 tailnet ACL 策略（HuJSON 格式）。
    ApplyACLPolicy(ctx context.Context, tailnet string, policy ACLPolicy) error

    // HealthCheck 验证 Headscale 可达性。
    HealthCheck(ctx context.Context) error
}

// AuthKeyRequest 注册 key 请求参数。
type AuthKeyRequest struct {
    Tailnet       string
    Reusable      bool     // 通常 false，一次性 key 更安全
    Ephemeral     bool     // true = 节点离线后自动从 tailnet 移除
    Tags          []string
    ExpirySeconds int
}

// AuthKey 生成结果。key 明文只返回一次，不持久化到 ANI DB。
type AuthKey struct {
    ID        string
    Key       string
    ExpiresAt time.Time
    Reusable  bool
    Ephemeral bool
}

// OverlayNode tailnet 节点信息。
type OverlayNode struct {
    ID            string
    Name          string
    TailscaleIP   string    // 100.x.x.x
    TailscaleIPv6 string    // fd7a:...（可选）
    Online        bool
    LastSeen      time.Time
    Tags          []string
    Routes        []string  // 广播的子网路由（Phase 2 使用）
}

// ACLPolicy tailnet ACL（HuJSON 格式原文）。
type ACLPolicy struct {
    Raw string
}
```

### 3.2 新增 Adapter：`HeadscaleAdapter`

**文件**：`pkg/adapters/overlay/headscale_adapter.go`

```go
// HeadscaleAdapter 通过 Headscale REST API 实现 OverlayNetworkProvider。
// Phase 1：只做 API 对接，不管理 Headscale 自身生命周期。
// ANI Core 不 import Headscale Go 包，只使用 HTTP REST 调用。
type HeadscaleAdapter struct {
    baseURL    string        // 从 HEADSCALE_URL 环境变量读取
    apiKey     string        // 从 HEADSCALE_API_KEY 环境变量读取（K8s Secret 注入）
    httpClient *http.Client
}
```

**配置来源**（遵循现有约定）：

```
HEADSCALE_URL      Headscale server 地址，例：http://headscale.internal:8080
HEADSCALE_API_KEY  Headscale admin API key，由 K8s Secret 注入，禁止硬编码
```

### 3.3 扩展现有 K8s Proxy：Tailscale IP Fallback

在现有 `ports.K8sClusterService` 的 proxy 目标解析逻辑中新增 fallback：

```
proxy 目标地址解析优先级：
  1. 直连 IP（现有逻辑，metadata store 中存储的 APIServer 地址）
  2. Tailscale IP fallback（新增，OVERLAY_ENABLED=true 时）：
     - 集群注册时若提供了 tailnet_node_name 字段
     - 则从 OverlayNetworkProvider.GetNodeAddress 查询 tailnet IP
     - 直连超时/拒绝时自动切换
```

**新增环境变量**：

```
K8S_CLUSTER_PROXY_OVERLAY_PROVIDER=headscale   # 默认 disabled
```

---

## 四、Core API 新增：管理员运维接口

**适用范围**：仅管理员（`admin` RBAC scope），不对普通租户暴露。
**路径前缀**：`/api/v1/overlay`（Core API）。
**设计原则**：只读查询 + 必要运维操作（auth key），不暴露完整 tailnet CRUD。

```
GET    /api/v1/overlay/nodes
       列出 tailnet 所有节点状态（在线/离线、IP、最近握手时间），分页

GET    /api/v1/overlay/nodes/{node_name}
       查询单节点详细状态（含路由广播情况，Phase 2 后可见）

POST   /api/v1/overlay/auth-keys
       为新节点/集群生成注册 key
       body:   { tailnet, reusable, ephemeral, expiry_seconds, tags }
       返回:   { key_id, key, expires_at }   ← key 明文只返回一次

DELETE /api/v1/overlay/auth-keys/{key_id}
       撤销未使用的注册 key

GET    /api/v1/overlay/health
       检查 Headscale 连通性，供运维快速诊断
```

**明确不新增**：tailnet CRUD、ACL 规则 CRUD、路由配置——这些属于 Headscale 管理员直接操作范围。

---

## 五、与现有功能的集成点

### 5.1 集群 Onboarding 流程扩展

`OVERLAY_ENABLED=true` 时，在现有 vCluster onboarding（`M1-K8S-C/D`）之后追加：

```
现有步骤（不变）：
  1. vCluster Helm install
  2. kubeconfig 获取
  3. proxy target 注册

新增 overlay onboarding 步骤（可选）：
  4. HeadscaleAdapter.GenerateAuthKey()  →  获取一次性 auth key
  5. 将 auth key 写入被管集群 K8s Secret（名称：tailscale-operator-auth）
  6. Helm install Tailscale Operator（复用 vCluster Helm provider 模式）
     chart:  tailscale/tailscale-operator
     values:
       authkey:    <from Secret>
       headscale:
         url:      <HEADSCALE_URL>
  7. 轮询 OverlayNetworkProvider.GetNodeByName 等待注册完成
  8. 更新 proxy target metadata：追加 tailscale_node_name 字段
```

### 5.2 SSH Trust Installer 扩展

现有 `repo/scripts/ani_ssh_trust_installer.py` 已有 `tailscale_ip` 字段，扩展：

- 新增 `--register-headscale` flag：调用 HeadscaleAdapter 生成 auth key 并写入节点配置
- 注册完成后自动从 Headscale API 回填 `tailscale_ip`，无需手动填写

### 5.3 Installer Profile 扩展

在 `CORE-INSTALLER-A`（`deploy/real-k8s-lab/`）的 installer profile 中新增 Headscale 可选组件：

```yaml
optional_components:
  - name: headscale
    type: self-hosted-tailscale-coordinator
    helm_chart: headscale/headscale
    enabled_when: "OVERLAY_NETWORK_ENABLED=true"
    notes: >
      Phase 1 要求外部管理员部署 Headscale；
      Phase 2 目标由 ANI Core 管理生命周期。
  - name: tailscale-derp
    type: relay-server
    notes: >
      部署在客户内网替代公共 Tailscale DERP，确保数据不出内网。
      推荐使用 Headscale 内置 DERP（v0.23+），减少额外组件。
```

---

## 六、地址规划与已知约束

### 6.1 CGNAT 地址范围与冲突规避

| 网络 | 地址段 | 状态 |
|---|---|---|
| Tailscale / Headscale tailnet | `100.64.0.0/10`（RFC 6598 CGNAT） | 固定，不可更改 |
| Kube-OVN join subnet | `172.30.0.0/16` | ✅ 无冲突，已在 M1-NETWORK-LIVE-C 完成迁移 |
| Kubernetes Pod CIDR（默认） | `10.244.0.0/16` 或 `192.168.0.0/16` | 部署时须确认不与 `100.64.0.0/10` 重叠 |

**强制约束**：

1. Kube-OVN join subnet **必须**保持在 `172.30.0.0/16`，禁止回退到 `100.64.0.0/16`
2. 新 K8s 集群 onboarding 时，Pod/Service CIDR **必须**检查与 `100.64.0.0/10` 无重叠
3. Headscale server 本机地址使用客户内网 IP，**禁止**使用 `100.64.x.x` 段

### 6.2 DERP 中继

私有云环境不可使用公有 Tailscale DERP 服务器（无公网访问）：

| 选项 | 说明 | 推荐 |
|---|---|---|
| Headscale 内置 DERP | v0.23+ 内置支持，配置简单 | ✅ 推荐（减少组件） |
| 独立 Tailscale DERP 服务 | 开源 MIT，部署在客户内网 | 备选（高可用场景） |

---

## 七、Live Gate 验证要求（实现前必须通过）

在进入代码实现阶段前，必须在三台物理服务器上验证以下 gate，归档 evidence JSON。

### Gate 1：Headscale + Tailscale Operator 基础兼容性

```
目标：Tailscale Operator 能以 Headscale 作为 backend 正常注册节点并建立 WireGuard 隧道

步骤：
  1. 在一台服务器部署 Headscale（Docker 或 systemd）
  2. 在现有 K8s 集群安装 tailscale-operator Helm chart，backend 指向 Headscale
  3. 验证节点自动出现在 headscale nodes list
  4. 验证 tailscale status 显示 peer 列表正常
  5. tailnet 节点间互 ping

成功标准：节点注册成功，WireGuard 隧道建立，peer 间 ping 通
```

### Gate 2：APIServer Service 暴露到 tailnet

```
目标：Operator annotation 将 K8s APIServer 暴露到 tailnet，ANI Core 可通过 tailnet IP 访问

步骤：
  1. 给 kubernetes Service 打 annotation: tailscale.com/expose=true
  2. 验证 Operator 创建对应 Tailscale device，分配 100.x.x.x IP
  3. 从 tailnet 另一节点（Mac）访问该 Tailscale IP 的 6443 端口

成功标准：kubectl --server=https://<tailscale-ip>:6443 正常执行
```

### Gate 3：HeadscaleAdapter Go API 对接

```
目标：Go HTTP client 可正常调用 Headscale REST API

步骤：
  1. 生成 Headscale API key
  2. Go HTTP client 调用 GET /api/v1/node 列出节点，解析响应
  3. Go HTTP client 调用 POST /api/v1/preauthkey 生成 auth key，解析响应

成功标准：Go 代码可正常调用 Headscale API，字段映射到 OverlayNode / AuthKey 结构体
```

### Gate 4（Phase 2 前置）：Connector 子网路由

```
目标：Connector CRD 在 Headscale 环境广播 Pod CIDR

步骤：
  1. 创建 Connector CR，advertiseRoutes 包含 Pod CIDR
  2. 在 Headscale 中批准路由广播
  3. 从 tailnet 另一节点访问 Pod IP

成功标准：跨 tailnet 节点可访问 Pod IP
风险：Connector 在 Headscale 的兼容性未经验证，此 gate 可能 blocking Phase 2 设计
```

---

## 八、开源组件准入评估（ANI-13 规范）

| 评估项 | Headscale | Tailscale Operator |
|---|---|---|
| GitHub Stars | ~25k ✅ | 随 tailscale/tailscale 主仓库 |
| License | BSD 3-Clause ✅ | BSD 3-Clause ✅ |
| 最新稳定版 | v0.24.x，活跃维护 ✅ | v1.x，随 Tailscale 主版本 ✅ |
| 源码可读性 | Go，清晰 ✅ | Go，清晰 ✅ |
| 离线部署能力 | ✅ 完全支持，无公网依赖 | ✅ Helm chart 可离线 |
| 可替换退出路径 | Netbird / Nebula / 商业 Tailscale | 手动 tailscale daemon 管理 |
| 生产运维能力 | 社区活跃，有 Prometheus metrics | Kubernetes 原生，kubectl 可观测 |
| ANI 依赖方式 | `bounded_direct`（HeadscaleAdapter HTTP 封装）| 部署依赖（Helm chart，不 import SDK）|

**关键约束**：ANI Core Go 代码**禁止 import Headscale SDK**，只通过 HTTP REST API 对接。Tailscale Operator 只作为 Helm 部署产物引入，不作为 Go 代码依赖。

---

## 九、实现检查清单（Sprint 启动时展开为批次）

> 本节为未来 Sprint 参考，不是当前执行清单。
> 实际批次 ID、验收命令、文档更新在 Sprint 启动时按 CLAUDE.md 规约分配。
> **前置条件**：第七节 Gate 1-3 全部通过并归档 evidence。

### Phase 1a：HeadscaleAdapter + 管理员 API

- [ ] `pkg/ports/overlay_network.go`：定义 `OverlayNetworkProvider` port 与数据类型
- [ ] `pkg/adapters/overlay/headscale_adapter.go`：实现 HeadscaleAdapter（HTTP only）
- [ ] `pkg/adapters/overlay/headscale_adapter_test.go`：单元测试（mock Headscale HTTP）
- [ ] `repo/api/openapi/v1.yaml`：新增 `/overlay/*` 路径（先改契约再写实现）
- [ ] Gateway：overlay handler 绑定，RBAC scope `admin`
- [ ] CLI 扩展：`ani overlay nodes`、`ani overlay auth-key generate`
- [ ] 环境变量文档：`HEADSCALE_URL`、`HEADSCALE_API_KEY`、`OVERLAY_NETWORK_ENABLED`

### Phase 1b：K8s Proxy Tailscale Fallback

- [ ] `ports.K8sClusterService` proxy target metadata 增加 `tailscale_node_name` 字段
- [ ] K8s proxy forwarding adapter：Tailscale IP fallback 逻辑
- [ ] `K8S_CLUSTER_PROXY_OVERLAY_PROVIDER` 环境变量接线
- [ ] 集群 onboarding 文档：说明如何注册 tailnet_node_name

### Phase 1c：Tailscale Operator Helm 集成（Onboarding 自动化）

- [ ] vCluster onboarding 流程新增可选 Operator 安装步骤
- [ ] auth key 生成 → K8s Secret 注入 → Operator Helm install 链路
- [ ] `OVERLAY_ENABLED` 开关（默认 disabled，不影响无 overlay 部署）
- [ ] 注册完成轮询验证（OverlayNetworkProvider.GetNodeByName）

### Phase 1d：SSH Trust Installer 扩展

- [ ] `ani_ssh_trust_installer.py` 新增 `--register-headscale` 模式
- [ ] 自动从 Headscale API 回填 `tailscale_ip`

### Phase 1e：文档与 Live Gate

- [ ] Gate 1-3 全部通过，归档 evidence JSON
- [ ] `make validate-overlay-network-live-gate` 新增验收目标
- [ ] ANI-06 和 CURRENT-SPRINT.md 在 Sprint 启动时同步更新

### Phase 2：工作负载数据平面（独立 Sprint，依赖 Gate 4）

- [ ] Gate 4（Connector 子网路由）通过
- [ ] Connector CRD 管理：ANI Core 可创建/删除 `Connector` CR
- [ ] 路由审批 API：管理员通过 Core API 批准子网路由广播
- [ ] 多集群 DNS 方案（Headscale MagicDNS + K8s CoreDNS 集成，需调研）
- [ ] Headscale 生命周期管理（Phase 2 最终目标：ANI Core 全权管理）

---

## 十、参考资料

- Headscale 官方文档：https://headscale.net/
- Headscale GitHub：https://github.com/juanfont/headscale
- Headscale REST API：https://headscale.net/api/
- Tailscale Kubernetes Operator 文档：https://tailscale.com/kb/1236/kubernetes-operator
- Tailscale Operator 源码：https://github.com/tailscale/tailscale（`cmd/k8s-operator/`）
- WireGuard 协议：https://www.wireguard.com/
- RFC 6598（CGNAT `100.64.0.0/10`）：https://datatracker.ietf.org/doc/html/rfc6598

相关历史批次（本项目内）：

| 批次 | 关联说明 |
|---|---|
| `M1-NETWORK-LIVE-C` | Kube-OVN join subnet 与 Tailscale CGNAT 冲突修复，join subnet 已迁至 `172.30.0.0/16` |
| `M1-K8S-LIVE-G/H` | vCluster Helm provider 实现，Operator Helm 集成的参考模式 |
| `CORE-INSTALLER-A` | installer profile 扩展基础（添加 Headscale 可选组件） |
| `repo/scripts/ani_ssh_trust_installer.py` | 已有 `tailscale_ip` 字段，Phase 1d 扩展基础 |
