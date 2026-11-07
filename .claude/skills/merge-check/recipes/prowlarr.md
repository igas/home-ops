# prowlarr

Read every app release and compare the migration directory independently of release-note bullets. On #906, 2.6.5.5623 → 2.7.0.5723 included 2.6.6.5717, changed indexer definition format 11 → 12, and left all migration files unchanged.

## Active database

A `/config/prowlarr.db` file does not prove SQLite is active. On #906 that file existed, but authenticated GET `/api/v1/system/status` reported `databaseType: postgreSQL` and database version 14.8. Read the status endpoint using the container's existing API-key environment variable, then print only the non-secret version/database fields. Do not substitute the local CNPG version or infer the backend from a leftover database file.

## Allowed hosts

Inspect both the non-secret config.xml field and `PROWLARR__SERVER__ALLOWEDHOSTS`. The 2.7 host-filter change ignores bind addresses such as 0.0.0.0 and [::]; an empty setting still permits all hosts. Do not copy Sonarr's Host-header probe requirement without checking Prowlarr's effective setting. Our #906 snapshot had an empty field/override and IP-based /ping probes.

## Kernel-specific crash reports

[Prowlarr #2884](https://github.com/Prowlarr/Prowlarr/issues/2884) reports .NET process aborts on Ubuntu kernel 7.0.0-42, including the exact home-operations image/digest and an isolated SQLite setup. Read the full comments: the reporter also reproduced on the old app, then reported success on kernel 6.8. Switching from linuxserver to home-operations alone did not solve it. Compare live node kernels before treating this as a version-specific regression. All our nodes ran 6.18.56-talos at review; re-evaluate the report before a future kernel 7 rollout. Never trigger real indexer searches or production syncs as a merge-check preflight.
