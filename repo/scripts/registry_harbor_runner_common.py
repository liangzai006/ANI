#!/usr/bin/env python3
"""Shared helpers for Harbor registry live gate runners."""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import validate_registry_harbor_live_gate as harbor_gate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_HARBOR_URL = "https://docker.kubercon.local"
DEFAULT_HARBOR_USERNAME = "admin"
DEFAULT_GATEWAY_PORT = 8080
DEFAULT_KUBECTL_PROXY_PORT = 18003
DEFAULT_DATABASE_URL = "postgres://ani:ani_dev_password@localhost:5432/ani?sslmode=disable"
DEFAULT_REDIS_URL = "redis://:ani_dev_password@127.0.0.1:6379/0"


class ManagedProcess:
    def __init__(self, proc: subprocess.Popen[bytes] | None, label: str, log_path: Path | None = None) -> None:
        self.proc = proc
        self.label = label
        self.log_path = log_path

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


_managed: list[ManagedProcess] = []


def register_cleanup() -> None:
    def _cleanup() -> None:
        for item in reversed(_managed):
            item.stop()

    atexit.register(_cleanup)


def fail(message: str) -> None:
    raise SystemExit(f"registry-harbor live gate: {message}")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


def resolve_harbor_password(cli_password: str) -> str:
    if cli_password.strip():
        return cli_password.strip()
    if os.environ.get("HARBOR_PASSWORD", "").strip():
        return os.environ["HARBOR_PASSWORD"].strip()
    password_file = os.environ.get("HARBOR_PASSWORD_FILE", "").strip()
    if password_file:
        path = Path(password_file)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    fail("HARBOR_PASSWORD or HARBOR_PASSWORD_FILE is required (lab Harbor admin password)")
    return ""


def default_host_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def harbor_registry_host(harbor_url: str) -> str:
    host = urllib.parse.urlparse(harbor_url).hostname or ""
    if not host:
        fail(f"could not derive registry host from harbor url {harbor_url!r}")
    return host


def wait_http_ok(url: str, attempts: int, sleep_seconds: float) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(sleep_seconds)
    return False


def kubectl(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["kubectl", *args], text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        fail(f"kubectl {' '.join(args)} failed: {detail}")
    return result


def ensure_namespace(namespace: str) -> None:
    dry_run = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        text=True,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=dry_run.stdout,
        text=True,
        capture_output=True,
        check=True,
    )


def start_kubectl_proxy(port: int) -> ManagedProcess | None:
    proxy_url = f"http://127.0.0.1:{port}/version"
    if wait_http_ok(proxy_url, attempts=1, sleep_seconds=0):
        print(f"kubectl proxy already listening on :{port}")
        return None
    log_path = Path("/tmp/ani-kubectl-proxy-harbor.log")
    log_handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["kubectl", "proxy", f"--address=127.0.0.1", f"--port={port}", "--accept-hosts=.*"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    managed = ManagedProcess(proc, "kubectl-proxy", log_path)
    _managed.append(managed)
    if not wait_http_ok(proxy_url, attempts=30, sleep_seconds=0.2):
        fail(f"kubectl proxy failed to start; see {log_path}")
    return managed


def start_dev_gateway(
    *,
    gateway_port: int,
    kubectl_proxy_port: int,
    harbor_username: str,
    harbor_password: str,
) -> ManagedProcess | None:
    health_url = f"http://127.0.0.1:{gateway_port}/healthz"
    if wait_http_ok(health_url, attempts=1, sleep_seconds=0):
        print(f"gateway already listening on :{gateway_port}")
        return None
    gateway_bin = ROOT / "bin/ani-gateway"
    if not gateway_bin.is_file():
        fail("missing bin/ani-gateway; run: make build-gateway")
    log_path = Path("/tmp/ani-gateway-harbor-live.log")
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "ANI_AUTH_MODE": "dev",
            "SECRET_PROVIDER_MODE": "kubernetes_rest",
            "KUBERNETES_API_HOST": f"http://127.0.0.1:{kubectl_proxy_port}",
            "KUBERNETES_PROVIDER_FIELD_MANAGER": "ani-registry-pull-secret-b3-live-gate",
            "REGISTRY_PROVIDER": "harbor",
            "REGISTRY_ENDPOINT": "docker.kubercon.local",
            "REGISTRY_USERNAME": harbor_username,
            "REGISTRY_PASSWORD": harbor_password,
            "REGISTRY_SECURE": "true",
            "REGISTRY_TLS_INSECURE": "true",
            "DATABASE_URL": env.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            "GATEWAY_REDIS_URL": env.get("GATEWAY_REDIS_URL", DEFAULT_REDIS_URL),
        }
    )
    proc = subprocess.Popen([str(gateway_bin)], stdout=log_handle, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
    managed = ManagedProcess(proc, "ani-gateway", log_path)
    _managed.append(managed)
    if not wait_http_ok(health_url, attempts=60, sleep_seconds=0.25):
        fail(f"ani-gateway failed to start; see {log_path}")
    return managed


def push_artifact_test_image(
    *,
    harbor_registry_host: str,
    harbor_username: str,
    harbor_password: str,
    tenant_id: str,
    repository: str,
    image_tag: str,
    source_image: str,
    skip_docker_push: bool,
) -> str:
    harbor_project = harbor_gate.harbor_provider_project_name(
        tenant_id, harbor_gate.DEFAULT_REGISTRY_PROJECT_NAME
    )
    target_image = f"{harbor_registry_host}/{harbor_project}/{repository}:{image_tag}"
    if skip_docker_push:
        print(f"SKIP_DOCKER_PUSH=true; using existing image {target_image}")
        return target_image
    docker = shutil_which("docker")
    if docker is None:
        fail("docker is required to push Harbor test image for artifact-track gate")
    subprocess.run(
        [docker, "login", harbor_registry_host, "-u", harbor_username, "--password-stdin"],
        input=harbor_password,
        text=True,
        check=True,
        capture_output=True,
    )
    subprocess.run([docker, "pull", source_image], check=True)
    subprocess.run([docker, "tag", source_image, target_image], check=True)
    subprocess.run([docker, "push", target_image], check=True)
    print(f"pushed {target_image}")
    return target_image


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)
