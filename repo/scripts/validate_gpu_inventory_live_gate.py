#!/usr/bin/env python3
"""Validate Sprint 13 GPU inventory live gate contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/gpu-inventory-live-gate.yaml"
PROFILE = "SPRINT13-GPU-INVENTORY-DCGM-A"
REQUIRED_CHECKS = {
    "nvidia-device-plugin-node-capacity",
    "core-gpu-inventory-list",
    "core-gpu-occupancy-get",
    "dcgm-exporter-metrics-readable",
}
REQUIRED_DOC_TOKENS = [
    "SPRINT13-GPU-INVENTORY-DCGM-A-TRACK",
    "validate-gpu-inventory-live-gate",
    "NVIDIA device-plugin",
    "DCGM",
    "LIVE PENDING",
]
NVIDIA_GPU_RESOURCE = "nvidia.com/gpu"
DCGM_GPU_UTIL_METRIC = "DCGM_FI_DEV_GPU_UTIL"


@dataclass(frozen=True)
class LiveArgs:
    gateway_url: str
    ani_bearer_token: str
    kubectl_binary: str
    kubeconfig: str
    kubernetes_nodes_url: str
    dcgm_metrics_url: str
    evidence_output: str


def fail(message: str) -> None:
    raise SystemExit(f"gpu inventory live gate invalid: {message}")


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
    if not isinstance(tools, list) or "kubectl" not in tools:
        fail("required_tools must include kubectl")
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


def trim_url(value: str) -> str:
    return value.strip().rstrip("/")


def default_command_runner(command: list[str]) -> str:
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        fail(f"command failed: {command[0]} returned {result.returncode}")
    return result.stdout


def default_json_getter(url: str, bearer_token: str) -> tuple[int, dict[str, Any]]:
    headers = {}
    if bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token.strip()}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read().decode("utf-8")
    except OSError as exc:
        fail(f"could not read {url}: {exc}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        fail(f"{url} did not return JSON")
    if not isinstance(payload, dict):
        fail(f"{url} must return a JSON object")
    return status, payload


def default_text_getter(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", response.getcode()))
            return status, response.read().decode("utf-8", errors="replace")
    except OSError as exc:
        fail(f"could not read {url}: {exc}")


def parse_gpu_capacity(value: Any) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def summarize_kubernetes_gpu_nodes(node_list: dict[str, Any]) -> tuple[int, int]:
    items = node_list.get("items")
    if not isinstance(items, list):
        fail("kubectl node list must contain items")
    gpu_nodes = 0
    total = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if not isinstance(status, dict):
            continue
        capacity = status.get("capacity")
        allocatable = status.get("allocatable")
        capacity_count = parse_gpu_capacity(capacity.get(NVIDIA_GPU_RESOURCE) if isinstance(capacity, dict) else None)
        allocatable_count = parse_gpu_capacity(allocatable.get(NVIDIA_GPU_RESOURCE) if isinstance(allocatable, dict) else None)
        count = max(capacity_count, allocatable_count)
        if count > 0:
            gpu_nodes += 1
            total += count
    return gpu_nodes, total


def load_kubernetes_nodes(
    args: LiveArgs,
    command_runner: Callable[[list[str]], str],
    json_getter: Callable[[str, str], tuple[int, dict[str, Any]]],
) -> dict[str, Any]:
    if args.kubernetes_nodes_url.strip():
        status, nodes_doc = json_getter(args.kubernetes_nodes_url.strip(), "")
        if status != 200:
            fail(f"Kubernetes nodes endpoint returned HTTP {status}")
        return nodes_doc

    kubectl_command = [args.kubectl_binary or "kubectl"]
    if args.kubeconfig.strip():
        kubectl_command.extend(["--kubeconfig", args.kubeconfig.strip()])
    kubectl_command.extend(["get", "nodes", "-o", "json"])
    try:
        nodes_doc = json.loads(command_runner(kubectl_command))
    except json.JSONDecodeError:
        fail("kubectl node list did not return JSON")
    if not isinstance(nodes_doc, dict):
        fail("kubectl node list must be a JSON object")
    return nodes_doc


def require_real_gpu_dev_profile(payload: dict[str, Any], label: str) -> None:
    profile = payload.get("dev_profile")
    if not isinstance(profile, dict):
        fail(f"{label} response must include dev_profile")
    if profile.get("mode") != "real" or profile.get("real_provider") is not True:
        fail(f"{label} response must use a real provider dev_profile")
    if profile.get("provider") != "kubernetes-gpu-inventory":
        fail(f"{label} response provider must be kubernetes-gpu-inventory")


def validate_live(
    args: LiveArgs,
    command_runner: Callable[[list[str]], str] = default_command_runner,
    json_getter: Callable[[str, str], tuple[int, dict[str, Any]]] = default_json_getter,
    text_getter: Callable[[str], tuple[int, str]] = default_text_getter,
) -> None:
    if not args.gateway_url.strip():
        fail("live mode requires --gateway-url")
    if not args.dcgm_metrics_url.strip():
        fail("live mode requires --dcgm-metrics-url")

    nodes_doc = load_kubernetes_nodes(args, command_runner, json_getter)
    gpu_node_count, gpu_capacity_total = summarize_kubernetes_gpu_nodes(nodes_doc)
    if gpu_node_count <= 0 or gpu_capacity_total <= 0:
        fail("no Kubernetes nodes report nvidia.com/gpu capacity")

    base_url = trim_url(args.gateway_url)
    inventory_status, inventory = json_getter(f"{base_url}/gpu-inventory", args.ani_bearer_token)
    if inventory_status != 200:
        fail(f"Core /gpu-inventory returned HTTP {inventory_status}")
    require_real_gpu_dev_profile(inventory, "Core /gpu-inventory")
    inventory_items = inventory.get("items")
    inventory_total = inventory.get("total")
    if not isinstance(inventory_items, list) or not isinstance(inventory_total, int) or inventory_total <= 0:
        fail("Core /gpu-inventory must return positive items and total")

    occupancy_status, occupancy = json_getter(f"{base_url}/gpu-inventory/occupancy", args.ani_bearer_token)
    if occupancy_status != 200:
        fail(f"Core /gpu-inventory/occupancy returned HTTP {occupancy_status}")
    require_real_gpu_dev_profile(occupancy, "Core /gpu-inventory/occupancy")
    occupancy_total = occupancy.get("total")
    if not isinstance(occupancy_total, int) or occupancy_total <= 0:
        fail("Core /gpu-inventory/occupancy must return a positive total")

    dcgm_status, metrics = text_getter(args.dcgm_metrics_url.strip())
    if dcgm_status != 200:
        fail(f"DCGM metrics endpoint returned HTTP {dcgm_status}")
    if DCGM_GPU_UTIL_METRIC not in metrics:
        fail(f"DCGM metrics must include {DCGM_GPU_UTIL_METRIC}")

    evidence = {
        "id": "gpu-inventory-live-gate",
        "profile": PROFILE,
        "status": "passed",
        "gpu_node_count": gpu_node_count,
        "gpu_capacity_total": gpu_capacity_total,
        "inventory_status": inventory_status,
        "inventory_count": inventory_total,
        "occupancy_status": occupancy_status,
        "occupancy_total": occupancy_total,
        "dcgm_metric_present": True,
    }
    if args.evidence_output.strip():
        output = Path(args.evidence_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="GPU inventory live gate YAML")
    parser.add_argument("--live", action="store_true", help="execute the human-gated live checks")
    parser.add_argument("--gateway-url", default="", help="ANI Core API base URL ending at /api/v1")
    parser.add_argument("--ani-bearer-token", default="", help="ANI Core bearer token")
    parser.add_argument("--kubectl-binary", default="kubectl", help="kubectl binary")
    parser.add_argument("--kubeconfig", default="", help="kubeconfig for live Kubernetes reads")
    parser.add_argument(
        "--kubernetes-nodes-url",
        default="",
        help="optional Kubernetes NodeList URL, for example a local kubectl proxy /api/v1/nodes endpoint",
    )
    parser.add_argument("--dcgm-metrics-url", default="", help="DCGM exporter metrics URL")
    parser.add_argument("--evidence-output", default="", help="non-sensitive evidence JSON output")
    args = parser.parse_args()

    validate_gate_path(args.gate)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        validate_live(LiveArgs(
            gateway_url=args.gateway_url,
            ani_bearer_token=args.ani_bearer_token,
            kubectl_binary=args.kubectl_binary,
            kubeconfig=args.kubeconfig,
            kubernetes_nodes_url=args.kubernetes_nodes_url,
            dcgm_metrics_url=args.dcgm_metrics_url,
            evidence_output=args.evidence_output,
        ))
        print(f"{PROFILE} live checks valid; evidence written to {args.evidence_output or '<not written>'}")
        return 0
    print("SPRINT13-GPU-INVENTORY-DCGM-A contract valid; live execution requires explicit --live arguments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
