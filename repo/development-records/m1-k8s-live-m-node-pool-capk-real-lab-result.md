# M1-K8S-LIVE-M · Node Pool CAPK Real Lab Result

日期：2026-06-03
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：通过。`M1-K8S-LIVE-B` node pool provider-backed create/scale live gate 已在 REAL-K8S-LAB-A 真实环境通过。

Evidence：`development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json`

## 结论

REAL-K8S-LAB-A 已具备 Cluster API + CAPK 路径，并通过 Core Gateway 触发 node pool create/update：

- Core node pool API 返回 provider-backed real dev profile，并生成真实 `MachineDeployment`。
- `gpu-pool-live` `MachineDeployment` 在租户 namespace 中达到 `2/2` desired/current/ready/available/up-to-date。
- 对应 `MachineSet` 聚合 `spec/status/ready/available/up-to-date` 均为 `2`。
- 两个 worker `Machine` 均 `Ready=True` / `Available=True`，包含 `nodeRef`、`providerID` 和 InternalIP。
- 两个 CAPK `KubevirtMachine` 均 Ready。
- 两个 KubeVirt `VirtualMachine` 与 `VirtualMachineInstance` 均 Running/Ready。
- `validate_k8s_node_pool_live_gate.py --live` 补强后会校验上述 CAPI/CAPK 资源就绪状态，并归档结构化 evidence。

本次重复运行 live gate 时，已存在的 node pool 处于 2 副本扩容完成状态，因此 evidence 中 `machine_deployment_create_replica_check` 为 `existing_replicas_2`。脚本仍执行 Core create/update API，并以当前真实 CAPI/CAPK 资源状态证明 provider-backed node pool 已达到扩容后的 Ready 状态。

## 已执行命令

```bash
python scripts/validate_k8s_node_pool_live_gate.py --live \
  --tenant-id 00000000-0000-0000-0000-000000000001 \
  --cluster-id k8sclu-7ca0e91a-696c-4620-897f-96c24c35d7b6 \
  --gateway-url http://127.0.0.1:8080/api/v1 \
  --ani-bearer-token dev-token \
  --node-pool-name gpu-pool-live \
  --instance-type gpu.rtx4090.xlarge \
  --gpu-vendor nvidia \
  --gpu-model RTX4090 \
  --gpu-count 1 \
  --gpu-resource-name nvidia.com/gpu \
  --kubeconfig /Users/zhangfan/ANI/local-secrets/real-k8s-lab.kubeconfig \
  --readiness-timeout-seconds 180 \
  --readiness-poll-seconds 5 \
  --evidence-output development-records/live-evidence/k8s-node-pool-live-gate-2026-06-03.json
```

补强后的 contract/local 验证：

```bash
python -m unittest validate_k8s_node_pool_live_gate_test.py
make validate-k8s-node-pool-live-gate
```

## 边界

- 本记录证明的是 Core node pool API 到 Cluster API/CAPK `MachineDeployment` / `MachineSet` / `Machine` / `KubevirtMachine` / VM / VMI 的真实 create/update/scale-ready 链路。
- CAPK workload cluster 是运行在 KubeVirt VM 内的真实 Kubernetes 集群；宿主物理 K8s 仍使用 Kube-OVN，workload cluster 内部 CNI 使用 Calico。
- 本记录不宣称 CAPK worker VM 已完成 GPU passthrough/vGPU。宿主三台物理服务器 GPU runtime/device-plugin/scheduler 已由 `M1-K8S-LIVE-K` 证明；VM 内 GPU 直通属于后续独立能力。
- 本记录不宣称生产级 clusterctl/bootstrap 自动化、生产镜像供应链、跨版本升级策略或直连 credential 管理已经完成。
- Tailscale 只用于 Mac/Codex 访问真实 lab；服务器之间和集群内部配置继续使用真实 LAN 地址。
