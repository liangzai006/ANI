#!/usr/bin/env python3
"""Tests for ANI SSH trust installer config rendering."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

import ani_ssh_trust_installer as installer


class AniSSHTrustInstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = [
            installer.Node(
                name="ANI1",
                tailscale_ip="100.64.128.1",
                management_ip="10.10.1.66",
                user="kubercloud",
            ),
            installer.Node(
                name="ANI2",
                tailscale_ip="100.64.128.2",
                management_ip="10.10.1.67",
                user="kubercloud",
            ),
        ]

    def test_remote_config_matches_name_aliases_and_ips(self) -> None:
        config = installer.render_ssh_config(
            self.nodes,
            identity_files=["~/.ssh/id_ed25519_ani_cluster"],
            include_identities_only=True,
        )

        self.assertIn("Host ANI1 ani1", config)
        self.assertIn("Host 100.64.128.1", config)
        self.assertIn("Host 10.10.1.66", config)
        self.assertIn("HostName 100.64.128.1", config)
        self.assertIn("HostName 10.10.1.66", config)
        self.assertIn("User kubercloud", config)
        self.assertIn("IdentityFile ~/.ssh/id_ed25519_ani_cluster", config)
        self.assertIn("IdentitiesOnly yes", config)

    def test_hosts_block_contains_name_aliases(self) -> None:
        hosts = installer.render_hosts_block(self.nodes)

        self.assertIn("# ANI managed hosts begin", hosts)
        self.assertIn("100.64.128.1 ANI1 ani1", hosts)
        self.assertIn("100.64.128.2 ANI2 ani2", hosts)
        self.assertIn("# ANI managed hosts end", hosts)

    def test_authorized_keys_deduplicates_input_keys(self) -> None:
        existing = "ssh-ed25519 AAAA-one old\n"
        keys = ["ssh-ed25519 AAAA-two mac", "ssh-ed25519 AAAA-two mac"]

        rendered = installer.render_authorized_keys(existing, keys)

        self.assertEqual(rendered.count("ssh-ed25519 AAAA-two mac"), 1)
        self.assertIn("ssh-ed25519 AAAA-one old", rendered)

    def test_uppercase_help_alias_prints_help(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            installer.build_parser().parse_args(["-H"])

        self.assertEqual(raised.exception.code, 0)

    def test_parse_path_list_accepts_comma_separated_paths(self) -> None:
        paths = installer.parse_path_list("~/.ssh/id_rsa.pub, /tmp/admin.pub")

        self.assertEqual(paths, [pathlib.Path("~/.ssh/id_rsa.pub"), pathlib.Path("/tmp/admin.pub")])

    def test_nodes_with_user_overrides_default_user(self) -> None:
        updated = installer.nodes_with_user(self.nodes, "ubuntu")

        self.assertEqual([node.user for node in updated], ["ubuntu", "ubuntu"])
        self.assertEqual(updated[0].name, "ANI1")

    def test_interactive_mode_writes_rendered_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            nodes_path = root / "nodes.json"
            pubkey_path = root / "admin.pub"
            output_dir = root / "out"
            nodes_path.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "name": "ANI1",
                                "tailscale_ip": "100.64.128.1",
                                "management_ip": "10.10.1.66",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pubkey_path.write_text("ssh-ed25519 AAAA-admin admin\n", encoding="utf-8")
            answers = iter(
                [
                    str(nodes_path),
                    "ubuntu",
                    str(pubkey_path),
                    "~/.ssh/id_ed25519_ani_cluster",
                    "",
                    str(output_dir),
                ]
            )

            exit_code = installer.run_interactive(input_func=lambda _prompt: next(answers), output_func=lambda _msg: None)

            self.assertEqual(exit_code, 0)
            self.assertIn("User ubuntu", (output_dir / "ani-ssh-config").read_text(encoding="utf-8"))
            self.assertIn("100.64.128.1 ANI1 ani1", (output_dir / "ani-hosts").read_text(encoding="utf-8"))
            self.assertIn("ssh-ed25519 AAAA-admin admin", (output_dir / "ani-authorized-keys").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
