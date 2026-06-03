#!/usr/bin/env python3
"""Tests for the Sprint 5 reconcile controller HA live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_reconcile_ha_live_gate as gate


class FakeLiveRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.metrics_urls: list[str] = []
        self.lease_holders = ["worker-a", "worker-b"]

    def run(self, command: list[str]) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get pods" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "ani-reconcile-worker-a",
                                "labels": {
                                    "app": "ani-reconcile-worker",
                                    "ani.kubercloud.io/reconcile-identity": "worker-a",
                                },
                            }
                        },
                        {
                            "metadata": {
                                "name": "ani-reconcile-worker-b",
                                "labels": {
                                    "app": "ani-reconcile-worker",
                                    "ani.kubercloud.io/reconcile-identity": "worker-b",
                                },
                            }
                        },
                    ]
                }
            )
        if "delete pod ani-reconcile-worker-a" in joined:
            return "pod \"ani-reconcile-worker-a\" deleted\n"
        raise AssertionError(f"unexpected command: {joined}")

    def query_lease_holder(self, config: gate.LiveConfig) -> str:
        return self.lease_holders.pop(0)

    def fetch_metrics(self, url: str) -> str:
        self.metrics_urls.append(url)
        return (
            "# HELP ani_workload_reconcile_leader_active active leader\n"
            "ani_workload_reconcile_leader_active{leader=\"true\"} 1\n"
            "ani_workload_reconcile_ticks_total 7\n"
            "ani_workload_reconcile_successes_total 7\n"
            "ani_workload_reconcile_failures_total 0\n"
        )


class KubectlPsqlRunner(gate.LiveRunner):
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get pods" in joined:
            return "ani-reconcile-ha-postgres-0\n"
        if "exec -n ani-system ani-reconcile-ha-postgres-0" in joined:
            return "worker-a\n"
        raise AssertionError(f"unexpected command: {joined}")


class KubectlMetricsRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> str:
        self.commands.append(command)
        return "ani_workload_reconcile_ticks_total 1\nani_workload_reconcile_successes_total 0\nani_workload_reconcile_failures_total 0\n"


class ReconcileHALiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_leader_failover_and_metrics_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("deploy-two-reconcile-workers", check_ids)
        self.assertIn("leader-lease-acquired", check_ids)
        self.assertIn("leader-metrics-active", check_ids)
        self.assertIn("kill-leader-pod", check_ids)
        self.assertIn("follower-acquires-lease", check_ids)
        self.assertIn("reconcile-continues-after-failover", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-reconcile-ha-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-reconcile-ha-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_reconcile_ha_live_gate.py"]),
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
                patch("sys.argv", ["validate_reconcile_ha_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_observes_lease_deletes_leader_and_confirms_failover(self) -> None:
        runner = FakeLiveRunner()
        result = gate.run_live(
            gate.LiveConfig(
                database_url="postgres://ani:ani@127.0.0.1:5432/ani",
                namespace="ani-system",
                worker_selector="app=ani-reconcile-worker",
                metrics_url="http://127.0.0.1:18080/metrics",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["namespace"], "ani-system")
        self.assertEqual(result["worker_selector"], "app=ani-reconcile-worker")
        self.assertEqual(result["lease_name"], "workload-reconcile-controller")
        self.assertEqual(result["metrics_url"], "http://127.0.0.1:18080/metrics")
        self.assertEqual(result["initial_leader"], "worker-a")
        self.assertEqual(result["new_leader"], "worker-b")
        self.assertEqual(runner.commands[0], ["kubectl", "get", "pods", "-n", "ani-system", "-l", "app=ani-reconcile-worker", "-o", "json"])
        self.assertEqual(runner.commands[1], ["kubectl", "delete", "pod", "ani-reconcile-worker-a", "-n", "ani-system"])
        self.assertEqual(runner.metrics_urls, ["http://127.0.0.1:18080/metrics", "http://127.0.0.1:18080/metrics"])

    def test_live_runner_can_query_lease_through_kubectl_exec_psql(self) -> None:
        runner = KubectlPsqlRunner()
        config = gate.LiveConfig(
            database_url="postgres://ani:ani@ani-reconcile-ha-postgres:5432/ani?sslmode=disable",
            namespace="ani-system",
            worker_selector="app=ani-reconcile-worker",
            metrics_url="http://127.0.0.1:18080/metrics",
            psql_kubectl_namespace="ani-system",
            psql_kubectl_selector="app=ani-reconcile-ha-postgres",
        )

        holder = runner.query_lease_holder(config)

        self.assertEqual(holder, "worker-a")
        self.assertEqual(
            runner.commands[0],
            [
                "kubectl",
                "get",
                "pods",
                "-n",
                "ani-system",
                "-l",
                "app=ani-reconcile-ha-postgres",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
        )
        self.assertEqual(runner.commands[1][:6], ["kubectl", "exec", "-n", "ani-system", "ani-reconcile-ha-postgres-0", "--"])
        self.assertIn("psql", runner.commands[1])

    def test_live_gate_can_fetch_metrics_through_kubectl_raw_service_proxy(self) -> None:
        runner = KubectlMetricsRunner()
        config = gate.LiveConfig(
            database_url="postgres://ani:ani@127.0.0.1:5432/ani",
            namespace="ani-system",
            worker_selector="app=ani-reconcile-worker",
            metrics_url="kubernetes-raw",
            metrics_kubectl_raw_path="/api/v1/namespaces/ani-system/services/ani-reconcile-worker-metrics:9205/proxy/metrics",
        )

        metrics = gate.fetch_live_metrics(config, runner)

        self.assertIn("ani_workload_reconcile_ticks_total", metrics)
        self.assertEqual(
            runner.commands[0],
            [
                "kubectl",
                "get",
                "--raw",
                "/api/v1/namespaces/ani-system/services/ani-reconcile-worker-metrics:9205/proxy/metrics",
            ],
        )

    def test_cli_live_mode_rejects_missing_database_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_reconcile_ha_live_gate.py", "--live"]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            database_url=" postgres://ani:ani@127.0.0.1:5432/ani ",
            namespace="ani-system",
            worker_selector="app=ani-reconcile-worker",
            metrics_url="http://127.0.0.1:18080/metrics",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/tool"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("database_url must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "reconcile-ha-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_reconcile_ha_live_gate.py",
                                "--live",
                                "--database-url",
                                "postgres://ani:ani@127.0.0.1:5432/ani",
                                "--namespace",
                                "ani-system",
                                "--metrics-url",
                                "http://127.0.0.1:18080/metrics",
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
                            "validate_reconcile_ha_live_gate.py",
                            "--live",
                            "--database-url",
                            "postgres://ani:ani@127.0.0.1:5432/ani",
                            "--namespace",
                            "ani-system",
                            "--metrics-url",
                            "http://127.0.0.1:18080/metrics",
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
                                "validate_reconcile_ha_live_gate.py",
                                "--live",
                                "--database-url",
                                "postgres://ani:ani@127.0.0.1:5432/ani",
                                "--namespace",
                                "ani-system",
                                "--metrics-url",
                                "http://127.0.0.1:18080/metrics",
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
            output = parent / "reconcile-ha-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_reconcile_ha_live_gate.py",
                                "--live",
                                "--database-url",
                                "postgres://ani:ani@127.0.0.1:5432/ani",
                                "--namespace",
                                "ani-system",
                                "--metrics-url",
                                "http://127.0.0.1:18080/metrics",
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
            output = blocker / "child" / "reconcile-ha-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_reconcile_ha_live_gate.py",
                                "--live",
                                "--database-url",
                                "postgres://ani:ani@127.0.0.1:5432/ani",
                                "--namespace",
                                "ani-system",
                                "--metrics-url",
                                "http://127.0.0.1:18080/metrics",
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
            output = Path(tmpdir) / "reconcile-ha-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_reconcile_ha_live_gate.py",
                                    "--live",
                                    "--database-url",
                                    "postgres://ani:ani@127.0.0.1:5432/ani",
                                    "--namespace",
                                    "ani-system",
                                    "--metrics-url",
                                    "http://127.0.0.1:18080/metrics",
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
            output = parent / "reconcile-ha-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_reconcile_ha_live_gate.py",
                                    "--live",
                                    "--database-url",
                                    "postgres://ani:ani@127.0.0.1:5432/ani",
                                    "--namespace",
                                    "ani-system",
                                    "--metrics-url",
                                    "http://127.0.0.1:18080/metrics",
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
            "namespace": "ani-system",
            "lease_name": "workload-reconcile-controller",
            "worker_selector": "app=ani-reconcile-worker",
            "metrics_url": "http://127.0.0.1:18080/metrics",
            "initial_leader": "worker-a",
            "new_leader": "worker-b",
            "deleted_pod": "ani-reconcile-worker-a",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "reconcile-ha-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_reconcile_ha_live_gate.py",
                            "--live",
                            "--database-url",
                            "postgres://ani:ani@127.0.0.1:5432/ani",
                            "--namespace",
                            "ani-system",
                            "--metrics-url",
                            "http://127.0.0.1:18080/metrics",
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
            self.assertEqual("reconcile-ha-live-gate", written["id"])
            self.assertEqual("M1-RECONCILE-LIVE-A", written["profile"])
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
