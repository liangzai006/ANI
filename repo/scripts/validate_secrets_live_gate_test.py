#!/usr/bin/env python3
"""Tests for the Sprint 5 Secret live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_secrets_live_gate as gate


class FakeLiveRunner:
    def __init__(self) -> None:
        self.json_calls: list[tuple[str, dict[str, object], str, str]] = []
        self.commands: list[tuple[list[str], str | None]] = []

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        bearer_token: str,
        tenant_id: str = "",
    ) -> dict[str, object]:
        self.json_calls.append((url, payload, bearer_token, tenant_id))
        if url.endswith("/secrets"):
            return {
                "id": "sec-live",
                "tenant_id": "tenant-a",
                "name": "live-secret",
                "keys": ["password", "token"],
                "state": "active",
                "dev_profile": {
                    "mode": "real",
                    "provider": "kubernetes-secret-provider",
                    "real_provider": True,
                },
            }
        if url.endswith("/secrets/sec-live/bindings"):
            return {
                "id": "sbind-live",
                "secret_id": "sec-live",
                "tenant_id": "tenant-a",
                "state": "bound",
                "dev_profile": {"mode": "local", "provider": "local-secret-service", "real_provider": False},
            }
        raise AssertionError(f"unexpected JSON URL: {url}")

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append((command, input_text))
        joined = " ".join(command)
        if joined.endswith("get secret sec-live -n ani-tenant-tenant-a -o json"):
            return json.dumps(
                {
                    "metadata": {"name": "sec-live", "namespace": "ani-tenant-tenant-a"},
                    "data": {"password": "cEBzc3cwcmQ=", "token": "dDBrZW4="},
                }
            )
        if "wait --for=condition=Ready pod/ani-secret-live-pod" in joined:
            return "pod/ani-secret-live-pod condition met\n"
        if joined.endswith("logs ani-secret-live-pod -n ani-tenant-tenant-a"):
            return "env:p@ssw0rd\nfile:t0ken\n"
        if "wait --for=condition=Ready vmi/ani-secret-live-vm" in joined:
            return "virtualmachineinstance.kubevirt.io/ani-secret-live-vm condition met\n"
        if joined.endswith("get vmi ani-secret-live-vm -n ani-tenant-tenant-a -o json"):
            return json.dumps(
                {
                    "metadata": {"name": "ani-secret-live-vm", "namespace": "ani-tenant-tenant-a"},
                    "status": {"phase": "Running", "nodeName": "dev-phys-03"},
                }
            )
        if "get pod -n ani-tenant-tenant-a -l kubevirt.io/domain=ani-secret-live-vm -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "virt-launcher-ani-secret-live-vm-abcde",
                                "namespace": "ani-tenant-tenant-a",
                            }
                        }
                    ]
                }
            )
        if joined.endswith(
            "logs pod/virt-launcher-ani-secret-live-vm-abcde -n ani-tenant-tenant-a --all-containers=true --tail=500"
        ):
            return (
                "ANI_VM_SECRET_GUEST_PROBE_START\n"
                "NAME SIZE LABEL\n"
                "vdb 1M ANISECRET\n"
                "ANI_VM_SECRET_GUEST_PASSWORD=p@ssw0rd\n"
                "ANI_VM_SECRET_GUEST_TOKEN=t0ken\n"
                "ANI_VM_SECRET_GUEST_PROBE_DONE\n"
            )
        if command[:2] == ["kubectl", "apply"] and input_text:
            if "VirtualMachine" in input_text:
                return "virtualmachine.kubevirt.io/ani-secret-live-vm serverside-applied\n"
            return "pod/ani-secret-live-pod created\n"
        if joined.endswith("delete pod ani-secret-live-pod -n ani-tenant-tenant-a --ignore-not-found=true"):
            return "pod deleted\n"
        if joined.endswith("delete vm ani-secret-live-vm -n ani-tenant-tenant-a --ignore-not-found=true --wait=false"):
            return "virtualmachine.kubevirt.io/ani-secret-live-vm deleted\n"
        raise AssertionError(f"unexpected command: {joined}")


class SecretsLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_secret_write_pod_and_vm_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("core-create-kubernetes-secret", check_ids)
        self.assertIn("kubectl-read-secret", check_ids)
        self.assertIn("pod-secret-env-visible", check_ids)
        self.assertIn("pod-secret-file-visible", check_ids)
        self.assertIn("kubevirt-vm-secret-volume-accepted", check_ids)
        self.assertIn("kubevirt-vm-secret-volume-guest-visible", check_ids)

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_secrets_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_secrets_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-secrets-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_secrets_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_secrets_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-secrets-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_secrets_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_secrets_live_gate.py"]),
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
                patch("sys.argv", ["validate_secrets_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_runs_core_secret_write_pod_env_file_and_vm_volume_checks(self) -> None:
        runner = FakeLiveRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                password_value="p@ssw0rd",
                token_value="t0ken",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tenant_id"], "tenant-a")
        self.assertEqual(result["gateway_url"], "http://127.0.0.1:3000/api/v1")
        self.assertEqual(result["secret_id"], "sec-live")
        self.assertEqual(result["namespace"], "ani-tenant-tenant-a")
        self.assertEqual(result["pod"], "ani-secret-live-pod")
        self.assertEqual(result["vm"], "ani-secret-live-vm")
        self.assertEqual(
            result["vm_guest_secret"],
            {
                "guest_secret_volume_visible": True,
                "launcher_pod": "virt-launcher-ani-secret-live-vm-abcde",
                "node": "dev-phys-03",
                "secret_disk_label": "ANISECRET",
            },
        )
        self.assertEqual(runner.json_calls[0][0], "http://127.0.0.1:3000/api/v1/secrets")
        self.assertEqual(runner.json_calls[1][0], "http://127.0.0.1:3000/api/v1/secrets/sec-live/bindings")
        self.assertEqual(runner.json_calls[0][3], "tenant-a")
        self.assertEqual(runner.json_calls[1][3], "tenant-a")
        self.assertEqual(runner.json_calls[2][3], "tenant-a")
        self.assertEqual(runner.commands[0][0], ["kubectl", "get", "secret", "sec-live", "-n", "ani-tenant-tenant-a", "-o", "json"])

    def test_vm_secret_manifest_uses_kubevirt_disk_schema_without_read_only_field(self) -> None:
        manifest = json.loads(gate.vm_manifest("ani-tenant-tenant-a", "ani-secret-live-vm", "sec-live"))

        disks = manifest["spec"]["template"]["spec"]["domain"]["devices"]["disks"]
        secret_disk = next(disk for disk in disks if disk["name"] == "secret-file")
        self.assertNotIn("readOnly", secret_disk)
        volumes = manifest["spec"]["template"]["spec"]["volumes"]
        self.assertIn({"name": "secret-file", "secret": {"secretName": "sec-live"}}, volumes)

    def test_vm_guest_probe_manifest_attaches_secret_disk_and_cloud_init_probe(self) -> None:
        manifest = gate.vm_guest_probe_manifest("ani-tenant-tenant-a", "ani-secret-live-vm", "sec-live", "tenant-a")
        document = gate.yaml.safe_load(manifest)

        volumes = document["spec"]["template"]["spec"]["volumes"]
        self.assertIn(
            {"name": "secret-file", "secret": {"secretName": "sec-live", "volumeLabel": "ANISECRET"}},
            volumes,
        )
        self.assertIn("cloudInitNoCloud", volumes[2])
        user_data = volumes[2]["cloudInitNoCloud"]["userData"]
        self.assertIn("ANI_VM_SECRET_GUEST_PASSWORD", user_data)
        self.assertIn("ANI_VM_SECRET_GUEST_TOKEN", user_data)
        self.assertIn("/dev/vdb", user_data)

    def test_cli_live_mode_rejects_missing_gateway_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_secrets_live_gate.py", "--live"]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            gateway_url=" http://127.0.0.1:3000/api/v1 ",
            ani_bearer_token="ani-token",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("gateway_url must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "secrets-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_secrets_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
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
                            "validate_secrets_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
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
                                "validate_secrets_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--password-value",
                                "p@ssw0rd",
                                "--token-value",
                                "t0ken",
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
            output = parent / "secrets-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_secrets_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--password-value",
                                "p@ssw0rd",
                                "--token-value",
                                "t0ken",
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
            output = blocker / "child" / "secrets-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_secrets_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--password-value",
                                "p@ssw0rd",
                                "--token-value",
                                "t0ken",
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
            output = Path(tmpdir) / "secrets-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_secrets_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
                                    "--password-value",
                                    "p@ssw0rd",
                                    "--token-value",
                                    "t0ken",
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
            output = parent / "secrets-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_secrets_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
                                    "--password-value",
                                    "p@ssw0rd",
                                    "--token-value",
                                    "t0ken",
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
            "tenant_id": "tenant-a",
            "gateway_url": "http://127.0.0.1:3000/api/v1",
            "secret_id": "sec-live",
            "namespace": "ani-tenant-tenant-a",
            "pod": "ani-secret-live-pod",
            "vm": "ani-secret-live-vm",
            "vm_guest_secret": {"guest_secret_volume_visible": True, "secret_disk_label": "ANISECRET"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "secrets-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_secrets_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
                            "--password-value",
                            "p@ssw0rd",
                            "--token-value",
                            "t0ken",
                            "--evidence-output",
                            str(output),
                        ],
                    ):
                        try:
                            gate.main()
                        except SystemExit:
                            pass

            self.assertTrue(output.exists())
            written = output.read_text(encoding="utf-8")
            written_json = json.loads(written)
            self.assertEqual("secrets-live-gate", written_json["id"])
            self.assertEqual("M1-SECRETS-LIVE-A", written_json["profile"])
            for key, value in fake_evidence.items():
                self.assertEqual(value, written_json[key])
            self.assertNotIn("ani-token", written)
            self.assertNotIn("p@ssw0rd", written)
            self.assertNotIn("t0ken", written)


    def test_live_evidence_rejects_unusable_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "not-a-directory"
            blocker.write_text("blocker", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                gate.write_live_evidence(blocker / "evidence.json", {"status": "passed"})

        self.assertIn("evidence output unusable", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
