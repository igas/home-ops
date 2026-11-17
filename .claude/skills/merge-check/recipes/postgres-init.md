# Postgres init

Use this recipe for `ghcr.io/home-operations/postgres-init` bumps. Discover every consumer from the PR files and live Pod init containers. An image shared by several apps can restart all of them.

## Review

1. Check each consumer's HelmRelease, workload readiness and `status.initContainerStatuses`. Record the image tag, imageID, exit code and restart count. A completed init container is the expected healthy state.
2. Resolve the **running imageID** and candidate tag through the registry. Read their image configs for PostgreSQL version, entrypoint and source revision. Tags can be rebuilt without changing their version; today's old tag may differ from what the cluster cached.
3. Read every PostgreSQL release between the two client versions. Review the wrapper's `Dockerfile`, `docker-bake.hcl` and `entrypoint.sh` in [home-operations/containers](https://github.com/home-operations/containers/tree/main/apps/postgres-init) at the resolved revisions. Its image source label points to `postgres/postgres`, which does not contain the wrapper.
4. Compare required `INIT_POSTGRES_*` variables, defaults and inherited `PG*` variables with every consumer's values and ExternalSecret templates. Preserve Woodpecker's explicit `PGDATABASE=postgres`: its application database may not exist when initialization starts.
5. Separate client changes from server changes. This entrypoint connects to the existing database server. A postgres-init bump does not upgrade CNPG, apply server security fixes, rebuild server extensions or perform the server release notes' REINDEX/backup work.
6. Check upstream reports against the exact base variant and entrypoint. Check all consumers' rollout strategies and current startup timings before judging downtime. Apply the merge-check downtime policy and require service recovery checks when interruption is expected.

For image-only bumps, chart values/schema diffs are not applicable. Still check the changed HelmRelease values and bootstrap chart applicability.

## Preflight boundary

The normal entrypoint changes passwords, grants privileges and can create roles/databases. Running it with production credentials is a production database write, even inside a throwaway Pod.

If review identifies a client compatibility risk, a preflight must override the entrypoint and use bounded, read-only queries. Define the exact query and connection scope before running anything. This recipe does not yet provide a validated candidate connection preflight; an applicable unresolved risk remains a recipe gap under the parent skill's verdict rules.

## Evidence from #959, 2026-11-15

- [Review](https://github.com/igas/home-ops/pull/959#issuecomment-6888399770): 18.6.0 → 18.7.0, `safe with prep`. Six healthy consumers used the August 18.6.0 digest, although the registry's 18.6.0 tag had been rebuilt in October.
- The running revision was `e5f2db5600d94a05c65b4f661a5d0e096474e952`; the candidate was `e48084cea26c845b593ae36e5a6d8a5fea19996c`. The component diff included the PostgreSQL version bump and the October CA-package refresh. The initialization script was identical, blob `7a855f981ad857883897e55903cbc16cff010b77`.
- [PostgreSQL 18.7 notes](https://www.postgresql.org/docs/release/18.7/) included client fixes but no new required init configuration. [docker-library/postgres #1427](https://github.com/docker-library/postgres/issues/1427) affected Debian server startup as an arbitrary UID. The report excluded Alpine, and this wrapper used Alpine with a client-only entrypoint.
- Five single-replica Deployments used `Recreate`; Woodpecker had one server replica. Existing Pods reached Ready 9–45 seconds after scheduling, with init duration 0–1 seconds. These were old-version observations, not a candidate rollout measurement.
- No candidate Pod was created. Static checks resolved the reported compatibility concern; Prep required checking initialization, workload readiness and service recovery after rollout.

### Post-merge recovery

The operator authorized merging #959. It merged at 03:17:27 UTC; all six HelmReleases, new Pods and HTTP checks passed by 03:18:37 UTC. Each 18.7.0 init container exited 0 with no restarts. Pod creation to Ready took 4–26 seconds; this is not an exact service downtime measurement.

Recovery checks returned 200 for Autobrr `/api/healthz/readiness`, Autopulse `/`, and Prowlarr/Radarr/Sonarr `/ping`; Woodpecker `/healthz` returned 204. Sonarr briefly returned 503 during rollout and recovered. These observations support this particular upgrade, not a timing guarantee for future versions.
