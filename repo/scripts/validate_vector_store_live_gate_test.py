#!/usr/bin/env python3
"""Tests for Sprint 13 vector-store Milvus live gate contract."""

from __future__ import annotations

import tempfile
import unittest
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_vector_store_live_gate as gate


class VectorStoreLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_milvus_insert_and_search_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("milvus-health-ready", check_ids)
        self.assertIn("core-vector-store-create", check_ids)
        self.assertIn("core-vector-documents-insert", check_ids)
        self.assertIn("core-vector-search-readiness", check_ids)

    def test_contract_gate_rejects_missing_check(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"] = [check for check in document["live_checks"] if check["id"] != "core-vector-documents-insert"]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("missing live checks: core-vector-documents-insert", str(raised.exception))

    def test_contract_gate_requires_curl(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["required_tools"] = []

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("required_tools must include curl", str(raised.exception))

    def test_contract_gate_rejects_production_like_status(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["status"] = "production_like"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("status must be contract or live", str(raised.exception))

    def test_cli_reports_missing_gate_path_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-vector-store-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_vector_store_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_validates_docs(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_vector_store_live_gate.py"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs") as validate_docs,
        ):
            gate.main()

        validate_docs.assert_called_once()

    def test_production_shaped_live_rejects_local_gateway(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            gate.validate_live(
                gate.LiveArgs(
                    gateway_url="http://localhost:18004/api/v1",
                    ani_bearer_token="token",
                    milvus_url="http://milvus.production:19530",
                    milvus_token="milvus-token",
                    milvus_database="ani",
                    evidence_output="",
                    production_shaped=True,
                ),
                json_requester=lambda *_args: (200, {"code": 0}),
            )

        self.assertIn("non-local production gateway URL", str(raised.exception))

    def test_production_shaped_live_requires_bearer_token(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            gate.validate_live(
                gate.LiveArgs(
                    gateway_url="https://gateway.production.example/api/v1",
                    ani_bearer_token="",
                    milvus_url="https://milvus.production.example",
                    milvus_token="milvus-token",
                    milvus_database="ani",
                    evidence_output="",
                    production_shaped=True,
                ),
                json_requester=lambda *_args: (200, {"code": 0}),
            )

        self.assertIn("requires --ani-bearer-token", str(raised.exception))

    def test_live_gate_writes_redacted_production_shape_evidence(self) -> None:
        calls: list[tuple[str, str]] = []

        def requester(method: str, url: str, bearer_token: str, payload: dict | None) -> tuple[int, dict]:
            calls.append((method, url))
            if url.endswith("/v2/vectordb/collections/list"):
                self.assertEqual(bearer_token, "milvus-token")
                self.assertEqual(payload, {"dbName": "ani"})
                return 200, {"code": 0, "data": []}
            if method == "POST" and url.endswith("/vector-stores"):
                return 201, {"id": "vst_live", "state": "ready"}
            if method == "POST" and url.endswith("/vector-stores/vst_live/documents"):
                return 202, {"inserted_count": 1, "task_id": "task-a", "status": "completed"}
            if method == "POST" and url.endswith("/vector-stores/vst_live/search"):
                return 200, {"items": [{"id": "doc-a", "score": 0.99}], "total": 1}
            if method == "POST" and url.endswith("/auth/api-keys"):
                return 201, {"key_id": "ak_cleanup", "key_value": "cleanup-token"}
            if method == "DELETE" and url.endswith("/vector-stores/vst_live"):
                self.assertEqual(bearer_token, "cleanup-token")
                return 200, {"id": "vst_live", "state": "deleted"}
            if method == "DELETE" and url.endswith("/auth/api-keys/ak_cleanup"):
                self.assertEqual(bearer_token, "cleanup-token")
                return 200, {"status": "revoked"}
            self.fail(f"unexpected request {method} {url}")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "evidence.json"
            gate.validate_live(
                gate.LiveArgs(
                    gateway_url="https://gateway.production.example/api/v1",
                    ani_bearer_token="ani-token",
                    milvus_url="https://milvus.production.example",
                    milvus_token="milvus-token",
                    milvus_database="ani",
                    evidence_output=str(evidence_path),
                    production_shaped=True,
                    cleanup=True,
                ),
                json_requester=requester,
            )

            payload = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["milvus_health_status"], 200)
        self.assertEqual(payload["vector_store_create_status"], 201)
        self.assertEqual(payload["document_insert_status"], 202)
        self.assertEqual(payload["search_status"], 200)
        self.assertEqual(payload["inserted_count"], 1)
        self.assertEqual(payload["search_hit_count"], 1)
        self.assertEqual(payload["cleanup_status"], 200)
        self.assertEqual(payload["production_shape"]["status"], "passed")
        self.assertIn("production_vector_collection_lifecycle", payload["production_shape"]["proof_items"])
        serialized = json.dumps(payload)
        self.assertNotIn("production.example", serialized)
        self.assertNotIn("ani-token", serialized)
        self.assertNotIn("milvus-token", serialized)
        self.assertGreaterEqual(len(calls), 6)


if __name__ == "__main__":
    unittest.main()
