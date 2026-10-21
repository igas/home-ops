# Reboot a Talos node

Use the task rather than calling `talosctl reboot` directly:

```bash
mise install
mise exec -- kubectl cnpg version
mise exec -- kubectl cnpg status postgres-18 -n database
task talos:reboot-node IP=192.168.6.12
```

The task checks Ceph health, then discovers CNPG clusters across all namespaces.
For each primary on the target node, it selects a Running, Ready, non-terminating
replica on another node and runs:

```bash
kubectl cnpg promote <cluster> <replica> --namespace <namespace>
```

Before rebooting, it waits until the cluster's `currentPrimary` and `targetPrimary`
both name the selected replica and its phase is `Cluster in healthy state`.
It then creates Alertmanager silences, sets Ceph `noout`, and reboots. After the
node and Ceph recover, it removes `noout` and expires the silences.

Immediately before reboot, it refreshes primary placement. If any primary has
moved onto the target node or cannot be located, it aborts. Inspect the clusters
before retrying. This check cannot prevent a concurrent promotion after the read,
so do not run other database maintenance during the reboot.

The task aborts before reboot if discovery or promotion fails, no eligible replica
exists, or the cluster does not recover within the script's timeout, 1800 seconds
by default. `FORCE=true` only bypasses the Ceph health precheck. It does not bypass
the CNPG safeguard. If a switchover succeeds but a later step fails, the new primary
stays primary. Inspect the cluster before retrying. Run one node reboot at a time.

## Verify a planned switchover

During the next planned reboot of a node hosting the primary, watch CNPG events
in a second terminal:

```bash
kubectl get events -n database --watch \
  --field-selector involvedObject.kind=Cluster,involvedObject.name=postgres-18
```

Confirm the operator emits `Switchover`, not `FailingOver`. Afterward, check:

```bash
kubectl cnpg status postgres-18 -n database
```

The primary should be on another node and the status should be
`Cluster in healthy state`. Offline tests check command ordering and failure
handling, but cannot verify real operator events.

## Keep the plugin and operator aligned

The plugin is pinned in `.mise.toml`. Renovate looks up its releases in
`cloudnative-pg/cloudnative-pg` and opens a PR without auto-merging it.
The operator version comes from the chart selected in
`kubernetes/apps/database/cloudnative-pg/app/ocirepository.yaml`, not an explicit
operator image pin. Chart and operator version numbers are different.

Review plugin and chart updates together. Check the chart's `appVersion` and
prefer the exact same plugin version. Never allow more than one minor version
of drift. When upgrading the chart, also check `.mise.toml`, even if Renovate has
not opened a plugin PR yet. After reconciliation, verify the deployed version:

```bash
kubectl -n database get deployment cloudnative-pg \
  -o jsonpath='{.spec.template.spec.containers[*].image}'
kubectl cnpg version
```

See the [CNPG plugin documentation](https://cloudnative-pg.io/docs/1.30/kubectl-plugin)
for promotion and status commands.
