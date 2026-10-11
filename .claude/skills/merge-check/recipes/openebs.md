# openebs

HelmRelease `openebs-system/openebs` from `oci://ghcr.io/openebs/charts/openebs` (tag in `kubernetes/apps/openebs-system/openebs/app/ocirepository.yaml`). Layer 3. Not in `bootstrap/helmfile.d`. onedr0p dropped OpenEBS in July 2026 (onedr0p/home-ops#11244), so there is no precedent past 4.5.1; say so rather than treating it as missing evidence.

The umbrella chart bundles several engines. We run **only Local PV Hostpath** (`localpv-provisioner`, one Deployment, `openebs-hostpath` StorageClass at `/var/mnt/local-hostpath`). Mayastor, ZFS, LVM, Rawfile (off by default), Loki, Alloy and MinIO are all disabled. Most OpenEBS release notes are about engines we don't run.

## Review

- Release notes: read the umbrella release, then only the **Hostpath** engine row (`openebs/dynamic-localpv-provisioner`). If that row says "remains at vX", the engine did not change.
- The chart has no `values.schema.json`. The decisive check is rendering both charts with our values and diffing:

```
yq '.spec.values' kubernetes/apps/openebs-system/openebs/app/helmrelease.yaml > values.yaml
helm template openebs old/openebs -n openebs-system -f values.yaml --include-crds > old.yaml
helm template openebs new/openebs -n openebs-system -f values.yaml --include-crds > new.yaml
diff old.yaml new.yaml
```

  An empty diff means the bump only moves the HelmRelease's chart version; Helm does an upgrade with no pod restarts. The flux-local helmrelease diff comment is absent in that case, which is expected.
- We set the image registry to `quay.io/` for `localpv` and `helperPod`. If upstream moves the Hostpath images off quay.io (as 4.6.2 did for MinIO, since `quay.io/minio` stopped allowing anonymous pulls), our override would pin the old location. Check for that.

## Cluster state

```
kubectl get helmrelease -n openebs-system openebs
kubectl get pods -n openebs-system -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.containers[*].image}{"\n"}{end}'
```

Expect one `openebs-localpv-provisioner` pod. The provisioner image tag tracks the Hostpath engine version, not the chart version (chart 4.6.x ships `provisioner-localpv:4.6.0`).
