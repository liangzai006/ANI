#!/usr/bin/env python3
"""Validate Sprint 5 M1-KUBEVIRT-LIVE-A KubeVirt VM live gate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/kubevirt-vm-live-gate.yaml"
REQUIRED_CHECKS = {
    "kubevirt-crds-ready",
    "kubevirt-control-plane-available",
    "kubevirt-vm-created",
    "kubevirt-vmi-ready",
    "kubevirt-vnc-subresource",
    "kubevirt-console-subresource",
    "kubevirt-vm-stopped",
    "kubevirt-vm-deleted",
}
KUBEVIRT_WEBSOCKET_SUBPROTOCOL = "plain.kubevirt.io"
REQUIRED_ENV = {"KUBECONFIG"}
REQUIRED_DOC_TOKENS = [
    "M1-KUBEVIRT-LIVE-A",
    "validate-kubevirt-vm-live-gate",
    "KubeVirt VM",
    "console/VNC",
]
PROFILE = "M1-KUBEVIRT-LIVE-A"
GATE_ID = "kubevirt-vm-live-gate"


def fail(message: str) -> None:
    raise SystemExit(f"KubeVirt VM live gate invalid: {message}")


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
    required_endpoints = {"kubernetes_api", "kubevirt_api", "kubevirt_subresources_api"}
    if not isinstance(endpoints, list) or required_endpoints - set(endpoints):
        fail("required_endpoints must include Kubernetes API, KubeVirt API and subresources API")
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
    namespace: str = ""
    vm_name: str = "ani-live-vm"
    container_disk_image: str = "quay.io/containerdisks/cirros:latest"
    memory: str = "256Mi"
    wait_timeout: str = "180s"
    kubeconfig: str = ""
    kubectl_binary: str = "kubectl"


class LiveRunner:
    def run(self, command: list[str], input_text: str | None = None) -> str:
        result = subprocess.run(command, input=input_text, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{' '.join(command)} failed: {detail}")
        return result.stdout


@dataclass(frozen=True)
class KubeconfigClient:
    server: str
    tls_server_name: str = ""
    certificate_authority_data: str = ""
    insecure_skip_tls_verify: bool = False
    client_certificate_data: str = ""
    client_key_data: str = ""
    token: str = ""


class WebSocketProber:
    def probe(self, config: LiveConfig, namespace: str, vm_name: str, subresource: str) -> dict[str, object]:
        client = load_kubeconfig_client(config.kubeconfig)
        return probe_websocket_session(client, namespace, vm_name, subresource)


def kubernetes_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    if not normalized:
        normalized = "ani-live-vm"
    return normalized[:63].rstrip("-")


def tenant_namespace(config: LiveConfig) -> str:
    if config.namespace.strip():
        return config.namespace.strip()
    return "ani-tenant-" + config.tenant_id.replace("_", "-")


def kubectl(config: LiveConfig, args: list[str]) -> list[str]:
    command = [config.kubectl_binary]
    if config.kubeconfig.strip():
        command.extend(["--kubeconfig", config.kubeconfig.strip()])
    command.extend(args)
    return command


def validate_live_config(config: LiveConfig) -> None:
    required = {
        "tenant_id": config.tenant_id,
        "vm_name": config.vm_name,
        "container_disk_image": config.container_disk_image,
        "memory": config.memory,
        "wait_timeout": config.wait_timeout,
        "kubeconfig": config.kubeconfig,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        fail(f"live mode requires {', '.join(missing)}")
    whitespace = [name for name, value in required.items() if value != value.strip()]
    if whitespace:
        fail(f"{', '.join(whitespace)} must not contain surrounding whitespace")
    if shutil.which(config.kubectl_binary) is None:
        fail(f"{config.kubectl_binary} is required for --live")


def vm_manifest(config: LiveConfig) -> str:
    namespace = tenant_namespace(config)
    vm_name = kubernetes_name(config.vm_name)
    return yaml.safe_dump(
        {
            "apiVersion": "kubevirt.io/v1",
            "kind": "VirtualMachine",
            "metadata": {
                "name": vm_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/part-of": "ani-platform",
                    "app.kubernetes.io/managed-by": "ani-core",
                    "ani.kubercloud.io/tenant-id": config.tenant_id,
                    "ani.kubercloud.io/live-gate": "m1-kubevirt-live-a",
                },
            },
            "spec": {
                "running": False,
                "template": {
                    "metadata": {
                        "labels": {
                            "app.kubernetes.io/part-of": "ani-platform",
                            "ani.kubercloud.io/tenant-id": config.tenant_id,
                        }
                    },
                    "spec": {
                        "domain": {
                            "devices": {"disks": [{"name": "containerdisk", "disk": {"bus": "virtio"}}]},
                            "resources": {"requests": {"memory": config.memory}},
                        },
                        "volumes": [
                            {"name": "containerdisk", "containerDisk": {"image": config.container_disk_image}}
                        ],
                    },
                },
            },
        },
        sort_keys=True,
    )


def load_json(raw: str, label: str) -> dict[str, Any]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as err:
        fail(f"{label} did not return JSON: {err}")
    if not isinstance(document, dict):
        fail(f"{label} must return a JSON object")
    return document


def assert_kubevirt_available(document: dict[str, Any]) -> None:
    items = document.get("items")
    if not isinstance(items, list) or not items:
        fail("kubectl get kubevirt -A must return at least one item")
    for item in items:
        status = item.get("status", {}) if isinstance(item, dict) else {}
        conditions = status.get("conditions", []) if isinstance(status, dict) else []
        for condition in conditions:
            if (
                isinstance(condition, dict)
                and condition.get("type") in {"Available", "Ready"}
                and condition.get("status") == "True"
            ):
                return
    fail("KubeVirt control plane must report Available or Ready")


def assert_named_kind(document: dict[str, Any], expected_kind: str, expected_name: str) -> None:
    if document.get("kind") != expected_kind:
        fail(f"observed kind = {document.get('kind')!r}, want {expected_kind!r}")
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict) or metadata.get("name") != expected_name:
        fail(f"observed {expected_kind} metadata.name must be {expected_name}")


def assert_vmi_ready(document: dict[str, Any], expected_name: str) -> None:
    assert_named_kind(document, "VirtualMachineInstance", expected_name)
    status = document.get("status", {})
    if not isinstance(status, dict):
        fail("VirtualMachineInstance status must be an object")
    if status.get("phase") == "Running":
        return
    conditions = status.get("conditions", [])
    for condition in conditions:
        if isinstance(condition, dict) and condition.get("type") == "Ready" and condition.get("status") == "True":
            return
    fail("VirtualMachineInstance must be Running or Ready")


def subresource_path(namespace: str, vm_name: str, subresource: str) -> str:
    return f"/apis/subresources.kubevirt.io/v1/namespaces/{namespace}/virtualmachineinstances/{vm_name}/{subresource}"


def select_named(items: object, name: str, item_kind: str) -> dict[str, Any]:
    if not isinstance(items, list):
        fail(f"kubeconfig {item_kind}s must be a list")
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    fail(f"kubeconfig references missing {item_kind} {name}")


def load_kubeconfig_client(path: str) -> KubeconfigClient:
    if not path.strip():
        fail("live mode requires kubeconfig for KubeVirt WebSocket session checks")
    kubeconfig_path = Path(path)
    try:
        document = yaml.safe_load(kubeconfig_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"kubeconfig not found: {path}")
    except OSError:
        fail(f"kubeconfig unreadable: {path}")
    except (UnicodeError, yaml.YAMLError):
        fail(f"kubeconfig malformed: {path}")
    if not isinstance(document, dict):
        fail("kubeconfig must be a YAML object")

    current_context = document.get("current-context")
    if not isinstance(current_context, str) or not current_context.strip():
        fail("kubeconfig current-context must be set")
    context_item = select_named(document.get("contexts"), current_context, "context")
    context = context_item.get("context")
    if not isinstance(context, dict):
        fail("kubeconfig current context must be an object")
    cluster_name = context.get("cluster")
    user_name = context.get("user")
    if not isinstance(cluster_name, str) or not cluster_name.strip():
        fail("kubeconfig current context must reference a cluster")
    if not isinstance(user_name, str) or not user_name.strip():
        fail("kubeconfig current context must reference a user")

    cluster_item = select_named(document.get("clusters"), cluster_name, "cluster")
    user_item = select_named(document.get("users"), user_name, "user")
    cluster = cluster_item.get("cluster")
    user = user_item.get("user")
    if not isinstance(cluster, dict) or not isinstance(user, dict):
        fail("kubeconfig cluster and user entries must be objects")
    server = cluster.get("server")
    if not isinstance(server, str) or not server.strip():
        fail("kubeconfig cluster server must be set")
    token = user.get("token")
    if token is None:
        token_file = user.get("tokenFile")
        if isinstance(token_file, str) and token_file.strip():
            try:
                token = Path(token_file).read_text(encoding="utf-8").strip()
            except OSError:
                fail("kubeconfig tokenFile is unreadable")
    return KubeconfigClient(
        server=server.strip(),
        tls_server_name=str(cluster.get("tls-server-name") or ""),
        certificate_authority_data=str(cluster.get("certificate-authority-data") or ""),
        insecure_skip_tls_verify=bool(cluster.get("insecure-skip-tls-verify", False)),
        client_certificate_data=str(user.get("client-certificate-data") or ""),
        client_key_data=str(user.get("client-key-data") or ""),
        token=str(token or ""),
    )


def websocket_path(namespace: str, vm_name: str, subresource: str) -> str:
    path = subresource_path(quote(namespace, safe=""), quote(vm_name, safe=""), quote(subresource, safe=""))
    if subresource == "vnc":
        path += "?" + urlencode({"preserveSession": "false"})
    return path


def websocket_url(client: KubeconfigClient, namespace: str, vm_name: str, subresource: str) -> tuple[str, str, int, str]:
    parsed = urlparse(client.server)
    if parsed.scheme not in {"http", "https"}:
        fail(f"kubeconfig cluster server must use http or https, got {parsed.scheme}")
    host = parsed.hostname
    if not host:
        fail("kubeconfig cluster server must include a host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    base_path = parsed.path.rstrip("/")
    path = base_path + websocket_path(namespace, vm_name, subresource)
    return scheme, host, port, path


def decode_pem(data: str, label: str) -> str:
    try:
        return base64.b64decode(data).decode("utf-8")
    except (ValueError, UnicodeError):
        fail(f"kubeconfig {label} must be valid base64 PEM data")


def ssl_context_for(client: KubeconfigClient) -> ssl.SSLContext:
    if client.insecure_skip_tls_verify:
        context = ssl._create_unverified_context()
    elif client.certificate_authority_data:
        context = ssl.create_default_context(cadata=decode_pem(client.certificate_authority_data, "certificate-authority-data"))
    else:
        context = ssl.create_default_context()
    if client.client_certificate_data or client.client_key_data:
        if not client.client_certificate_data or not client.client_key_data:
            fail("kubeconfig client certificate and key must both be set")
        cert_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        key_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        try:
            cert_file.write(decode_pem(client.client_certificate_data, "client-certificate-data"))
            key_file.write(decode_pem(client.client_key_data, "client-key-data"))
            cert_file.close()
            key_file.close()
            context.load_cert_chain(cert_file.name, key_file.name)
        finally:
            cert_file.close()
            key_file.close()
            for temporary_path in (cert_file.name, key_file.name):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
    return context


def recv_exact(sock: socket.socket | ssl.SSLSocket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("websocket connection closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_http_response(sock: socket.socket | ssl.SSLSocket) -> tuple[int, dict[str, str]]:
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("websocket handshake closed before response")
        raw += chunk
        if len(raw) > 65536:
            raise RuntimeError("websocket handshake response exceeded limit")
    header_text = raw.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
    lines = header_text.split("\r\n")
    status_parts = lines[0].split()
    if len(status_parts) < 2 or not status_parts[1].isdigit():
        raise RuntimeError("websocket handshake returned malformed status line")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    return int(status_parts[1]), headers


def send_ws_frame(sock: socket.socket | ssl.SSLSocket, payload: bytes, opcode: int = 2) -> None:
    mask_key = secrets.token_bytes(4)
    length = len(payload)
    header = bytearray([0x80 | opcode])
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    sock.sendall(bytes(header) + mask_key + masked)


def read_ws_payload(sock: socket.socket | ssl.SSLSocket, timeout_seconds: float) -> bytes:
    sock.settimeout(timeout_seconds)
    payloads: list[bytes] = []
    try:
        while True:
            first, second = recv_exact(sock, 2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(recv_exact(sock, 2), "big")
            elif length == 127:
                length = int.from_bytes(recv_exact(sock, 8), "big")
            mask = recv_exact(sock, 4) if masked else b""
            payload = recv_exact(sock, length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode in {1, 2, 0}:
                payloads.append(payload)
                if payloads:
                    return b"".join(payloads)
            if opcode == 8:
                return b"".join(payloads)
            if opcode == 9:
                send_ws_frame(sock, payload, opcode=10)
    except socket.timeout:
        return b"".join(payloads)


def probe_websocket_session(
    client: KubeconfigClient,
    namespace: str,
    vm_name: str,
    subresource: str,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    scheme, host, port, path = websocket_url(client, namespace, vm_name, subresource)
    raw_sock = socket.create_connection((host, port), timeout=timeout_seconds)
    with raw_sock:
        sock: socket.socket | ssl.SSLSocket = raw_sock
        if scheme == "wss":
            server_name = client.tls_server_name or host
            sock = ssl_context_for(client).wrap_socket(raw_sock, server_hostname=server_name)
        with sock:
            sock.settimeout(timeout_seconds)
            key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
            host_header = f"{host}:{port}" if port not in {80, 443} else host
            headers = [
                f"GET {path} HTTP/1.1",
                f"Host: {host_header}",
                "Connection: Upgrade",
                "Upgrade: websocket",
                "Sec-WebSocket-Version: 13",
                f"Sec-WebSocket-Key: {key}",
                f"Sec-WebSocket-Protocol: {KUBEVIRT_WEBSOCKET_SUBPROTOCOL}",
            ]
            if client.token:
                headers.append(f"Authorization: Bearer {client.token}")
            request = "\r\n".join(headers) + "\r\n\r\n"
            sock.sendall(request.encode("ascii"))
            status_code, response_headers = read_http_response(sock)
            if status_code != 101:
                raise RuntimeError(f"{subresource} websocket handshake returned HTTP {status_code}")
            expected_accept = base64.b64encode(
                hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
            ).decode("ascii")
            if response_headers.get("sec-websocket-accept") != expected_accept:
                raise RuntimeError(f"{subresource} websocket handshake returned invalid accept header")
            selected_protocol = response_headers.get("sec-websocket-protocol", "")
            if selected_protocol != KUBEVIRT_WEBSOCKET_SUBPROTOCOL:
                raise RuntimeError(f"{subresource} websocket selected unexpected subprotocol {selected_protocol!r}")
            sent_bytes = 0
            if subresource == "console":
                send_ws_frame(sock, b"\n")
                sent_bytes = 1
            received = read_ws_payload(sock, timeout_seconds)
            try:
                send_ws_frame(sock, b"", opcode=8)
            except OSError:
                pass
            return {
                "websocket_session_established": True,
                "http_status": status_code,
                "subprotocol": selected_protocol,
                "sent_bytes": sent_bytes,
                "received_bytes": len(received),
            }


def cleanup_vm(config: LiveConfig, runner: LiveRunner, namespace: str, vm_name: str) -> None:
    cleanup_commands = [
        kubectl(
            config,
            ["patch", "virtualmachine", vm_name, "-n", namespace, "--type=merge", "-p", '{"spec":{"running":false}}'],
        ),
        kubectl(
            config,
            [
                "wait",
                "--for=delete",
                f"virtualmachineinstance/{vm_name}",
                "-n",
                namespace,
                f"--timeout={config.wait_timeout}",
            ],
        ),
        kubectl(config, ["delete", "virtualmachine", vm_name, "-n", namespace, "--ignore-not-found=true"]),
        kubectl(
            config,
            ["wait", "--for=delete", f"virtualmachine/{vm_name}", "-n", namespace, f"--timeout={config.wait_timeout}"],
        ),
    ]
    for command in cleanup_commands:
        try:
            runner.run(command)
        except RuntimeError:
            pass


def run_live(
    config: LiveConfig,
    runner: LiveRunner | None = None,
    websocket_prober: WebSocketProber | None = None,
) -> dict[str, object]:
    runner = runner or LiveRunner()
    websocket_prober = websocket_prober or WebSocketProber()
    namespace = tenant_namespace(config)
    vm_name = kubernetes_name(config.vm_name)

    runner.run(kubectl(config, ["get", "crd", "virtualmachines.kubevirt.io", "-o", "json"]))
    runner.run(kubectl(config, ["get", "crd", "virtualmachineinstances.kubevirt.io", "-o", "json"]))
    assert_kubevirt_available(load_json(runner.run(kubectl(config, ["get", "kubevirt", "-A", "-o", "json"])), "kubectl get kubevirt"))

    try:
        runner.run(kubectl(config, ["apply", "-f", "-"]), input_text=vm_manifest(config))
        vm = load_json(
            runner.run(kubectl(config, ["get", "virtualmachine", vm_name, "-n", namespace, "-o", "json"])),
            "kubectl get virtualmachine",
        )
        assert_named_kind(vm, "VirtualMachine", vm_name)

        runner.run(
            kubectl(
                config,
                ["patch", "virtualmachine", vm_name, "-n", namespace, "--type=merge", "-p", '{"spec":{"running":true}}'],
            )
        )
        runner.run(
            kubectl(
                config,
                [
                    "wait",
                    "--for=condition=Ready",
                    f"virtualmachineinstance/{vm_name}",
                    "-n",
                    namespace,
                    f"--timeout={config.wait_timeout}",
                ],
            )
        )
        vmi = load_json(
            runner.run(kubectl(config, ["get", "virtualmachineinstance", vm_name, "-n", namespace, "-o", "json"])),
            "kubectl get virtualmachineinstance",
        )
        assert_vmi_ready(vmi, vm_name)

        websocket_sessions = {}
        for subresource in ("vnc", "console"):
            session = websocket_prober.probe(config, namespace, vm_name, subresource)
            if session.get("websocket_session_established") is not True:
                fail(f"{subresource} websocket session was not established")
            websocket_sessions[subresource] = session

        return {"status": "passed", "namespace": namespace, "vm": vm_name, "websocket_sessions": websocket_sessions}
    finally:
        cleanup_vm(config, runner, namespace, vm_name)


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
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="KubeVirt VM live gate YAML")
    parser.add_argument("--live", action="store_true", help="run live kubectl KubeVirt VM checks")
    parser.add_argument("--tenant-id", default=os.getenv("ANI_LIVE_TENANT_ID", "tenant-a"))
    parser.add_argument("--namespace", default=os.getenv("ANI_LIVE_NAMESPACE", ""))
    parser.add_argument("--vm-name", default=os.getenv("ANI_LIVE_KUBEVIRT_VM_NAME", "ani-live-vm"))
    parser.add_argument("--container-disk-image", default=os.getenv("ANI_LIVE_KUBEVIRT_IMAGE", "quay.io/containerdisks/cirros:latest"))
    parser.add_argument("--memory", default=os.getenv("ANI_LIVE_KUBEVIRT_MEMORY", "256Mi"))
    parser.add_argument("--wait-timeout", default=os.getenv("ANI_LIVE_KUBEVIRT_WAIT_TIMEOUT", "180s"))
    parser.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG", ""))
    parser.add_argument(
        "--evidence-output",
        default=os.getenv("ANI_KUBEVIRT_VM_LIVE_EVIDENCE_OUTPUT") or None,
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
            namespace=args.namespace,
            vm_name=args.vm_name,
            container_disk_image=args.container_disk_image,
            memory=args.memory,
            wait_timeout=args.wait_timeout,
            kubeconfig=args.kubeconfig,
        )
        validate_live_config(config)
        if args.evidence_output is not None:
            validate_evidence_output(args.evidence_output)
        result = run_live(config)
        if args.evidence_output is not None:
            write_live_evidence(Path(args.evidence_output), result)
            print(f"M1-KUBEVIRT-LIVE-A live checks valid; evidence written to {args.evidence_output}")
        else:
            print(f"M1-KUBEVIRT-LIVE-A live checks valid: {json.dumps(result, sort_keys=True)}")
    else:
        print("M1-KUBEVIRT-LIVE-A contract valid; use --live with KUBECONFIG against REAL-K8S-LAB-A")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
