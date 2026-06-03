#!/usr/bin/env python3
"""Tests for the Sprint 5 K8s node pool live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_k8s_node_pool_live_gate as gate


class FakeLiveRunner:
    def __init__(self) -> None:
        self.json_calls: list[tuple[str, str, dict[str, object], str, str]] = []
        self.commands: list[tuple[list[str], str | None]] = []
        self.machine_deployment_replicas = 1

    def post_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str) -> dict[str, object]:
        self.json_calls.append(("POST", url, payload, bearer_token, tenant_id))
        if url.endswith("/node-pools"):
            return {
                "id": "k8snp-live",
                "tenant_id": "tenant-a",
                "cluster_id": "k8sclu-live",
                "name": "gpu-pool",
                "node_count": 1,
                "instance_type": "gpu.l4.xlarge",
                "state": "running",
                "gpu": {"vendor": "nvidia", "model": "L4", "count": 1, "resource_name": "nvidia.com/gpu"},
                "dev_profile": {"mode": "real", "provider": "clusterapi-provider", "real_provider": True},
            }
        raise AssertionError(f"unexpected JSON URL: {url}")

    def patch_json(self, url: str, payload: dict[str, object], bearer_token: str, tenant_id: str) -> dict[str, object]:
        self.json_calls.append(("PATCH", url, payload, bearer_token, tenant_id))
        if url.endswith("/node-pools/k8snp-live"):
            self.machine_deployment_replicas = int(payload["node_count"])
            return {
                "id": "k8snp-live",
                "tenant_id": "tenant-a",
                "cluster_id": "k8sclu-live",
                "name": "gpu-pool",
                "node_count": payload["node_count"],
                "instance_type": payload["instance_type"],
                "state": "running",
                "gpu": payload["gpu"],
                "dev_profile": {"mode": "real", "provider": "clusterapi-provider", "real_provider": True},
            }
        raise AssertionError(f"unexpected JSON URL: {url}")

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append((command, input_text))
        joined = " ".join(command)
        if "get machinedeployment gpu-pool" in joined:
            return json.dumps(
                {
                    "metadata": {
                        "name": "gpu-pool",
                        "namespace": "ani-tenant-tenant-a",
                        "labels": {
                            "ani.kubercloud.io/node-pool-id": "k8snp-live",
                            "ani.kubercloud.io/gpu-vendor": "nvidia",
                        },
                    },
                    "spec": {
                        "replicas": self.machine_deployment_replicas,
                        "template": {
                            "metadata": {
                                "labels": {
                                    "ani.kubercloud.io/gpu-vendor": "nvidia",
                                    "ani.kubercloud.io/gpu-model": "L4",
                                },
                                "annotations": {
                                    "ani.kubercloud.io/gpu-count": "1",
                                    "ani.kubercloud.io/gpu-resource-name": "nvidia.com/gpu",
                                },
                            },
                            "spec": {
                                "clusterName": "vc-a",
                                "bootstrap": {"dataSecretName": "gpu-pool-bootstrap"},
                                "infrastructureRef": {
                                    "apiVersion": "infrastructure.cluster.x-k8s.io/v1beta1",
                                    "kind": "ANIMachineTemplate",
                                    "name": "gpu-pool",
                                },
                            },
                        },
                    },
                    "status": {
                        "replicas": self.machine_deployment_replicas,
                        "readyReplicas": self.machine_deployment_replicas,
                        "availableReplicas": self.machine_deployment_replicas,
                        "upToDateReplicas": self.machine_deployment_replicas,
                        "conditions": [{"type": "Available", "status": "True"}],
                    },
                }
            )
        if "get machineset -n ani-tenant-tenant-a -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "gpu-pool-ms",
                                "namespace": "ani-tenant-tenant-a",
                                "labels": {"ani.kubercloud.io/node-pool-id": "k8snp-live"},
                                "ownerReferences": [{"kind": "MachineDeployment", "name": "gpu-pool"}],
                            },
                            "spec": {"replicas": self.machine_deployment_replicas},
                            "status": {
                                "replicas": self.machine_deployment_replicas,
                                "readyReplicas": self.machine_deployment_replicas,
                                "availableReplicas": self.machine_deployment_replicas,
                                "upToDateReplicas": self.machine_deployment_replicas,
                                "conditions": [{"type": "Ready", "status": "True"}],
                            },
                        }
                    ]
                }
            )
        if "get machine -n ani-tenant-tenant-a -l ani.kubercloud.io/node-pool-id=k8snp-live -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": f"gpu-pool-machine-{index}",
                                "namespace": "ani-tenant-tenant-a",
                                "labels": {"ani.kubercloud.io/node-pool-id": "k8snp-live"},
                            },
                            "spec": {
                                "providerID": f"kubevirt://gpu-pool-machine-{index}",
                                "infrastructureRef": {"kind": "KubevirtMachine", "name": f"gpu-pool-machine-{index}"},
                            },
                            "status": {
                                "nodeRef": {"name": f"gpu-pool-machine-{index}"},
                                "addresses": [{"type": "InternalIP", "address": f"10.16.0.{40 + index}"}],
                                "conditions": [
                                    {"type": "Ready", "status": "True"},
                                    {"type": "Available", "status": "True"},
                                ],
                            },
                        }
                        for index in range(1, self.machine_deployment_replicas + 1)
                    ]
                }
            )
        if "get kubevirtmachine -n ani-tenant-tenant-a -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {"name": f"gpu-pool-machine-{index}", "namespace": "ani-tenant-tenant-a"},
                            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                        }
                        for index in range(1, self.machine_deployment_replicas + 1)
                    ]
                }
            )
        if "get vm -n ani-tenant-tenant-a -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {"name": f"gpu-pool-machine-{index}", "namespace": "ani-tenant-tenant-a"},
                            "status": {"printableStatus": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
                        }
                        for index in range(1, self.machine_deployment_replicas + 1)
                    ]
                }
            )
        if "get vmi -n ani-tenant-tenant-a -o json" in joined:
            return json.dumps(
                {
                    "items": [
                        {
                            "metadata": {"name": f"gpu-pool-machine-{index}", "namespace": "ani-tenant-tenant-a"},
                            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
                        }
                        for index in range(1, self.machine_deployment_replicas + 1)
                    ]
                }
            )
        if command[:2] == ["kubectl", "apply"] and input_text:
            return "pod/ani-node-pool-gpu-smoke created\n"
        if "wait --for=condition=PodScheduled pod/ani-node-pool-gpu-smoke" in joined:
            return "pod/ani-node-pool-gpu-smoke condition met\n"
        if joined.endswith("delete pod ani-node-pool-gpu-smoke -n ani-tenant-tenant-a --ignore-not-found=true"):
            return "pod deleted\n"
        raise AssertionError(f"unexpected command: {joined}")


class K8sNodePoolLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_core_clusterapi_scale_and_gpu_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("core-create-node-pool", check_ids)
        self.assertIn("clusterapi-machinedeployment-created", check_ids)
        self.assertIn("core-scale-node-pool", check_ids)
        self.assertIn("clusterapi-machinedeployment-scaled", check_ids)
        self.assertIn("clusterapi-machinesets-ready", check_ids)
        self.assertIn("clusterapi-machines-ready", check_ids)
        self.assertIn("capk-kubevirtmachines-ready", check_ids)
        self.assertIn("capk-vms-ready", check_ids)
        self.assertIn("gpu-workload-scheduled", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-k8s-node-pool-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-k8s-node-pool-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_k8s_node_pool_live_gate.py"]),
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
                patch("sys.argv", ["validate_k8s_node_pool_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_runs_core_node_pool_clusterapi_scale_and_gpu_scheduling_checks(self) -> None:
        runner = FakeLiveRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                cluster_id="k8sclu-live",
                gateway_url="http://127.0.0.1:3000/api/v1",
                ani_bearer_token="ani-token",
                node_pool_name="gpu-pool",
                instance_type="gpu.l4.xlarge",
                initial_node_count=1,
                scaled_node_count=3,
                gpu_vendor="nvidia",
                gpu_model="L4",
                gpu_count=1,
                gpu_resource_name="nvidia.com/gpu",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["node_pool_id"], "k8snp-live")
        self.assertEqual(result["scaled_replicas"], 3)
        self.assertEqual(result["readiness"]["machines"]["ready_count"], 3)
        self.assertEqual(result["readiness"]["kubevirt_machines"]["ready_count"], 3)
        self.assertEqual(result["readiness"]["virtual_machines"]["vm_ready_count"], 3)
        self.assertEqual(result["readiness"]["virtual_machines"]["vmi_ready_count"], 3)
        self.assertEqual(runner.json_calls[0][0], "POST")
        self.assertEqual(runner.json_calls[0][1], "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-live/node-pools")
        self.assertEqual(runner.json_calls[0][4], "tenant-a")
        self.assertEqual(runner.json_calls[1][0], "PATCH")
        self.assertEqual(runner.json_calls[1][1], "http://127.0.0.1:3000/api/v1/k8s-clusters/k8sclu-live/node-pools/k8snp-live")
        self.assertEqual(runner.json_calls[1][4], "tenant-a")
        self.assertEqual(
            runner.commands[0][0],
            ["kubectl", "get", "machinedeployment", "gpu-pool", "-n", "ani-tenant-tenant-a", "-o", "json"],
        )
        self.assertIn("nvidia.com/gpu", runner.commands[-2][1] or "")

    def test_cli_live_mode_rejects_missing_gateway_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_k8s_node_pool_live_gate.py", "--live"]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            cluster_id="k8sclu-live",
            gateway_url=" http://127.0.0.1:3000/api/v1 ",
            ani_bearer_token="ani-token",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("gateway_url must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "node-pool-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_k8s_node_pool_live_gate.py",
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
                            "validate_k8s_node_pool_live_gate.py",
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
                                "validate_k8s_node_pool_live_gate.py",
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
            output = parent / "node-pool-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_k8s_node_pool_live_gate.py",
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
            output = blocker / "child" / "node-pool-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_k8s_node_pool_live_gate.py",
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
            output = Path(tmpdir) / "node-pool-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_k8s_node_pool_live_gate.py",
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
            output = parent / "node-pool-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_k8s_node_pool_live_gate.py",
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
        fake_evidence = {
            "status": "passed",
            "node_pool_id": "k8snp-live",
            "machine_deployment": "gpu-pool",
            "namespace": "ani-tenant-tenant-a",
            "scaled_replicas": 3,
            "gpu_workload": "ani-node-pool-gpu-smoke",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "node-pool-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_k8s_node_pool_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--cluster-id",
                            "k8sclu-live",
                            "--gateway-url",
                            "http://127.0.0.1:3000/api/v1",
                            "--ani-bearer-token",
                            "ani-token",
                            "--node-pool-name",
                            "gpu-pool",
                            "--scaled-node-count",
                            "3",
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
            self.assertEqual("k8s-node-pool-live-gate", written["id"])
            self.assertEqual("M1-K8S-LIVE-B", written["profile"])
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
