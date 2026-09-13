# rook-ceph

Two charts in one Renovate group: `rook-ceph` (operator) and `rook-ceph-cluster` (CephCluster, pools, StorageClasses, toolbox). Caught 2026-09-13 on PR #561 (v1.19.5 → v1.20.7).

## Read the rendered diff, not the version line

`kubernetes/apps/rook-ceph/rook-ceph/cluster/helmrelease.yaml` does **not** pin `cephImage`, so the CephCluster inherits the chart's default Ceph image. A chart minor can carry a Ceph **major** (v1.20 chart defaults to v20.2.4 Tentacle while the cluster ran 19.2.3 Squid). Always grep the flux-local diff for `quay.io/ceph/ceph:` and treat a changed tag as a separate upgrade that needs its own PR, pinned via `cephImage.tag`.

## 1.19 → 1.20: CSI leaves the operator chart

Rook v1.20 removes CSI driver management from `rook-ceph`; the drivers are owned by the `ceph-csi-drivers` chart (ceph-csi-operator). The rendered diff for a naive bump **deletes** the `ceph-csi-*-sa` ServiceAccounts and ClusterRoles that the live rbd/cephfs ctrlplugin and nodeplugin pods run under. Merging that alone breaks CSI. Required shape (onedr0p [#11548](https://github.com/onedr0p/home-ops/pull/11548)):

1. New HelmRelease `ceph-csi-drivers` with Rook-compatible values (driver names `rook-ceph.rbd.csi.ceph.com` / `rook-ceph.cephfs.csi.ceph.com`, imageSet `rook-csi-operator-image-set-configmap`, `grpcTimeout: 150`, controller `replicas: 2`, log rotation off to match the live Driver CRs).
2. Kustomization order: `ceph-csi-drivers` depends on `rook-ceph`; `rook-ceph-cluster` depends on both.
3. `csi.cephFSKernelMountOptions` moves to `cephClusterSpec.csi.cephfs.kernelMountOptions`. The operator chart's `csi.*` keys are silently ignored (no `values.schema.json`).
4. Snapshot first: `kubectl -n rook-ceph get drivers.csi.ceph.io,operatorconfigs.csi.ceph.io -o yaml`.

Check what actually runs before trusting the values: this cluster has `enableCephfsDriver: false` yet runs the CephFS driver pods.

## CVE-2025-30156 (CephX)

Ceph ≥ v19.2.6 / v20.2.4 plus `spec.security.cephx.daemon.keyRotationPolicy: KeyGeneration`, `keyGeneration: 2`. Verify with `kubectl -n rook-ceph get cephcluster rook-ceph -o jsonpath='{.status.cephx}'`. CSI keys must stay `security.cephx.csi.keyType: aes` because aes256k kernel mounts need Linux 7.0+ and Talos ships 6.18; mute the four `AUTH_INSECURE_*` warnings via `healthCheck.muteHealthWarning` as onedr0p does in [#11552](https://github.com/onedr0p/home-ops/pull/11552).

## HelmRelease timeout and the rollback trap (2026-09-13, #720/#722)

A `cephImage` change rolls every mon, mgr and OSD and the cluster chart's health check keeps the CephCluster `Progressing` for the whole run (about 25 minutes on this cluster). The `rook-ceph-cluster` HelmRelease needs `spec.timeout: 30m`; with Flux's default 5m the upgrade "fails" and Flux rolls back, which reverts the CephCluster image and any `security.cephx` change mid-upgrade.

Once rolled back, Rook sees mixed versions and takes the "more than one ceph version running, triggering upgrade" path, which has **no downgrade guard**: it will move already-upgraded daemons back to the older spec image. The only thing holding it off is the HEALTH_ERR pre-check, and after a Ceph 19.2.6+ bump that HEALTH_ERR is the CVE's own `AUTH_INSECURE_SERVICE_*` errors. So:

1. Never mute those errors while the CephCluster spec is at the old image. Mute only after confirming `spec.cephVersion.image` is the new one and Flux cannot roll it back (`flux suspend hr rook-ceph-cluster -n rook-ceph`, or a HelmRelease timeout long enough).
2. If a rollback already happened: suspend the HelmRelease, `kubectl patch` the CephCluster back to the Git-declared image and cephx block, let Rook finish to `Ready`, then `flux resume`. The v1.19.11 upgrade then passes its health check quickly because the CephCluster already matches.
3. The errors clear by themselves once daemon keys reach generation 2; no mute is needed at all if the rollout is not interrupted.

The v1.19 toolbox does not reload its keyring after the admin key rotates (`RADOS permission denied`). `kubectl -n rook-ceph rollout restart deploy/rook-ceph-tools`. The v1.20 toolbox script watches the keyring.

Verification that this cluster reached: `status.cephx` generation 2 for admin/mon/mgr/osd/crashCollector/cephExporter with mgr and osd `keyType: aes256k`; csi and rbdMirrorPeer stay at generation 1 `aes`. Expect exactly four remaining warnings: `AUTH_INSECURE_CLIENT_KEY_TYPE`, `AUTH_INSECURE_KEYS_ALLOWED`, `AUTH_INSECURE_KEYS_CREATABLE`, `AUTH_INSECURE_ROTATING_SERVICE_KEY_TYPE` (the last clears after 2-3 hours).

## Health gate

Before any verdict: `kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status` is `HEALTH_OK`, all OSDs up/in, PGs `active+clean`. Rook v1.20.0 supports Kubernetes v1.31–v1.36; check the release notes before letting a kubelet bump past that.
