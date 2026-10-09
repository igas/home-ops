# multus

Chart `ghcr.io/bjw-s-labs/helm/multus`, pinned once in `kubernetes/apps/kube-system/multus/app/ocirepository.yaml`. It isn't in `bootstrap/helmfile.d`. The `multus-networks` Kustomization depends on it, and the Kustomization health-checks the `network-attachment-definitions.k8s.cni.cncf.io` CRD.

Most releases are chart-only: `appVersion` (multus-cni) doesn't move, and the only change is the bundled bjw-s common library (`Chart.yaml` `dependencies[common]`). For those releases, read the `common-X.Y.Z` releases in bjw-s-labs/helm-charts across the range instead of the multus-cni releases. When `appVersion` does move, read k8snetworkplumbingwg/multus-cni releases. The DaemonSet runs on every node, and it is a CNI meta-plugin, so a broken rollout breaks pod networking for pods that use a NetworkAttachmentDefinition.

## Render diff decides whether pods roll

```
helm template multus <chart-dir> -n kube-system -f <our values> --include-crds > rX.yaml   # old and new, then diff
```

If the only diff is `helm.sh/chart`, that label is in DaemonSet object metadata, not `spec.template`, so the merge won't restart pods. A diff inside `spec.template` means a rolling restart on all nodes. Check the pods come back Ready on each node.

common 5.2.0 (2026-09) added tpl rendering for every string value. Our values contain no `{{`, so this has no effect on us. Re-check if values gain templated strings.

## Precedent

onedr0p left this chart in July 2026 for `ghcr.io/home-operations/charts/multus` (onedr0p/home-ops#11324). In the new chart, `multus.resources` becomes top-level `resources`, and `cni.binDir`/`netDir` defaults match our paths. There is no direct precedent for bjw-s multus versions after 1.3.2. Treat the gap as neutral. For the common library itself, his app-template bumps are useful precedent.
