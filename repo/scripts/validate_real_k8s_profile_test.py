#!/usr/bin/env python3
"""Tests for the Sprint 5 REAL-K8S-LAB-A profile gate."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_real_k8s_profile as gate


REQUIRED_CONTRACT_GATE_IDS = {
    "vcluster-live-gate",
    "vcluster-upgrade-live-gate",
    "k8s-node-pool-live-gate",
    "kubeovn-network-live-gate",
    "kubevirt-vm-live-gate",
    "reconcile-ha-live-gate",
    "kms-sm4-live-gate",
    "secrets-live-gate",
}


class RealK8sProfileGateTest(unittest.TestCase):
    def valid_kubeconfig_text(self) -> str:
        return "\n".join(
            [
                "apiVersion: v1",
                "kind: Config",
                "clusters:",
                "- name: real-lab",
                "  cluster:",
                "    server: https://127.0.0.1:6443",
                "contexts:",
                "- name: real-lab",
                "  context:",
                "    cluster: real-lab",
                "    user: real-lab",
                "current-context: real-lab",
                "users:",
                "- name: real-lab",
                "  user:",
                "    token: token",
                "",
            ]
        )

    def component_live_env(self) -> dict[str, str]:
        return {
            "ANI_GATEWAY_URL": "http://127.0.0.1:3000/api/v1",
            "ANI_BEARER_TOKEN": "ani-token",
            "ANI_LIVE_K8S_CLUSTER_ID": "k8sclu-live",
            "KUBECONFIG": "/tmp/real-lab.kubeconfig",
            "DATABASE_URL": "postgres://ani:ani@127.0.0.1:5432/ani",
            "RECONCILE_WORKER_METRICS_URL": "http://127.0.0.1:9090/metrics",
            "KMS_PROVIDER_BASE_URL": "http://127.0.0.1:8081",
            "KMS_PROVIDER_BEARER_TOKEN": "kms-token",
            "OBJECTSTORE_LIVE_PUT_URL": "http://127.0.0.1:9000/put",
            "OBJECTSTORE_LIVE_GET_URL": "http://127.0.0.1:9000/get",
        }

    def component_summary_command(self, gate_id: str, evidence_output: Path | str) -> list[str]:
        profile = gate.load_profile(gate.PROFILE)
        gate_entry = next(entry for entry in profile["contract_gates"] if entry["id"] == gate_id)
        return [sys.executable, str(gate.ROOT / gate_entry["validator_script"]), "--live", "--evidence-output", str(evidence_output)]

    def with_component_gate_required_env(self, profile: dict, evidence: dict) -> dict:
        evidence = copy.deepcopy(evidence)
        required_env_by_gate = {
            entry["id"]: list(entry.get("required_env", []))
            for entry in profile.get("contract_gates", [])
            if isinstance(entry.get("id"), str)
        }
        status_value = evidence.get("status")
        include_live_validator_script = isinstance(status_value, str) and status_value in {"component_live", "component_live_failed"}
        validator_script_by_gate = {}
        if include_live_validator_script:
            validator_script_by_gate = {
                entry["id"]: str(entry.get("validator_script", ""))
                for entry in profile.get("contract_gates", [])
                if isinstance(entry.get("id"), str)
            }
        for gate_entry in evidence.get("component_gates", []):
            if not isinstance(gate_entry, dict):
                continue
            gate_id = gate_entry.get("id")
            if isinstance(gate_id, str) and "required_env" not in gate_entry:
                gate_entry["required_env"] = required_env_by_gate.get(gate_id, [])
            if include_live_validator_script and isinstance(gate_id, str) and "validator_script" not in gate_entry:
                gate_entry["validator_script"] = validator_script_by_gate.get(gate_id, "")
        return evidence

    def component_summary_report(self, profile: dict, evidence: dict, **kwargs: object) -> dict:
        evidence = self.with_component_gate_required_env(profile, evidence)
        return gate.component_summary_report(profile, evidence, **kwargs)

    def test_profile_indexes_all_component_contract_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        gate.validate_contract(profile)

        contract_gates = profile.get("contract_gates")
        self.assertIsInstance(contract_gates, list)
        gate_ids = {entry["id"] for entry in contract_gates}
        self.assertEqual(REQUIRED_CONTRACT_GATE_IDS, gate_ids)
        for entry in contract_gates:
            self.assertTrue(entry["command"].startswith("make validate-"))
            self.assertTrue((gate.ROOT / entry["manifest"]).exists())
            self.assertTrue((gate.ROOT / entry["validator_script"]).exists())

    def test_contract_validation_rejects_gate_command_validator_mismatch(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"][0]["command"] = "make validate-secrets-live-gate"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("command target validate-secrets-live-gate does not run scripts/validate_vcluster_live_gate.py", str(raised.exception))

    def test_contract_validation_rejects_gate_profile_manifest_mismatch(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"][0]["profile"] = "M1-SECRETS-LIVE-A"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate profile M1-SECRETS-LIVE-A does not match manifest profile M1-K8S-LIVE-A", str(raised.exception))

    def test_contract_validation_rejects_gate_manifest_duplicate_live_check_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "vcluster-live-gate.yaml"
            manifest.write_text(
                """
profile: M1-K8S-LIVE-A
status: contract
live_checks:
  - id: helm-install
    command: helm upgrade --install
    pass_condition: command_succeeds
  - id: helm-install
    command: vcluster connect
    pass_condition: stdout_contains_kubeconfig
""".lstrip(),
                encoding="utf-8",
            )
            profile["contract_gates"][0]["manifest"] = str(manifest)

            with self.assertRaises(SystemExit) as raised:
                gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate manifest duplicate live check id: helm-install", str(raised.exception))

    def test_contract_validation_rejects_gate_manifest_live_check_missing_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "vcluster-live-gate.yaml"
            manifest.write_text(
                """
profile: M1-K8S-LIVE-A
status: contract
live_checks:
  - id: helm-install
    pass_condition: command_succeeds
""".lstrip(),
                encoding="utf-8",
            )
            profile["contract_gates"][0]["manifest"] = str(manifest)

            with self.assertRaises(SystemExit) as raised:
                gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate manifest live check command must be a non-empty string", str(raised.exception))

    def test_contract_validation_rejects_gate_manifest_unsupported_pass_condition(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "vcluster-live-gate.yaml"
            manifest.write_text(
                """
profile: M1-K8S-LIVE-A
status: contract
live_checks:
  - id: helm-install
    command: helm upgrade --install
    pass_condition: not_a_real_condition
""".lstrip(),
                encoding="utf-8",
            )
            profile["contract_gates"][0]["manifest"] = str(manifest)

            with self.assertRaises(SystemExit) as raised:
                gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate manifest live check pass_condition unsupported: not_a_real_condition", str(raised.exception))

    def test_contract_validation_supports_vcluster_connect_generated_kubeconfig_condition(self) -> None:
        for condition in (
            "vcluster_connect_runs_kubectl_with_generated_kubeconfig",
            "http_2xx_response_has_cluster_id",
            "guest_console_logs_include_secret_volume_values",
        ):
            self.assertIn(condition, gate.SUPPORTED_CONTRACT_GATE_MANIFEST_PASS_CONDITIONS)

    def test_contract_validation_rejects_gate_manifest_missing_validator_required_live_check(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "vcluster-live-gate.yaml"
            manifest.write_text(
                """
profile: M1-K8S-LIVE-A
status: contract
live_checks:
  - id: helm-install
    command: helm upgrade --install
    pass_condition: command_succeeds
  - id: kubectl-version
    command: kubectl --kubeconfig /tmp/vcluster.yaml get --raw /version
    pass_condition: json_has_kubernetes_version
  - id: core-proxy-version
    command: curl /api/v1/k8s-clusters/cluster/proxy/version
    pass_condition: http_2xx
""".lstrip(),
                encoding="utf-8",
            )
            profile["contract_gates"][0]["manifest"] = str(manifest)

            with self.assertRaises(SystemExit) as raised:
                gate.validate_contract(profile)

        self.assertIn(
            "vcluster-live-gate manifest missing validator required live checks: core-cluster-register, vcluster-kubeconfig",
            str(raised.exception),
        )

    def test_contract_validation_rejects_gate_profile_missing_validator_required_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = Path(tmpdir) / "vcluster_validator.py"
            validator.write_text(
                '''
PROFILE = "M1-K8S-LIVE-A"
GATE_ID = "vcluster-live-gate"
REQUIRED_CHECKS = {"helm-install", "vcluster-kubeconfig", "kubectl-version", "core-proxy-version"}
REQUIRED_ENV = {"KUBECONFIG", "ANI_GATEWAY_URL", "ANI_BEARER_TOKEN", "MISSING_LIVE_ENV"}
'''.lstrip(),
                encoding="utf-8",
            )
            profile["contract_gates"][0]["validator_script"] = str(validator)

            makefile = gate.read(gate.ROOT / "Makefile")
            makefile = makefile.replace(
                "python scripts/validate_vcluster_live_gate.py",
                f"python {validator}",
                1,
            )

            with patch.object(gate, "read", side_effect=lambda path: makefile if path == gate.ROOT / "Makefile" else Path(path).read_text(encoding="utf-8")):
                with self.assertRaises(SystemExit) as raised:
                    gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate profile missing validator required env: MISSING_LIVE_ENV", str(raised.exception))

    def test_contract_validation_rejects_gate_validator_identity_mismatch(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = Path(tmpdir) / "wrong_validator.py"
            validator.write_text('PROFILE = "M1-SECRETS-LIVE-A"\nGATE_ID = "secrets-live-gate"\n', encoding="utf-8")
            profile["contract_gates"][0]["validator_script"] = str(validator)

            makefile = gate.read(gate.ROOT / "Makefile")
            makefile = makefile.replace(
                "python scripts/validate_vcluster_live_gate.py",
                f"python {validator}",
                1,
            )

            with patch.object(gate, "read", side_effect=lambda path: makefile if path == gate.ROOT / "Makefile" else Path(path).read_text(encoding="utf-8")):
                with self.assertRaises(SystemExit) as raised:
                    gate.validate_contract(profile)

        self.assertIn("vcluster-live-gate validator GATE_ID mismatch: expected vcluster-live-gate, got secrets-live-gate", str(raised.exception))

    def test_profile_documents_required_env_for_each_component_gate(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        gate.validate_contract(profile)

        gates = {entry["id"]: entry for entry in profile["contract_gates"]}
        for gate_id, entry in gates.items():
            self.assertIsInstance(entry.get("required_env"), list, gate_id)
            self.assertTrue(entry["required_env"], gate_id)
            self.assertTrue(all(isinstance(name, str) and name for name in entry["required_env"]), gate_id)
        self.assertIn("ANI_GATEWAY_URL", gates["vcluster-live-gate"]["required_env"])
        self.assertIn("KUBECONFIG", gates["kubeovn-network-live-gate"]["required_env"])
        self.assertIn("DATABASE_URL", gates["reconcile-ha-live-gate"]["required_env"])
        self.assertIn("OBJECTSTORE_LIVE_PUT_URL", gates["kms-sm4-live-gate"]["required_env"])

    def test_contract_validation_rejects_missing_contract_gate(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"] = [
            entry for entry in profile.get("contract_gates", []) if entry.get("id") != "kubevirt-vm-live-gate"
        ]

        with self.assertRaises(SystemExit):
            gate.validate_contract(profile)

    def test_load_profile_rejects_missing_external_profile_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing-profile.yaml"

            with self.assertRaises(SystemExit) as raised:
                gate.load_profile(missing)

        self.assertIn("missing", str(raised.exception))
        self.assertIn("missing-profile.yaml", str(raised.exception))

    def test_load_profile_rejects_unreadable_profile_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(SystemExit) as raised:
                gate.load_profile(Path(tmpdir))

        self.assertIn("profile unreadable", str(raised.exception))

    def test_load_profile_rejects_malformed_profile_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            malformed = Path(tmpdir) / "malformed-profile.yaml"
            malformed.write_text("profile: [\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                gate.load_profile(malformed)

        self.assertIn("profile malformed", str(raised.exception))
        self.assertIn("malformed-profile.yaml", str(raised.exception))

    def test_contract_validation_rejects_non_integer_minimum_nodes_without_traceback(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["minimum_nodes"] = "not-an-integer"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("minimum_nodes must be an integer", str(raised.exception))

    def test_contract_validation_rejects_non_string_live_check_field(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"][0]["command"] = ["kubectl", "get", "nodes"]

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes live check command must be a non-empty string", str(raised.exception))

    def test_contract_validation_rejects_unsupported_live_check_pass_condition(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"][0]["pass_condition"] = "not_a_real_condition"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes live check pass_condition unsupported: not_a_real_condition", str(raised.exception))

    def test_contract_validation_rejects_duplicate_component_live_check_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"].append(dict(profile["components"]["kubernetes"]["live_checks"][0]))

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes duplicate live check id: kubernetes-nodes-ready", str(raised.exception))

    def test_contract_validation_rejects_non_kubectl_live_check_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"][0]["command"] = "echo ok"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes live check command must start with kubectl", str(raised.exception))

    def test_contract_validation_rejects_malformed_contract_gate_live_check_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kms_sm4_and_secret"]["live_checks"][1]["command"] = "python scripts/validate_kms_sm4_live_gate.py"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kms_sm4_and_secret live check command must be a make validate-* target", str(raised.exception))

    def test_contract_validation_rejects_json_live_check_without_json_output_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"][0]["command"] = "kubectl get nodes"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes live check command must request JSON output", str(raised.exception))

    def test_contract_validation_allows_stdout_live_check_without_json_output_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        gate.validate_contract(profile)

        stdout_checks = [
            check
            for check in profile["components"]["kms_sm4_and_secret"]["live_checks"]
            if check["pass_condition"] == "stdout_yes"
        ]
        self.assertTrue(stdout_checks)

    def test_contract_validation_rejects_mutating_json_live_check_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kubernetes"]["live_checks"][0]["command"] = "kubectl delete pods -A -o json"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kubernetes JSON live check command must use kubectl get", str(raised.exception))

    def test_contract_validation_rejects_stdout_live_check_without_auth_can_i(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["components"]["kms_sm4_and_secret"]["live_checks"][0]["command"] = "kubectl get pods -A"

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(profile)

        self.assertIn("kms_sm4_and_secret stdout live check command must use kubectl auth can-i", str(raised.exception))

    def test_contract_validation_rejects_component_gate_without_required_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"][0].pop("required_env", None)

        with self.assertRaises(SystemExit):
            gate.validate_contract(profile)

    def test_contract_validation_rejects_invalid_required_env_name(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"][0]["required_env"] = ["KUBECONFIG", "bad-env-name"]

        with self.assertRaises(SystemExit):
            gate.validate_contract(profile)

    def test_contract_validation_rejects_duplicate_component_gate_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        profile["contract_gates"].append(dict(profile["contract_gates"][0]))

        with self.assertRaises(SystemExit):
            gate.validate_contract(profile)

    def test_live_validation_returns_structured_evidence_for_required_checks(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with patch.object(gate, "condition_passed", return_value=True):
                evidence = gate.validate_live(profile, "/tmp/real-lab.kubeconfig")

        self.assertIsInstance(evidence, dict)
        self.assertEqual("REAL-K8S-LAB-A", evidence["profile"])
        self.assertEqual("live", evidence["status"])
        self.assertTrue(evidence["passed"])
        self.assertTrue(evidence["kubeconfig_provided"])
        self.assertEqual(3, evidence["minimum_nodes"])
        checks = evidence["checks"]
        self.assertEqual({"total": len(checks), "passed": len(checks), "failed": 0}, evidence["summary"])
        self.assertTrue(all(check["passed"] for check in checks))
        check_ids = {(check["component"], check["id"]) for check in checks}
        self.assertIn(("kubernetes", "kubernetes-nodes-ready"), check_ids)
        self.assertIn(("kube_ovn", "kubeovn-vpc-crd"), check_ids)
        self.assertIn(("kubevirt", "kubevirt-vm-crd"), check_ids)
        self.assertIn(("vcluster", "vcluster-workloads"), check_ids)
        self.assertNotIn(("kms_sm4_and_secret", "kms-provider-config"), check_ids)

    def test_main_writes_live_evidence_json_when_requested(self) -> None:
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "live",
            "checks": [{"component": "kubernetes", "id": "kubernetes-nodes-ready", "passed": True}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(self.valid_kubeconfig_text(), encoding="utf-8")
            output = Path(tmpdir) / "real-k8s-live-evidence.json"

            with patch.object(gate, "validate_live", return_value=fake_evidence):
                with patch(
                    "sys.argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--live",
                        "--kubeconfig",
                        str(kubeconfig),
                        "--evidence-output",
                        str(output),
                    ],
                ):
                    gate.main()

            self.assertEqual(fake_evidence, json.loads(output.read_text(encoding="utf-8")))

    def test_live_evidence_rejects_unusable_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "not-a-directory"
            blocker.write_text("blocker", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                gate.write_live_evidence(blocker / "real-k8s-live-evidence.json", {"status": "live"})

        self.assertIn("profile output unusable", str(raised.exception))

    def test_main_rejects_evidence_output_with_surrounding_whitespace_before_writing(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "real-k8s-live.json"
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--evidence-output", f" {output} "]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                patch.object(gate, "write_live_evidence") as writer,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("profile output path must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_empty_evidence_output_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--evidence-output", ""]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_live") as live,
            patch.object(gate, "write_live_evidence") as writer,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("profile output path must not be empty", str(raised.exception))
        live.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_uncreatable_evidence_output_parent_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "not-a-directory"
            blocker.write_text("blocker\n", encoding="utf-8")
            output = blocker / "child" / "real-k8s-live.json"
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--evidence-output", str(output)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                patch.object(gate, "write_live_evidence") as writer,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("profile output parent must be a directory", str(raised.exception))
        live.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_uncreatable_evidence_output_parent_due_permissions_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir) / "unwritable-parent"
            parent.mkdir()
            parent.chmod(0o500)
            try:
                output = parent / "child" / "real-k8s-live.json"
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--evidence-output", str(output)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                    patch.object(gate, "write_live_evidence") as writer,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                parent.chmod(0o700)

        self.assertIn("profile output parent must be writable", str(raised.exception))
        live.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_unwritable_evidence_output_before_component_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "component-live-summary.json"
            output.write_text("old\n", encoding="utf-8")
            output.chmod(0o400)
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--component-live", "--evidence-output", str(output)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_component_live_gates", return_value={"component_gates": [], "passed": True}) as live_gates,
                    patch.object(gate, "write_live_evidence") as writer,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                output.chmod(0o600)

        self.assertIn("profile output path must be writable", str(raised.exception))
        live_gates.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_unwritable_evidence_output_parent_before_component_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir) / "unwritable-summary-dir"
            parent.mkdir()
            parent.chmod(0o500)
            try:
                with (
                    patch.object(
                        sys,
                        "argv",
                        ["validate_real_k8s_profile.py", "--component-live", "--evidence-output", str(parent / "summary.json")],
                    ),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_component_live_gates", return_value={"component_gates": [], "passed": True}) as live_gates,
                    patch.object(gate, "write_live_evidence") as writer,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                parent.chmod(0o700)

        self.assertIn("profile output parent must be writable", str(raised.exception))
        live_gates.assert_not_called()
        writer.assert_not_called()

    def test_main_rejects_component_env_template_output_with_surrounding_whitespace_before_writing(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "real-k8s-component-live.env"
            with (
                patch.object(
                    sys,
                    "argv",
                    ["validate_real_k8s_profile.py", "--component-env-template-output", f" {output} "],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "write_component_env_template") as writer,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("profile output path must not contain surrounding whitespace", str(raised.exception))
        writer.assert_not_called()

    def test_main_rejects_empty_component_env_template_output_before_writing(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(
                sys,
                "argv",
                ["validate_real_k8s_profile.py", "--component-env-template-output", ""],
            ),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "write_component_env_template") as writer,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("profile output path must not be empty", str(raised.exception))
        writer.assert_not_called()

    def test_main_rejects_profile_path_with_surrounding_whitespace_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--profile", f" {gate.PROFILE} "]),
            patch.object(gate, "load_profile", return_value=profile) as load_profile,
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("profile path must not contain surrounding whitespace", str(raised.exception))
        load_profile.assert_not_called()

    def test_main_rejects_empty_profile_path_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--profile", ""]),
            patch.object(gate, "load_profile", return_value=profile) as load_profile,
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("profile path must not be empty", str(raised.exception))
        load_profile.assert_not_called()

    def test_main_rejects_kubeconfig_path_with_surrounding_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", " /tmp/real-lab.kubeconfig "]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_live") as live,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("kubeconfig path must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_empty_kubeconfig_path_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", ""]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_live") as live,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("kubeconfig path must not be empty", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_missing_kubeconfig_path_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "missing-real-lab.kubeconfig"
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path must exist", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_directory_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "kubeconfig-dir"
            kubeconfig.mkdir()
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path must be a file", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_unreadable_kubeconfig_file_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
            kubeconfig.chmod(0o200)
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                kubeconfig.chmod(0o600)

        self.assertIn("kubeconfig path must be readable", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_malformed_kubeconfig_file_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text("apiVersion: [\n", encoding="utf-8")
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path must be valid YAML", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_missing_required_fields_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path missing required field: clusters", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_empty_api_version_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                self.valid_kubeconfig_text().replace("apiVersion: v1", "apiVersion: ''"),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path apiVersion must not be empty", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_api_version_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                self.valid_kubeconfig_text().replace("apiVersion: v1", "apiVersion: ' v1 '"),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path apiVersion must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_empty_kind_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                self.valid_kubeconfig_text().replace("kind: Config", "kind: ''"),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path kind must not be empty", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_kind_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                self.valid_kubeconfig_text().replace("kind: Config", "kind: ' Config '"),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path kind must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_empty_required_collections_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters: []",
                        "contexts: []",
                        "current-context: real-lab",
                        "users: []",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path field must not be empty: clusters", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_cluster_entry_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- real-lab",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path clusters entries must be objects", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_context_entry_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path contexts entries must be objects", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_user_entry_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- real-lab",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users entries must be objects", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_cluster_entry_missing_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path clusters entries must contain a non-empty string name", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_context_entry_empty_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: ''",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path contexts entries must contain a non-empty string name", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_user_entry_non_string_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: 42",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users entries must contain a non-empty string name", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_duplicate_cluster_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.2:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path clusters names must be unique", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_duplicate_context_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path contexts names must be unique", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_duplicate_user_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "- name: real-lab",
                        "  user:",
                        "    token: other-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users names must be unique", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_cluster_entry_non_object_payload_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "- name: stale-lab",
                        "  cluster: invalid",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path clusters entries must contain a cluster object", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_context_entry_non_object_payload_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "- name: stale-lab",
                        "  context: invalid",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path contexts entries must contain a context object", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_user_entry_non_object_payload_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "- name: stale-lab",
                        "  user: invalid",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users entries must contain a user object", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_unresolved_current_context_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: other-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context must reference a context", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: ' real-lab '",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_context_name_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: ' real-lab '",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path contexts name must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_unresolved_cluster_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: missing-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context cluster must reference a cluster", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: ' real-lab '",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster must not contain surrounding whitespace", str(raised.exception)
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_cluster_name_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: ' real-lab '",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path clusters name must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_unresolved_user_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: missing-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context user must reference a user", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: ' real-lab '",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context user must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace: true",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context namespace must be a string", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace:",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context namespace must be a string", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace: ''",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context namespace must be a non-empty string", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace: ' real-lab '",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context namespace must not contain surrounding whitespace", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn(" real-lab ", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_invalid_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace: Real_Lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context namespace must be a valid Kubernetes namespace name",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("Real_Lab", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_namespace_system_namespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "    namespace: kube-system",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context namespace must not use a Kubernetes system namespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("kube-system", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_user_name_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: ' real-lab '",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users name must not contain surrounding whitespace", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_missing_server_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster: {}",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context cluster server must not be empty", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_invalid_server_url_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: not-a-url",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context cluster server must be an http(s) URL", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_server_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: 'https://127.0.0.1:6443 '",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster server must not contain surrounding whitespace",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_insecure_skip_tls_verify_non_boolean_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    insecure-skip-tls-verify: 'true'",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster insecure-skip-tls-verify must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_insecure_skip_tls_verify_null_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    insecure-skip-tls-verify:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster insecure-skip-tls-verify must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_data_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority-data: true",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority-data must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_data_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority-data:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority-data must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_data_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        '    certificate-authority-data: ""',
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority-data must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_data_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority-data: 'LS0tCg== '",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority-data must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("LS0tCg", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_data_invalid_base64_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority-data: not-base64!!",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority-data must be valid base64",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("not-base64", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: true",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        '    certificate-authority: ""',
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: '/etc/kubernetes/pki/ca.crt '",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("/etc/kubernetes/pki/ca.crt", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_missing_file_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: missing-ca.crt",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority file must exist",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("missing-ca.crt", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_directory_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            ca_dir = Path(tmpdir) / "real-lab-ca-dir"
            ca_dir.mkdir()
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: real-lab-ca-dir",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority file must be a file",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("real-lab-ca-dir", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_certificate_authority_unreadable_file_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            ca_file = Path(tmpdir) / "real-lab-ca.crt"
            ca_file.write_text("test-ca", encoding="utf-8")
            ca_file.chmod(0o200)
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: real-lab-ca.crt",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                ca_file.chmod(0o600)

        self.assertIn(
            "kubeconfig path current-context cluster certificate-authority file must be readable",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("real-lab-ca.crt", str(raised.exception))
        live.assert_not_called()

    def test_main_accepts_kubeconfig_current_context_cluster_relative_certificate_authority_file_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            ca_file = Path(tmpdir) / "real-lab-ca.crt"
            ca_file.write_text("test-ca", encoding="utf-8")
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    certificate-authority: real-lab-ca.crt",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_rejects_kubeconfig_current_context_cluster_tls_server_name_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    tls-server-name: true",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster tls-server-name must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_tls_server_name_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    tls-server-name:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster tls-server-name must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_tls_server_name_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        '    tls-server-name: ""',
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster tls-server-name must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_tls_server_name_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    tls-server-name: 'api.real-lab.local '",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster tls-server-name must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("api.real-lab.local", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_proxy_url_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    proxy-url: true",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster proxy-url must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_proxy_url_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    proxy-url:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster proxy-url must be a string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_proxy_url_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        '    proxy-url: ""',
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster proxy-url must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_proxy_url_invalid_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    proxy-url: not-a-url",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster proxy-url must be an http(s) or socks5 URL",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("not-a-url", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_proxy_url_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    proxy-url: 'http://proxy.local:8080 '",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster proxy-url must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("http://proxy.local:8080", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_disable_compression_non_boolean_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    disable-compression: sometimes",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster disable-compression must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_cluster_disable_compression_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "    disable-compression:",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context cluster disable-compression must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_missing_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path users entries must contain a user object", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_empty_auth_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user: {}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("kubeconfig path current-context user auth material must not be empty", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_empty_auth_value_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: ''",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must be a non-empty string",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_unknown_only_auth_value_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    notes: present",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material must contain a non-empty value",
            str(raised.exception),
        )
        self.assertNotIn("present", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_empty_auth_provider_object_with_scoped_diagnostic_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider: {}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider name must be a non-empty string",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_empty_exec_object_with_scoped_diagnostic_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec: {}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec command must be a non-empty string",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_null_auth_provider_with_scoped_diagnostic_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider must be an object",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_null_exec_with_scoped_diagnostic_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec must be an object",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_allows_kubeconfig_current_context_user_unknown_whitespace_with_supported_auth_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "    notes: ' operator note '",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_allows_kubeconfig_current_context_user_unknown_nested_auth_like_field_with_supported_auth_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "    notes:",
                        "      token: 123",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_rejects_kubeconfig_current_context_user_empty_auth_string_with_other_auth_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: ''",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_null_auth_string_only_with_scoped_diagnostic_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must be a non-empty string",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_null_auth_string_with_other_auth_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token:",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_value_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: ' bearer-secret '",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" bearer-secret ", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_value_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: 123",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material token must be a string",
            str(raised.exception),
        )
        self.assertNotIn("123", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_certificate_data_invalid_base64_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate-data: not-base64!!",
                        "    client-key-data: dGVzdC1jbGllbnQta2V5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-certificate-data must be valid base64",
            str(raised.exception),
        )
        self.assertNotIn("not-base64", str(raised.exception))
        self.assertNotIn("test-client-key", str(raised.exception))
        self.assertNotIn("dGVzdC1jbGllbnQta2V5", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_key_data_invalid_base64_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "    client-key-data: not-base64!!",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-key-data must be valid base64",
            str(raised.exception),
        )
        self.assertNotIn("not-base64", str(raised.exception))
        self.assertNotIn("dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_token_file_missing_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    tokenFile: missing-token.txt",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material tokenFile file must exist",
            str(raised.exception),
        )
        self.assertNotIn("missing-token.txt", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_token_file_directory_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "token-dir"
            token_file.mkdir()
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    tokenFile: token-dir",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material tokenFile file must be a file",
            str(raised.exception),
        )
        self.assertNotIn("token-dir", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_token_file_unreadable_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "real-lab-token.txt"
            token_file.write_text("secret-token", encoding="utf-8")
            token_file.chmod(0o200)
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    tokenFile: real-lab-token.txt",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                token_file.chmod(0o600)

        self.assertIn(
            "kubeconfig path current-context user auth material tokenFile file must be readable",
            str(raised.exception),
        )
        self.assertNotIn("secret-token", str(raised.exception))
        self.assertNotIn("real-lab-token.txt", str(raised.exception))
        live.assert_not_called()

    def test_main_accepts_kubeconfig_current_context_user_relative_token_file_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "real-lab-token.txt"
            token_file.write_text("secret-token", encoding="utf-8")
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    tokenFile: real-lab-token.txt",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_rejects_kubeconfig_current_context_user_client_certificate_missing_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate: missing-client.crt",
                        "    client-key-data: dGVzdC1jbGllbnQta2V5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-certificate file must exist",
            str(raised.exception),
        )
        self.assertNotIn("missing-client.crt", str(raised.exception))
        self.assertNotIn("test-client-key", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_certificate_directory_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            client_certificate = Path(tmpdir) / "client-certificate-dir"
            client_certificate.mkdir()
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate: client-certificate-dir",
                        "    client-key-data: dGVzdC1jbGllbnQta2V5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-certificate file must be a file",
            str(raised.exception),
        )
        self.assertNotIn("client-certificate-dir", str(raised.exception))
        self.assertNotIn("test-client-key", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_certificate_unreadable_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            client_certificate = Path(tmpdir) / "real-lab-client.crt"
            client_certificate.write_text("test-client-certificate", encoding="utf-8")
            client_certificate.chmod(0o000)
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate: real-lab-client.crt",
                        "    client-key-data: dGVzdC1jbGllbnQta2V5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                client_certificate.chmod(0o600)

        self.assertIn(
            "kubeconfig path current-context user auth material client-certificate file must be readable",
            str(raised.exception),
        )
        self.assertNotIn("real-lab-client.crt", str(raised.exception))
        self.assertNotIn("test-client-key", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_key_missing_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "    client-key: missing-client.key",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-key file must exist",
            str(raised.exception),
        )
        self.assertNotIn("missing-client.key", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_key_directory_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            client_key = Path(tmpdir) / "client-key-dir"
            client_key.mkdir()
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "    client-key: client-key-dir",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material client-key file must be a file",
            str(raised.exception),
        )
        self.assertNotIn("client-key-dir", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_client_key_unreadable_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            client_key = Path(tmpdir) / "real-lab-client.key"
            client_key.write_text("test-client-key", encoding="utf-8")
            client_key.chmod(0o000)
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    client-certificate-data: dGVzdC1jbGllbnQtY2VydGlmaWNhdGU=",
                        "    client-key: real-lab-client.key",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            try:
                with (
                    patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                    patch.object(gate, "load_profile", return_value=profile),
                    patch.object(gate, "validate_contract"),
                    patch.object(gate, "validate_docs"),
                    patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        gate.main()
            finally:
                client_key.chmod(0o600)

        self.assertIn(
            "kubeconfig path current-context user auth material client-key file must be readable",
            str(raised.exception),
        )
        self.assertNotIn("real-lab-client.key", str(raised.exception))
        self.assertNotIn("test-client-key", str(raised.exception))
        self.assertNotIn("test-client-certificate", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "    auth-provider: true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider must be an object",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config: true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config must be an object",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_null_config_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    token: secret",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config must be an object",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_missing_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      config:",
                        "        id-token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider name must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_name_surrounding_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: \" oidc \"",
                        "      config:",
                        "        id-token: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider name must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("oidc", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_value_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        id-token: true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config values must be strings",
            str(raised.exception),
        )
        self.assertNotIn("true", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_value_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        id-token: \"\"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config values must be non-empty strings",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_value_surrounding_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        id-token: \" secret \"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config values must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_key_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        true: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config keys must be strings",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_key_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        \"\": secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config keys must be non-empty strings",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_auth_provider_config_key_surrounding_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        \" id-token \": secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material auth-provider config keys must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_allows_kubeconfig_current_context_user_auth_provider_unknown_nested_auth_like_field_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        id-token: secret",
                        "      metadata:",
                        "        token: 123",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_allows_kubeconfig_current_context_user_auth_provider_unknown_nested_whitespace_before_live(
        self,
    ) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    auth-provider:",
                        "      name: oidc",
                        "      config:",
                        "        id-token: secret",
                        "      metadata:",
                        "        note: ' operator note '",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_rejects_kubeconfig_current_context_user_exec_args_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubectl",
                        "      args:",
                        "      - 123",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec args entries must be strings",
            str(raised.exception),
        )
        self.assertNotIn("123", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_args_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      command: kubelogin",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      interactiveMode: Never",
                        "      args:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec args must be a list",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_empty_arg_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      args:",
                        "      - ''",
                        "      env:",
                        "      - name: TOKEN",
                        "        value: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec args entries must be non-empty strings",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_arg_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      args:",
                        "      - ' get-token '",
                        "      env:",
                        "      - name: TOKEN",
                        "        value: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec args entries must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" get-token ", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_non_list_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubectl",
                        "      env: TOKEN=secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env must be a list",
            str(raised.exception),
        )
        self.assertNotIn("TOKEN=secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      command: kubelogin",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      interactiveMode: Never",
                        "      env:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env must be a list",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubectl",
                        "      env:",
                        "      - TOKEN=secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries must be objects",
            str(raised.exception),
        )
        self.assertNotIn("TOKEN=secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_missing_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubectl",
                        "      env:",
                        "      - value: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries must contain a non-empty string name",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_invalid_name_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      env:",
                        "      - name: TOKEN-NAME",
                        "        value: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries must contain a valid env name",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_name_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      env:",
                        "      - name: ' TOKEN '",
                        "        value: secret",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries name must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" TOKEN ", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_missing_value_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubectl",
                        "      env:",
                        "      - name: TOKEN",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries must contain a string value",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_empty_value_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      env:",
                        "      - name: TOKEN",
                        "        value: ''",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries must contain a non-empty string value",
            str(raised.exception),
        )
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_env_entry_value_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      env:",
                        "      - name: TOKEN",
                        "        value: ' secret '",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec env entries value must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" secret ", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_missing_command_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      args:",
                        "      - token-from-plugin",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec command must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("token-from-plugin", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_command_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: true",
                        "      interactiveMode: Never",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec command must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_non_object_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec: kubelogin-secret-plugin",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec must be an object",
            str(raised.exception),
        )
        self.assertNotIn("kubelogin-secret-plugin", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_command_with_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin --token secret",
                        "      interactiveMode: Never",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec command must not contain whitespace",
            str(raised.exception),
        )
        self.assertNotIn("secret", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_missing_api_version_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      command: kubelogin",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec apiVersion must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_api_version_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: true",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec apiVersion must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_unsupported_api_version_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1alpha1",
                        "      command: kubelogin",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec apiVersion must be a supported client authentication version",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_api_version_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: ' client.authentication.k8s.io/v1 '",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec apiVersion must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" client.authentication.k8s.io/v1 ", str(raised.exception))
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_v1_missing_interactive_mode_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must be set for client.authentication.k8s.io/v1",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_unsupported_interactive_mode_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Sometimes",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must be Never, IfAvailable, or Always",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_interactive_mode_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1beta1",
                        "      command: kubelogin",
                        "      interactiveMode:",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_interactive_mode_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: ''",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_interactive_mode_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: true",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_interactive_mode_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: ' Never '",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec interactiveMode must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" Never ", str(raised.exception))
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_install_hint_non_string_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      installHint: true",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec installHint must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_install_hint_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      installHint:",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec installHint must be a string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_install_hint_empty_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      installHint: ''",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec installHint must be a non-empty string",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_install_hint_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      installHint: ' install kubelogin '",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec installHint must not contain surrounding whitespace",
            str(raised.exception),
        )
        self.assertNotIn(" install kubelogin ", str(raised.exception))
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_provide_cluster_info_non_boolean_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      provideClusterInfo: 'true'",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec provideClusterInfo must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_rejects_kubeconfig_current_context_user_exec_provide_cluster_info_null_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      provideClusterInfo:",
                        "      args:",
                        "      - get-token",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(
            "kubeconfig path current-context user auth material exec provideClusterInfo must be a boolean",
            str(raised.exception),
        )
        self.assertNotIn("get-token", str(raised.exception))
        live.assert_not_called()

    def test_main_allows_kubeconfig_current_context_user_exec_unknown_nested_auth_like_field_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      metadata:",
                        "        token: 123",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_allows_kubeconfig_current_context_user_exec_unknown_nested_whitespace_before_live(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig = Path(tmpdir) / "real-lab.kubeconfig"
            kubeconfig.write_text(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Config",
                        "clusters:",
                        "- name: real-lab",
                        "  cluster:",
                        "    server: https://127.0.0.1:6443",
                        "contexts:",
                        "- name: real-lab",
                        "  context:",
                        "    cluster: real-lab",
                        "    user: real-lab",
                        "current-context: real-lab",
                        "users:",
                        "- name: real-lab",
                        "  user:",
                        "    exec:",
                        "      apiVersion: client.authentication.k8s.io/v1",
                        "      command: kubelogin",
                        "      interactiveMode: Never",
                        "      metadata:",
                        "        note: ' operator note '",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--live", "--kubeconfig", str(kubeconfig)]),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_live", return_value={"status": "passed", "checks": []}) as live,
            ):
                gate.main()

        live.assert_called_once_with(profile, str(kubeconfig))

    def test_main_rejects_component_live_evidence_dir_with_surrounding_whitespace_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "component-gates"
            with (
                patch.object(
                    sys,
                    "argv",
                    ["validate_real_k8s_profile.py", "--component-live", "--component-evidence-dir", f" {evidence_dir} "],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_component_live_gates", return_value={"component_gates": [], "passed": True}) as live_gates,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component evidence dir path must not contain surrounding whitespace", str(raised.exception))
        live_gates.assert_not_called()

    def test_main_rejects_empty_component_live_evidence_dir_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(
                sys,
                "argv",
                ["validate_real_k8s_profile.py", "--component-live", "--component-evidence-dir", ""],
            ),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_component_live_gates", return_value={"component_gates": [], "passed": True}) as live_gates,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component evidence dir path must not be empty", str(raised.exception))
        live_gates.assert_not_called()

    def test_main_rejects_component_report_evidence_dir_with_surrounding_whitespace_before_loading_summary(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "component-gates"
            summary = Path(tmpdir) / "component-summary.json"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-report",
                        str(summary),
                        "--component-evidence-dir",
                        f" {evidence_dir} ",
                    ],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "load_component_summary") as load_summary,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component evidence dir path must not contain surrounding whitespace", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_empty_component_report_evidence_dir_before_loading_summary(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "component-summary.json"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-report",
                        str(summary),
                        "--component-evidence-dir",
                        "",
                    ],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "load_component_summary") as load_summary,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component evidence dir path must not be empty", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_component_preflight_env_file_with_surrounding_whitespace_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text("", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    ["validate_real_k8s_profile.py", "--component-preflight", "--component-env-file", f" {env_file} "],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_component_live_preflight") as preflight,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component env file path must not contain surrounding whitespace", str(raised.exception))
        preflight.assert_not_called()

    def test_main_rejects_empty_component_preflight_env_file_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        fake_evidence = {"component_gates": [], "passed": True, "summary": {"total": 0, "passed": 0, "blocked": 0}}
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--component-preflight", "--component-env-file", ""]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_component_live_preflight", return_value=fake_evidence) as preflight,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component env file path must not be empty", str(raised.exception))
        preflight.assert_not_called()

    def test_main_rejects_component_live_env_file_with_surrounding_whitespace_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text("", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    ["validate_real_k8s_profile.py", "--component-live", "--component-env-file", f" {env_file} "],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "validate_component_live_gates") as live_gates,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component env file path must not contain surrounding whitespace", str(raised.exception))
        live_gates.assert_not_called()

    def test_main_rejects_empty_component_live_env_file_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        fake_evidence = {"component_gates": [], "passed": True, "summary": {"total": 0, "passed": 0, "failed": 0}}
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--component-live", "--component-env-file", ""]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_component_live_gates", return_value=fake_evidence) as live_gates,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component env file path must not be empty", str(raised.exception))
        live_gates.assert_not_called()

    def test_main_rejects_component_report_env_file_with_surrounding_whitespace_before_loading_summary(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text("", encoding="utf-8")
            summary = Path(tmpdir) / "component-summary.json"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-report",
                        str(summary),
                        "--component-env-file",
                        f" {env_file} ",
                    ],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "load_component_summary") as load_summary,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component env file path must not contain surrounding whitespace", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_empty_component_report_env_file_before_loading_summary(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "component-summary.json"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-report",
                        str(summary),
                        "--component-env-file",
                        "",
                    ],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "load_component_summary") as load_summary,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component env file path must not be empty", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_component_report_summary_path_with_surrounding_whitespace_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "component-summary.json"
            summary.write_text("{}", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    ["validate_real_k8s_profile.py", "--component-report", f" {summary} "],
                ),
                patch.object(gate, "load_profile", return_value=profile),
                patch.object(gate, "validate_contract"),
                patch.object(gate, "validate_docs"),
                patch.object(gate, "load_component_summary") as load_summary,
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("component summary path must not contain surrounding whitespace", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_empty_component_report_summary_path_before_loading(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(sys, "argv", ["validate_real_k8s_profile.py", "--component-report", ""]),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "load_component_summary") as load_summary,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component summary path must not be empty", str(raised.exception))
        load_summary.assert_not_called()

    def test_main_rejects_component_preflight_gate_with_surrounding_whitespace_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(
                sys,
                "argv",
                ["validate_real_k8s_profile.py", "--component-preflight", "--component-gate", " secrets-live-gate "],
            ),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_component_live_preflight") as preflight,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component gate id must not contain surrounding whitespace", str(raised.exception))
        preflight.assert_not_called()

    def test_main_rejects_component_live_gate_with_surrounding_whitespace_before_running(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with (
            patch.object(
                sys,
                "argv",
                ["validate_real_k8s_profile.py", "--component-live", "--component-gate", " secrets-live-gate "],
            ),
            patch.object(gate, "load_profile", return_value=profile),
            patch.object(gate, "validate_contract"),
            patch.object(gate, "validate_docs"),
            patch.object(gate, "validate_component_live_gates") as live_gates,
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("component gate id must not contain surrounding whitespace", str(raised.exception))
        live_gates.assert_not_called()

    def test_live_json_check_rejects_non_object_json_without_traceback(self) -> None:
        result = subprocess.CompletedProcess(["kubectl"], 0, "[]", "")

        with patch.object(gate, "kubectl", return_value=result):
            with self.assertRaises(SystemExit) as raised:
                gate.run_json_check("kubectl get nodes -o json", None)

        self.assertIn("returned non-object JSON", str(raised.exception))

    def test_live_stdout_condition_rejects_non_kubectl_command_without_running(self) -> None:
        with patch.object(gate, "kubectl") as kubectl:
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("stdout_yes", "echo yes", None, 3)

        kubectl.assert_not_called()
        self.assertIn("live command must start with kubectl", str(raised.exception))

    def test_live_condition_rejects_unsupported_pass_condition_without_running(self) -> None:
        with patch.object(gate, "run_json_check") as run_json_check:
            with patch.object(gate, "kubectl") as kubectl:
                with self.assertRaises(SystemExit) as raised:
                    gate.condition_passed("contract_gate_exists", "make validate-kms-sm4-live-gate", None, 3)

        run_json_check.assert_not_called()
        kubectl.assert_not_called()
        self.assertIn("unsupported pass_condition contract_gate_exists", str(raised.exception))

    def test_live_condition_rejects_non_string_command_without_traceback(self) -> None:
        with patch.object(gate, "kubectl") as kubectl:
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_one_item", ["kubectl", "get", "pods"], None, 3)  # type: ignore[arg-type]

        kubectl.assert_not_called()
        self.assertIn("live command must be a string", str(raised.exception))

    def test_live_condition_rejects_kubectl_command_without_arguments(self) -> None:
        with patch.object(gate, "kubectl") as kubectl:
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_one_item", "kubectl ", None, 3)

        kubectl.assert_not_called()
        self.assertIn("live command must include kubectl arguments", str(raised.exception))

    def test_live_condition_rejects_non_list_items_without_false_pass(self) -> None:
        with patch.object(gate, "run_json_check", return_value={"items": "not-a-list"}):
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_one_item", "kubectl get pods -o json", None, 3)

        self.assertIn("items must be a list", str(raised.exception))

    def test_live_condition_rejects_non_object_items_without_traceback(self) -> None:
        with patch.object(gate, "run_json_check", return_value={"items": ["not-an-object"]}):
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_minimum_nodes_ready", "kubectl get nodes -o json", None, 3)

        self.assertIn("items entries must be objects", str(raised.exception))

    def test_live_condition_rejects_non_object_node_status_without_traceback(self) -> None:
        with patch.object(gate, "run_json_check", return_value={"items": [{"status": "not-an-object"}]}):
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_minimum_nodes_ready", "kubectl get nodes -o json", None, 3)

        self.assertIn("node status must be an object", str(raised.exception))

    def test_live_condition_rejects_non_list_node_conditions_without_traceback(self) -> None:
        with patch.object(gate, "run_json_check", return_value={"items": [{"status": {"conditions": "not-a-list"}}]}):
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("at_least_minimum_nodes_ready", "kubectl get nodes -o json", None, 3)

        self.assertIn("node conditions must be a list", str(raised.exception))

    def test_live_condition_rejects_non_object_metadata_without_traceback(self) -> None:
        with patch.object(gate, "run_json_check", return_value={"metadata": "not-an-object"}):
            with self.assertRaises(SystemExit) as raised:
                gate.condition_passed("crd_exists", "kubectl get crd vpcs.kubeovn.io -o json", None, 3)

        self.assertIn("metadata must be an object", str(raised.exception))

    def test_component_live_runner_executes_indexed_validators_with_evidence_outputs(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        gate_profiles = {str(gate_entry["id"]): str(gate_entry["profile"]) for gate_entry in profile["contract_gates"]}
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            gate_id = Path(command[-1]).stem
            Path(command[-1]).write_text(
                json.dumps({"passed": True, "id": gate_id, "profile": gate_profiles[gate_id]}) + "\n",
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("REAL-K8S-LAB-A", evidence["profile"])
        self.assertEqual("component_live", evidence["status"])
        component_gates = evidence["component_gates"]
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), len(component_gates))
        gate_ids = {entry["id"] for entry in component_gates}
        self.assertEqual(REQUIRED_CONTRACT_GATE_IDS, gate_ids)
        self.assertTrue(all(entry["passed"] for entry in component_gates))
        self.assertTrue(all(str(entry["evidence_output"]).endswith(".json") for entry in component_gates))
        self.assertTrue(all(isinstance(entry["command"], list) for entry in component_gates))
        self.assertTrue(all(entry["command"][0] == sys.executable for entry in component_gates))
        self.assertTrue(all(entry["command"][-3:] == ["--live", "--evidence-output", entry["evidence_output"]] for entry in component_gates))
        self.assertTrue(all(entry["returncode"] == 0 for entry in component_gates))
        self.assertTrue(all("--live" in command for command in commands))
        self.assertTrue(all("--evidence-output" in command for command in commands))
        self.assertTrue(
            any(command[-3:] == ["--live", "--evidence-output", str(Path(tmpdir) / "secrets-live-gate.json")] for command in commands)
        )

    def test_component_live_runner_collects_all_failures_before_reporting(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        gate_profiles = {str(gate_entry["id"]): str(gate_entry["profile"]) for gate_entry in profile["contract_gates"]}
        commands: list[list[str]] = []
        failed_gate_ids = {"kubeovn-network-live-gate", "secrets-live-gate"}

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            gate_id = Path(command[-1]).stem
            if gate_id in failed_gate_ids:
                return gate.subprocess.CompletedProcess(command, 1, stdout="", stderr=f"{gate_id} unavailable\n")
            Path(command[-1]).write_text(
                json.dumps({"passed": True, "id": gate_id, "profile": gate_profiles[gate_id]}) + "\n",
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), len(commands))
        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual(
            {"total": len(REQUIRED_CONTRACT_GATE_IDS), "passed": len(REQUIRED_CONTRACT_GATE_IDS) - 2, "failed": 2},
            evidence["summary"],
        )
        failed_entries = {entry["id"]: entry for entry in evidence["component_gates"] if not entry["passed"]}
        self.assertEqual(failed_gate_ids, set(failed_entries))
        self.assertEqual(1, failed_entries["kubeovn-network-live-gate"]["returncode"])
        self.assertIn("unavailable", failed_entries["secrets-live-gate"]["error"])

    def test_component_live_runner_redacts_sensitive_failure_output(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            return gate.subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="request failed ANI_BEARER_TOKEN=secret-token Authorization: Bearer live-token\n",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        error = evidence["component_gates"][0]["error"]
        self.assertIn("request failed", error)
        self.assertIn("ANI_BEARER_TOKEN=<redacted>", error)
        self.assertIn("Authorization: Bearer <redacted>", error)
        self.assertNotIn("secret-token", error)
        self.assertNotIn("live-token", error)

    def test_component_live_runner_fails_successful_validator_without_evidence_file(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual(1, len(commands))
        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        gate_result = evidence["component_gates"][0]
        self.assertFalse(gate_result["passed"])
        self.assertEqual(0, gate_result["returncode"])
        self.assertIn("missing evidence output", gate_result["error"])

    def test_component_live_runner_rejects_unusable_evidence_dir(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "component-gates"
            evidence_dir.write_text("not a directory\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as err:
                gate.validate_component_live_gates(
                    profile,
                    evidence_dir,
                    env=self.component_live_env(),
                )

        self.assertIn("component evidence dir unusable", str(err.exception))

    def test_component_live_runner_rejects_unwritable_evidence_dir_before_running(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "component-gates"
            evidence_dir.mkdir()
            evidence_dir.chmod(0o500)
            try:
                with self.assertRaises(SystemExit) as err:
                    gate.validate_component_live_gates(
                        profile,
                        evidence_dir,
                        runner=lambda command: self.fail(f"runner should not be called: {command}"),
                        env=self.component_live_env(),
                    )
            finally:
                evidence_dir.chmod(0o700)

        self.assertIn("component evidence dir must be writable", str(err.exception))

    def test_component_live_runner_rejects_mismatched_evidence_profile(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text('{"status": "passed", "id": "secrets-live-gate", "profile": "OTHER-LAB"}\n', encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        gate_result = evidence["component_gates"][0]
        self.assertFalse(gate_result["passed"])
        self.assertIn("evidence profile mismatch", gate_result["error"])

    def test_component_live_runner_rejects_missing_evidence_profile(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text('{"status": "passed", "id": "secrets-live-gate"}\n', encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        self.assertIn("missing evidence profile", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_non_string_evidence_profile(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": {"name": "M1-SECRETS-LIVE-A"}}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence profile must be a string", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_evidence_profile_with_surrounding_whitespace(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": " M1-SECRETS-LIVE-A "}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence profile must not contain surrounding whitespace", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_evidence_gate_id_with_surrounding_whitespace(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "id": " secrets-live-gate ", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence gate id must not contain surrounding whitespace", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_mismatched_evidence_gate_id(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text('{"status": "passed", "id": "vcluster-live-gate"}\n', encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        gate_result = evidence["component_gates"][0]
        self.assertFalse(gate_result["passed"])
        self.assertIn("evidence gate id mismatch", gate_result["error"])

    def test_component_live_runner_rejects_missing_evidence_gate_id(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text('{"status": "passed", "profile": "M1-SECRETS-LIVE-A"}\n', encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        self.assertIn("missing evidence gate id", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_non_string_evidence_gate_id(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "id": ["secrets-live-gate"], "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence gate id must be a string", evidence["component_gates"][0]["error"])

    def test_component_live_runner_fails_successful_validator_with_invalid_evidence_json(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text("not-json\n", encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        gate_result = evidence["component_gates"][0]
        self.assertFalse(gate_result["passed"])
        self.assertEqual(0, gate_result["returncode"])
        self.assertIn("invalid evidence JSON", gate_result["error"])

    def test_component_live_runner_fails_successful_validator_with_nonpassing_evidence_json(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text('{"status": "failed"}\n', encoding="utf-8")
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1}, evidence["summary"])
        gate_result = evidence["component_gates"][0]
        self.assertFalse(gate_result["passed"])
        self.assertEqual(0, gate_result["returncode"])
        self.assertIn("non-passing evidence status: failed", gate_result["error"])

    def test_component_live_runner_rejects_missing_evidence_outcome(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("missing evidence outcome", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_passed_status_with_false_passed_flag(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "passed": false, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence passed flag must be true when present", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_nonpassed_status_with_true_passed_flag(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "failed", "passed": true, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence status/passed mismatch", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_non_string_evidence_status(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": ["passed"], "passed": true, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence status must be a string", evidence["component_gates"][0]["error"])

    def test_component_live_runner_rejects_empty_evidence_status(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": " ", "passed": true, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence status must not be empty", evidence["component_gates"][0]["error"])

    def test_component_live_runner_reports_nonpassing_evidence_status(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "skipped", "passed": false, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("non-passing evidence status: skipped", evidence["component_gates"][0]["error"])

    def test_component_live_runner_redacts_sensitive_evidence_errors(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "failed token=inline-secret ANI_BEARER_TOKEN=bearer-secret", "passed": false, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        error = evidence["component_gates"][0]["error"]
        self.assertIn("token=<redacted>", error)
        self.assertIn("ANI_BEARER_TOKEN=<redacted>", error)
        self.assertNotIn("inline-secret", error)
        self.assertNotIn("bearer-secret", error)

    def test_component_live_runner_rejects_non_boolean_evidence_passed_flag(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            Path(command[-1]).write_text(
                '{"status": "passed", "passed": "true", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env=self.component_live_env(),
            )

        self.assertEqual("component_live_failed", evidence["status"])
        self.assertIn("evidence passed flag must be a boolean", evidence["component_gates"][0]["error"])

    def test_component_live_runner_preflights_required_env_before_running_validators(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env={"ANI_GATEWAY_URL": "http://127.0.0.1:3000/api/v1"},
            )

        self.assertEqual([], commands)
        self.assertEqual("component_live_preflight_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual(0, evidence["summary"]["passed"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["blocked"])
        blocked = {entry["id"]: entry for entry in evidence["component_gates"]}
        self.assertIn("ANI_BEARER_TOKEN", blocked["vcluster-live-gate"]["missing_env"])
        self.assertIn("KUBECONFIG", blocked["kubevirt-vm-live-gate"]["missing_env"])
        self.assertIn("KMS_PROVIDER_BASE_URL", blocked["kms-sm4-live-gate"]["missing_env"])

    def test_component_live_runner_blocked_preflight_summary_is_reportable(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["vcluster-live-gate", "kms-sm4-live-gate"])
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env={
                    "ANI_GATEWAY_URL": "http://127.0.0.1:3000/api/v1",
                    "ANI_BEARER_TOKEN": "token",
                    "KUBECONFIG": "/tmp/kubeconfig",
                },
            )

        self.assertEqual([], commands)
        self.assertEqual("component_live_preflight_failed", evidence["status"])

        report = self.component_summary_report(
            profile,
            evidence,
            component_env_file="/tmp/ani-real-k8s.env",
            component_evidence_dir="/tmp/component-gates",
        )

        self.assertEqual([], report["failed_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["blocked_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["unresolved_gates"])

    def test_component_summary_report_fails_blocked_preflight_gate_with_mismatched_validator_script(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["kms-sm4-live-gate"])
        contract_gate = profile["contract_gates"][0]
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "kms-sm4-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_preflight_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 0, "blocked": 1},
                "component_gates": [
                    {
                        "id": "kms-sm4-live-gate",
                        "profile": "M1-ENCRYPT-LIVE-A",
                        "validator_script": "scripts/validate_secrets_live_gate.py",
                        "command": self.component_summary_command("kms-sm4-live-gate", evidence_output),
                        "evidence_output": str(evidence_output),
                        "required_env": contract_gate["required_env"],
                        "missing_env": ["KMS_PROVIDER_BASE_URL"],
                        "passed": False,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["kms-sm4-live-gate"], report["failed_gates"])
        self.assertEqual([], report["blocked_gates"])
        self.assertIn("validator_script mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_blocked_preflight_gate_with_command_evidence_output_mismatch(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["kms-sm4-live-gate"])
        contract_gate = profile["contract_gates"][0]
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "kms-sm4-live-gate.json"
            command_evidence_output = component_evidence_dir / "other-kms-sm4-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_preflight_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 0, "blocked": 1},
                "component_gates": [
                    {
                        "id": "kms-sm4-live-gate",
                        "profile": "M1-ENCRYPT-LIVE-A",
                        "validator_script": contract_gate["validator_script"],
                        "command": self.component_summary_command("kms-sm4-live-gate", command_evidence_output),
                        "evidence_output": str(evidence_output),
                        "required_env": contract_gate["required_env"],
                        "missing_env": ["KMS_PROVIDER_BASE_URL"],
                        "passed": False,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["kms-sm4-live-gate"], report["failed_gates"])
        self.assertEqual([], report["blocked_gates"])
        self.assertIn("command must end with --live --evidence-output", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_preflight_failed_gate_with_mismatched_validator_script(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["vcluster-live-gate", "kms-sm4-live-gate"])
        vcluster_gate = next(entry for entry in profile["contract_gates"] if entry["id"] == "vcluster-live-gate")
        kms_gate = next(entry for entry in profile["contract_gates"] if entry["id"] == "kms-sm4-live-gate")
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            vcluster_evidence = component_evidence_dir / "vcluster-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_preflight_failed",
                "passed": False,
                "summary": {"total": 2, "passed": 1, "failed": 0, "blocked": 1},
                "component_gates": [
                    {
                        "id": "vcluster-live-gate",
                        "profile": "M1-K8S-LIVE-A",
                        "validator_script": "scripts/validate_secrets_live_gate.py",
                        "command": self.component_summary_command("vcluster-live-gate", vcluster_evidence),
                        "evidence_output": str(vcluster_evidence),
                        "required_env": vcluster_gate["required_env"],
                        "missing_env": [],
                        "passed": True,
                    },
                    {
                        "id": "kms-sm4-live-gate",
                        "profile": "M1-ENCRYPT-LIVE-A",
                        "required_env": kms_gate["required_env"],
                        "missing_env": ["KMS_PROVIDER_BASE_URL"],
                        "passed": False,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["vcluster-live-gate"], report["failed_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["blocked_gates"])
        details = {entry["id"]: entry for entry in report["gate_details"]}
        self.assertIn("validator_script mismatch", details["vcluster-live-gate"]["error"])

    def test_component_summary_report_fails_passed_preflight_failed_gate_with_command_evidence_output_mismatch(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["vcluster-live-gate", "kms-sm4-live-gate"])
        vcluster_gate = next(entry for entry in profile["contract_gates"] if entry["id"] == "vcluster-live-gate")
        kms_gate = next(entry for entry in profile["contract_gates"] if entry["id"] == "kms-sm4-live-gate")
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            vcluster_evidence = component_evidence_dir / "vcluster-live-gate.json"
            command_evidence = component_evidence_dir / "other-vcluster-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_preflight_failed",
                "passed": False,
                "summary": {"total": 2, "passed": 1, "failed": 0, "blocked": 1},
                "component_gates": [
                    {
                        "id": "vcluster-live-gate",
                        "profile": "M1-K8S-LIVE-A",
                        "validator_script": vcluster_gate["validator_script"],
                        "command": self.component_summary_command("vcluster-live-gate", command_evidence),
                        "evidence_output": str(vcluster_evidence),
                        "required_env": vcluster_gate["required_env"],
                        "missing_env": [],
                        "passed": True,
                    },
                    {
                        "id": "kms-sm4-live-gate",
                        "profile": "M1-ENCRYPT-LIVE-A",
                        "required_env": kms_gate["required_env"],
                        "missing_env": ["KMS_PROVIDER_BASE_URL"],
                        "passed": False,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["vcluster-live-gate"], report["failed_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["blocked_gates"])
        details = {entry["id"]: entry for entry in report["gate_details"]}
        self.assertIn("command must end with --live --evidence-output", details["vcluster-live-gate"]["error"])

    def test_component_live_runner_honors_explicit_empty_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> gate.subprocess.CompletedProcess[str]:
            commands.append(command)
            return gate.subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = gate.validate_component_live_gates(
                profile,
                Path(tmpdir),
                runner=fake_runner,
                env={},
            )

        self.assertEqual([], commands)
        self.assertEqual("component_live_preflight_failed", evidence["status"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["blocked"])
        blocked = {entry["id"]: entry for entry in evidence["component_gates"]}
        self.assertIn("KUBECONFIG", blocked["vcluster-live-gate"]["missing_env"])

    def test_component_env_template_lists_unique_required_env_without_secret_values(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        template = gate.component_env_template(profile)

        self.assertIn("# REAL-K8S-LAB-A component live required environment", template)
        self.assertIn("--component-preflight", template)
        self.assertEqual(1, template.count('export KUBECONFIG=""'))
        self.assertIn('export ANI_GATEWAY_URL=""', template)
        self.assertIn('export KMS_PROVIDER_BEARER_TOKEN=""', template)
        self.assertIn("# vcluster-live-gate: KUBECONFIG, ANI_GATEWAY_URL, ANI_BEARER_TOKEN", template)
        self.assertIn("# kms-sm4-live-gate: ANI_GATEWAY_URL, ANI_BEARER_TOKEN, KMS_PROVIDER_BASE_URL", template)
        self.assertIn("--evidence-output development-records/live/real-k8s-component-preflight.json", template)
        self.assertIn("--component-evidence-dir development-records/live/component-gates", template)
        self.assertNotIn("repo/development-records/live", template)
        self.assertNotIn("ani-token", template)
        self.assertNotIn("kms-token", template)

    def test_main_writes_component_env_template_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "real-k8s-component-live.env"

            with patch(
                "sys.argv",
                [
                    "validate_real_k8s_profile.py",
                    "--component-env-template-output",
                    str(output),
                ],
            ):
                gate.main()

            template = output.read_text(encoding="utf-8")
            self.assertIn('export OBJECTSTORE_LIVE_PUT_URL=""', template)
            self.assertIn("# secrets-live-gate: KUBECONFIG, ANI_GATEWAY_URL, ANI_BEARER_TOKEN", template)

    def test_component_env_template_rejects_unusable_output_path(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            blocker = Path(tmpdir) / "not-a-directory"
            blocker.write_text("blocker", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                gate.write_component_env_template(blocker / "real-k8s-component-live.env", profile)

        self.assertIn("profile output unusable", str(raised.exception))

    def test_component_env_file_loader_parses_export_template_without_shell_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text(
                "\n".join(
                    [
                        "# filled REAL-K8S-LAB-A component env",
                        'export KUBECONFIG="/tmp/lab kubeconfig.yaml"',
                        "ANI_GATEWAY_URL='http://127.0.0.1:3000/api/v1'",
                        'export ANI_BEARER_TOKEN="token value"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            env = gate.load_component_env_file(env_file)

        self.assertEqual("/tmp/lab kubeconfig.yaml", env["KUBECONFIG"])
        self.assertEqual("http://127.0.0.1:3000/api/v1", env["ANI_GATEWAY_URL"])
        self.assertEqual("token value", env["ANI_BEARER_TOKEN"])

    def test_component_env_file_loader_rejects_non_assignment_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text("export KUBECONFIG=/tmp/lab\nsource /tmp/secret.env\n", encoding="utf-8")

            with self.assertRaises(SystemExit):
                gate.load_component_env_file(env_file)

    def test_component_env_file_loader_rejects_unreadable_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(SystemExit) as err:
                gate.load_component_env_file(Path(tmpdir))

        self.assertIn("component env file unreadable", str(err.exception))

    def test_component_env_file_loader_rejects_duplicate_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text(
                "export KUBECONFIG=/tmp/lab-a.yaml\nKUBECONFIG=/tmp/lab-b.yaml\n",
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as err:
                gate.load_component_env_file(env_file)

        self.assertIn("duplicate component env assignment", str(err.exception))

    def test_component_env_file_loader_rejects_value_with_surrounding_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text('export KUBECONFIG=" /tmp/lab.yaml "\n', encoding="utf-8")

            with self.assertRaises(SystemExit) as err:
                gate.load_component_env_file(env_file)

        self.assertIn("env value must not contain surrounding whitespace", str(err.exception))

    def test_component_env_file_loader_rejects_assignment_name_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text('export KUBECONFIG ="/tmp/lab.yaml"\n', encoding="utf-8")

            with self.assertRaises(SystemExit) as err:
                gate.load_component_env_file(env_file)

        self.assertIn("env assignment must not contain whitespace around '='", str(err.exception))

    def test_component_env_file_loader_rejects_assignment_value_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text('export KUBECONFIG= "/tmp/lab.yaml"\n', encoding="utf-8")

            with self.assertRaises(SystemExit) as err:
                gate.load_component_env_file(env_file)

        self.assertIn("env assignment must not contain whitespace around '='", str(err.exception))

    def test_main_component_live_merges_component_env_file_with_process_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text(
                "\n".join(f'export {name}="{name.lower()}-from-file"' for name in gate.component_required_env_names(profile)),
                encoding="utf-8",
            )

            with patch.object(gate, "validate_component_live_gates", return_value={"component_gates": [], "passed": True}) as validate:
                with patch.dict(gate.os.environ, {"ANI_GATEWAY_URL": "http://from-process.example/api/v1"}, clear=True):
                    with patch(
                        "sys.argv",
                        [
                            "validate_real_k8s_profile.py",
                            "--component-live",
                            "--component-env-file",
                            str(env_file),
                            "--component-evidence-dir",
                            str(Path(tmpdir) / "components"),
                        ],
                    ):
                        gate.main()

        merged_env = validate.call_args.kwargs["env"]
        self.assertEqual("ani_gateway_url-from-file", merged_env["ANI_GATEWAY_URL"])
        self.assertEqual("kubeconfig-from-file", merged_env["KUBECONFIG"])

    def test_component_live_preflight_reports_complete_env_without_running_validators(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        evidence = gate.validate_component_live_preflight(profile, self.component_live_env())

        self.assertEqual("component_live_preflight_passed", evidence["status"])
        self.assertTrue(evidence["passed"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["total"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["passed"])
        self.assertEqual(0, evidence["summary"]["blocked"])
        self.assertTrue(all(entry["passed"] for entry in evidence["component_gates"]))
        self.assertTrue(all(entry["missing_env"] == [] for entry in evidence["component_gates"]))

    def test_component_live_preflight_reports_missing_env_without_running_validators(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        evidence = gate.validate_component_live_preflight(profile, {"ANI_GATEWAY_URL": "http://127.0.0.1:3000/api/v1"})

        self.assertEqual("component_live_preflight_failed", evidence["status"])
        self.assertFalse(evidence["passed"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["total"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), evidence["summary"]["blocked"])
        blocked = {entry["id"]: entry for entry in evidence["component_gates"]}
        self.assertIn("KUBECONFIG", blocked["vcluster-live-gate"]["missing_env"])
        self.assertIn("OBJECTSTORE_LIVE_GET_URL", blocked["kms-sm4-live-gate"]["missing_env"])

    def test_component_live_preflight_rejects_env_value_with_surrounding_whitespace(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        env = self.component_live_env()
        env["KUBECONFIG"] = " /tmp/real-lab.kubeconfig "

        with self.assertRaises(SystemExit) as err:
            gate.validate_component_live_preflight(profile, env)

        self.assertIn("component required env KUBECONFIG must not contain surrounding whitespace", str(err.exception))

    def test_component_live_runner_rejects_env_value_with_surrounding_whitespace(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        env = self.component_live_env()
        env["KUBECONFIG"] = " /tmp/real-lab.kubeconfig "
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(SystemExit) as err:
                gate.validate_component_live_gates(
                    profile,
                    Path(tmpdir) / "components",
                    runner=lambda _command: self.fail("validator runner must not be called"),
                    env=env,
                )

        self.assertIn("component required env KUBECONFIG must not contain surrounding whitespace", str(err.exception))

    def test_select_component_contract_gates_filters_requested_gate_ids(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        selected = gate.select_component_contract_gates(profile, ["secrets-live-gate"])

        self.assertEqual(["secrets-live-gate"], [entry["id"] for entry in selected["contract_gates"]])
        self.assertEqual(profile["profile"], selected["profile"])
        self.assertEqual(len(REQUIRED_CONTRACT_GATE_IDS), len(profile["contract_gates"]))

    def test_select_component_contract_gates_rejects_unknown_gate_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        with self.assertRaises(SystemExit):
            gate.select_component_contract_gates(profile, ["missing-live-gate"])

    def test_select_component_contract_gates_rejects_gate_id_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)

        with self.assertRaises(SystemExit) as raised:
            gate.select_component_contract_gates(profile, [" secrets-live-gate "])

        self.assertIn("component gate id must not contain surrounding whitespace", str(raised.exception))

    def test_main_component_preflight_uses_env_file_without_running_live_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": len(REQUIRED_CONTRACT_GATE_IDS), "passed": len(REQUIRED_CONTRACT_GATE_IDS), "blocked": 0},
            "component_gates": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text(
                "\n".join(f'export {name}="{name.lower()}-from-file"' for name in gate.component_required_env_names(profile)),
                encoding="utf-8",
            )
            output = Path(tmpdir) / "component-preflight-summary.json"

            with patch.object(gate, "validate_component_live_preflight", return_value=fake_evidence) as preflight:
                with patch.object(gate, "validate_component_live_gates") as live_gates:
                    with patch(
                        "sys.argv",
                        [
                            "validate_real_k8s_profile.py",
                            "--component-preflight",
                            "--component-env-file",
                            str(env_file),
                            "--evidence-output",
                            str(output),
                        ],
                    ):
                        gate.main()

            live_gates.assert_not_called()
            merged_env = preflight.call_args.args[1]
            self.assertEqual("kubeconfig-from-file", merged_env["KUBECONFIG"])
            self.assertEqual(fake_evidence, json.loads(output.read_text(encoding="utf-8")))

    def test_main_component_preflight_rejects_unknown_env_file_assignment(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": len(REQUIRED_CONTRACT_GATE_IDS), "passed": len(REQUIRED_CONTRACT_GATE_IDS), "blocked": 0},
            "component_gates": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            lines = [f'export {name}="{name.lower()}-from-file"' for name in gate.component_required_env_names(profile)]
            lines.append('export KUBECOFIG="/tmp/typo.yaml"')
            env_file.write_text("\n".join(lines), encoding="utf-8")

            with patch.object(gate, "validate_component_live_preflight", return_value=fake_evidence) as preflight:
                with patch(
                    "sys.argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-preflight",
                        "--component-env-file",
                        str(env_file),
                    ],
                ):
                    with self.assertRaises(SystemExit) as err:
                        gate.main()

        preflight.assert_not_called()
        self.assertIn("unknown component env assignment", str(err.exception))
        self.assertIn("KUBECOFIG", str(err.exception))

    def test_main_component_preflight_filters_selected_gate(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [{"id": "secrets-live-gate", "passed": True}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "real-k8s-component-live.env"
            env_file.write_text(
                "\n".join(f'export {name}="{name.lower()}-from-file"' for name in gate.component_required_env_names(profile)),
                encoding="utf-8",
            )

            with patch.object(gate, "validate_component_live_preflight", return_value=fake_evidence) as preflight:
                with patch(
                    "sys.argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-preflight",
                        "--component-gate",
                        "secrets-live-gate",
                        "--component-env-file",
                        str(env_file),
                    ],
                ):
                    gate.main()

            selected_profile = preflight.call_args.args[0]
            self.assertEqual(["secrets-live-gate"], [entry["id"] for entry in selected_profile["contract_gates"]])

    def test_component_summary_report_classifies_blocked_preflight_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 2, "passed": 1, "blocked": 1},
            "component_gates": [
                {
                    "id": "vcluster-live-gate",
                    "profile": "M1-K8S-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                },
                {
                    "id": "kms-sm4-live-gate",
                    "profile": "M1-ENCRYPT-LIVE-A",
                    "passed": False,
                    "missing_env": ["KMS_PROVIDER_BASE_URL"],
                },
            ],
        }

        report = self.component_summary_report(
            profile,
            evidence,
            component_env_file="/tmp/ani-real-k8s.env",
            component_evidence_dir="/tmp/component-gates",
        )

        self.assertEqual("component_report", report["status"])
        self.assertFalse(report["passed"])
        self.assertEqual(["kms-sm4-live-gate"], report["unresolved_gates"])
        self.assertEqual("component_live_preflight_failed", report["source_status"])
        self.assertEqual([], report["failed_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["blocked_gates"])
        commands = {entry["id"]: entry for entry in report["next_commands"]}
        self.assertIn("--component-env-file /tmp/ani-real-k8s.env", commands["kms-sm4-live-gate"]["preflight"])
        self.assertIn("--component-evidence-dir /tmp/component-gates", commands["kms-sm4-live-gate"]["live"])
        self.assertIn(
            "--evidence-output development-records/live/kms-sm4-live-gate-live-summary.json",
            commands["kms-sm4-live-gate"]["live"],
        )
        self.assertNotIn("repo/development-records/live", commands["kms-sm4-live-gate"]["live"])
        details = {entry["id"]: entry for entry in report["gate_details"]}
        self.assertEqual("blocked", details["kms-sm4-live-gate"]["status"])
        self.assertEqual(["KMS_PROVIDER_BASE_URL"], details["kms-sm4-live-gate"]["missing_env"])

    def test_component_summary_report_accepts_preflight_passed_gate_without_live_evidence_output(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["vcluster-live-gate", "kms-sm4-live-gate"])
        evidence = gate.validate_component_live_preflight(
            profile,
            {
                "ANI_GATEWAY_URL": "http://127.0.0.1:3000/api/v1",
                "ANI_BEARER_TOKEN": "token",
                "KUBECONFIG": "/tmp/kubeconfig",
            },
        )

        report = self.component_summary_report(
            profile,
            evidence,
            component_env_file="/tmp/ani-real-k8s.env",
            component_evidence_dir="/tmp/component-gates",
        )

        self.assertEqual("component_live_preflight_failed", report["source_status"])
        self.assertEqual([], report["failed_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["blocked_gates"])
        self.assertEqual(["kms-sm4-live-gate"], report["unresolved_gates"])
        details = {entry["id"]: entry for entry in report["gate_details"]}
        self.assertEqual("blocked", details["kms-sm4-live-gate"]["status"])
        self.assertNotIn("vcluster-live-gate", details)

    def test_component_summary_report_redacts_sensitive_errors(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "kms-sm4-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "kms-sm4-live-gate",
                        "profile": "M1-ENCRYPT-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "returncode": 1,
                        "error": "kms call failed KMS_PROVIDER_BEARER_TOKEN=kms-secret token=inline-secret",
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("kms-sm4-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        error = report["gate_details"][0]["error"]
        self.assertIn("kms call failed", error)
        self.assertIn("KMS_PROVIDER_BEARER_TOKEN=<redacted>", error)
        self.assertIn("token=<redacted>", error)
        self.assertNotIn("kms-secret", error)
        self.assertNotIn("inline-secret", error)

    def test_component_summary_report_rejects_failed_live_gate_without_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "returncode": 1,
                        "error": "validator failed",
                        "evidence_output": str(evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("missing component summary gate command", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_failed_live_gate_without_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": contract_gate["validator_script"],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "error": "validator failed",
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("failed live gate returncode is required", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_failed_live_gate_without_error_field(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": contract_gate["validator_script"],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 1,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("failed live gate error field is required", report["gate_details"][0].get("error", ""))

    def test_component_summary_report_rejects_failed_live_gate_with_empty_error(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": contract_gate["validator_script"],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 1,
                        "error": "",
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("failed live gate error must be non-empty", report["gate_details"][0].get("error", ""))

    def test_component_summary_report_rejects_failed_live_gate_error_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": False,
                "summary": {"total": 1, "passed": 0, "failed": 1},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": False,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": contract_gate["validator_script"],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 1,
                        "error": " validator failed ",
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("failed live gate error must not contain surrounding whitespace", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_live_gate_without_validator_script_provenance(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(
            entry["required_env"]
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "required_env": required_env,
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("missing component summary gate validator_script", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_live_gate_with_non_string_validator_script_provenance(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": {"path": contract_gate["validator_script"]},
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 0,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("validator_script must be a string", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_live_gate_validator_script_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        contract_gate = next(
            entry
            for entry in profile["contract_gates"]
            if entry["id"] == "secrets-live-gate"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "required_env": contract_gate["required_env"],
                        "validator_script": f" {contract_gate['validator_script']} ",
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 0,
                    },
                ],
            }

            report = gate.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("validator_script must not contain surrounding whitespace", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_unknown_gate_ids_from_stale_summary(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "component_gates": [
                {"id": "stale-live-gate", "passed": False, "missing_env": [], "returncode": 1},
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_rejects_mismatched_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "OTHER-LAB",
            "status": "component_live_failed",
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_rejects_unknown_source_status(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "live",
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_rejects_mismatched_gate_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "OTHER-LAB",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_accepts_declared_contract_gate_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])

    def test_component_summary_report_requires_gate_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate profile is required", str(raised.exception))

    def test_component_summary_report_requires_gate_required_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate required_env is required", str(raised.exception))

    def test_component_summary_report_rejects_non_list_gate_required_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "required_env": "KUBECONFIG",
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate required_env must be a string list", str(raised.exception))

    def test_component_summary_report_rejects_gate_required_env_mismatch(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "required_env": ["KUBECONFIG"],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate required_env mismatch", str(raised.exception))

    def test_component_summary_report_rejects_undeclared_gate_missing_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": ["UNDECLARED_ENV"],
                    "required_env": ["KUBECONFIG"],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary gate secrets-live-gate missing_env contains undeclared required env: UNDECLARED_ENV",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_failed_status_without_unresolved_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live_failed",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            with self.assertRaises(SystemExit) as raised:
                self.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary status component_live_failed requires unresolved gates",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_live_failed_status_with_blocked_gate(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": ["KUBECONFIG"],
                    "required_env": required_env,
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary status component_live_failed cannot include blocked gates",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_failed_status_with_failed_gate(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "required_env": required_env,
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary status component_live_preflight_failed cannot include failed gates",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_blocked_gate_with_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": ["KUBECONFIG"],
                    "required_env": required_env,
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight blocked gate secrets-live-gate must not include returncode",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_blocked_gate_with_error(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": ["KUBECONFIG"],
                    "required_env": required_env,
                    "error": "validator failed",
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight blocked gate secrets-live-gate must not include error",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_passed_gate_with_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "required_env": required_env,
                    "returncode": 0,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight gate secrets-live-gate must not include returncode",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_passed_gate_with_error(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "required_env": required_env,
                    "error": "validator failed",
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight gate secrets-live-gate must not include error",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_passed_gate_with_missing_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": ["ANI_GATEWAY_URL"],
                    "required_env": required_env,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary passed gate secrets-live-gate missing_env must be empty",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_passed_gate_with_command(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "required_env": required_env,
                    "command": self.component_summary_command("secrets-live-gate", "/tmp/secrets-live-gate.json"),
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight gate secrets-live-gate must not include command",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_passed_gate_with_evidence_output(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "required_env": required_env,
                    "evidence_output": "/tmp/secrets-live-gate.json",
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight gate secrets-live-gate must not include evidence_output",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_preflight_passed_gate_with_validator_script(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        required_env = next(entry["required_env"] for entry in profile["contract_gates"] if entry["id"] == "secrets-live-gate")
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "required_env": required_env,
                    "validator_script": "scripts/validate_secrets_live_gate.py",
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            gate.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary preflight gate secrets-live-gate must not include validator_script",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_missing_summary_object(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary summary is required", str(raised.exception))

    def test_component_summary_report_rejects_missing_summary_total_count(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary total count is required", str(raised.exception))

    def test_component_summary_report_rejects_non_integer_summary_total_count(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": True, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary total count must be a non-negative integer", str(raised.exception))

    def test_component_summary_report_rejects_inconsistent_summary_counts(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 2, "passed": 2, "failed": 0},
            "component_gates": [
                {"id": "secrets-live-gate", "passed": False, "missing_env": [], "returncode": 1},
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_rejects_missing_passed_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary passed is required", str(raised.exception))

    def test_component_summary_report_rejects_non_boolean_passed_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": "false",
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary passed must be a boolean", str(raised.exception))

    def test_component_summary_report_rejects_inconsistent_passed_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": True,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary passed mismatch", str(raised.exception))

    def test_component_summary_report_rejects_duplicate_gate_ids(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 2, "passed": 0, "failed": 2},
            "component_gates": [
                {"id": "secrets-live-gate", "passed": False, "missing_env": [], "returncode": 1},
                {"id": "secrets-live-gate", "passed": False, "missing_env": [], "returncode": 1},
            ],
        }

        with self.assertRaises(SystemExit):
            self.component_summary_report(profile, evidence)

    def test_component_summary_report_rejects_non_boolean_gate_passed_flag(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": "true",
                    "missing_env": [],
                    "returncode": 0,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate passed must be a boolean", str(raised.exception))

    def test_component_summary_report_rejects_non_list_gate_missing_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "kms-sm4-live-gate",
                    "profile": "M1-ENCRYPT-LIVE-A",
                    "passed": False,
                    "missing_env": "KMS_PROVIDER_BASE_URL",
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate kms-sm4-live-gate missing_env must be a string list", str(raised.exception))

    def test_component_summary_report_requires_gate_missing_env(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "returncode": 1,
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate missing_env is required", str(raised.exception))

    def test_component_summary_report_rejects_non_integer_gate_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": "1",
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate returncode must be a non-negative integer", str(raised.exception))

    def test_component_summary_report_rejects_non_string_gate_error(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                    "error": {"message": "pod env missing"},
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate error must be a string", str(raised.exception))

    def test_component_summary_report_rejects_non_string_gate_evidence_output(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "blocked": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "evidence_output": {"path": "secrets-live-gate.json"},
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate evidence_output must be a string", str(raised.exception))

    def test_component_summary_report_rejects_non_string_gate_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": {"name": "M1-SECRETS-LIVE-A"},
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate profile must be a string", str(raised.exception))

    def test_component_summary_report_rejects_gate_profile_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": " M1-SECRETS-LIVE-A ",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary gate secrets-live-gate profile must not contain surrounding whitespace",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_non_string_gate_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": {"name": "secrets-live-gate"},
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate id must be a string", str(raised.exception))

    def test_component_summary_report_rejects_gate_id_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": " secrets-live-gate ",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate id must not contain surrounding whitespace", str(raised.exception))

    def test_component_summary_report_rejects_required_env_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "required_env": [
                        " ANI_GATEWAY_URL ",
                        "ANI_BEARER_TOKEN",
                        "ANI_SECRET_TENANT_ID",
                        "ANI_SECRET_NAMESPACE",
                        "ANI_SECRET_POD_NAME",
                        "ANI_SECRET_VM_NAME",
                    ],
                    "missing_env": ["ANI_GATEWAY_URL"],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary gate secrets-live-gate required_env must not contain surrounding whitespace",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_missing_env_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "blocked": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "required_env": [
                        "ANI_GATEWAY_URL",
                        "ANI_BEARER_TOKEN",
                        "ANI_SECRET_TENANT_ID",
                        "ANI_SECRET_NAMESPACE",
                        "ANI_SECRET_POD_NAME",
                        "ANI_SECRET_VM_NAME",
                    ],
                    "missing_env": [" ANI_GATEWAY_URL "],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn(
            "component summary gate secrets-live-gate missing_env must not contain surrounding whitespace",
            str(raised.exception),
        )

    def test_component_summary_report_rejects_non_string_summary_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": {"name": "REAL-K8S-LAB-A"},
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary profile must be a string", str(raised.exception))

    def test_component_summary_report_rejects_summary_profile_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": " REAL-K8S-LAB-A ",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary profile must not contain surrounding whitespace", str(raised.exception))

    def test_component_summary_report_rejects_non_string_summary_status(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": {"name": "component_live_failed"},
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary status must be a string", str(raised.exception))

    def test_component_summary_report_rejects_summary_status_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": " component_live_failed ",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                },
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary status must not contain surrounding whitespace", str(raised.exception))

    def test_component_summary_report_requires_component_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_preflight_passed",
            "passed": True,
            "summary": {"total": 0, "passed": 0, "blocked": 0},
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary component_gates is required", str(raised.exception))

    def test_component_summary_report_rejects_empty_component_gates(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
            "summary": {"total": 0, "passed": 0, "failed": 0},
            "component_gates": [],
        }

        with self.assertRaises(SystemExit) as raised:
            self.component_summary_report(profile, evidence)

        self.assertIn("component summary component_gates must not be empty", str(raised.exception))

    def test_component_summary_report_fails_passed_gate_without_evidence_output_field(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                },
            ],
        }

        report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(["secrets-live-gate"], report["unresolved_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        detail = report["gate_details"][0]
        self.assertEqual("secrets-live-gate", detail["id"])
        self.assertEqual("failed", detail["status"])
        self.assertIn("missing evidence_output", detail["error"])

    def test_component_summary_report_counts_audited_passed_gate_failures(self) -> None:
        profile = gate.select_component_contract_gates(gate.load_profile(gate.PROFILE), ["secrets-live-gate"])
        evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "evidence_output": "",
                },
            ],
        }

        report = self.component_summary_report(profile, evidence)

        self.assertFalse(report["passed"])
        self.assertEqual({"total": 1, "passed": 0, "failed": 1, "blocked": 0}, report["summary"])

    def test_component_summary_report_fails_passed_live_gate_without_command_audit(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(["secrets-live-gate"], report["unresolved_gates"])
        self.assertIn("missing component summary gate command", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_live_gate_with_mismatched_command_evidence_output(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", Path(tmpdir) / "other.json"),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("command must end with --live --evidence-output", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_live_gate_with_whitespace_evidence_output_provenance(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": f" {evidence_output} ",
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                        "returncode": 0,
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("evidence_output must not contain surrounding whitespace", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_live_gate_with_mismatched_command_executable(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            command = self.component_summary_command("secrets-live-gate", evidence_output)
            command[0] = "python-from-other-host"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": command,
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("command shape mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_live_gate_command_part_with_surrounding_whitespace(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            command = self.component_summary_command("secrets-live-gate", evidence_output)
            command[0] = f" {command[0]} "
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": command,
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("command entries must not contain surrounding whitespace", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_live_gate_with_extra_command_argument(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            command = self.component_summary_command("secrets-live-gate", evidence_output)
            command.insert(2, "--forged")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": command,
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("command shape mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_passed_live_gate_with_nonzero_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "returncode": 1,
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("passed live gate returncode must be zero", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_passed_live_gate_without_returncode(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("passed live gate returncode is required", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_passed_live_gate_with_error(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "returncode": 0,
                        "error": "validator failed",
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("passed live gate must not include error", report["gate_details"][0]["error"])

    def test_component_summary_report_rejects_evidence_output_outside_component_dir(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            component_evidence_dir = Path(tmpdir) / "component-gates"
            external_dir = Path(tmpdir) / "external"
            external_dir.mkdir()
            evidence_output = external_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(
                profile,
                evidence,
                component_evidence_dir=str(component_evidence_dir),
            )

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertIn("evidence output path mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_gate_without_summary_gate_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                    },
                ],
            }

            with self.assertRaises(SystemExit) as raised:
                self.component_summary_report(profile, evidence)

        self.assertIn("component summary gate secrets-live-gate profile is required", str(raised.exception))

    def test_component_summary_report_fails_passed_gate_with_missing_evidence_file(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual([], report["blocked_gates"])
        self.assertEqual(["secrets-live-gate"], [entry["id"] for entry in report["next_commands"]])
        self.assertEqual(1, len(report["gate_details"]))
        detail = report["gate_details"][0]
        self.assertEqual("secrets-live-gate", detail["id"])
        self.assertEqual("failed", detail["status"])
        self.assertIn("missing evidence output", detail["error"])

    def test_component_summary_report_fails_passed_gate_with_unreadable_evidence_output(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": tmpdir,
                        "command": self.component_summary_command("secrets-live-gate", tmpdir),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(["secrets-live-gate"], report["unresolved_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        detail = report["gate_details"][0]
        self.assertEqual("secrets-live-gate", detail["id"])
        self.assertEqual("failed", detail["status"])
        self.assertIn("unreadable evidence output", detail["error"])

    def test_component_summary_report_fails_passed_gate_with_invalid_evidence_output(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text("not-json\n", encoding="utf-8")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        self.assertIn("invalid evidence JSON", report["gate_details"][0]["error"])

    def test_component_summary_report_redacts_sensitive_evidence_errors(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "failed token=inline-secret ANI_BEARER_TOKEN=bearer-secret", "passed": false, "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        error = report["gate_details"][0]["error"]
        self.assertIn("token=<redacted>", error)
        self.assertIn("ANI_BEARER_TOKEN=<redacted>", error)
        self.assertNotIn("inline-secret", error)
        self.assertNotIn("bearer-secret", error)

    def test_component_summary_report_fails_passed_gate_with_mismatched_evidence_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text('{"status": "passed", "id": "secrets-live-gate", "profile": "OTHER-LAB"}\n', encoding="utf-8")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        self.assertIn("evidence profile mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_gate_with_missing_evidence_profile(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text('{"status": "passed", "id": "secrets-live-gate"}\n', encoding="utf-8")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        self.assertIn("missing evidence profile", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_gate_with_mismatched_evidence_gate_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text('{"status": "passed", "id": "vcluster-live-gate"}\n', encoding="utf-8")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        self.assertIn("evidence gate id mismatch", report["gate_details"][0]["error"])

    def test_component_summary_report_fails_passed_gate_with_missing_evidence_gate_id(self) -> None:
        profile = gate.load_profile(gate.PROFILE)
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_output = Path(tmpdir) / "secrets-live-gate.json"
            evidence_output.write_text('{"status": "passed", "profile": "M1-SECRETS-LIVE-A"}\n', encoding="utf-8")
            evidence = {
                "profile": "REAL-K8S-LAB-A",
                "status": "component_live",
                "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
                "component_gates": [
                    {
                        "id": "secrets-live-gate",
                        "profile": "M1-SECRETS-LIVE-A",
                        "passed": True,
                        "missing_env": [],
                        "evidence_output": str(evidence_output),
                        "command": self.component_summary_command("secrets-live-gate", evidence_output),
                    },
                ],
            }

            report = self.component_summary_report(profile, evidence)

        self.assertEqual(["secrets-live-gate"], report["failed_gates"])
        self.assertEqual(1, len(report["gate_details"]))
        self.assertIn("missing evidence gate id", report["gate_details"][0]["error"])

    def test_main_component_report_reads_summary_and_writes_report(self) -> None:
        summary = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 2, "passed": 1, "failed": 1},
            "component_gates": [
                {
                    "id": "vcluster-live-gate",
                    "profile": "M1-K8S-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "evidence_output": "",
                },
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": False,
                    "missing_env": [],
                    "returncode": 1,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "component-live-summary.json"
            report_path = Path(tmpdir) / "component-report.json"
            component_evidence_dir = Path(tmpdir) / "components"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "vcluster-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "vcluster-live-gate", "profile": "M1-K8S-LIVE-A"}\n',
                encoding="utf-8",
            )
            summary["component_gates"][0]["evidence_output"] = str(evidence_output)
            summary["component_gates"][0]["command"] = self.component_summary_command("vcluster-live-gate", evidence_output)
            summary["component_gates"][0]["returncode"] = 0
            summary_path.write_text(json.dumps(self.with_component_gate_required_env(gate.load_profile(gate.PROFILE), summary)), encoding="utf-8")
            env_file = Path(tmpdir) / "ani-real-k8s.env"
            env_file.write_text(
                "\n".join(f'export {name}="{name.lower()}-from-file"' for name in gate.component_required_env_names(gate.load_profile(gate.PROFILE))),
                encoding="utf-8",
            )

            with patch(
                "sys.argv",
                [
                    "validate_real_k8s_profile.py",
                    "--component-report",
                    str(summary_path),
                    "--component-env-file",
                    str(env_file),
                    "--component-evidence-dir",
                    str(component_evidence_dir),
                    "--evidence-output",
                    str(report_path),
                ],
            ):
                with self.assertRaises(SystemExit):
                    gate.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("component_report", report["status"])
            self.assertEqual(["secrets-live-gate"], report["failed_gates"])
            self.assertEqual([], report["blocked_gates"])
            self.assertEqual(["secrets-live-gate"], [entry["id"] for entry in report["next_commands"]])

    def test_component_report_rejects_unreadable_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(SystemExit) as err:
                gate.load_component_summary(Path(tmpdir))

        self.assertIn("component summary unreadable", str(err.exception))

    def test_main_component_report_rejects_unreadable_env_file_path(self) -> None:
        summary = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "evidence_output": "",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "component-live-summary.json"
            report_path = Path(tmpdir) / "component-report.json"
            component_evidence_dir = Path(tmpdir) / "components"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            summary["component_gates"][0]["evidence_output"] = str(evidence_output)
            summary["component_gates"][0]["command"] = self.component_summary_command("secrets-live-gate", evidence_output)
            summary["component_gates"][0]["returncode"] = 0
            summary_path.write_text(json.dumps(self.with_component_gate_required_env(gate.load_profile(gate.PROFILE), summary)), encoding="utf-8")

            with patch(
                "sys.argv",
                [
                    "validate_real_k8s_profile.py",
                    "--component-report",
                    str(summary_path),
                    "--component-env-file",
                    tmpdir,
                    "--evidence-output",
                    str(report_path),
                ],
            ):
                with self.assertRaises(SystemExit) as err:
                    gate.main()

        self.assertIn("component env file unreadable", str(err.exception))
        self.assertFalse(report_path.exists())

    def test_main_component_report_exits_zero_when_no_unresolved_gates(self) -> None:
        summary = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
                "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [
                {
                    "id": "secrets-live-gate",
                    "profile": "M1-SECRETS-LIVE-A",
                    "passed": True,
                    "missing_env": [],
                    "evidence_output": "",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "component-live-summary.json"
            report_path = Path(tmpdir) / "component-report.json"
            component_evidence_dir = Path(tmpdir) / "components"
            component_evidence_dir.mkdir()
            evidence_output = component_evidence_dir / "secrets-live-gate.json"
            evidence_output.write_text(
                '{"status": "passed", "id": "secrets-live-gate", "profile": "M1-SECRETS-LIVE-A"}\n',
                encoding="utf-8",
            )
            summary["component_gates"][0]["evidence_output"] = str(evidence_output)
            summary["component_gates"][0]["command"] = self.component_summary_command("secrets-live-gate", evidence_output)
            summary["component_gates"][0]["returncode"] = 0
            summary_path.write_text(json.dumps(self.with_component_gate_required_env(gate.load_profile(gate.PROFILE), summary)), encoding="utf-8")

            with patch(
                "sys.argv",
                [
                    "validate_real_k8s_profile.py",
                    "--component-report",
                    str(summary_path),
                    "--component-evidence-dir",
                    str(component_evidence_dir),
                    "--evidence-output",
                    str(report_path),
                ],
            ):
                gate.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual([], report["unresolved_gates"])
            self.assertEqual([], report["failed_gates"])
            self.assertEqual([], report["blocked_gates"])
            self.assertEqual([], report["next_commands"])

    def test_main_component_report_rejects_stale_summary_gate_ids(self) -> None:
        summary = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 1, "passed": 0, "failed": 1},
            "component_gates": [
                {"id": "stale-live-gate", "passed": False, "missing_env": [], "returncode": 1},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "component-live-summary.json"
            report_path = Path(tmpdir) / "component-report.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            with patch(
                "sys.argv",
                [
                    "validate_real_k8s_profile.py",
                    "--component-report",
                    str(summary_path),
                    "--evidence-output",
                    str(report_path),
                ],
            ):
                with self.assertRaises(SystemExit):
                    gate.main()

            self.assertFalse(report_path.exists())

    def test_main_writes_component_live_summary_when_requested(self) -> None:
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live",
            "passed": True,
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "component_gates": [{"id": "secrets-live-gate", "passed": True}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "component-live-summary.json"

            with patch.object(gate, "validate_component_live_gates", return_value=fake_evidence):
                with patch(
                    "sys.argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-live",
                        "--component-evidence-dir",
                        str(Path(tmpdir) / "components"),
                        "--evidence-output",
                        str(output),
                    ],
                ):
                    gate.main()

            self.assertEqual(fake_evidence, json.loads(output.read_text(encoding="utf-8")))

    def test_main_writes_component_live_failure_summary_before_exiting(self) -> None:
        fake_evidence = {
            "profile": "REAL-K8S-LAB-A",
            "status": "component_live_failed",
            "passed": False,
            "summary": {"total": 2, "passed": 1, "failed": 1},
            "component_gates": [
                {"id": "vcluster-live-gate", "passed": True},
                {"id": "secrets-live-gate", "passed": False, "error": "kubectl unavailable"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "component-live-summary.json"

            with patch.object(gate, "validate_component_live_gates", return_value=fake_evidence):
                with patch(
                    "sys.argv",
                    [
                        "validate_real_k8s_profile.py",
                        "--component-live",
                        "--component-evidence-dir",
                        str(Path(tmpdir) / "components"),
                        "--evidence-output",
                        str(output),
                    ],
                ):
                    with self.assertRaises(SystemExit):
                        gate.main()

            self.assertEqual(fake_evidence, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
