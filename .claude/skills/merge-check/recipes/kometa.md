# kometa

CronJob `default/kometa` (app-template), daily, four sequential `python3 kometa.py --run --read-only-config --run-libraries <lib>` calls under `/bin/sh -c`. Pod runs as uid 1000 with a read-only root filesystem.

**A broken run looks green.** `kometa.py` exits **0** on a missing Python requirement (`Requirements Error: Requirements are not installed`), and the shell chains the four runs with `;`, so the Job shows `Complete` either way. Health means reading the logs, not the Job status. The pod log is truncated by kubelet rotation (only the tail of the last library survives); the `Version: x  Newest Version: y` banner near the end confirms which image ran.

## Settings that decide which release notes matter

- Config: `kubernetes/apps/default/kometa/app/resources/config.yml`. Only `plex` and `tmdb` connectors. No Trakt, MDBList API key, Tautulli, Radarr/Sonarr, or notifications. Notes about those skip us.
- `tmdb.region` unset, so `streaming` Defaults run with the default (US) region.
- Defaults in use: collections `aspect based basic collectionless content_rating_au country emmy golden network oscars resolution seasonal streaming studio tmdb universe`; overlays `status audio_codec resolution`. Diff `defaults/` between tags for these files only: `git diff vOLD vNEW -- defaults/both/<f>.yml defaults/movie/<f>.yml ...`.
- No `delete_collections` operation, but `delete_below_minimum: true` with `minimum_items: 2`.

## Image layout changes

v2.5.x moved dependencies into a uv venv at `/.venv` and puts `/.venv/bin` first in the image `PATH`. Anything that overrides `PATH` (we don't: the container env is `TZ` only) picks the system `python3` and hits the exit-0 requirements error (upstream #3656). Check the image env without pulling:

```
docker buildx imagetools inspect kometateam/kometa@<digest> --format '{{json .Image}}' | jq '."linux/amd64".config.Env'
```

## Preflight: requirements import under our pod spec

Tests that the new image imports its requirements as uid 1000 with a read-only root. Talks to nothing; no Plex, no PVC.

```
kubectl run merge-check-kometa-<pr> -n default --restart=Never --labels=merge-check=preflight \
  --image=kometateam/kometa:<tag>@<digest> --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"runAsGroup":1000},"containers":[{"name":"merge-check-kometa-<pr>","image":"kometateam/kometa:<tag>@<digest>","command":["/bin/sh","-c"],"args":["command -v python3 && python3 -c \"import packaging.requirements, arrapi, dateutil, lxml, pathvalidate, PIL, plexapi.server, psutil, requests, ruamel.yaml, schedule, setuptools, tmdbapis, dotenv; print(\\\"imports ok\\\")\""],"securityContext":{"allowPrivilegeEscalation":false,"readOnlyRootFilesystem":true,"capabilities":{"drop":["ALL"]}}}]}}'
kubectl wait -n default pod/merge-check-kometa-<pr> --for=jsonpath='{.status.phase}'=Succeeded --timeout=180s
kubectl logs -n default merge-check-kometa-<pr>
kubectl delete pod -n default merge-check-kometa-<pr>
```

Pass: `python3` resolves to `/.venv/bin/python3` and `imports ok` prints. Take the import list from the `try:` block near the top of `kometa.py` at the new tag.

## Prep after merge

The Job runs `@daily` Australia/Sydney. After the first run on the new tag, `kubectl logs -n default job/<latest>` and grep for `Requirements Error`, `Critical`, and the version banner.
