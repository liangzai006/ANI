#!/usr/bin/env python3
"""Unit tests for Gateway metadata persistence P6-B3 contract validator."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import validate_gateway_metadata_p6_b3 as gate


ROOT = Path(__file__).resolve().parents[1]


class ValidateGatewayMetadataP6B3Test(unittest.TestCase):
    def test_validate_openapi_contract_requires_kubernetes_apply_path(self) -> None:
        fake_path = mock.Mock()
        fake_path.read_text.return_value = "no kubernetes apply"
        with mock.patch.object(gate, "OPENAPI", fake_path):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_openapi_contract()
            self.assertIn("openapi must define", str(raised.exception))

    def test_validate_harbor_gate_optional_check_requires_b3_check(self) -> None:
        with mock.patch(
            "validate_gateway_metadata_p6_b3.harbor_gate.load_gate",
            return_value={"optional_live_checks": [{"id": "other"}]},
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_harbor_gate_optional_check()
            self.assertIn("core-registry-pull-secret-kubernetes-apply", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
