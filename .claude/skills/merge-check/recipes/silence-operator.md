# silence-operator

The chart is `oci://gsoci.azurecr.io/charts/giantswarm/silence-operator`, pinned in `kubernetes/apps/observability/silence-operator/app/ocirepository.yaml`. It isn't in `bootstrap/helmfile.d`. Chart and app versions move together. The release notes are in the repo's `CHANGELOG.md`, and the Renovate body usually quotes them in full. For behaviour changes, read the controller diff rather than the changelog:

```
gh api repos/giantswarm/silence-operator/compare/v<old>...v<new> \
  --jq '.files[] | select(.filename=="internal/controller/silence_v2_controller.go") | .patch'
```

## CRDs live in templates

The chart renders the Silence CRD from `templates/crds.yml` (gated on `crds.install`, which defaults to true), so Helm applies CRD changes on every upgrade. flux-local's diff comment leaves CRDs out, so an image-tag-only CI diff can hide a CRD schema change. Always diff the pulled charts.

## Our silences rely on the end-time fallback

All Silences in `kubernetes/apps/observability/silence-operator/silences/` set only `matchers`, with no `startsAt`, `endsAt`, `duration`, or `valid-until` annotation. They stay active only because the controller falls back to creationTimestamp + 100 years. From 0.21.0 that's step 4 of `calculateSilenceTimes`. A release that changes this fallback would quietly expire them, so check it on every bump.

## Registry lag

GitHub releases sometimes land before the chart and image reach gsoci (giantswarm/silence-operator#627, #731). If CI can't pull the chart, check the image with `docker manifest inspect gsoci.azurecr.io/giantswarm/silence-operator:<new>` before treating it as a real failure.
