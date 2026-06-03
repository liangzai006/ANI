#!/usr/bin/env python3
"""Validate Sprint 5 M1-RECONCILE-LIVE-A controller HA live gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/reconcile-ha-live-gate.yaml"
REQUIRED_CHECKS = {
    "deploy-two-reconcile-workers",
    "leader-lease-acquired",
    "leader-metrics-active",
    "kill-leader-pod",
    "follower-acquires-lease",
    "reconcile-continues-after-failover",
}
REQUIRED_ENV = {"KUBECONFIG", "DATABASE_URL", "RECONCILE_WORKER_METRICS_URL"}
REQUIRED_DOC_TOKENS = [
    "M1-RECONCILE-LIVE-A",
    "validate-reconcile-ha-live-gate",
    "control_plane_leases",
    "HA failover",
]
PROFILE = "M1-RECONCILE-LIVE-A"
GATE_ID = "reconcile-ha-live-gate"


def fail(message: str) -> None:
    raise SystemExit(f"reconcile HA live gate invalid: {message}")


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
    if document.get("status") not in {"contract", "live", "production_like"}:
        fail("status must be contract, live or production_like")
    tools = document.get("required_tools")
    if not isinstance(tools, list) or {"kubectl", "psql"} - set(tools):
        fail("required_tools must include kubectl and psql")
    endpoints = document.get("required_endpoints")
    required_endpoints = {"postgres_control_plane_leases", "reconcile_worker_metrics", "kubernetes_api"}
    if not isinstance(endpoints, list) or required_endpoints - set(endpoints):
        fail("required_endpoints must include metadata DB, reconcile metrics and Kubernetes API")
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


@dataclass(frozen=True)
class LiveConfig:
    database_url: str
    namespace: str = "ani-system"
    worker_selector: str = "app=ani-reconcile-worker"
    metrics_url: str = ""
    lease_name: str = "workload-reconcile-controller"
    kubectl_binary: str = "kubectl"
    psql_binary: str = "psql"
    psql_kubectl_namespace: str = ""
    psql_kubectl_selector: str = ""
    metrics_kubectl_raw_path: str = ""
    failover_attempts: int = 12
    failover_sleep_seconds: float = 5.0


class LiveRunner:
    def run(self, command: list[str]) -> str:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{' '.join(command)} failed: {detail}")
        return result.stdout

    def query_lease_holder(self, config: LiveConfig) -> str:
        lease_name = config.lease_name.replace("'", "''")
        query = (
            "SELECT holder_id FROM control_plane_leases "
            f"WHERE lease_name = '{lease_name}' AND lease_until > now() "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        if config.psql_kubectl_selector:
            pod = self.run(
                [
                    config.kubectl_binary,
                    "get",
                    "pods",
                    "-n",
                    config.psql_kubectl_namespace,
                    "-l",
                    config.psql_kubectl_selector,
                    "-o",
                    "jsonpath={.items[0].metadata.name}",
                ]
            ).strip()
            if not pod:
                raise RuntimeError("kubectl psql selector did not match a pod")
            return self.run(
                [
                    config.kubectl_binary,
                    "exec",
                    "-n",
                    config.psql_kubectl_namespace,
                    pod,
                    "--",
                    config.psql_binary,
                    config.database_url,
                    "-t",
                    "-A",
                    "-c",
                    query,
                ]
            ).strip()
        return self.run([config.psql_binary, config.database_url, "-t", "-A", "-c", query]).strip()

    def fetch_metrics(self, url: str) -> str:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as err:
            raise RuntimeError(f"fetch metrics failed: {err}") from err


def validate_live_config(config: LiveConfig) -> None:
    required = {
        "database_url": config.database_url,
        "namespace": config.namespace,
        "worker_selector": config.worker_selector,
        "metrics_url": config.metrics_url,
        "lease_name": config.lease_name,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    if config.failover_attempts <= 0:
        fail("failover_attempts must be greater than zero")
    if config.failover_sleep_seconds < 0:
        fail("failover_sleep_seconds cannot be negative")
    if shutil.which(config.kubectl_binary) is None:
        fail(f"{config.kubectl_binary} is required for --live")
    if config.psql_kubectl_selector:
        if not config.psql_kubectl_namespace.strip():
            fail("psql_kubectl_namespace is required when psql_kubectl_selector is set")
    elif shutil.which(config.psql_binary) is None:
        fail(f"{config.psql_binary} is required for --live")


def list_worker_pods(config: LiveConfig, runner: LiveRunner) -> dict[str, str]:
    command = [
        config.kubectl_binary,
        "get",
        "pods",
        "-n",
        config.namespace,
        "-l",
        config.worker_selector,
        "-o",
        "json",
    ]
    output = runner.run(command)
    pods: dict[str, str] = {}
    try:
        document = json.loads(output)
    except json.JSONDecodeError as err:
        fail(f"worker pod list JSON is malformed: {err}")
    for item in document.get("items", []):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        name = metadata.get("name")
        labels = metadata.get("labels", {})
        if not isinstance(labels, dict):
            continue
        identity = labels.get("ani.kubercloud.io/reconcile-identity")
        if isinstance(identity, str) and identity.strip() and isinstance(name, str) and name.strip():
            pods[identity] = name
    if len(pods) < 2:
        fail("live mode requires at least two reconcile worker pods with reconcile identity labels")
    return pods


def assert_metrics_exposed(metrics: str) -> None:
    required = [
        "ani_workload_reconcile_ticks_total",
        "ani_workload_reconcile_successes_total",
        "ani_workload_reconcile_failures_total",
    ]
    missing = [name for name in required if name not in metrics]
    if missing:
        fail(f"metrics endpoint missing {', '.join(missing)}")


def fetch_live_metrics(config: LiveConfig, runner: LiveRunner) -> str:
    if config.metrics_kubectl_raw_path:
        return runner.run([config.kubectl_binary, "get", "--raw", config.metrics_kubectl_raw_path])
    return runner.fetch_metrics(config.metrics_url)


def wait_for_new_leader(config: LiveConfig, runner: LiveRunner, initial_leader: str) -> str:
    for _ in range(config.failover_attempts):
        holder = runner.query_lease_holder(config)
        if holder and holder != initial_leader:
            return holder
        if config.failover_sleep_seconds:
            time.sleep(config.failover_sleep_seconds)
    fail("follower did not acquire reconcile leader lease after deleting leader pod")


def run_live(config: LiveConfig, runner: LiveRunner | None = None) -> dict[str, object]:
    runner = runner or LiveRunner()
    pods = list_worker_pods(config, runner)
    initial_leader = runner.query_lease_holder(config)
    if not initial_leader:
        fail("control_plane_leases has no active reconcile leader holder")
    leader_pod = pods.get(initial_leader)
    if not leader_pod:
        fail(f"active leader {initial_leader} does not match observed reconcile worker pods")

    assert_metrics_exposed(fetch_live_metrics(config, runner))
    runner.run([config.kubectl_binary, "delete", "pod", leader_pod, "-n", config.namespace])
    new_leader = wait_for_new_leader(config, runner, initial_leader)
    assert_metrics_exposed(fetch_live_metrics(config, runner))
    return {
        "status": "passed",
        "namespace": config.namespace,
        "worker_selector": config.worker_selector,
        "lease_name": config.lease_name,
        "metrics_url": config.metrics_url,
        "metrics_kubectl_raw_path": config.metrics_kubectl_raw_path,
        "initial_leader": initial_leader,
        "new_leader": new_leader,
        "deleted_pod": leader_pod,
    }


def write_live_evidence(path: Path, evidence: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        identified = {**evidence, "id": GATE_ID, "profile": PROFILE}
        path.write_text(json.dumps(identified, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as err:
        fail(f"evidence output unusable: {err}")


def validate_gate_path(path: str) -> None:
    if not path.strip():
        fail("gate path must not be empty")
    if path != path.strip():
        fail("gate path must not contain surrounding whitespace")


def validate_evidence_output(path: str) -> None:
    if not path.strip():
        fail("evidence_output must not be empty")
    if path != path.strip():
        fail("evidence_output must not contain surrounding whitespace")
    output_path = Path(path)
    if output_path.is_dir():
        fail("evidence_output must be a file path")
    if output_path.parent.exists() and not output_path.parent.is_dir():
        fail("evidence_output parent must be a directory")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        fail("evidence_output parent must be a directory")
    try:
        if output_path.parent.stat().st_mode & 0o222 == 0:
            fail("evidence_output parent must be writable")
        if output_path.exists() and output_path.stat().st_mode & 0o222 == 0:
            fail("evidence_output must be writable")
    except OSError:
        fail("evidence_output must be writable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="reconcile HA live gate YAML")
    parser.add_argument("--live", action="store_true", help="run live Kubernetes/lease/metrics failover checks")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--namespace", default=os.getenv("RECONCILE_WORKER_NAMESPACE", "ani-system"))
    parser.add_argument("--worker-selector", default=os.getenv("RECONCILE_WORKER_SELECTOR", "app=ani-reconcile-worker"))
    parser.add_argument("--metrics-url", default=os.getenv("RECONCILE_WORKER_METRICS_URL", ""))
    parser.add_argument("--metrics-kubectl-raw-path", default=os.getenv("RECONCILE_WORKER_METRICS_KUBECTL_RAW_PATH", ""))
    parser.add_argument("--lease-name", default=os.getenv("WORKLOAD_RECONCILE_LEADER_LEASE_NAME", "workload-reconcile-controller"))
    parser.add_argument("--psql-binary", default=os.getenv("PSQL_BINARY", "psql"))
    parser.add_argument("--psql-kubectl-namespace", default=os.getenv("RECONCILE_PSQL_KUBECTL_NAMESPACE", ""))
    parser.add_argument("--psql-kubectl-selector", default=os.getenv("RECONCILE_PSQL_KUBECTL_SELECTOR", ""))
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_RECONCILE_HA_LIVE_EVIDENCE_OUTPUT") or None,
        help="write --live evidence JSON to this path",
    )
    args = parser.parse_args()

    validate_gate_path(args.gate)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        config = LiveConfig(
            database_url=args.database_url,
            namespace=args.namespace,
            worker_selector=args.worker_selector,
            metrics_url=args.metrics_url,
            metrics_kubectl_raw_path=args.metrics_kubectl_raw_path,
            lease_name=args.lease_name,
            psql_binary=args.psql_binary,
            psql_kubectl_namespace=args.psql_kubectl_namespace,
            psql_kubectl_selector=args.psql_kubectl_selector,
        )
        validate_live_config(config)
        if args.evidence_output is not None:
            validate_evidence_output(args.evidence_output)
        result = run_live(config)
        if args.evidence_output is not None:
            write_live_evidence(Path(args.evidence_output), result)
            print(f"M1-RECONCILE-LIVE-A live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"M1-RECONCILE-LIVE-A live checks valid: {json.dumps(result, sort_keys=True)}")
    else:
        print("M1-RECONCILE-LIVE-A contract valid; use --live with DATABASE_URL and RECONCILE_WORKER_METRICS_URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
