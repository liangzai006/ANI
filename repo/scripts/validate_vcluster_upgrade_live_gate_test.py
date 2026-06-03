#!/usr/bin/env python3
"""Tests for the Sprint 5 vCluster upgrade live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_vcluster_upgrade_live_gate as gate


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.posts: list[tuple[str, dict[str, object], str]] = []
        self.starts: list[list[str]] = []
        self.waited_urls: list[str] = []

    def run(self, command: list[str], env: dict[str, str] | None = None) -> str:
        self.commands.append(command)
        self.envs.append(env)
        joined = " ".join(command)
        if command[0] == "kubectl" and "apply" in command:
            return "persistentvolume/ani-vcluster-upgrade-k8sclu-core-live configured"
        if joined.startswith("helm get values"):
            return json.dumps({"controlPlane": {"distro": {"k8s": {"version": "v1.31.0"}}}})
        if command[0] == "vcluster":
            return '10:30:00 done vCluster is up and running\n{"major":"1","minor":"31","gitVersion":"v1.31.0"}\n'
        if command[0] == "kubectl":
            return '{"major":"1","minor":"31","gitVersion":"v1.31.0"}'
        raise AssertionError(f"unexpected command: {joined}")

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        bearer_token: str,
        tenant_id: str = "",
    ) -> dict[str, object]:
        self.posts.append((url, payload, bearer_token))
        if url.endswith("/k8s-clusters"):
            return {
                "id": "k8sclu-core-live",
                "version": "v1.30.0",
                "state": "running",
                "dev_profile": {"mode": "real", "provider": "vcluster", "real_provider": True},
            }
        if url.endswith("/upgrade"):
            return {
                "id": "k8sclu-core-live",
                "version": "v1.31.0",
                "state": "running",
                "dev_profile": {"mode": "real", "provider": "vcluster", "real_provider": True},
            }
        if url.endswith("/proxy"):
            return {"status_code": 200, "headers": {"x-upstream": "vcluster"}, "body": {"gitVersion": "v1.31.0"}}
        raise AssertionError(f"unexpected JSON URL: {url}")

    def start(self, command: list[str], env: dict[str, str] | None = None) -> "FakeProcess":
        self.starts.append(command)
        self.envs.append(env)
        return FakeProcess()

    def wait_url(self, url: str) -> None:
        self.waited_urls.append(url)


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> None:
        return None


class VClusterUpgradeLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_core_helm_kubeconfig_kubectl_and_proxy_upgrade_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("core-cluster-register", check_ids)
        self.assertIn("dev-hostpath-pv", check_ids)
        self.assertIn("core-upgrade-cluster", check_ids)
        self.assertIn("helm-values-target-version", check_ids)
        self.assertIn("kubectl-version-after-upgrade", check_ids)
        self.assertIn("local-proxy-after-upgrade", check_ids)
        self.assertIn("core-proxy-version-after-upgrade", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-vcluster-upgrade-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-vcluster-upgrade-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py"]),
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
                patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_runs_core_create_pv_upgrade_helm_values_kubectl_and_core_proxy(self) -> None:
        runner = FakeRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                cluster_id="k8sclu-live-upgrade",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                kubeconfig="/tmp/real-lab.kubeconfig",
                target_version="v1.31.0",
                local_proxy_port=18002,
                work_dir=Path("/tmp"),
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["target_version"], "v1.31.0")
        self.assertEqual(result["core_cluster_id"], "k8sclu-core-live")
        self.assertEqual(
            runner.posts[0],
            (
                "http://127.0.0.1:3000/api/v1/k8s-clusters",
                {
                    "idempotency_key": "live-upgrade-create-k8sclu-live-upgrade",
                    "name": "k8sclu-live-upgrade",
                    "version": "v1.30.0",
                },
                "ani-token",
            ),
        )
        self.assertEqual(runner.commands[0][0:3], ["kubectl", "--kubeconfig", "/tmp/real-lab.kubeconfig"])
        self.assertIn("apply", runner.commands[0])
        self.assertEqual(
            runner.posts[1],
            (
                "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-core-live/upgrade",
                {"idempotency_key": "live-upgrade-k8sclu-core-live-v1.31.0", "version": "v1.31.0"},
                "ani-token",
            ),
        )
        self.assertEqual(
            runner.commands[1],
            ["helm", "get", "values", "k8sclu-core-live", "--namespace", "ani-tenant-tenant-a", "-a", "-o", "json"],
        )
        self.assertEqual(
            runner.commands[2],
            [
                "vcluster",
                "connect",
                "k8sclu-core-live",
                "--namespace",
                "ani-tenant-tenant-a",
                "--background-proxy=false",
                "--",
                "kubectl",
                "get",
                "--raw",
                "/version",
            ],
        )
        self.assertEqual(runner.starts[0][0:5], ["vcluster", "connect", "k8sclu-core-live", "--namespace", "ani-tenant-tenant-a"])
        self.assertEqual(runner.waited_urls[0], "http://127.0.0.1:18002/version")
        self.assertEqual(runner.posts[2][1]["path"], "/version")

    def test_cli_live_mode_rejects_missing_gateway_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_vcluster_upgrade_live_gate.py", "--live"]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            cluster_id="k8sclu-live",
            gateway_url=" http://127.0.0.1:3000/api/v1 ",
            ani_bearer_token="ani-token",
            kubeconfig="/tmp/real-lab.kubeconfig",
            target_version="v1.31.0",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/tool"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("gateway_url must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "vcluster-upgrade-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_upgrade_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--target-version",
                                "v1.31.0",
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
                            "validate_vcluster_upgrade_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--cluster-id",
                            "k8sclu-live",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
                            "--target-version",
                            "v1.31.0",
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
                                "validate_vcluster_upgrade_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--target-version",
                                "v1.31.0",
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
            output = parent / "vcluster-upgrade-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_upgrade_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--target-version",
                                "v1.31.0",
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
            output = blocker / "child" / "vcluster-upgrade-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_upgrade_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
                                "--target-version",
                                "v1.31.0",
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
            output = Path(tmpdir) / "vcluster-upgrade-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_vcluster_upgrade_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--cluster-id",
                                    "k8sclu-live",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
                                    "--target-version",
                                    "v1.31.0",
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
            output = parent / "vcluster-upgrade-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_vcluster_upgrade_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--cluster-id",
                                    "k8sclu-live",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
                                    "--target-version",
                                    "v1.31.0",
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
            "core_cluster_id": "k8sclu-core-live",
            "target_version": "v1.31.0",
            "kubectl_version": "v1.31.0",
            "proxy_status": 200,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "vcluster-upgrade-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_vcluster_upgrade_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--cluster-id",
                            "k8sclu-live",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
                            "--target-version",
                            "v1.31.0",
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
            self.assertEqual("vcluster-upgrade-live-gate", written["id"])
            self.assertEqual("M1-K8S-LIVE-C", written["profile"])
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
