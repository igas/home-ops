# descheduler

Deployment `kube-system/descheduler` from the `ghcr.io/home-operations/charts-mirror/descheduler` chart (tag in `kubernetes/apps/kube-system/descheduler/app/ocirepository.yaml`). Layer 2. Chart version equals appVersion, so one Renovate bump moves both. The chart is not in `bootstrap/helmfile.d`.

Descheduler 0.x minors track Kubernetes minors (0.37 ↔ k8s 1.37, bumped in the upstream "release prep" PR). A descheduler minor *ahead* of the cluster's Kubernetes minor is a finding: compare with `kubectl version`.

## Review

- The chart has no `values.schema.json`. Diff `values.yaml` and `templates/` between the two pulled charts. New chart features have so far all been opt-in and off by default.
- Our policy is `deschedulerPolicyAPIVersion: descheduler/v1alpha2` with custom `pluginConfig`. Look for plugin renames, arg renames, and changes to `DefaultEvictor.podProtections` in the release notes.
- RBAC changes show up in the flux-local diff as ClusterRole edits. Eviction only needs `pods/eviction: create`. 0.37.0 dropped the unused `pods: delete` ([#1888](https://github.com/kubernetes-sigs/descheduler/pull/1888)).

## Rollout risk

Leader election is on with 1 replica and RollingUpdate (25% surge). The pod has a liveness probe (`/healthz` on 10258, HTTPS) and **no readiness probe**, so the [leader-elected-controllers](leader-elected-controllers.md) deadlock does not apply unless a bump adds a readiness probe. Check with:

```
kubectl get deploy -n kube-system descheduler -o jsonpath='{.spec.template.spec.containers[0].readinessProbe}'
helm history -n kube-system descheduler   # earlier upgrades with this same setup went through cleanly
```

## Cluster notes

A `Completed` descheduler pod can linger on a node after a graceful node shutdown. It is harmless, and RemoveFailedPods does not touch it because it only handles failed pods.
