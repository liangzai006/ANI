# ANI · 当前冲刺上手指南

> 新开发者（人类或 AI 工具）的第一个入口文件。本文只描述当前真实执行状态；历史完成批次查 `repo/development-records/README.md`。

> 历史门禁保留：Sprint 4 的 `SPEC-SPLIT-A`、`SPEC-CORE-BETA`、`SPEC-COMPAT-A`、`SDK-BETA-A`、`SDK-BETA-B`、`SDK-BETA-C`、`SDK-BETA-D`、`SDK-MOCK-SMOKE-A`、`SDK-MOCK-SMOKE-B`、`SDK-MOCK-SMOKE-C`、`SDK-MOCK-SMOKE-D`、`MOCK-A`、`DOC-API-A`、`SPRINT4-CLOSURE-A` 和 `validate-sprint4-closure` 仍是提交前回归门禁，不作为当前任务清单。

> **仓库范围：仅 ANI Core。** ANI Services 已冻结并移交外部产品团队，本仓库不再开发任何 Services 代码（旧 Services 骨架只读保留）。外部团队预计 2026-06-10 前后给出清晰的产品功能/交互/API 定义，Core 据此以 AI Coding 快速循环实现支撑。
> **当前重心：Sprint 5 真实 live gate 已完成并通过验收命令（物理服务器 2026-05-29 到位）+ guard 冻结。** 证据清单见下方"真实 live gate 结果"。

## 当前冲刺

| 字段 | 值 |
|---|---|
| **冲刺编号** | Sprint 5（真实验证完成） |
| **主题** | K8s 集群管理 + 加解密主链路 + **真实底座 live gate 推进**（契约/local 已完成，转入真实验证） |
| **当前状态** | ✅ local profile 主链路、K8s proxy forwarding adapter/target resolver/metadata 持久化/Gateway 注入接线与 forwarding_static/forwarding_metadata runtime 选择、vCluster Helm/kubeconfig/upgrade provider 代码边界、K8s node pool local profile 与 Cluster API/CAPK provider 代码边界、Kube-OVN/KubeVirt/controller HA/KMS-SM4/Secrets live contract gates 与 evidence JSON 输出、REAL-K8S-LAB-A component live runner/report/preflight/evidence guard 系列已收敛到 `M1-REAL-LAB-KX` KMS/SM4 live gate command type guard；三台物理开发服务器已完成 Kubernetes `v1.36.1` + Kube-OVN `v1.15.8` + KubeVirt `v1.8.2` 最小组件部署；Kube-OVN network resource live gate 与 external LoadBalancer IP 可达性、KubeVirt VM lifecycle 与 console/VNC WebSocket session live gate、vCluster Helm/kubeconfig/Core proxy live gate、vCluster upgrade live gate、Secret live gate（含 VM guest Secret volume 可见性）、controller HA failover live gate、KMS/SM4 provider streaming/objectstore round trip live gate、GPU runtime/device-plugin/scheduler 依赖与 CAPK node pool create/scale live gate 已在真实 lab 跑通并归档 evidence；验收命令、`make test`、`make validate-architecture` 和 `git diff --check` 已通过 |
| **已由代码/真实环境证明完成** | `M1-K8S-A/B/C/D/E/F/G`、`M1-K8S-PROXY-A/B/C/D/E/F`、`M1-K8S-LIVE-A/B/C/D/E/F/G/H/J/K/L/M`、`M1-NETWORK-LIVE-A/B/C/D`、`M1-KUBEVIRT-LIVE-A/B/C/D`、`M1-ENCRYPT-A/B/C/D`、`M1-ENCRYPT-LIVE-A/B/C`、`M1-SECRETS-A/B/C/D`、`M1-SECRETS-LIVE-A/B/C/D`、`M1-RECONCILE-A/B/C/D/E`、`M1-RECONCILE-LIVE-A/B/C`、`REAL-K8S-LAB-A`、`M1-REAL-LAB-B` 至 `M1-REAL-LAB-KX` 的验证器、文档记录和测试闭环、`REAL-K8S-LAB physical base environment` 最小物理基础环境记录、`REAL-K8S-LAB K8s/Kube-OVN/KubeVirt bootstrap` 真实底座组件部署记录；完整批次索引见 `repo/development-records/README.md` |
| **生产化边界** | CAPK node pool 本次证明 VM worker create/scale-ready，不代表 CAPK VM 内 GPU passthrough/vGPU 已完成；vCluster Core proxy 本次经本机 kubectl proxy 转发，不代表生产 per-cluster metadata target/KMS token 管理已完成；vCluster upgrade 本次目标版本为当前 chart 默认的 `v1.35.0`，不宣称跨小版本真实升级策略已生产化；Secret provider 本次经本机 kubectl proxy 访问 Kubernetes API，不代表生产 Kubernetes API CA/client credential 管理已完成；Controller HA 本次使用 REAL-K8S-LAB-A 最小 live gate 依赖和 hostPath worker 二进制，不代表生产 Helm/Operator 化控制面部署已完成；KMS/SM4 本次使用 REAL-K8S-LAB-A live-gate fixture，不代表生产 KMS/对象存储、直连 TLS/credential 管理或平台化 Helm/Operator 部署完成；Kube-OVN external LoadBalancer 本次使用 live-gate helper 镜像/脚本兼容方案，不代表生产镜像供应链或 Helm/Operator 化部署完成 |
| **关联历史门禁** | Sprint 4 `SPEC-CORE-BETA` / `api/core-beta-readiness.yaml`、`DOC-API-A` 仍需保持 API docs 与 OpenAPI 同步；`SDK-BETA-A`、`SDK-BETA-B`、`SDK-BETA-C`、`SDK-BETA-D` 仍需保持 SDK helper 与新增 Core API 同步 |
| **最后校准日期** | 2026-06-03 |

## 已完成切片

本节保留当前 Sprint 的可执行事实，完整历史清单以 `repo/development-records/README.md` 为唯一归档索引。

1. `M1-K8S-A/B/C/D/E/F/G`：K8s 集群 CRUD/kubeconfig/proxy local profile、vCluster Helm provider、vCluster kubeconfig provider、cluster upgrade provider、node pool local profile 和 Cluster API node pool provider 代码边界已完成；该切片当时不代表真实 vCluster 或节点池 live 验证完成；后续已由 M1-K8S-LIVE-G（vCluster）、M1-K8S-LIVE-H（upgrade）、M1-K8S-LIVE-M（node pool/CAPK）补齐。
2. `M1-K8S-PROXY-A/B/C/D/E/F`：proxy forwarding adapter、target resolver/store、metadata 持久化、Gateway 注入接线和 `forwarding_static` / `forwarding_metadata` runtime 选择已完成；该切片当时不代表 live proxy 验证完成；后续已由 M1-K8S-LIVE-G（Core live proxy `/version` 转发）补齐。
3. `M1-K8S-LIVE-A/B/C/D/E/F/G/H/J/K/L/M`：vCluster、`M1-K8S-LIVE-B` node pool（含 Cluster API/CAPK 和 GPU 调度检查）、`M1-K8S-LIVE-C` vCluster upgrade（含 Helm `controlPlane.distro.k8s.version` 检查）live contract gates 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行 `validate_vcluster_live_gate.py --live` 并归档 `development-records/live-evidence/vcluster-live-gate-2026-06-02.json`，证明 Helm install、vCluster kubeconfig 可用性和 Core live proxy `/version` 转发通过；同日已执行 `validate_vcluster_upgrade_live_gate.py --live` 并归档 `development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json`，证明 Core provider-backed create、Helm upgrade values、升级后 vCluster `/version` 和 Core live proxy `/version` 通过；`M1-K8S-LIVE-J` 已把 node pool provider manifest harden 为真实 Cluster API `v1beta1` schema 合法结构；`M1-K8S-LIVE-K` 已证明 GPU runtime/device-plugin/scheduler 可用；`M1-K8S-LIVE-L` 已支持通过 Gateway env 配置 CAPK bootstrap/infrastructure refs；2026-06-03 已执行增强后的 `validate_k8s_node_pool_live_gate.py --live` 并归档 `development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json`，证明 Core create/update 后 CAPK `MachineDeployment`、`MachineSet`、worker `Machine`、`KubevirtMachine`、VM/VMI 均达到 2 副本 Ready/Available/Running。
4. `M1-NETWORK-LIVE-A/B/C/D`：`M1-NETWORK-LIVE-A` Kube-OVN `Vpc/Subnet`、NetworkPolicy、Service/LB live contract gate 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行增强后的 `validate_kubeovn_network_live_gate.py --live --external-lb-live` 并归档 `development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json`。本次同步修复了 live runner 未创建租户 namespace 的缺口、Kube-OVN join subnet 与 Tailscale CGNAT 地址段冲突，并补齐 Multus/macvlan underlay、external LB helper EIP/DNAT/MASQUERADE 与三节点 HTTP 可达性证明。
5. `M1-KUBEVIRT-LIVE-A/B/C/D`：KubeVirt VM lifecycle、console/VNC live contract gate 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行增强后的 `validate_kubevirt_vm_live_gate.py --live` 并归档 `development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json`。当前证明 VM create/start/observe/stop/delete 生命周期可运行，console/VNC subresource 可达，并且 console/VNC WebSocket session 均以 KubeVirt `plain.kubevirt.io` 子协议完成 HTTP 101 upgrade 与流式读写。
6. `M1-ENCRYPT-A/B/C/D` 与 `M1-ENCRYPT-LIVE-A/B/C`：Encryption local profile、KMS/SM4 HTTP provider 代码边界、对象内容 SM4-GCM 流式加解密边界、KMS/SM4 live gate 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行 `validate_kms_sm4_live_gate.py --live` 并归档 `development-records/live-evidence/kms-sm4-live-gate-2026-06-02.json`，证明 Core KMS provider、SM4-GCM streaming seal/open 和 objectstore sealed content round trip 通过。本次使用 live-gate fixture，不宣称生产 KMS/对象存储部署形态已完成。
7. `M1-SECRETS-A/B/C/D` 与 `M1-SECRETS-LIVE-A/B/C/D`：Secret local profile、Kubernetes Secret provider 写入代码边界、容器/Job env/file 注入、VM Secret volume 注入、Secrets live gate 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行增强后的 `validate_secrets_live_gate.py --live` 并归档 `development-records/live-evidence/secrets-live-gate-2026-06-02.json`，证明 Kubernetes Secret provider 写入、Pod env/file 可见、KubeVirt VM Secret volume manifest API 接受以及 VM guest 内 Secret volume 可读，覆盖 env/file/VM 注入检查的当前可验证范围。
8. `M1-RECONCILE-A/B/C/D/E` 与 `M1-RECONCILE-LIVE-A/B/C`：controller adapter、opt-in bootstrap、目标级失败退避、Prometheus metrics、独立 worker、metadata-backed leader election、controller HA live gate 与 evidence JSON 输出已完成；2026-06-02 已在 REAL-K8S-LAB-A 真实执行 `validate_reconcile_ha_live_gate.py --live` 并归档 `development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json`，证明两副本 worker、`control_plane_leases` active holder、metrics、删除 leader Pod 与 follower 接管通过。本次使用最小 live gate 依赖和 hostPath worker 二进制，不宣称生产控制面部署形态已完成。
9. `REAL-K8S-LAB-A` 真实底座验证门禁 + `M1-REAL-LAB guard series`（B~KX，299 个 guard validators）：REAL-K8S-LAB-A 组件级 contract gate、`--live` evidence JSON、component live runner、preflight/env/report/evidence/provenance/diagnostic guards，以及 kubeconfig/vCluster/vCluster upgrade/node pool/Kube-OVN/KubeVirt/controller HA/KMS-SM4 live gate 前置校验系列已完成；完整 guard 列表见 [`repo/development-records/guard-series/REAL-K8S-LAB-guard-index.md`](development-records/guard-series/REAL-K8S-LAB-guard-index.md)；最新完成 ID：`M1-REAL-LAB-KX`（KMS/SM4 live gate command type guard）；该切片当时的 guard 系列不代表组件级 `--live` 已在真实 lab 执行成功；后续 8 个真实 live gate 均已在 REAL-K8S-LAB-A 跑通并归档 evidence（见下方"真实 live gate 结果"）。
10. `REAL-K8S-LAB physical base environment`：三台物理开发服务器已完成最小基础软件环境，包含 `containerd`、Kubernetes v1.36 bootstrap 工具、CRI 工具、Kubernetes 所需 OS 包、国内 APT 源和常见境外容器镜像仓库的国内 mirror hosts；未执行 `kubeadm init/join`，未安装 Helm、vCluster、Kube-OVN、KubeVirt、KMS/SM4 backend 或其它上层组件；记录见 `repo/development-records/real-k8s-lab-physical-base-environment.md`。
11. `REAL-K8S-LAB K8s/Kube-OVN/KubeVirt bootstrap`：三台物理开发服务器已完成 Kubernetes `v1.36.1` 集群、Kube-OVN `v1.15.8` 和 KubeVirt `v1.8.2` 最小部署；Kube-OVN CNI/CoreDNS Ready，KubeVirt phase `Deployed`；记录见 `repo/development-records/real-k8s-lab-k8s-kubeovn-kubevirt-bootstrap.md`。Kube-OVN network resource live gate 的真实结果见 `repo/development-records/m1-network-live-c-kubeovn-real-lab-result.md`；KubeVirt VM lifecycle live gate 的真实结果见 `repo/development-records/m1-kubevirt-live-c-vm-real-lab-result.md`。

## 当前事实边界

- K8s 集群当前默认仍是 local profile 模拟服务；runtime 层已有 vCluster Helm/kubeconfig/upgrade provider、node pool provider 和 proxy forwarding 代码边界，且 vCluster live Helm 安装、kubeconfig 可用性、upgrade values、升级后 `/version` 与 Core proxy `/version` 已在 REAL-K8S-LAB-A 通过；node pool provider manifest 已按真实 Cluster API `v1beta1` schema 修正为合法 `bootstrap` / `infrastructureRef` 结构，GPU/规格 intent 通过 metadata 保留，并已支持通过 Gateway env 配置 CAPK `KubeadmConfigTemplate` / `KubevirtMachineTemplate` refs；GPU runtime/device-plugin/scheduler 已在 REAL-K8S-LAB-A 通过，ANI1/ANI2/ANI3 三台服务器均暴露 `nvidia.com/gpu: 2`，通用 GPU smoke Pod 与 ANI1 control-plane 专属 GPU smoke Pod 均已成功运行 `nvidia-smi`；CAPK node pool provider-backed create/update/scale-ready 已在 REAL-K8S-LAB-A 通过，证据见 `development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json`。CAPK worker 是 KubeVirt VM 内的 Kubernetes 节点，本次不宣称 VM 内 GPU passthrough/vGPU 已完成。
- Kubeconfig 默认仍指向模拟 vCluster endpoint；`vcluster_helm` provider mode 已具备通过 `vcluster connect --print` 获取 kubeconfig 的代码边界，REAL-K8S-LAB-A 已通过非交互 `vcluster connect -- kubectl get --raw /version` 验证真实 kubeconfig 可用性。
- K8s proxy 当前默认仍是 Core API 契约和 local profile 响应；`M1-K8S-LIVE-G` 已通过 `forwarding_static` + 本机 `kubectl proxy` 证明 Core proxy 可转发到 live vCluster API，但生产 per-cluster metadata target、直连 TLS CA 和 KMS token 管理仍未完成。
- Encryption 当前已有 local profile、KMS/SM4 HTTP provider 代码边界、对象内容 SM4-GCM 流式加解密代码边界和 `validate-kms-sm4-live-gate`，且 KMS/SM4 provider streaming + objectstore round trip 已在 REAL-K8S-LAB-A 通过；本次通过 live-gate fixture 和本机 kubectl proxy 访问真实集群 Service，不代表生产 KMS/对象存储、直连 TLS/credential 管理或平台化部署完成。
- Secret 当前已有 Kubernetes Secret provider 写入代码边界和实例 binding manifest 注入边界，且 Kubernetes Secret live 写入、Pod env/file 可见性、KubeVirt VM Secret volume manifest API 接受与 VM guest 内 Secret volume 可读性均已在 REAL-K8S-LAB-A 通过。
- Reconcile controller 当前完成 metadata-backed leader election 代码边界和 `validate-reconcile-ha-live-gate`，且 controller 多副本 live HA failover 已在 REAL-K8S-LAB-A 通过；当前不宣称生产 Helm/Operator 化控制面部署已完成。
- REAL-K8S-LAB-A 当前已完成验证门禁定义与大量前置 guard；三台物理开发服务器已完成 Kubernetes `v1.36.1`、Kube-OVN `v1.15.8`、KubeVirt `v1.8.2` 最小组件部署。Kube-OVN network resource live gate 与 external LoadBalancer IP 可达性、KubeVirt VM lifecycle live gate、vCluster Helm/kubeconfig/Core proxy live gate、vCluster upgrade live gate、Secret live gate、controller HA failover live gate、KMS/SM4 provider streaming/objectstore round trip live gate、GPU 调度依赖与 CAPK node pool create/scale live gate 已真实跑通。
- Sprint 5 真实验证已完成；切换 Sprint 6 时必须按 Sprint 切换规则同步 `ANI-06-开发计划.md`、`repo/CURRENT-SPRINT.md` 和 `ANI-DOCS-INDEX.md`。

## 真实底座门禁

从 Sprint 5 起，涉及 K8s、Kube-OVN、KubeVirt、vCluster、KMS/SM4、K8s Secret 注入等真实组件的能力，不能再只靠 local profile 宣称完成。local profile 只能证明 API、SDK、状态机和调用边界正确；真实运行能力必须由真实组件环境、固定验证命令或批次记录证明。当前固定入口是 `REAL-K8S-LAB-A` 和 `make validate-real-k8s-profile`。

当前必须并行准备的真实验证环境：

| 组件 | 进入时机 | 验证目标 |
|---|---|---|
| K8s 测试集群 | Sprint 5 当前起 | API Server、Namespace、RBAC、ServiceAccount、StorageClass 基础可用 |
| Kube-OVN | Sprint 5 当前起 | VPC、Subnet、NetworkPolicy、Service/LB 可创建、可观察，external LoadBalancer IP 可达 |
| KubeVirt | Sprint 5 当前起 | VM 创建、启动、停止、删除、console/VNC 可运行 |
| vCluster | Sprint 5 当前起 | K8s 集群创建、kubeconfig、proxy 能真实访问租户集群 |
| KMS/SM4 + K8s Secret | Sprint 5~6 | 加解密、密钥轮换、Secret 写入和实例注入真实跑通 |

## ⛔ Guard 冻结令（2026-05-30 起）

REAL-K8S-LAB guard 系列（`M1-REAL-LAB-*`，已 299 个）**冻结，不再新增**。唯一例外：真实 live gate 执行中**实际复现**的缺陷，且只能用一个新 guard 防回归——此时新增一个并在 guard-index 注明对应真实缺陷。禁止再为"假设可能出现"的字段/空值/空格/类型边角预防性批量生成 guard。**当前唯一重心是把下面的真实 live gate 跑通，不是扩充校验器。**

## 真实 live gate 结果（Sprint 5 证据清单）

> 物理服务器 2026-05-29 到位，K8s `v1.36.1` + Kube-OVN `v1.15.8` + KubeVirt `v1.8.2` 已最小部署。
> 本仓库**只做 Core**；Services 已冻结移交外部团队，不在此推进。
> 执行原则：① 组件已就绪的先做；② 产品关键链路优先；③ 每个 gate 跑通后立刻 `--evidence-output` 归档 JSON 证据，并在 `repo/development-records/` 写一条 live 结果记录（Feature batch 规则）。
> 通用前置（每个 gate 进入前）：`--component-env-template-output` 生成 env 模板 → 填好 `contract_gates[].required_env` → `--component-preflight --component-env-file ... --evidence-output ...` 校验配置完整 → `--component-gate <id>` 重跑单个失败项。

> 命令说明：`make validate-*-live-gate` 只跑 **contract 模式**（无真实集群）；真实 **live 模式**必须直接运行脚本并带 `--live --evidence-output <path>`（脚本均支持这两个 flag）。

| 顺序 | Live gate | live 命令 | 前置/需补装 | 通过判据 |
|---|---|---|---|---|
| 1 | Kube-OVN 网络 + external LoadBalancer（已执行） | `python scripts/validate_kubeovn_network_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --external-lb-live --external-lb-curl-host ANI1 --external-lb-curl-host ANI2 --external-lb-curl-host ANI3 --evidence-output development-records/live-evidence/kubeovn-network-live-gate-2026-06-02.json` | 已修复 Kube-OVN join subnet 与 Tailscale CGNAT 冲突；CNI 三节点 Ready；已补齐 Multus/macvlan underlay、Kube-OVN LB service enablement 和 helper 镜像/脚本兼容方案 | Vpc/Subnet、NetworkPolicy、Service(LB 类型) 创建可观察；external LB helper 持有外部 IP，DNAT/MASQUERADE 存在，三节点 HTTP 访问返回 smoke 响应 |
| 2 | KubeVirt VM 生命周期与 console/VNC WebSocket session（已执行） | `python scripts/validate_kubevirt_vm_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a --container-disk-image quay.io/kubevirt/cirros-container-disk-demo:v1.8.2 --evidence-output development-records/live-evidence/kubevirt-vm-live-gate-2026-06-02.json` | 使用 KubeVirt `v1.8.2` cirros container disk；无需在本步补装 virtctl/CDI；WebSocket session 使用 KubeVirt `plain.kubevirt.io` 子协议 | VM create/start/observe/stop/delete 通过；console/VNC WebSocket session HTTP 101、子协议回选和流式读写通过 |
| 3 | vCluster 集群 + kubeconfig + live proxy（已执行） | `python scripts/validate_vcluster_live_gate.py --live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --namespace ani-tenant-tenant-a-vcluster --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 --evidence-output development-records/live-evidence/vcluster-live-gate-2026-06-02.json` | Helm + vCluster CLI + dev hostPath PV + Gateway `forwarding_static` 指向本机 kubectl proxy | Helm 装出 vCluster、kubeconfig 可用、kubectl `/version` 返回 `v1.35.0`、Core proxy `/version` 转发 HTTP 200；不代表生产 per-cluster metadata target/KMS token 管理已完成 |
| 4 | vCluster 升级（已执行） | `python scripts/validate_vcluster_upgrade_live_gate.py --live --tenant-id tenant-a-vcluster-upgrade --cluster-id k8sclu-upgrade-live --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --initial-version v1.35.0 --target-version v1.35.0 --vcluster-binary /private/tmp/vcluster-v0.34.1-darwin-arm64 --local-proxy-port 18002 --evidence-output development-records/live-evidence/vcluster-upgrade-live-gate-2026-06-02.json` | Helm + vCluster CLI + dev hostPath PV + Gateway `vcluster_helm`/`forwarding_static` | Core provider-backed create、Helm `controlPlane.distro.k8s.version`、升级后 vCluster `/version` 与 Core proxy `/version` 均通过；本次目标版本为 `v1.35.0`，不宣称跨小版本升级策略已生产化 |
| 5 | 节点池扩缩容 + GPU 调度（已执行） | `python scripts/validate_k8s_node_pool_live_gate.py --live --tenant-id 00000000-0000-0000-0000-000000000001 --cluster-id k8sclu-7ca0e91a-696c-4620-897f-96c24c35d7b6 --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --node-pool-name gpu-pool-live --instance-type gpu.rtx4090.xlarge --gpu-vendor nvidia --gpu-model RTX4090 --gpu-count 1 --gpu-resource-name nvidia.com/gpu --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --evidence-output development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json` | Node pool provider manifest 已完成真实 CAPI schema hardening，且已支持配置 CAPK bootstrap/infrastructure refs；GPU 节点依赖已补齐，ANI1/ANI2/ANI3 三台服务器均暴露 `nvidia.com/gpu: 2`，通用 GPU smoke Pod 与 ANI1 control-plane 专属 GPU smoke Pod 均已成功运行 `nvidia-smi`；CAPK workload cluster 使用 VM 内 Calico，宿主物理 K8s 继续使用 Kube-OVN | Core provider-backed create/update 通过；`gpu-pool-live` `MachineDeployment`、`MachineSet`、两个 worker `Machine`、两个 `KubevirtMachine`、两个 VM/VMI 均达到 2 副本 Ready/Available/Running；GPU smoke 调度通过；不代表 CAPK VM 内 GPU passthrough/vGPU 已完成 |
| 6 | Kubernetes Secret 写入 + 注入（已执行） | `python scripts/validate_secrets_live_gate.py --live --tenant-id tenant-a --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig --evidence-output development-records/live-evidence/secrets-live-gate-2026-06-02.json` | Gateway `SECRET_PROVIDER_MODE=kubernetes_rest` + 本机 kubectl proxy + KubeVirt API | Secret 真实写入、Pod env/file 可见、KubeVirt VM Secret volume manifest 被 API server 接受，且 VM guest 串口 probe 证明 Secret volume 中的 key 文件可读 |
| 7 | KMS/SM4 加解密 + 对象存储 round trip（已执行） | `python scripts/validate_kms_sm4_live_gate.py --live --tenant-id tenant-a --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --kms-base-url http://127.0.0.1:18004/api/v1/namespaces/ani-system/services/ani-kms-sm4-live-fixture:9305/proxy --kms-bearer-token <redacted> --object-put-url <redacted> --object-get-url <redacted> --evidence-output development-records/live-evidence/kms-sm4-live-gate-2026-06-02.json` | 已部署 REAL-K8S-LAB-A KMS/SM4 live-gate fixture + Gateway `kms_sm4_http` + Kubernetes API service proxy | Core key/seal/token、SM4-GCM 流式 seal/open、objectstore sealed 内容回读一致；不宣称生产 KMS/对象存储部署形态已完成 |
| 8 | Controller HA failover（已执行） | `python scripts/validate_reconcile_ha_live_gate.py --live --database-url 'postgres://ani:ani_dev_password@ani-reconcile-ha-postgres.ani-system.svc.cluster.local:5432/ani?sslmode=disable' --namespace ani-system --worker-selector app=ani-reconcile-worker --metrics-url kubernetes-raw --metrics-kubectl-raw-path /api/v1/namespaces/ani-system/services/ani-reconcile-worker-metrics:9205/proxy/metrics --psql-kubectl-namespace ani-system --psql-kubectl-selector app=ani-reconcile-ha-postgres --evidence-output development-records/live-evidence/reconcile-ha-live-gate-2026-06-02.json` | 已部署最小 Postgres/NATS/Redis + 双副本 worker；metrics 经 Kubernetes API service proxy | `control_plane_leases` holder 从 `worker-a` 切到 `worker-b`，删 leader Pod 后 follower 接管；不宣称生产 Helm/Operator 化控制面部署已完成 |

八个真实 live gate 均已通过并归档 evidence；对应能力已从"local profile / 代码边界"升级为"real-provider 已验证"。切换 Sprint 6 时继续保留本文的边界说明，不把开发验证形态误写成生产化部署形态。

> 注：也可用 `make validate-real-k8s-profile` 的组件级聚合模式（`--component-live --component-env-file ... --component-evidence-dir ... --evidence-output ...`）一次跑多个 gate；上表的单 gate 脚本命令用于聚焦推进与排错。

## 文档入口边界

- `CLAUDE.md` 只维护稳定强制规则、读取顺序、架构边界、提交门禁和 Karpathy 五条开发原则。
- 当前 Sprint 的详细完成项、未完成项、验收命令、下一步和真实底座边界以本文为准。
- 批次实现细节只写入 `repo/development-records/*.md`，不得把每日开发流水账或 API path 长列表写回 `CLAUDE.md`。
- 修改入口文档后必须运行 `make validate-doc-entrypoints`。

## 验收命令

```bash
make validate-doc-entrypoints
python scripts/validate_yaml.py api/openapi/v1.yaml api/openapi/services/v1.yaml deploy/real-k8s-lab/profile.yaml deploy/real-k8s-lab/vcluster-live-gate.yaml deploy/real-k8s-lab/vcluster-upgrade-live-gate.yaml deploy/real-k8s-lab/k8s-node-pool-live-gate.yaml deploy/real-k8s-lab/kubeovn-network-live-gate.yaml deploy/real-k8s-lab/kubeovn-lb-external-deps.yaml deploy/real-k8s-lab/kubeovn-lb-svc-script-configmap.yaml deploy/real-k8s-lab/kubevirt-vm-live-gate.yaml deploy/real-k8s-lab/reconcile-ha-live-gate.yaml deploy/real-k8s-lab/reconcile-ha-live-deps.yaml deploy/real-k8s-lab/kms-sm4-live-gate.yaml deploy/real-k8s-lab/kms-sm4-live-deps.yaml deploy/real-k8s-lab/secrets-live-gate.yaml
make validate-mock-a
make validate-doc-api
make validate-sdk-beta
make validate-sdk-mock-smoke
make validate-real-k8s-profile
make validate-vcluster-live-gate
make validate-vcluster-upgrade-live-gate
make validate-k8s-node-pool-live-gate
make validate-kubeovn-network-live-gate
make validate-kubevirt-vm-live-gate
make validate-reconcile-ha-live-gate
make validate-kms-sm4-live-gate
make validate-secrets-live-gate
go test ./services/ani-gateway/internal/router ./pkg/adapters/runtime
go test ./pkg/adapters/runtime ./pkg/bootstrap -run 'TestLocalWorkloadReconcileController|TestNewCapabilitiesDefaults|TestConfigEnvironmentOverridesWorkloadReconcileController|TestStartWorkloadReconcileControllerRequiresOptIn' -v
git diff --check
```

> 在没有联网依赖缓存时，`go test` 可能需要下载 Go module；本地可复用 `Makefile` 中的 `GOCACHE`/`GOMODCACHE` 设置。
