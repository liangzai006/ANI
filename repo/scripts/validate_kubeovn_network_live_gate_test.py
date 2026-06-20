#!/usr/bin/env python3
"""Tests for the Sprint 5 Kube-OVN network live validation gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import validate_kubeovn_network_live_gate as gate


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.applied_manifests: list[str] = []
        self.route_applied = False

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get crd" in joined:
            return '{"metadata":{"name":"vpcs.kubeovn.io"}}'
        if "get vpc" in joined:
            name = command[-3]
            document: dict[str, object] = {
                "kind": "Vpc",
                "metadata": {"name": name},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
            if self.route_applied or name == "vpc-vpc-gateway":
                document["spec"] = {"staticRoutes": [{"cidr": "0.0.0.0/0", "nextHopIP": "10.244.80.1", "policy": "policyDst"}]}
            return json.dumps(document)
        if "get subnet" in joined:
            name = command[-3]
            return json.dumps(
                {
                    "kind": "Subnet",
                    "metadata": {"name": name},
                    "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                }
            )
        if "get networkpolicy" in joined:
            return json.dumps({"kind": "NetworkPolicy", "metadata": {"name": command[3]}})
        if "get service" in joined:
            return json.dumps({"kind": "Service", "metadata": {"name": command[3]}, "spec": {"type": "LoadBalancer"}})
        if "auth can-i" in joined:
            return "yes\n"
        if "delete " in joined:
            return "deleted\n"
        if "apply -f -" in joined:
            if not input_text or "apiVersion" not in input_text:
                raise AssertionError("apply command must receive a manifest")
            self.applied_manifests.append(input_text)
            if "staticRoutes:" in input_text:
                self.route_applied = True
            return "created\n"
        raise AssertionError(f"unexpected command: {joined}")


class FakeHTTPClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str, str, dict[str, object] | None]] = []

    def request(
        self,
        method: str,
        url: str,
        bearer_token: str,
        tenant_id: str,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        self.requests.append((method, url, bearer_token, tenant_id, body))
        if method == "POST" and url.endswith("/networks/vpcs"):
            return 201, {"id": "vpc-gateway", "cidr": body["cidr"] if body else ""}
        if method == "POST" and url.endswith("/networks/subnets"):
            return 201, {"id": "subnet-gateway", "vpc_id": body["vpc_id"] if body else ""}
        if method == "POST" and url.endswith("/networks/routes"):
            return 201, {
                "id": "rt-gateway",
                "vpc_id": body["vpc_id"] if body else "",
                "destination_cidr": body["destination_cidr"] if body else "",
                "next_hop_type": body["next_hop_type"] if body else "",
                "next_hop_id": body["next_hop_id"] if body else "",
            }
        if method == "GET" and "/networks/routes" in url:
            return 200, {"items": [{"id": "rt-gateway"}], "total": 1, "next_cursor": None}
        raise AssertionError(f"unexpected HTTP request: {method} {url}")


class FakeExternalLBRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.service_status_ip = ""

    def run(self, command: list[str], input_text: str | None = None) -> str:
        self.commands.append(command)
        joined = " ".join(command)
        if "get deploy kube-ovn-controller" in joined:
            return json.dumps(
                {
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {"args": ["/kube-ovn/start-controller.sh", "--enable-lb-svc=false"]}
                                ]
                            }
                        }
                    }
                }
            )
        if "patch deploy kube-ovn-controller" in joined:
            return "patched\n"
        if "rollout status deploy/kube-ovn-controller" in joined:
            return "rolled out\n"
        if "apply -f" in joined:
            return "configured\n"
        if "rollout status deploy/ani-kubeovn-external-lb-smoke" in joined:
            return "rolled out\n"
        if "get deploy lb-svc-ani-kubeovn-external-lb-smoke" in joined:
            return '{"kind":"Deployment","metadata":{"name":"lb-svc-ani-kubeovn-external-lb-smoke"}}'
        if "patch deploy lb-svc-ani-kubeovn-external-lb-smoke" in joined:
            return "patched\n"
        if "get svc ani-kubeovn-external-lb-smoke" in joined:
            ingress = [{"ip": self.service_status_ip}] if self.service_status_ip else []
            return json.dumps(
                {
                    "kind": "Service",
                    "metadata": {"name": "ani-kubeovn-external-lb-smoke"},
                    "status": {"loadBalancer": {"ingress": ingress}},
                }
            )
        if "patch svc ani-kubeovn-external-lb-smoke" in joined:
            self.service_status_ip = "10.10.1.250"
            return "patched\n"
        if "delete pod -l app=lb-svc-ani-kubeovn-external-lb-smoke" in joined:
            return "deleted\n"
        if "rollout status deploy/lb-svc-ani-kubeovn-external-lb-smoke" in joined:
            return "rolled out\n"
        if "exec deploy/lb-svc-ani-kubeovn-external-lb-smoke" in joined:
            return "\n".join(
                [
                    "inet 10.10.1.250/22 scope global net1",
                    "10.99.242.146 via 10.16.0.1 dev eth0",
                    "-A PREROUTING -d 10.10.1.250/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination 10.99.242.146:8080",
                    "-A POSTROUTING -d 10.99.242.146/32 -j MASQUERADE",
                ]
            )
        if command[:2] == ["ssh", "ANI1"] or command[:2] == ["ssh", "ANI2"] or command[:2] == ["ssh", "ANI3"]:
            return "ani-kubeovn-external-lb-ok\n"
        raise AssertionError(f"unexpected command: {joined}")


class KubeOVNNetworkLiveGateTest(unittest.TestCase):
    def test_contract_gate_defines_kubeovn_vpc_subnet_route_networkpolicy_and_lb_checks(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)

        gate.validate_contract(document)

        check_ids = {check["id"] for check in document["live_checks"]}
        self.assertIn("kubeovn-crds-ready", check_ids)
        self.assertIn("kubeovn-vpc-created", check_ids)
        self.assertIn("kubeovn-subnet-created", check_ids)
        self.assertIn("kubeovn-route-created", check_ids)
        self.assertIn("networkpolicy-created", check_ids)
        self.assertIn("service-lb-created", check_ids)

    def test_contract_gate_rejects_live_check_command_non_string(self) -> None:
        document = deepcopy(gate.load_gate(gate.DEFAULT_GATE))
        document["live_checks"][0]["command"] = True

        with self.assertRaises(SystemExit) as raised:
            gate.validate_contract(document)

        self.assertIn("live check command must be a non-empty string", str(raised.exception))

    def test_cli_rejects_empty_gate_path_before_loading(self) -> None:
        document = gate.load_gate(gate.DEFAULT_GATE)
        with (
            patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--gate", ""]),
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
            patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--gate", f" {gate.DEFAULT_GATE} "]),
            patch.object(gate, "load_gate", return_value=document) as load_gate,
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn("gate path must not contain surrounding whitespace", str(raised.exception))
        load_gate.assert_not_called()

    def test_cli_reports_missing_gate_path_outside_root_without_traceback(self) -> None:
        missing_gate = Path(tempfile.gettempdir()) / "ani-missing-kubeovn-network-live-gate.yaml"
        with (
            patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--gate", str(missing_gate)]),
            patch.object(gate, "validate_docs"),
        ):
            with self.assertRaises(SystemExit) as raised:
                gate.main()

        self.assertIn(f"missing {missing_gate}", str(raised.exception))

    def test_cli_reports_unreadable_gate_path_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir)
            with (
                patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--gate", str(gate_path)]),
                patch.object(gate, "validate_docs"),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn(f"unreadable {gate_path}", str(raised.exception))

    def test_cli_reports_malformed_gate_yaml_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gate_path = Path(tmpdir) / "malformed-kubeovn-network-live-gate.yaml"
            gate_path.write_text("profile: [\n", encoding="utf-8")
            with (
                patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--gate", str(gate_path)]),
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
                patch("sys.argv", ["validate_kubeovn_network_live_gate.py"]),
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
                patch("sys.argv", ["validate_kubeovn_network_live_gate.py"]),
                patch.object(gate, "load_gate", return_value=document),
                patch.object(gate, "DOC_ROOT", doc_root),
                patch.object(gate, "ROOT", root),
            ):
                with self.assertRaises(SystemExit) as raised:
                    gate.main()

        self.assertIn("malformed doc ANI-DOCS-INDEX.md", str(raised.exception))

    def test_live_gate_applies_and_observes_kubeovn_network_resources(self) -> None:
        runner = FakeRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                vpc_name="ani-live-net",
                subnet_name="ani-live-subnet",
                security_group_name="ani-live-sg",
                load_balancer_name="ani-live-lb",
                namespace="ani-tenant-tenant-a",
            ),
            runner=runner,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["vpc"], "vpc-ani-live-net")
        self.assertEqual(result["subnet"], "subnet-ani-live-subnet")
        self.assertIn(["kubectl", "get", "crd", "vpcs.kubeovn.io", "-o", "json"], runner.commands)
        apply_commands = [command for command in runner.commands if command[-2:] == ["-f", "-"]]
        self.assertEqual(len(apply_commands), 6)
        self.assertTrue(any("staticRoutes:" in manifest for manifest in runner.applied_manifests))

    def test_live_gate_cleanup_deletes_temporary_resources_after_observe(self) -> None:
        runner = FakeRunner()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                vpc_name="ani-live-net",
                subnet_name="ani-live-subnet",
                security_group_name="ani-live-sg",
                load_balancer_name="ani-live-lb",
                namespace="ani-tenant-tenant-a",
            ),
            runner=runner,
            cleanup=True,
        )

        self.assertEqual(result["cleanup"]["status"], "deleted")
        delete_commands = [" ".join(command) for command in runner.commands if "delete" in command]
        self.assertEqual(
            [
                "kubectl -n ani-tenant-tenant-a delete service lb-ani-live-lb --ignore-not-found",
                "kubectl -n ani-tenant-tenant-a delete networkpolicy sg-ani-live-sg --ignore-not-found",
                "kubectl delete subnet subnet-ani-live-subnet --ignore-not-found",
                "kubectl delete vpc vpc-ani-live-net --ignore-not-found",
                "kubectl delete namespace ani-tenant-tenant-a --ignore-not-found",
            ],
            delete_commands,
        )

    def test_production_shaped_live_config_rejects_local_gateway(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            vpc_name="ani-live-net",
            subnet_name="ani-live-subnet",
            security_group_name="ani-live-sg",
            load_balancer_name="ani-live-lb",
            gateway_url="http://127.0.0.1:8080/api/v1",
            ani_bearer_token="dev-token",
            production_shaped=True,
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("production-shaped live mode requires a non-local production gateway URL", str(raised.exception))

    def test_production_shaped_live_config_requires_bearer_token(self) -> None:
        config = gate.LiveConfig(
            tenant_id="tenant-a",
            vpc_name="ani-live-net",
            subnet_name="ani-live-subnet",
            security_group_name="ani-live-sg",
            load_balancer_name="ani-live-lb",
            gateway_url="https://ani-gateway.example.test/api/v1",
            production_shaped=True,
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("production-shaped live mode requires --ani-bearer-token", str(raised.exception))

    def test_production_shaped_live_gate_writes_s01_proof_items(self) -> None:
        runner = FakeRunner()
        http_client = FakeHTTPClient()
        result = gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                vpc_name="ani-live-net",
                subnet_name="ani-live-subnet",
                security_group_name="ani-live-sg",
                load_balancer_name="ani-live-lb",
                namespace="ani-tenant-tenant-a",
                gateway_url="https://ani-gateway.example.test/api/v1",
                ani_bearer_token="dev-token",
                production_shaped=True,
            ),
            runner=runner,
            cleanup=True,
            http_client=http_client,
        )

        self.assertEqual(result["production_shape"]["status"], "passed")
        self.assertEqual(result["gateway_route_create_status"], 201)
        self.assertEqual(result["gateway_route_list_status"], 200)
        self.assertEqual(result["gateway_route_id"], "rt-gateway")
        self.assertEqual(result["vpc"], "vpc-vpc-gateway")
        self.assertEqual(result["subnet"], "subnet-subnet-gateway")
        self.assertEqual(result["cleanup"]["resources"][2], "subnet/subnet-subnet-gateway")
        self.assertEqual(result["cleanup"]["resources"][3], "vpc/vpc-vpc-gateway")
        self.assertEqual([request[0] for request in http_client.requests], ["POST", "POST", "POST", "GET"])
        self.assertTrue(http_client.requests[-1][1].endswith("/networks/routes?vpc_id=vpc-gateway"))
        self.assertTrue(all(request[2] == "dev-token" for request in http_client.requests))
        self.assertEqual(result["production_shape"]["missing_items"], [])
        self.assertEqual(result["production_shape"]["transport_profile"], "production_gateway_in_cluster_serviceaccount")
        self.assertEqual(
            {
                "production_gateway",
                "in_cluster_serviceaccount_rbac",
                "persistent_route_metadata_reconciliation",
            },
            set(result["production_shape"]["proof_items"]),
        )

    def test_external_lb_live_gate_patches_helper_and_proves_curl_results(self) -> None:
        runner = FakeExternalLBRunner()

        result = gate.run_external_lb_live(
            gate.ExternalLBConfig(
                kubeconfig="/tmp/kubeconfig",
                deps_manifest=str(gate.DEFAULT_EXTERNAL_LB_DEPS),
                script_configmap_manifest=str(gate.DEFAULT_EXTERNAL_LB_SCRIPT_CONFIGMAP),
                curl_hosts=("ANI1", "ANI2", "ANI3"),
                reconcile_stamp="test-stamp",
            ),
            runner=runner,
        )

        self.assertEqual("passed", result["status"])
        self.assertEqual("10.10.1.250", result["external_ip"])
        self.assertTrue(result["dnat_rule_observed"])
        self.assertEqual(
            [{"host": "ANI1", "body_matched": True}, {"host": "ANI2", "body_matched": True}, {"host": "ANI3", "body_matched": True}],
            result["curl_results"],
        )
        joined_commands = [" ".join(command) for command in runner.commands]
        self.assertTrue(any("patch deploy kube-ovn-controller" in command for command in joined_commands))
        self.assertTrue(any("patch deploy lb-svc-ani-kubeovn-external-lb-smoke" in command for command in joined_commands))

    def test_external_lb_config_requires_curl_hosts(self) -> None:
        with patch.object(gate.shutil, "which", return_value="/usr/bin/tool"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_external_lb_config(
                    gate.ExternalLBConfig(
                        deps_manifest=str(gate.DEFAULT_EXTERNAL_LB_DEPS),
                        script_configmap_manifest=str(gate.DEFAULT_EXTERNAL_LB_SCRIPT_CONFIGMAP),
                    )
                )

        self.assertIn("external LB live mode requires at least one curl host", str(raised.exception))

    def test_live_gate_creates_tenant_namespace_before_namespaced_resources(self) -> None:
        runner = FakeRunner()

        gate.run_live(
            gate.LiveConfig(
                tenant_id="tenant-a",
                vpc_name="ani-live-net",
                subnet_name="ani-live-subnet",
                security_group_name="ani-live-sg",
                load_balancer_name="ani-live-lb",
                namespace="ani-tenant-tenant-a",
            ),
            runner=runner,
        )

        self.assertIn("kind: Namespace", runner.applied_manifests[0])
        self.assertIn("name: ani-tenant-tenant-a", runner.applied_manifests[0])

    def test_cli_live_mode_rejects_missing_tenant_config(self) -> None:
        with patch.object(gate, "run_live") as run_live:
            with patch("sys.argv", ["validate_kubeovn_network_live_gate.py", "--live", "--tenant-id", ""]):
                with self.assertRaises(SystemExit):
                    gate.main()
        run_live.assert_not_called()

    def test_live_config_rejects_required_field_surrounding_whitespace(self) -> None:
        config = gate.LiveConfig(
            tenant_id=" tenant-a ",
            vpc_name="ani-live-net",
            subnet_name="ani-live-subnet",
            security_group_name="ani-live-sg",
            load_balancer_name="ani-live-lb",
        )

        with patch.object(gate.shutil, "which", return_value="/usr/bin/kubectl"):
            with self.assertRaises(SystemExit) as raised:
                gate.validate_live_config(config)

        self.assertIn("tenant_id must not contain surrounding whitespace", str(raised.exception))

    def test_cli_live_mode_rejects_evidence_output_surrounding_whitespace_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "kubeovn-network-live-evidence.json"

            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live") as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubeovn_network_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
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
                            "validate_kubeovn_network_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--namespace",
                            "ani-tenant-tenant-a",
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
                                "validate_kubeovn_network_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
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
            output = parent / "kubeovn-network-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubeovn_network_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
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
            output = blocker / "child" / "kubeovn-network-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                    with patch.object(gate, "write_live_evidence") as write_live_evidence:
                        with patch(
                            "sys.argv",
                            [
                                "validate_kubeovn_network_live_gate.py",
                                "--live",
                                "--tenant-id",
                                "tenant-a",
                                "--namespace",
                                "ani-tenant-tenant-a",
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
            output = Path(tmpdir) / "kubeovn-network-live-evidence.json"
            output.write_text("existing evidence", encoding="utf-8")
            output.chmod(0o400)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_kubeovn_network_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--namespace",
                                    "ani-tenant-tenant-a",
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
            output = parent / "kubeovn-network-live-evidence.json"
            parent.chmod(0o500)
            try:
                with patch.object(gate, "validate_live_config"):
                    with patch.object(gate, "run_live", return_value={"status": "passed"}) as run_live:
                        with patch.object(gate, "write_live_evidence") as write_live_evidence:
                            with patch(
                                "sys.argv",
                                [
                                    "validate_kubeovn_network_live_gate.py",
                                    "--live",
                                    "--tenant-id",
                                    "tenant-a",
                                    "--namespace",
                                    "ani-tenant-tenant-a",
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
            "namespace": "ani-tenant-tenant-a",
            "vpc": "vpc-ani-live-net",
            "subnet": "subnet-ani-live-subnet",
            "security_group": "sg-ani-live-sg",
            "load_balancer": "lb-ani-live-lb",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "kubeovn-network-live-evidence.json"
            with patch.object(gate, "validate_live_config"):
                with patch.object(gate, "run_live", return_value=fake_evidence):
                    with patch(
                        "sys.argv",
                        [
                            "validate_kubeovn_network_live_gate.py",
                            "--live",
                            "--tenant-id",
                            "tenant-a",
                            "--namespace",
                            "ani-tenant-tenant-a",
                            "--vpc-name",
                            "ani-live-net",
                            "--subnet-name",
                            "ani-live-subnet",
                            "--security-group-name",
                            "ani-live-sg",
                            "--load-balancer-name",
                            "ani-live-lb",
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
            self.assertEqual("kubeovn-network-live-gate", written["id"])
            self.assertEqual("M1-NETWORK-LIVE-A", written["profile"])
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
