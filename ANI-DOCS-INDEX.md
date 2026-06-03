# KuberCloud ANI · 文档导航与一致性矩阵

> 最后更新：2026-06-03
> 目的：让人类开发者和 AI 工具在 5 分钟内判断当前开发阶段、文档职责、下一步入口和闭环规则。

---

## 当前结论

```text
当前阶段：Phase 1 / Sprint 5 真实验证完成
当前不是 Phase 2：Phase 2 指 2026-10 以后延期能力
当前入口：repo/CURRENT-SPRINT.md
当前真实底座门禁：REAL-K8S-LAB-A / make validate-real-k8s-profile；Kube-OVN network resource 与 external LoadBalancer IP 可达性、KubeVirt VM lifecycle 与 console/VNC WebSocket session、vCluster Helm/kubeconfig/Core proxy、vCluster upgrade、Secret（含 VM guest Secret volume 可见性）、controller HA failover、KMS/SM4 provider streaming/objectstore round trip 与 node pool CAPK create/scale live evidence 已归档；GPU 调度依赖已在 ANI1/ANI2/ANI3 三台服务器跑通
```

Sprint 5 已完成 K8s、Kube-OVN、KubeVirt、vCluster、KMS/SM4、Kubernetes Secret 与 controller HA 的真实 provider 主链路验证，并已通过当前验收命令。local profile 只能证明 API、SDK、状态机和调用边界正确；真实运行能力必须由真实组件环境、固定验证命令或批次记录证明。

历史门禁仍保留：`SPEC-SPLIT-A`、`SPEC-CORE-BETA`、`SPEC-COMPAT-A`、`MOCK-A`、`DOC-API-A`、`SDK-BETA-A`、`SDK-BETA-B`、`SDK-BETA-C`、`SDK-BETA-D`、`SDK-MOCK-SMOKE-A`、`SDK-MOCK-SMOKE-B`、`SDK-MOCK-SMOKE-C`、`SDK-MOCK-SMOKE-D` 和 `SPRINT4-CLOSURE-A` 继续作为 Sprint 4 回归验收入口。

最近的 node pool real lab 结果是 `M1-K8S-LIVE-M`：在 `M1-K8S-LIVE-B` / `validate-k8s-node-pool-live-gate` 基础上，结合 `M1-K8S-LIVE-J` 真实 Cluster API `v1beta1` schema hardening、`M1-K8S-LIVE-L` CAPK bootstrap/infrastructure refs 配置能力和 `M1-K8S-LIVE-K` 三节点 GPU 调度依赖解除，真实执行 `validate_k8s_node_pool_live_gate.py --live` 并归档 `development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json`。证据显示 `gpu-pool-live` `MachineDeployment`、`MachineSet`、两个 worker `Machine`、两个 `KubevirtMachine`、两个 VM/VMI 均达到 2 副本 Ready/Available/Running 状态。该结果证明 CAPK provider-backed node pool create/update/scale-ready 链路，不代表 CAPK VM 内 GPU passthrough/vGPU 已完成；宿主三节点 GPU runtime/device-plugin/scheduler 可用性仍由 `M1-K8S-LIVE-K` 证明。

三台物理开发服务器已完成最小真实底座组件部署：Kubernetes `v1.36.1` 集群、Kube-OVN `v1.15.8` 和 KubeVirt `v1.8.2` 已在物理环境中达到组件 Ready/Deployed 状态；记录见 `repo/development-records/real-k8s-lab-k8s-kubeovn-kubevirt-bootstrap.md`。Kube-OVN network resource live gate 与 external LoadBalancer IP 可达性、KubeVirt VM lifecycle 与 console/VNC WebSocket session live gate、vCluster Helm/kubeconfig/Core proxy live gate、vCluster upgrade live gate、Secret live gate（含 VM guest Secret volume 可见性）、controller HA failover live gate、KMS/SM4 provider streaming/objectstore round trip live gate、GPU 调度依赖与 CAPK node pool create/scale live gate 已通过。

M1-NETWORK-LIVE-D 已在 `M1-NETWORK-LIVE-A` / validate-kubeovn-network-live-gate 基础上真实执行 `validate_kubeovn_network_live_gate.py --live --external-lb-live` 并归档 Kube-OVN Vpc/Subnet、NetworkPolicy、Service(LB 类型)、external LB helper EIP/DNAT/MASQUERADE 和三节点 HTTP 可达 evidence；此前 `M1-NETWORK-LIVE-C` 已将 Kube-OVN join subnet 从 Tailscale CGNAT 段迁移到 `172.30.0.0/16`，CNI 三节点 Ready。M1-KUBEVIRT-LIVE-D 已在 `M1-KUBEVIRT-LIVE-A` / validate-kubevirt-vm-live-gate 基础上增强并真实执行 `validate_kubevirt_vm_live_gate.py --live`，归档 KubeVirt VM lifecycle、console/VNC HTTP 101、`plain.kubevirt.io` 子协议和流数据字节 evidence，证明 console/VNC WebSocket session 已建立。M1-K8S-LIVE-G 已在 `M1-K8S-LIVE-A` / validate-vcluster-live-gate 基础上真实执行 `validate_vcluster_live_gate.py --live` 并归档 Helm install、vCluster kubeconfig 和 Core live proxy `/version` evidence；M1-K8S-LIVE-H 已在 `M1-K8S-LIVE-C` / validate-vcluster-upgrade-live-gate 基础上真实执行 `validate_vcluster_upgrade_live_gate.py --live` 并归档 Core provider-backed create、Helm `controlPlane.distro.k8s.version` upgrade values、升级后 vCluster `/version` 和 Core live proxy `/version` evidence；M1-K8S-LIVE-M 已真实执行增强后的 `validate_k8s_node_pool_live_gate.py --live` 并归档 Core node pool create/update、Cluster API MachineDeployment/MachineSet/Machine、CAPK KubevirtMachine 和 KubeVirt VM/VMI Ready evidence；M1-K8S-LIVE-K 已证明三台服务器 GPU runtime/device-plugin/scheduler 依赖可用；M1-SECRETS-LIVE-D 已在 `M1-SECRETS-LIVE-A` / validate-secrets-live-gate 基础上增强并真实执行 `validate_secrets_live_gate.py --live`，归档 Kubernetes Secret provider 写入、Pod env/file 可见、KubeVirt VM Secret volume manifest API 接受和 VM guest 内 Secret volume 可读 evidence，覆盖 env/file/VM 注入检查的当前可验证范围；M1-RECONCILE-LIVE-C 已在 `M1-RECONCILE-LIVE-A` / validate-reconcile-ha-live-gate 基础上真实执行 `validate_reconcile_ha_live_gate.py --live` 并归档 `control_plane_leases` holder 切换与 controller 多副本 HA failover evidence；M1-ENCRYPT-LIVE-C 已在 `M1-ENCRYPT-LIVE-A` / validate-kms-sm4-live-gate 基础上真实执行 `validate_kms_sm4_live_gate.py --live` 并归档 Core KMS provider、SM4-GCM streaming seal/open 与 objectstore sealed content round trip evidence。Core proxy 本次经本机 kubectl proxy 转发到 live vCluster，不代表生产 per-cluster metadata target/KMS token 管理已完成；Secret provider 本次经本机 kubectl proxy 访问 Kubernetes API，不代表生产 Kubernetes API credential 管理已完成；Controller HA 本次使用最小 live gate 依赖和 hostPath worker 二进制，不代表生产 Helm/Operator 化控制面部署已完成；KMS/SM4 本次使用 live-gate fixture，不代表生产 KMS/对象存储、直连 TLS/credential 管理或平台化部署完成；Kube-OVN external LB 本次使用 live-gate helper 镜像/脚本兼容方案，不代表生产镜像供应链或 Helm/Operator 化部署完成；CAPK node pool 本次证明 VM worker create/scale-ready，不代表 VM 内 GPU passthrough/vGPU 已完成。

---

## 唯一真实来源矩阵

| 问题 | 先看哪里 | 说明 |
|---|---|---|
| 当前做什么 | `repo/CURRENT-SPRINT.md` | 当前 Sprint 的执行入口，状态、任务、验收命令以它为准 |
| 全局开发节奏 | `ANI-06-开发计划.md` | Sprint 计划、Services 解锁门禁、延期项以它为准 |
| 产品功能边界 | `ANI-02-产品功能设计.md` | Core/Services 分层、v1.0.0 P0 能力边界以它为准 |
| 系统架构图和模块边界 | `ANI-05-系统架构设计.md` | Core/Services、API/SDK、ports/adapters、local profile/real provider 的结构图以它为准 |
| 路线图阶段 | `ANI-03-产品路线图.md` | Phase 1/2/3 与版本号关系以它为准 |
| 工程约定和 AI 工作规则 | `CLAUDE.md` | AI/人类开发前必须先读；只维护稳定规则和入口，不维护批次流水账 |
| API 契约 | `repo/api/openapi/v1.yaml` | Core OpenAPI REST API 与 Core/Services 跨层控制面契约的唯一真实来源 |
| Services API 契约 | `repo/api/openapi/services/v1.yaml` | Services 层业务 API 契约 |
| 已完成批次 | `repo/development-records/README.md` | 历史完成记录索引，不作为当前任务清单 |
| 单批次细节 | `repo/development-records/*.md` | 追溯实现、验证和关键文件时再读 |
| guard 微批次系列详情 | `repo/development-records/guard-series/{series}-guard-index.md` | guard 系列完整 ID 列表和批次链接；新 guard 微批次只更新此文件，不更新主文档 |

---

## 推荐阅读路径

### 人类开发者

1. `ANI-DOCS-INDEX.md`
2. `CLAUDE.md` 的 5 分钟快速上手
3. `repo/CURRENT-SPRINT.md`
4. `ANI-06-开发计划.md` Section 零和当前 Sprint
5. `ANI-05-系统架构设计.md`
6. `repo/api/openapi/v1.yaml` + `repo/api/openapi/services/v1.yaml` + 相关代码入口

### AI 编码工具

1. 必须先读 `CLAUDE.md`
2. 再读 `ANI-DOCS-INDEX.md`
3. 再读 `repo/CURRENT-SPRINT.md`
4. 开发前检查 `ANI-06-开发计划.md` Section 零
5. 涉及架构边界时检查 `ANI-05-系统架构设计.md`
6. 涉及接口时先改 `repo/api/openapi/v1.yaml` 或 `repo/api/openapi/services/v1.yaml`
7. 完成后按 `CLAUDE.md` 的进度更新规约闭环

---

## 当前开发门禁

| 日期 | 门禁 | 当前影响 |
|---|---|---|
| 2026-05-31 | P0 依赖矩阵冻结 | 已完成历史批次归档，后续只按当前 Sprint 补缺口 |
| 2026-06-10 | Core API Alpha Freeze | 已完成 instances 等核心路径冻结；新增能力必须保持兼容性 |
| 2026-06-20 | SDK Alpha | 四语言 Core/Services SDK 已可生成，并由 SDK Beta/Mock smoke 持续校验 |
| 2026-06-30 | Core Dev Profile Ready | Core dev/local profile 边界已建立；Sprint 5 继续补真实 provider |
| 2026-07-31 | Core Real Path Beta | Sprint 5 已通过：K8s/Kube-OVN/KubeVirt/vCluster/KMS-SM4/Secrets/HA 8 个真实 live gate 已归档 evidence；后续作为回归门禁保留 |
| 2026-09-30 | v1.0.0 Final Delivery | ANI Core v1.0.0 + ANI Services P0 |

---

## 文档维护规则

1. 当前阶段变更时，必须同步 `ANI-DOCS-INDEX.md`、`ANI-06-开发计划.md` 和 `repo/CURRENT-SPRINT.md`。
2. 批次完成时，必须新增或更新 `repo/development-records/{批次名}.md`，并更新 `repo/development-records/README.md`。
3. 历史归档文档允许保留当时日期和上下文，不反向改写为当前态。
4. 若 `CLAUDE.md` 与其它文档冲突，以 `CLAUDE.md` 的工程规则为准；若是进度状态冲突，以 `ANI-06-开发计划.md` Section 零和 `repo/CURRENT-SPRINT.md` 为准。
5. `CLAUDE.md` 只保留稳定强制规则、读取顺序、架构边界、提交门禁和 Karpathy 五条开发原则；禁止写入单批次完成清单、API path 长列表、文件级变更清单和每日开发流水账。
6. 动态进度只维护在 `repo/CURRENT-SPRINT.md`、`ANI-06-开发计划.md` Section 零和 `repo/development-records/*.md`；入口文档只保留当前状态、下一步和链接。
7. 更换 AI 模型或工具时，必须先重新读取本文件、`CLAUDE.md` 和 `repo/CURRENT-SPRINT.md`，不得依赖上一个会话的记忆。
8. 修改文档入口后必须运行 `make validate-doc-entrypoints`。
