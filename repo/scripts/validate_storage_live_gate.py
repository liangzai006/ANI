#!/usr/bin/env python3
"""Validate Sprint 13 storage snapshot/mount-target live gate contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/storage-live-gate.yaml"
PROFILE = "SPRINT13-STORAGE-ROOK-CEPH-A"
GATE_ID = "storage-live-gate"
COMMAND_TIMEOUT_SECONDS = 120
REQUIRED_CHECKS = {
    "core-volume-create",
    "core-volume-snapshot-create",
    "core-volume-snapshots-list",
    "core-filesystem-create",
    "core-mount-targets-list",
}
REQUIRED_DOC_TOKENS = [
    "SPRINT13-STORAGE-ROOK-CEPH-A-TRACK",
    "validate-storage-live-gate",
    "Rook-Ceph",
    "LIVE PENDING",
]


def fail(message: str) -> None:
    raise SystemExit(f"storage live gate invalid: {message}")


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


@dataclass(frozen=True)
class LiveConfig:
    gateway_url: str
    ani_bearer_token: str
    tenant_id: str = "tenant-a"
    namespace: str = "ani-tenant-tenant-a"
    storage_class: str = "ani-rbd-ssd"
    snapshot_class: str = "csi-rbdplugin-snapclass"
    filesystem_backend: str = "nfs"
    volume_name: str = "ani-s03-live-volume"
    snapshot_name: str = "ani-s03-live-snapshot"
    filesystem_name: str = "ani-s03-live-filesystem"
    kubeconfig: str = ""
    kubectl_binary: str = "kubectl"
    evidence_output: Path | None = None


class CommandRunner:
    def run(self, command: list[str], input_text: str | None = None) -> str:
        try:
            result = subprocess.run(
                command,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"{' '.join(command)} timed out after {COMMAND_TIMEOUT_SECONDS}s") from err
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{' '.join(command)} failed: {detail}")
        return result.stdout


class HTTPClient:
    def request(self, method: str, url: str, bearer_token: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        payload = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {bearer_token}"}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            detail = raw or err.reason
            raise RuntimeError(f"{method} {url} failed: HTTP {err.code} {detail}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"{method} {url} failed: {err.reason}") from err


def kubernetes_name(prefix: str, value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9.-]+", "-", value.strip()).lower().strip("-.")
    if not clean:
        clean = "resource"
    return (prefix + "-" + clean)[:63].rstrip("-.")


def kubectl(config: LiveConfig, args: list[str]) -> list[str]:
    command = [config.kubectl_binary]
    if config.kubeconfig.strip():
        command.extend(["--kubeconfig", config.kubeconfig.strip()])
    command.extend(args)
    return command


def validate_live_config(config: LiveConfig) -> None:
    required = {
        "gateway_url": config.gateway_url,
        "ani_bearer_token": config.ani_bearer_token,
        "tenant_id": config.tenant_id,
        "namespace": config.namespace,
        "storage_class": config.storage_class,
        "snapshot_class": config.snapshot_class,
        "filesystem_backend": config.filesystem_backend,
        "volume_name": config.volume_name,
        "snapshot_name": config.snapshot_name,
        "filesystem_name": config.filesystem_name,
        "evidence_output": str(config.evidence_output or ""),
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    if config.filesystem_backend not in {"nfs", "cephfs"}:
        fail("filesystem_backend must be nfs or cephfs")
    if shutil.which(config.kubectl_binary) is None:
        fail(f"{config.kubectl_binary} is required for --live")


def core_url(config: LiveConfig, path: str) -> str:
    return config.gateway_url.rstrip("/") + path


def require_status(name: str, status: int, expected: set[int]) -> None:
    if status not in expected:
        raise RuntimeError(f"{name} returned HTTP {status}, want {sorted(expected)}")


def require_object_id(name: str, document: dict[str, object]) -> str:
    value = document.get("id")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{name} response missing id")
    return value


def require_items(name: str, document: dict[str, object]) -> list[object]:
    items = document.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"{name} response missing items")
    return items


def run_live(
    config: LiveConfig,
    http_client: HTTPClient | Any | None = None,
    runner: CommandRunner | Any | None = None,
) -> dict[str, object]:
    validate_live_config(config)
    http_client = http_client or HTTPClient()
    runner = runner or CommandRunner()

    runner.run(kubectl(config, ["get", "namespace", config.namespace, "-o", "json"]))
    runner.run(kubectl(config, ["get", "sc", config.storage_class, "-o", "json"]))
    runner.run(kubectl(config, ["get", "volumesnapshotclass", config.snapshot_class, "-o", "json"]))
    runner.run(kubectl(config, ["get", "crd", "volumesnapshots.snapshot.storage.k8s.io", "-o", "json"]))

    resource_ids: dict[str, str] = {}
    try:
        volume_status, volume = http_client.request(
            "POST",
            core_url(config, "/volumes"),
            config.ani_bearer_token,
            {
                "idempotency_key": "s03-live-volume",
                "name": config.volume_name,
                "size_gib": 1,
                "storage_class": config.storage_class,
            },
        )
        require_status("volume create", volume_status, {200, 201})
        resource_ids["volume"] = require_object_id("volume create", volume)

        snapshot_status, snapshot_task = http_client.request(
            "POST",
            core_url(config, f"/volumes/{resource_ids['volume']}/snapshots"),
            config.ani_bearer_token,
            {
                "idempotency_key": "s03-live-snapshot",
                "name": config.snapshot_name,
                "description": "Sprint 13 S03 live gate snapshot",
            },
        )
        require_status("snapshot create", snapshot_status, {202})
        snapshot_doc = snapshot_task.get("result")
        if isinstance(snapshot_doc, dict):
            snapshot_value = snapshot_doc.get("snapshot")
            if isinstance(snapshot_value, dict):
                snapshot_id = snapshot_value.get("id")
                if isinstance(snapshot_id, str) and snapshot_id.strip():
                    resource_ids["snapshot"] = snapshot_id

        snapshots_status, snapshots = http_client.request(
            "GET",
            core_url(config, f"/volumes/{resource_ids['volume']}/snapshots"),
            config.ani_bearer_token,
        )
        require_status("snapshot list", snapshots_status, {200})
        snapshot_items = require_items("snapshot list", snapshots)

        filesystem_status, filesystem = http_client.request(
            "POST",
            core_url(config, "/filesystems"),
            config.ani_bearer_token,
            {
                "idempotency_key": "s03-live-filesystem",
                "name": config.filesystem_name,
                "protocol": config.filesystem_backend,
                "size_gib": 1,
            },
        )
        require_status("filesystem create", filesystem_status, {200, 201})
        resource_ids["filesystem"] = require_object_id("filesystem create", filesystem)

        targets_status, targets = http_client.request(
            "GET",
            core_url(config, f"/filesystems/{resource_ids['filesystem']}/mount-targets"),
            config.ani_bearer_token,
        )
        require_status("mount-target list", targets_status, {200})
        target_items = require_items("mount-target list", targets)
        if target_items:
            first_target = target_items[0]
            if isinstance(first_target, dict):
                mount_target_id = first_target.get("id")
                if isinstance(mount_target_id, str) and mount_target_id.strip():
                    resource_ids["mount_target"] = mount_target_id

        evidence = {
            "id": GATE_ID,
            "profile": PROFILE,
            "status": "passed",
            "tenant_id": config.tenant_id,
            "namespace": config.namespace,
            "storage_class": config.storage_class,
            "snapshot_class": config.snapshot_class,
            "filesystem_backend": config.filesystem_backend,
            "volume_status": volume_status,
            "snapshot_status": snapshot_status,
            "snapshot_count": len(snapshot_items),
            "filesystem_status": filesystem_status,
            "mount_target_count": len(target_items),
            "cleanup": "pending",
        }
    finally:
        cleanup_storage_resources(config, runner, resource_ids)

    evidence["cleanup"] = "deleted"
    if config.evidence_output is not None:
        config.evidence_output.parent.mkdir(parents=True, exist_ok=True)
        config.evidence_output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def cleanup_storage_resources(config: LiveConfig, runner: CommandRunner | Any, resource_ids: dict[str, str]) -> None:
    delete_args: list[str] = []
    if snapshot_id := resource_ids.get("snapshot"):
        delete_args.extend(["volumesnapshot", kubernetes_name("snap", snapshot_id)])
    if filesystem_id := resource_ids.get("filesystem"):
        if mount_target_id := resource_ids.get("mount_target"):
            delete_args.extend(["svc", kubernetes_name("mt", mount_target_id)])
        delete_args.extend(["pvc", kubernetes_name("fs", filesystem_id)])
    if volume_id := resource_ids.get("volume"):
        delete_args.extend(["pvc", kubernetes_name("vol", volume_id)])
    if delete_args:
        runner.run(kubectl(config, ["delete", "-n", config.namespace, *delete_args, "--ignore-not-found=true"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="storage live gate YAML")
    parser.add_argument("--live", action="store_true", help="run human-approved live Core storage checks")
    parser.add_argument("--gateway-url", default=os.getenv("ANI_GATEWAY_URL", ""))
    parser.add_argument("--ani-bearer-token", default=os.getenv("ANI_BEARER_TOKEN", ""))
    parser.add_argument("--tenant-id", default=os.getenv("ANI_LIVE_TENANT_ID", "tenant-a"))
    parser.add_argument("--namespace", default=os.getenv("ANI_STORAGE_LIVE_NAMESPACE", "ani-tenant-tenant-a"))
    parser.add_argument("--storage-class", default=os.getenv("ANI_STORAGE_LIVE_STORAGE_CLASS", "ani-rbd-ssd"))
    parser.add_argument("--snapshot-class", default=os.getenv("ANI_STORAGE_LIVE_SNAPSHOT_CLASS", "csi-rbdplugin-snapclass"))
    parser.add_argument("--filesystem-backend", default=os.getenv("ANI_STORAGE_LIVE_FILESYSTEM_BACKEND", "nfs"))
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG", ""))
    parser.add_argument("--kubectl-binary", default=os.getenv("ANI_KUBECTL_BINARY", "kubectl"))
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_STORAGE_LIVE_EVIDENCE_OUTPUT") or None,
        help="write --live evidence JSON to this path",
    )
    args = parser.parse_args()

    validate_gate_path(args.gate)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        result = run_live(
            LiveConfig(
                gateway_url=args.gateway_url,
                ani_bearer_token=args.ani_bearer_token,
                tenant_id=args.tenant_id,
                namespace=args.namespace,
                storage_class=args.storage_class,
                snapshot_class=args.snapshot_class,
                filesystem_backend=args.filesystem_backend,
                kubeconfig=args.kubeconfig,
                kubectl_binary=args.kubectl_binary,
                evidence_output=Path(args.evidence_output) if args.evidence_output else None,
            )
        )
        if args.evidence_output:
            print(f"SPRINT13-STORAGE-ROOK-CEPH-A live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"SPRINT13-STORAGE-ROOK-CEPH-A live checks valid: {json.dumps(result, sort_keys=True)}")
        return 0
    print("SPRINT13-STORAGE-ROOK-CEPH-A contract valid; live execution is human-gated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
