# SPRINT13-NETROUTE-KUBEOVN-LIVE-A - Network route Kube-OVN live gate result

> 记录类型：Sprint 13 B-track production-shaped live result
> 完成日期：2026-06-20
> 范围：ANI Core S01 network route Kube-OVN provider / route metadata / cleanup
> 状态：**production-shaped gate passed**；不代表 full platform production ready

## §153 五项实测结果

| 项 | 实测结果 |
|---|---|
| 当前状态 | S01 已重新执行严格版 `--production-shaped` live gate 并通过。ANI Gateway 先经 Core API 创建 VPC/Subnet/Route 并通过 `GET /networks/routes` list 校验，再用 kubectl 只做真实 Kubernetes + Kube-OVN 底层对象 observe/cleanup。 |
| 真实组件 + 版本 | Kubernetes `v1.36.1`；Kube-OVN `v1.15.8`；route 写入 `Vpc.spec.staticRoutes`。 |
| live gate 命令 | `python3 scripts/validate_kubeovn_network_live_gate.py --live --cleanup --production-shaped --gateway-url http://ani-gateway.ani-system.svc:8080/api/v1 --ani-bearer-token <redacted> --kubeconfig /tmp/incluster.kubeconfig --tenant-id tenant-a --vpc-name ani-s01-prodshape-gateway-vpc3 --subnet-name ani-s01-prodshape-gateway-subnet3 --route-name ani-s01-prodshape-gateway-route3 --security-group-name ani-s01-prodshape-gateway-sg3 --load-balancer-name ani-s01-prodshape-gateway-lb3 --evidence-output development-records/live-evidence/sprint13-netroute-kubeovn-live-evidence.json` |
| evidence 输出路径 | `repo/development-records/live-evidence/sprint13-netroute-kubeovn-live-evidence.json` |
| 边界 | Production-shaped gate passed 只证明 S01 Gateway create/list、provider apply/observe、in-cluster RBAC 与 route metadata reconciliation 门禁通过；cleanup 由 live gate 对底层临时资源执行，不证明 Gateway delete / provider delete 全生命周期；不代表 production ready / full platform release，不代表外部 LB 数据面 SLA、生产凭据轮换或所有网络高级能力完成。 |

## Evidence 摘要

```json
{
  "status": "passed",
  "namespace": "ani-tenant-tenant-a",
  "cleanup": {"status": "deleted"},
  "gateway_vpc_create_status": 201,
  "gateway_subnet_create_status": 201,
  "gateway_route_create_status": 201,
  "gateway_route_list_status": 200,
  "gateway_route_count": 1,
  "production_shape": {
    "status": "passed",
    "transport_profile": "production_gateway_in_cluster_serviceaccount",
    "missing_items": [],
    "proof_items": [
      "production_gateway",
      "in_cluster_serviceaccount_rbac",
      "persistent_route_metadata_reconciliation"
    ]
  }
}
```

## 代码与部署闭环

- S01 live gate 禁止本地 Gateway / kubectl proxy 形态标 passed，并强制 production-shaped evidence 包含 Gateway VPC/Subnet/Route create 与 Route list 字段。
- 本次修复了 S01 network provider route-only 缺口：Gateway network provider 现在覆盖 VPC/Subnet/SecurityGroup/LoadBalancer/Route；Kubernetes dry-run 使用 server-side apply PATCH `dryRun=All`，避免 route 更新既有 VPC 时 POST create 409。
- Kube-OVN tenant subnet 不使用物理管理网 `10.10.0.0/22` 或 Tailscale `100.64.128.0/24`，避免和三台物理服务器管理/远程访问网段重叠。
- 本次临时 Service、NetworkPolicy、Subnet、Vpc 与 Namespace 底层资源已 cleanup；Core route metadata 作为持久 metadata reconciliation 证据保留，不等同底层临时资源未清理。
- 当前 Kube-OVN provider adapter 仍只允许 create/apply/observe；若后续要把 S01 标为完整 network lifecycle production ready，必须补 Gateway delete -> provider delete 的代码路径、live gate 和 evidence。
- S01 live gate 使用的临时 Gateway builder Pod/Service 已在验证后清理，复查 `ani-system` 与 `ani-tenant-tenant-a` 无本次临时对象残留。
