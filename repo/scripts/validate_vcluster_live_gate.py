#!/usr/bin/env python3
"""Validate Sprint 5 M1-K8S-LIVE-A vCluster live gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/vcluster-live-gate.yaml"
REQUIRED_CHECKS = {
    "helm-install",
    "vcluster-kubeconfig",
    "kubectl-version",
    "vcluster-workload-create",
    "core-cluster-register",
    "core-proxy-version",
    "core-workloads-list",
    "vcluster-workload-cleanup",
}
REQUIRED_ENV = {"KUBECONFIG", "ANI_GATEWAY_URL", "ANI_BEARER_TOKEN"}
REQUIRED_DOC_TOKENS = ["M1-K8S-LIVE-A", "validate-vcluster-live-gate", "vCluster", "live proxy"]
PROFILE = "M1-K8S-LIVE-A"
GATE_ID = "vcluster-live-gate"
LIVE_WORKLOAD_NAME = "ani-s02-live-workload"
LIVE_WORKLOAD_IMAGE = "registry.k8s.io/pause:3.10"
REQUIRED_CHART_VERSION = "0.34.1"
PRODUCTION_SHAPED_REQUESTED_VERSION = "v1.35.0"
COMMAND_TIMEOUT_SECONDS = 120


def fail(message: str) -> None:
    raise SystemExit(f"vCluster live gate invalid: {message}")


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
    if not isinstance(tools, list) or {"helm", "vcluster", "kubectl"} - set(tools):
        fail("required_tools must include helm, vcluster and kubectl")
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
        if check["id"] == "helm-install" and f"--version {REQUIRED_CHART_VERSION}" not in check["command"]:
            fail(f"helm-install must pin vCluster chart version {REQUIRED_CHART_VERSION}")
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
    tenant_id: str
    cluster_id: str
    gateway_url: str
    ani_bearer_token: str
    kubeconfig: str = ""
    namespace: str = ""
    vcluster_server: str = ""
    proxy_server: str = ""
    helm_binary: str = "helm"
    vcluster_binary: str = "vcluster"
    kubectl_binary: str = "kubectl"
    chart_name: str = "vcluster"
    chart_repo: str = "https://charts.loft.sh"
    chart_version: str = "0.34.1"
    helm_set_values: tuple[str, ...] = ()
    production_shaped: bool = False
    work_dir: Path | None = None


class CommandRunner:
    def run(self, command: list[str], env: dict[str, str] | None = None) -> str:
        try:
            result = subprocess.run(
                command,
                env=env,
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

    def post_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str = "") -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer " + bearer_token,
        }
        if tenant_id:
            headers["x-dev-tenant-id"] = tenant_id
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT_SECONDS) as response:
                response_body = response.read().decode("utf-8")
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers.items()),
                    "body": json.loads(response_body) if response_body else {},
                }
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Core proxy request failed: HTTP {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"Core proxy request failed: {err.reason}") from err

    def get_json(self, url: str, bearer_token: str, tenant_id: str = "") -> dict[str, object]:
        headers = {
            "accept": "application/json",
            "authorization": "Bearer " + bearer_token,
        }
        if tenant_id:
            headers["x-dev-tenant-id"] = tenant_id
        request = urllib.request.Request(
            url,
            method="GET",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=COMMAND_TIMEOUT_SECONDS) as response:
                response_body = response.read().decode("utf-8")
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers.items()),
                    "body": json.loads(response_body) if response_body else {},
                }
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Core workloads request failed: HTTP {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"Core workloads request failed: {err.reason}") from err


def tenant_namespace(tenant_id: str) -> str:
    return "ani-tenant-" + tenant_id


def live_namespace(config: LiveConfig) -> str:
    if config.namespace.strip():
        return config.namespace.strip()
    return tenant_namespace(config.tenant_id)


def validate_live_config(config: LiveConfig) -> None:
    required = {
        "tenant_id": config.tenant_id,
        "cluster_id": config.cluster_id,
        "gateway_url": config.gateway_url,
        "ani_bearer_token": config.ani_bearer_token,
        "kubeconfig": config.kubeconfig,
    }
    if config.chart_repo.strip().lower() not in {"", "none", "local", "-"}:
        required["chart_version"] = config.chart_version
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    binaries = [config.helm_binary, config.kubectl_binary]
    if not config.proxy_server.strip():
        binaries.append(config.vcluster_binary)
    for binary in binaries:
        if shutil.which(binary) is None:
            fail(f"{binary} is required for --live")
    if config.production_shaped:
        validate_production_shaped_live_config(config)


def is_local_transport(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        "127.0.0.1" in lowered
        or "localhost" in lowered
        or "kubectl proxy" in lowered
        or "kubectl-proxy" in lowered
        or "port-forward" in lowered
    )


def validate_production_shaped_live_config(config: LiveConfig) -> None:
    if is_local_transport(config.gateway_url):
        fail("production-shaped live mode requires a non-local production gateway URL")
    if config.proxy_server.strip():
        fail("production-shaped live mode must not use --proxy-server")
    if not config.vcluster_server.strip():
        fail("production-shaped live mode requires --vcluster-server from metadata target")
    if is_local_transport(config.vcluster_server):
        fail("production-shaped live mode requires non-local metadata target server")


def helm_install_command(config: LiveConfig) -> list[str]:
    command = [
        config.helm_binary,
        "upgrade",
        "--install",
        config.cluster_id,
        config.chart_name,
        "--namespace",
        live_namespace(config),
        "--create-namespace",
        "--repository-config=",
        "--set",
        "sync.toHost.services.enabled=true",
    ]
    if config.chart_repo.strip().lower() not in {"", "none", "local", "-"}:
        command[5:5] = ["--repo", config.chart_repo.strip()]
    if config.chart_version.strip():
        command.extend(["--version", config.chart_version.strip()])
    for value in config.helm_set_values:
        if value.strip():
            command.extend(["--set", value.strip()])
    return command


def vcluster_print_kubeconfig_command(config: LiveConfig) -> list[str]:
    command = [
        config.vcluster_binary,
        "connect",
        config.cluster_id,
        "--namespace",
        live_namespace(config),
        "--print",
    ]
    if config.vcluster_server.strip():
        command.extend(["--server", config.vcluster_server.strip()])
    return command


def resolved_vcluster_server(config: LiveConfig, cluster_id: str) -> str:
    value = config.vcluster_server.strip()
    if not value:
        return value
    return (
        value.replace("{cluster_id}", cluster_id)
        .replace("{tenant_id}", config.tenant_id)
        .replace("{namespace}", live_namespace(config))
    )


def vcluster_connect_command(config: LiveConfig, direct_kubeconfig: str = "") -> list[str]:
    return vcluster_kubectl_command(config, ["get", "--raw", "/version"], direct_kubeconfig=direct_kubeconfig)


def vcluster_kubectl_command(config: LiveConfig, kubectl_args: list[str], direct_kubeconfig: str = "") -> list[str]:
    if direct_kubeconfig.strip():
        return [
            config.kubectl_binary,
            "--kubeconfig",
            direct_kubeconfig.strip(),
            *kubectl_args,
        ]
    if config.proxy_server.strip():
        return [
            config.kubectl_binary,
            "--server",
            config.proxy_server.strip(),
            *kubectl_args,
        ]
    command = [
        config.vcluster_binary,
        "connect",
        config.cluster_id,
        "--namespace",
        live_namespace(config),
        "--background-proxy=false",
    ]
    if config.vcluster_server.strip():
        command.extend(["--server", config.vcluster_server.strip()])
    command.extend(["--", config.kubectl_binary])
    command.extend(kubectl_args)
    return command


def workload_delete_command(config: LiveConfig, direct_kubeconfig: str = "") -> list[str]:
    return vcluster_kubectl_command(
        config,
        [
            "-n",
            "default",
            "delete",
            "deployment",
            LIVE_WORKLOAD_NAME,
            "--ignore-not-found=true",
        ],
        direct_kubeconfig=direct_kubeconfig,
    )


def workload_create_command(config: LiveConfig, direct_kubeconfig: str = "") -> list[str]:
    return vcluster_kubectl_command(
        config,
        [
            "-n",
            "default",
            "create",
            "deployment",
            LIVE_WORKLOAD_NAME,
            "--image",
            LIVE_WORKLOAD_IMAGE,
            "--replicas",
            "1",
        ],
        direct_kubeconfig=direct_kubeconfig,
    )


def host_kube_env(config: LiveConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["KUBECONFIG"] = config.kubeconfig
    return env


def kubeconfig_path(config: LiveConfig) -> Path:
    if config.work_dir is not None:
        return config.work_dir / f"{config.cluster_id}.kubeconfig"
    return Path(tempfile.gettempdir()) / f"{config.cluster_id}.kubeconfig"


def parse_version_output(output: str) -> dict[str, object]:
    json_start = output.find("{")
    if json_start < 0:
        fail("vcluster kubectl /version did not return JSON")
    try:
        value, _ = json.JSONDecoder().raw_decode(output[json_start:])
    except json.JSONDecodeError as err:
        fail(f"vcluster kubectl /version did not return JSON: {err}")
    if not isinstance(value, dict):
        fail("vcluster kubectl /version response must be a JSON object")
    return value


def write_vcluster_kubeconfig(config: LiveConfig, kubeconfig: str) -> str:
    path = kubeconfig_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kubeconfig, encoding="utf-8")
    except OSError as err:
        fail(f"vcluster kubeconfig output unusable: {err}")
    return str(path)


def create_core_cluster(config: LiveConfig, runner: CommandRunner, version: dict[str, object]) -> str:
    payload = {
        "idempotency_key": f"live-core-{config.cluster_id}",
        "name": config.cluster_id,
        "version": str(version.get("gitVersion") or version.get("major") or ""),
    }
    response = runner.post_json(
        config.gateway_url.rstrip("/") + "/k8s-clusters",
        payload,
        config.ani_bearer_token,
        config.tenant_id,
    )
    status_code = int(response.get("status_code", 0))
    if status_code < 200 or status_code >= 300:
        fail(f"Core cluster create returned HTTP {status_code}")
    body = response.get("body", {})
    if not isinstance(body, dict) or not isinstance(body.get("id"), str) or not body["id"].strip():
        fail("Core cluster create response missing id")
    return body["id"].strip()


def run_live(config: LiveConfig, runner: CommandRunner | None = None) -> dict[str, object]:
    runner = runner or CommandRunner()
    active_config = config
    direct_kubeconfig = ""
    core_cluster_id = ""
    if config.production_shaped:
        core_cluster_id = create_core_cluster(config, runner, {"gitVersion": PRODUCTION_SHAPED_REQUESTED_VERSION})
        active_config = replace(
            config,
            cluster_id=core_cluster_id,
            vcluster_server=resolved_vcluster_server(config, core_cluster_id),
        )
        kubeconfig_output = runner.run(vcluster_print_kubeconfig_command(active_config), env=host_kube_env(config))
        direct_kubeconfig = write_vcluster_kubeconfig(active_config, kubeconfig_output)
    else:
        runner.run(helm_install_command(config), env=host_kube_env(config))
    version_output = runner.run(vcluster_connect_command(active_config, direct_kubeconfig=direct_kubeconfig), env=host_kube_env(config))
    version = parse_version_output(version_output)
    if not isinstance(version, dict) or not (version.get("gitVersion") or version.get("major")):
        fail("vcluster kubectl /version response missing Kubernetes version")
    runner.run(workload_delete_command(active_config, direct_kubeconfig=direct_kubeconfig), env=host_kube_env(config))
    runner.run(workload_create_command(active_config, direct_kubeconfig=direct_kubeconfig), env=host_kube_env(config))
    try:
        if not core_cluster_id:
            core_cluster_id = create_core_cluster(config, runner, version)

        payload = {
            "idempotency_key": f"live-proxy-{core_cluster_id}-version",
            "method": "GET",
            "path": "/version",
            "query": {},
            "body": {},
        }
        proxy_response = runner.post_json(
            config.gateway_url.rstrip("/") + f"/k8s-clusters/{core_cluster_id}/proxy",
            payload,
            config.ani_bearer_token,
            config.tenant_id,
        )
        status_code = int(proxy_response.get("status_code", 0))
        if status_code < 200 or status_code >= 300:
            fail(f"Core proxy returned HTTP {status_code}")
        workloads_response = runner.get_json(
            config.gateway_url.rstrip("/") + f"/k8s-clusters/{core_cluster_id}/workloads?namespace=default&kind=Deployment",
            config.ani_bearer_token,
            config.tenant_id,
        )
        workloads_status = int(workloads_response.get("status_code", 0))
        if workloads_status < 200 or workloads_status >= 300:
            fail(f"Core workloads list returned HTTP {workloads_status}")
        workloads_body = workloads_response.get("body", {})
        if not isinstance(workloads_body, dict) or not isinstance(workloads_body.get("items"), list):
            fail("Core workloads list response missing items")
        workload_items = workloads_body["items"]
        observed_workload = None
        for item in workload_items:
            if isinstance(item, dict) and item.get("name") == LIVE_WORKLOAD_NAME:
                observed_workload = item
                break
        if observed_workload is None:
            fail(f"Core workloads list response missing {LIVE_WORKLOAD_NAME}")
        for field in ("name", "namespace", "kind", "status"):
            if not isinstance(observed_workload.get(field), str) or not observed_workload[field].strip():
                fail(f"Core workloads list item missing {field}")
        result = {
            "status": "passed",
            "core_cluster_id": core_cluster_id,
            "kubectl_version": str(version.get("gitVersion") or version.get("major")),
            "proxy_status": status_code,
            "workloads_status": workloads_status,
            "workload_count": len(workload_items),
            "workload_name": LIVE_WORKLOAD_NAME,
        }
        if config.production_shaped:
            result["production_shape"] = {
                "status": "passed",
                "transport_profile": "metadata_target_tls",
                "missing_items": [],
                "proof_items": [
                    "production_gateway",
                    "production_per_cluster_metadata_target",
                    "production_tls_and_token_management",
                ],
            }
    finally:
        runner.run(workload_delete_command(active_config, direct_kubeconfig=direct_kubeconfig), env=host_kube_env(config))
    result["cleanup"] = "deleted"
    return result


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
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="vCluster live gate YAML")
    parser.add_argument("--live", action="store_true", help="run live Helm/vCluster/kubectl/Core proxy checks")
    parser.add_argument("--tenant-id", default=os.getenv("ANI_LIVE_TENANT_ID", "tenant-a"))
    parser.add_argument("--namespace", default=os.getenv("ANI_LIVE_NAMESPACE", ""))
    parser.add_argument("--cluster-id", default=os.getenv("ANI_LIVE_K8S_CLUSTER_ID", "k8sclu-live"))
    parser.add_argument("--gateway-url", default=os.getenv("ANI_GATEWAY_URL", ""))
    parser.add_argument("--ani-bearer-token", default=os.getenv("ANI_BEARER_TOKEN", ""))
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG", ""))
    parser.add_argument("--vcluster-server", default=os.getenv("VCLUSTER_LIVE_SERVER", ""))
    parser.add_argument("--proxy-server", default=os.getenv("VCLUSTER_LIVE_PROXY_SERVER", ""))
    parser.add_argument("--helm-binary", default=os.getenv("ANI_HELM_BINARY", "helm"))
    parser.add_argument("--vcluster-binary", default=os.getenv("ANI_VCLUSTER_BINARY", "vcluster"))
    parser.add_argument("--kubectl-binary", default=os.getenv("ANI_KUBECTL_BINARY", "kubectl"))
    parser.add_argument("--chart-name", default=os.getenv("VCLUSTER_CHART_NAME", "vcluster"))
    parser.add_argument("--chart-repo", default=os.getenv("VCLUSTER_CHART_REPO", "https://charts.loft.sh"))
    parser.add_argument("--chart-version", default=os.getenv("VCLUSTER_CHART_VERSION", "0.34.1"))
    parser.add_argument("--helm-set", action="append", default=[], help="additional Helm --set value for vCluster")
    parser.add_argument("--production-shaped", action="store_true", help="require production-shaped S02 transport and write production_shape evidence")
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_VCLUSTER_LIVE_EVIDENCE_OUTPUT") or None,
        help="write --live evidence JSON to this path",
    )
    args = parser.parse_args()

    validate_gate_path(args.gate)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        config = LiveConfig(
            tenant_id=args.tenant_id,
            cluster_id=args.cluster_id,
            gateway_url=args.gateway_url,
            ani_bearer_token=args.ani_bearer_token,
            kubeconfig=args.kubeconfig,
            namespace=args.namespace,
            vcluster_server=args.vcluster_server,
            proxy_server=args.proxy_server,
            helm_binary=args.helm_binary,
            vcluster_binary=args.vcluster_binary,
            kubectl_binary=args.kubectl_binary,
            chart_name=args.chart_name,
            chart_repo=args.chart_repo,
            chart_version=args.chart_version,
            helm_set_values=tuple(args.helm_set),
            production_shaped=args.production_shaped,
        )
        validate_live_config(config)
        if args.evidence_output is not None:
            validate_evidence_output(args.evidence_output)
        result = run_live(config)
        if args.evidence_output is not None:
            write_live_evidence(Path(args.evidence_output), result)
            print(f"M1-K8S-LIVE-A live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"M1-K8S-LIVE-A live checks valid: {json.dumps(result, sort_keys=True)}")
    else:
        print("M1-K8S-LIVE-A contract valid; use --live with ANI_GATEWAY_URL and ANI_BEARER_TOKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
