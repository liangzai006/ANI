#!/usr/bin/env python3
"""Tests for the Sprint 5 vCluster live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path

import validate_vcluster_live_gate as gate


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.posts: list[tuple[str, dict[str, object], str, str]] = []
        self.gets: list[tuple[str, str, str]] = []

    def run(self, command: list[str], env: dict[str, str] | None = None) -> str:
        self.commands.append(command)
        self.envs.append(env)
        if command[0] == "vcluster":
            return '{"major":"1","minor":"35","gitVersion":"v1.35.0"}'
        if command[0] == "kubectl":
            return '{"major":"1","minor":"30"}'
        return "ok"

    def post_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str = "") -> dict[str, object]:
        self.posts.append((url, payload, bearer_token, tenant_id))
        if url.endswith("/k8s-clusters"):
            return {
                "status_code": 201,
                "headers": {},
                "body": {
                    "id": "k8sclu-core-live",
                    "state": "running",
                    "tenant_id": "tenant-a",
                },
            }
        return {"status_code": 200, "headers": {"x-upstream": "vcluster"}, "body": {"kind": "Status"}}

    def get_json(self, url: str, bearer_token: str, tenant_id: str = "") -> dict[str, object]:
        self.gets.append((url, bearer_token, tenant_id))
        return {
            "status_code": 200,
            "headers": {},
            "body": {
                "items": [
                    {
                        "name": "ani-s02-live-workload",
                        "namespace": "default",
                        "kind": "Deployment",
                        "replicas": 1,
                        "ready_replicas": 1,
                        "status": "running",
                        "created_at": "2026-06-19T10:00:00Z",
                    }
                ],
                "total": 1,
                "next_cursor": None,
            },
        }


class VClusterCommandRunner(FakeRunner):
    def run(self, command: list[str], env: dict[str, str] | None = None) -> str:
        self.commands.append(command)
        self.envs.append(env)
        if command[0] == "vcluster":
            return '10:30:00 done vCluster is up and running\n{"major":"1","minor":"35","gitVersion":"v1.35.0"}\n'
        return "ok"


class VClusterLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_helm_kubeconfig_kubectl_and_proxy_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("helm-install", check_ids)
        self.assertIn("vcluster-kubeconfig", check_ids)
        self.assertIn("kubectl-version", check_ids)
        self.assertIn("vcluster-workload-create", check_ids)
        self.assertIn("core-proxy-version", check_ids)
        self.assertIn("core-workloads-list", check_ids)
        self.assertIn("vcluster-workload-cleanup", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_contract_gate_rejects_unpinned_helm_chart_version(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        for check in document["live_checks"]:
            if check["id"] == "helm-install":
                check["command"] = check["command"].replace(" --version 0.34.1", "")

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("helm-install must pin vCluster chart version 0.34.1", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_vcluster_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_vcluster_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-vcluster-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_vcluster_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_vcluster_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-vcluster-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_vcluster_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_vcluster_live_gate.py"]),
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
                patch("sys.argv", ["validate_vcluster_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_runs_helm_connect_kubectl_and_core_proxy(self) -> None:
        runner = FakeRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                cluster_id="k8sclu-live",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                vcluster_server="https://k8sclu-live.example",
                work_dir=Path("/tmp"),
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            runner.commands[0],
            [
                "helm",
                "upgrade",
                "--install",
                "k8sclu-live",
                "vcluster",
                "--repo",
                "https://charts.loft.sh",
                "--namespace",
                "ani-tenant-tenant-a",
                "--create-namespace",
                "--repository-config=",
                "--set",
                "sync.toHost.services.enabled=true",
                "--version",
                "0.34.1",
            ],
        )
        self.assertEqual(
            runner.commands[1],
            [
                "vcluster",
                "connect",
                "k8sclu-live",
                "--namespace",
                "ani-tenant-tenant-a",
                "--background-proxy=false",
                "--server",
                "https://k8sclu-live.example",
                "--",
                "kubectl",
                "get",
                "--raw",
                "/version",
            ],
        )
        self.assertEqual(
            runner.posts[0],
            (
                "http://127.0.0.1:3000/api/v1/k8s-clusters",
                {
                    "idempotency_key": "live-core-k8sclu-live",
                    "name": "k8sclu-live",
                    "version": "v1.35.0",
                },
                "ani-token",
                "tenant-a",
            ),
        )
        self.assertEqual(
            runner.posts[1],
            (
                "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-core-live/proxy",
                {
                    "idempotency_key": "live-proxy-k8sclu-core-live-version",
                    "method": "GET",
                    "path": "/version",
                    "query": {},
                    "body": {},
                },
                "ani-token",
                "tenant-a",
            ),
        )
        self.assertEqual(
            runner.gets[0],
            (
                "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-core-live/workloads?namespace=default&kind=Deployment",
                "ani-token",
                "tenant-a",
            ),
        )
        self.assertEqual(result["workload_count"], 1)
        self.assertEqual(result["workload_name"], "ani-s02-live-workload")
        self.assertEqual(result["cleanup"], "deleted")
        self.assertEqual(
            runner.commands[2],
            [
                "vcluster",
                "connect",
                "k8sclu-live",
                "--namespace",
                "ani-tenant-tenant-a",
                "--background-proxy=false",
                "--server",
                "https://k8sclu-live.example",
                "--",
                "kubectl",
                "-n",
                "default",
                "delete",
                "deployment",
                "ani-s02-live-workload",
                "--ignore-not-found=true",
            ],
        )
        self.assertEqual(
            runner.commands[3],
            [
                "vcluster",
                "connect",
                "k8sclu-live",
                "--namespace",
                "ani-tenant-tenant-a",
                "--background-proxy=false",
                "--server",
                "https://k8sclu-live.example",
                "--",
                "kubectl",
                "-n",
                "default",
                "create",
                "deployment",
                "ani-s02-live-workload",
                "--image",
                "registry.k8s.io/pause:3.10",
                "--replicas",
                "1",
            ],
        )
        self.assertEqual(runner.commands[4], runner.commands[2])

    def test_live_gate_uses_vcluster_connect_to_run_kubectl_version_without_printing_kubeconfig(self) -> None:
        runner = VClusterCommandRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                cluster_id="k8sclu-live",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                kubeconfig="/tmp/real-lab.kubeconfig",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertNotIn("kubeconfig", result)
        self.assertEqual(
            runner.commands[1],
            [
                "vcluster",
                "connect",
                "k8sclu-live",
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

    def test_live_gate_can_use_existing_vcluster_proxy_server_for_kubectl_steps(self) -> None:
        runner = FakeRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                cluster_id="k8sclu-live",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                kubeconfig="/tmp/real-lab.kubeconfig",
                proxy_server="http://127.0.0.1:18002",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            runner.commands[1],
            [
                "kubectl",
                "--server",
                "http://127.0.0.1:18002",
                "get",
                "--raw",
                "/version",
            ],
        )
        self.assertEqual(
            runner.commands[2],
            [
                "kubectl",
                "--server",
                "http://127.0.0.1:18002",
                "-n",
                "default",
                "delete",
                "deployment",
                "ani-s02-live-workload",
                "--ignore-not-found=true",
            ],
        )
        self.assertEqual(
            runner.commands[3],
            [
                "kubectl",
                "--server",
                "http://127.0.0.1:18002",
                "-n",
                "default",
                "create",
                "deployment",
                "ani-s02-live-workload",
                "--image",
                "registry.k8s.io/pause:3.10",
                "--replicas",
                "1",
            ],
        )

    def test_command_runner_reports_core_proxy_connection_errors_without_traceback(self) -> None:
        runner = gate.CommandRunner()
        with patch.object(gate.urllib.request, "urlopen", side_effect=gate.urllib.error.URLError("refused")):
            with self.assertRaises(RuntimeError) as raised:
                runner.post_json(
                    "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-live/proxy",
                    {"path": "/version"},
                    "ani-token",
                )

        self.assertIn("Core proxy request failed", str(raised.exception))
        self.assertIn("refused", str(raised.exception))

    def test_command_runner_reports_core_workloads_connection_errors_without_traceback(self) -> None:
        runner = gate.CommandRunner()
        with patch.object(gate.urllib.request, "urlopen", side_effect=gate.urllib.error.URLError("refused")):
            with self.assertRaises(RuntimeError) as raised:
                runner.get_json(
                    "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-live/workloads?namespace=default&kind=Deployment",
                    "ani-token",
                )

        self.assertIn("Core workloads request failed", str(raised.exception))
        self.assertIn("refused", str(raised.exception))

    def test_command_runner_reports_subprocess_timeout_without_hanging(self) -> None:
        runner = gate.CommandRunner()
        with patch.object(gate.subprocess, "run", side_effect=gate.subprocess.TimeoutExpired(["vcluster"], gate.COMMAND_TIMEOUT_SECONDS)):
            with self.assertRaises(RuntimeError) as raised:
                runner.run(["vcluster", "connect", "k8sclu-live"])

        self.assertIn("timed out after 120s", str(raised.exception))

    def test_cli_live_mode_rejects_missing_gateway_before_running_commands(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch(
                "sys.argv",
                [
                    "validate_vcluster_live_gate.py",
                    "--live",
                    "--tenant-id",
                    "tenant-a",
                    "--cluster-id",
                    "k8sclu-live",
                ],
            ):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_cli_live_mode_forwards_custom_tool_binaries(self) -> None:
        captured_config: gate.LiveConfig | None = None

        def capture_run_live(config: gate.LiveConfig) -> dict[str, object]:
            nonlocal captured_config
            captured_config = config
            return {"status": "passed"}

        with patch.object(gate, "validate_live_config"):
            with patch.object(gate, "run_live", side_effect=capture_run_live):
                with patch(
                    "sys.argv",
                    [
                        "validate_vcluster_live_gate.py",
                        "--live",
                        "--tenant-id",
                        "tenant-a",
                        "--cluster-id",
                        "k8sclu-live",
                        "--gateway-url",
                        "http://127.0.0.1:3000/api/v1",
                        "--ani-bearer-token",
                        "ani-token",
                        "--helm-binary",
                        "/opt/homebrew/bin/helm",
                        "--vcluster-binary",
                        "/tmp/vcluster",
                        "--kubectl-binary",
                        "/opt/homebrew/bin/kubectl",
                    ],
                ):
                    gate.main()

        self.assertIsNotNone(captured_config)
        self.assertEqual("/opt/homebrew/bin/helm", captured_config.helm_binary)
        self.assertEqual("/tmp/vcluster", captured_config.vcluster_binary)
        self.assertEqual("/opt/homebrew/bin/kubectl", captured_config.kubectl_binary)

    def test_cli_live_mode_forwards_namespace_override(self) -> None:
        captured_config: gate.LiveConfig | None = None

        def capture_run_live(config: gate.LiveConfig) -> dict[str, object]:
            nonlocal captured_config
            captured_config = config
            return {"status": "passed"}

        with patch.object(gate, "validate_live_config"):
            with patch.object(gate, "run_live", side_effect=capture_run_live):
                with patch(
                    "sys.argv",
                    [
                        "validate_vcluster_live_gate.py",
                        "--live",
                        "--tenant-id",
                        "tenant-a",
                        "--namespace",
                        "ani-tenant-tenant-a-vcluster",
                        "--cluster-id",
                        "k8sclu-live",
                        "--gateway-url",
                        "http://127.0.0.1:3000/api/v1",
                        "--ani-bearer-token",
                        "ani-token",
                    ],
                ):
                    gate.main()

        self.assertIsNotNone(captured_config)
        self.assertEqual("ani-tenant-tenant-a-vcluster", captured_config.namespace)

    def test_live_gate_passes_host_kubeconfig_to_helm_and_vcluster_commands(self) -> None:
        runner = FakeRunner()
        gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                namespace="ani-tenant-tenant-a-vcluster",
                cluster_id="k8sclu-live",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                kubeconfig="/tmp/real-lab.kubeconfig",
            ),
            runner=runner,
        )

        self.assertEqual("/tmp/real-lab.kubeconfig", runner.envs[0]["KUBECONFIG"])
        self.assertEqual("/tmp/real-lab.kubeconfig", runner.envs[1]["KUBECONFIG"])
        self.assertIn("ani-tenant-tenant-a-vcluster", runner.commands[0])
        self.assertIn("ani-tenant-tenant-a-vcluster", runner.commands[1])

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            cluster_id="k8sclu-live",
            gateway_url=" http://127.0.0.1:3000/api/v1 ",
            ani_bearer_token="ani-token",
            kubeconfig="/tmp/real-lab.kubeconfig",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/tool"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("gateway_url must not contain surrounding whitespace", str(raised.exception))

    def test_live_config_rejects_empty_chart_version(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            cluster_id="k8sclu-live",
            gateway_url="http://127.0.0.1:3000/api/v1",
            ani_bearer_token="ani-token",
            kubeconfig="/tmp/real-lab.kubeconfig",
            chart_version="",
        )

        with self.assertRaises(SystemExit) as raised:
            gate.validate_live_config(config)

        self.assertIn("live mode requires chart_version", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "vcluster-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
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
                            "validate_vcluster_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--cluster-id",
                            "k8sclu-live",
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
                                "validate_vcluster_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
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
            output = parent / "vcluster-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
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
            output = blocker / "child" / "vcluster-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_vcluster_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--cluster-id",
                                "k8sclu-live",
                                "--gateway-url",
                                "http://127.0.0.1:3000/api/v1",
                                "--ani-bearer-token",
                                "ani-token",
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
            output = Path(tmpdir) / "vcluster-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_vcluster_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--cluster-id",
                                    "k8sclu-live",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
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
            output = parent / "vcluster-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_vcluster_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--cluster-id",
                                    "k8sclu-live",
                                    "--gateway-url",
                                    "http://127.0.0.1:3000/api/v1",
                                    "--ani-bearer-token",
                                    "ani-token",
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
        fake_evidence = {"status": "passed", "kubectl_version": "v1.35.0", "proxy_status": 200}
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "vcluster-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_vcluster_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--cluster-id",
                            "k8sclu-live",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
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
            self.assertEqual("vcluster-live-gate", written["id"])
            self.assertEqual("M1-K8S-LIVE-A", written["profile"])
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
