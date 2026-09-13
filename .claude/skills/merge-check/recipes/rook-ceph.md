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

## Health gate

Before any verdict: `kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph status` is `HEALTH_OK`, all OSDs up/in, PGs `active+clean`. Rook v1.20.0 supports Kubernetes v1.31–v1.36; check the release notes before letting a kubelet bump past that.
