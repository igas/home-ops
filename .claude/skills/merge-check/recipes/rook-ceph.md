# rook-ceph

Two charts in one Renovate group: `rook-ceph` (operator) and `rook-ceph-cluster` (CephCluster, pools, StorageClasses, toolbox). Since #732 a third chart, `ceph-csi-drivers`, carries the CSI drivers; it versions on its own line (1.0.x) and sits **outside** that group, so it bumps alone and can drift from the operator. Check both when either moves.

## Read the rendered diff, not the version line

A chart minor can carry a Ceph **major**: the v1.20 chart defaulted to v20.2.4 Tentacle while this cluster still ran Squid, and the pin is the only reason that did not ride in on #732. `kubernetes/apps/rook-ceph/rook-ceph/cluster/helmrelease.yaml` pins `cephImage` since #720, so the CephCluster no longer inherits the chart default, but keep grepping the flux-local diff for `quay.io/ceph/ceph:`: a changed tag is a separate upgrade that needs its own PR.

## 1.19 → 1.20: CSI leaves the operator chart

Done on 2026-09-13 in #732 (v1.19.11 → v1.20.7). Full writeup, including the ServiceAccount rename table and the helm-adoption trap on the CephFS `Driver` CR, in `docs/runbooks/rook-ceph-1.20-csi-split.md`. The short version:

1. The drivers live in the `ceph-csi-drivers` chart. Upstream publishes it only to a GitHub Pages index (`https://ceph.github.io/ceph-csi-operator`); pull it from `ghcr.io/home-operations/charts-mirror/ceph-csi-drivers` instead, the mirror this repo already uses for eight other charts, so it keeps the usual `OCIRepository` shape. The ceph-csi-operator controller still ships inside `rook-ceph`.
2. Kustomization order: `ceph-csi-drivers` depends on `rook-ceph`; `rook-ceph-cluster` depends on both.
3. `csi.cephFSKernelMountOptions` moves to `cephClusterSpec.csi.cephfs.kernelMountOptions`. The operator chart's old `csi.*` keys are silently ignored (no `values.schema.json`).
4. Values start from Rook's own recommended file (`deploy/charts/ceph-csi-drivers/values.yaml` at the tag), which the chart is documented as requiring. It is not sufficient on an upgrade: rendered as-is it gives RBD `snapshotPolicy: none`, and the operator only runs a `csi-snapshotter` when the policy is not `none` — that silently kills RBD VolumeSnapshots and VolSync. Snapshot first (`kubectl -n rook-ceph get drivers.csi.ceph.io,operatorconfigs.csi.ceph.io -o yaml`), then diff the rendered `Driver` specs against it.
5. Every CSI ServiceAccount and its RBAC is renamed (`ceph-csi-rbd-nodeplugin-sa` → `rook-ceph-rbd-csi-ceph-com-nodeplugin-sa`), because ceph-csi-operator v1.0.4 drops the `CSI_SERVICE_ACCOUNT_PREFIX`. Reading the diff as "these get deleted" is the trap; check each deletion has a renamed equivalent instead.

Check what actually runs before trusting the values. Under v1.19 this cluster set `enableCephfsDriver: false` and ran the CephFS driver pods anyway; the live `Driver` CRs then set neither `grpcTimeout` nor `snapshotPolicy`, so the effective values had to be read off the running sidecar args.

## CVE-2025-30156 (CephX)

Ceph ≥ v19.2.6 / v20.2.4 plus `spec.security.cephx.daemon.keyRotationPolicy: KeyGeneration`, `keyGeneration: 2`. Verify with `kubectl -n rook-ceph get cephcluster rook-ceph -o jsonpath='{.status.cephx}'`. CSI keys must stay `security.cephx.csi.keyType: aes` because aes256k kernel mounts need Linux 7.0+ and Talos ships 6.18; mute the four `AUTH_INSECURE_*` warnings via `healthCheck.muteHealthWarning` as onedr0p does in [#11552](https://github.com/onedr0p/home-ops/pull/11552).

## HelmRelease timeout and the rollback trap (2026-09-13, #720/#722)

A `cephImage` change rolls every mon, mgr and OSD and the cluster chart's health check keeps the CephCluster `Progressing` for the whole run (about 25 minutes on this cluster). The `rook-ceph-cluster` HelmRelease needs a `spec.timeout` in that range (30m through the 19.2.6 patch bump, raised to 45m in #733 for the Squid -> Tentacle major, which converts on-disk state as it rolls); with Flux's default 5m the upgrade "fails" and Flux rolls back, which reverts the CephCluster image and any `security.cephx` change mid-upgrade.

Once rolled back, Rook sees mixed versions and takes the "more than one ceph version running, triggering upgrade" path, which has **no downgrade guard**: it will move already-upgraded daemons back to the older spec image. The only thing holding it off is the HEALTH_ERR pre-check, and after a Ceph 19.2.6+ bump that HEALTH_ERR is the CVE's own `AUTH_INSECURE_SERVICE_*` errors. So:

1. Never mute those errors while the CephCluster spec is at the old image. Mute only after confirming `spec.cephVersion.image` is the new one and Flux cannot roll it back (`flux suspend hr rook-ceph-cluster -n rook-ceph`, or a HelmRelease timeout long enough).
2. If a rollback already happened: suspend the HelmRelease, `kubectl patch` the CephCluster back to the Git-declared image and cephx block, let Rook finish to `Ready`, then `flux resume`. The v1.19.11 upgrade then passes its health check quickly because the CephCluster already matches.
3. The errors clear by themselves once daemon keys reach generation 2; no mute is needed at all if the rollout is not interrupted.

The v1.19 toolbox does not reload its keyring after the admin key rotates (`RADOS permission denied`). `kubectl -n rook-ceph rollout restart deploy/rook-ceph-tools`. The v1.20 toolbox script watches the keyring.

Verification that this cluster reached: `status.cephx` generation 2 for admin/mon/mgr/osd/crashCollector/cephExporter with mgr and osd `keyType: aes256k`; csi and rbdMirrorPeer stay at generation 1 `aes`. Expect exactly four remaining warnings: `AUTH_INSECURE_CLIENT_KEY_TYPE`, `AUTH_INSECURE_KEYS_ALLOWED`, `AUTH_INSECURE_KEYS_CREATABLE`, `AUTH_INSECURE_ROTATING_SERVICE_KEY_TYPE` (the last clears after 2-3 hours).

## 19.2.6 -> 20.2.4: Squid to Tentacle

Done in #733. The cluster HelmRelease pins `cephImage`, so the major is one tag change; the chart derives `cephVersion.image` and the toolbox image from it. Preconditions worth reading before the merge, because Rook will not stop you: every daemon already on the same Squid build (`ceph versions`), `require_osd_release squid` in `ceph osd dump`, `HEALTH_OK`, all PGs `active+clean`. `security.cephx.daemon.keyGeneration` stays at 2 — bumping it in the same PR would rotate keys mid-major.

The rollout itself is quick: about 6 minutes for all 8 daemons (mons, then mgrs, then OSDs), against the ~25 minutes the 19.2.6 bump took. That 25 minutes was the cephx rotation, not the image. Rook bumps `require_osd_release` to `tentacle` by itself once the last OSD is up.

`status.cephx` keeps `keyCephVersion: 19.2.6-0` at generation 2 after the major, and that is correct, not a stalled upgrade: Rook only re-stamps `keyCephVersion` when it actually mints a new key, and generation 2 is already the desired generation, so nothing rotates. Expecting the field to follow the Ceph version is the trap (#733's acceptance criteria assumed it would). Read `keyGeneration` and `keyType` for the CVE posture; `keyCephVersion` records which build minted the key that is still in use.

## Health gate

Before any verdict: `kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status` is `HEALTH_OK`, all OSDs up/in, PGs `active+clean`. Rook v1.20.7 supports Kubernetes v1.31–v1.36 (`Documentation/Getting-Started/Prerequisites/prerequisites.md` at the tag; no chart declares a `kubeVersion`). The cluster sits on v1.36, the top edge: re-read that file before letting a kubelet bump past it.
