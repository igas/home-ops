# envoy-gateway

Chart `gateway-helm` from `mirror.gcr.io/envoyproxy`; also rendered with no values by `bootstrap/helmfile.d/00-crds.yaml`. Provider mode here is `deploy.type: GatewayNamespace`. Reviewed 2026-09-13 on PR #640 (v1.8.3 → v1.9.1).

## What a chart bump really changes

1. **Data-plane image.** The EnvoyProxy CR in `kubernetes/apps/network/envoy-gateway/app/envoy.yaml` overrides only `imageRepository`; tag and digest come from the controller's default (`api/v1alpha1/shared_types.go` at the new tag). Every proxy pod rolls on merge. Note the new Envoy version in the comment.
2. **Gateway API CRDs.** The chart bundles them under `charts/crds/crds/`. flux-local omits CRDs from its diff, so compare yourself: `yq` the bundle's `gateways.gateway.networking.k8s.io` versions against `kubectl get crd ... -o json | jq .spec.versions` (md5 both). Live CRDs matched the running chart on 2026-09-13, so CRD upgrades are applied here; re-check after merge that `bundle-version` moved.
3. **Policy validation tightening.** Check `ClientTrafficPolicy.clientIPDetection` (exactly one of `xForwardedFor`/`customHeader`/`directSourceIP` from 1.9), `SecurityPolicy` fields, and `BackendTrafficPolicy.mergeType` against `envoy.yaml`.

## Known rollout behaviour

- **JWT expiry wedge**: after a controller restart, proxies may pin stale xDS pod IPs and return 503 while the controller logs `service account token has expired`. Fix: rollout-restart `envoy-gateway`, then the proxy Deployments.
- **SDS readiness gap** ([envoyproxy/gateway#9918](https://github.com/envoyproxy/gateway/issues/9918)): read the later corrections, not just the original cold-start explanation. A changed SDS config-source shape can starve a new provider on a warm proxy; recovery is not guaranteed without a secret push or proxy restart. Compare `makeConfigSource()` between the actual tags. It is identical in v1.9.3 and v1.10.0, so that specific shape-change trigger was not found in PR #930. Verify real TLS traffic after a rollout rather than relying only on readiness.
- **Infra runner does not retry** ([#10000](https://github.com/envoyproxy/gateway/issues/10000)): a Gateway stuck `Programmed=False` after a transient error recovers with a controller restart.

## Health gate

Both Gateways `Programmed=True`, proxies 2/2 each, `kubectl -n network logs deploy/envoy-gateway --tail=300 | grep -i error` empty.

## v1.10 review findings

Reviewed 2026-11-09 on PR #930, v1.9.3 to v1.10.0.

- The controller default moves the data plane from `distroless-v1.39.5` to `distroless-v1.40.2`, digest `sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded`. Read the Envoy changelogs too. Version 1.40 changes connection-drain notification and proactive closure of long-lived connections; 1.40.2 corrects the distroless CA bundle for the eMudhra compromise.
- Both chart artifacts bundle the same Gateway API v1.6.1 CRDs. Live schemas matched the old chart, including all Envoy extension CRDs. Flux uses `CreateReplace` for install and upgrade. The seven changed extension schemas need review even though CI omits them. The v1.10 guide's Gateway API v1.6 prerequisite is already satisfied here.
- Chart values add only optional control-plane `deployment.pod.initContainers` and `extraContainers`, plus the image bump. Neither artifact has `values.schema.json`. The target renders with the exact PR HelmRelease values and with no values, as the bootstrap Helmfile requires.
- `BackendTrafficPolicy.compression` still works in 1.10 but is scheduled for removal in 1.11. A future migration to `compressor` must include `brotli: {}` and `gzip: {}` beside their respective types. Type-only entries are silently ignored, including on 1.10, per [#9870](https://github.com/envoyproxy/gateway/issues/9870). Do not mechanically rename the key.

## Long-drain recipe gap

Risk: the shutdown manager can wait longer than its HTTP write deadline and fail to return a valid `/shutdown/ready` response during a proxy rollout.

[envoyproxy/gateway#10562](https://github.com/envoyproxy/gateway/issues/10562) reproduces an empty response when the marker arrives after 20 seconds. [#10563](https://github.com/envoyproxy/gateway/pull/10563) merged on 2026-11-08, after v1.10.0 was released. The exact v1.10.0 source still sets `WriteTimeout: 10 * time.Second` without extending the handler deadline. v1.9.3 has the same behavior, so this is not a newly introduced regression. The report establishes a failed HTTP response, not proof that connections terminate early.

This cluster uses a 180-second drain, `--ready-timeout=190s`, and a 480-second termination grace period. A healthy running Pod does not test this shutdown path. There is no validated bounded single-Pod procedure here for delayed-marker responses and long-lived connections across the old/new image transition. Record this as a recipe gap, not as a passed preflight. A future procedure must use fresh labels, no production Services, Secrets, service account or controller ownership, and clean up its single throwaway Pod. Do not trigger shutdown or restart production proxies as a merge-check experiment.

On 2026-11-09 the operator explicitly approved merging PR #930 despite this downtime-only gap. Apply the accepted downtime budget in [the merge-check skill](../SKILL.md#accepted-downtime-budget). The approval does not establish a measured recovery time or a passed preflight. Check actual HTTPS service recovery after rollout; Pod readiness alone is insufficient.
