# recyclarr

`default/recyclarr` is an app-template **CronJob**, not a Deployment. It runs `sync` daily at `0 0 * * *`. The `ghcr.io/recyclarr/recyclarr` tag is pinned in `kubernetes/apps/default/recyclarr/app/helmrelease.yaml`. Config comes from the `recyclarr-configmap` ConfigMap, mounted at `/config/recyclarr.yml`. API keys come from `recyclarr-secret`. `RECYCLARR_DATA_DIR=/tmp`, so the `config` PVC (`ceph-block`) holds almost nothing.

## Cluster state

A CronJob has no running pod to check. Read the image off the CronJob, then check whether the last run succeeded:

```
kubectl -n default get cronjob recyclarr -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}{.status.lastScheduleTime} {.status.lastSuccessfulTime}{"\n"}'
kubectl -n default get jobs -l app.kubernetes.io/name=recyclarr
```

If `lastSuccessfulTime` is earlier than `lastScheduleTime`, the most recent sync failed. Read its pod logs before deciding.

## Release notes

`CHANGELOG.md` is the release body. The Renovate PR body quotes it in full. The compare file list is the quickest way to find a change that ships in the image:

```
gh api repos/recyclarr/recyclarr/compare/vOLD...vNEW --jq '.files[].filename' | grep -vE '^(\.github|\.opencode|tests)/|\.md$'
```

Check every change under `docker/`. Because we pass `args: [sync]`, only the `"$#" -gt 0` branch of `docker/scripts/entrypoint.sh` runs. The supercronic and `CRON_SCHEDULE` branch never runs here. Since v8.7.3 that branch `exec`s recyclarr, so recyclarr gets SIGTERM directly. Changes to the YAML schema (`src/Recyclarr.Core/Config/`, or anything else under `Config`) need to be compared with `app/resources/recyclarr.yml`.

## Preflight

None exists yet. A real sync writes to Sonarr and Radarr, so a throwaway Pod running `sync` is not read-only. `recyclarr config list` or `sync --preview` would be the place to start if a config-schema risk ever earns a preflight.

## Precedent

onedr0p bumps the same image, usually within a day of release: `gh pr list -R onedr0p/home-ops --state merged --search "recyclarr"`. The search also returns his sonarr and radarr PRs, so match on the title.
