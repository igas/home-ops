# talos

Layer 1. Extra steps live in [UPGRADES.md](../UPGRADES.md); this file holds what those steps found on real reviews. Caught 2026-09-13 on PR #725 (v1.13.10 → v1.14.0).

## Preflight: the render check, with a local fallback

The `Talos Config` workflow (`.github/workflows/talos.yaml`) runs on every PR that touches `talos/`. It installs the talhelper pinned in `.mise.toml`, generates a throwaway secret bundle, and runs `scripts/talos-render-check.sh`, so a Renovate bump whose contract rejects the patches goes red with talhelper's message in the `Talos Config Render` log and step summary. Read that log before the verdict. The check is green on 1.14 since #731 migrated the controller patches, so any red is a finding.

Local fallback, when the check did not run or the rendered files are needed (no AGE key, no cluster access):

```sh
task talos:render-check TALOS_VERSION=vX.Y.Z                     # bump under review
scripts/talos-render-check.sh --talos-version vX.Y.Z --out-dir "$S/rendered"   # same, keeping the output
```

Render the old version too so a failure is attributable to the bump. The script copies `talos/` to a temp dir, strips `clusterconfig/` and `talsecret.sops.yaml`, overrides `talenv.yaml`, and runs `talhelper genconfig --offline-mode`.

## 1.14: v1alpha1 `cluster.*` patches stop merging (migrated in #731)

For the 1.14 contract talhelper emits the multi-document Kubernetes config (`KubeAPIServerConfig`, `KubeProxyConfig`, ...) and rejects the matching v1alpha1 fields with `kube-apiserver config is already set in v1alpha1 config (.cluster.apiServer)`. `talos/patches/controller/kubernetes.yaml` now carries the document kinds; `cluster.yaml` keeps what has to stay v1alpha1. `KubeClusterConfig` is deliberately absent: siderolabs/talos#14338 panics machined on any cluster with a service-account key.

What talhelper 3.1.17 gets wrong for 1.14 (it vendors Talos machinery `v1.14.0-alpha.2`; check `go.mod` on the talhelper tag before trusting a bump):

- `KubeCoreDNSConfig`, `KubeNodeConfig`, `KubeTalosAPIAccessConfig` are `not registered`, so `cluster.coreDNS`, `cluster.allowSchedulingOnControlPlanes` and `machine.features.kubernetesTalosAPIAccess` stay v1alpha1 until talhelper ships >= 1.14.0 machinery.
- `KubeEtcdEncryptionConfig` renders with key name `key1` and no `identity` provider. The running kube-apiserver (legacy path and the 1.14.0 generator, see `pkg/machinery/config/generate/kubernetes.go`) uses `key2` plus `identity`; a renamed key makes every existing Secret unreadable. `kubernetes.yaml` deletes the generated document and `kube-etcd-encryption.yaml` re-adds the live shape with `${secretboxEncryptionSecret}` from `talos/talenv.sops.yaml`. Compare against the node before any apply: `talosctl -n <ip> read /system/secrets/kubernetes/kube-apiserver/encryptionconfig.yaml`.
- `additionalApiServerCertSans` is dropped from `KubeAPIServerConfig`; the patch repeats them as `certExtraSANs`.

Both pins become redundant once talhelper vendors >= 1.14.0 machinery. Talos list fields append on merge and one patch file may touch a document once, hence the delete in one file and the re-add in the next.

Verify a render against a live node with a per-document diff, not the raw `apply-config --dry-run` output: installed configs written under an older contract also gain `DiscoveryServiceConfig`, `ResolverConfig.hostDNS`, `KubeNetworkConfig`, `KubeAudit/Authentication/AuthorizerConfig` and `FilesystemTrimConfig`, all pure moves. Watch `cluster.controlPlane.endpoint`: kube-apiserver derives `--service-account-issuer` and `--api-audiences` from it, so a changed endpoint invalidates in-cluster tokens until rotation. `talconfig.yaml` pins the live value for that reason.

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

`machine.sysctls`, `machine.files` (CRI `20-customization.part`), `machine.features.hostDNS`, `machine.kubelet.nodeIP` and `extraConfig`, `cluster.etcd` (no document kind yet), and the three blocked on talhelper's machinery: `machine.features.kubernetesTalosAPIAccess` (tuppr's grant; still honoured, home-operations/tuppr#455), `cluster.allowSchedulingOnControlPlanes`, `cluster.coreDNS`. Re-check each against the next minor's "removed" list.
