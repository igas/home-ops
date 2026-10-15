# app-template

`oci://ghcr.io/bjw-s-labs/helm/app-template` is a platform-layer chart. Each consumer pins it in its own `kubernetes/apps/<ns>/<app>/app/ocirepository.yaml` (17 as of 2026-10-15), and the bootstrap `onepassword` release pins it in `bootstrap/helmfile.d/01-apps.yaml`. That release reads its values from the onepassword HelmRelease (`templates/values.yaml.gotmpl`), so rendering the HelmRelease covers bootstrap too.

## Release notes

The app-template release only says "Upgraded the common library to vX". Read the matching `common-X` releases on bjw-s-labs/helm-charts for every version in the range:

```
gh api repos/bjw-s-labs/helm-charts/releases/tags/common-5.3.0 --jq .body
```

## Render every consumer against current main

Renovate keeps one long-lived branch for this chart. It often sits many commits behind main, so CI's flux-local diff can miss value changes merged since. Render every consumer from current main values with both chart versions, and diff with keys sorted:

```
D=<scratch>/at; mkdir -p $D/c510 $D/c530 $D/vals $D/out
helm pull oci://ghcr.io/bjw-s-labs/helm/app-template --version <old> --untar -d $D/c510
helm pull oci://ghcr.io/bjw-s-labs/helm/app-template --version <new> --untar -d $D/c530
for ocir in $(grep -rl 'bjw-s-labs/helm/app-template' kubernetes/apps --include=ocirepository.yaml); do
  dir=$(dirname "$ocir"); name=$(yq '.metadata.name' $dir/helmrelease.yaml); ns=$(echo $dir | cut -d/ -f3)
  yq '.spec.values' $dir/helmrelease.yaml > $D/vals/$name.yaml
  for v in 510 530; do
    helm template $name $D/c$v/app-template -n $ns -f $D/vals/$name.yaml \
      | yq -P 'sort_keys(..)' | grep -v 'helm.sh/chart: app-template-' > $D/out/$name.$v.norm
  done
  echo "$name: $(diff $D/out/$name.510.norm $D/out/$name.530.norm | grep -c '^[<>]') changed lines"
done
```

`helm template` enforces the chart's `values.schema.json`, so a clean render also proves the schema accepts our values. No consumer uses `valuesFrom` or `postRenderers` (as of 2026-10-15). If one does, this render is incomplete for it.

Selector or label-order changes show up in flux-local as `+`/`-` pairs that move a key inside `matchLabels`. That is harmless when the key set is identical. A key added to or removed from a selector is a hold, because Deployment and StatefulSet selectors are immutable and Helm upgrades fail.

## Restarts

`helm.sh/chart` is not on any pod template, so a bump that renders identically upgrades all releases without rolling a pod. Check `.spec.template.metadata` (and `.spec.jobTemplate...` for CronJobs) in the new render if a release changes pod labels or annotations.

## Precedent

onedr0p bumps app-template across ~25 releases with only version lines: `gh pr list -R onedr0p/home-ops --state merged --search "app-template"`. The search also returns unrelated PRs that mention the chart, so match on the title.
