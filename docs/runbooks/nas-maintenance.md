# NAS maintenance

Before updating or rebooting the NAS at `192.168.3.5`:

```bash
task nas:down                      # Alerts silenced for 2 hours
# Or: task nas:down DURATION=4h TIMEOUT=1200
```

Only proceed when the command succeeds and says it is safe to update. It does
not update or reboot the NAS itself.

The task saves state in `.private/nas-maintenance.json`, bound to the current
Kubernetes context and cluster UID. Keep that file until restoration succeeds.
The Task wrapper uses the repo's kubeconfig. Direct script calls use your
current kubeconfig.

## What stops

- All Flux Kustomizations and HelmReleases are temporarily suspended. Parent
  reconciliation must not undo maintenance changes. Other running applications
  continue operating, but GitOps changes wait until restoration.
- Deployments, StatefulSets and CronJobs with direct NAS NFS mounts or claims
  backed by NAS NFS are stopped or suspended. This includes Plex, Sonarr,
  Radarr, qBittorrent, Qui and Autopulse in the current configuration.
- Autobrr, Kometa and Recyclarr in `default` are also stopped or suspended
  because they call the affected services.
- The VolSync controller is scaled to zero because its S3 repository lives on
  the NAS. Existing backup jobs are allowed to finish, not deleted.

Scheduled jobs drain while their dependent APIs are still running. The task
then stops consumers and waits for their pods to stop. It refuses to report success
if reconciliation is still running or a job or pod remains after `TIMEOUT`
seconds. Investigate those resources before proceeding. A failed backup job is
not proof that backups are healthy; inspect failures before starting maintenance.

Temporary Alertmanager silences match the NAS IP, affected endpoint names,
workload labels and VolSync alerts. They do not silence the whole cluster.
Silences do not stop applications recording errors, or suppress notifications
sent outside Alertmanager. Alerts with unrelated labels are not covered.

## Restore

After the NAS returns, verify that its NFS exports and S3 service are healthy:

```bash
task nas:up
```

This restores the recorded replica counts, waits for workloads to roll out,
then restores VolSync, CronJob suspension and Flux suspension. Resources that
were already suspended stay suspended. Maintenance silences are expired only
after restoration succeeds, and the state file is removed.

If either command fails, keep the state file. Retry `nas:down` to finish the
shutdown and renew silences, or `nas:up` to restore the saved state. Once a
restore has started, only retry `nas:up`. A failed restore keeps the state and
remaining silences so it can be retried. Do not run these commands concurrently
from another checkout or machine; the lock only covers this local state file.

For a longer maintenance window, rerun `task nas:down DURATION=4h` before the
existing silences expire. Every shutdown attempt adds fresh silences and keeps
their IDs for cleanup. Avoid manual changes to managed resources during the
window because restoration uses the settings recorded at its start.

The discovery covers the repo's NAS address and `nfs-slow` storage class.
Workloads using other NAS addresses, protocols, or external API dependencies
need to be added to discovery before relying on this task for them.
