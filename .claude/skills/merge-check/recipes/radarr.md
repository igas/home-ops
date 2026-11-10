# radarr

## Digest rebuilds are separate from app upgrades

Inspect immutable old/new image configs for app version, build revision, User, entrypoint, environment and working directory. The `org.opencontainers.image.source` label names Radarr, but the build revision identifies the home-operations/containers repository. Compare that repository's relevant Dockerfile and entrypoint files.

On #869 both digests kept app version 6.4.4.10685. The relevant Dockerfile change was `apk add --upgrade`; runtime configuration stayed unchanged. The separate #884 PR upgrades the application to 7.0.0.10815. Do not infer a Radarr app migration from a container build-revision change alone.

## PostgreSQL and authentication on Radarr 7

This cluster uses PostgreSQL, not SQLite. Read the live authentication method rather than copying Sonarr's setting: on #884 Radarr used Forms/DisabledForLocalAddresses while Sonarr used External. Target 7.0.0.10815 still supports Forms and adds OIDC.

Radarr 7 moves to .NET 10 and changes FluentMigrator/PostgreSQL generator selection. GitHub's compare response caps at 300 files for this range; compare complete migration-directory listings separately. Through 7.0.0.10815, no numbered migration file was added or removed, and the live database maximum was 242. Existing migration edits do not imply those migrations rerun.

Re-review at 7.0.1.10859 found a new `243_mediainfo_multiple_streams.cs` migration. Complete directory inventories changed from 141 entries at 6.4.4.10685 and 7.0.0.10815 to 142 at 7.0.1.10859. It rewrites MovieFiles.MediaInfo from scalar audio/subtitle fields to stream arrays, removes the old JSON keys and resets MovieMetadata.LastInfoSync. The target batches 1000 IDs at a time after earlier OOM fixes, but it still changes persisted data. Live schema remained 242 with 2761 MovieFiles at review. The earlier no-new-migration finding cannot be carried forward; verify a recoverable database restore point before treating an old-image rollback as sufficient. Both published Radarr 7 tags were marked pre-release by GitHub.

Read the CNPG backup inventory. A config PVC backup or `/config/Backups` mount does not prove a PostgreSQL dump exists. There is no validated isolated PostgreSQL-backed startup/authentication and rollback recipe yet. Keep that gap explicit; never start the candidate against the production database as a preflight. Recyclarr 8.8.1 fixes Radarr 7 OIDC handling, but current Forms auth does not itself require OIDC configuration.

## 7.0.2 packaging and provider removal

At 7.0.2.10888, migration 243 is unchanged from 7.0.1.10859. The numbered migration inventory alone misses startup writes: this release removes KometaMetadata and its settings type. `ProviderRepository.Query` substitutes NullConfig for a missing settings type, then `ProviderFactory.RemoveMissingImplementations` deletes obsolete definitions on ApplicationStartedEvent. The live Kometa row was disabled on 2026-11-10, so its removal does not disable an active exporter, but an image rollback does not restore the row. Inspect only its ID, implementation, enabled flag and contract; provider settings can contain secrets.

The exact 7.0.2 image build adds `krb5-libs` and `PGGSSENCMODE=disable`. Its Dockerfile explains that the default Npgsql GSS probe can segfault on musl's non-thread-safe krb5. Inspect the pinned digest's config, not just the app release tag, before carrying forward a PostgreSQL packaging concern. This workaround is positive static evidence, not a validated startup test against our database. The app also redacts PostgreSQL passwords in migration logs; inspect source rather than retrieving raw migration logs that might contain credentials.
