# gatus

StatefulSet `observability/gatus` (app-template), one replica. The `ghcr.io/twin/gatus` image tag is pinned in `kubernetes/apps/observability/gatus/app/helmrelease.yaml`; `gatus-sidecar` runs as a native sidecar (init container, `restartPolicy: Always`) and has its own image bumps.

## Settings that decide which release notes matter

- Config: `kubernetes/apps/observability/gatus/app/resources/config.yaml`. Storage is `sqlite` with `caching: true` at `/config/gatus.db` on a 5Gi `ceph-block` PVC. Notes about postgres skip us; a `modernc.org/sqlite` bump in `go.mod` touches us (SQLite is backward compatible on disk, so a driver bump alone is not a risk).
- No `alerting:` block, so alert provider changes (Zulip, ntfy, Home Assistant, …) skip us.
- Read the exact PR-head endpoint file. It now includes ICMP, direct LoadBalancer TCP checks and a DNS query, plus a `connectivity.checker` on `1.1.1.1:53`. The sidecar adds HTTP endpoints from Services and HTTPRoutes, so `client/` and condition-parsing changes do touch us.
- Probes hit `/health` on port 80.

## Release notes

Release bodies omit dependency bumps. Read the commit range for `go.mod` changes:

```
gh api repos/TwiN/gatus/compare/vOLD...vNEW --jq '.commits[].commit.message | split("\n")[0]'
```

## Precedent

onedr0p no longer pins `ghcr.io/twin/gatus` directly. He runs the `ghcr.io/home-operations/charts/gatus-sidecar` chart (`kubernetes/apps/o11y/gatus-sidecar/`) with its default `gatus.image.tag`. To find which gatus a chart release bundles:

```
helm pull oci://ghcr.io/home-operations/charts/gatus-sidecar --version <v> --untar
grep -A6 '^gatus:' gatus-sidecar/values.yaml
```

A merged chart bump whose bundled tag and digest match the PR counts as precedent.

## gatus-sidecar bumps

The `ghcr.io/home-operations/gatus-sidecar` repo ships the binary and the `gatus-sidecar` chart from one tree, so most of each release is chart, CI, and tooling noise. Only Go source, `go.mod`, and the `Dockerfile` reach the image we run:

```
gh api repos/home-operations/gatus-sidecar/compare/OLD...NEW --jq '.files[] | "\(.status) \(.filename)"'
```

A changelog line that bumps `ghcr.io/twin/gatus` changes only the chart's default; we pin gatus separately in the HelmRelease.

Precedent: the sidecar chart's `sidecar.image.digest` in `values.yaml` (same `helm pull` as above) is the digest the release pipeline pinned. A match with the PR's digest makes onedr0p's chart bump direct precedent.

Sidecar 0.6.0 changes `guarded` inside endpoint templates: boolean false or null now disables the inherited DNS-only guard; a quoted string "false" still enables it. This is separate from the `gatus.home-operations.com/enabled: "false"` annotation. Inspect Gateway parent templates and route overrides before treating the breaking note as applicable. On #862 no affected guarded override existed; chart 0.6.0's sidecar digest matched the image PR exactly.

For the separate Gatus 5.38.0 bump, chart 0.6.0 still bundled Gatus 5.37.0. That chart merge is not target-version precedent. Gatus 5.38 validates DNS/SSH/external maintenance windows earlier, but the reviewed endpoint config had no maintenance windows. SQLite remained at modernc.org/sqlite 1.59.0; the dependency bumps were AWS/OIDC/gRPC rather than a storage-driver migration.

Sidecar 0.6.1 changes Kubernetes/Gateway API client dependencies as well as chart defaults. The 0.6.0 to 0.6.1 comparison changes no non-test Go implementation or Dockerfile. An older 0.6.0 verdict is still stale when Renovate advances the image; review the dependency rebuild and do not describe chart-default Gatus changes as an additional app upgrade here.

## Verify endpoint preservation after a sidecar rollout

Capture the endpoint keys and group counts before merging with the read-only API proxy:

```sh
kubectl get --raw /api/v1/namespaces/observability/services/gatus:80/proxy/api/v1/endpoints/statuses
```

After the desired image reaches the StatefulSet, wait for its rollout and HelmRelease readiness, then compare every endpoint key and group count. Check each latest result's timestamp is after the new app container started; SQLite history alone is not proof the new process checked an endpoint. Read sidecar startup logs for informer synchronization and endpoint updates. On #862 at 0.6.1, all 31 keys survived with connectivity 3, external 5 and services 23, and all had fresh results. The external Woodpecker check failed both before and after; record baseline failures separately from upgrade regressions.
