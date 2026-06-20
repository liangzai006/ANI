#!/usr/bin/env python3
"""Validate Sprint 13 vector-store Milvus live gate contract."""

from __future__ import annotations

import argparse
import datetime
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent
DEFAULT_GATE = ROOT / "deploy/real-k8s-lab/vector-store-live-gate.yaml"
PROFILE = "SPRINT13-VECTOR-MILVUS-A"
REQUIRED_CHECKS = {
    "milvus-health-ready",
    "core-vector-store-create",
    "core-vector-documents-insert",
    "core-vector-search-readiness",
}
REQUIRED_DOC_TOKENS = [
    "SPRINT13-VECTOR-MILVUS-A-TRACK",
    "validate-vector-store-live-gate",
    "Milvus",
    "LIVE PENDING",
]
PROOF_ITEMS = [
    "production_gateway",
    "production_vector_store_credentials",
    "production_vector_collection_lifecycle",
]


@dataclass(frozen=True)
class LiveArgs:
    gateway_url: str
    ani_bearer_token: str
    milvus_url: str
    milvus_token: str
    milvus_database: str
    evidence_output: str
    production_shaped: bool = False
    cleanup: bool = False


def fail(message: str) -> None:
    raise SystemExit(f"vector-store live gate invalid: {message}")


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
    if not isinstance(tools, list) or "curl" not in tools:
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
    if not args.ani_bearer_token.strip():
        fail("production-shaped live mode requires --ani-bearer-token")
    if not args.milvus_url.strip():
        fail("production-shaped live mode requires --milvus-url")
    if is_local_transport(args.milvus_url):
        fail("production-shaped live mode requires a non-local Milvus endpoint")


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
        fail(f"could not call vector-store live API: {exc}")
    try:
        parsed = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        fail("vector-store live API did not return JSON")
    if not isinstance(parsed, dict):
        fail("vector-store live API must return a JSON object")
    return status, parsed


def require_status(status: int, expected: int, label: str) -> None:
    if status != expected:
        fail(f"{label} returned HTTP {status}, want {expected}")


def require_non_empty_string(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must include non-empty {field}")
    return value.strip()


def validate_live(
    args: LiveArgs,
    json_requester: Callable[[str, str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]] = default_json_requester,
) -> None:
    if not args.gateway_url.strip():
        fail("live mode requires --gateway-url")
    if args.production_shaped:
        validate_production_shaped_live_args(args)

    milvus_list_payload: dict[str, Any] = {}
    if args.milvus_database.strip():
        milvus_list_payload["dbName"] = args.milvus_database.strip()
    milvus_health_status, milvus_health = json_requester(
        "POST",
        trim_url(args.milvus_url) + "/v2/vectordb/collections/list",
        args.milvus_token,
        milvus_list_payload,
    )
    require_status(milvus_health_status, 200, "Milvus collections readiness")
    if milvus_health.get("code") not in (0, None):
        fail("Milvus collections readiness returned non-zero code")

    base_url = trim_url(args.gateway_url)
    create_status, store = json_requester(
        "POST",
        f"{base_url}/vector-stores",
        args.ani_bearer_token,
        {
            "name": "sprint13-vector-milvus-live",
            "dimension": 4,
            "metric": "cosine",
            "idempotency_key": "sprint13-vector-milvus-create",
        },
    )
    require_status(create_status, 201, "Core vector store create")
    vector_store_id = require_non_empty_string(store, "id", "Core vector store create response")

    insert_status, insert_result = json_requester(
        "POST",
        f"{base_url}/vector-stores/{vector_store_id}/documents",
        args.ani_bearer_token,
        {
            "idempotency_key": "sprint13-vector-milvus-insert",
            "documents": [
                {
                    "id": "sprint13-vector-doc-a",
                    "content": "Sprint 13 Milvus live readiness document",
                    "metadata": {"source": "sprint13-live-gate"},
                }
            ],
        },
    )
    require_status(insert_status, 202, "Core vector documents insert")
    inserted_count = insert_result.get("inserted_count")
    if not isinstance(inserted_count, int) or inserted_count < 1:
        fail("Core vector documents insert must report inserted_count >= 1")

    search_status = 0
    search_items: list[Any] = []
    search_payload = {"vector": [0.1, 0.2, 0.3, 0.4], "top_k": 1}
    for attempt in range(1, 7):
        search_status, search_result = json_requester(
            "POST",
            f"{base_url}/vector-stores/{vector_store_id}/search",
            args.ani_bearer_token,
            search_payload,
        )
        require_status(search_status, 200, "Core vector search readiness")
        raw_items = search_result.get("items")
        search_items = raw_items if isinstance(raw_items, list) else []
        if len(search_items) >= 1:
            break
        if attempt < 6:
            time.sleep(5)
    if len(search_items) < 1:
        fail("Core vector search readiness must return at least one hit")

    cleanup_api_key_status = 0
    cleanup_api_key_revoke_status = 0
    cleanup_status = 0
    if args.cleanup:
        expires_at = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        cleanup_api_key_status, cleanup_key = json_requester(
            "POST",
            f"{base_url}/auth/api-keys",
            args.ani_bearer_token,
            {
                "name": "sprint13-vectorstore-cleanup",
                "scopes": ["scope:vector-stores:delete", "scope:auth:delete"],
                "rate_limit_rpm": 20,
                "expires_at": expires_at,
            },
        )
        require_status(cleanup_api_key_status, 201, "Core cleanup API key create")
        cleanup_token = require_non_empty_string(cleanup_key, "key_value", "Core cleanup API key create response")
        cleanup_key_id = require_non_empty_string(cleanup_key, "key_id", "Core cleanup API key create response")
        cleanup_status, _ = json_requester("DELETE", f"{base_url}/vector-stores/{vector_store_id}", cleanup_token, None)
        require_status(cleanup_status, 200, "Core vector store cleanup delete")
        cleanup_api_key_revoke_status, _ = json_requester("DELETE", f"{base_url}/auth/api-keys/{cleanup_key_id}", cleanup_token, None)
        require_status(cleanup_api_key_revoke_status, 200, "Core cleanup API key revoke")

    evidence: dict[str, Any] = {
        "id": "vector-store-live-gate",
        "profile": PROFILE,
        "status": "passed",
        "milvus_health_status": milvus_health_status,
        "milvus_health_ready": True,
        "vector_store_create_status": create_status,
        "document_insert_status": insert_status,
        "search_status": search_status,
        "inserted_count": inserted_count,
        "search_hit_count": len(search_items),
        "cleanup_enabled": args.cleanup,
        "cleanup_api_key_status": cleanup_api_key_status,
        "cleanup_status": cleanup_status,
        "cleanup_api_key_revoke_status": cleanup_api_key_revoke_status,
    }
    if args.production_shaped:
        evidence["production_shape"] = {
            "status": "passed",
            "transport_profile": "production_gateway_and_vector_store_service",
            "missing_items": [],
            "proof_items": PROOF_ITEMS,
        }
    if args.evidence_output.strip():
        output = Path(args.evidence_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", default=str(DEFAULT_GATE), help="vector-store live gate YAML")
    parser.add_argument("--live", action="store_true", help="execute the human-gated live checks")
    parser.add_argument("--production-shaped", action="store_true", help="require production-shaped transport and proof_items")
    parser.add_argument("--gateway-url", default="", help="ANI Core API base URL ending at /api/v1")
    parser.add_argument("--ani-bearer-token", default="", help="ANI Core bearer token")
    parser.add_argument("--milvus-url", default="", help="approved Milvus REST endpoint used by the production Gateway")
    parser.add_argument("--milvus-token", default="", help="Milvus bearer token, if enabled")
    parser.add_argument("--milvus-database", default="", help="Milvus database name, if configured")
    parser.add_argument("--evidence-output", default="", help="write non-sensitive evidence JSON")
    parser.add_argument("--cleanup", action="store_true", help="delete temporary vector store metadata created by the live check")
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
                milvus_url=args.milvus_url,
                milvus_token=args.milvus_token,
                milvus_database=args.milvus_database,
                evidence_output=args.evidence_output,
                production_shaped=args.production_shaped,
                cleanup=args.cleanup,
            )
        )
        print("SPRINT13-VECTOR-MILVUS-A live checks passed")
        return 0
    print("SPRINT13-VECTOR-MILVUS-A contract valid; use --live for human-gated execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
