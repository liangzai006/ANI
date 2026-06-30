#!/usr/bin/env python3
"""Run Sprint 13 / Gateway metadata Harbor registry live gates (Python unified runner).

Tracks (--track):
  production              P6-B1 base / dev Gateway production-shaped gate
  in-cluster              P6-B1 in-cluster NodePort :30080 + bearer token
  artifact                P6-B2 docker push + artifacts + scan-result
  pull-secret-kubernetes  P6-B3 Harbor robot -> K8s imagePullSecret

Use --dev with pull-secret-kubernetes to orchestrate kubectl proxy + local Gateway.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Literal

import validate_registry_harbor_live_gate as harbor_gate

import registry_harbor_runner_common as common


Track = Literal["production", "in-cluster", "artifact", "pull-secret-kubernetes"]

TRACK_DEFAULTS: dict[Track, dict[str, str]] = {
    "production": {
        "run_id": "sprint13-registry-harbor",
        "evidence_output": "development-records/live-evidence/sprint13-registry-harbor-live-evidence.json",
    },
    "in-cluster": {
        "run_id": "sprint13-registry-harbor-in-cluster",
        "evidence_output": (
            "development-records/live-evidence/sprint13-registry-harbor-in-cluster-live-evidence.json"
        ),
    },
    "artifact": {
        "run_id": "sprint13-registry-harbor-b2",
        "evidence_output": "development-records/live-evidence/sprint13-registry-harbor-b2-live-evidence.json",
    },
    "pull-secret-kubernetes": {
        "run_id": "sprint13-registry-harbor-b3",
        "evidence_output": "development-records/live-evidence/sprint13-registry-harbor-b3-live-evidence.json",
    },
}


@dataclass(frozen=True)
class RunnerConfig:
    track: Track
    dev: bool
    gateway_url: str
    harbor_url: str
    harbor_username: str
    harbor_password: str
    tenant_id: str
    repository: str
    image_tag: str
    scan_image: str
    pull_secret_kubernetes_namespace: str
    pull_secret_kubernetes_name: str
    ani_bearer_token: str
    production_shaped: bool
    artifact_track: bool
    pull_secret_kubernetes_track: bool
    cleanup: bool
    run_id: str
    evidence_output: str
    harbor_tls_insecure: bool
    gateway_port: int
    kubectl_proxy_port: int
    skip_gateway_start: bool
    skip_kubectl_proxy: bool
    skip_docker_push: bool
    source_image: str


def build_config(args: argparse.Namespace, harbor_password: str) -> RunnerConfig:
    track: Track = args.track
    defaults = TRACK_DEFAULTS[track]
    tenant_id = (args.tenant_id or os.environ.get("TENANT_ID", common.DEFAULT_TENANT_ID)).strip()
    run_id = (args.run_id or os.environ.get("RUN_ID", defaults["run_id"])).strip()
    if track == "pull-secret-kubernetes" and args.dev and run_id == defaults["run_id"]:
        run_id = os.environ.get("RUN_ID", f"{defaults['run_id']}-dev").strip()

    gateway_port = args.gateway_port or common.env_int("GATEWAY_PORT", common.DEFAULT_GATEWAY_PORT)
    if track == "in-cluster":
        node_ip = os.environ.get("GATEWAY_NODE_IP", "").strip() or common.default_host_ip()
        node_port = common.env_int("GATEWAY_NODE_PORT", 30080)
        gateway_url = (args.gateway_url or os.environ.get("GATEWAY_URL", "")).strip()
        if not gateway_url:
            gateway_url = f"http://{node_ip}:{node_port}/api/v1"
    else:
        host_ip = os.environ.get("HOST_IP", "").strip() or common.default_host_ip()
        gateway_url = (args.gateway_url or os.environ.get("GATEWAY_URL", "")).strip()
        if not gateway_url:
            gateway_url = f"http://{host_ip}:{gateway_port}/api/v1"

    repository = (
        args.repository or os.environ.get("REGISTRY_REPOSITORY", harbor_gate.DEFAULT_ARTIFACT_REPOSITORY)
    ).strip()
    image_tag = (args.image_tag or os.environ.get("REGISTRY_IMAGE_TAG", harbor_gate.DEFAULT_ARTIFACT_TAG)).strip()
    scan_image = (
        args.scan_image
        or os.environ.get("REGISTRY_SCAN_IMAGE", "")
        or harbor_gate.default_scan_image_for_tenant(tenant_id, repository, image_tag)
    ).strip()

    namespace = (
        args.pull_secret_kubernetes_namespace
        or os.environ.get("PULL_SECRET_K8S_NAMESPACE", "")
        or f"ani-{tenant_id}"
    ).strip()
    secret_name = (
        args.pull_secret_kubernetes_name
        or os.environ.get("PULL_SECRET_K8S_NAME", "")
        or f"{harbor_gate.DEFAULT_PULL_SECRET_K8S_NAME}-{run_id}"
    ).strip()

    evidence_output = (args.evidence_output or os.environ.get("EVIDENCE_OUTPUT", defaults["evidence_output"])).strip()
    harbor_url = (args.harbor_url or os.environ.get("HARBOR_URL", common.DEFAULT_HARBOR_URL)).strip()
    harbor_username = (
        args.harbor_username or os.environ.get("HARBOR_USERNAME", common.DEFAULT_HARBOR_USERNAME)
    ).strip()

    production_shaped = track in {"production", "in-cluster"} or args.production_shaped or common.env_bool(
        "PRODUCTION_SHAPED"
    )
    cleanup_default = args.dev if track == "pull-secret-kubernetes" else False
    cleanup = args.cleanup or common.env_bool("CLEANUP", default=cleanup_default)

    return RunnerConfig(
        track=track,
        dev=args.dev,
        gateway_url=gateway_url,
        harbor_url=harbor_url,
        harbor_username=harbor_username,
        harbor_password=harbor_password,
        tenant_id=tenant_id,
        repository=repository,
        image_tag=image_tag,
        scan_image=scan_image,
        pull_secret_kubernetes_namespace=namespace,
        pull_secret_kubernetes_name=secret_name,
        ani_bearer_token=(args.ani_bearer_token or os.environ.get("ANI_BEARER_TOKEN", "")).strip(),
        production_shaped=production_shaped,
        artifact_track=track == "artifact",
        pull_secret_kubernetes_track=track == "pull-secret-kubernetes",
        cleanup=cleanup,
        run_id=run_id,
        evidence_output=evidence_output,
        harbor_tls_insecure=args.harbor_tls_insecure or common.env_bool("HARBOR_TLS_INSECURE", default=True),
        gateway_port=gateway_port,
        kubectl_proxy_port=args.kubectl_proxy_port or common.env_int("KUBECTL_PROXY_PORT", common.DEFAULT_KUBECTL_PROXY_PORT),
        skip_gateway_start=args.skip_gateway_start or common.env_bool("SKIP_GATEWAY_START"),
        skip_kubectl_proxy=args.skip_kubectl_proxy or common.env_bool("SKIP_KUBECTL_PROXY"),
        skip_docker_push=args.skip_docker_push or common.env_bool("SKIP_DOCKER_PUSH"),
        source_image=(args.source_image or os.environ.get("SOURCE_IMAGE", "registry.k8s.io/pause:3.10")).strip(),
    )


def validate_config(config: RunnerConfig) -> None:
    if not config.tenant_id:
        common.fail("--tenant-id is required")
    if not config.harbor_url or not config.harbor_username:
        common.fail("harbor url/username are required")
    if config.track == "production" and not (config.gateway_url or os.environ.get("GATEWAY_URL")):
        common.fail("production track requires --gateway-url or GATEWAY_URL")
    if config.track == "in-cluster" and not config.ani_bearer_token:
        common.fail("in-cluster track requires --ani-bearer-token or ANI_BEARER_TOKEN")


def run_live_gate(config: RunnerConfig) -> None:
    harbor_gate.validate_live(
        harbor_gate.LiveArgs(
            gateway_url=config.gateway_url,
            ani_bearer_token=config.ani_bearer_token,
            harbor_url=config.harbor_url,
            harbor_username=config.harbor_username,
            harbor_password=config.harbor_password,
            tenant_id=config.tenant_id,
            repository=config.repository if config.artifact_track else "",
            scan_image=config.scan_image if config.artifact_track else "",
            evidence_output=config.evidence_output,
            production_shaped=config.production_shaped,
            artifact_track=config.artifact_track,
            pull_secret_kubernetes_track=config.pull_secret_kubernetes_track,
            pull_secret_kubernetes_namespace=config.pull_secret_kubernetes_namespace,
            pull_secret_kubernetes_name=config.pull_secret_kubernetes_name,
            cleanup=config.cleanup,
            run_id=config.run_id,
            harbor_tls_insecure=config.harbor_tls_insecure,
        )
    )
    print(f"SPRINT13-REGISTRY-HARBOR-A {config.track} live checks passed")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--track",
        choices=list(TRACK_DEFAULTS),
        default="production",
        help="live gate track (default: production)",
    )
    parser.add_argument("--dev", action="store_true", help="pull-secret-kubernetes: start proxy + local gateway")
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--harbor-url", default="")
    parser.add_argument("--harbor-username", default="")
    parser.add_argument("--harbor-password", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--repository", default="")
    parser.add_argument("--image-tag", default="")
    parser.add_argument("--scan-image", default="")
    parser.add_argument("--pull-secret-kubernetes-namespace", default="")
    parser.add_argument("--pull-secret-kubernetes-name", default="")
    parser.add_argument("--ani-bearer-token", default="")
    parser.add_argument("--production-shaped", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--evidence-output", default="")
    parser.add_argument("--harbor-tls-insecure", action="store_true")
    parser.add_argument("--gateway-port", type=int, default=0)
    parser.add_argument("--kubectl-proxy-port", type=int, default=0)
    parser.add_argument("--skip-gateway-start", action="store_true")
    parser.add_argument("--skip-kubectl-proxy", action="store_true")
    parser.add_argument("--skip-docker-push", action="store_true")
    parser.add_argument("--source-image", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    common.register_cleanup()
    common.load_dotenv(common.ROOT / ".env")
    args = parse_args(argv)
    harbor_password = common.resolve_harbor_password(args.harbor_password)
    config = build_config(args, harbor_password)
    validate_config(config)

    if config.track == "artifact":
        registry_host = common.harbor_registry_host(config.harbor_url)
        common.push_artifact_test_image(
            harbor_registry_host=registry_host,
            harbor_username=config.harbor_username,
            harbor_password=harbor_password,
            tenant_id=config.tenant_id,
            repository=config.repository,
            image_tag=config.image_tag,
            source_image=config.source_image,
            skip_docker_push=config.skip_docker_push,
        )

    if config.track == "pull-secret-kubernetes" and config.dev:
        common.ensure_namespace(config.pull_secret_kubernetes_namespace)
        if not config.skip_kubectl_proxy:
            common.start_kubectl_proxy(config.kubectl_proxy_port)
        if not config.skip_gateway_start:
            common.start_dev_gateway(
                gateway_port=config.gateway_port,
                kubectl_proxy_port=config.kubectl_proxy_port,
                harbor_username=config.harbor_username,
                harbor_password=harbor_password,
            )

    run_live_gate(config)

    if config.track == "pull-secret-kubernetes" and config.dev:
        result = common.kubectl(
            [
                "get",
                "secret",
                "-n",
                config.pull_secret_kubernetes_namespace,
                config.pull_secret_kubernetes_name,
                "-o",
                "jsonpath={.type}",
            ],
            check=True,
        )
        if result.stdout.strip() != "kubernetes.io/dockerconfigjson":
            common.fail(f"kubectl secret type = {result.stdout.strip()!r}, want kubernetes.io/dockerconfigjson")
        print(
            "kubectl verified dockerconfigjson secret "
            f"{config.pull_secret_kubernetes_namespace}/{config.pull_secret_kubernetes_name}"
        )
        print(f"evidence: {config.evidence_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
