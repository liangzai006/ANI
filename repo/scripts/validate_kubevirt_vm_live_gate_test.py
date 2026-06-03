#!/usr/bin/env python3
"""Tests for the Sprint 5 KubeVirt VM live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_kubevirt_vm_live_gate as gate


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get crd" in joined:
            return '{"metadata":{"name":"virtualmachines.kubevirt.io"}}'
        if "get kubevirt" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "kind": "KubeVirt",
                            "metadata": {"name": "kubevirt", "namespace": "kubevirt"},
                            "status": {"conditions": [{"type": "Available", "status": "True"}]},
                        }
                    ]
                }
            )
        if "apply -f -" in joined:
            if not input_text or "VirtualMachine" not in input_text:
                raise AssertionError("apply command must receive a KubeVirt VM manifest")
            return "virtualmachine.kubevirt.io/ani-live-vm created\n"
        if "patch virtualmachine" in joined:
            return "virtualmachine.kubevirt.io/ani-live-vm patched\n"
        if "wait" in joined:
            return "condition met\n"
        if "get virtualmachine " in joined:
            return '{"kind":"VirtualMachine","metadata":{"name":"ani-live-vm"}}'
        if "get virtualmachineinstance" in joined:
            return json.dumps(
                {
                    "kind": "VirtualMachineInstance",
                    "metadata": {"name": "ani-live-vm"},
                    "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
                }
            )
        if "get --raw" in joined:
            return "subresource accepted\n"
        if "delete virtualmachine" in joined:
            return "virtualmachine.kubevirt.io/ani-live-vm deleted\n"
        raise AssertionError(f"unexpected command: {joined}")


class FakeWebSocketProber:
    def __init__(self) -> None:
        self.probes: list[tuple[str, str, str]] = []

    def probe(self, config: gate.LiveConfig, namespace: str, vm_name: str, subresource: str) -> dict[str, object]:
        self.probes.append((namespace, vm_name, subresource))
        return {
            "websocket_session_established": True,
            "http_status": 101,
            "subprotocol": gate.KUBEVIRT_WEBSOCKET_SUBPROTOCOL,
            "sent_bytes": 1 if subresource == "console" else 0,
            "received_bytes": 12 if subresource == "vnc" else 0,
        }


class KubeVirtVMLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_vm_start_stop_console_and_delete_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("kubevirt-crds-ready", check_ids)
        self.assertIn("kubevirt-control-plane-available", check_ids)
        self.assertIn("kubevirt-vm-created", check_ids)
        self.assertIn("kubevirt-vmi-ready", check_ids)
        self.assertIn("kubevirt-vnc-subresource", check_ids)
        self.assertIn("kubevirt-console-subresource", check_ids)
        self.assertIn("kubevirt-vm-stopped", check_ids)
        self.assertIn("kubevirt-vm-deleted", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--gate", ""]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not be empty", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_rejects_gate_path_surrounding_whitespace_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-kubevirt-vm-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-kubevirt-vm-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"malformed {gate_path}", str(raised.exception))

    def test_cli_reports_missing_doc_without_traceback(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_root = Path(tmpdir) / "missing-root"
            with (
                patch("sys.argv", ["validate_kubevirt_vm_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", missing_root),
                patch.object(gate, "ROOT", missing_root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("missing doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_cli_reports_malformed_doc_without_traceback(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_root = Path(tmpdir)
            root = doc_root / "repo"
            root.mkdir()
            (doc_root / "ANI-DOCS-INDEX.md").write_bytes(b"\xff")
            with (
                patch("sys.argv", ["validate_kubevirt_vm_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_creates_starts_checks_console_stops_and_deletes_vm(self) -> None:
        runner = FakeRunner()
        websocket_prober = FakeWebSocketProber()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                namespace="ani-tenant-tenant-a",
                vm_name="ani-live-vm",
            ),
            runner=runner,
            websocket_prober=websocket_prober,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["vm"], "ani-live-vm")
        self.assertIn(["kubectl", "get", "crd", "virtualmachines.kubevirt.io", "-o", "json"], runner.commands)
        self.assertTrue(any(command[-2:] == ["-f", "-"] for command in runner.commands))
        self.assertEqual(
            websocket_prober.probes,
            [("ani-tenant-tenant-a", "ani-live-vm", "vnc"), ("ani-tenant-tenant-a", "ani-live-vm", "console")],
        )
        self.assertEqual(
            result["websocket_sessions"]["vnc"],
            {
                "websocket_session_established": True,
                "http_status": 101,
                "subprotocol": gate.KUBEVIRT_WEBSOCKET_SUBPROTOCOL,
                "sent_bytes": 0,
                "received_bytes": 12,
            },
        )
        joined_commands = [" ".join(command) for command in runner.commands]
        stop_patch_indexes = [
            index
            for index, command in enumerate(joined_commands)
            if "patch virtualmachine" in command and '"running":false' in command
        ]
        self.assertTrue(stop_patch_indexes, "live gate must stop the KubeVirt VM before delete")
        stop_patch_index = stop_patch_indexes[0]
        delete_index = next(index for index, command in enumerate(joined_commands) if "delete virtualmachine" in command)
        self.assertLess(stop_patch_index, delete_index)
        self.assertTrue(any("wait --for=delete virtualmachineinstance/ani-live-vm" in command for command in joined_commands))

    def test_live_gate_rejects_missing_websocket_session(self) -> None:
        class MissingSessionProber(FakeWebSocketProber):
            def probe(self, config: gate.LiveConfig, namespace: str, vm_name: str, subresource: str) -> dict[str, object]:
                self.probes.append((namespace, vm_name, subresource))
                return {"websocket_session_established": False}

        runner = FakeRunner()
        prober = MissingSessionProber()

        with self.assertRaises(SystemExit) as raised:
            gate.run_live(
                gate.LiveConfig(
                    tenant_id="tenant-a",
                    namespace="ani-tenant-tenant-a",
                    vm_name="ani-live-vm",
                ),
                runner=runner,
                websocket_prober=prober,
            )

        self.assertIn("vnc websocket session was not established", str(raised.exception))
        joined_commands = [" ".join(command) for command in runner.commands]
        self.assertTrue(any("patch virtualmachine" in command and '"running":false' in command for command in joined_commands))
        self.assertTrue(any("delete virtualmachine" in command for command in joined_commands))

    def test_cli_live_mode_rejects_missing_tenant_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_kubevirt_vm_live_gate.py", "--live", "--tenant-id", ""]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id=" tenant-a ",
            vm_name="ani-live-vm",
            container_disk_image="quay.io/containerdisks/cirros:latest",
            memory="256Mi",
            wait_timeout="180s",
            kubeconfig="/tmp/kubeconfig",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("tenant_id must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "kubevirt-vm-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubevirt_vm_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
                                "--evidence-output",
                                f" {output} ",
                            ],
                        ):
                            with self.assertRaises(SystemExit) as raised:
                                gate.main()

        self.assertIn("evidence_output must not contain surrounding whitespace", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_empty_evidence_output_before_running(self) -> None:
        with patch.object(gate, "validate_live_config"):
            with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                with patch.object(gate, "write_live_evidence") as write_live_evidence:
                    with patch(
                        "sys.argv",
                        [
                            "validate_kubevirt_vm_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--namespace",
                            "ani-tenant-tenant-a",
                            "--evidence-output",
                            "",
                        ],
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            gate.main()

        self.assertIn("evidence_output must not be empty", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_directory_evidence_output_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubevirt_vm_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
                                "--evidence-output",
                                tmpdir,
                            ],
                        ):
                            with self.assertRaises(SystemExit) as raised:
                                gate.main()

        self.assertIn("evidence_output must be a file path", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_file_evidence_output_parent_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir) / "not-a-directory"
            parent.write_text("blocker", encoding="utf-8")
            output = parent / "kubevirt-vm-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubevirt_vm_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
                                "--evidence-output",
                                str(output),
                            ],
                        ):
                            with self.assertRaises(SystemExit) as raised:
                                gate.main()

        self.assertIn("evidence_output parent must be a directory", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_blocked_evidence_output_parent_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "blocked-parent"
            blocker.write_text("blocker", encoding="utf-8")
            output = blocker / "child" / "kubevirt-vm-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubevirt_vm_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
                                "--evidence-output",
                                str(output),
                            ],
                        ):
                            with self.assertRaises(SystemExit) as raised:
                                gate.main()

        self.assertIn("evidence_output parent must be a directory", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_unwritable_evidence_output_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "kubevirt-vm-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_kubevirt_vm_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--namespace",
                                    "ani-tenant-tenant-a",
                                    "--evidence-output",
                                    str(output),
                                ],
                            ):
                                with self.assertRaises(SystemExit) as raised:
                                    gate.main()
            finally:
                output.chmod(0o600)

        self.assertIn("evidence_output must be writable", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_rejects_unwritable_evidence_output_parent_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir) / "evidence"
            parent.mkdir()
            output = parent / "kubevirt-vm-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_kubevirt_vm_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--namespace",
                                    "ani-tenant-tenant-a",
                                    "--evidence-output",
                                    str(output),
                                ],
                            ):
                                with self.assertRaises(SystemExit) as raised:
                                    gate.main()
            finally:
                parent.chmod(0o700)

        self.assertIn("evidence_output parent must be writable", str(raised.exception))
        run_live.assert_not_called()
        write_live_evidence.assert_not_called()

    def test_cli_live_mode_writes_evidence_json_when_requested(self) -> None:
        fake_evidence = {
            "status": "passed",
            "namespace": "ani-tenant-tenant-a",
            "vm": "ani-live-vm",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "kubevirt-vm-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_kubevirt_vm_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--namespace",
                            "ani-tenant-tenant-a",
                            "--vm-name",
                            "ani-live-vm",
                            "--evidence-output",
                            str(output),
                        ],
                    ):
                        try:
                            gate.main()
                        except SystemExit:
                            pass

            self.assertTrue(output.exists())
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("kubevirt-vm-live-gate", written["id"])
            self.assertEqual("M1-KUBEVIRT-LIVE-A", written["profile"])
            for key, value in fake_evidence.items():
                self.assertEqual(value, written[key])


    def test_live_evidence_rejects_unusable_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "not-a-directory"
            blocker.write_text("blocker", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                gate.write_live_evidence(blocker / "evidence.json", {"status": "passed"})

        self.assertIn("evidence output unusable", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
