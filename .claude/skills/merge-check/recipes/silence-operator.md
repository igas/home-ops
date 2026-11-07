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

Release 0.21.1 changes binary architecture packaging and removes the pod-template `releaseRevision` annotation. That removal explains its non-image Flux diff. The controller implementation and templated CRD stayed unchanged on #871; confirm those facts rather than assuming every patch is image-only.

## Optional extra arguments in 0.22.0

On #929, both pulled chart artifacts confirmed matching appVersions, 0.21.1 and 0.22.0. The only values/schema addition is optional `extraArgs: []`, an array of strings appended after the existing container arguments. Leaving it unset preserves the existing arguments. No bootstrap entry is needed.

The complete 19-file upstream comparison contains no application Go source changes. The controller's 100-year fallback and the chart's templated CRDs are unchanged. Old/new renders with this repo's Alertmanager address and disabled NetworkPolicy differ only in version labels and image. The release also changes China-registry publishing order, not our registry address. Do not infer a runtime preflight requirement from the minor version alone; recheck these facts on later releases.

## Registry lag

GitHub releases sometimes land before the chart and image reach gsoci (giantswarm/silence-operator#627, #731). If CI can't pull the chart, check the image with `docker manifest inspect gsoci.azurecr.io/giantswarm/silence-operator:<new>` before treating it as a real failure.
