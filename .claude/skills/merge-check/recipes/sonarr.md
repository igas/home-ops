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

Inspect newly added migrations under `src/NzbDrone.Core/Datastore/Migration/` and their rollback consequences. A migration's existence alone does not require a backup. Use backup **Prep** for major upgrades or a specific destructive data change or recovery risk that warrants it, and name that reason in the review. Routine patches and non-destructive migrations do not require a fresh dump by default. The dump taken for the earlier v4 to v5 major upgrade was not a policy to back up before every update.

When a backup is warranted, verify the current database backup inventory. On the 2026-11-01 review there were no CNPG ScheduledBackups or Barman plugin. Sonarr's own backups (`/config/Backups`, NFS) only hold `config.xml` when it runs on Postgres, and VolSync only covers the `config` PVC. Neither establishes a PostgreSQL restore point. A custom-format dump can be taken with:

```
kubectl -n database exec $(kubectl -n database get cluster postgres-18 -o jsonpath='{.status.currentPrimary}') -c postgres -- pg_dump -Fc -d sonarr-main > sonarr-main.dump
```

v4 → v5 (2026-10): migration 207 moves the quality-definition size limits into quality profiles and drops the old columns. For the follow-up, check the profile sizes, then check that the next recyclarr sync succeeds.

A changed existing migration is not automatically a new migration. On #892, 5.0.0.2742 to 5.0.0.2870 changed migration 225 to batch MediaInfo conversion, but added no numbered migration. The running PostgreSQL database was already at 237. Read the version table before claiming that a migration edit runs again on upgrade.

Re-review the migration inventory when Renovate advances the target. The later #892 head targets 5.0.0.2907 and **does** add migration 240, absent from its release-note bullets. It replaces the unique `Series.TitleSlug` index with a non-unique index without deleting rows. The live schema was still 237 on 2026-11-01. Record that an image rollback does not restore uniqueness after duplicate slugs can be inserted, but do not require a fresh dump solely because this non-destructive migration exists. The earlier mandatory-backup prep on #892 overgeneralized the major-upgrade precaution.

After the requested #892 merge, read-only queries confirmed schema version 240 and `pg_indexes.indexdef` showed `CREATE INDEX` rather than `CREATE UNIQUE INDEX` for `IX_Series_TitleSlug`. The app's authenticated V3 status reported the target version and unchanged External auth, and its health report was empty. No dump or real Recyclarr sync was triggered during that rollout check.

## Auth

v5 removed Basic auth (#7651) and defaults to Forms with a generated `sonarr` user (#9013). Ours is `AuthenticationMethod=External` / `DisabledForLocalAddresses` in `config.xml`, and that is not pinned by env. `InitialUserService` only acts when the method is `Forms`, so External survives. If `config.xml` is ever regenerated, the default flips to Forms.

## API consumers

The `refresh-series.sh` and `tag-codecs.sh` scripts (configmap), kometa and autopulse all call `/api/v3`. Confirm that `src/Sonarr.Api.V3` still exists at the new tag. Recyclarr picks V3 or V5 gateways by Sonarr major. It needs ≥ 8.8.0 for Sonarr v5 (recyclarr#988), so see [recyclarr.md](recyclarr.md).
