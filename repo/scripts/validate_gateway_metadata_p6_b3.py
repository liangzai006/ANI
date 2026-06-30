#!/usr/bin/env python3
"""Validate Gateway metadata persistence P6-B3 pull secret Kubernetes apply contract."""

from __future__ import annotations

from pathlib import Path

import validate_registry_harbor_live_gate as harbor_gate


ROOT = Path(__file__).resolve().parents[1]
K8S_RUNNER = ROOT / "scripts/run_registry_harbor_live_gate.py"
GATE_YAML = ROOT / "deploy/real-k8s-lab/registry-harbor-live-gate.yaml"
OPENAPI = ROOT / "api/openapi/v1.yaml"


def fail(message: str) -> None:
    raise SystemExit(f"gateway-metadata P6-B3 invalid: {message}")


def validate_kubernetes_apply_runner() -> None:
    if not K8S_RUNNER.exists():
        fail(f"missing {K8S_RUNNER.relative_to(ROOT)}")
    runner = K8S_RUNNER.read_text(encoding="utf-8")
    for token in (
        "pull-secret-kubernetes",
        "pull_secret_kubernetes_track=track == \"pull-secret-kubernetes\"",
        "sprint13-registry-harbor-b3-live-evidence.json",
        "--dev",
        "kubernetes.io/dockerconfigjson",
    ):
        if token not in runner:
            fail(f"kubernetes apply runner must reference {token}")


def validate_openapi_contract() -> None:
    content = OPENAPI.read_text(encoding="utf-8")
    for token in (
        "/registry/projects/{project}/pull-secret/kubernetes-apply",
        "applyRegistryProjectPullSecretToKubernetes",
        "RegistryPullSecretKubernetesApply",
    ):
        if token not in content:
            fail(f"openapi must define {token}")


def validate_harbor_gate_optional_check() -> None:
    document = harbor_gate.load_gate(GATE_YAML)
    optional = document.get("optional_live_checks")
    if not isinstance(optional, list):
        fail("registry harbor gate must define optional_live_checks")
    check_ids = {check.get("id") for check in optional if isinstance(check, dict)}
    if "core-registry-pull-secret-kubernetes-apply" not in check_ids:
        fail("optional_live_checks must include core-registry-pull-secret-kubernetes-apply")


def validate_harbor_gate_helpers() -> None:
    if harbor_gate.DEFAULT_PULL_SECRET_K8S_NAME != "ani-live-gate-pull":
        fail("DEFAULT_PULL_SECRET_K8S_NAME must be ani-live-gate-pull")
    if "production_registry_pull_secret_kubernetes_applied" not in harbor_gate.PULL_SECRET_K8S_TRACK_PROOF_ITEMS:
        fail("PULL_SECRET_K8S_TRACK_PROOF_ITEMS must include production_registry_pull_secret_kubernetes_applied")


def main() -> int:
    validate_kubernetes_apply_runner()
    validate_openapi_contract()
    validate_harbor_gate_optional_check()
    validate_harbor_gate_helpers()
    print("Gateway metadata persistence P6-B3 pull secret Kubernetes apply contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
