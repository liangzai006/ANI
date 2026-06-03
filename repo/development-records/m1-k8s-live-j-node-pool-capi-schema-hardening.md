# M1-K8S-LIVE-J — Node Pool CAPI Schema Hardening

日期：2026-06-02
对应 Sprint：Sprint 5（真实 live gate 收敛）
验证结果：通过 contract/runtime 聚焦测试；不代表 `M1-K8S-LIVE-B` 真实 node pool/GPU live gate 已通过。

## 背景

推进 `M1-K8S-LIVE-B` 时复核 Cluster API `v1beta1` `MachineDeployment` schema，确认真实 CAPI 要求 `spec.template.spec.bootstrap`、`clusterName` 和 `infrastructureRef`，且不会保留任意 `template.spec.gpu` / `template.spec.instanceType` 字段。

原 node pool provider adapter 将 ANI intent 放入这些非 CAPI 字段。即使补装 Cluster API CRD，也会因为 manifest 不符合真实 CAPI schema 而无法作为可靠 live gate 基础。

## 实现了什么

- `KubernetesNodePoolProviderAdapter` 改为渲染 CAPI schema 合法的 `MachineDeployment`：
  - `spec.template.spec.clusterName`
  - `spec.template.spec.bootstrap.dataSecretName`
  - `spec.template.spec.infrastructureRef`
- GPU vendor/model/count/resource 与 instance type intent 改由 `MachineDeployment` 和 machine template metadata labels/annotations 保留。
- `validate_k8s_node_pool_live_gate.py` 不再要求非法的 `template.spec.gpu`，改为验证合法 metadata intent，同时校验 CAPI 必需字段存在。

## 当前边界

这次只修正真实 Cluster API schema 兼容性，未改变 live gate 完成判据。REAL-K8S-LAB-A 当前仍未安装 Cluster API / 对应基础设施 provider，且三台真实节点仍未暴露 `nvidia.com/gpu`。因此 `M1-K8S-LIVE-B` 仍不能标记通过。

安装 Cluster API core 只能提供 `MachineDeployment` API resource；要证明真实节点池扩缩容，还需要明确并安装能管理当前节点形态的基础设施 provider。要证明 GPU 调度，还需要至少一个真实节点暴露 `nvidia.com/gpu`。

## 验证命令

```bash
python -m unittest validate_k8s_node_pool_live_gate_test.py
GOCACHE=/private/tmp/ani-go-build GOMODCACHE=/Users/zhangfan/ANI/repo/.cache/gomod go test ./pkg/adapters/runtime -run 'TestKubernetesNodePoolProviderAdapter|TestLocalK8sClusterServiceAppliesNodePoolsThroughProvider|TestLocalK8sClusterServiceKeepsNodePoolsLocalWithoutNodePoolProvider|TestKubernetesRESTClientSupportsClusterAPIMachineDeployment' -v
make validate-k8s-node-pool-live-gate
python scripts/validate_yaml.py deploy/real-k8s-lab/k8s-node-pool-live-gate.yaml
```
