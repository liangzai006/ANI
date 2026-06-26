#!/usr/bin/env python3
"""Validate Sprint 13 registry Harbor live gate contract."""

from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/registry-harbor-live-gate.yaml"
PROFILE = "SPRINT13-REGISTRY-HARBOR-A"
REQUIRED_CHECKS = {
    "harbor-health-ready",
    "core-registry-project-create",
    "core-registry-projects-list",
    "core-registry-repositories-list",
    "core-registry-project-scan-report",
    "core-registry-pull-secret-create",
}
REQUIRED_TOOLS = {"curl"}
REQUIRED_DOC_TOKENS = [
    "SPRINT13-REGISTRY-HARBOR-A",
    "validate-registry-harbor-live-gate",
    "Harbor",
    "LIVE PENDING",
]
PROOF_ITEMS = [
    "production_gateway",
    "production_harbor_credentials",
    "production_registry_provider_runtime",
]


@dataclass(frozen=True)
class LiveArgs:
    gateway_url: str
    ani_bearer_token: str
    harbor_url: str
    harbor_username: str
    harbor_password: str
    tenant_id: str
    repository: str
    scan_image: str
    evidence_output: str
    production_shaped: bool = False


def fail(message: str) -> None:
    raise SystemExit(f"registry-harbor live gate invalid: {message}")


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
    if not isinstance(tools, list) or not REQUIRED_TOOLS.issubset(set(tools)):
        fail("required_tools must include curl")
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


def is_local_transport(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        "127.0.0.1" in lowered
        or "localhost" in lowered
        or "kubectl proxy" in lowered
        or "kubectl-proxy" in lowered
        or "port-forward" in lowered
    )


def validate_production_shaped_live_args(args: LiveArgs) -> None:
    if is_local_transport(args.gateway_url):
        fail("production-shaped live mode requires a non-local production gateway URL")
    if not args.harbor_url.strip():
        fail("production-shaped live mode requires --harbor-url")
    if is_local_transport(args.harbor_url):
        fail("production-shaped live mode requires a non-local Harbor endpoint")
    if not args.harbor_username.strip() or not args.harbor_password.strip():
        fail("production-shaped live mode requires --harbor-username and --harbor-password")


def default_json_requester(
    method: str,
    url: str,
    bearer_token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token.strip()}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        fail(f"could not call Core registry API: {exc}")
    try:
        parsed = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        fail("Core registry API did not return JSON")
    if not isinstance(parsed, dict):
        fail("Core registry API must return a JSON object")
    return status, parsed


def default_harbor_requester(
    method: str,
    url: str,
    username: str,
    password: str,
) -> tuple[int, dict[str, Any]]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Basic {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        fail(f"could not call Harbor API: {exc}")
    try:
        parsed = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        fail("Harbor API did not return JSON")
    if not isinstance(parsed, dict):
        fail("Harbor API must return a JSON object")
    return status, parsed


def require_status(status: int, expected: int, label: str) -> None:
    if status != expected:
        fail(f"{label} returned HTTP {status}, want {expected}")


def require_non_empty_string(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must include non-empty {field}")
    return value.strip()


def require_items_list(payload: dict[str, Any], label: str) -> list[Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        fail(f"{label} must include items array")
    return items


def require_dev_profile_real_provider(payload: dict[str, Any], label: str) -> None:
    dev_profile = payload.get("dev_profile")
    if not isinstance(dev_profile, dict):
        fail(f"{label} must include dev_profile")
    if dev_profile.get("real_provider") is not True:
        fail(f"{label} dev_profile.real_provider must be true for Harbor live gate")
    if dev_profile.get("provider") != "harbor":
        fail(f"{label} dev_profile.provider must be harbor")


def validate_live(
    args: LiveArgs,
    json_requester: Callable[[str, str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]] = default_json_requester,
    harbor_requester: Callable[[str, str, str, str], tuple[int, dict[str, Any]]] = default_harbor_requester,
) -> None:
    if not args.gateway_url.strip():
        fail("live mode requires --gateway-url")
    if not args.harbor_username.strip() or not args.harbor_password.strip():
        fail("live mode requires --harbor-username and --harbor-password")
    tenant_id = args.tenant_id.strip()
    if not tenant_id:
        fail("live mode requires --tenant-id")
    if args.production_shaped:
        validate_production_shaped_live_args(args)

    harbor_health_url = trim_url(args.harbor_url) + "/api/v2.0/health"
    harbor_health_status, harbor_health = harbor_requester(
        "GET",
        harbor_health_url,
        args.harbor_username,
        args.harbor_password,
    )
    require_status(harbor_health_status, 200, "Harbor health")
    if harbor_health.get("status") not in {"healthy", "ok"}:
        fail("Harbor health response status must be healthy")

    base_url = trim_url(args.gateway_url)
    project_request = {
        "name": tenant_id,
        "public": False,
        "idempotency_key": "sprint13-registry-harbor-project",
    }
    create_status, project = json_requester(
        "POST",
        f"{base_url}/registry/projects",
        args.ani_bearer_token,
        project_request,
    )
    require_status(create_status, 201, "Core registry project create")
    require_non_empty_string(project, "id", "Core registry project create response")
    require_non_empty_string(project, "name", "Core registry project create response")
    require_dev_profile_real_provider(project, "Core registry project create response")

    list_status, projects = json_requester("GET", f"{base_url}/registry/projects", args.ani_bearer_token, None)
    require_status(list_status, 200, "Core registry projects list")
    project_items = require_items_list(projects, "Core registry projects list")
    if not any(item.get("name") == tenant_id for item in project_items if isinstance(item, dict)):
        fail("Core registry projects list must include the tenant project")

    repositories_status, repositories = json_requester(
        "GET",
        f"{base_url}/registry/projects/{urllib.parse.quote(tenant_id, safe='')}/repositories",
        args.ani_bearer_token,
        None,
    )
    require_status(repositories_status, 200, "Core registry repositories list")
    require_items_list(repositories, "Core registry repositories list")

    scan_report_status, scan_report = json_requester(
        "GET",
        f"{base_url}/registry/projects/{urllib.parse.quote(tenant_id, safe='')}/scan-report",
        args.ani_bearer_token,
        None,
    )
    require_status(scan_report_status, 200, "Core registry project scan report")
    require_non_empty_string(scan_report, "status", "Core registry project scan report")
    require_dev_profile_real_provider(scan_report, "Core registry project scan report")

    pull_secret_status, pull_secret = json_requester(
        "POST",
        f"{base_url}/registry/projects/{urllib.parse.quote(tenant_id, safe='')}/pull-secret",
        args.ani_bearer_token,
        {
            "name": "ani-registry-pull",
            "namespace": f"ani-{tenant_id}",
            "idempotency_key": "sprint13-registry-harbor-pull-secret",
        },
    )
    require_status(pull_secret_status, 201, "Core registry pull secret create")
    require_non_empty_string(pull_secret, "secret_ref", "Core registry pull secret create response")
    require_non_empty_string(pull_secret, "registry", "Core registry pull secret create response")
    require_dev_profile_real_provider(pull_secret, "Core registry pull secret create response")

    artifacts_status = 0
    artifacts_count = 0
    repository = args.repository.strip()
    if repository:
        artifacts_status, artifacts = json_requester(
            "GET",
            f"{base_url}/registry/projects/{urllib.parse.quote(tenant_id, safe='')}/repositories/{urllib.parse.quote(repository, safe='')}/artifacts",
            args.ani_bearer_token,
            None,
        )
        require_status(artifacts_status, 200, "Core registry artifacts list")
        artifacts_count = len(require_items_list(artifacts, "Core registry artifacts list"))

    scan_result_status = 0
    scan_image = args.scan_image.strip()
    if scan_image:
        query = urllib.parse.urlencode({"image": scan_image})
        scan_result_status, scan_result = json_requester(
            "GET",
            f"{base_url}/registry/images/scan-result?{query}",
            args.ani_bearer_token,
            None,
        )
        require_status(scan_result_status, 200, "Core registry image scan result")
        require_non_empty_string(scan_result, "status", "Core registry image scan result")
        require_dev_profile_real_provider(scan_result, "Core registry image scan result")

    evidence: dict[str, Any] = {
        "id": "registry-harbor-live-gate",
        "profile": PROFILE,
        "status": "passed",
        "harbor_health_status": harbor_health_status,
        "harbor_health_ready": True,
        "project_create_status": create_status,
        "projects_list_status": list_status,
        "projects_list_count": len(project_items),
        "repositories_list_status": repositories_status,
        "scan_report_status": scan_report_status,
        "pull_secret_status": pull_secret_status,
        "optional_artifacts_enabled": bool(repository),
        "optional_artifacts_status": artifacts_status,
        "optional_artifacts_count": artifacts_count,
        "optional_scan_result_enabled": bool(scan_image),
        "optional_scan_result_status": scan_result_status,
        "dev_profile_real_provider": True,
    }
    if args.production_shaped:
        evidence["production_shape"] = {
            "status": "passed",
            "transport_profile": "production_gateway_and_harbor_service",
            "missing_items": [],
            "proof_items": list(PROOF_ITEMS),
        }
    if args.evidence_output.strip():
        output = Path(args.evidence_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="registry Harbor live gate YAML")
    parser.add_argument("--live", action="store_true", help="execute the human-gated live checks")
    parser.add_argument("--production-shaped", action="store_true", help="require production-shaped transport and proof_items")
    parser.add_argument("--gateway-url", default="", help="ANI Core API base URL ending at /api/v1")
    parser.add_argument("--ani-bearer-token", default="", help="ANI Core bearer token")
    parser.add_argument("--harbor-url", default="", help="approved Harbor endpoint used by REGISTRY_PROVIDER=harbor")
    parser.add_argument("--harbor-username", default="", help="Harbor admin or robot username for health probe")
    parser.add_argument("--harbor-password", default="", help="Harbor password for health probe")
    parser.add_argument("--tenant-id", default="", help="tenant/project name; must match bearer token tenant")
    parser.add_argument("--repository", default="", help="optional repository name for artifacts list check")
    parser.add_argument("--scan-image", default="", help="optional image reference for scan-result check")
    parser.add_argument("--evidence-output", default="", help="write non-sensitive evidence JSON")
    args = parser.parse_args()

    validate_gate_path(args.gate)
    document = load_gate(Path(args.gate))
    validate_contract(document)
    validate_docs()
    if args.live:
        validate_live(
            LiveArgs(
                gateway_url=args.gateway_url,
                ani_bearer_token=args.ani_bearer_token,
                harbor_url=args.harbor_url,
                harbor_username=args.harbor_username,
                harbor_password=args.harbor_password,
                tenant_id=args.tenant_id,
                repository=args.repository,
                scan_image=args.scan_image,
                evidence_output=args.evidence_output,
                production_shaped=args.production_shaped,
            )
        )
        print("SPRINT13-REGISTRY-HARBOR-A live checks passed")
        return 0
    print("SPRINT13-REGISTRY-HARBOR-A contract valid; use --live for human-gated execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
