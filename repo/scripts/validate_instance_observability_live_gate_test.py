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

        self.assertIn("status must be contract or live", str(raised.exception))

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


if __name__ == "__main__":
    unittest.main()
