# autobrr

Deployment `default/autobrr` (app-template), one replica. The `ghcr.io/autobrr/autobrr` tag is pinned in `kubernetes/apps/default/autobrr/app/helmrelease.yaml`. State lives in Postgres (the database is created by the `init-db` postgres-init container from `autobrr-secret`), not SQLite. The `config` PVC holds only the TOML.

autobrr ships a minor about every two weeks, and Renovate labels every one `type/minor`. They are almost always indexer and feature changes.

## Release notes

The GitHub release body is the whole changelog. Since v1.88.0 ([#2727](https://github.com/autobrr/autobrr/pull/2727)), breaking changes are listed first, so read the top of each release in the range:

```
gh release view vX.Y.Z -R autobrr/autobrr --json body --jq .body | head -20
```

## Config and migrations

The changelog doesn't flag schema changes. List them from the compare diff:

```
gh api repos/autobrr/autobrr/compare/vOLD...vNEW --jq '.files[].filename' | grep -iE 'migrations/postgres/|internal/config/|internal/domain/config.go'
```

Migrations run on startup and are forward-only. Rolling back the image after a migration means restoring the database from backup. Changes to `internal/config/config.go` are where new or renamed `AUTOBRR__*` env vars show up. Compare them to the `env:` block in the HelmRelease.

## Cluster-specific settings

- `AUTOBRR__CHECK_FOR_UPDATES: false`. Update-available notifications (including the v1.88.0 built-in inbox) stay quiet.
- `AUTOBRR__SESSION_SECRET` has been dead since v1.82.0 ([autobrr#2509](https://github.com/autobrr/autobrr/pull/2509)). onedr0p dropped his whole `autobrr-secret` ([#11765](https://github.com/onedr0p/home-ops/pull/11765)), but ours also holds the Postgres credentials, so only that key can go: line `AUTOBRR__SESSION_SECRET` in `app/externalsecret.yaml`.

## Precedent

onedr0p bumps the same image, usually within a day of release: `gh pr list -R onedr0p/home-ops --state merged --search "ghcr.io/autobrr/autobrr"`. Don't confuse it with `ghcr.io/autobrr/qui`, which the same search returns.
