# csi-driver-nfs

Chart `oci://ghcr.io/home-operations/charts-mirror/csi-driver-nfs`, pinned in `kubernetes/apps/kube-system/csi-driver-nfs/app/ocirepository.yaml`. It isn't in `bootstrap/helmfile.d`. The chart version tracks the app version (`appVersion` == `version`), and the chart ships no `values.schema.json`.

## Release notes

Read the GitHub release in kubernetes-csi/csi-driver-nfs. Each release lists cherry-picked PRs. The chart also bundles sidecar images (csi-provisioner, csi-resizer, csi-snapshotter, livenessprobe, node-driver-registrar). Each sidecar bump that shows up in the flux-local diff means reading that sidecar's `CHANGELOG/CHANGELOG-<minor>.md` on its release branch, e.g. kubernetes-csi/external-resizer `release-2.2`.

New controller flags often reach the chart with a `| default 0` template. Before calling a new arg a no-op, check the flag's own default in the PR diff. In 4.13.5 the `--max-snapshot-*` flags use `0` = unlimited.

## Blast radius

As of 2026-10-11 the `nfs-slow` StorageClass exists but nothing uses it: no PVs on `nfs.csi.k8s.io`, no PVCs on `nfs-slow`, and no NFS VolumeSnapshotClass. Re-check every review, because once something mounts NFS a node-plugin restart matters:

```
kubectl get pv -o jsonpath='{range .items[*]}{.spec.csi.driver}{"\n"}{end}' | sort | uniq -c
kubectl get pvc -A --no-headers | grep -c nfs-slow
```

## Precedent

onedr0p removed csi-driver-nfs on 2026-02-07 ("chore: remove csi driver nfs/smb"). His last bump was #10445 (4.12.1 → 4.13.0). Later versions have no precedent. Treat that as neutral.
