#!/usr/bin/env python3
"""Tests for Sprint 13 storage snapshot/mount-target live gate contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_storage_live_gate as gate


class StorageLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_snapshot_and_mount_target_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("core-volume-create", check_ids)
        self.assertIn("core-volume-snapshot-create", check_ids)
        self.assertIn("core-volume-snapshots-list", check_ids)
        self.assertIn("core-filesystem-create", check_ids)
        self.assertIn("core-mount-targets-list", check_ids)

    def test_contract_gate_rejects_missing_check(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"] = [check for check in document["live_checks"] if check["id"] != "core-mount-targets-list"]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("missing live checks: core-mount-targets-list", str(raised.exception))

    def test_contract_gate_rejects_production_like_status(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["status"] = "production_like"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("status must be contract or live", str(raised.exception))

    def test_cli_reports_missing_gate_path_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-storage-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_storage_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_storage_live_gate.py", "--gate", ""]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not be empty", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_validates_docs(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_storage_live_gate.py"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs") as validate_docs,
        ):
            gate.main()

        validate_docs.assert_called_once()

    def test_live_gate_runs_core_storage_checks_and_writes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "storage-live-evidence.json"
            result = gate.run_live(
                gate.LiveConfig(
                    gateway_url="http://127.0.0.1:8080/api/v1",
                    ani_bearer_token="dev-token",
                    tenant_id="tenant-a",
                    namespace="ani-tenant-tenant-a",
                    storage_class="ani-rbd-ssd",
                    snapshot_class="csi-rbdplugin-snapclass",
                    filesystem_backend="nfs",
                    evidence_output=evidence,
                ),
                http_client=FakeHTTPClient(),
                runner=FakeRunner(),
            )

            self.assertEqual("passed", result["status"])
            self.assertEqual(201, result["volume_status"])
            self.assertEqual(202, result["snapshot_status"])
            self.assertEqual(1, result["snapshot_count"])
            self.assertEqual(1, result["mount_target_count"])
            written = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("SPRINT13-STORAGE-ROOK-CEPH-A", written["profile"])
            self.assertNotIn("dev-token", json.dumps(written))

    def test_cli_live_mode_requires_evidence_output(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_storage_live_gate.py", "--live", "--gateway-url", "http://127.0.0.1:8080/api/v1", "--ani-bearer-token", "dev-token"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("live mode requires evidence_output", str(raised.exception))


class FakeHTTPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, bearer_token: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        self.calls.append((method, url))
        if method == "POST" and url.endswith("/volumes"):
            return 201, {"id": "vol_live", "state": "available"}
        if method == "POST" and url.endswith("/volumes/vol_live/snapshots"):
            return 202, {"id": "task-live", "result": {"snapshot": {"id": "snap_live", "status": "available"}}}
        if method == "GET" and url.endswith("/volumes/vol_live/snapshots"):
            return 200, {"items": [{"id": "snap_live", "status": "available"}], "total": 1, "next_cursor": None}
        if method == "POST" and url.endswith("/filesystems"):
            return 201, {"id": "fs_live", "state": "available"}
        if method == "GET" and url.endswith("/filesystems/fs_live/mount-targets"):
            return 200, {"items": [{"id": "mt_live", "status": "available"}], "total": 1, "next_cursor": None}
        raise AssertionError(f"unexpected HTTP call: {method} {url}")


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get namespace ani-tenant-tenant-a" in joined:
            return '{"metadata":{"name":"ani-tenant-tenant-a"}}'
        if "get sc ani-rbd-ssd" in joined:
            return '{"metadata":{"name":"ani-rbd-ssd"}}'
        if "get volumesnapshotclass csi-rbdplugin-snapclass" in joined:
            return '{"metadata":{"name":"csi-rbdplugin-snapclass"}}'
        if "get crd volumesnapshots.snapshot.storage.k8s.io" in joined:
            return '{"metadata":{"name":"volumesnapshots.snapshot.storage.k8s.io"}}'
        if "delete " in joined:
            return "deleted\n"
        raise AssertionError(f"unexpected command: {joined}")


if __name__ == "__main__":
    unittest.main()
