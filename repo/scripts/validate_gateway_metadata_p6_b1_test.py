#!/usr/bin/env python3
"""Tests for Gateway metadata persistence P6-B1 contract."""

from __future__ import annotations

import unittest

import validate_gateway_metadata_p6_b1 as gate


class GatewayMetadataP6B1Test(unittest.TestCase):
    def test_contract_validates_registry_secret_and_runner(self) -> None:
        gate.validate_registry_secret_manifest()
        gate.validate_in_cluster_runner()
        gate.validate_gateway_profile_s08()


if __name__ == "__main__":
    unittest.main()
