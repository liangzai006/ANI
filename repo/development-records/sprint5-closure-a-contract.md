# SPRINT5-CLOSURE-A — Sprint 5 Closure Contract

完成日期：2026-06-03
对应 Sprint：Sprint 5（2026-05 提前启动；计划窗口 2026-07-16 ~ 2026-07-31）
验证结果：`make validate-real-k8s-profile`、8 个真实 live gate (`--live --evidence-output`) 均通过并归档 evidence、`make test`、`make validate-architecture`、`make validate-doc-entrypoints`、YAML 校验和 `git diff --check` 已通过

## 实现了什么

完成 Sprint 5 真实 live gate 全链路收敛：在三台物理开发服务器（Kubernetes `v1.36.1` + Kube-OVN `v1.15.8` + KubeVirt `v1.8.2`）上，真实跑通并归档了 8 个 live gate 的 evidence JSON，把以下能力从"local profile / 代码边界"升级为"real-provider 已验证"：

1. Kube-OVN network resource 与 external LoadBalancer IP 可达性（`M1-NETWORK-LIVE-D`）
2. KubeVirt VM lifecycle 与 console/VNC WebSocket session（`M1-KUBEVIRT-LIVE-D`）
3. vCluster Helm install / kubeconfig 可用性 / Core live proxy 转发（`M1-K8S-LIVE-G`）
4. vCluster Helm upgrade / 升级后 `/version` 与 Core proxy（`M1-K8S-LIVE-H`）
5. CAPK node pool create/update/scale-ready，MachineDeployment/MachineSet/Machine/VM/VMI 均 Ready（`M1-K8S-LIVE-M`）
6. Kubernetes Secret 写入、Pod env/file 可见、VM guest Secret volume 可读（`M1-SECRETS-LIVE-D`）
7. KMS/SM4 provider streaming seal/open 与 objectstore sealed content round trip（`M1-ENCRYPT-LIVE-C`）
8. Controller HA failover：双副本 worker、leader 删除后 follower 接管（`M1-RECONCILE-LIVE-C`）

同步完成 Sprint 5 文档闭环：guard 计数统一为 299（guard-index 为准）、CLAUDE.md 状态行去掉"收敛中/推进中"等动态词、CURRENT-SPRINT.md 字段名"不可标记为完成"改为"生产化边界"、历史切片中的时点否定句补充"后续已由 M1-* 补齐"说明、ANI-DOCS-INDEX.md 里程碑改为"已通过"措辞。

## 关键文件改动

| 文件 | 修改说明 |
|---|---|
| `CLAUDE.md` | Section 0 去除"Sprint 5 收敛中"和"真实 live gate 推进"等动态状态词，改为只指向 `repo/CURRENT-SPRINT.md` |
| `repo/CURRENT-SPRINT.md` | 字段名"不可标记为完成"→"生产化边界"；guard 数 237→299；已完成切片 1/2/9 补充时点说明 |
| `repo/development-records/README.md` | guard 系列行 237→299；新增 SPRINT5-CLOSURE-A 条目 |
| `ANI-06-开发计划.md` | Sprint 5 行 237→299 |
| `ANI-DOCS-INDEX.md` | 2026-07-31 里程碑改为"Sprint 5 已通过…后续作为回归门禁保留" |

## 完工标准达成

- [x] 所有 8 个真实 live gate 均已真实执行并归档 evidence JSON（`development-records/live-evidence/`）。
- [x] `make test`、`make validate-architecture`、`make validate-doc-entrypoints` 和 `git diff --check` 通过。
- [x] 全部入口文档（CLAUDE.md、ANI-06、CURRENT-SPRINT.md、ANI-DOCS-INDEX.md、README.md）guard 수 일치：299。
- [x] CLAUDE.md 不再含动态流水账状态词，符合"轻量入口稳定规则"原则。
- [x] 历史切片否定句已补充"后续已由 M1-* 补齐"上下文，消除与当前完成态的语义冲突。
- [x] Sprint 5 closure 记录已建立，与 Sprint 3/4 保持一致的文档惯例。

## 备注

Sprint 5 证明了 Core 真实 provider 主链路可运行，但不代表生产化部署形态已完成（生产 KMS/对象存储、直连 TLS credential 管理、Helm/Operator 化控制面、CAPK VM 内 GPU passthrough/vGPU、生产 per-cluster metadata target 等仍在后续 Sprint 推进）。

切换 Sprint 6 时须按 Sprint 切换规则同步 `ANI-06-开发计划.md`、`repo/CURRENT-SPRINT.md` 和 `ANI-DOCS-INDEX.md`。
