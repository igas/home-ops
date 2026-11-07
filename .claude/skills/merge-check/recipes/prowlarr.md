# prowlarr

Read every app release and compare the migration directory independently of release-note bullets. On #906, 2.6.5.5623 → 2.7.0.5723 included 2.6.6.5717, changed indexer definition format 11 → 12, and left all migration files unchanged.

## Active database

A `/config/prowlarr.db` file does not prove SQLite is active. On #906 that file existed, but authenticated GET `/api/v1/system/status` reported `databaseType: postgreSQL` and database version 14.8. Read the status endpoint using the container's existing API-key environment variable, then print only the non-secret version/database fields. Do not substitute the local CNPG version or infer the backend from a leftover database file.

### Prowlarr 3 PostgreSQL minimum

On #931, 2.7.0.5723 → 3.0.0.5737 raised the documented PostgreSQL minimum to 15. [The upstream change](https://github.com/Prowlarr/Prowlarr/commit/f6ba9e9cf16eb74cbd766f200a219cb0b5dbd9eb) switches startup initialization to `AddPostgres15_0()`; the target also upgrades FluentMigrator to 8.0.1 and Npgsql to 10.0.3. At the initial review, the live status endpoint reported PostgreSQL 14.8 and schema 44. That required hold even though both complete migration-directory inventories had the same 44 entries and no newly numbered migration. Existing migration edits do not imply those migrations rerun.

Before re-review, establish a recoverable backup and move the active database to a supported PostgreSQL version. Verify the database through Prowlarr's status endpoint again. An isolated candidate startup/authentication check against a disposable restored database still needs a validated recipe; starting the candidate against production is not an allowed preflight. A config-PVC backup alone does not establish PostgreSQL recovery.

The operator-approved migration on 2026-11-07 moved both `prowlarr-main` and `prowlarr-log` from NAS PostgreSQL 14.8 to CNPG `database/postgres-18`. With Prowlarr stopped, PostgreSQL 18 `pg_dump --format=custom --no-owner --no-acl` produced both archives. Restores used `pg_restore --exit-on-error --single-transaction --no-owner --no-acl --role=prowlarr` into empty databases owned by the dedicated `prowlarr` role, preserving the source `en_US.utf8` locale names. All 23 table row counts, 21 sequence states and both schema versions matched before startup. The NAS databases were retained for rollback. This verifies those archives through an actual restore, not just `pg_restore --list`.

After the database move, the operator explicitly requested merging #931. The live app reported 3.0.0.5737, PostgreSQL 18.1, schema 44 and .NET 10.0.14; the Pod was Ready with zero restarts. This was an operational rollout, not an isolated merge-check preflight. Keep that distinction when applying the recipe's write limits to future reviews.

## Allowed hosts

Inspect both the non-secret config.xml field and `PROWLARR__SERVER__ALLOWEDHOSTS`. The 2.7 host-filter change ignores bind addresses such as 0.0.0.0 and [::]; an empty setting still permits all hosts. Do not copy Sonarr's Host-header probe requirement without checking Prowlarr's effective setting. Our #906 snapshot had an empty field/override and IP-based /ping probes.

After the operator set Allowed Hosts through the UI on 2026-11-07, all three `/ping` probes gained `Host: prowlarr.default.svc.cluster.local`, matching an allowed service hostname. The rollout succeeded and the Allowed Hosts warning disappeared. Keep the UI-managed host list and probe headers aligned; this deployment does not pin Allowed Hosts through an environment variable.

## Kernel-specific crash reports

[Prowlarr #2884](https://github.com/Prowlarr/Prowlarr/issues/2884) reports .NET process aborts on Ubuntu kernel 7.0.0-42, including the exact home-operations image/digest and an isolated SQLite setup. Read the full comments: the reporter also reproduced on the old app, then reported success on kernel 6.8. Switching from linuxserver to home-operations alone did not solve it. Compare live node kernels before treating this as a version-specific regression. All our nodes ran 6.18.56-talos at review; re-evaluate the report before a future kernel 7 rollout. Never trigger real indexer searches or production syncs as a merge-check preflight.
