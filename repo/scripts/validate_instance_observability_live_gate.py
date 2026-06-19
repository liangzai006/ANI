#!/usr/bin/env python3
"""Validate Sprint 13 instance observability Prometheus live gate contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/instance-observability-live-gate.yaml"
PROFILE = "SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A"
REQUIRED_CHECKS = {
    "prometheus-health-ready",
    "core-instance-logs-list",
    "core-instance-events-list",
    "core-instance-metrics-get",
    "core-instance-security-events-list",
    "core-instance-exec-session-create",
}
REQUIRED_DOC_TOKENS = [
    "SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A-TRACK",
    "validate-instance-observability-live-gate",
    "Prometheus",
    "kubelet",
    "LIVE PENDING",
]


def fail(message: str) -> None:
    raise SystemExit(f"instance observability live gate invalid: {message}")


def gate_path_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_gate(path: Path) -> dict[str, Any]:
    label = gate_path_label(path)
    if not path.exists():
        fail(f"missing {label}")
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError:
        fail(f"unreadable {label}")
    except yaml.YAMLError:
        fail(f"malformed {label}")
    if not isinstance(data, dict):
        fail(f"{label} must be a YAML object")
    return data


def validate_contract(document: dict[str, Any]) -> None:
    if document.get("profile") != PROFILE:
        fail(f"profile must be {PROFILE}")
    if document.get("status") not in {"contract", "live"}:
        fail("status must be contract or live")
    tools = document.get("required_tools")
    if not isinstance(tools, list) or "curl" not in tools:
        fail("required_tools must include curl")
    checks = document.get("live_checks")
    if not isinstance(checks, list):
        fail("live_checks must be a list")
    check_ids = set()
    for check in checks:
        if not isinstance(check, dict):
            fail("live check must be an object")
        for field in ("id", "command", "pass_condition"):
            value = check.get(field)
            if not isinstance(value, str) or not value.strip():
                fail(f"live check {field} must be a non-empty string")
        check_ids.add(check["id"])
    missing = REQUIRED_CHECKS - check_ids
    if missing:
        fail(f"missing live checks: {', '.join(sorted(missing))}")


def validate_docs() -> None:
    docs = {
        "ANI-DOCS-INDEX.md": DOC_ROOT / "ANI-DOCS-INDEX.md",
        "ANI-06-开发计划.md": DOC_ROOT / "ANI-06-开发计划.md",
        "CURRENT-SPRINT.md": ROOT / "CURRENT-SPRINT.md",
        "development-records/README.md": ROOT / "development-records/README.md",
    }
    for label, path in docs.items():
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            fail(f"missing doc {label}")
        except OSError:
            fail(f"unreadable doc {label}")
        except UnicodeError:
            fail(f"malformed doc {label}")
        for token in REQUIRED_DOC_TOKENS:
            if token not in content:
                fail(f"{label} must reference {token}")


def validate_gate_path(path: str) -> None:
    if not path.strip():
        fail("gate path must not be empty")
    if path != path.strip():
        fail("gate path must not contain surrounding whitespace")


def validate_optional_output_path(path: str | None) -> None:
    if path is None:
        return
    if not path.strip():
        fail("evidence output path must not be empty")
    if path != path.strip():
        fail("evidence output path must not contain surrounding whitespace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="instance observability live gate YAML")
    parser.add_argument("--live", action="store_true", help="reserved for human-gated live execution")
    parser.add_argument("--evidence-output", help="reserved path for human-gated live evidence JSON")
    args = parser.parse_args()

    validate_gate_path(args.gate)
    validate_optional_output_path(args.evidence_output)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        fail("--live is human-gated for SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A and is not automated in A-track")
    print("SPRINT13-INSTANCE-OBSERVABILITY-PROMETHEUS-A contract valid; live execution is human-gated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
