#!/usr/bin/env python3
"""Validate Gateway metadata persistence P6-B1 in-cluster Harbor production-shaped contract."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_LIVE_MANIFEST = ROOT / "deploy/real-k8s-lab/sprint13-registry-harbor-live.yaml"
GATEWAY_DEPLOYMENT = ROOT / "deploy/real-k8s-lab/sprint13-production-shaped-gateway-deployment.yaml"
GATEWAY_PROFILE = ROOT / "deploy/real-k8s-lab/sprint13-production-shaped-gateway-profile.yaml"
IN_CLUSTER_RUNNER = ROOT / "scripts/run_registry_harbor_live_gate.py"
REQUIRED_REGISTRY_SECRET_KEYS = {
    "endpoint",
    "username",
    "password",
    "secure",
    "tls_insecure",
}
REQUIRED_S08_PROOF_ITEMS = {
    "production_gateway",
    "production_harbor_credentials",
    "production_registry_provider_runtime",
    "production_registry_artifacts_observed",
    "production_registry_scan_result_observed",
}


def fail(message: str) -> None:
    raise SystemExit(f"gateway-metadata P6-B1 invalid: {message}")


def load_yaml_documents(path: Path) -> list[dict]:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return [doc for doc in documents if isinstance(doc, dict)]


def validate_registry_secret_manifest() -> None:
    documents = load_yaml_documents(REGISTRY_LIVE_MANIFEST)
    secrets = [doc for doc in documents if doc.get("kind") == "Secret"]
    if len(secrets) != 1:
        fail("sprint13-registry-harbor-live.yaml must define exactly one Secret")
    secret = secrets[0]
    if secret.get("metadata", {}).get("name") != "ani-registry-production-shaped-runtime":
        fail("registry Secret name must be ani-registry-production-shaped-runtime")
    if secret.get("metadata", {}).get("namespace") != "ani-system":
        fail("registry Secret namespace must be ani-system")
    string_data = secret.get("stringData")
    if not isinstance(string_data, dict):
        fail("registry Secret must define stringData")
    missing = REQUIRED_REGISTRY_SECRET_KEYS - set(string_data)
    if missing:
        fail(f"registry Secret stringData missing keys: {', '.join(sorted(missing))}")


def validate_in_cluster_runner() -> None:
    if not IN_CLUSTER_RUNNER.exists():
        fail("missing in-cluster Harbor live gate runner script")
    content = IN_CLUSTER_RUNNER.read_text(encoding="utf-8")
    for token in (
        "ANI_BEARER_TOKEN",
        "--track",
        "in-cluster",
        "GATEWAY_NODE_PORT",
        "sprint13-registry-harbor-in-cluster-live-evidence.json",
    ):
        if token not in content:
            fail(f"in-cluster runner must reference {token}")


def validate_gateway_profile_s08() -> None:
    documents = load_yaml_documents(GATEWAY_PROFILE)
    if len(documents) != 1:
        fail("production-shaped gateway profile must be a single YAML document")
    profile = documents[0]
    slice_proof_items = profile.get("slice_proof_items")
    if not isinstance(slice_proof_items, dict):
        fail("production profile must define slice_proof_items")
    s08_items = slice_proof_items.get("S08")
    if not isinstance(s08_items, list):
        fail("production profile must define slice_proof_items.S08")
    proof_set = {str(item).strip() for item in s08_items if str(item).strip()}
    missing = REQUIRED_S08_PROOF_ITEMS - proof_set
    if missing:
        fail(f"production profile S08 proof_items missing {', '.join(sorted(missing))}")


def main() -> int:
    validate_registry_secret_manifest()
    validate_in_cluster_runner()
    validate_gateway_profile_s08()
    print("Gateway metadata persistence P6-B1 in-cluster Harbor contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
