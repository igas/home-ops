# snapshot-controller

Chart `ghcr.io/piraeusdatastore/helm-charts/snapshot-controller`, pinned once in `kubernetes/apps/kube-system/snapshot-controller/app/ocirepository.yaml`. It isn't in `bootstrap/helmfile.d`. The chart's GitHub releases have no notes. Read the commit log for `charts/snapshot-controller` between the two release dates instead:

```
gh api 'repos/piraeusdatastore/helm-charts/commits?path=charts/snapshot-controller&per_page=10' \
  --jq '.[] | .sha[0:8] + " " + .commit.committer.date + " " + (.commit.message|split("\n")[0])'
```

Many releases are chart-only, with `appVersion` unchanged. When `appVersion` does move, read the matching releases in kubernetes-csi/external-snapshotter, and look hard at CRD version changes and conversion webhooks. 5.1.1 injected a conversion webhook for the v8.6.0 CRDs, and 5.2.0 disabled the webhook by default.

## Feature gate removal

The chart's default `controller.args.featureGates: CSIVolumeGroupSnapshot=true` renders as `--feature-gates=CSIVolumeGroupSnapshot=true`. We don't set it ourselves. external-snapshotter v8.7.0 (chart 5.4.0) made the gate GA with default true and said the next release deletes it ([#1475](https://github.com/kubernetes-csi/external-snapshotter/pull/1475)). Once deleted, an explicit flag for an unknown gate stops the controller starting. On the first bump past v8.7.0, check the new chart's `values.yaml`. If `featureGates` still names the gate, the PR is a hold until our HelmRelease values set `controller.args.featureGates: null`. `deployment_controller.yaml` renders every `controller.args` key as `--<kebab>=<val>`, and a Helm `null` deletes the default key, so no flag is rendered. An empty string would render `--feature-gates=` instead.

## CRDs live in templates

The chart renders the snapshot CRDs from `templates/crds.yaml`, not `crds/`, so Helm owns them. If the HelmRelease is uninstalled (for example, the Kustomization is pruned), Helm deletes the CRDs along with every VolumeSnapshot, and VolSync relies on those. From 5.3.0, `keepCRDs: true` annotates the CRDs `helm.sh/resource-policy: keep`. We don't set it yet (as of 2026-10-05). Any change to how the chart templates the CRDs is worth a rendered diff:

```
helm template sc <chart-dir> -n kube-system -f <our values> > out.yaml   # old and new, then diff
```

## Precedent

onedr0p left this chart in July 2026 for `ghcr.io/home-operations/charts/snapshot-controller` (onedr0p/home-ops#11323) and bootstraps its CRDs through helmfile (#11547). There is no direct precedent for piraeus chart versions after that point. Treat the gap as neutral, not negative.
