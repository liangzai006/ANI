#!/usr/bin/env python3
"""Unit tests for unified Harbor registry live gate runner."""

from __future__ import annotations

import unittest
from unittest import mock

import run_registry_harbor_live_gate as runner


class RunRegistryHarborLiveGateTest(unittest.TestCase):
    def test_build_config_artifact_track_defaults(self) -> None:
        with mock.patch.dict("os.environ", {"TENANT_ID": "tenant-a"}, clear=True):
            config = runner.build_config(
                runner.parse_args(["--track", "artifact", "--harbor-password", "secret"]),
                "secret",
            )
        self.assertEqual(config.track, "artifact")
        self.assertTrue(config.artifact_track)
        self.assertEqual(config.repository, "ani-live-gate-smoke")
        self.assertEqual(config.scan_image, "default/ani-live-gate-smoke:latest")

    def test_build_config_in_cluster_requires_bearer(self) -> None:
        config = runner.build_config(
            runner.parse_args(["--track", "in-cluster", "--harbor-password", "secret", "--tenant-id", "t"]),
            "secret",
        )
        with self.assertRaises(SystemExit):
            runner.validate_config(config)

    def test_build_config_pull_secret_dev_namespace(self) -> None:
        with mock.patch.dict("os.environ", {"TENANT_ID": "tenant-a", "RUN_ID": "run-a"}, clear=True):
            config = runner.build_config(
                runner.parse_args(
                    ["--track", "pull-secret-kubernetes", "--dev", "--harbor-password", "secret"]
                ),
                "secret",
            )
        self.assertTrue(config.pull_secret_kubernetes_track)
        self.assertEqual(config.pull_secret_kubernetes_namespace, "ani-tenant-a")


if __name__ == "__main__":
    unittest.main()
