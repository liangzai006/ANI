# M1-K8S-LIVE-L · Node Pool CAPK Ref Config

> 日期：2026-06-02
> 范围：ANI Core `M1-K8S-LIVE-B` node pool provider-backed live gate 的代码硬阻塞修正。

## 背景

`M1-K8S-LIVE-J` 已把 `MachineDeployment` manifest 修正为 Cluster API `v1beta1` schema 合法结构，但 provider 仍固定渲染：

- `bootstrap.dataSecretName: <node-pool>-bootstrap`
- `infrastructureRef.kind: ANIMachineTemplate`
- `infrastructureRef.apiVersion: infrastructure.cluster.x-k8s.io/v1beta1`

真实 lab 里没有 `ANIMachineTemplate` CRD/provider；只安装 Cluster API core 也不能证明真实节点池扩缩容。官方 CAPK 模板使用 `KubeadmConfigTemplate` 与 `KubevirtMachineTemplate` 组合，因此当前固定 ref 会阻断 CAPK 路径。

## 实现

本批次新增 `KubernetesNodePoolProviderConfig`，默认保持历史输出不变，同时允许 Gateway 通过环境变量配置真实 provider refs：

- `K8S_NODE_POOL_MACHINE_VERSION`
- `K8S_NODE_POOL_BOOTSTRAP_DATA_SECRET_NAME_TEMPLATE`
- `K8S_NODE_POOL_BOOTSTRAP_REF_API_VERSION`
- `K8S_NODE_POOL_BOOTSTRAP_REF_KIND`
- `K8S_NODE_POOL_BOOTSTRAP_REF_NAME_TEMPLATE`
- `K8S_NODE_POOL_BOOTSTRAP_REF_NAMESPACE`
- `K8S_NODE_POOL_INFRASTRUCTURE_REF_API_VERSION`
- `K8S_NODE_POOL_INFRASTRUCTURE_REF_KIND`
- `K8S_NODE_POOL_INFRASTRUCTURE_REF_NAME_TEMPLATE`
- `K8S_NODE_POOL_INFRASTRUCTURE_REF_NAMESPACE`

模板支持 `{tenant_id}`、`{cluster_id}`、`{cluster_name}`、`{node_pool_id}`、`{node_pool_name}`、`{machine_deployment_name}`、`{namespace}`。

CAPK 方向可配置为：

- bootstrap `configRef`: `bootstrap.cluster.x-k8s.io/v1beta1` / `KubeadmConfigTemplate`
- infrastructureRef: `infrastructure.cluster.x-k8s.io/v1alpha1` / `KubevirtMachineTemplate`

## 验证

已通过：

```bash
GOPROXY=https://goproxy.cn,direct GOCACHE=/private/tmp/ani-go-cache GOMODCACHE=/private/tmp/ani-go-mod go test ./pkg/adapters/runtime -run 'TestKubernetesNodePoolProviderAdapter|TestLocalK8sClusterService' -v
GOPROXY=https://goproxy.cn,direct GOCACHE=/private/tmp/ani-go-cache GOMODCACHE=/private/tmp/ani-go-mod go test ./services/ani-gateway -run 'TestGatewayK8sClusterServiceFromConfigUsesClusterAPINodePoolProvider|TestGatewayK8sClusterServiceFromConfigUsesVClusterProvider' -v
```

真实 lab 复核仍显示：

- Kubernetes 三节点 Ready，内部地址为 `10.10.1.66-68`
- NVIDIA device plugin 在三节点 Running
- Cluster API / bootstrap / control-plane / infrastructure CRD 仍未安装
- `clusterctl` 仍未安装

## 边界

本批次只解除 Core node pool provider 固定 `ANIMachineTemplate` 的代码阻塞，不宣称 `M1-K8S-LIVE-B` 完整通过。完整通过仍需要真实安装并验证 Cluster API + 兼容基础设施 provider，并证明 provider-backed `MachineDeployment` create/scale 的实际效果。
