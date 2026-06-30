#!/usr/bin/env python3
"""Validate Gateway metadata persistence P6-B2 Harbor artifact-track contract."""

from __future__ import annotations

from pathlib import Path

import validate_registry_harbor_live_gate as harbor_gate


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_RUNNER = ROOT / "scripts/run_registry_harbor_live_gate.py"
GATE_YAML = ROOT / "deploy/real-k8s-lab/registry-harbor-live-gate.yaml"


def fail(message: str) -> None:
    raise SystemExit(f"gateway-metadata P6-B2 invalid: {message}")


def validate_artifact_runner_scripts() -> None:
    if not ARTIFACT_RUNNER.exists():
        fail(f"missing {ARTIFACT_RUNNER.relative_to(ROOT)}")
    runner = ARTIFACT_RUNNER.read_text(encoding="utf-8")
    for token in (
        "--track",
        "artifact",
        "push_artifact_test_image",
        "sprint13-registry-harbor-b2-live-evidence.json",
        'artifact_track=track == "artifact"',
    ):
        if token not in runner:
            fail(f"artifact runner must reference {token}")
    common = ROOT / "scripts/registry_harbor_runner_common.py"
    if not common.exists():
        fail(f"missing {common.relative_to(ROOT)}")
    push = common.read_text(encoding="utf-8")
    for token in ('"push"', "harbor_registry_host", "push_artifact_test_image"):
        if token not in push:
            fail(f"push helper must reference {token}")


def validate_harbor_gate_artifact_track_helpers() -> None:
    if harbor_gate.DEFAULT_ARTIFACT_REPOSITORY != "ani-live-gate-smoke":
        fail("DEFAULT_ARTIFACT_REPOSITORY must be ani-live-gate-smoke")
    sample = harbor_gate.default_scan_image_for_tenant("tenant-a", "ani-live-gate-smoke")
    if sample != "default/ani-live-gate-smoke:latest":
        fail(f"unexpected default scan image {sample}")


def validate_gate_yaml_optional_checks() -> None:
    document = harbor_gate.load_gate(GATE_YAML)
    optional = document.get("optional_live_checks")
    if not isinstance(optional, list):
        fail("registry harbor gate must define optional_live_checks")
    check_ids = {check.get("id") for check in optional if isinstance(check, dict)}
    for required in ("core-registry-artifacts-list", "core-registry-scan-result"):
        if required not in check_ids:
            fail(f"optional_live_checks must include {required}")


def main() -> int:
    validate_artifact_runner_scripts()
    validate_harbor_gate_artifact_track_helpers()
    validate_gate_yaml_optional_checks()
    print("Gateway metadata persistence P6-B2 Harbor artifact-track contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
