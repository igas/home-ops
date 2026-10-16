# talos

Layer 1. Extra steps live in [UPGRADES.md](../UPGRADES.md); this file holds what those steps found on real reviews. Caught 2026-09-13 on PR #725 (v1.13.10 → v1.14.0).

## Preflight: the render check, with a local fallback

The `Talos Config` workflow (`.github/workflows/talos.yaml`) runs on every PR that touches `talos/`. It installs the talhelper pinned in `.mise.toml`, generates a throwaway secret bundle, and runs `scripts/talos-render-check.sh`, so a Renovate bump whose contract rejects the patches goes red with talhelper's message in the `Talos Config Render` log and step summary. Read that log before the verdict. The check is green on 1.14 since #731 migrated the controller patches, so any red is a finding.

Local fallback, when the check did not run or the rendered files are needed (no AGE key, no cluster access):

```sh
task talos:render-check TALOS_VERSION=vX.Y.Z                     # bump under review
scripts/talos-render-check.sh --talos-version vX.Y.Z --out-dir "$S/rendered"   # same, keeping the output
```

The script copies `talos/` to a temp dir, strips `clusterconfig/` and `talsecret.sops.yaml`, overrides `talenv.yaml`, and runs `talhelper genconfig --offline-mode`. Render the old version too so a failure is attributable to the bump. For a kubelet bump, render at the new **Kubernetes** version against the Talos version in main (`--kubernetes-version vX.Y.Z`); a clean pass whose only non-secret diff is the kubelet and the four `registry.k8s.io/kube-*` image tags is the whole preflight, so no throwaway Pod is needed.

A long-lived Renovate branch can predate the workflow itself: #656 was opened 2026-08-22 and last built 2026-09-07, so `Talos Config` (added by #734) never ran on it and its `statusCheckRollup` simply has no such entry. An *absent* check is not a passing one — run the fallback locally and put a rebase in **Prep**.

## Preflight: validate with the *new* talosctl, rendered and live

talhelper validates with its own vendored machinery, not the target release. A Talos patch can still tighten node-side validation: 1.14.1 `7a2c4e8` added cross-document checks, and 1.14.2 `c792fa4` added hostname/search-domain checks. The node validates its **installed** config on boot, so check both the render and each node's live config with the target `talosctl` (download from the release and verify against `sha256sum.txt`):

```sh
for f in "$S"/rendered/kubernetes-*.yaml; do talosctl-NEW validate --mode metal -c "$f"; done
for ip in 192.168.6.1 192.168.6.2 192.168.6.3 192.168.6.12; do
  T=$(mktemp "$S/live.XXXXXX"); talosctl -n $ip get machineconfig v1alpha1 -o jsonpath='{.spec}' > "$T"
  talosctl-NEW validate --mode metal -c "$T"; rm -f "$T"   # holds secrets: never print it, delete at once
done
```

Leave out `--strict`: it turns the known `.machine.files` deprecation warning (#747) into an error. Baseline as of 1.14.2 is valid with that one warning.

Renovate's body for `siderolabs/talos` can quote the wrong notes. On #753 it showed v1.14.0-beta.1 text under `v1.14.2`. Read `gh api repos/siderolabs/talos/releases/tags/vX.Y.Z --jq .body` instead.

## Talos and kubelet PRs together

tuppr runs one upgrade at a time cluster-wide: a `TalosUpgrade` and the `KubernetesUpgrade` never run concurrently ([coordination docs](https://tuppr.home-operations.com/coordination/)). Merging both is safe, but merge Talos first and let it finish, so a failure is attributable. Both edit `talos/talenv.yaml` on lines with an unchanged line between them, so they merge cleanly in either order. Check with a squash-merge simulation in a throwaway `git worktree`, not `git merge-tree` of one branch onto the other.

## 1.14: v1alpha1 `cluster.*` patches stop merging (migrated in #731)

For the 1.14 contract talhelper emits the multi-document Kubernetes config (`KubeAPIServerConfig`, `KubeProxyConfig`, ...) and rejects the matching v1alpha1 fields with `kube-apiserver config is already set in v1alpha1 config (.cluster.apiServer)`. `talos/patches/controller/kubernetes.yaml` now carries the document kinds; `cluster.yaml` keeps what has to stay v1alpha1. `KubeClusterConfig` is deliberately absent: siderolabs/talos#14338 panics machined on any cluster with a service-account key.

What talhelper 3.1.17 gets wrong for 1.14 (it vendors Talos machinery `v1.14.0-alpha.2`; check `go.mod` on the talhelper tag before trusting a bump):

- `KubeCoreDNSConfig`, `KubeNodeConfig`, `KubeTalosAPIAccessConfig`, `KubeServiceAccountConfig` are `not registered`, so `cluster.coreDNS`, `cluster.allowSchedulingOnControlPlanes` and `machine.features.kubernetesTalosAPIAccess` stay v1alpha1, and the service account issuer stays pinned in `KubeAPIServerConfig.extraArgs` until talhelper ships >= 1.14.0 machinery. Re-check by putting the kind in a controller patch and rendering: the failure is `error decoding document v1alpha1/<Kind>/ (line 1): "<Kind>" "v1alpha1": not registered`. Still all four on 2026-09-13; v3.1.17 is the newest release and talhelper `master` is also on `v1.14.0-alpha.2`, with budimanjojo/talhelper#1708 open at rc.2.
- `KubeEtcdEncryptionConfig` renders with key name `key1` and no `identity` provider. The live nodes run `key2` plus `identity`, written by the legacy path: under the 1.13 contract the config carries only `secretboxEncryptionSecret` and Talos builds the file itself. A renamed key makes every existing Secret unreadable. `kubernetes.yaml` deletes the generated document and `kube-etcd-encryption.yaml` re-adds the live shape with `${secretboxEncryptionSecret}` from `talos/talenv.sops.yaml`. Compare against the node before any apply: `talosctl -n <ip> read /system/secrets/kubernetes/kube-apiserver/encryptionconfig.yaml`.
- `additionalApiServerCertSans` is dropped from `KubeAPIServerConfig`; the patch repeats them as `certExtraSANs`.

Only the SAN pin goes away cleanly on a machinery bump. Checked 2026-09-13 against real 1.14.0 (`talosctl gen config`, the same `config/generate` package talhelper calls): `--additional-sans` does reach `KubeAPIServerConfig.certExtraSANs`, but the generated `KubeEtcdEncryptionConfig` is `key2` with no `identity` provider, so the bump fixes the key name and not the missing fallback. The 1.14 reference page for the kind still shows `identity: {}` in its example, so the field is supported — narrow the pin to re-add `identity` rather than deleting the file, and diff the rendered document against the node before dropping anything. Talos list fields append on merge and one patch file may touch a document once, hence the delete in one file and the re-add in the next.

Two kube-apiserver changes come with the `KubeAPIServerConfig` document type itself and cannot be patched away (seen on the #731 apply, `talosctl get apiserverconfig`): `--anonymous-auth=false` becomes `--authentication-config=...` with anonymous access allowed only on `/healthz`, `/livez` and `/readyz` (upstream and fresh-1.14 default; `/version` still 401), and the static pods gain startup probes plus a read-only `/etc/ssl/certs` mount. Accepted, no ticket.

Verify a render against a live node with a per-document diff, not the raw `apply-config --dry-run` output: installed configs written under an older contract also gain `DiscoveryServiceConfig`, `ResolverConfig.hostDNS`, `KubeNetworkConfig`, `KubeAudit/Authentication/AuthorizerConfig` and `FilesystemTrimConfig`, all pure moves. Watch `cluster.controlPlane.endpoint`: kube-apiserver derives `--service-account-issuer` and `--api-audiences` from it, so a changed endpoint would invalidate in-cluster tokens until rotation. Since #736 both flags are pinned in `KubeAPIServerConfig.extraArgs` (neither is on the merge denylist, and extraArgs overwrite the derived value), which is what let the endpoint move to `https://k8s.igas.dev:6443`; the pins are still the pre-move value. Treat a rendered change to either flag as a finding, and read [docs/runbooks/talos-control-plane-endpoint.md](../../../../docs/runbooks/talos-control-plane-endpoint.md) before touching them.

## 1.14.0: Secure Boot nodes boot with `lockdown=none`

Release notes say `integrity` applies implicitly after `confidentiality` was dropped; siderolabs/talos#14237 shows it does not. Fix siderolabs/talos#14241 merged to main 2026-09-04. The first release carrying it is **1.14.1**, as siderolabs/pkgs `fd0c2b2` "add a kernel patch for EFI SecureBoot integrity lockdown" (tracked here as #729). Verify after rollout with `talosctl -n <masters> read /sys/kernel/security/lockdown`; the worker isn't Secure Boot and stays `[none]`. Nodes with `machineSpec.secureboot: true` are affected (the three masters here). Options: accept until the fixed patch release, or add `lockdown=integrity` as an extra kernel arg in a new schematic (changes the schematic ID, so `talconfig.yaml` and the node's installed schematic both move).

Since 2026-10-16 Secure Boot is off in k8s-master-01's firmware (not in `talconfig.yaml`), so master-01 reads `[none]` by design. Only master-02 and master-03 should show `[integrity]`.

## Renovate rebases past the reviewed version

#753 was reviewed at v1.14.2 and merged at v1.14.3: Renovate rebased it after the verdict, and the patch had no GitHub release yet (only a tag and factory images). Before merging a node-layer PR, compare `headRefOid` with the SHA in the verdict. If it moved, re-review. For a tag with no release, read `gh api repos/siderolabs/talos/compare/vOLD...vNEW` for the commit list. The factory builds new-version installer images on demand, so tuppr's first pre-pull can time out with "no pull progress after 1m30s". It retries and succeeds once the build finishes.

## A node that never comes back: suspect the NIC first

On 2026-10-15 master-01 shut down cleanly for v1.14.3 and then had no network presence for 72 minutes (no ping, no ARP, no Talos API). The console showed `e1000e ... eno1: Detected Hardware Unit Hang` on every boot attempt: the kernel booted, but the NIC wedged. systemd-boot's boot counter (`Talos-vX~1.efi`) falls back to the previous UKI at the next power cycle, but only until Talos logs `removing fallback entry` on a successful boot. Check the NIC drivers before blaming the boot chain: `talosctl -n <ip> get links -o json | jq -r 'select(.spec.type=="ether" and (.spec.busPath//"")!="") | "\(.metadata.id)=\(.spec.driver)"'`. master-01 is the only `e1000e` node (master-02 and master-03 use `r8169`, worker-02 uses `igc`). Its TSO is off via an `EthernetConfig` in `patches/nodes/master-01.yaml` (#848). A kernel bump that touches `e1000e` is worth a finding. If the hang returns, disable `tx-generic-segmentation` and `rx-gro` next.

`task talos:apply-node` applies the last *generated* `clusterconfig/`, not the patches. Run `task talos:generate-config` first, dry-run, apply, then check the live resource (for example `talosctl get ethernetstatus eno1`).

## tuppr health gate depends on Ceph

`talosupgrade.yaml` requires `CephCluster status.ceph.health == HEALTH_OK`. Each node reboot takes that node's OSD down for about 5 minutes, so expect a pause between nodes. A `Failed` TalosUpgrade is terminal; resume it with `kubectl annotate talosupgrade talos tuppr.home-operations.com/reset="$(date)"`, which skips nodes already at the target version. After a cephx rotation the four `AUTH_INSECURE_*` warnings keep the cluster at `HEALTH_WARN` and the plan sits `Pending`. Check `ceph health detail` before the verdict and point at the mute in [rook-ceph.md](rook-ceph.md) when that is the only thing red.

## Schematic and extension check

Installed extensions: `talosctl -n <ip> get extensions -o yaml` (includes the `schematic` pseudo-extension; compare its version to `talosImageURL` in `talconfig.yaml`, they drifted apart on paper before). Factory availability:

```sh
curl -s https://factory.talos.dev/version/vX.Y.Z/extensions/official | jq -r '.[].name'
curl -s -o /dev/null -w '%{http_code}\n' https://factory.talos.dev/image/<schematic>/vX.Y.Z/installer-amd64.tar   # 302 = exists
```

The masters use `installer-secureboot`. The tarball endpoint returns 400 for `installer-secureboot-amd64.tar` at *every* version, including the one running, so check the OCI manifest instead. It can take a minute or more while the factory builds, so give it `--max-time 100`:

```sh
curl -s -o /dev/null --max-time 100 -w '%{http_code}\n' \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json' \
  https://factory.talos.dev/v2/installer-secureboot/<schematic>/manifests/vX.Y.Z   # 200 = exists
```

## etcd port move in 1.14

etcd HTTP endpoints (`/metrics`, `/health`) move from 2379 to 2383, unless `--listen-metrics-urls` is set. This cluster sets it to `0.0.0.0:2381` in `patches/controller/cluster.yaml` and kube-prometheus-stack scrapes the chart default 2381, so nothing moves.

## Deprecated-but-supported fields this cluster still uses (as of 1.14)

`machine.sysctls`, `machine.files` (CRI `20-customization.part`), `machine.features.hostDNS`, `machine.kubelet.nodeIP` and `extraConfig`, `cluster.etcd` (no document kind yet), and the three blocked on talhelper's machinery: `machine.features.kubernetesTalosAPIAccess` (tuppr's grant; still honoured, home-operations/tuppr#455), `cluster.allowSchedulingOnControlPlanes`, `cluster.coreDNS`. Re-check each against the next minor's "removed" list.
