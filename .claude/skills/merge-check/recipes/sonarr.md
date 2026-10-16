# sonarr

`default/sonarr` is an app-template Deployment running `ghcr.io/home-operations/sonarr`. That image builds from Sonarr's develop feed (`SONARR__UPDATE__BRANCH: develop`), so v5 tags are GitHub **prereleases** off `v5-develop`. That is normal here and is not a finding by itself. Renovate automerges patch bumps only (`.renovaterc.json5`), so a minor or major PR is expected to stay open.

The database is **Postgres**, not SQLite: `sonarr-main` and `sonarr-log` on CNPG `database/postgres-18`. The credentials come from `sonarr-secret`. Note that onedr0p runs Sonarr on SQLite, so his precedent never covers the Postgres migration path.

## Cluster state

```
kubectl -n default get pod -l app.kubernetes.io/name=sonarr -o jsonpath='{..image}'
kubectl -n default exec deploy/sonarr -c app -- grep -E '<Auth|<Branch' /config/config.xml
```

The API needs the `Host` header, because AllowedHosts rejects the pod IP:

```
kubectl -n default exec deploy/sonarr -c app -- sh -c 'curl -s -H "X-Api-Key: $SONARR__AUTH__APIKEY" -H "Host: sonarr.default.svc.cluster.local" http://localhost/api/v3/<endpoint>'
```

## Database rollback

Nothing backs up the Sonarr database. There are no CNPG ScheduledBackups and no Barman plugin, and Sonarr's own backups (`/config/Backups`, NFS) only hold `config.xml` when it runs on Postgres. VolSync only covers the `config` PVC. Any bump that adds a migration (check `src/NzbDrone.Core/Datastore/Migration/` in the compare) is one-way. Put a dump in **Prep**:

```
kubectl -n database exec $(kubectl -n database get cluster postgres-18 -o jsonpath='{.status.currentPrimary}') -c postgres -- pg_dump -Fc -d sonarr-main > sonarr-main.dump
```

v4 → v5 (2026-10): migration 207 moves the quality-definition size limits into quality profiles and drops the old columns. For the follow-up, check the profile sizes, then check that the next recyclarr sync succeeds.

## Auth

v5 removed Basic auth (#7651) and defaults to Forms with a generated `sonarr` user (#9013). Ours is `AuthenticationMethod=External` / `DisabledForLocalAddresses` in `config.xml`, and that is not pinned by env. `InitialUserService` only acts when the method is `Forms`, so External survives. If `config.xml` is ever regenerated, the default flips to Forms.

## API consumers

The `refresh-series.sh` and `tag-codecs.sh` scripts (configmap), kometa and autopulse all call `/api/v3`. Confirm that `src/Sonarr.Api.V3` still exists at the new tag. Recyclarr picks V3 or V5 gateways by Sonarr major. It needs ≥ 8.8.0 for Sonarr v5 (recyclarr#988), so see [recyclarr.md](recyclarr.md).
