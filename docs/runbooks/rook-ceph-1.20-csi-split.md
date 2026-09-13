# Rook v1.20: moving CSI to the ceph-csi-drivers chart

Rook v1.20 stopped managing the Ceph CSI drivers from the `rook-ceph` chart. The
`ceph-csi-operator` controller still ships as a subchart of `rook-ceph`, but the
`OperatorConfig` and the per-driver `Driver` CRs it reconciles now come from the
separate `ceph-csi-drivers` chart. Bumping `rook-ceph` on its own deletes the
ServiceAccounts and RBAC the live plugin pods run under and creates nothing in
their place.

Written for the 2026-09 v1.19.11 → v1.20.7 move, issue #732. Figures below were
read off this cluster on 2026-09-13; re-check them before reusing this.

## What the split actually renames

This cluster was already on ceph-csi-operator (`ROOK_USE_CSI_OPERATOR: "true"`
under v1.19), so the plugin pods were already named after the drivers. What
changes is who owns them and what their ServiceAccounts are called.

ceph-csi-operator v0.6.0 passed `CSI_SERVICE_ACCOUNT_PREFIX: "ceph-csi-"`; v1.0.4
passes an empty prefix and derives the name from the driver instead. So every
ServiceAccount and every Role, RoleBinding, ClusterRole and ClusterRoleBinding
around it is renamed:

| v1.19.11 (rook-ceph chart) | v1.20.7 (ceph-csi-drivers chart) |
| --- | --- |
| `ceph-csi-rbd-nodeplugin-sa` | `rook-ceph-rbd-csi-ceph-com-nodeplugin-sa` |
| `ceph-csi-rbd-ctrlplugin-sa` | `rook-ceph-rbd-csi-ceph-com-ctrlplugin-sa` |
| `ceph-csi-cephfs-nodeplugin-sa` | `rook-ceph-cephfs-csi-ceph-com-nodeplugin-sa` |
| `ceph-csi-cephfs-ctrlplugin-sa` | `rook-ceph-cephfs-csi-ceph-com-ctrlplugin-sa` |
| `ceph-csi-controller-manager` | `ceph-csi` (still from the `rook-ceph` chart) |

The `-cr`, `-crb`, `-r` and `-rb` objects follow the same rename. The operator
rolls the DaemonSets and Deployments onto the new ServiceAccounts once the new
`Driver` CRs land, which is why `ceph-csi-drivers` has to reconcile straight
after `rook-ceph` and before anything that provisions volumes.

The rendered diff also drops `ceph-csi-nfs-*`, `ceph-csi-nvmeof-*` and the
pre-operator `rook-csi-rbd-*` / `rook-csi-cephfs-*` ServiceAccounts with no
replacement. Nothing runs under those here; confirm the same before merging:

```sh
kubectl -n rook-ceph get pods -o jsonpath='{range .items[*]}{.spec.serviceAccountName}{"\n"}{end}' | sort -u
```

## Adopting the CRs helm already expects to own

The v1.19 Rook operator pre-stamps the CRs it manages with the helm ownership
metadata of the chart that is about to take over, so helm adopts them instead of
failing on "invalid ownership metadata". It only stamps CRs it is actively
reconciling. Under v1.19 this cluster set `csi.enableCephfsDriver: false`, so the
CephFS `Driver` was left unstamped while its pods kept running.

Check all three before merging:

```sh
for r in driver/rook-ceph.cephfs.csi.ceph.com \
         driver/rook-ceph.rbd.csi.ceph.com \
         operatorconfig/ceph-csi-operator-config; do
  echo -n "$r => "
  kubectl -n rook-ceph get "$r" \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}|{.metadata.labels.app\.kubernetes\.io/managed-by}{"\n"}'
done
```

Anything that answers `|` needs stamping, or the first `ceph-csi-drivers`
reconcile fails:

```sh
kubectl -n rook-ceph annotate driver rook-ceph.cephfs.csi.ceph.com \
  meta.helm.sh/release-name=ceph-csi-drivers \
  meta.helm.sh/release-namespace=rook-ceph
kubectl -n rook-ceph label driver rook-ceph.cephfs.csi.ceph.com \
  app.kubernetes.io/managed-by=Helm
```

Deleting the CR instead would take the running CephFS plugin pods with it. For
#732 the CephFS `Driver` was stamped this way on 2026-09-13, ahead of the merge;
RBD and the `OperatorConfig` already carried it.

## Values that have to be carried over by hand

Start from Rook's own recommended values file, which the drivers chart is
documented as requiring because its bare defaults do not work with Rook at all:
[`deploy/charts/ceph-csi-drivers/values.yaml`](https://github.com/rook/rook/blob/v1.20.7/deploy/charts/ceph-csi-drivers/values.yaml).
It sets the namespace, the `imageSet`, the two priority class names and the four
prefixed driver names, and nothing else.

That baseline is not enough on an upgrade, because it leaves everything else at
chart defaults that do not match what Rook wrote into the live CRs. Rendered
against this cluster it would give RBD `snapshotPolicy: none`, `grpcTimeout: 30`,
one controller replica and log rotation on.

**The `snapshotPolicy` one is the dangerous default.** The operator only runs a
`csi-snapshotter` when the policy is not `none`
([`driver_controller.go` v1.0.5](https://github.com/ceph/ceph-csi-operator/blob/v1.0.5/internal/controller/driver_controller.go), the `snPolicy != csiv1.NoneSnapshotPolicy` guard), so
taking the recommended file as-is would drop the sidecar behind the
`csi-ceph-blockpool` VolumeSnapshotClass and every VolSync RBD snapshot with it.

Snapshot the live CRs first and diff the render against the snapshot:

```sh
kubectl -n rook-ceph get drivers.csi.ceph.io,operatorconfigs.csi.ceph.io -o yaml
```

The gaps worth knowing about:

- `grpcTimeout` defaults to 30; Rook ran 150.
- `controllerPlugin.replicas` defaults to 1; Rook ran 2.
- `snapshotPolicy`: see above. The live CRs set no policy at all, and an unset
  policy resolves to `volumeSnapshot` (`cmp.Or(spec.SnapshotPolicy,
  VolumeSnapshotSnapshotPolicy)`), so read the real value off the running sidecar:
  RBD's `csi-snapshotter` has no `--feature-gates=CSIVolumeGroupSnapshot=true`
  (so: `volumeSnapshot`), CephFS's does (so: `volumeGroupSnapshot`).
- `log.rotation.enabled` defaults to true, which adds a log-rotator sidecar and a
  hostPath the live drivers do not have. Setting it false is what suppresses the
  whole block; the chart emits no `enabled` key either way.
- Resource requests and priority class names only exist under
  `operatorConfig.driverSpecDefaults`. The per-driver `drivers.*` blocks in the
  chart template ignore them. One set of defaults also straightens out the
  priority classes Rook wrote the wrong way round for CephFS (`ctrlplugin` on
  `system-node-critical`, `nodeplugin` on `system-cluster-critical`); the CephFS
  pods restart once for it.
- `controllerPlugin.hostNetwork` reads `true` in the live `OperatorConfig` and
  renders `false` here. Both `ctrlplugin` Deployments already run without host
  network, so this only makes the CR agree with the pods. The `nodeplugin`
  DaemonSets are on host network either way.

Rook keeps ownership of the `CephConnection` and `ClientProfile` CRs, so the
chart's `cephConnections` and `clientProfiles` lists stay empty. That is also why
`csi.cephFSKernelMountOptions` moves to `cephClusterSpec.csi.cephfs.kernelMountOptions`
on the *cluster* chart rather than into this one: Rook writes it into the
`ClientProfile` the CephFS driver reads. The operator chart has no
`values.schema.json`, so a leftover `csi.cephFSKernelMountOptions` would be
accepted and silently ignored.

## What else the bump carries

- CSI sidecar images move with the chart: cephcsi v3.16.3 → v3.17.1, provisioner
  v6.1.1 → v6.2.0, attacher v4.11.0 → v4.12.0, registrar v2.16.0 → v2.17.0. The
  plugin pods restart.
- The image set lands in `rook-csi-operator-image-set-configmap`, which the
  v1.20 `rook-ceph` chart now renders itself. The v1.19 operator already created
  it with matching helm metadata, so it is adopted, not recreated.
- `ceph-csi-drivers` versions independently of the two Rook charts and sits
  outside their Renovate group, so it bumps on its own. Pinned at 1.0.5 against
  the ceph-csi-operator v1.0.4 that `rook-ceph` v1.20.7 vendors as a subchart.
- New operator defaults: `ROOK_CEPH_MON_RUN_AS_ROOT: "false"` and
  `ROOK_DELETE_UNUSED_CRUSH_RULES: "true"`.
- `cephImage` stays pinned at `v19.2.6`. The v1.20 chart defaults to Ceph v20
  (Tentacle); that is a separate upgrade.
- The v1.20 toolbox script watches the keyring, so it no longer needs the manual
  `rollout restart` the v1.19 one did after a cephx rotation.
- `rook-ceph-cluster` keeps `timeout: 30m` for Ceph daemon rollouts. The
  `rook-ceph` HelmRelease does not need one: its health check is the operator
  Deployment, and the CSI pods roll asynchronously afterwards.
