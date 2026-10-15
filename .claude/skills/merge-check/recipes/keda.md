# keda

HelmRelease `observability/keda`, chart `oci://ghcr.io/home-operations/charts-mirror/keda` (chart version = appVersion). Also pinned in `bootstrap/helmfile.d/00-crds.yaml`, so every bump touches both files. onedr0p dropped KEDA in onedr0p/home-ops#10788 (2026-04), so there is no precedent after 2.19.0.

## Settings that decide which release notes matter

- One consumer: ScaledObject `default/zigbee`, `minReplicaCount: 0`, `maxReplicaCount: 1`, one `prometheus` trigger against in-cluster Prometheus with **no authentication**.
- No ScaledJobs, no TriggerAuthentication or ClusterTriggerAuthentication, no Vault, no `boundServiceAccountToken`. Check this hasn't changed: `kubectl get scaledobjects,scaledjobs,triggerauthentications,clustertriggerauthentications -A`.
- So notes about cloud scalers, auth providers and ScaledJob strategies skip us. Notes that do matter: the Prometheus scaler, scale-to-zero/activation (`minReplicaCount: 0`), the polling loop, ScaledObject conditions, and the metrics-apiserver ↔ operator gRPC link.

## Explaining the flux-local diff

The HelmRelease sets only the `prometheus.*` ServiceMonitor values, so new chart defaults land straight in the Deployments. Render both versions with our values and diff the non-CRD objects. A match with the flux-local diff means every line is explained:

```
yq '.spec.values' kubernetes/apps/observability/keda/app/helmrelease.yaml > values.yaml
helm template keda <chart-dir> -n observability -f values.yaml
```

Rendering without `-f` also proves the `00-crds.yaml` no-values render passes `values.schema.json`, which ships from 2.21.0 onward.

## Since 2.21.0

The chart defaults to `operator.serviceAccountTokens.mode: enforce-audience` and mounts an unused projected token (audience `vault`) at `/var/run/secrets/keda-vault`. We need no migration while we have no Vault or BSAT auth. Setting `hashiCorpVault.kubernetesAuth.audience: ""` drops the mount.

## Cluster state gotcha

Graceful node shutdown leaves `Completed` pods from the current ReplicaSet behind, which look like failed replicas. Judge health from the Deployments, the HelmRelease, and `kubectl get scaledobject -n default zigbee` (Ready/Active/HPAActive).
