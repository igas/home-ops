# Node upgrades: Talos and kubelet

Layer 1 bumps change `talos/talenv.yaml` and a tuppr resource under `kubernetes/apps/system-upgrade/tuppr/upgrades/`. Merging starts a rolling upgrade of every node. These extra checks sit on top of the ten steps in [SKILL.md](SKILL.md).

## Extra checks

1. **Support matrix.** Query the Sidero docs (`siderolabs-docs` MCP) for the Talos version's supported Kubernetes versions. A kubelet bump must be supported by the Talos version the nodes run **now**, since tuppr upgrades Kubernetes on the current Talos. A Talos bump must support the Kubernetes version running now.
2. **Deprecations against this cluster's config.** Read the Talos release notes (all intermediate versions) for machine config changes, removed features, and kernel or extension changes, and check each against `talos/talconfig.yaml` and `talos/patches/`. Read the Kubernetes release notes for removed APIs and check them against `kubernetes/` with `kubectl get --raw` or `pluto` if available. Anything this cluster uses is a finding.
3. **Fleet health.** All nodes `Ready`, all on the version the repo currently declares, etcd healthy (`talosctl etcd status`), no Kustomization or HelmRelease not `Ready`. A cluster mid-drift is `hold`.
4. **Extensions and images.** For a Talos bump, the schematic in `talos/talconfig.yaml` still lists extensions that exist for the new version (check the factory or release notes).
5. **Storage.** Rook-Ceph tolerates one node down at a time. Confirm the Ceph cluster is `HEALTH_OK` before the verdict.

## Verdict rule

Best possible verdict is `safe with prep`. The **Prep** line names how to watch: `kubectl get nodes -w` and the tuppr resource status, and which order tuppr will take the nodes in.
