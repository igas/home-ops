# talos

Layer 1. Extra steps live in [UPGRADES.md](../UPGRADES.md); this file holds what those steps found on real reviews. Caught 2026-09-13 on PR #725 (v1.13.10 → v1.14.0).

## Preflight: render the config locally before the verdict

CI does not render Talos config on Renovate PRs (only flux-local runs; the e2e workflow did not). Render in the scratchpad with the new version so `task talos:generate-config` is known to work after merge:

```sh
cp -R talos "$S/talos" && rm -rf "$S/talos/clusterconfig"
sed -i '' 's/^talosVersion: .*/talosVersion: vX.Y.Z/' "$S/talos/talenv.yaml"
(cd "$S/talos" && talhelper genconfig -c talconfig.yaml -o ./clusterconfig -s talsecret.sops.yaml)
```

Needs the AGE key for `talsecret.sops.yaml`; no cluster access. Render the old version too so a failure is attributable to the bump.

## 1.14: v1alpha1 `cluster.*` patches stop merging

For the 1.14 contract talhelper emits the multi-document Kubernetes config (`KubeAPIServerConfig`, `KubeProxyConfig`, ...). This repo's `talos/patches/controller/cluster.yaml` then fails with `patch delete: path 'cluster.apiServer.admissionControl' ... lookup failed`, and once that line is dropped with `kube-apiserver config is already set in v1alpha1 config (.cluster.apiServer)` plus the same for `.cluster.controllerManager`, `.cluster.scheduler`, and `.cluster.proxy` vs `KubeProxyConfig`.

The nodes are unaffected: tuppr upgrades in place and the installed v1alpha1 config stays supported. What breaks is regeneration, so `talos:apply-node` is unavailable until the patches are migrated. Migrate **after** every node is on 1.14 (1.13 rejects the new kinds), using onedr0p's `talos/controlplane.yaml.j2` as the shape. Skip `KubeClusterConfig`: siderolabs/talos#14338 panics machined on any cluster with a service-account key.

## 1.14.0: Secure Boot nodes boot with `lockdown=none`

Release notes say `integrity` applies implicitly after `confidentiality` was dropped; siderolabs/talos#14237 shows it does not. Fix siderolabs/talos#14241 merged to main 2026-09-04, first release carrying it is after 1.14.0. Nodes with `machineSpec.secureboot: true` are affected (the three masters here). Options: accept until the fixed patch release, or add `lockdown=integrity` as an extra kernel arg in a new schematic (changes the schematic ID, so `talconfig.yaml` and the node's installed schematic both move).

## tuppr health gate depends on Ceph

`talosupgrade.yaml` requires `CephCluster status.ceph.health == HEALTH_OK`. After a cephx rotation the four `AUTH_INSECURE_*` warnings keep the cluster at `HEALTH_WARN` and the plan sits `Pending`. Check `ceph health detail` before the verdict and point at the mute in [rook-ceph.md](rook-ceph.md) when that is the only thing red.

## Schematic and extension check

Installed extensions: `talosctl -n <ip> get extensions -o yaml` (includes the `schematic` pseudo-extension; compare its version to `talosImageURL` in `talconfig.yaml`, they drifted apart on paper before). Factory availability:

```sh
curl -s https://factory.talos.dev/version/vX.Y.Z/extensions/official | jq -r '.[].name'
curl -s -o /dev/null -w '%{http_code}\n' https://factory.talos.dev/image/<schematic>/vX.Y.Z/installer-amd64.tar   # 302 = exists
```

## etcd port move in 1.14

etcd HTTP endpoints (`/metrics`, `/health`) move from 2379 to 2383, unless `--listen-metrics-urls` is set. This cluster sets it to `0.0.0.0:2381` in `patches/controller/cluster.yaml` and kube-prometheus-stack scrapes the chart default 2381, so nothing moves.

## Deprecated-but-supported fields this cluster still uses (as of 1.14)

`machine.sysctls`, `machine.files` (CRI `20-customization.part`), `machine.features.hostDNS`, `machine.features.kubernetesTalosAPIAccess` (tuppr's grant; still honoured, home-operations/tuppr#455), `machine.kubelet.nodeIP` and `extraConfig`, `cluster.allowSchedulingOnControlPlanes`. Re-check each against the next minor's "removed" list.
