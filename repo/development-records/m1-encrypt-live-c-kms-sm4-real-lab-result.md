# M1-ENCRYPT-LIVE-C — KMS/SM4 Real Lab Live Result

完成日期：2026-06-02
对应 Sprint：Sprint 5（2026-07-16 ~ 07-31）
验证结果：真实执行 `validate_kms_sm4_live_gate.py --live`，归档 `development-records/live-evidence/kms-sm4-live-gate-2026-06-02.json`，KMS/SM4 live gate 通过。

## 实现了什么

在 REAL-K8S-LAB-A 上补齐 KMS/SM4 live-gate fixture 依赖：

- 新增 `tools/kms-sm4-live-fixture`，提供 KMS provider HTTP API、SM4-GCM streaming seal/open 和验证对象 PUT/GET 存储路径。
- 新增 `deploy/real-k8s-lab/kms-sm4-live-deps.yaml`，将 fixture 作为真实集群 Pod + Service 运行。
- `ani-gateway` 使用既有 `ENCRYPTION_PROVIDER_MODE=kms_sm4_http` 接线访问 fixture，证明 Core encryption API 没有退回 local profile。
- live validator 通过 Core create key、Core seal、Core unseal-token、KMS streaming seal/open 和 objectstore sealed content PUT/GET round trip。

本次通过本机 `kubectl proxy` 访问真实集群 Service。`kubectl proxy` 不转发 `Authorization` header 到后端 Service，因此 fixture 内部 bearer 校验关闭；访问边界由本机 kubeconfig 和 Kubernetes API proxy 保护。该结果不代表生产 KMS、生产对象存储、生产直连 TLS/credential 管理或平台化 Helm/Operator 部署形态完成。

## 关键文件改动

| 文件 | 新增/修改 | 说明 |
|---|---|---|
| `tools/kms-sm4-live-fixture/` | 新增 | REAL-K8S-LAB-A KMS/SM4 + objectstore live-gate fixture |
| `deploy/real-k8s-lab/kms-sm4-live-deps.yaml` | 新增 | fixture Deployment/Service manifest |
| `pkg/adapters/runtime/sm4.go` | 修改 | 暴露 `NewSM4BlockCipher` 供 live fixture 复用现有 SM4 实现 |
| `development-records/live-evidence/kms-sm4-live-gate-2026-06-02.json` | 新增 | KMS/SM4 live gate 通过证据 |

## 完工标准达成

- [x] Core `POST /api/v1/encryption/keys` 经 Gateway KMS provider 创建 SM4 key
- [x] Core `POST /api/v1/encryption/seal` 返回 `kms+sm4://...` sealed URI 和 unseal token
- [x] Core `POST /api/v1/encryption/unseal-token` 返回 unseal token
- [x] KMS provider streaming seal 返回非明文 ciphertext
- [x] objectstore PUT 写入 sealed content
- [x] objectstore GET 读回 sealed content 与写入一致
- [x] KMS provider streaming open 还原原始 plaintext
- [x] evidence JSON 不包含 bearer token 或 objectstore PUT/GET URL

## 验证命令

```bash
go test ./tools/kms-sm4-live-fixture
go test ./pkg/adapters/runtime -run 'TestSM4BlockCipherMatchesStandardVector|TestLocalEncryptionServiceSealsObjectContentWithSM4GCMChunks|TestLocalEncryptionServiceDelegatesLifecycleAndSealToProvider' -v
python scripts/validate_yaml.py deploy/real-k8s-lab/kms-sm4-live-deps.yaml deploy/real-k8s-lab/kms-sm4-live-gate.yaml
python scripts/validate_kms_sm4_live_gate.py --live --tenant-id tenant-a --gateway-url http://127.0.0.1:8080/api/v1 --ani-bearer-token dev-token --kms-base-url http://127.0.0.1:18004/api/v1/namespaces/ani-system/services/ani-kms-sm4-live-fixture:9305/proxy --kms-bearer-token <redacted> --object-put-url <redacted> --object-get-url <redacted> --evidence-output development-records/live-evidence/kms-sm4-live-gate-2026-06-02.json
```

## 备注

真实 lab fixture 运行在 `ani-system` namespace，节点内 hostPath 二进制用于避免为一次性 live gate 引入镜像构建和 registry 依赖。该 fixture 是验证依赖，不是生产 KMS/对象存储实现。
