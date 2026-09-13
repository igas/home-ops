# Node upgrades: Talos and kubelet

Layer 1 bumps change `talos/talenv.yaml` and a tuppr resource under `kubernetes/apps/system-upgrade/tuppr/upgrades/`. Merging starts a rolling upgrade of every node. These extra checks sit on top of the ten steps in [SKILL.md](SKILL.md).

## Extra checks

0. **Read the render check.** The `Talos Config` workflow renders the machine config with throwaway secrets on every PR that touches `talos/`; its `Talos Config Render` job log carries talhelper's error when the declared versions reject the patches. When the check did not run, or you need the rendered output, follow the local fallback in [recipes/talos.md](recipes/talos.md).
1. **Support matrix.** Query the Sidero docs (`siderolabs-docs` MCP) for the Talos version's supported Kubernetes versions. A kubelet bump must be supported by the Talos version the nodes run **now**, since tuppr upgrades Kubernetes on the current Talos. A Talos bump must support the Kubernetes version running now.
2. **Deprecations against this cluster's config.** Read the Talos release notes (all intermediate versions) for machine config changes, removed features, and kernel or extension changes, and check each against `talos/talconfig.yaml` and `talos/patches/`. Read the Kubernetes release notes for removed APIs and check them against `kubernetes/` with `kubectl get --raw` or `pluto` if available. Anything this cluster uses is a finding.
3. **Fleet health.** All nodes `Ready`, all on the version the repo currently declares, etcd healthy (`talosctl etcd status`), no Kustomization or HelmRelease not `Ready`. A cluster mid-drift is `hold`.
4. **Extensions and images.** For a Talos bump, the schematic in `talos/talconfig.yaml` still lists extensions that exist for the new version (check the factory or release notes).
5. **Storage.** Rook-Ceph tolerates one node down at a time. Confirm the Ceph cluster is `HEALTH_OK` before the verdict.

## Verdict rule

Best possible verdict is `safe with prep`. The **Prep** line names how to watch: `kubectl get nodes -w` and the tuppr resource status, and which order tuppr will take the nodes in.

## Gotcha: kubelet bumps are gated by the *running* Talos

The support matrix is enforced at runtime, **server-side**. tuppr vendors newer machinery than the nodes run, but the check that matters is the one on the node: a Kubernetes minor the *running* Talos does not list fails with `unsupported upgrade path 1.36->1.37` ([home-operations/tuppr#544](https://github.com/home-operations/tuppr/issues/544), closed with exactly that finding). So read the node versions, never `talenv.yaml`, when deciding whether a kubelet bump can land.

Caught 2026-09-13 on PR #656, both halves in one day: at 03:11 the nodes ran Talos 1.13.10, which tops out at Kubernetes 1.36, so the kubelet 1.37 PR was `hold` pending a Talos 1.14 bump. By 22:00 #725 had merged and tuppr's TalosUpgrade had rolled all four nodes to 1.14.0, and the same PR at the same head SHA became `safe with prep` with nothing about the PR itself changed. When a kubelet PR is blocked this way, the unblocking event is the *rollout*, not the merge — re-review after `kubectl get nodes -o wide` shows the new Talos on every node.

When the kubelet PR exists but the Talos one does not, check the Renovate dashboard: since #723 Talos comes from `custom.talos-factory` as `siderolabs/talos`, not the retired `ghcr.io/siderolabs/installer` image.
