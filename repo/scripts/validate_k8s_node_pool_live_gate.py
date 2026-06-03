#!/usr/bin/env python3
"""Validate Sprint 5 M1-K8S-LIVE-B K8s node pool live gate."""

from __future__ import annotations

import argparse
import json
import os
import re
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
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/k8s-node-pool-live-gate.yaml"
REQUIRED_CHECKS = {
    "core-create-node-pool",
    "clusterapi-machinedeployment-created",
    "core-scale-node-pool",
    "clusterapi-machinedeployment-scaled",
    "clusterapi-machinesets-ready",
    "clusterapi-machines-ready",
    "capk-kubevirtmachines-ready",
    "capk-vms-ready",
    "gpu-workload-scheduled",
}
REQUIRED_ENV = {"KUBECONFIG", "ANI_GATEWAY_URL", "ANI_BEARER_TOKEN", "ANI_LIVE_K8S_CLUSTER_ID"}
REQUIRED_DOC_TOKENS = [
    "M1-K8S-LIVE-B",
    "validate-k8s-node-pool-live-gate",
    "Cluster API",
    "GPU",
]
PROFILE = "M1-K8S-LIVE-B"
GATE_ID = "k8s-node-pool-live-gate"


def fail(message: str) -> None:
    raise SystemExit(f"K8s node pool live gate invalid: {message}")


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
    if not isinstance(tools, list) or "kubectl" not in tools:
        fail("required_tools must include kubectl")
    endpoints = document.get("required_endpoints")
    required_endpoints = {"ani_gateway_api_v1", "kubernetes_api", "cluster_api"}
    if not isinstance(endpoints, list) or required_endpoints - set(endpoints):
        fail("required_endpoints must include Gateway, Kubernetes API and Cluster API")
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
    node_pool_name: str = "gpu-pool"
    instance_type: str = "gpu.l4.xlarge"
    initial_node_count: int = 1
    scaled_node_count: int = 2
    gpu_vendor: str = "nvidia"
    gpu_model: str = "L4"
    gpu_count: int = 1
    gpu_resource_name: str = "nvidia.com/gpu"
    kubeconfig: str = ""
    workload_kubeconfig: str = ""
    kubectl_binary: str = "kubectl"
    gpu_smoke_pod_name: str = "ani-node-pool-gpu-smoke"
    readiness_timeout_seconds: int = 600
    readiness_poll_seconds: int = 10


class LiveRunner:
    def request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, object],
        bearer_token: str,
        tenant_id: str,
    ) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "content-type": "application/json",
                "authorization": "Bearer " + bearer_token,
                "x-dev-tenant-id": tenant_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} returned HTTP {err.code}: {detail}") from err

    def post_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str) -> dict[str, object]:
        return self.request_json("POST", url, payload, bearer_token, tenant_id)

    def patch_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str) -> dict[str, object]:
        return self.request_json("PATCH", url, payload, bearer_token, tenant_id)

    def run(self, command: list[str], input_text: str | None = None) -> str:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{' '.join(command)} failed: {detail}")
        return result.stdout


def tenant_namespace(tenant_id: str) -> str:
    return "ani-tenant-" + tenant_id.replace("_", "-")


def kubernetes_name(name: str) -> str:
    lowered = name.lower()
    normalized = re.sub(r"[^a-z0-9-]+", "-", lowered).strip("-")
    if not normalized:
        normalized = "node-pool"
    return normalized[:63].rstrip("-")


def validate_live_fields(config: LiveConfig) -> None:
    required = {
        "tenant_id": config.tenant_id,
        "cluster_id": config.cluster_id,
        "gateway_url": config.gateway_url,
        "ani_bearer_token": config.ani_bearer_token,
        "node_pool_name": config.node_pool_name,
        "instance_type": config.instance_type,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    if config.initial_node_count <= 0:
        fail("initial_node_count must be greater than zero")
    if config.scaled_node_count <= 0:
        fail("scaled_node_count must be greater than zero")
    if config.initial_node_count == config.scaled_node_count:
        fail("scaled_node_count must differ from initial_node_count")
    if config.gpu_count < 0:
        fail("gpu_count cannot be negative")
    if config.gpu_count > 0 and not config.gpu_resource_name.strip():
        fail("gpu_resource_name is required when gpu_count is greater than zero")
    if config.readiness_timeout_seconds < 0:
        fail("readiness_timeout_seconds cannot be negative")
    if config.readiness_poll_seconds <= 0:
        fail("readiness_poll_seconds must be greater than zero")


def validate_live_config(config: LiveConfig) -> None:
    validate_live_fields(config)
    if shutil.which(config.kubectl_binary) is None:
        fail(f"{config.kubectl_binary} is required for --live")


def kubectl(config: LiveConfig, args: list[str], *, workload: bool = False) -> list[str]:
    command = [config.kubectl_binary]
    kubeconfig = config.workload_kubeconfig if workload and config.workload_kubeconfig else config.kubeconfig
    if kubeconfig.strip():
        command.extend(["--kubeconfig", kubeconfig.strip()])
    command.extend(args)
    return command


def load_kubernetes_json(config: LiveConfig, runner: LiveRunner, args: list[str], description: str) -> dict[str, Any]:
    raw = runner.run(kubectl(config, args))
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as err:
        fail(f"{description} did not return JSON: {err}")
    if not isinstance(document, dict):
        fail(f"{description} must return a JSON object")
    return document


def list_items(document: dict[str, Any], description: str) -> list[dict[str, Any]]:
    items = document.get("items")
    if not isinstance(items, list):
        fail(f"{description} must include items")
    typed_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            fail(f"{description} items must be objects")
        typed_items.append(item)
    return typed_items


def object_name(document: dict[str, Any]) -> str:
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("name") or "")


def condition_true(document: dict[str, Any], condition_type: str) -> bool:
    status = document.get("status", {})
    conditions = status.get("conditions", []) if isinstance(status, dict) else []
    if not isinstance(conditions, list):
        return False
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        if condition.get("type") == condition_type and str(condition.get("status")) == "True":
            return True
    return False


def status_int(document: dict[str, Any], field: str) -> int:
    status = document.get("status", {})
    if not isinstance(status, dict):
        return 0
    try:
        return int(status.get(field, 0) or 0)
    except (TypeError, ValueError):
        return 0


def phase_or_status(document: dict[str, Any]) -> str:
    status = document.get("status", {})
    if not isinstance(status, dict):
        return ""
    return str(status.get("phase") or status.get("printableStatus") or "")


def vm_ready(document: dict[str, Any]) -> bool:
    return condition_true(document, "Ready") or phase_or_status(document) in {"Running", "Ready"}


def vmi_ready(document: dict[str, Any]) -> bool:
    return condition_true(document, "Ready") and phase_or_status(document) == "Running"


def owner_machine_name(machine: dict[str, Any]) -> str:
    metadata = machine.get("metadata", {})
    owners = metadata.get("ownerReferences", []) if isinstance(metadata, dict) else []
    if not isinstance(owners, list):
        return ""
    for owner in owners:
        if not isinstance(owner, dict):
            continue
        if owner.get("kind") == "MachineSet":
            return str(owner.get("name") or "")
    return ""


def has_owner(document: dict[str, Any], kind: str, name: str) -> bool:
    metadata = document.get("metadata", {})
    owners = metadata.get("ownerReferences", []) if isinstance(metadata, dict) else []
    if not isinstance(owners, list):
        return False
    for owner in owners:
        if not isinstance(owner, dict):
            continue
        if owner.get("kind") == kind and owner.get("name") == name:
            return True
    return False


def has_label(document: dict[str, Any], key: str, value: str) -> bool:
    metadata = document.get("metadata", {})
    labels = metadata.get("labels", {}) if isinstance(metadata, dict) else {}
    return isinstance(labels, dict) and labels.get(key) == value


def machine_infrastructure_ref_name(machine: dict[str, Any]) -> str:
    spec = machine.get("spec", {})
    infrastructure_ref = spec.get("infrastructureRef", {}) if isinstance(spec, dict) else {}
    if not isinstance(infrastructure_ref, dict):
        return ""
    return str(infrastructure_ref.get("name") or "")


def gpu_workload_manifest(namespace: str, pod_name: str, gpu_resource_name: str) -> str:
    return json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": pod_name, "namespace": namespace},
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "gpu-smoke",
                        "image": "nvidia/cuda:12.4.1-base-ubuntu22.04",
                        "command": ["sh", "-c", "nvidia-smi || true; sleep 5"],
                        "resources": {"limits": {gpu_resource_name: 1}},
                    }
                ],
            },
        },
        indent=2,
        sort_keys=True,
    )


def assert_real_node_pool_response(response: dict[str, Any]) -> str:
    node_pool_id = str(response.get("id") or response.get("node_pool_id") or "")
    if not node_pool_id:
        fail("Core node pool response missing node pool id")
    profile = response.get("dev_profile", {})
    if not isinstance(profile, dict) or profile.get("mode") != "real" or not profile.get("real_provider"):
        fail("Core node pool response must be provider-backed real dev profile")
    return node_pool_id


def load_machine_deployment(config: LiveConfig, runner: LiveRunner, namespace: str, name: str) -> dict[str, Any]:
    return load_kubernetes_json(config, runner, ["get", "machinedeployment", name, "-n", namespace, "-o", "json"], "kubectl get machinedeployment")


def machine_deployment_spec_replicas(document: dict[str, Any]) -> int:
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        fail("MachineDeployment spec must be an object")
    try:
        return int(spec.get("replicas", -1))
    except (TypeError, ValueError):
        fail("MachineDeployment spec.replicas must be an integer")


def assert_machine_deployment(document: dict[str, Any], expected_replicas: int | None, node_pool_id: str, config: LiveConfig) -> None:
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict):
        fail("MachineDeployment metadata must be an object")
    labels = metadata.get("labels", {})
    if not isinstance(labels, dict) or labels.get("ani.kubercloud.io/node-pool-id") != node_pool_id:
        fail("MachineDeployment missing ANI node pool id label")
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        fail("MachineDeployment spec must be an object")
    if expected_replicas is not None and machine_deployment_spec_replicas(document) != expected_replicas:
        fail(f"MachineDeployment replicas must be {expected_replicas}")
    template = spec.get("template", {})
    template_metadata = template.get("metadata", {}) if isinstance(template, dict) else {}
    template_labels = template_metadata.get("labels", {}) if isinstance(template_metadata, dict) else {}
    template_annotations = template_metadata.get("annotations", {}) if isinstance(template_metadata, dict) else {}
    if not isinstance(template_labels, dict):
        fail("MachineDeployment template.metadata.labels must be an object")
    if not isinstance(template_annotations, dict):
        fail("MachineDeployment template.metadata.annotations must be an object")
    machine_spec = template.get("spec", {}) if isinstance(template, dict) else {}
    if not isinstance(machine_spec, dict):
        fail("MachineDeployment template.spec must be an object")
    for required_field in ("bootstrap", "clusterName", "infrastructureRef"):
        if required_field not in machine_spec:
            fail(f"MachineDeployment template.spec.{required_field} is required for Cluster API")
    if config.gpu_count > 0:
        if template_labels.get("ani.kubercloud.io/gpu-vendor") != config.gpu_vendor:
            fail("MachineDeployment template metadata must preserve GPU vendor intent")
        if template_labels.get("ani.kubercloud.io/gpu-model") != config.gpu_model:
            fail("MachineDeployment template metadata must preserve GPU model intent")
        if str(template_annotations.get("ani.kubercloud.io/gpu-count", "")) != str(config.gpu_count):
            fail("MachineDeployment template metadata must preserve GPU count intent")
        if template_annotations.get("ani.kubercloud.io/gpu-resource-name") != config.gpu_resource_name:
            fail("MachineDeployment template metadata must preserve GPU resource intent")


def assert_machine_deployment_ready(document: dict[str, Any], expected_replicas: int) -> None:
    if not condition_true(document, "Available"):
        fail("MachineDeployment must have Available condition True")
    for field in ("replicas", "readyReplicas", "availableReplicas", "upToDateReplicas"):
        if status_int(document, field) != expected_replicas:
            fail(f"MachineDeployment status.{field} must be {expected_replicas}")


def assert_machine_sets_ready(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    machine_deployment_name: str,
    node_pool_id: str,
    expected_replicas: int,
) -> dict[str, object]:
    document = load_kubernetes_json(config, runner, ["get", "machineset", "-n", namespace, "-o", "json"], "kubectl get machineset")
    items = [
        item
        for item in list_items(document, "MachineSet list")
        if has_label(item, "ani.kubercloud.io/node-pool-id", node_pool_id) or has_owner(item, "MachineDeployment", machine_deployment_name)
    ]
    if not items:
        fail("no MachineSet found for node pool")
    ready_names: list[str] = []
    spec_replicas = status_replicas = ready_replicas = available_replicas = up_to_date_replicas = 0
    for item in items:
        spec = item.get("spec", {})
        if not isinstance(spec, dict):
            fail("MachineSet spec must be an object")
        try:
            spec_replicas += int(spec.get("replicas", 0) or 0)
        except (TypeError, ValueError):
            fail("MachineSet spec.replicas must be an integer")
        status_replicas += status_int(item, "replicas")
        ready_replicas += status_int(item, "readyReplicas")
        available_replicas += status_int(item, "availableReplicas")
        up_to_date_replicas += status_int(item, "upToDateReplicas")
        if condition_true(item, "Ready") or status_int(item, "readyReplicas") > 0:
            ready_names.append(object_name(item))
    totals = {
        "spec_replicas": spec_replicas,
        "status_replicas": status_replicas,
        "ready_replicas": ready_replicas,
        "available_replicas": available_replicas,
        "up_to_date_replicas": up_to_date_replicas,
    }
    for label, count in totals.items():
        if count != expected_replicas:
            fail(f"MachineSet aggregate {label} must be {expected_replicas}")
    return {
        "count": len(items),
        "names": [object_name(item) for item in items],
        **totals,
        "ready_names": ready_names,
    }


def machine_internal_ips(machine: dict[str, Any]) -> list[str]:
    status = machine.get("status", {})
    addresses = status.get("addresses", []) if isinstance(status, dict) else []
    if not isinstance(addresses, list):
        return []
    ips: list[str] = []
    for address in addresses:
        if not isinstance(address, dict):
            continue
        if address.get("type") == "InternalIP" and address.get("address"):
            ips.append(str(address["address"]))
    return ips


def assert_machines_ready(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    node_pool_id: str,
    expected_replicas: int,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    document = load_kubernetes_json(
        config,
        runner,
        ["get", "machine", "-n", namespace, "-l", f"ani.kubercloud.io/node-pool-id={node_pool_id}", "-o", "json"],
        "kubectl get machine",
    )
    machines = list_items(document, "Machine list")
    if len(machines) != expected_replicas:
        fail(f"Machine count must be {expected_replicas}")
    ready_names: list[str] = []
    internal_ips: dict[str, list[str]] = {}
    provider_ids: dict[str, str] = {}
    infrastructure_refs: list[str] = []
    for machine in machines:
        name = object_name(machine)
        if not name:
            fail("Machine metadata.name is required")
        if not condition_true(machine, "Ready"):
            fail(f"Machine {name} must have Ready condition True")
        if not condition_true(machine, "Available"):
            fail(f"Machine {name} must have Available condition True")
        status = machine.get("status", {})
        node_ref = status.get("nodeRef", {}) if isinstance(status, dict) else {}
        if not isinstance(node_ref, dict) or not node_ref.get("name"):
            fail(f"Machine {name} must have status.nodeRef")
        spec = machine.get("spec", {})
        provider_id = str(spec.get("providerID") or "") if isinstance(spec, dict) else ""
        if not provider_id:
            fail(f"Machine {name} must have spec.providerID")
        ips = machine_internal_ips(machine)
        if not ips:
            fail(f"Machine {name} must have an InternalIP")
        infra_ref_name = machine_infrastructure_ref_name(machine)
        if not infra_ref_name:
            fail(f"Machine {name} must have spec.infrastructureRef.name")
        ready_names.append(name)
        internal_ips[name] = ips
        provider_ids[name] = provider_id
        infrastructure_refs.append(infra_ref_name)
    return machines, {
        "count": len(machines),
        "ready_count": len(ready_names),
        "names": ready_names,
        "internal_ips": internal_ips,
        "provider_ids": provider_ids,
        "infrastructure_refs": infrastructure_refs,
    }


def assert_kubevirt_machines_ready(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    infrastructure_ref_names: list[str],
) -> dict[str, object]:
    document = load_kubernetes_json(config, runner, ["get", "kubevirtmachine", "-n", namespace, "-o", "json"], "kubectl get kubevirtmachine")
    expected = set(infrastructure_ref_names)
    items = [item for item in list_items(document, "KubevirtMachine list") if object_name(item) in expected]
    if len(items) != len(expected):
        fail("KubevirtMachine count must match Machine infrastructure refs")
    ready_names: list[str] = []
    for item in items:
        name = object_name(item)
        if not condition_true(item, "Ready"):
            fail(f"KubevirtMachine {name} must have Ready condition True")
        ready_names.append(name)
    return {"count": len(items), "ready_count": len(ready_names), "names": ready_names}


def assert_vms_ready(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    expected_names: list[str],
) -> dict[str, object]:
    expected = set(expected_names)
    vm_document = load_kubernetes_json(config, runner, ["get", "vm", "-n", namespace, "-o", "json"], "kubectl get vm")
    vmi_document = load_kubernetes_json(config, runner, ["get", "vmi", "-n", namespace, "-o", "json"], "kubectl get vmi")
    vms = [item for item in list_items(vm_document, "VirtualMachine list") if object_name(item) in expected]
    vmis = [item for item in list_items(vmi_document, "VirtualMachineInstance list") if object_name(item) in expected]
    if len(vms) != len(expected):
        fail("VirtualMachine count must match KubevirtMachine names")
    if len(vmis) != len(expected):
        fail("VirtualMachineInstance count must match KubevirtMachine names")
    ready_vms: list[str] = []
    ready_vmis: list[str] = []
    for vm in vms:
        name = object_name(vm)
        if not vm_ready(vm):
            fail(f"VirtualMachine {name} must be Running/Ready")
        ready_vms.append(name)
    for vmi in vmis:
        name = object_name(vmi)
        if not vmi_ready(vmi):
            fail(f"VirtualMachineInstance {name} must be Running and Ready")
        ready_vmis.append(name)
    return {
        "vm_count": len(vms),
        "vm_ready_count": len(ready_vms),
        "vm_names": ready_vms,
        "vmi_count": len(vmis),
        "vmi_ready_count": len(ready_vmis),
        "vmi_names": ready_vmis,
    }


def observe_node_pool_readiness(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    machine_deployment_name: str,
    node_pool_id: str,
    expected_replicas: int,
) -> dict[str, object]:
    machine_deployment = load_machine_deployment(config, runner, namespace, machine_deployment_name)
    assert_machine_deployment(machine_deployment, expected_replicas, node_pool_id, config)
    assert_machine_deployment_ready(machine_deployment, expected_replicas)
    machine_sets = assert_machine_sets_ready(config, runner, namespace, machine_deployment_name, node_pool_id, expected_replicas)
    machines, machine_summary = assert_machines_ready(config, runner, namespace, node_pool_id, expected_replicas)
    infrastructure_ref_names = [machine_infrastructure_ref_name(machine) for machine in machines]
    kubevirt_machine_summary = assert_kubevirt_machines_ready(config, runner, namespace, infrastructure_ref_names)
    vm_summary = assert_vms_ready(config, runner, namespace, infrastructure_ref_names)
    return {
        "machine_deployment": {
            "name": machine_deployment_name,
            "replicas": expected_replicas,
            "ready_replicas": status_int(machine_deployment, "readyReplicas"),
            "available_replicas": status_int(machine_deployment, "availableReplicas"),
            "up_to_date_replicas": status_int(machine_deployment, "upToDateReplicas"),
        },
        "machine_sets": machine_sets,
        "machines": machine_summary,
        "kubevirt_machines": kubevirt_machine_summary,
        "virtual_machines": vm_summary,
    }


def wait_for_node_pool_readiness(
    config: LiveConfig,
    runner: LiveRunner,
    namespace: str,
    machine_deployment_name: str,
    node_pool_id: str,
    expected_replicas: int,
) -> dict[str, object]:
    deadline = time.monotonic() + max(config.readiness_timeout_seconds, 0)
    last_error: SystemExit | None = None
    while True:
        try:
            return observe_node_pool_readiness(config, runner, namespace, machine_deployment_name, node_pool_id, expected_replicas)
        except SystemExit as err:
            last_error = err
            if time.monotonic() >= deadline:
                raise last_error
            time.sleep(max(config.readiness_poll_seconds, 1))


def run_gpu_workload_check(config: LiveConfig, runner: LiveRunner, namespace: str) -> None:
    if config.gpu_count <= 0:
        return
    runner.run(kubectl(config, ["delete", "pod", config.gpu_smoke_pod_name, "-n", namespace, "--ignore-not-found=true"], workload=True))
    runner.run(
        kubectl(config, ["apply", "-f", "-"], workload=True),
        input_text=gpu_workload_manifest(namespace, config.gpu_smoke_pod_name, config.gpu_resource_name),
    )
    runner.run(
        kubectl(
            config,
            ["wait", "--for=condition=PodScheduled", f"pod/{config.gpu_smoke_pod_name}", "-n", namespace, "--timeout=180s"],
            workload=True,
        )
    )


def run_live(config: LiveConfig, runner: LiveRunner | None = None) -> dict[str, object]:
    validate_live_fields(config)
    runner = runner or LiveRunner()
    gateway = config.gateway_url.rstrip("/")
    namespace = tenant_namespace(config.tenant_id)
    machine_deployment_name = kubernetes_name(config.node_pool_name)
    gpu = {
        "vendor": config.gpu_vendor,
        "model": config.gpu_model,
        "count": config.gpu_count,
        "resource_name": config.gpu_resource_name,
    }

    created = runner.post_json(
        gateway + f"/k8s-clusters/{config.cluster_id}/node-pools",
        {
            "idempotency_key": f"node-pool-live-{config.cluster_id}-{config.node_pool_name}",
            "name": config.node_pool_name,
            "node_count": config.initial_node_count,
            "instance_type": config.instance_type,
            "gpu": gpu,
        },
        config.ani_bearer_token,
        config.tenant_id,
    )
    node_pool_id = assert_real_node_pool_response(created)
    machine_deployment = load_machine_deployment(config, runner, namespace, machine_deployment_name)
    observed_create_replicas = machine_deployment_spec_replicas(machine_deployment)
    create_replica_check = "matched_create_request"
    create_expected_replicas: int | None = config.initial_node_count
    if observed_create_replicas != config.initial_node_count:
        create_expected_replicas = None
        create_replica_check = f"existing_replicas_{observed_create_replicas}"
    assert_machine_deployment(machine_deployment, create_expected_replicas, node_pool_id, config)

    updated = runner.patch_json(
        gateway + f"/k8s-clusters/{config.cluster_id}/node-pools/{node_pool_id}",
        {
            "idempotency_key": f"node-pool-live-scale-{config.cluster_id}-{node_pool_id}",
            "node_count": config.scaled_node_count,
            "instance_type": config.instance_type,
            "gpu": gpu,
        },
        config.ani_bearer_token,
        config.tenant_id,
    )
    assert_real_node_pool_response(updated)
    readiness = wait_for_node_pool_readiness(config, runner, namespace, machine_deployment_name, node_pool_id, config.scaled_node_count)
    run_gpu_workload_check(config, runner, namespace)

    return {
        "status": "passed",
        "node_pool_id": node_pool_id,
        "machine_deployment": machine_deployment_name,
        "machine_deployment_create_replica_check": create_replica_check,
        "namespace": namespace,
        "scaled_replicas": config.scaled_node_count,
        "readiness": readiness,
        "gpu_workload": config.gpu_smoke_pod_name if config.gpu_count > 0 else "",
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
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="K8s node pool live gate YAML")
    parser.add_argument("--live", action="store_true", help="run live Core/Cluster API/GPU scheduling checks")
    parser.add_argument("--tenant-id", default=os.getenv("ANI_LIVE_TENANT_ID", "tenant-a"))
    parser.add_argument("--cluster-id", default=os.getenv("ANI_LIVE_K8S_CLUSTER_ID", ""))
    parser.add_argument("--gateway-url", default=os.getenv("ANI_GATEWAY_URL", ""))
    parser.add_argument("--ani-bearer-token", default=os.getenv("ANI_BEARER_TOKEN", ""))
    parser.add_argument("--node-pool-name", default=os.getenv("ANI_LIVE_NODE_POOL_NAME", "gpu-pool"))
    parser.add_argument("--instance-type", default=os.getenv("ANI_LIVE_NODE_POOL_INSTANCE_TYPE", "gpu.l4.xlarge"))
    parser.add_argument("--initial-node-count", type=int, default=int(os.getenv("ANI_LIVE_NODE_POOL_INITIAL_COUNT", "1")))
    parser.add_argument("--scaled-node-count", type=int, default=int(os.getenv("ANI_LIVE_NODE_POOL_SCALED_COUNT", "2")))
    parser.add_argument("--gpu-vendor", default=os.getenv("ANI_LIVE_NODE_POOL_GPU_VENDOR", "nvidia"))
    parser.add_argument("--gpu-model", default=os.getenv("ANI_LIVE_NODE_POOL_GPU_MODEL", "L4"))
    parser.add_argument("--gpu-count", type=int, default=int(os.getenv("ANI_LIVE_NODE_POOL_GPU_COUNT", "1")))
    parser.add_argument("--gpu-resource-name", default=os.getenv("ANI_LIVE_NODE_POOL_GPU_RESOURCE", "nvidia.com/gpu"))
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG", ""))
    parser.add_argument("--workload-kubeconfig", default=os.getenv("ANI_WORKLOAD_KUBECONFIG", ""))
    parser.add_argument("--readiness-timeout-seconds", type=int, default=int(os.getenv("ANI_LIVE_NODE_POOL_READINESS_TIMEOUT_SECONDS", "600")))
    parser.add_argument("--readiness-poll-seconds", type=int, default=int(os.getenv("ANI_LIVE_NODE_POOL_READINESS_POLL_SECONDS", "10")))
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_K8S_NODE_POOL_LIVE_EVIDENCE_OUTPUT") or None,
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
            node_pool_name=args.node_pool_name,
            instance_type=args.instance_type,
            initial_node_count=args.initial_node_count,
            scaled_node_count=args.scaled_node_count,
            gpu_vendor=args.gpu_vendor,
            gpu_model=args.gpu_model,
            gpu_count=args.gpu_count,
            gpu_resource_name=args.gpu_resource_name,
            kubeconfig=args.kubeconfig,
            workload_kubeconfig=args.workload_kubeconfig,
            readiness_timeout_seconds=args.readiness_timeout_seconds,
            readiness_poll_seconds=args.readiness_poll_seconds,
        )
        validate_live_config(config)
        if args.evidence_output is not None:
            validate_evidence_output(args.evidence_output)
        result = run_live(config)
        if args.evidence_output is not None:
            write_live_evidence(Path(args.evidence_output), result)
            print(f"M1-K8S-LIVE-B live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"M1-K8S-LIVE-B live checks valid: {json.dumps(result, sort_keys=True)}")
    else:
        print("M1-K8S-LIVE-B contract valid; use --live with ANI_GATEWAY_URL, ANI_BEARER_TOKEN and KUBECONFIG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
