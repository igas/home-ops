# Woodpecker CI

Woodpecker runs CI for other projects, initially repositories owned by `igas` and `visiblelightio`. It does not replace this repository's GitHub Actions. No pipeline changes to `visiblelightio/stdlib` are included.

## Deployment

- UI and GitHub webhooks: `https://ci.igas.dev`, through Cloudflare Tunnel and `envoy-external`.
- Official Helm chart 3.7.5, Woodpecker server/agent v3.19.0.
- `woodpecker` contains the server, agent, credentials and backup jobs.
- `woodpecker-builds` contains temporary pipeline Pods, Services, Secrets and workspace PVCs. Its policies reconcile before Woodpecker starts.
- One agent permits four concurrent workflows. Each workflow has a temporary 10Gi `ceph-block` workspace. Required affinity keeps its steps on the same node.
- Each build container defaults to and cannot exceed 2 CPU cores and 4Gi RAM. Requests default to 250m CPU and 256Mi RAM.
- Build namespace ceilings are 16 CPU cores and 32Gi RAM in limits, 8 CPU cores and 16Gi RAM in requests, and four workspace PVCs. This permits four workflows with one test and one service container each at default limits. Larger parallel graphs can hit admission quotas; four workflows is a concurrency ceiling, not a resource guarantee.
- PostgreSQL uses a dedicated `woodpecker` database/user on `postgres-18`, with at most 10 server connections. The database initializer follows the existing postgres-init pattern; only that init container receives the superuser credential.

## Provisioning requirements

Deployment cannot complete until these external resources exist. Do not paste credentials into chat or commit them to Git.

1. A GitHub **OAuth application**, not a GitHub App. Its homepage is `https://ci.igas.dev` and callback is `https://ci.igas.dev/authorize`. It produces `GITHUB_CLIENT` and `GITHUB_SECRET` for 1Password, not files in this repo. Private repository access is enabled. `visiblelightio` may need to approve the OAuth application under its organization policy.
2. A `woodpecker` item in the 1Password vault used by the `onepassword` ClusterSecretStore, with these exact field names:

   | Field | Purpose |
   | --- | --- |
   | `GITHUB_CLIENT` | GitHub OAuth client ID |
   | `GITHUB_SECRET` | GitHub OAuth client secret |
   | `AGENT_SECRET` | Shared agent registration secret |
   | `GRPC_SECRET` | Separate persistent gRPC signing secret |
   | `POSTGRES_PASSWORD` | Password for the dedicated database user |

   Generate three different random 32-byte hex values for the agent, gRPC and database fields. The existing postgres-init script interpolates the database password into SQL, so use hex rather than a password containing quotes. Existing `cloudnative-pg` and `volsync-template` 1Password items are reused. The latter supplies the Restic/S3 backup credentials.
3. Reconcile and validate the deployment, then log in as `igas` and explicitly enable each intended repository. Registration remains closed; `visiblelightio` is an allowed repository owner, not a grant of login access to every organization member. Check that enabled repositories require approval for fork PRs and have no approval-allowed users that bypass the intended gate.

## Isolation limits

Build Pods have no service-account token. Per-step service-account changes, native Kubernetes Secret references, labels, annotations, affinity, node selectors, runtime classes and tolerations are disabled. Baseline Pod Security admission rejects privileged containers, host namespaces and hostPath mounts even if application configuration changes.

Build egress allows cluster DNS, peer build Pods, and public IPv4 destinations excluding private, link-local and reserved ranges. Cilium also explicitly denies node and Kubernetes API identities. There is no IPv6 egress allow rule. Builds cannot reach the Woodpecker control namespace or LAN services directly.

Peer communication is namespace-wide, not per workflow. Do not treat concurrent workflows as mutually isolated tenants. Builds can access public services, including publicly exposed home endpoints, through their public addresses. DNS is permitted and can be used for exfiltration. Only approve code you are willing to execute; this is not a sandbox for hostile code.

Privileged image building, image publishing and deployment credentials are out of scope. Ordinary images may run as container root under baseline policy; non-root execution is not forced on arbitrary pipeline images. Server and agent containers run as UID/GID 1000 with read-only root filesystems and dropped capabilities.

## Validation before enabling production repositories

Offline checks require the repo's `flux`, `helm`, `kustomize` and `yq` tools:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_woodpecker.py' -v
```

Set `WOODPECKER_CHART` to an unpacked chart 3.7.5 directory to include the Helm/post-rendering test. Without it, that test is explicitly skipped.

After reconciliation:

```bash
kubectl -n woodpecker get externalsecrets,helmreleases,pods,pvc
kubectl -n woodpecker-builds get networkpolicies,ciliumnetworkpolicies,resourcequotas,limitranges
kubectl -n woodpecker get replicationsources,replicationdestinations,cronjobs
```

Use a disposable repository before enabling real workloads:

- Confirm an external fork PR stays blocked, with no build Pods, until `igas` approves it. `WOODPECKER_DEFAULT_APPROVAL_MODE=forks` is a default for newly enabled repositories, not a permanent global override. Recheck repository settings after activation or restore.
- Run four workflows with at least two steps each and a test service. Verify each workflow's Pods share a node and workspace, and different workflows have different claims. The affinity uses Kubernetes `matchLabelKeys`, supported by the current Kubernetes 1.37 cluster.
- From a build, verify public HTTPS and cluster DNS work; LAN endpoints, the Kubernetes API, node addresses and other application Pods are unreachable. Verify workflow service access separately. Static manifest tests do not prove live Cilium enforcement.
- Verify no token is mounted at `/var/run/secrets/kubernetes.io/serviceaccount`.
- Verify a privileged step, host mount or resource limit above the ceiling is rejected.
- Complete a successful database backup and a restore into a disposable database. Do not claim recovery is verified merely because manifests rendered or `pg_restore --list` passed.

## Database backups

The `woodpecker-database-backup` CronJob runs at 01:00 `Australia/Sydney`, before the server-volume VolSync snapshot at 17:00 UTC. The dump job shares the server's node to mount its RWO PVC. It connects using only the Woodpecker database user's credentials, runs `pg_dump` in custom format, and checks the archive list before atomically replacing the latest dump.

Files on the `woodpecker` PVC:

- `/database-backups/woodpecker.dump`, the latest complete dump.
- `/database-backups/woodpecker.previous.dump`, the previous complete dump.
- `/database-backups/last-success`, a UTC completion timestamp.

Inside the server container, prepend `/var/lib/woodpecker` to those paths. Failed dumps leave the last complete archive intact. The 10Gi server volume must hold application state and both dumps; monitor space as build logs accumulate in PostgreSQL. There is no automatic database log archival.

VolSync sends server-volume snapshots, including completed dumps, to the existing Restic/S3 repository at `backups/woodpecker`. It retains 24 hourly, 7 daily and 5 weekly snapshots under the shared component's retention policy, though this application's snapshot schedule is daily. Temporary workspaces are never backed up. Agent registration identity has its own 1Gi PVC and is not backed up; an agent can register again using the preserved registration secret.

`WoodpeckerDatabaseBackupStale` alerts after 27 hours without a successful dump. Also verify VolSync's `lastSyncTime` and existing backup-failure alerts. A successful dump on Ceph is not an off-cluster backup until VolSync succeeds.

For a deliberate first backup after the server is healthy:

```bash
kubectl -n woodpecker create job --from=cronjob/woodpecker-database-backup woodpecker-database-backup-initial
kubectl -n woodpecker wait --for=condition=complete job/woodpecker-database-backup-initial --timeout=30m
kubectl -n woodpecker logs job/woodpecker-database-backup-initial
```

Do not overlap a manual job with the scheduled job. CronJob `concurrencyPolicy` does not serialize separately created manual jobs. Wait for the subsequent VolSync snapshot or trigger a backup deliberately after the dump completes.

## Recovery

1. Stop Woodpecker server and agents, suspend the dump CronJob and prevent Flux/Helm reconciliation from undoing the maintenance changes. Disable external build triggers during recovery.
2. Restore the `woodpecker` server PVC from the selected Restic snapshot through the existing VolSync `ReplicationDestination`. Preserve the 1Password OAuth, agent, gRPC and database credentials. Restore does not recreate the PostgreSQL database automatically.
3. With the server still stopped, create an **empty** target database owned by the Woodpecker user. For a drill, use a new database name rather than the live database. Run PostgreSQL 18 `pg_restore --exit-on-error --no-owner --no-acl --dbname=<target>` against `/database-backups/woodpecker.dump` on a maintenance Pod mounting the restored claim. Supply the database credentials through a Secret, not command-line password arguments. Do not overwrite the live database without an explicit recovery decision.
4. Validate schema/data in the restored database and the selected backup timestamp. Recheck repository owners, closed registration and fork approval settings before reconnecting the server to it. If using a drill database, leave production configuration untouched.
5. Resume the server, agent, CronJob and GitOps reconciliation. Confirm login, a test workflow, a fresh dump and an off-cluster VolSync backup.

This is daily logical backup recovery, not continuous WAL archiving or point-in-time recovery. Changes since the selected dump are lost. A restore drill remains required after provisioning.

## Sources and decisions

- [Community and official-source research](../research/woodpecker-ci.md)
- [Isolation and storage decision](../adr/0001-isolate-woodpecker-builds.md)
- [Upstream approval implementation at v3.19.0](https://github.com/woodpecker-ci/woodpecker/blob/v3.19.0/server/pipeline/gated.go)
