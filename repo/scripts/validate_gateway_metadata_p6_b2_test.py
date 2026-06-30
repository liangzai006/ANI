#!/usr/bin/env python3
"""Tests for Gateway metadata persistence P6-B2 contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_gateway_metadata_p6_b2 as gate
import validate_registry_harbor_live_gate as harbor_gate


class GatewayMetadataP6B2Test(unittest.TestCase):
    def test_contract_validates_artifact_track_scripts(self) -> None:
        gate.validate_artifact_runner_scripts()
        gate.validate_harbor_gate_artifact_track_helpers()
        gate.validate_gate_yaml_optional_checks()

    def test_artifact_track_requires_repository_and_scan_image(self) -> None:
        args = harbor_gate.LiveArgs(
            gateway_url="https://gateway.example/api/v1",
            ani_bearer_token="token",
            harbor_url="https://harbor.example",
            harbor_username="admin",
            harbor_password="secret",
            tenant_id="tenant-a",
            repository="",
            scan_image="",
            evidence_output="",
            artifact_track=True,
        )
        with self.assertRaises(SystemExit) as raised:
            harbor_gate.validate_artifact_track_live_args(args)
        self.assertIn("artifact-track live mode requires --repository", str(raised.exception))

    def test_artifact_track_live_requires_non_empty_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "b2.json"
            args = harbor_gate.LiveArgs(
                gateway_url="https://gateway.example/api/v1",
                ani_bearer_token="token",
                harbor_url="https://harbor.example",
                harbor_username="admin",
                harbor_password="secret",
                tenant_id="tenant-a",
                repository="runtime",
                scan_image="default/runtime:latest",
                evidence_output=str(evidence),
                artifact_track=True,
            )

            with self.assertRaises(SystemExit) as raised:
                harbor_gate.validate_live(
                    args,
                    json_requester=empty_artifacts_requester,
                    harbor_requester=harbor_gate_requester,
                )

            self.assertIn("requires at least one Harbor artifact", str(raised.exception))


def empty_artifacts_requester(method: str, url: str, bearer_token: str, payload: dict | None = None) -> tuple[int, dict]:
    dev_profile = {"mode": "real", "provider": "harbor", "real_provider": True}
    project = harbor_gate.DEFAULT_REGISTRY_PROJECT_NAME
    if method == "POST" and url.endswith("/registry/projects"):
        return 201, {"id": "harbor-1", "name": project, "dev_profile": dev_profile}
    if method == "GET" and url.endswith("/registry/projects"):
        return 200, {"items": [{"name": project}], "total": 1}
    if method == "GET" and "/artifacts" in url:
        return 200, {"items": [], "total": 0}
    if method == "GET" and f"/registry/projects/{project}/repositories" in url:
        return 200, {"items": [{"name": "runtime"}], "total": 1}
    if method == "GET" and url.endswith(f"/registry/projects/{project}/scan-report"):
        return 200, {"status": "complete", "dev_profile": dev_profile}
    if method == "POST" and url.endswith(f"/registry/projects/{project}/pull-secret"):
        return 201, {"secret_ref": f"{project}/ani-registry-pull", "registry": "harbor.example", "dev_profile": dev_profile}
    raise AssertionError(f"unexpected request {method} {url}")


def harbor_gate_requester(method: str, url: str, username: str, password: str, tls_insecure: bool = False) -> tuple[int, dict]:
    if method == "GET" and url.endswith("/api/v2.0/health"):
        return 200, {"status": "healthy"}
    raise AssertionError(f"unexpected Harbor request {method} {url}")


if __name__ == "__main__":
    unittest.main()
