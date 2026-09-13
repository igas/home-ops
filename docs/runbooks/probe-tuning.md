# Tuning liveness, readiness and startup probes

Written for issue #741, the Plex self-kill after the Talos 1.14 rollout rebooted
k8s-worker-02 on 2026-09-13. The values chosen for Plex are the template for the
other apps that share the same probe shape (issue #742), so this records the
reasoning rather than only the numbers.

## What went wrong

Plex was SIGKILLed 66 seconds after starting: exit 137, `reason: Error`, not
`OOMKilled` (~240Mi against a 16Gi limit). Its liveness probe was:

```yaml
initialDelaySeconds: 0
periodSeconds: 10
timeoutSeconds: 1
failureThreshold: 3
```

Three `/identity` responses slower than one second, roughly 30 seconds apart,
restart the container. A cold Plex warming its library off freshly-remounted
Ceph RBD answers slowly for minutes. It is alive the whole time.

Two separate mistakes produced that. The liveness timeout could not tell slow
from hung. And the startup probe, which is supposed to hold liveness off until
the container can actually serve, was app-template's default `tcpSocket` check.
That passes the moment Plex binds 32400, long before the library is warm, so
liveness took over within seconds of the process starting.

## The rules

The three probes answer different questions, and the cost of a false positive
differs wildly between them:

- **Readiness** pulls the Pod from the Service. A false positive costs a few
  seconds of traffic. It should fail fast, because a warming Plex should not be
  serving.
- **Liveness** restarts the container, discarding all warmup progress. A false
  positive costs the whole startup again, and on a slow backing store it can
  loop. It should fire only on a process that is hung, not merely slow.
- **Startup** decides when the other two begin. It has to gate on the same
  signal liveness will judge, or liveness inherits a container that was never
  really ready. A `tcpSocket` probe in front of an `httpGet` liveness is the bug
  that caused this incident.

Liveness and readiness must not share one YAML anchor. `liveness: &probes` /
`readiness: *probes` is the pattern that produced this across the repo; split
it.

## The values

| Probe | period | timeout | failureThreshold | Budget |
| --- | --- | --- | --- | --- |
| startup | 10s | 10s | 60 | 600s to answer `/identity` once |
| liveness | 30s | 10s | 5 | 150s hung before restart |
| readiness | 10s | 1s | 3 | ~30s slow before leaving the Service |

All three now `httpGet /identity`. The numbers come from three constraints:

- `timeoutSeconds: 10` on startup and liveness is the line between slow and
  hung. A warming Plex answers `/identity` in seconds; a wedged one does not
  answer at all. Ten seconds is comfortably past the former and still far short
  of a stall.
- Startup's `10s × 60 = 600s` is the warmup allowance. Liveness does not run at
  all until Plex has served one `/identity`, or until ten minutes have passed
  and the container is restarted as failed-to-start. That is the change that
  actually fixes the incident; the liveness tuning is the second line of
  defence.
- Liveness's `30s × 5 = 150s` is the unresponsiveness a genuinely hung process
  buys before the restart. Long enough that a burst of RBD latency cannot
  accumulate five strikes, short enough that a wedged media server is back
  inside a few minutes.

`initialDelaySeconds` is 0 everywhere because startup already gates the first
liveness and readiness checks.

Readiness keeps the original numbers on purpose. Failing fast there is correct,
and it is what keeps a warming Plex out of the Service while liveness leaves it
alone.

## Applying this to other apps

Issue #742 covers the rollout. These apps still share one anchor between
liveness and readiness, and most also carry the default `tcpSocket` startup
probe:

- `network/cloudflare-tunnel`
- `default/qbittorrent`, `default/echo`, `default/prowlarr`, `default/radarr`,
  `default/qui`, `default/sonarr`
- `observability/gatus`

Use the table above as the default. Raise the startup or liveness budget further
only for an app whose warmup is known to be slower than Plex's, and say why in a
comment next to the probe.

## Verifying

Render the change before pushing:

```bash
yq '.spec.values' kubernetes/apps/default/plex/app/helmrelease.yaml \
  | helm template plex oci://ghcr.io/bjw-s-labs/helm/app-template \
      --version 5.1.0 -n default -f - \
  | yq 'select(.kind=="Deployment") | .spec.template.spec.containers[]
        | {"live": .livenessProbe, "ready": .readinessProbe, "startup": .startupProbe}'
```

Then exercise the real path, a reschedule onto a cold mount, and confirm the new
Pod reaches Ready with no restarts. k8s-worker-02 is the only worker, so check
first that Plex's GPU ResourceClaim has somewhere else to land before draining
it:

```bash
kubectl drain k8s-worker-02 --ignore-daemonsets --delete-emptydir-data
kubectl -n default get pod -l app.kubernetes.io/name=plex -w
kubectl -n default get pod -l app.kubernetes.io/name=plex \
  -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
kubectl uncordon k8s-worker-02
```

`restartCount` must be `0`.
