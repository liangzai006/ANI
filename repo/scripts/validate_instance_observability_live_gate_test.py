#!/usr/bin/env python3
"""Tests for Sprint 13 instance observability Prometheus live gate contract."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_instance_observability_live_gate as gate


class InstanceObservabilityLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_prometheus_and_instance_observation_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("prometheus-health-ready", check_ids)
        self.assertIn("core-instance-logs-list", check_ids)
        self.assertIn("core-instance-events-list", check_ids)
        self.assertIn("core-instance-metrics-get", check_ids)
        self.assertIn("core-instance-security-events-list", check_ids)
        self.assertIn("core-instance-exec-session-create", check_ids)

    def test_contract_gate_rejects_missing_check(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"] = [check for check in document["live_checks"] if check["id"] != "core-instance-metrics-get"]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("missing live checks: core-instance-metrics-get", str(raised.exception))

    def test_contract_gate_requires_curl(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["required_tools"] = []

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("required_tools must include curl", str(raised.exception))

    def test_contract_gate_rejects_runtime_ready_status(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["status"] = "runtime_ready"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("status must be contract, live or passed", str(raised.exception))

    def test_cli_reports_missing_gate_path_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-instance-observability-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_instance_observability_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_validates_docs(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_instance_observability_live_gate.py"]),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs") as validate_docs,
        ):
            gate.main()

        validate_docs.assert_called_once()

    def test_cli_live_invokes_automated_validator(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        evidence_path = Path(tempfile.gettempdir()) / "ani-instance-observability-evidence.json"
        with (
            patch(
                "sys.argv",
                [
                    "validate_instance_observability_live_gate.py",
                    "--live",
                    "--gateway-url",
                    "https://gateway.example/api/v1",
                    "--ani-bearer-token",
                    "redacted-test-token",
                    "--prometheus-url",
                    "https://prometheus.example",
                    "--evidence-output",
                    str(evidence_path),
                ],
            ),
            patch.object(gate, "load_gate", return_value=document),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_live") as validate_live,
        ):
            gate.main()

        validate_live.assert_called_once()
        live_args = validate_live.call_args.args[0]
        self.assertEqual(live_args.gateway_url, "https://gateway.example/api/v1")
        self.assertEqual(live_args.prometheus_url, "https://prometheus.example")
        self.assertEqual(live_args.evidence_output, str(evidence_path))

    def test_production_shaped_live_rejects_local_gateway(self) -> None:
        args = gate.LiveArgs(
            gateway_url="http://127.0.0.1:18004/api/v1",
            ani_bearer_token="redacted-test-token",
            prometheus_url="https://prometheus.example",
            kubeconfig="",
            namespace="ani-tenant-tenant-a",
            instance_name="sprint13-observability-live",
            evidence_output="",
            production_shaped=True,
            cleanup=True,
        )

        with self.assertRaises(SystemExit) as raised:
            gate.validate_production_shaped_live_args(args)

        self.assertIn("non-local production gateway URL", str(raised.exception))

    def test_target_manifest_uses_single_rfc3339_event_timestamp(self) -> None:
        manifest = gate.target_manifest("ani-tenant-tenant-a", "sprint13-observability-live")

        self.assertIn("firstTimestamp:", manifest)
        self.assertIn("lastTimestamp:", manifest)
        self.assertIn('Z"', manifest)

    def test_live_derives_target_namespace_from_core_tenant_id(self) -> None:
        args = gate.LiveArgs(
            gateway_url="https://gateway.example/api/v1",
            ani_bearer_token="redacted-test-token",
            prometheus_url="https://prometheus.example",
            kubeconfig="",
            namespace="auto",
            instance_name="sprint13-observability-live",
            evidence_output="",
            production_shaped=True,
            cleanup=False,
        )
        responses = {
            ("POST", "https://gateway.example/api/v1/instances"): (201, {"instance": {"id": "inst-1", "tenant_id": "tenant_a"}}),
            ("GET", "https://gateway.example/api/v1/instances/inst-1/logs?limit=20"): (200, {"items": [{"message": "ok"}], "total": 1}),
            ("GET", "https://gateway.example/api/v1/instances/inst-1/events?type=Warning"): (200, {"items": [{"reason": "Warning"}], "total": 1}),
            ("GET", "https://gateway.example/api/v1/instances/inst-1/metrics"): (200, {"cpu_utilization_pct": 1.0}),
            ("GET", "https://gateway.example/api/v1/instances/inst-1/security-events?severity=warning"): (200, {"items": [{"severity": "warning"}], "total": 1}),
            ("POST", "https://gateway.example/api/v1/instances/inst-1/exec"): (200, {"ws_url": "wss://gateway.example/api/v1/instances/sprint13/exec/session-1"}),
        }

        def json_requester(method: str, url: str, _token: str, _payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
            return responses[(method, url)]

        with patch.object(gate, "ensure_target_pod") as ensure_target_pod:
            gate.validate_live(args, json_requester=json_requester, text_requester=lambda _url: (200, "ready"))

        ensure_target_pod.assert_called_once()
        self.assertEqual(args.namespace, "ani-tenant-tenant-a")


if __name__ == "__main__":
    unittest.main()
