# Bootstrap helmfile renders charts with no values

`bootstrap/helmfile.d/00-crds.yaml` (run by `scripts/bootstrap-apps.sh`) templates charts to extract CRDs and passes **no values**. A chart version that adds a `required` schema field breaks a fresh bootstrap while CI stays green, because flux-local renders with the real HelmRelease values.

## Check

For every key that becomes required in the values schema diff: is the chart listed in `00-crds.yaml`? If so, add the key inline under that release's `values:` and confirm with:

```
helmfile -f bootstrap/helmfile.d/00-crds.yaml template
```

The fix belongs in the same PR or the **Prep** line, not in a follow-up you have to remember.
