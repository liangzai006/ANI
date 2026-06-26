#!/usr/bin/env python3
"""Tests for Sprint 13 registry Harbor live gate contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_registry_harbor_live_gate as gate


class RegistryHarborLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_harbor_registry_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("harbor-health-ready", check_ids)
        self.assertIn("core-registry-project-create", check_ids)
        self.assertIn("core-registry-projects-list", check_ids)
        self.assertIn("core-registry-repositories-list", check_ids)
        self.assertIn("core-registry-project-scan-report", check_ids)
        self.assertIn("core-registry-pull-secret-create", check_ids)

    def test_contract_gate_rejects_missing_check(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"] = [
            check for check in document["live_checks"] if check["id"] != "core-registry-pull-secret-create"
        ]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("missing live checks: core-registry-pull-secret-create", str(raised.exception))

    def test_contract_gate_requires_curl_tool(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["required_tools"] = []

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("required_tools must include curl", str(raised.exception))

    def test_cli_reports_missing_gate_path_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-registry-harbor-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_registry_harbor_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_validates_docs(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_registry_harbor_live_gate.py"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs") as validate_docs,
        ):
            gate.main()

        validate_docs.assert_called_once()

    def test_live_production_shaped_writes_redacted_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "registry-harbor.json"
            args = gate.LiveArgs(
                gateway_url="https://gateway.example/api/v1",
                ani_bearer_token="token",
                harbor_url="https://harbor.example",
                harbor_username="admin",
                harbor_password="secret",
                tenant_id="tenant-a",
                repository="runtime",
                scan_image="tenant-a/runtime:latest",
                evidence_output=str(evidence),
                production_shaped=True,
            )

            gate.validate_live(
                args,
                json_requester=registry_json_requester,
                harbor_requester=registry_harbor_requester,
            )

            payload = json.loads(evidence.read_text(encoding="utf-8"))

        self.assertEqual("passed", payload["status"])
        self.assertEqual(201, payload["project_create_status"])
        self.assertEqual(200, payload["projects_list_status"])
        self.assertEqual(200, payload["repositories_list_status"])
        self.assertEqual(200, payload["scan_report_status"])
        self.assertEqual(201, payload["pull_secret_status"])
        self.assertTrue(payload["optional_artifacts_enabled"])
        self.assertEqual(200, payload["optional_artifacts_status"])
        self.assertTrue(payload["optional_scan_result_enabled"])
        self.assertEqual(200, payload["optional_scan_result_status"])
        self.assertEqual("passed", payload["production_shape"]["status"])
        self.assertIn("production_harbor_credentials", payload["production_shape"]["proof_items"])
        self.assertNotIn("harbor.example", json.dumps(payload))
        self.assertNotIn("admin", json.dumps(payload))

    def test_production_shaped_live_rejects_local_gateway(self) -> None:
        args = gate.LiveArgs(
            gateway_url="http://127.0.0.1:3000/api/v1",
            ani_bearer_token="token",
            harbor_url="https://harbor.example",
            harbor_username="admin",
            harbor_password="secret",
            tenant_id="tenant-a",
            repository="",
            scan_image="",
            evidence_output="",
            production_shaped=True,
        )

        with self.assertRaises(SystemExit) as raised:
            gate.validate_live(
                args,
                json_requester=registry_json_requester,
                harbor_requester=registry_harbor_requester,
            )

        self.assertIn("production-shaped live mode requires a non-local production gateway URL", str(raised.exception))


def registry_json_requester(method: str, url: str, bearer_token: str, payload: dict | None = None) -> tuple[int, dict]:
    dev_profile = {"mode": "real", "provider": "harbor", "real_provider": True}
    if method == "POST" and url.endswith("/registry/projects"):
        return 201, {"id": "harbor-1", "name": "tenant-a", "dev_profile": dev_profile}
    if method == "GET" and url.endswith("/registry/projects"):
        return 200, {"items": [{"name": "tenant-a"}], "total": 1}
    if method == "GET" and "/registry/projects/tenant-a/repositories/runtime/artifacts" in url:
        return 200, {"items": [{"digest": "sha256:abc"}], "total": 1}
    if method == "GET" and "/registry/projects/tenant-a/repositories" in url:
        return 200, {"items": [{"name": "runtime"}], "total": 1}
    if method == "GET" and url.endswith("/registry/projects/tenant-a/scan-report"):
        return 200, {"status": "complete", "dev_profile": dev_profile}
    if method == "POST" and url.endswith("/registry/projects/tenant-a/pull-secret"):
        return 201, {"secret_ref": "tenant-a/ani-registry-pull", "registry": "harbor.example", "dev_profile": dev_profile}
    if method == "GET" and "/registry/images/scan-result" in url:
        return 200, {"status": "complete", "dev_profile": dev_profile}
    raise AssertionError(f"unexpected request {method} {url}")


def registry_harbor_requester(method: str, url: str, username: str, password: str) -> tuple[int, dict]:
    if method == "GET" and url.endswith("/api/v2.0/health"):
        return 200, {"status": "healthy"}
    raise AssertionError(f"unexpected Harbor request {method} {url}")


if __name__ == "__main__":
    unittest.main()
