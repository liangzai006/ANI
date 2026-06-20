#!/usr/bin/env python3
"""Tests for Sprint 13 GPU inventory live gate contract."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_gpu_inventory_live_gate as gate


class GPUInventoryLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_gpu_inventory_and_occupancy_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("nvidia-device-plugin-node-capacity", check_ids)
        self.assertIn("core-gpu-inventory-list", check_ids)
        self.assertIn("core-gpu-occupancy-get", check_ids)
        self.assertIn("dcgm-exporter-metrics-readable", check_ids)

    def test_contract_gate_rejects_missing_check(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"] = [check for check in document["live_checks"] if check["id"] != "core-gpu-occupancy-get"]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("missing live checks: core-gpu-occupancy-get", str(raised.exception))

    def test_contract_gate_rejects_production_like_status(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["status"] = "production_like"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("status must be contract or live", str(raised.exception))

    def test_cli_reports_missing_gate_path_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-gpu-inventory-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_gpu_inventory_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_validates_docs(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_gpu_inventory_live_gate.py"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs") as validate_docs,
        ):
            gate.main()

        validate_docs.assert_called_once()

    def test_json_getter_reports_network_errors_without_traceback(self) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("network blocked")):
            with self.assertRaises(SystemExit) as raised:
                gate.default_json_getter("http://127.0.0.1:18004/api/v1/nodes", "")

        self.assertIn("could not read http://127.0.0.1:18004/api/v1/nodes", str(raised.exception))

    def test_live_requires_dcgm_metrics_url(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_gpu_inventory_live_gate.py", "--live", "--gateway-url", "http://core.example/api/v1"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("live mode requires --dcgm-metrics-url", str(raised.exception))

    def test_live_writes_non_sensitive_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "gpu-evidence.json"
            args = gate.LiveArgs(
                gateway_url="http://core.example/api/v1",
                ani_bearer_token="dev-token",
                kubectl_binary="kubectl",
                kubeconfig="local-secrets/kubeconfig",
                kubernetes_nodes_url="",
                dcgm_metrics_url="http://dcgm.example/metrics",
                evidence_output=str(evidence),
            )

            gate.validate_live(
                args,
                command_runner=lambda _: """{
  "items": [{
    "metadata": {"name": "gpu-node-a"},
    "status": {
      "capacity": {"nvidia.com/gpu": "2"},
      "allocatable": {"nvidia.com/gpu": "2"}
    }
  }]
}""",
                json_getter=lambda url, _: (
                    200,
                    {
                        "items": [{"id": "gpu-0"}, {"id": "gpu-1"}],
                        "total": 2,
                        "dev_profile": {"mode": "real", "provider": "kubernetes-gpu-inventory", "real_provider": True},
                    }
                    if url.endswith("/gpu-inventory")
                    else {
                        "total": 2,
                        "available": 2,
                        "in_use": 0,
                        "fault": 0,
                        "dev_profile": {"mode": "real", "provider": "kubernetes-gpu-inventory", "real_provider": True},
                    },
                ),
                text_getter=lambda _: (200, "DCGM_FI_DEV_GPU_UTIL{gpu=\"0\"} 0\n"),
            )

            content = evidence.read_text(encoding="utf-8")
            self.assertIn('"status": "passed"', content)
            self.assertIn('"gpu_capacity_total": 2', content)
            self.assertNotIn("dev-token", content)
            self.assertNotIn("local-secrets/kubeconfig", content)

    def test_live_can_read_nodes_from_kubernetes_nodes_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "gpu-evidence.json"
            args = gate.LiveArgs(
                gateway_url="http://core.example/api/v1",
                ani_bearer_token="dev-token",
                kubectl_binary="kubectl",
                kubeconfig="local-secrets/kubeconfig",
                kubernetes_nodes_url="http://127.0.0.1:18004/api/v1/nodes",
                dcgm_metrics_url="http://dcgm.example/metrics",
                evidence_output=str(evidence),
            )

            def json_getter(url: str, bearer_token: str) -> tuple[int, dict]:
                if url.endswith("/api/v1/nodes"):
                    self.assertEqual("", bearer_token)
                    return 200, {
                        "items": [{
                            "metadata": {"name": "gpu-node-a"},
                            "status": {
                                "capacity": {"nvidia.com/gpu": "2"},
                                "allocatable": {"nvidia.com/gpu": "2"},
                            },
                        }]
                    }
                if url.endswith("/gpu-inventory"):
                    self.assertEqual("dev-token", bearer_token)
                    return 200, {
                        "items": [{"id": "gpu-0"}, {"id": "gpu-1"}],
                        "total": 2,
                        "dev_profile": {"mode": "real", "provider": "kubernetes-gpu-inventory", "real_provider": True},
                    }
                return 200, {
                    "total": 2,
                    "available": 2,
                    "in_use": 0,
                    "fault": 0,
                    "dev_profile": {"mode": "real", "provider": "kubernetes-gpu-inventory", "real_provider": True},
                }

            def command_runner(_: list[str]) -> str:
                raise AssertionError("kubectl should not be called when kubernetes_nodes_url is provided")

            gate.validate_live(
                args,
                command_runner=command_runner,
                json_getter=json_getter,
                text_getter=lambda _: (200, "DCGM_FI_DEV_GPU_UTIL{gpu=\"0\"} 0\n"),
            )

            content = evidence.read_text(encoding="utf-8")
            self.assertIn('"status": "passed"', content)
            self.assertNotIn("dev-token", content)
            self.assertNotIn("local-secrets/kubeconfig", content)


if __name__ == "__main__":
    unittest.main()
