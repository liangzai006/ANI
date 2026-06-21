#!/usr/bin/env python3
"""Validate Sprint 4 closure alignment across API, SDK, Mock, docs, and records."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

import yaml

import validate_sdk_beta as sdk_beta


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT.parent

SPRINT4_BATCHES = {
    "SPEC-SPLIT-A": "spec-split-a-core-services-api-boundary.md",
    "SPEC-CORE-BETA-A": "spec-core-beta-a-readiness-matrix.md",
    "SPEC-COMPAT-A": "spec-compat-a-core-api-v1-baseline.md",
    "SDK-BETA-A": "sdk-beta-a-idempotency-helper.md",
    "SDK-BETA-B": "sdk-beta-b-cursor-pagination-helper.md",
    "SDK-BETA-C": "sdk-beta-c-api-error-helper.md",
    "SDK-BETA-D": "sdk-beta-d-basic-examples.md",
    "SDK-MOCK-SMOKE-A": "sdk-mock-smoke-a-python-sdk-mock-server.md",
    "SDK-MOCK-SMOKE-B": "sdk-mock-smoke-b-typescript-sdk-mock-server.md",
    "SDK-MOCK-SMOKE-C": "sdk-mock-smoke-c-go-sdk-mock-server.md",
    "SDK-MOCK-SMOKE-D": "sdk-mock-smoke-d-java-sdk-mock-server.md",
    "MOCK-A": "mock-a-core-openapi-mock-server.md",
    "DOC-API-A": "doc-api-a-static-api-docs.md",
    "SPRINT4-CLOSURE-A": "sprint4-closure-a-contract.md",
}

DOC_REQUIRED_TOKENS = {
    "ANI-DOCS-INDEX.md": (
        "SPEC-SPLIT-A",
        "SPEC-CORE-BETA",
        "SPEC-COMPAT-A",
        "SDK-BETA-A",
        "SDK-BETA-B",
        "SDK-BETA-C",
        "SDK-BETA-D",
        "SDK-MOCK-SMOKE-A",
        "SDK-MOCK-SMOKE-B",
        "SDK-MOCK-SMOKE-C",
        "SDK-MOCK-SMOKE-D",
        "MOCK-A",
        "DOC-API-A",
        "SPRINT4-CLOSURE-A",
    ),
    "ANI-06-开发计划.md": (
        "SPEC-CORE-BETA",
        "SPEC-COMPAT-A",
        "SDK-BETA-A",
        "SDK-BETA-B",
        "SDK-BETA-C",
        "SDK-BETA-D",
        "SDK-MOCK-SMOKE-A",
        "SDK-MOCK-SMOKE-B",
        "SDK-MOCK-SMOKE-C",
        "SDK-MOCK-SMOKE-D",
        "MOCK-A",
        "DOC-API-A",
        "SPRINT4-CLOSURE-A",
    ),
    "CURRENT-SPRINT.md": (
        "SPEC-SPLIT-A",
        "SPEC-CORE-BETA",
        "SPEC-COMPAT-A",
        "SDK-BETA-A",
        "SDK-BETA-B",
        "SDK-BETA-C",
        "SDK-BETA-D",
        "SDK-MOCK-SMOKE-A",
        "SDK-MOCK-SMOKE-B",
        "SDK-MOCK-SMOKE-C",
        "SDK-MOCK-SMOKE-D",
        "MOCK-A",
        "DOC-API-A",
        "SPRINT4-CLOSURE-A",
        "validate-sprint4-closure",
    ),
    "development-records/README.md": tuple(SPRINT4_BATCHES),
}

SPRINT4_TARGETS = (
    "validate-spec-split",
    "validate-core-beta",
    "validate-core-api-compatibility",
    "validate-sdk-beta",
    "validate-mock-a",
    "validate-doc-api",
    "validate-sdk-mock-smoke",
)

SERVICES_PATH_PREFIXES = ("/models", "/inference-services", "/knowledge-bases")
CORE_INFRA_PREFIXES = ("/instances", "/networks", "/volumes", "/filesystems", "/objects", "/vector-stores")


def fail(message: str) -> None:
    raise SystemExit(f"sprint4 closure invalid: {message}")


def read_repo(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def read_doc(path: str) -> str:
    return (DOC_ROOT / path).read_text(encoding="utf-8")


def load_yaml(path: str) -> dict[str, Any]:
    data = yaml.safe_load(read_repo(path))
    if not isinstance(data, dict):
        fail(f"{path} must parse to an object")
    return data


def validate_docs() -> None:
    docs = {
        "ANI-DOCS-INDEX.md": read_doc("ANI-DOCS-INDEX.md"),
        "ANI-06-开发计划.md": read_doc("ANI-06-开发计划.md"),
        "CURRENT-SPRINT.md": read_repo("CURRENT-SPRINT.md"),
        "development-records/README.md": read_repo("development-records/README.md"),
    }
    for path, content in docs.items():
        if "Sprint 4" not in content:
            fail(f"{path} must reference Sprint 4")
        for token in DOC_REQUIRED_TOKENS[path]:
            if token not in content:
                fail(f"{path} missing {token}")
    claude = read_doc("CLAUDE.md")
    if "Phase 2" not in claude or "当前不是 Phase 2" not in claude:
        fail("CLAUDE.md must keep Phase 2 deferral boundary")


def validate_development_records() -> None:
    index = read_repo("development-records/README.md")
    for batch, filename in SPRINT4_BATCHES.items():
        path = ROOT / "development-records" / filename
        if not path.exists():
            fail(f"missing development record {filename}")
        if batch not in index or filename not in index:
            fail(f"development-records/README.md missing {batch} -> {filename}")
        content = path.read_text(encoding="utf-8")
        if not re.search(r"完成日期：20\d{2}-\d{2}-\d{2}", content):
            fail(f"{filename} must record completion date")


def validate_makefile() -> None:
    makefile = read_repo("Makefile")
    if "validate-sprint4-closure:" not in makefile:
        fail("Makefile missing validate-sprint4-closure target")
    for target in SPRINT4_TARGETS:
        if f"{target}:" not in makefile:
            fail(f"Makefile missing {target} target")
        if f"$(MAKE) {target}" not in makefile:
            fail(f"validate-sprint4-closure must call {target}")


def validate_api_split() -> None:
    core = load_yaml("api/openapi/v1.yaml")
    services = load_yaml("api/openapi/services/v1.yaml")
    matrix = load_yaml("api/core-beta-readiness.yaml")

    core_paths = set(core.get("paths", {}).keys())
    services_paths = set(services.get("paths", {}).keys())
    leaked_services = sorted(path for path in core_paths if path.startswith(SERVICES_PATH_PREFIXES))
    if leaked_services:
        fail(f"Core API contains Services business paths: {leaked_services}")
    leaked_core = sorted(path for path in services_paths if path.startswith(CORE_INFRA_PREFIXES))
    if leaked_core:
        fail(f"Services API contains Core infrastructure paths: {leaked_core}")
    if not matrix.get("p0_resources"):
        fail("api/core-beta-readiness.yaml must list p0_resources")
    baseline = load_yaml("api/core-v1-compatibility-baseline.yaml")
    if baseline.get("batch") != "SPEC-COMPAT-A":
        fail("api/core-v1-compatibility-baseline.yaml must be owned by SPEC-COMPAT-A")
    if not baseline.get("paths") or not baseline.get("schemas"):
        fail("api/core-v1-compatibility-baseline.yaml must protect paths and schemas")
    compatibility = matrix.get("compatibility")
    if not isinstance(compatibility, dict):
        fail("api/core-beta-readiness.yaml must list compatibility rules")
    if not compatibility.get("allowed_additive_changes") or not compatibility.get("forbidden_breaking_changes"):
        fail("api/core-beta-readiness.yaml must list additive and forbidden changes")


def validate_sdk_outputs() -> None:
    core_metadata = json.loads((ROOT / "sdks/core/sdk-metadata.json").read_text(encoding="utf-8"))
    services_metadata = json.loads((ROOT / "sdks/services/sdk-metadata.json").read_text(encoding="utf-8"))
    if not core_metadata.get("idempotencyOperations"):
        fail("Core SDK metadata must list idempotencyOperations")
    if not core_metadata.get("cursorPaginationOperations"):
        fail("Core SDK metadata must list cursorPaginationOperations")
    if not core_metadata.get("errorCodes"):
        fail("Core SDK metadata must list errorCodes")
    try:
        sdk_beta.validate_services_idempotency_separation(core_metadata, services_metadata)
    except SystemExit as exc:
        fail(str(exc).removeprefix("sdk beta invalid: "))
    examples = [
        "sdks/core/go/examples/basic/main.go",
        "sdks/core/python/examples/basic.py",
        "sdks/core/typescript/examples/basic.mjs",
        "sdks/core/java/examples/Basic.java",
        "sdks/services/go/examples/basic/main.go",
        "sdks/services/python/examples/basic.py",
        "sdks/services/typescript/examples/basic.mjs",
        "sdks/services/java/examples/Basic.java",
    ]
    for relative in examples:
        path = ROOT / relative
        if not path.exists():
            fail(f"missing SDK example {relative}")
        content = path.read_text(encoding="utf-8")
        for token in ("idempotency", "cursor", "BAD_REQUEST"):
            if token not in content.lower() and token not in content:
                fail(f"{relative} missing example token {token}")
    core_python = read_repo("sdks/core/python/kubercloud_ani_core/client.py")
    for token in ("def request(", "urllib", "Authorization", "APIError"):
        if token not in core_python:
            fail(f"Core Python SDK missing mock smoke client token {token}")
    core_ts = read_repo("sdks/core/typescript/src/index.mjs")
    for token in ("async request(", "fetch(", "Authorization", "apiError"):
        if token not in core_ts:
            fail(f"Core TypeScript SDK missing mock smoke client token {token}")
    core_go = read_repo("sdks/core/go/anisdk/client.go")
    for token in ("func (client Client) Request(", "net/http", "Authorization", "APIError"):
        if token not in core_go:
            fail(f"Core Go SDK missing mock smoke client token {token}")
    core_java = read_repo("sdks/core/java/src/main/java/com/kubercloud/ani/core/ApiClient.java")
    for token in (
        "java.net.http.HttpClient",
        "String request(",
        "Authorization",
        "APIException",
        "APIError",
        "Pattern.compile(\"\\\\\\\"\"",
    ):
        if token not in core_java:
            fail(f"Core Java SDK missing mock smoke client token {token}")


def validate_mock_and_docs_outputs() -> None:
    for relative in (
        "scripts/serve_core_mock.py",
        "scripts/validate_mock_server_contract.py",
        "scripts/generate_api_docs.py",
        "scripts/validate_api_docs_contract.py",
        "docs/api/index.html",
        "docs/api/core.html",
        "docs/api/services.html",
    ):
        if not (ROOT / relative).exists():
            fail(f"missing {relative}")
    core_docs = read_repo("docs/api/core.html")
    for forbidden in SERVICES_PATH_PREFIXES:
        if forbidden in core_docs:
            fail(f"Core API docs must not contain {forbidden}")
    if "http://127.0.0.1:4010/api/v1" not in read_doc("CLAUDE.md"):
        fail("CLAUDE.md must document Core mock server local URL")


def main() -> None:
    validate_docs()
    validate_development_records()
    validate_makefile()
    validate_api_split()
    validate_sdk_outputs()
    validate_mock_and_docs_outputs()
    print("sprint4 closure contract valid")


if __name__ == "__main__":
    main()
