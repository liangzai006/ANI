#!/usr/bin/env python3
"""Validate Sprint 5 M1-K8S-LIVE-C vCluster upgrade live gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/vcluster-upgrade-live-gate.yaml"
REQUIRED_CHECKS = {
    "core-cluster-register",
    "dev-hostpath-pv",
    "core-upgrade-cluster",
    "helm-values-target-version",
    "kubectl-version-after-upgrade",
    "local-proxy-after-upgrade",
    "core-proxy-version-after-upgrade",
}
REQUIRED_ENV = {"KUBECONFIG", "ANI_GATEWAY_URL", "ANI_BEARER_TOKEN"}
REQUIRED_DOC_TOKENS = [
    "M1-K8S-LIVE-C",
    "validate-vcluster-upgrade-live-gate",
    "vCluster upgrade",
    "controlPlane.distro.k8s.version",
]
PROFILE = "M1-K8S-LIVE-C"
GATE_ID = "vcluster-upgrade-live-gate"


def fail(message: str) -> None:
    raise SystemExit(f"vCluster upgrade live gate invalid: {message}")


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
    endpoints = document.get("required_endpoints")
    required_endpoints = {"ani_gateway_api_v1", "kubernetes_api", "vcluster_helm_release"}
    if not isinstance(endpoints, list) or required_endpoints - set(endpoints):
        fail("required_endpoints must include Gateway API, Kubernetes API and vCluster Helm release")
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
    tenant_id: str
    cluster_id: str
    gateway_url: str
    ani_bearer_token: str
    kubeconfig: str = ""
    target_version: str = "v1.31.0"
    initial_version: str = "v1.30.0"
    vcluster_server: str = ""
    local_proxy_port: int = 18002
    helm_binary: str = "helm"
    vcluster_binary: str = "vcluster"
    kubectl_binary: str = "kubectl"
    work_dir: Path | None = None


class LiveRunner:
    def run(self, command: list[str], env: dict[str, str] | None = None) -> str:
        result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{' '.join(command)} failed: {detail}")
        return result.stdout

    def start(self, command: list[str], env: dict[str, str] | None = None) -> subprocess.Popen[str]:
        return subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def wait_url(self, url: str) -> None:
        deadline = time.monotonic() + 60
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    if 200 <= response.status < 300:
                        return
            except (OSError, urllib.error.URLError) as err:
                last_error = err
            time.sleep(1)
        raise RuntimeError(f"waiting for {url} failed: {last_error}")

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        bearer_token: str,
        tenant_id: str = "",
    ) -> dict[str, object]:
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
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"POST {url} returned HTTP {err.code}: {detail}") from err


def tenant_namespace(tenant_id: str) -> str:
    return "ani-tenant-" + tenant_id


def validate_live_config(config: LiveConfig) -> None:
    required = {
        "tenant_id": config.tenant_id,
        "cluster_id": config.cluster_id,
        "gateway_url": config.gateway_url,
        "ani_bearer_token": config.ani_bearer_token,
        "kubeconfig": config.kubeconfig,
        "target_version": config.target_version,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    for binary in (config.helm_binary, config.vcluster_binary, config.kubectl_binary):
        if shutil.which(binary) is None:
            fail(f"{binary} is required for --live")


def helm_values_command(config: LiveConfig, cluster_id: str) -> list[str]:
    return [
        config.helm_binary,
        "get",
        "values",
        cluster_id,
        "--namespace",
        tenant_namespace(config.tenant_id),
        "-a",
        "-o",
        "json",
    ]


def vcluster_connect_command(config: LiveConfig, cluster_id: str) -> list[str]:
    command = [
        config.vcluster_binary,
        "connect",
        cluster_id,
        "--namespace",
        tenant_namespace(config.tenant_id),
        "--background-proxy=false",
    ]
    if config.vcluster_server.strip():
        command.extend(["--server", config.vcluster_server.strip()])
    command.extend(["--", config.kubectl_binary, "get", "--raw", "/version"])
    return command


def local_proxy_command(config: LiveConfig, cluster_id: str) -> list[str]:
    command = [
        config.vcluster_binary,
        "connect",
        cluster_id,
        "--namespace",
        tenant_namespace(config.tenant_id),
        "--background-proxy=false",
    ]
    if config.vcluster_server.strip():
        command.extend(["--server", config.vcluster_server.strip()])
    command.extend(
        [
            "--",
            config.kubectl_binary,
            "proxy",
            "--address=127.0.0.1",
            f"--port={config.local_proxy_port}",
            "--accept-hosts=.*",
        ]
    )
    return command


def kubeconfig_path(config: LiveConfig, cluster_id: str) -> Path:
    if config.work_dir is not None:
        return config.work_dir / f"{cluster_id}-upgrade.kubeconfig"
    return Path(tempfile.gettempdir()) / f"{cluster_id}-upgrade.kubeconfig"


def host_kube_env(config: LiveConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["KUBECONFIG"] = config.kubeconfig
    return env


def nested_value(document: dict[str, Any], path: list[str]) -> Any:
    value: Any = document
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def assert_core_upgrade_response(response: dict[str, Any], target_version: str) -> None:
    if response.get("version") != target_version:
        fail("Core upgrade response version must match target_version")
    profile = response.get("dev_profile", {})
    if not isinstance(profile, dict) or profile.get("mode") != "real" or not profile.get("real_provider"):
        fail("Core upgrade response must be provider-backed real dev profile")
    if response.get("state") not in {"running", "upgrading"}:
        fail("Core upgrade response state must be running or upgrading")


def assert_core_create_response(response: dict[str, Any]) -> str:
    cluster_id = response.get("id")
    if not isinstance(cluster_id, str) or not cluster_id.strip():
        fail("Core create response missing cluster id")
    profile = response.get("dev_profile", {})
    if not isinstance(profile, dict) or profile.get("mode") != "real" or not profile.get("real_provider"):
        fail("Core create response must be provider-backed real dev profile")
    if response.get("state") not in {"running", "creating"}:
        fail("Core create response state must be running or creating")
    return cluster_id.strip()


def assert_helm_values_target_version(raw_values: str, target_version: str) -> None:
    try:
        values = json.loads(raw_values)
    except json.JSONDecodeError as err:
        fail(f"helm get values did not return JSON: {err}")
    if not isinstance(values, dict):
        fail("helm get values must return a JSON object")
    actual = nested_value(values, ["controlPlane", "distro", "k8s", "version"])
    if actual != target_version:
        fail(f"helm values target version = {actual!r}, want {target_version!r}")


def parse_json_object_from_output(output: str, label: str) -> dict[str, Any]:
    json_start = output.find("{")
    if json_start < 0:
        fail(f"{label} did not return JSON")
    try:
        value, _ = json.JSONDecoder().raw_decode(output[json_start:])
    except json.JSONDecodeError as err:
        fail(f"{label} did not return JSON: {err}")
    if not isinstance(value, dict):
        fail(f"{label} response must be a JSON object")
    return value


def assert_kubernetes_version(raw_version: str, target_version: str) -> None:
    version = parse_json_object_from_output(raw_version, "kubectl /version")
    if not isinstance(version, dict) or not (version.get("gitVersion") or version.get("major")):
        fail("kubectl /version response missing Kubernetes version")
    git_version = str(version.get("gitVersion") or "")
    if git_version and not git_version.startswith(target_version):
        fail(f"kubectl gitVersion = {git_version}, want prefix {target_version}")


def upgrade_hostpath_pv_manifest(config: LiveConfig, cluster_id: str) -> str:
    namespace = tenant_namespace(config.tenant_id)
    pv_name = "ani-vcu-" + cluster_id
    pvc_name = "data-" + cluster_id + "-0"
    path = "/var/local/ani-pv/vcluster-upgrade/" + cluster_id
    return "\n".join(
        [
            "apiVersion: v1",
            "kind: PersistentVolume",
            "metadata:",
            f"  name: {pv_name}",
            "  labels:",
            "    app.kubernetes.io/part-of: ani-platform",
            "    app.kubernetes.io/managed-by: ani-core",
            "    ani.kubercloud.io/live-gate: m1-k8s-live-c",
            "spec:",
            "  capacity:",
            "    storage: 20Gi",
            "  accessModes:",
            "    - ReadWriteOnce",
            "  persistentVolumeReclaimPolicy: Retain",
            "  volumeMode: Filesystem",
            "  claimRef:",
            f"    namespace: {namespace}",
            f"    name: {pvc_name}",
            "  hostPath:",
            f"    path: {path}",
            "    type: DirectoryOrCreate",
            "",
        ]
    )


def apply_upgrade_hostpath_pv(config: LiveConfig, cluster_id: str, runner: LiveRunner) -> None:
    manifest_path = kubeconfig_path(config, cluster_id).with_suffix(".pv.yaml")
    manifest_path.write_text(upgrade_hostpath_pv_manifest(config, cluster_id), encoding="utf-8")
    runner.run([config.kubectl_binary, "--kubeconfig", config.kubeconfig, "apply", "-f", str(manifest_path)], env=host_kube_env(config))


def run_live(config: LiveConfig, runner: LiveRunner | None = None) -> dict[str, object]:
    runner = runner or LiveRunner()
    create_response = runner.post_json(
        config.gateway_url.rstrip("/") + "/k8s-clusters",
        {
            "idempotency_key": f"live-upgrade-create-{config.cluster_id}",
            "name": config.cluster_id,
            "version": config.initial_version,
        },
        config.ani_bearer_token,
        config.tenant_id,
    )
    core_cluster_id = assert_core_create_response(create_response)
    apply_upgrade_hostpath_pv(config, core_cluster_id, runner)

    upgrade_payload = {
        "idempotency_key": f"live-upgrade-{core_cluster_id}-{config.target_version}",
        "version": config.target_version,
    }
    upgrade_response = runner.post_json(
        config.gateway_url.rstrip("/") + f"/k8s-clusters/{core_cluster_id}/upgrade",
        upgrade_payload,
        config.ani_bearer_token,
        config.tenant_id,
    )
    assert_core_upgrade_response(upgrade_response, config.target_version)

    assert_helm_values_target_version(runner.run(helm_values_command(config, core_cluster_id), env=host_kube_env(config)), config.target_version)
    version_output = runner.run(vcluster_connect_command(config, core_cluster_id), env=host_kube_env(config))
    assert_kubernetes_version(version_output, config.target_version)

    proxy_process = runner.start(local_proxy_command(config, core_cluster_id), env=host_kube_env(config))
    try:
        runner.wait_url(f"http://127.0.0.1:{config.local_proxy_port}/version")
        proxy_response = runner.post_json(
            config.gateway_url.rstrip("/") + f"/k8s-clusters/{core_cluster_id}/proxy",
            {
                "idempotency_key": f"live-upgrade-proxy-{core_cluster_id}-{config.target_version}",
                "method": "GET",
                "path": "/version",
                "query": {},
                "body": {},
            },
            config.ani_bearer_token,
            config.tenant_id,
        )
        status_code = int(proxy_response.get("status_code", 0))
        if status_code < 200 or status_code >= 300:
            fail(f"Core proxy returned HTTP {status_code} after upgrade")
    finally:
        proxy_process.terminate()
        try:
            proxy_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proxy_process.kill()
            proxy_process.wait(timeout=5)
    return {
        "status": "passed",
        "core_cluster_id": core_cluster_id,
        "target_version": config.target_version,
        "kubectl_version": config.target_version,
        "proxy_status": status_code,
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
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="vCluster upgrade live gate YAML")
    parser.add_argument("--live", action="store_true", help="run live Core upgrade/Helm/vCluster/kubectl/Core proxy checks")
    parser.add_argument("--tenant-id", default=os.getenv("ANI_LIVE_TENANT_ID", "tenant-a"))
    parser.add_argument("--cluster-id", default=os.getenv("ANI_LIVE_K8S_CLUSTER_ID", "k8sclu-live"))
    parser.add_argument("--gateway-url", default=os.getenv("ANI_GATEWAY_URL", ""))
    parser.add_argument("--ani-bearer-token", default=os.getenv("ANI_BEARER_TOKEN", ""))
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG", ""))
    parser.add_argument("--initial-version", default=os.getenv("ANI_LIVE_K8S_INITIAL_VERSION", "v1.30.0"))
    parser.add_argument("--target-version", default=os.getenv("ANI_LIVE_K8S_UPGRADE_TARGET_VERSION", "v1.31.0"))
    parser.add_argument("--vcluster-server", default=os.getenv("VCLUSTER_LIVE_SERVER", ""))
    parser.add_argument("--local-proxy-port", type=int, default=int(os.getenv("ANI_VCLUSTER_UPGRADE_LOCAL_PROXY_PORT", "18002")))
    parser.add_argument("--helm-binary", default=os.getenv("ANI_HELM_BINARY", "helm"))
    parser.add_argument("--vcluster-binary", default=os.getenv("ANI_VCLUSTER_BINARY", "vcluster"))
    parser.add_argument("--kubectl-binary", default=os.getenv("ANI_KUBECTL_BINARY", "kubectl"))
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_VCLUSTER_UPGRADE_LIVE_EVIDENCE_OUTPUT") or None,
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
            target_version=args.target_version,
            initial_version=args.initial_version,
            vcluster_server=args.vcluster_server,
            local_proxy_port=args.local_proxy_port,
            helm_binary=args.helm_binary,
            vcluster_binary=args.vcluster_binary,
            kubectl_binary=args.kubectl_binary,
        )
        validate_live_config(config)
        if args.evidence_output is not None:
            validate_evidence_output(args.evidence_output)
        result = run_live(config)
        if args.evidence_output is not None:
            write_live_evidence(Path(args.evidence_output), result)
            print(f"M1-K8S-LIVE-C live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"M1-K8S-LIVE-C live checks valid: {json.dumps(result, sort_keys=True)}")
    else:
        print("M1-K8S-LIVE-C contract valid; use --live with ANI_GATEWAY_URL and ANI_BEARER_TOKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
