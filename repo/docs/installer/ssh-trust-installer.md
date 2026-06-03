# ANI SSH Trust Installer Helper

`repo/scripts/ani_ssh_trust_installer.py` renders deterministic SSH bootstrap assets for ANI node initialization. It can be used as a standalone operations helper today, and can later be called by the full ANI installer during OS bootstrap, host naming, and SSH trust setup.

## Scope

The helper does not open SSH sessions and does not store passwords. It only renders text artifacts that an installer, cloud-init step, Ansible playbook, or operator can copy into place.

It currently supports:

- SSH Host entries for node names, lowercase aliases, Tailscale IPs, and management IPs.
- `/etc/hosts` blocks for ANI node name resolution.
- `authorized_keys` rendering with duplicate public keys removed.
- An interactive mode for operators who prefer prompted input.

It intentionally does not yet perform:

- Remote command execution.
- Hostname mutation.
- SSH key generation.
- Password login hardening.
- System service changes.

Those actions belong to the higher-level installer flow that consumes these rendered assets.

## Input Nodes JSON

```json
{
  "nodes": [
    {
      "name": "ANI1",
      "tailscale_ip": "100.64.128.1",
      "management_ip": "10.10.1.66",
      "user": "kubercloud"
    }
  ]
}
```

Fields:

| Field | Required | Meaning |
|---|---:|---|
| `name` | yes | Canonical ANI hostname, for example `ANI1`. |
| `tailscale_ip` | yes | Tailscale address used for remote access when outside the management LAN. |
| `management_ip` | yes | Physical or private LAN management address. |
| `user` | no | SSH user. Defaults to `kubercloud`. |

## CLI Help

Both `-h` and `-H` print usage:

```bash
python repo/scripts/ani_ssh_trust_installer.py -h
python repo/scripts/ani_ssh_trust_installer.py -H
```

## Interactive Mode

Use interactive mode when an operator wants to be prompted for the required inputs:

```bash
python repo/scripts/ani_ssh_trust_installer.py interactive
```

Prompts:

| Prompt | Meaning |
|---|---|
| `Nodes JSON path` | Path to the node inventory JSON. |
| `SSH user` | User to write into rendered SSH config, defaults to `kubercloud`. |
| `Public key path(s)` | One or more public key files, separated by comma or spaces. |
| `Identity file(s)` | Private key paths to reference in generated SSH config. |
| `Existing authorized_keys path` | Optional existing file to merge before appending public keys. |
| `Output directory` | Directory where rendered files will be written. |

Interactive mode writes:

| File | Purpose |
|---|---|
| `ani-ssh-config` | SSH Host entries for node names, lowercase aliases, Tailscale IPs, and management IPs. |
| `ani-hosts` | Bounded `/etc/hosts` block. |
| `ani-authorized-keys` | Merged authorized keys. |

## Render SSH Config

For server-to-server trust, render entries that use the per-node cluster key:

```bash
python repo/scripts/ani_ssh_trust_installer.py render-ssh-config \
  --nodes-json nodes.json \
  --identity-file '~/.ssh/id_ed25519_ani_cluster' \
  --identities-only
```

For an operations client, render entries that use local admin keys:

```bash
python repo/scripts/ani_ssh_trust_installer.py render-ssh-config \
  --nodes-json nodes.json \
  --identity-file '~/.ssh/id_rsa' \
  --identity-file '~/.ssh/id_ed25519_github' \
  --identities-only
```

The output includes all of these access forms for each node:

```text
ANI1
ani1
100.64.128.1
10.10.1.66
```

## Render Hosts Block

```bash
python repo/scripts/ani_ssh_trust_installer.py render-hosts \
  --nodes-json nodes.json
```

The output is bounded by markers:

```text
# ANI managed hosts begin
100.64.128.1 ANI1 ani1
# ANI managed hosts end
```

An installer can replace the block between the markers in `/etc/hosts`.

## Render Authorized Keys

```bash
python repo/scripts/ani_ssh_trust_installer.py render-authorized-keys \
  --existing authorized_keys \
  --public-key admin.pub \
  --public-key node.pub
```

The output preserves existing keys and appends new keys once.

## Integration Notes

A future ANI installer can use this helper in a staged bootstrap flow:

1. Discover or receive node inventory.
2. Set hostnames on each node.
3. Generate or import cluster SSH keys.
4. Render `/etc/hosts`, `~/.ssh/config`, and `authorized_keys`.
5. Copy rendered assets to nodes.
6. Verify that node names, Tailscale IPs, and management IPs all work with `ssh -o BatchMode=yes`.

The current helper is deliberately small so it can be reused by shell, Python, Go, cloud-init, or a later installer controller without carrying SSH transport assumptions.
