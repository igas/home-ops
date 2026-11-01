# radarr

## Digest rebuilds are separate from app upgrades

Inspect immutable old/new image configs for app version, build revision, User, entrypoint, environment and working directory. The `org.opencontainers.image.source` label names Radarr, but the build revision identifies the home-operations/containers repository. Compare that repository's relevant Dockerfile and entrypoint files.

On #869 both digests kept app version 6.4.4.10685. The relevant Dockerfile change was `apk add --upgrade`; runtime configuration stayed unchanged. The separate #884 PR upgrades the application to 7.0.0.10815. Do not infer a Radarr app migration from a container build-revision change alone.

## PostgreSQL and authentication on Radarr 7

This cluster uses PostgreSQL, not SQLite. Read the live authentication method rather than copying Sonarr's setting: on #884 Radarr used Forms/DisabledForLocalAddresses while Sonarr used External. Target 7.0.0.10815 still supports Forms and adds OIDC.

Radarr 7 moves to .NET 10 and changes FluentMigrator/PostgreSQL generator selection. GitHub's compare response caps at 300 files for this range; compare complete migration-directory listings separately. No numbered migration file was added or removed, and the live database maximum was 242. Existing migration edits do not imply those migrations rerun.

Read the CNPG backup inventory. A config PVC backup or `/config/Backups` mount does not prove a PostgreSQL dump exists. There is no validated isolated PostgreSQL-backed startup/authentication and rollback recipe yet. Keep that gap explicit; never start the candidate against the production database as a preflight. Recyclarr 8.8.1 fixes Radarr 7 OIDC handling, but current Forms auth does not itself require OIDC configuration.
