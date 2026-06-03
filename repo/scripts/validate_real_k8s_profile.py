#!/usr/bin/env python3
"""Validate Sprint 5 REAL-K8S-LAB-A real provider lab gate."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
PROFILE = ROOT / "deploy/real-k8s-lab/profile.yaml"
REQUIRED_COMPONENTS = {"kubernetes", "kube_ovn", "kubevirt", "vcluster"}
REQUIRED_CONTRACT_GATE_IDS = {
    "vcluster-live-gate",
    "vcluster-upgrade-live-gate",
    "k8s-node-pool-live-gate",
    "kubeovn-network-live-gate",
    "kubevirt-vm-live-gate",
    "reconcile-ha-live-gate",
    "kms-sm4-live-gate",
    "secrets-live-gate",
}
SUPPORTED_LIVE_PASS_CONDITIONS = {
    "at_least_minimum_nodes_ready",
    "at_least_one_storageclass",
    "at_least_one_item",
    "crd_exists",
    "stdout_yes",
}
SUPPORTED_PROFILE_PASS_CONDITIONS = SUPPORTED_LIVE_PASS_CONDITIONS | {
    "contract_gate_exists",
}
SUPPORTED_CONTRACT_GATE_MANIFEST_PASS_CONDITIONS = {
    "active_holder_id_exists",
    "active_leader_pod_deleted",
    "at_least_one_kubevirt_cr_available",
    "at_least_two_workers_with_unique_reconcile_identity_labels",
    "binding_record_created",
    "ciphertext_differs_from_plaintext",
    "command_succeeds",
    "console_websocket_session_established",
    "content_matches_written_sealed_bytes",
    "controlPlane.distro.k8s.version_matches_target",
    "external_load_balancer_ip_reachable_from_all_real_lab_nodes",
    "gpu_pod_scheduled_on_workload_cluster",
    "guest_console_logs_include_secret_volume_values",
    "holder_id_changes_from_deleted_leader_identity",
    "http_2xx",
    "http_2xx_after_upgrade",
    "http_2xx_response_has_cluster_id",
    "json_git_version_matches_target",
    "json_has_kubernetes_version",
    "kubeovn_subnet_exists_and_ready_or_observable",
    "kubeovn_vpc_and_subnet_crds_exist",
    "kubeovn_vpc_exists_and_ready_or_observable",
    "kubevirt_accepts_secret_volume_manifest",
    "kubevirt_vm_and_vmi_crds_exist",
    "networkpolicy_exists_in_tenant_namespace",
    "plaintext_matches_original",
    "pod_logs_include_env_secret_value",
    "pod_logs_include_file_secret_value",
    "reconcile_prometheus_counters_exposed_after_failover",
    "reconcile_prometheus_counters_exposed_before_failover",
    "response_dev_profile_real_provider",
    "response_dev_profile_real_provider_and_version_matches_target",
    "response_has_kms_sm4_sealed_uri_and_unseal_token",
    "response_has_unseal_token",
    "secret_data_matches_core_request",
    "service_type_load_balancer_or_observable",
    "spec_replicas_and_gpu_intent_match_create_request",
    "spec_replicas_and_available_status_match_scaled_node_count",
    "spec_replicas_match_scaled_node_count",
    "matching_machineset_replicas_ready_available_and_up_to_date",
    "machine_count_node_refs_provider_ids_internal_ips_ready_and_available",
    "machine_infrastructure_refs_resolve_to_ready_kubevirtmachines",
    "capk_virtualmachines_and_instances_running_ready",
    "stdout_contains_kubeconfig",
    "stdout_contains_kubeconfig_after_upgrade",
    "virtualmachine_deleted",
    "virtualmachine_exists_in_tenant_namespace",
    "virtualmachineinstance_ready_or_running",
    "virtualmachineinstance_stopped",
    "vcluster_connect_runs_kubectl_with_generated_kubeconfig",
    "vnc_websocket_session_established",
}
JSON_OUTPUT_PASS_CONDITIONS = SUPPORTED_LIVE_PASS_CONDITIONS - {"stdout_yes"}
COMPONENT_SUMMARY_STATUSES = {
    "component_live",
    "component_live_failed",
    "component_live_preflight_passed",
    "component_live_preflight_failed",
}
REQUIRED_DOC_TOKENS = [
    "REAL-K8S-LAB-A",
    "validate-real-k8s-profile",
    "Kube-OVN",
    "KubeVirt",
    "vCluster",
    "local profile",
]
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
KUBERNETES_NAMESPACE_NAME_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
KUBERNETES_SYSTEM_NAMESPACES = {"kube-node-lease", "kube-public", "kube-system"}
COMPONENT_LIVE_RECORD_DIR = "development-records/live"
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|BEARER)[A-Za-z0-9_]*|token|secret|password|credential)\s*=\s*([^\s,;]+)",
    re.IGNORECASE,
)
AUTHORIZATION_BEARER_PATTERN = re.compile(r"\b(Authorization:\s*Bearer\s+)([^\s,;]+)", re.IGNORECASE)


def fail(message: str) -> None:
    raise SystemExit(f"real k8s profile invalid: {message}")


def redact_sensitive_text(text: str) -> str:
    redacted = SENSITIVE_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return AUTHORIZATION_BEARER_PATTERN.sub(lambda match: f"{match.group(1)}<redacted>", redacted)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing {display_path(path)}")
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as err:
        fail(f"profile unreadable: {display_path(path)}: {err}")
    except yaml.YAMLError as err:
        fail(f"profile malformed: {display_path(path)}: {err}")
    if not isinstance(data, dict):
        fail(f"{display_path(path)} must be a YAML object")
    return data


def validate_profile_live_check_command(component_name: str, command: str, pass_condition: str, makefile: str) -> None:
    if pass_condition == "contract_gate_exists":
        if not command.startswith("make validate-"):
            fail(f"{component_name} live check command must be a make validate-* target")
        target = command.removeprefix("make ").strip()
        if f"{target}:" not in makefile:
            fail(f"{component_name} live check command target {target} missing from Makefile")
        return
    if not command.startswith("kubectl "):
        fail(f"{component_name} live check command must start with kubectl: {command}")
    try:
        args = shlex.split(command)
    except ValueError as err:
        fail(f"{component_name} live check command is not parseable: {err}")
    if not args[1:]:
        fail(f"{component_name} live check command must include kubectl arguments")
    validate_kubectl_live_check_verb(component_name, args[1:], pass_condition)
    if pass_condition in JSON_OUTPUT_PASS_CONDITIONS and not kubectl_command_requests_json(args[1:]):
        fail(f"{component_name} live check command must request JSON output: {command}")


def validate_kubectl_live_check_verb(component_name: str, args: list[str], pass_condition: str) -> None:
    if pass_condition in JSON_OUTPUT_PASS_CONDITIONS:
        if args[0] != "get":
            fail(f"{component_name} JSON live check command must use kubectl get")
        return
    if pass_condition == "stdout_yes":
        if args[:2] != ["auth", "can-i"]:
            fail(f"{component_name} stdout live check command must use kubectl auth can-i")


def kubectl_command_requests_json(args: list[str]) -> bool:
    for index, arg in enumerate(args):
        if arg in {"-o", "--output"} and index + 1 < len(args) and args[index + 1] == "json":
            return True
        if arg in {"-o=json", "--output=json", "-ojson"}:
            return True
    return False


def makefile_target_body(makefile: str, target: str) -> str:
    body: list[str] = []
    in_target = False
    for line in makefile.splitlines():
        if not in_target:
            if line.startswith(f"{target}:"):
                in_target = True
            continue
        if line and not line[0].isspace() and ":" in line:
            break
        body.append(line)
    return "\n".join(body)


def validate_contract_gate_command_runs_validator(gate_id: str, target: str, validator_script: str, makefile: str) -> None:
    target_body = makefile_target_body(makefile, target)
    if f"python {validator_script}" not in target_body:
        fail(f"{gate_id} command target {target} does not run {validator_script}")


def validate_contract_gate_manifest_profile(gate_id: str, expected_profile: str, manifest: Path) -> set[str]:
    manifest_document = load_profile(manifest)
    manifest_profile = str(manifest_document.get("profile", "")).strip()
    if manifest_profile != expected_profile:
        fail(f"{gate_id} profile {expected_profile} does not match manifest profile {manifest_profile or '<missing>'}")
    live_checks = manifest_document.get("live_checks")
    if not isinstance(live_checks, list) or not live_checks:
        fail(f"{gate_id} manifest live_checks must be a non-empty list")
    observed_check_ids: set[str] = set()
    for check in live_checks:
        if not isinstance(check, dict):
            fail(f"{gate_id} manifest live check must be an object")
        for field in ("id", "command", "pass_condition"):
            value = check.get(field)
            if not isinstance(value, str) or not value.strip():
                fail(f"{gate_id} manifest live check {field} must be a non-empty string")
        check_id = check["id"].strip()
        if not check_id:
            fail(f"{gate_id} manifest live check missing id")
        if check_id in observed_check_ids:
            fail(f"{gate_id} manifest duplicate live check id: {check_id}")
        observed_check_ids.add(check_id)
        pass_condition = check["pass_condition"].strip()
        if pass_condition not in SUPPORTED_CONTRACT_GATE_MANIFEST_PASS_CONDITIONS:
            fail(f"{gate_id} manifest live check pass_condition unsupported: {pass_condition}")
    return observed_check_ids


def validate_contract_gate_manifest_required_checks(gate_id: str, manifest_check_ids: set[str], required_checks: set[str]) -> None:
    missing = required_checks - manifest_check_ids
    if missing:
        fail(f"{gate_id} manifest missing validator required live checks: {', '.join(sorted(missing))}")


def validate_contract_gate_required_env(gate_id: str, profile_required_env: set[str], validator_required_env: set[str]) -> None:
    missing = validator_required_env - profile_required_env
    if missing:
        fail(f"{gate_id} profile missing validator required env: {', '.join(sorted(missing))}")


def validator_script_identity(path: Path) -> dict[str, str]:
    try:
        module = ast.parse(read(path), filename=str(path))
    except OSError as err:
        fail(f"validator_script unreadable: {display_path(path)}: {err}")
    except SyntaxError as err:
        fail(f"validator_script malformed: {display_path(path)}: {err}")
    identity: dict[str, str] = {}
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, str):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id in {"GATE_ID", "PROFILE"}:
                identity[target.id] = statement.value.value
    for name in ("GATE_ID", "PROFILE"):
        if not identity.get(name):
            fail(f"{display_path(path)} must declare {name}")
    return identity


def validator_script_required_checks(path: Path) -> set[str]:
    try:
        module = ast.parse(read(path), filename=str(path))
    except OSError as err:
        fail(f"validator_script unreadable: {display_path(path)}: {err}")
    except SyntaxError as err:
        fail(f"validator_script malformed: {display_path(path)}: {err}")
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "REQUIRED_CHECKS" for target in statement.targets):
            continue
        if not isinstance(statement.value, ast.Set):
            fail(f"{display_path(path)} REQUIRED_CHECKS must be a set")
        checks: set[str] = set()
        for element in statement.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str) or not element.value.strip():
                fail(f"{display_path(path)} REQUIRED_CHECKS entries must be non-empty strings")
            checks.add(element.value.strip())
        if not checks:
            fail(f"{display_path(path)} REQUIRED_CHECKS must be non-empty")
        return checks
    fail(f"{display_path(path)} must declare REQUIRED_CHECKS")


def validator_script_required_env(path: Path) -> set[str]:
    try:
        module = ast.parse(read(path), filename=str(path))
    except OSError as err:
        fail(f"validator_script unreadable: {display_path(path)}: {err}")
    except SyntaxError as err:
        fail(f"validator_script malformed: {display_path(path)}: {err}")
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "REQUIRED_ENV" for target in statement.targets):
            continue
        if not isinstance(statement.value, ast.Set):
            fail(f"{display_path(path)} REQUIRED_ENV must be a set")
        env_names: set[str] = set()
        for element in statement.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str) or not element.value.strip():
                fail(f"{display_path(path)} REQUIRED_ENV entries must be non-empty strings")
            env_name = element.value.strip()
            if not ENV_NAME_PATTERN.match(env_name):
                fail(f"{display_path(path)} REQUIRED_ENV entry has invalid env name: {env_name}")
            env_names.add(env_name)
        if not env_names:
            fail(f"{display_path(path)} REQUIRED_ENV must be non-empty")
        return env_names
    fail(f"{display_path(path)} must declare REQUIRED_ENV")


def validate_contract_gate_validator_identity(gate_id: str, expected_profile: str, validator_script: Path) -> None:
    identity = validator_script_identity(validator_script)
    if identity["GATE_ID"] != gate_id:
        fail(f"{gate_id} validator GATE_ID mismatch: expected {gate_id}, got {identity['GATE_ID']}")
    if identity["PROFILE"] != expected_profile:
        fail(f"{gate_id} validator PROFILE mismatch: expected {expected_profile}, got {identity['PROFILE']}")


def validate_contract(profile: dict[str, Any]) -> None:
    if profile.get("profile") != "REAL-K8S-LAB-A":
        fail("profile must be REAL-K8S-LAB-A")
    if profile.get("status") not in {"contract", "live", "production_like"}:
        fail("status must be contract, live or production_like")
    if profile_minimum_nodes(profile) < 3:
        fail("minimum_nodes must be at least 3")
    components = profile.get("components")
    if not isinstance(components, dict):
        fail("components must be an object")
    missing = REQUIRED_COMPONENTS - set(components)
    if missing:
        fail(f"missing required components: {', '.join(sorted(missing))}")
    makefile = read(ROOT / "Makefile")
    for name, component in components.items():
        if not isinstance(component, dict):
            fail(f"{name} component must be an object")
        if "purpose" not in component:
            fail(f"{name} must document purpose")
        checks = component.get("live_checks")
        if not isinstance(checks, list) or not checks:
            fail(f"{name} must define live_checks")
        observed_live_check_ids = set()
        for check in checks:
            if not isinstance(check, dict):
                fail(f"{name} live check must be an object")
            for field in ("id", "command", "pass_condition"):
                value = check.get(field)
                if not isinstance(value, str) or not value.strip():
                    fail(f"{name} live check {field} must be a non-empty string")
            check_id = check["id"].strip()
            if check_id in observed_live_check_ids:
                fail(f"{name} duplicate live check id: {check_id}")
            observed_live_check_ids.add(check_id)
            if check["pass_condition"] not in SUPPORTED_PROFILE_PASS_CONDITIONS:
                fail(f"{name} live check pass_condition unsupported: {check['pass_condition']}")
            validate_profile_live_check_command(name, check["command"], check["pass_condition"], makefile)
    contract_gates = profile.get("contract_gates")
    if not isinstance(contract_gates, list):
        fail("contract_gates must be a list")
    observed_gate_ids = set()
    for gate in contract_gates:
        if not isinstance(gate, dict):
            fail("contract gate must be an object")
        for field in ("id", "profile", "command", "manifest", "validator_script"):
            if not gate.get(field):
                fail(f"contract gate missing {field}")
        gate_id = str(gate["id"])
        if gate_id in observed_gate_ids:
            fail(f"duplicate contract gate id: {gate_id}")
        required_env = gate.get("required_env")
        if not isinstance(required_env, list) or not required_env:
            fail(f"{gate['id']} required_env must be a non-empty list")
        profile_required_env: set[str] = set()
        for env_name in required_env:
            if not isinstance(env_name, str) or not env_name.strip():
                fail(f"{gate['id']} required_env entries must be non-empty strings")
            if not ENV_NAME_PATTERN.match(env_name):
                fail(f"{gate['id']} required_env entry has invalid env name: {env_name}")
            profile_required_env.add(env_name)
        observed_gate_ids.add(gate_id)
        command = gate["command"]
        if not isinstance(command, str) or not command.startswith("make validate-"):
            fail(f"{gate['id']} command must be a make validate-* target")
        target = command.removeprefix("make ").strip()
        if f"{target}:" not in makefile:
            fail(f"{gate['id']} command target {target} missing from Makefile")
        validate_contract_gate_command_runs_validator(gate_id, target, str(gate["validator_script"]), makefile)
        for field in ("manifest", "validator_script"):
            path = ROOT / str(gate[field])
            if not path.exists():
                fail(f"{gate['id']} {field} missing: {gate[field]}")
        validator_script = ROOT / str(gate["validator_script"])
        manifest_check_ids = validate_contract_gate_manifest_profile(gate_id, str(gate["profile"]).strip(), ROOT / str(gate["manifest"]))
        validate_contract_gate_validator_identity(gate_id, str(gate["profile"]).strip(), validator_script)
        validate_contract_gate_manifest_required_checks(gate_id, manifest_check_ids, validator_script_required_checks(validator_script))
        validate_contract_gate_required_env(gate_id, profile_required_env, validator_script_required_env(validator_script))
    missing_gates = REQUIRED_CONTRACT_GATE_IDS - observed_gate_ids
    if missing_gates:
        fail(f"missing contract gates: {', '.join(sorted(missing_gates))}")


def validate_docs() -> None:
    docs = {
        "CLAUDE.md": DOC_ROOT / "CLAUDE.md",
        "ANI-DOCS-INDEX.md": DOC_ROOT / "ANI-DOCS-INDEX.md",
        "ANI-06-开发计划.md": DOC_ROOT / "ANI-06-开发计划.md",
        "CURRENT-SPRINT.md": ROOT / "CURRENT-SPRINT.md",
        "development-records/README.md": ROOT / "development-records/README.md",
    }
    for label, path in docs.items():
        content = read(path)
        for token in REQUIRED_DOC_TOKENS:
            if token not in content:
                fail(f"{label} must reference {token}")


def profile_minimum_nodes(profile: dict[str, Any], default: int = 0) -> int:
    raw_value = profile.get("minimum_nodes", default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        fail("minimum_nodes must be an integer")


def kubectl(args: list[str], kubeconfig: str | None) -> subprocess.CompletedProcess[str]:
    command = ["kubectl", *args]
    env = os.environ.copy()
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig
    return subprocess.run(command, env=env, text=True, capture_output=True, check=False)


def kubectl_args(command: Any) -> list[str]:
    if not isinstance(command, str):
        fail(f"live command must be a string: {command!r}")
    if not command.startswith("kubectl "):
        fail(f"live command must start with kubectl: {command}")
    args = command.split()[1:]
    if not args:
        fail("live command must include kubectl arguments")
    return args


def run_json_check(command: str, kubeconfig: str | None) -> dict[str, Any]:
    result = kubectl(kubectl_args(command), kubeconfig)
    if result.returncode != 0:
        fail(f"{command} failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as err:
        fail(f"{command} did not return JSON: {err}")
    if not isinstance(data, dict):
        fail(f"{command} returned non-object JSON")
    return data


def json_items(data: dict[str, Any], command: str) -> list[dict[str, Any]]:
    items = data.get("items", [])
    if not isinstance(items, list):
        fail(f"{command} items must be a list")
    if not all(isinstance(item, dict) for item in items):
        fail(f"{command} items entries must be objects")
    return items


def json_metadata(data: dict[str, Any], command: str) -> dict[str, Any]:
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        fail(f"{command} metadata must be an object")
    return metadata


def node_ready_conditions(node: dict[str, Any], command: str) -> list[dict[str, Any]]:
    status = node.get("status", {})
    if not isinstance(status, dict):
        fail(f"{command} node status must be an object")
    conditions = status.get("conditions", [])
    if not isinstance(conditions, list):
        fail(f"{command} node conditions must be a list")
    if not all(isinstance(item, dict) for item in conditions):
        fail(f"{command} node condition entries must be objects")
    return conditions


def condition_passed(condition: str, command: str, kubeconfig: str | None, minimum_nodes: int) -> bool:
    if not isinstance(condition, str) or condition not in SUPPORTED_LIVE_PASS_CONDITIONS:
        fail(f"unsupported pass_condition {condition}")
    if condition == "stdout_yes":
        result = kubectl(kubectl_args(command), kubeconfig)
        return result.returncode == 0 and result.stdout.strip().lower() == "yes"

    data = run_json_check(command, kubeconfig)
    if condition == "at_least_minimum_nodes_ready":
        items = json_items(data, command)
        ready = 0
        for node in items:
            conditions = node_ready_conditions(node, command)
            if any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions):
                ready += 1
        return ready >= minimum_nodes
    if condition == "at_least_one_storageclass":
        return len(json_items(data, command)) >= 1
    if condition == "crd_exists":
        return bool(json_metadata(data, command).get("name"))
    if condition == "at_least_one_item":
        return len(json_items(data, command)) >= 1
    fail(f"unsupported pass_condition {condition}")


def validate_live(profile: dict[str, Any], kubeconfig: str | None) -> dict[str, Any]:
    if shutil.which("kubectl") is None:
        fail("kubectl is required for --live")
    minimum_nodes = profile_minimum_nodes(profile, default=3)
    evidence: dict[str, Any] = {
        "profile": profile["profile"],
        "status": "live",
        "passed": True,
        "minimum_nodes": minimum_nodes,
        "kubeconfig_provided": bool(kubeconfig),
        "summary": {"total": 0, "passed": 0, "failed": 0},
        "checks": [],
    }
    for component_name, component in profile["components"].items():
        if not component.get("required", False):
            continue
        for check in component.get("live_checks", []):
            if not condition_passed(check["pass_condition"], check["command"], kubeconfig, minimum_nodes):
                fail(f"{component_name}/{check['id']} did not satisfy {check['pass_condition']}")
            evidence["summary"]["total"] += 1
            evidence["summary"]["passed"] += 1
            evidence["checks"].append(
                {
                    "component": component_name,
                    "id": check["id"],
                    "command": check["command"],
                    "pass_condition": check["pass_condition"],
                    "passed": True,
                }
            )
    return evidence


def component_gate_evidence_error(path: Path, expected_profile: str = "", expected_gate_id: str = "") -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        return f"unreadable evidence output: {err}"
    except json.JSONDecodeError as err:
        return f"invalid evidence JSON: {err}"
    if not isinstance(data, dict):
        return "invalid evidence JSON: root must be an object"
    if "passed" in data and not isinstance(data["passed"], bool):
        return "evidence passed flag must be a boolean"
    if "status" in data:
        if not isinstance(data["status"], str):
            return "evidence status must be a string"
        if not data["status"].strip():
            return "evidence status must not be empty"
        if data.get("status") != "passed":
            if data.get("passed") is True:
                return "evidence status/passed mismatch: passed=true requires status=passed"
            return f"non-passing evidence status: {data['status']}"
        if "passed" in data and data.get("passed") is not True:
            return "evidence passed flag must be true when present"
    elif "passed" not in data:
        return "missing evidence outcome: expected status=passed or passed=true"
    elif data.get("passed") is not True:
        return "non-passing evidence JSON: expected status=passed or passed=true"
    if expected_gate_id and "id" in data and not isinstance(data["id"], str):
        return "evidence gate id must be a string"
    evidence_gate_id_value = str(data.get("id", ""))
    if expected_gate_id and evidence_gate_id_value != evidence_gate_id_value.strip():
        return "evidence gate id must not contain surrounding whitespace"
    evidence_gate_id = evidence_gate_id_value.strip()
    if expected_gate_id and not evidence_gate_id:
        return f"missing evidence gate id: expected {expected_gate_id}"
    if expected_gate_id and evidence_gate_id and evidence_gate_id != expected_gate_id:
        return f"evidence gate id mismatch: expected {expected_gate_id}, got {evidence_gate_id}"
    if expected_profile and "profile" in data and not isinstance(data["profile"], str):
        return "evidence profile must be a string"
    evidence_profile_value = str(data.get("profile", ""))
    if expected_profile and evidence_profile_value != evidence_profile_value.strip():
        return "evidence profile must not contain surrounding whitespace"
    evidence_profile = evidence_profile_value.strip()
    if expected_profile and not evidence_profile:
        return f"missing evidence profile: expected {expected_profile}"
    if expected_profile and evidence_profile and evidence_profile != expected_profile:
        return f"evidence profile mismatch: expected {expected_profile}, got {evidence_profile}"
    return ""


def validate_component_live_gates(
    profile: dict[str, Any],
    evidence_dir: Path,
    runner: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if env is None:
        env = os.environ
    command_env = os.environ.copy()
    command_env.update({name: str(value) for name, value in env.items()})
    runner = runner or (
        lambda command: subprocess.run(command, env=command_env, text=True, capture_output=True, check=False)
    )
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        fail(f"component evidence dir unusable: {err}")
    if not evidence_dir.is_dir():
        fail(f"component evidence dir unusable: {evidence_dir} is not a directory")
    try:
        if evidence_dir.stat().st_mode & 0o222 == 0:
            fail("component evidence dir must be writable")
    except OSError as err:
        fail(f"component evidence dir unusable: {err}")
    evidence: dict[str, Any] = {
        "profile": profile["profile"],
        "status": "component_live",
        "passed": True,
        "summary": {"total": 0, "passed": 0, "failed": 0},
        "component_gates": [],
    }
    for gate in profile.get("contract_gates", []):
        gate_id = str(gate["id"])
        validator = ROOT / str(gate["validator_script"])
        gate_evidence = evidence_dir / f"{gate_id}.json"
        command = [sys.executable, str(validator), "--live", "--evidence-output", str(gate_evidence)]
        evidence["summary"]["total"] += 1
        required_env = [str(name) for name in gate.get("required_env", [])]
        missing_env = component_missing_required_env(required_env, env)
        gate_result: dict[str, Any] = {
            "id": gate_id,
            "profile": gate["profile"],
            "validator_script": gate["validator_script"],
            "command": command,
            "evidence_output": str(gate_evidence),
            "required_env": required_env,
            "missing_env": missing_env,
            "passed": not missing_env,
        }
        evidence["component_gates"].append(gate_result)
    blocked = [gate for gate in evidence["component_gates"] if gate["missing_env"]]
    if blocked:
        evidence["passed"] = False
        evidence["status"] = "component_live_preflight_failed"
        evidence["summary"] = {
            "total": evidence["summary"]["total"],
            "passed": evidence["summary"]["total"] - len(blocked),
            "failed": 0,
            "blocked": len(blocked),
        }
        return evidence

    for gate_result, gate in zip(evidence["component_gates"], profile.get("contract_gates", []), strict=True):
        gate_id = str(gate["id"])
        gate_evidence = evidence_dir / f"{gate_id}.json"
        validator = ROOT / str(gate["validator_script"])
        command = [sys.executable, str(validator), "--live", "--evidence-output", str(gate_evidence)]
        gate_result["passed"] = False
        result = runner(command)
        if result.returncode != 0:
            detail = redact_sensitive_text((result.stderr or result.stdout or "").strip())
            evidence["passed"] = False
            evidence["status"] = "component_live_failed"
            evidence["summary"]["failed"] += 1
            gate_result["returncode"] = result.returncode
            gate_result["error"] = detail
        elif not gate_evidence.exists():
            evidence["passed"] = False
            evidence["status"] = "component_live_failed"
            evidence["summary"]["failed"] += 1
            gate_result["returncode"] = result.returncode
            gate_result["error"] = f"missing evidence output: {gate_evidence}"
        elif evidence_error := component_gate_evidence_error(
            gate_evidence,
            expected_profile=str(gate["profile"]),
            expected_gate_id=gate_id,
        ):
            evidence["passed"] = False
            evidence["status"] = "component_live_failed"
            evidence["summary"]["failed"] += 1
            gate_result["returncode"] = result.returncode
            gate_result["error"] = redact_sensitive_text(evidence_error)
        else:
            gate_result["returncode"] = result.returncode
            gate_result["passed"] = True
            evidence["summary"]["passed"] += 1
    return evidence


def component_missing_required_env(required_env: list[str], env: Mapping[str, str]) -> list[str]:
    missing_env = []
    for name in required_env:
        raw_value = env.get(name, "")
        if raw_value is None or not str(raw_value).strip():
            missing_env.append(name)
            continue
        value = str(raw_value)
        if value != value.strip():
            fail(f"component required env {name} must not contain surrounding whitespace")
    return missing_env


def validate_component_live_preflight(profile: dict[str, Any], env: Mapping[str, str] | None = None) -> dict[str, Any]:
    if env is None:
        env = os.environ
    evidence: dict[str, Any] = {
        "profile": profile["profile"],
        "status": "component_live_preflight_passed",
        "passed": True,
        "summary": {"total": 0, "passed": 0, "blocked": 0},
        "component_gates": [],
    }
    for gate in profile.get("contract_gates", []):
        required_env = [str(name) for name in gate.get("required_env", [])]
        missing_env = component_missing_required_env(required_env, env)
        gate_passed = not missing_env
        evidence["summary"]["total"] += 1
        if gate_passed:
            evidence["summary"]["passed"] += 1
        else:
            evidence["passed"] = False
            evidence["status"] = "component_live_preflight_failed"
            evidence["summary"]["blocked"] += 1
        evidence["component_gates"].append(
            {
                "id": str(gate["id"]),
                "profile": gate["profile"],
                "required_env": required_env,
                "missing_env": missing_env,
                "passed": gate_passed,
            }
        )
    return evidence


def failed_component_gate_ids(evidence: dict[str, Any]) -> list[str]:
    return [str(gate["id"]) for gate in evidence.get("component_gates", []) if not gate.get("passed")]


def component_gate_command(
    mode: str,
    gate_id: str,
    component_env_file: str = "",
    component_evidence_dir: str = "",
) -> str:
    command = ["python", "scripts/validate_real_k8s_profile.py", mode, "--component-gate", gate_id]
    if component_env_file:
        command.extend(["--component-env-file", component_env_file])
    if mode == "--component-live" and component_evidence_dir:
        command.extend(["--component-evidence-dir", component_evidence_dir])
    suffix = "preflight-summary" if mode == "--component-preflight" else "live-summary"
    command.extend(["--evidence-output", f"{COMPONENT_LIVE_RECORD_DIR}/{gate_id}-{suffix}.json"])
    return shlex.join(command)


def validate_component_summary_gate_ids(profile: dict[str, Any], evidence: dict[str, Any]) -> None:
    if "profile" in evidence and not isinstance(evidence["profile"], str):
        fail("component summary profile must be a string")
    summary_profile_value = str(evidence.get("profile", ""))
    if summary_profile_value != summary_profile_value.strip():
        fail("component summary profile must not contain surrounding whitespace")
    summary_profile = summary_profile_value.strip()
    current_profile = str(profile.get("profile", "")).strip()
    if summary_profile != current_profile:
        fail(f"component summary profile mismatch: expected {current_profile}, got {summary_profile or '<missing>'}")
    if "status" in evidence and not isinstance(evidence["status"], str):
        fail("component summary status must be a string")
    source_status_value = str(evidence.get("status", ""))
    if source_status_value != source_status_value.strip():
        fail("component summary status must not contain surrounding whitespace")
    source_status = source_status_value.strip()
    if source_status not in COMPONENT_SUMMARY_STATUSES:
        fail(f"component summary status unsupported: {source_status or '<missing>'}")
    expected_gate_profiles = {str(gate["id"]): str(gate.get("profile", "")).strip() for gate in profile.get("contract_gates", [])}
    expected_gate_required_env = {
        str(gate["id"]): [str(name) for name in gate.get("required_env", [])]
        for gate in profile.get("contract_gates", [])
    }
    known_gate_ids = set(expected_gate_profiles)
    unknown_gate_ids: list[str] = []
    observed_gate_ids: set[str] = set()
    duplicate_gate_ids: list[str] = []
    if "component_gates" not in evidence:
        fail("component summary component_gates is required")
    component_gates = evidence.get("component_gates", [])
    if not isinstance(component_gates, list):
        fail("component summary component_gates must be a list")
    if not component_gates:
        fail("component summary component_gates must not be empty")
    for gate in component_gates:
        if not isinstance(gate, dict):
            fail("component summary gate entries must be objects")
        if "id" in gate and not isinstance(gate["id"], str):
            fail("component summary gate id must be a string")
        gate_id = str(gate.get("id", ""))
        if gate_id != gate_id.strip():
            fail("component summary gate id must not contain surrounding whitespace")
        if not gate_id:
            fail("component summary gate missing id")
        if not isinstance(gate.get("passed"), bool):
            fail(f"component summary gate {gate_id} passed must be a boolean")
        if "missing_env" not in gate:
            fail(f"component summary gate {gate_id} missing_env is required")
        missing_env = gate.get("missing_env", [])
        if not isinstance(missing_env, list) or any(not isinstance(name, str) or not name.strip() for name in missing_env):
            fail(f"component summary gate {gate_id} missing_env must be a string list")
        if any(name != name.strip() for name in missing_env):
            fail(f"component summary gate {gate_id} missing_env must not contain surrounding whitespace")
        if gate.get("passed") and missing_env:
            fail(f"component summary passed gate {gate_id} missing_env must be empty")
        if "returncode" in gate:
            returncode = gate["returncode"]
            if isinstance(returncode, bool) or not isinstance(returncode, int) or returncode < 0:
                fail(f"component summary gate {gate_id} returncode must be a non-negative integer")
        if "error" in gate and not isinstance(gate["error"], str):
            fail(f"component summary gate {gate_id} error must be a string")
        if "evidence_output" in gate and not isinstance(gate["evidence_output"], str):
            fail(f"component summary gate {gate_id} evidence_output must be a string")
        if "profile" not in gate:
            fail(f"component summary gate {gate_id} profile is required")
        if "profile" in gate and not isinstance(gate["profile"], str):
            fail(f"component summary gate {gate_id} profile must be a string")
        gate_profile_value = str(gate.get("profile", ""))
        if gate_profile_value != gate_profile_value.strip():
            fail(f"component summary gate {gate_id} profile must not contain surrounding whitespace")
        gate_profile = gate_profile_value.strip()
        if "required_env" not in gate:
            fail(f"component summary gate {gate_id} required_env is required")
        required_env = gate.get("required_env", [])
        if not isinstance(required_env, list) or any(not isinstance(name, str) or not name.strip() for name in required_env):
            fail(f"component summary gate {gate_id} required_env must be a string list")
        if any(name != name.strip() for name in required_env):
            fail(f"component summary gate {gate_id} required_env must not contain surrounding whitespace")
        undeclared_missing_env = sorted(set(missing_env) - set(required_env))
        if undeclared_missing_env:
            fail(
                f"component summary gate {gate_id} missing_env contains undeclared required env: "
                f"{', '.join(undeclared_missing_env)}"
            )
        if gate_id not in known_gate_ids:
            unknown_gate_ids.append(gate_id)
        elif gate_profile and gate_profile != expected_gate_profiles[gate_id]:
            fail(f"component summary gate {gate_id} profile mismatch: expected {expected_gate_profiles[gate_id]}, got {gate_profile}")
        elif required_env != expected_gate_required_env[gate_id]:
            fail(f"component summary gate {gate_id} required_env mismatch: expected {', '.join(expected_gate_required_env[gate_id])}")
        if gate_id in observed_gate_ids:
            duplicate_gate_ids.append(gate_id)
        observed_gate_ids.add(gate_id)
    if unknown_gate_ids:
        fail(f"component summary references unknown gate ids: {', '.join(sorted(set(unknown_gate_ids)))}")
    if duplicate_gate_ids:
        fail(f"component summary contains duplicate gate ids: {', '.join(sorted(set(duplicate_gate_ids)))}")
    if "passed" not in evidence:
        fail("component summary passed is required")
    passed = evidence["passed"]
    if not isinstance(passed, bool):
        fail("component summary passed must be a boolean")
    expected_passed = all(bool(gate.get("passed")) for gate in component_gates)
    if passed != expected_passed:
        fail(f"component summary passed mismatch: expected {expected_passed}, got {passed}")
    if source_status in {"component_live", "component_live_preflight_passed"} and not expected_passed:
        fail(f"component summary status {source_status} requires all gates passed")
    if source_status in {"component_live_failed", "component_live_preflight_failed"} and expected_passed:
        fail(f"component summary status {source_status} requires unresolved gates")
    summary = evidence.get("summary")
    if summary is None:
        fail("component summary summary is required")
    if not isinstance(summary, dict):
        fail("component summary summary must be an object")
    expected_counts = {
        "total": len(component_gates),
        "passed": sum(1 for gate in component_gates if gate.get("passed")),
        "blocked": sum(1 for gate in component_gates if not gate.get("passed") and gate.get("missing_env")),
    }
    expected_counts["failed"] = expected_counts["total"] - expected_counts["passed"] - expected_counts["blocked"]
    if source_status in {"component_live", "component_live_failed"} and expected_counts["blocked"]:
        fail(f"component summary status {source_status} cannot include blocked gates")
    if source_status in {"component_live_preflight_passed", "component_live_preflight_failed"} and expected_counts["failed"]:
        fail(f"component summary status {source_status} cannot include failed gates")
    if source_status in {"component_live_preflight_passed", "component_live_preflight_failed"}:
        for gate in component_gates:
            gate_id = str(gate.get("id", "")).strip()
            preflight_status = "blocked " if gate.get("missing_env", []) else ""
            for field in ("returncode", "error", "command", "evidence_output", "validator_script"):
                if field in {"returncode", "error"} and field in gate:
                    fail(f"component summary preflight {preflight_status}gate {gate_id} must not include {field}")
                if source_status == "component_live_preflight_passed" and field in gate:
                    fail(f"component summary preflight {preflight_status}gate {gate_id} must not include {field}")
    required_count_keys = {"total", "passed"}
    if source_status in {"component_live", "component_live_failed"} or expected_counts["failed"]:
        required_count_keys.add("failed")
    if source_status in {"component_live_preflight_passed", "component_live_preflight_failed"} or expected_counts["blocked"]:
        required_count_keys.add("blocked")
    for key in sorted(required_count_keys):
        if key not in summary:
            fail(f"component summary {key} count is required")
    for key, expected in expected_counts.items():
        if key not in summary:
            continue
        actual = summary[key]
        if not isinstance(actual, int) or isinstance(actual, bool) or actual < 0:
            fail(f"component summary {key} count must be a non-negative integer")
        if actual != expected:
            fail(f"component summary {key} count mismatch: expected {expected}, got {summary[key]}")


def component_summary_gate_command_error(
    gate_id: str,
    gate: dict[str, Any],
    expected_validator_script: str,
    evidence_output: str,
) -> str:
    command = gate.get("command")
    if command is None:
        return f"missing component summary gate command for live gate: {gate_id}"
    if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part.strip() for part in command):
        return f"component summary gate {gate_id} command must be a non-empty string list"
    if any(part != part.strip() for part in command):
        return f"component summary gate {gate_id} command entries must not contain surrounding whitespace"
    expected_validator = str(ROOT / expected_validator_script)
    if len(command) < 2 or command[1] != expected_validator:
        return f"component summary gate {gate_id} command validator mismatch: expected {display_path(Path(expected_validator))}"
    expected_suffix = ["--live", "--evidence-output", evidence_output]
    if command[-3:] != expected_suffix:
        return f"component summary gate {gate_id} command must end with --live --evidence-output {evidence_output}"
    expected_command = [sys.executable, expected_validator, "--live", "--evidence-output", evidence_output]
    if command != expected_command:
        return f"component summary gate {gate_id} command shape mismatch: expected {shlex.join(expected_command)}"
    return ""


def component_summary_evidence_output_path_error(gate_id: str, evidence_output: str, component_evidence_dir: str) -> str:
    if not component_evidence_dir:
        return ""
    expected_path = Path(component_evidence_dir) / f"{gate_id}.json"
    if Path(evidence_output) != expected_path:
        return f"evidence output path mismatch: expected {expected_path}"
    return ""


def component_summary_live_gate_provenance_error(
    gate_id: str,
    gate: dict[str, Any],
    expected_validator_script: str,
    component_evidence_dir: str,
) -> str:
    if "validator_script" not in gate:
        return f"missing component summary gate validator_script for live gate: {gate_id}"
    validator_script = gate.get("validator_script")
    if not isinstance(validator_script, str):
        return f"component summary gate {gate_id} validator_script must be a string"
    if not validator_script.strip():
        return f"missing component summary gate validator_script for live gate: {gate_id}"
    if validator_script != validator_script.strip():
        return f"component summary gate {gate_id} validator_script must not contain surrounding whitespace"
    if validator_script != expected_validator_script:
        return (
            f"component summary gate {gate_id} validator_script mismatch: "
            f"expected {expected_validator_script}"
        )
    evidence_output_value = gate.get("evidence_output", "")
    if not isinstance(evidence_output_value, str) or not evidence_output_value.strip():
        return f"missing evidence_output for live gate: {gate_id}"
    if evidence_output_value != evidence_output_value.strip():
        return f"component summary gate {gate_id} evidence_output must not contain surrounding whitespace"
    evidence_output = evidence_output_value
    command_error = component_summary_gate_command_error(
        gate_id,
        gate,
        expected_validator_script,
        evidence_output,
    )
    if command_error:
        return command_error
    return component_summary_evidence_output_path_error(
        gate_id,
        evidence_output,
        component_evidence_dir,
    )


def component_summary_planned_live_provenance_error(
    gate_id: str,
    gate: dict[str, Any],
    expected_validator_script: str,
) -> str:
    if not any(field in gate for field in ("validator_script", "evidence_output", "command")):
        return ""
    return component_summary_live_gate_provenance_error(
        gate_id,
        gate,
        expected_validator_script,
        "",
    )


def component_summary_report(
    profile: dict[str, Any],
    evidence: dict[str, Any],
    component_env_file: str = "",
    component_evidence_dir: str = "",
) -> dict[str, Any]:
    validate_component_summary_gate_ids(profile, evidence)
    source_status = str(evidence.get("status", "")).strip()
    expected_gate_validators = {str(gate["id"]): str(gate.get("validator_script", "")) for gate in profile.get("contract_gates", [])}
    failed_gates: list[str] = []
    blocked_gates: list[str] = []
    gate_details: list[dict[str, Any]] = []
    for gate in evidence.get("component_gates", []):
        gate_id = str(gate["id"])
        expected_profile = str(gate.get("profile", "")).strip()
        requires_live_evidence = source_status in {"component_live", "component_live_failed"}
        if gate.get("passed"):
            evidence_output = str(gate.get("evidence_output", "")).strip()
            if not expected_profile:
                evidence_error = f"missing component summary gate profile for passed gate: {gate_id}"
            elif requires_live_evidence:
                evidence_error = component_summary_live_gate_provenance_error(
                    gate_id, gate, expected_gate_validators[gate_id], component_evidence_dir
                )
            elif source_status == "component_live_preflight_failed":
                evidence_error = component_summary_planned_live_provenance_error(
                    gate_id,
                    gate,
                    expected_gate_validators[gate_id],
                )
            else:
                evidence_error = ""
            if not evidence_error and requires_live_evidence and evidence_output:
                evidence_path = Path(evidence_output)
                if not evidence_path.exists():
                    evidence_error = f"missing evidence output: {evidence_path}"
                else:
                    evidence_error = component_gate_evidence_error(
                        evidence_path,
                        expected_profile=expected_profile,
                        expected_gate_id=gate_id,
                    )
            if not evidence_error and requires_live_evidence and "returncode" not in gate:
                evidence_error = f"passed live gate returncode is required: {gate_id}"
            elif not evidence_error and requires_live_evidence and gate.get("returncode", 0) != 0:
                evidence_error = f"passed live gate returncode must be zero: {gate_id}"
            elif not evidence_error and requires_live_evidence and str(gate.get("error", "")).strip():
                evidence_error = f"passed live gate must not include error: {gate_id}"
            if not evidence_error:
                continue
            failed_gates.append(gate_id)
            detail = {
                "id": gate_id,
                "status": "failed",
                "missing_env": [str(name) for name in gate.get("missing_env", [])],
                "error": redact_sensitive_text(evidence_error),
            }
            if "returncode" in gate:
                detail["returncode"] = gate["returncode"]
            gate_details.append(detail)
        elif gate.get("missing_env"):
            evidence_error = ""
            if source_status == "component_live_preflight_failed":
                evidence_error = component_summary_planned_live_provenance_error(
                    gate_id,
                    gate,
                    expected_gate_validators[gate_id],
                )
            if evidence_error:
                failed_gates.append(gate_id)
                detail = {
                    "id": gate_id,
                    "status": "failed",
                    "missing_env": [str(name) for name in gate.get("missing_env", [])],
                    "error": redact_sensitive_text(evidence_error),
                }
                gate_details.append(detail)
                continue
            blocked_gates.append(gate_id)
            detail = {
                "id": gate_id,
                "status": "blocked",
                "missing_env": [str(name) for name in gate.get("missing_env", [])],
            }
            if "returncode" in gate:
                detail["returncode"] = gate["returncode"]
            if gate.get("error"):
                detail["error"] = redact_sensitive_text(str(gate["error"]))
            gate_details.append(detail)
        else:
            failed_gates.append(gate_id)
            evidence_error = ""
            if requires_live_evidence:
                evidence_error = component_summary_live_gate_provenance_error(
                    gate_id, gate, expected_gate_validators[gate_id], component_evidence_dir
                )
                if not evidence_error and "returncode" not in gate:
                    evidence_error = f"failed live gate returncode is required: {gate_id}"
                elif not evidence_error and "error" not in gate:
                    evidence_error = f"failed live gate error field is required: {gate_id}"
                elif not evidence_error and not gate["error"].strip():
                    evidence_error = f"failed live gate error must be non-empty: {gate_id}"
                elif not evidence_error and gate["error"] != gate["error"].strip():
                    evidence_error = f"failed live gate error must not contain surrounding whitespace: {gate_id}"
            detail = {
                "id": gate_id,
                "status": "failed",
                "missing_env": [str(name) for name in gate.get("missing_env", [])],
            }
            if "returncode" in gate:
                detail["returncode"] = gate["returncode"]
            if evidence_error:
                detail["error"] = redact_sensitive_text(evidence_error)
            elif gate.get("error"):
                detail["error"] = redact_sensitive_text(str(gate["error"]))
            gate_details.append(detail)
    next_gate_ids = list(dict.fromkeys([*blocked_gates, *failed_gates]))
    total_gates = len(evidence.get("component_gates", []))
    report_summary = {
        "total": total_gates,
        "passed": total_gates - len(next_gate_ids),
        "failed": len(failed_gates),
        "blocked": len(blocked_gates),
    }
    return {
        "profile": evidence.get("profile", "REAL-K8S-LAB-A"),
        "status": "component_report",
        "passed": not next_gate_ids,
        "source_status": evidence.get("status", ""),
        "source_summary": evidence.get("summary", {}),
        "summary": report_summary,
        "failed_gates": failed_gates,
        "blocked_gates": blocked_gates,
        "unresolved_gates": next_gate_ids,
        "gate_details": gate_details,
        "next_commands": [
            {
                "id": gate_id,
                "preflight": component_gate_command(
                    "--component-preflight",
                    gate_id,
                    component_env_file=component_env_file,
                ),
                "live": component_gate_command(
                    "--component-live",
                    gate_id,
                    component_env_file=component_env_file,
                    component_evidence_dir=component_evidence_dir,
                ),
            }
            for gate_id in next_gate_ids
        ],
    }


def load_component_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"component summary missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        fail(f"component summary unreadable: {err}")
    except json.JSONDecodeError as err:
        fail(f"component summary is not valid JSON: {err}")
    if not isinstance(data, dict):
        fail("component summary must be a JSON object")
    return data


def write_live_evidence(path: Path, evidence: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as err:
        fail(f"profile output unusable: {err}")


def validate_profile_output_path(path: str) -> None:
    if not path.strip():
        fail("profile output path must not be empty")
    if path != path.strip():
        fail("profile output path must not contain surrounding whitespace")
    output_path = Path(path)
    if output_path.exists() and output_path.is_dir():
        fail("profile output path must be a file path")
    if output_path.parent.exists() and not output_path.parent.is_dir():
        fail("profile output parent must be a directory")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fail("profile output parent must be writable")
    except NotADirectoryError:
        fail("profile output parent must be a directory")
    except OSError as err:
        fail(f"profile output unusable: {err}")
    try:
        if output_path.parent.stat().st_mode & 0o222 == 0:
            fail("profile output parent must be writable")
        if output_path.exists() and output_path.stat().st_mode & 0o222 == 0:
            fail("profile output path must be writable")
    except OSError as err:
        fail(f"profile output unusable: {err}")


def validate_profile_path(path: str) -> None:
    if not path.strip():
        fail("profile path must not be empty")
    if path != path.strip():
        fail("profile path must not contain surrounding whitespace")


def has_non_empty_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(has_non_empty_value(item) for item in value.values())
    if isinstance(value, list):
        return any(has_non_empty_value(item) for item in value)
    return value is not None


def has_non_empty_auth_value(value: Mapping[str, Any]) -> bool:
    return any(
        isinstance(key, str) and key in KUBECONFIG_USER_AUTH_FIELDS and has_non_empty_value(item)
        for key, item in value.items()
    )


def has_value_with_surrounding_whitespace(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip()) and value != value.strip()
    if isinstance(value, Mapping):
        return any(has_value_with_surrounding_whitespace(item) for item in value.values())
    if isinstance(value, list):
        return any(has_value_with_surrounding_whitespace(item) for item in value)
    return False


def has_supported_auth_value_with_surrounding_whitespace(key: str, item: Any) -> bool:
    if key == "auth-provider" and isinstance(item, Mapping):
        return any(
            field in item and has_value_with_surrounding_whitespace(item[field])
            for field in KUBECONFIG_AUTH_PROVIDER_WHITESPACE_FIELDS
        )
    if key == "exec" and isinstance(item, Mapping):
        return any(
            field in item and has_value_with_surrounding_whitespace(item[field])
            for field in KUBECONFIG_EXEC_WHITESPACE_FIELDS
        )
    return has_value_with_surrounding_whitespace(item)


def has_auth_value_with_surrounding_whitespace(value: Mapping[str, Any]) -> bool:
    return any(
        isinstance(key, str)
        and key in KUBECONFIG_USER_AUTH_FIELDS
        and has_supported_auth_value_with_surrounding_whitespace(key, item)
        for key, item in value.items()
    )


KUBECONFIG_AUTH_STRING_FIELDS = {
    "apiVersion",
    "client-certificate",
    "client-certificate-data",
    "client-key",
    "client-key-data",
    "command",
    "installHint",
    "interactiveMode",
    "name",
    "password",
    "token",
    "tokenFile",
    "username",
    "value",
}

KUBECONFIG_TOP_LEVEL_AUTH_STRING_FIELDS = {
    "client-certificate",
    "client-certificate-data",
    "client-key",
    "client-key-data",
    "password",
    "token",
    "tokenFile",
    "username",
}
KUBECONFIG_USER_AUTH_FIELDS = KUBECONFIG_TOP_LEVEL_AUTH_STRING_FIELDS | {"auth-provider", "exec"}
KUBECONFIG_AUTH_PROVIDER_WHITESPACE_FIELDS = {"config", "name"}
KUBECONFIG_EXEC_WHITESPACE_FIELDS = {
    "apiVersion",
    "args",
    "command",
    "env",
    "installHint",
    "interactiveMode",
}
KUBECONFIG_AUTH_STRING_LIST_FIELDS = {"args"}
KUBECONFIG_AUTH_OBJECT_LIST_FIELDS = {"env"}
KUBECONFIG_AUTH_BOOLEAN_FIELDS = {"provideClusterInfo"}
SUPPORTED_KUBECONFIG_EXEC_API_VERSIONS = {
    "client.authentication.k8s.io/v1",
    "client.authentication.k8s.io/v1beta1",
}
SUPPORTED_KUBECONFIG_EXEC_INTERACTIVE_MODES = {"Never", "IfAvailable", "Always"}


def find_auth_type_error(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key == "auth-provider" and not isinstance(item, Mapping):
                return "auth-provider must be an object"
            if isinstance(key, str) and key == "auth-provider" and isinstance(item, Mapping):
                provider_name = item.get("name")
                if not isinstance(provider_name, str) or not provider_name.strip():
                    return "auth-provider name must be a non-empty string"
                if provider_name != provider_name.strip():
                    return "auth-provider name must not contain surrounding whitespace"
                config = item.get("config")
                if "config" in item and not isinstance(config, Mapping):
                    return "auth-provider config must be an object"
                if isinstance(config, Mapping) and any(not isinstance(config_key, str) for config_key in config.keys()):
                    return "auth-provider config keys must be strings"
                if isinstance(config, Mapping) and any(not config_key.strip() for config_key in config.keys()):
                    return "auth-provider config keys must be non-empty strings"
                if isinstance(config, Mapping) and any(config_key != config_key.strip() for config_key in config.keys()):
                    return "auth-provider config keys must not contain surrounding whitespace"
                if isinstance(config, Mapping) and any(not isinstance(config_value, str) for config_value in config.values()):
                    return "auth-provider config values must be strings"
                if isinstance(config, Mapping) and any(not config_value.strip() for config_value in config.values()):
                    return "auth-provider config values must be non-empty strings"
                if isinstance(config, Mapping) and any(config_value != config_value.strip() for config_value in config.values()):
                    return "auth-provider config values must not contain surrounding whitespace"
                continue
            if isinstance(key, str) and key == "exec":
                if not isinstance(item, Mapping):
                    return "exec must be an object"
                command = item.get("command")
                if command is None:
                    return "exec command must be a non-empty string"
                if not isinstance(command, str):
                    return "exec command must be a string"
                if not command.strip():
                    return "exec command must be a non-empty string"
                if any(char.isspace() for char in command):
                    return "exec command must not contain whitespace"
                api_version = item.get("apiVersion")
                if api_version is None:
                    return "exec apiVersion must be a non-empty string"
                if not isinstance(api_version, str):
                    return "exec apiVersion must be a string"
                if not api_version.strip():
                    return "exec apiVersion must be a non-empty string"
                if api_version != api_version.strip():
                    return "exec apiVersion must not contain surrounding whitespace"
                if api_version not in SUPPORTED_KUBECONFIG_EXEC_API_VERSIONS:
                    return "exec apiVersion must be a supported client authentication version"
                interactive_mode = item.get("interactiveMode")
                if "interactiveMode" in item and not isinstance(interactive_mode, str):
                    return "exec interactiveMode must be a string"
                if isinstance(interactive_mode, str) and not interactive_mode.strip():
                    return "exec interactiveMode must be a non-empty string"
                if isinstance(interactive_mode, str) and interactive_mode != interactive_mode.strip():
                    return "exec interactiveMode must not contain surrounding whitespace"
                if interactive_mode is not None and interactive_mode not in SUPPORTED_KUBECONFIG_EXEC_INTERACTIVE_MODES:
                    return "exec interactiveMode must be Never, IfAvailable, or Always"
                install_hint = item.get("installHint")
                if "installHint" in item and not isinstance(install_hint, str):
                    return "exec installHint must be a string"
                if isinstance(install_hint, str) and not install_hint.strip():
                    return "exec installHint must be a non-empty string"
                if isinstance(install_hint, str) and install_hint != install_hint.strip():
                    return "exec installHint must not contain surrounding whitespace"
                provide_cluster_info = item.get("provideClusterInfo")
                if "provideClusterInfo" in item and not isinstance(provide_cluster_info, bool):
                    return "exec provideClusterInfo must be a boolean"
                args = item.get("args")
                if "args" in item:
                    if not isinstance(args, list):
                        return "exec args must be a list"
                    if any(not isinstance(entry, str) for entry in args):
                        return "exec args entries must be strings"
                    if any(not entry.strip() for entry in args):
                        return "exec args entries must be non-empty strings"
                    if any(entry != entry.strip() for entry in args):
                        return "exec args entries must not contain surrounding whitespace"
                env = item.get("env")
                if "env" in item:
                    if not isinstance(env, list):
                        return "exec env must be a list"
                    for entry in env:
                        if not isinstance(entry, Mapping):
                            return "exec env entries must be objects"
                        name = entry.get("name")
                        if not isinstance(name, str) or not name.strip():
                            return "exec env entries must contain a non-empty string name"
                        if name != name.strip():
                            return "exec env entries name must not contain surrounding whitespace"
                        if not ENV_NAME_PATTERN.match(name):
                            return "exec env entries must contain a valid env name"
                        if not isinstance(entry.get("value"), str):
                            return "exec env entries must contain a string value"
                        if not entry["value"].strip():
                            return "exec env entries must contain a non-empty string value"
                        if entry["value"] != entry["value"].strip():
                            return "exec env entries value must not contain surrounding whitespace"
                if api_version == "client.authentication.k8s.io/v1" and interactive_mode is None:
                    return "exec interactiveMode must be set for client.authentication.k8s.io/v1"
                continue
            if isinstance(key, str) and key in KUBECONFIG_AUTH_STRING_FIELDS and item is not None and not isinstance(item, str):
                return f"{key} must be a string"
            if isinstance(key, str) and key in KUBECONFIG_AUTH_BOOLEAN_FIELDS and item is not None and not isinstance(item, bool):
                return f"{key} must be a boolean"
            if isinstance(key, str) and key in KUBECONFIG_AUTH_STRING_LIST_FIELDS and item is not None:
                if not isinstance(item, list):
                    return f"{key} must be a list"
                if any(not isinstance(entry, str) for entry in item):
                    return f"{key} entries must be strings"
                if any(not entry.strip() for entry in item):
                    return f"{key} entries must be non-empty strings"
                if any(entry != entry.strip() for entry in item):
                    return f"{key} entries must not contain surrounding whitespace"
            if isinstance(key, str) and key in KUBECONFIG_AUTH_OBJECT_LIST_FIELDS and item is not None:
                if not isinstance(item, list):
                    return f"{key} must be a list"
                for entry in item:
                    if not isinstance(entry, Mapping):
                        return f"{key} entries must be objects"
                    name = entry.get("name")
                    if not isinstance(name, str) or not name.strip():
                        return f"{key} entries must contain a non-empty string name"
                    if name != name.strip():
                        return f"{key} entries name must not contain surrounding whitespace"
                    if not ENV_NAME_PATTERN.match(name):
                        return f"{key} entries must contain a valid env name"
                    if not isinstance(entry.get("value"), str):
                        return f"{key} entries must contain a string value"
                    if not entry["value"].strip():
                        return f"{key} entries must contain a non-empty string value"
                    if entry["value"] != entry["value"].strip():
                        return f"{key} entries value must not contain surrounding whitespace"
            error = find_auth_type_error(item)
            if error is not None:
                return error
    if isinstance(value, list):
        for item in value:
            error = find_auth_type_error(item)
            if error is not None:
                return error
    return None


def find_user_auth_type_error(value: Mapping[str, Any]) -> str | None:
    for key, item in value.items():
        if isinstance(key, str) and key in KUBECONFIG_USER_AUTH_FIELDS:
            error = find_auth_type_error({key: item})
            if error is not None:
                return error
    return None


def validate_kubeconfig_path(path: str) -> None:
    if not path.strip():
        fail("kubeconfig path must not be empty")
    if path != path.strip():
        fail("kubeconfig path must not contain surrounding whitespace")
    kubeconfig_path = Path(path)
    if not kubeconfig_path.exists():
        fail("kubeconfig path must exist")
    if not kubeconfig_path.is_file():
        fail("kubeconfig path must be a file")
    try:
        if kubeconfig_path.stat().st_mode & 0o444 == 0:
            fail("kubeconfig path must be readable")
    except OSError as err:
        fail(f"kubeconfig path unusable: {err}")
    try:
        with kubeconfig_path.open(encoding="utf-8") as handle:
            kubeconfig = yaml.safe_load(handle)
    except yaml.YAMLError as err:
        fail(f"kubeconfig path must be valid YAML: {err}")
    except OSError as err:
        fail(f"kubeconfig path unusable: {err}")
    if not isinstance(kubeconfig, dict):
        fail("kubeconfig path must be a YAML object")
    required_fields = {
        "apiVersion": str,
        "kind": str,
        "clusters": list,
        "contexts": list,
        "current-context": str,
        "users": list,
    }
    for field, expected_type in required_fields.items():
        value = kubeconfig.get(field)
        if value is None:
            fail(f"kubeconfig path missing required field: {field}")
        if not isinstance(value, expected_type):
            fail(f"kubeconfig path field must be {expected_type.__name__}: {field}")
    for field in ("apiVersion", "kind"):
        value = kubeconfig[field]
        if not value.strip():
            fail(f"kubeconfig path {field} must not be empty")
        if value != value.strip():
            fail(f"kubeconfig path {field} must not contain surrounding whitespace")
    if kubeconfig["apiVersion"] != "v1":
        fail("kubeconfig path apiVersion must be v1")
    if kubeconfig["kind"] != "Config":
        fail("kubeconfig path kind must be Config")
    payload_fields = {
        "clusters": "cluster",
        "contexts": "context",
        "users": "user",
    }
    for field in ("clusters", "contexts", "users"):
        if not kubeconfig[field]:
            fail(f"kubeconfig path field must not be empty: {field}")
        seen_names: set[str] = set()
        for item in kubeconfig[field]:
            if not isinstance(item, dict):
                fail(f"kubeconfig path {field} entries must be objects")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                fail(f"kubeconfig path {field} entries must contain a non-empty string name")
            if name != name.strip():
                fail(f"kubeconfig path {field} name must not contain surrounding whitespace")
            if name in seen_names:
                fail(f"kubeconfig path {field} names must be unique")
            seen_names.add(name)
            payload_field = payload_fields[field]
            if not isinstance(item.get(payload_field), dict):
                fail(f"kubeconfig path {field} entries must contain a {payload_field} object")
    if not kubeconfig["current-context"].strip():
        fail("kubeconfig path current-context must not be empty")
    if kubeconfig["current-context"] != kubeconfig["current-context"].strip():
        fail("kubeconfig path current-context must not contain surrounding whitespace")
    context_names = {
        context.get("name")
        for context in kubeconfig["contexts"]
        if isinstance(context, dict) and isinstance(context.get("name"), str)
    }
    if kubeconfig["current-context"] not in context_names:
        fail("kubeconfig path current-context must reference a context")
    active_context = next(
        context
        for context in kubeconfig["contexts"]
        if isinstance(context, dict) and context.get("name") == kubeconfig["current-context"]
    )
    context_body = active_context.get("context")
    if not isinstance(context_body, dict):
        fail("kubeconfig path current-context must contain a context object")
    namespace = context_body.get("namespace")
    if "namespace" in context_body and not isinstance(namespace, str):
        fail("kubeconfig path current-context namespace must be a string")
    if isinstance(namespace, str) and not namespace.strip():
        fail("kubeconfig path current-context namespace must be a non-empty string")
    if isinstance(namespace, str) and namespace != namespace.strip():
        fail("kubeconfig path current-context namespace must not contain surrounding whitespace")
    if isinstance(namespace, str) and (
        len(namespace) > 63 or not KUBERNETES_NAMESPACE_NAME_PATTERN.fullmatch(namespace)
    ):
        fail("kubeconfig path current-context namespace must be a valid Kubernetes namespace name")
    if isinstance(namespace, str) and namespace in KUBERNETES_SYSTEM_NAMESPACES:
        fail("kubeconfig path current-context namespace must not use a Kubernetes system namespace")
    cluster_name = context_body.get("cluster")
    if not isinstance(cluster_name, str) or not cluster_name.strip():
        fail("kubeconfig path current-context cluster must not be empty")
    if cluster_name != cluster_name.strip():
        fail("kubeconfig path current-context cluster must not contain surrounding whitespace")
    cluster_names = {
        cluster.get("name")
        for cluster in kubeconfig["clusters"]
        if isinstance(cluster, dict) and isinstance(cluster.get("name"), str)
    }
    if cluster_name not in cluster_names:
        fail("kubeconfig path current-context cluster must reference a cluster")
    active_cluster = next(
        cluster for cluster in kubeconfig["clusters"] if isinstance(cluster, dict) and cluster.get("name") == cluster_name
    )
    cluster_body = active_cluster.get("cluster")
    if not isinstance(cluster_body, dict):
        fail("kubeconfig path current-context cluster must contain a cluster object")
    server = cluster_body.get("server")
    if not isinstance(server, str) or not server.strip():
        fail("kubeconfig path current-context cluster server must not be empty")
    if server != server.strip():
        fail("kubeconfig path current-context cluster server must not contain surrounding whitespace")
    parsed_server = urlparse(server)
    if parsed_server.scheme not in {"http", "https"} or not parsed_server.netloc:
        fail("kubeconfig path current-context cluster server must be an http(s) URL")
    insecure_skip_tls_verify = cluster_body.get("insecure-skip-tls-verify")
    if "insecure-skip-tls-verify" in cluster_body and not isinstance(insecure_skip_tls_verify, bool):
        fail("kubeconfig path current-context cluster insecure-skip-tls-verify must be a boolean")
    certificate_authority_data = cluster_body.get("certificate-authority-data")
    if "certificate-authority-data" in cluster_body and not isinstance(certificate_authority_data, str):
        fail("kubeconfig path current-context cluster certificate-authority-data must be a string")
    if isinstance(certificate_authority_data, str) and not certificate_authority_data.strip():
        fail("kubeconfig path current-context cluster certificate-authority-data must be a non-empty string")
    if isinstance(certificate_authority_data, str) and certificate_authority_data != certificate_authority_data.strip():
        fail("kubeconfig path current-context cluster certificate-authority-data must not contain surrounding whitespace")
    if isinstance(certificate_authority_data, str):
        try:
            base64.b64decode(certificate_authority_data, validate=True)
        except binascii.Error:
            fail("kubeconfig path current-context cluster certificate-authority-data must be valid base64")
    certificate_authority = cluster_body.get("certificate-authority")
    if "certificate-authority" in cluster_body and not isinstance(certificate_authority, str):
        fail("kubeconfig path current-context cluster certificate-authority must be a string")
    if isinstance(certificate_authority, str) and not certificate_authority.strip():
        fail("kubeconfig path current-context cluster certificate-authority must be a non-empty string")
    if isinstance(certificate_authority, str) and certificate_authority != certificate_authority.strip():
        fail("kubeconfig path current-context cluster certificate-authority must not contain surrounding whitespace")
    if isinstance(certificate_authority, str):
        certificate_authority_path = Path(certificate_authority)
        if not certificate_authority_path.is_absolute():
            certificate_authority_path = kubeconfig_path.parent / certificate_authority_path
        if not certificate_authority_path.exists():
            fail("kubeconfig path current-context cluster certificate-authority file must exist")
        if not certificate_authority_path.is_file():
            fail("kubeconfig path current-context cluster certificate-authority file must be a file")
        try:
            if certificate_authority_path.stat().st_mode & 0o444 == 0:
                fail("kubeconfig path current-context cluster certificate-authority file must be readable")
        except OSError:
            fail("kubeconfig path current-context cluster certificate-authority file must be readable")
    tls_server_name = cluster_body.get("tls-server-name")
    if "tls-server-name" in cluster_body and not isinstance(tls_server_name, str):
        fail("kubeconfig path current-context cluster tls-server-name must be a string")
    if isinstance(tls_server_name, str) and not tls_server_name.strip():
        fail("kubeconfig path current-context cluster tls-server-name must be a non-empty string")
    if isinstance(tls_server_name, str) and tls_server_name != tls_server_name.strip():
        fail("kubeconfig path current-context cluster tls-server-name must not contain surrounding whitespace")
    proxy_url = cluster_body.get("proxy-url")
    if "proxy-url" in cluster_body and not isinstance(proxy_url, str):
        fail("kubeconfig path current-context cluster proxy-url must be a string")
    if isinstance(proxy_url, str) and not proxy_url.strip():
        fail("kubeconfig path current-context cluster proxy-url must be a non-empty string")
    if isinstance(proxy_url, str) and proxy_url != proxy_url.strip():
        fail("kubeconfig path current-context cluster proxy-url must not contain surrounding whitespace")
    if isinstance(proxy_url, str) and proxy_url.strip():
        parsed_proxy_url = urlparse(proxy_url)
        if parsed_proxy_url.scheme not in {"http", "https", "socks5"} or not parsed_proxy_url.netloc:
            fail("kubeconfig path current-context cluster proxy-url must be an http(s) or socks5 URL")
    disable_compression = cluster_body.get("disable-compression")
    if "disable-compression" in cluster_body and not isinstance(disable_compression, bool):
        fail("kubeconfig path current-context cluster disable-compression must be a boolean")
    user_name = context_body.get("user")
    if not isinstance(user_name, str) or not user_name.strip():
        fail("kubeconfig path current-context user must not be empty")
    if user_name != user_name.strip():
        fail("kubeconfig path current-context user must not contain surrounding whitespace")
    user_names = {
        user.get("name")
        for user in kubeconfig["users"]
        if isinstance(user, dict) and isinstance(user.get("name"), str)
    }
    if user_name not in user_names:
        fail("kubeconfig path current-context user must reference a user")
    active_user = next(user for user in kubeconfig["users"] if isinstance(user, dict) and user.get("name") == user_name)
    user_body = active_user.get("user")
    if not isinstance(user_body, dict):
        fail("kubeconfig path current-context user must contain a user object")
    if not user_body:
        fail("kubeconfig path current-context user auth material must not be empty")
    auth_type_error = find_user_auth_type_error(user_body)
    if auth_type_error is not None:
        fail(f"kubeconfig path current-context user auth material {auth_type_error}")
    for auth_field in sorted(KUBECONFIG_TOP_LEVEL_AUTH_STRING_FIELDS):
        if auth_field in user_body and user_body.get(auth_field) is None:
            fail(f"kubeconfig path current-context user auth material {auth_field} must be a non-empty string")
        auth_value = user_body.get(auth_field)
        if isinstance(auth_value, str) and not auth_value.strip():
            fail(f"kubeconfig path current-context user auth material {auth_field} must be a non-empty string")
        if isinstance(auth_value, str) and auth_value.strip() and auth_value != auth_value.strip():
            fail(f"kubeconfig path current-context user auth material {auth_field} must not contain surrounding whitespace")
    if not has_non_empty_auth_value(user_body):
        fail("kubeconfig path current-context user auth material must contain a non-empty value")
    if has_auth_value_with_surrounding_whitespace(user_body):
        fail("kubeconfig path current-context user auth material must not contain surrounding whitespace")
    client_certificate_data = user_body.get("client-certificate-data")
    if isinstance(client_certificate_data, str):
        try:
            base64.b64decode(client_certificate_data, validate=True)
        except binascii.Error:
            fail("kubeconfig path current-context user auth material client-certificate-data must be valid base64")
    client_key_data = user_body.get("client-key-data")
    if isinstance(client_key_data, str):
        try:
            base64.b64decode(client_key_data, validate=True)
        except binascii.Error:
            fail("kubeconfig path current-context user auth material client-key-data must be valid base64")
    token_file = user_body.get("tokenFile")
    if isinstance(token_file, str):
        token_file_path = Path(token_file)
        if not token_file_path.is_absolute():
            token_file_path = kubeconfig_path.parent / token_file_path
        if not token_file_path.exists():
            fail("kubeconfig path current-context user auth material tokenFile file must exist")
        if not token_file_path.is_file():
            fail("kubeconfig path current-context user auth material tokenFile file must be a file")
        try:
            if token_file_path.stat().st_mode & 0o444 == 0:
                fail("kubeconfig path current-context user auth material tokenFile file must be readable")
        except OSError:
            fail("kubeconfig path current-context user auth material tokenFile file must be readable")
    client_certificate = user_body.get("client-certificate")
    if isinstance(client_certificate, str):
        client_certificate_path = Path(client_certificate)
        if not client_certificate_path.is_absolute():
            client_certificate_path = kubeconfig_path.parent / client_certificate_path
        if not client_certificate_path.exists():
            fail("kubeconfig path current-context user auth material client-certificate file must exist")
        if not client_certificate_path.is_file():
            fail("kubeconfig path current-context user auth material client-certificate file must be a file")
        try:
            if client_certificate_path.stat().st_mode & 0o444 == 0:
                fail("kubeconfig path current-context user auth material client-certificate file must be readable")
        except OSError:
            fail("kubeconfig path current-context user auth material client-certificate file must be readable")
    client_key = user_body.get("client-key")
    if isinstance(client_key, str):
        client_key_path = Path(client_key)
        if not client_key_path.is_absolute():
            client_key_path = kubeconfig_path.parent / client_key_path
        if not client_key_path.exists():
            fail("kubeconfig path current-context user auth material client-key file must exist")
        if not client_key_path.is_file():
            fail("kubeconfig path current-context user auth material client-key file must be a file")
        try:
            if client_key_path.stat().st_mode & 0o444 == 0:
                fail("kubeconfig path current-context user auth material client-key file must be readable")
        except OSError:
            fail("kubeconfig path current-context user auth material client-key file must be readable")


def validate_component_evidence_dir_path(path: str) -> None:
    if not path.strip():
        fail("component evidence dir path must not be empty")
    if path != path.strip():
        fail("component evidence dir path must not contain surrounding whitespace")


def validate_component_env_file_path(path: str) -> None:
    if not path.strip():
        fail("component env file path must not be empty")
    if path != path.strip():
        fail("component env file path must not contain surrounding whitespace")


def validate_component_summary_path(path: str) -> None:
    if not path.strip():
        fail("component summary path must not be empty")
    if path != path.strip():
        fail("component summary path must not contain surrounding whitespace")


def validate_component_gate_ids(gate_ids: list[str]) -> None:
    for gate_id in gate_ids:
        if gate_id != gate_id.strip():
            fail("component gate id must not contain surrounding whitespace")
        if not gate_id:
            fail("component gate id must not be empty")


def select_component_contract_gates(profile: dict[str, Any], gate_ids: list[str] | None) -> dict[str, Any]:
    if not gate_ids:
        return profile
    validate_component_gate_ids(gate_ids)
    selected_ids = list(dict.fromkeys(gate_ids))
    gates_by_id = {str(gate["id"]): gate for gate in profile.get("contract_gates", [])}
    missing = [gate_id for gate_id in selected_ids if gate_id not in gates_by_id]
    if missing:
        fail(f"unknown component gate: {', '.join(missing)}")
    selected_profile = dict(profile)
    selected_profile["contract_gates"] = [gates_by_id[gate_id] for gate_id in selected_ids]
    return selected_profile


def component_required_env_names(profile: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for gate in profile.get("contract_gates", []):
        for name in gate.get("required_env", []):
            names.add(str(name))
    return sorted(names)


def component_env_template(profile: dict[str, Any]) -> str:
    lines = [
        "# REAL-K8S-LAB-A component live required environment",
        "# Fill these values before running:",
        f"# python scripts/validate_real_k8s_profile.py --component-preflight --component-env-file <this-file> --evidence-output {COMPONENT_LIVE_RECORD_DIR}/real-k8s-component-preflight.json",
        f"# python scripts/validate_real_k8s_profile.py --component-live --component-env-file <this-file> --component-evidence-dir {COMPONENT_LIVE_RECORD_DIR}/component-gates --evidence-output {COMPONENT_LIVE_RECORD_DIR}/real-k8s-component-summary.json",
        "",
    ]
    for name in component_required_env_names(profile):
        lines.append(f'export {name}=""')
    lines.extend(["", "# Component gate env mapping"])
    for gate in profile.get("contract_gates", []):
        required_env = ", ".join(str(name) for name in gate.get("required_env", []))
        lines.append(f"# {gate['id']}: {required_env}")
    return "\n".join(lines) + "\n"


def write_component_env_template(path: Path, profile: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(component_env_template(profile), encoding="utf-8")
    except OSError as err:
        fail(f"profile output unusable: {err}")


def parse_component_env_assignment(line: str, path: Path, line_number: int) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()
    if "=" not in stripped:
        fail(f"{path}:{line_number} must be an env assignment")
    name, raw_value = stripped.split("=", 1)
    if name != name.strip() or raw_value != raw_value.strip():
        fail(f"{path}:{line_number} env assignment must not contain whitespace around '='")
    if not ENV_NAME_PATTERN.match(name):
        fail(f"{path}:{line_number} has invalid env name {name!r}")
    if raw_value == "":
        return name, ""
    try:
        tokens = shlex.split(raw_value, posix=True)
    except ValueError as err:
        fail(f"{path}:{line_number} has invalid quoted value: {err}")
    if len(tokens) != 1:
        fail(f"{path}:{line_number} env value must be one shell-quoted token")
    value = tokens[0]
    if value != value.strip():
        fail(f"{path}:{line_number} env value must not contain surrounding whitespace")
    return name, value


def load_component_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        fail(f"component env file missing: {path}")
    env: dict[str, str] = {}
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        fail(f"component env file unreadable: {err}")
    for line_number, line in enumerate(lines, 1):
        assignment = parse_component_env_assignment(line, path, line_number)
        if assignment is None:
            continue
        name, value = assignment
        if name in seen:
            fail(f"{path}:{line_number} duplicate component env assignment for {name}")
        seen.add(name)
        env[name] = value
    return env


def validate_component_env_assignments(profile: dict[str, Any], path: Path, component_env: Mapping[str, str]) -> None:
    allowed = set(component_required_env_names(profile))
    unknown = sorted(name for name in component_env if name not in allowed)
    if unknown:
        fail(f"{path} contains unknown component env assignment: {', '.join(unknown)}")


def merged_component_env(component_env_file: str | None, profile: dict[str, Any] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if component_env_file:
        component_env_path = Path(component_env_file)
        component_env = load_component_env_file(component_env_path)
        if profile is not None:
            validate_component_env_assignments(profile, component_env_path, component_env)
        env.update(component_env)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=str(PROFILE), help="real lab profile YAML")
    parser.add_argument("--live", action="store_true", help="run live kubectl checks")
    parser.add_argument("--component-live", action="store_true", help="run indexed component live gates")
    parser.add_argument("--component-preflight", action="store_true", help="check component live required env without running live gates")
    parser.add_argument(
        "--component-evidence-dir",
        default=os.getenv("ANI_REAL_K8S_COMPONENT_EVIDENCE_DIR", str(ROOT / "development-records/live/component-gates")),
        help="directory for per-component --live evidence JSON files",
    )
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG"), help="kubeconfig for live checks")
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_REAL_K8S_EVIDENCE_OUTPUT") or None,
        help="write --live evidence JSON to this path",
    )
    parser.add_argument(
        "--component-env-template-output",
        default=os.getenv("ANI_REAL_K8S_COMPONENT_ENV_TEMPLATE_OUTPUT") or None,
        help="write a fillable shell env template for --component-live",
    )
    parser.add_argument(
        "--component-env-file",
        default=os.getenv("ANI_REAL_K8S_COMPONENT_ENV_FILE") or None,
        help="load a filled component env template for --component-live without shell sourcing it",
    )
    parser.add_argument(
        "--component-gate",
        action="append",
        default=[],
        help="limit --component-live or --component-preflight to one indexed contract gate id; repeat for multiple gates",
    )
    parser.add_argument(
        "--component-report",
        default=None,
        help="read a component live/preflight summary JSON and output failed/blocked gate rerun commands",
    )
    args = parser.parse_args()

    validate_profile_path(args.profile)
    profile = load_profile(Path(args.profile))
    validate_contract(profile)
    validate_docs()
    selected_modes = [
        bool(args.live),
        bool(args.component_live),
        bool(args.component_preflight),
        bool(args.component_env_template_output),
        args.component_report is not None,
    ]
    if sum(selected_modes) > 1:
        fail("--live, --component-live, --component-preflight, --component-env-template-output and --component-report must be run separately")
    if args.component_env_file is not None and not (args.component_live or args.component_preflight or args.component_report is not None):
        fail("--component-env-file requires --component-live, --component-preflight or --component-report")
    if args.component_gate and not (args.component_live or args.component_preflight):
        fail("--component-gate requires --component-live or --component-preflight")
    if args.component_env_file is not None:
        validate_component_env_file_path(args.component_env_file)
    if args.component_report is not None:
        validate_component_summary_path(args.component_report)
    if args.evidence_output is not None:
        validate_profile_output_path(args.evidence_output)
    if args.component_env_template_output is not None:
        validate_profile_output_path(args.component_env_template_output)
    if args.component_live or args.component_report is not None:
        validate_component_evidence_dir_path(args.component_evidence_dir)
    if args.live and args.kubeconfig is not None:
        validate_kubeconfig_path(args.kubeconfig)
    if args.live:
        evidence = validate_live(profile, args.kubeconfig)
        if args.evidence_output:
            write_live_evidence(Path(args.evidence_output), evidence)
            print(f"REAL-K8S-LAB-A live checks valid; evidence written to {args.evidence_output}")
        else:
            print("REAL-K8S-LAB-A live checks valid")
    elif args.component_preflight:
        component_profile = select_component_contract_gates(profile, args.component_gate)
        evidence = validate_component_live_preflight(component_profile, merged_component_env(args.component_env_file, profile))
        if args.evidence_output:
            write_live_evidence(Path(args.evidence_output), evidence)
            print(f"REAL-K8S-LAB-A component live preflight evidence written to {args.evidence_output}")
        else:
            print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        failed_gates = failed_component_gate_ids(evidence)
        if failed_gates:
            fail(f"component live preflight failed: {', '.join(failed_gates)}")
        print("REAL-K8S-LAB-A component live preflight valid")
    elif args.component_live:
        component_profile = select_component_contract_gates(profile, args.component_gate)
        evidence = validate_component_live_gates(
            component_profile,
            Path(args.component_evidence_dir),
            env=merged_component_env(args.component_env_file, profile),
        )
        if args.evidence_output:
            write_live_evidence(Path(args.evidence_output), evidence)
            print(f"REAL-K8S-LAB-A component live gates evidence written to {args.evidence_output}")
        else:
            print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        failed_gates = failed_component_gate_ids(evidence)
        if failed_gates:
            fail(f"component live gates failed: {', '.join(failed_gates)}")
        print("REAL-K8S-LAB-A component live gates valid")
    elif args.component_env_template_output:
        write_component_env_template(Path(args.component_env_template_output), profile)
        print(f"REAL-K8S-LAB-A component env template written to {args.component_env_template_output}")
    elif args.component_report is not None:
        if args.component_env_file is not None:
            merged_component_env(args.component_env_file, profile)
        report = component_summary_report(
            profile,
            load_component_summary(Path(args.component_report)),
            component_env_file=args.component_env_file or "",
            component_evidence_dir=args.component_evidence_dir,
        )
        if args.evidence_output:
            write_live_evidence(Path(args.evidence_output), report)
            print(f"REAL-K8S-LAB-A component report written to {args.evidence_output}")
        else:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        unresolved_gates = report["unresolved_gates"]
        if unresolved_gates:
            fail(f"component report has unresolved gates: {', '.join(unresolved_gates)}")
    else:
        print("REAL-K8S-LAB-A contract valid; use --live with KUBECONFIG to verify a real lab")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
