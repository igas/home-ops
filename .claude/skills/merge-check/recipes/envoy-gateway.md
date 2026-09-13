# envoy-gateway

Chart `gateway-helm` from `mirror.gcr.io/envoyproxy`; also rendered with no values by `bootstrap/helmfile.d/00-crds.yaml`. Provider mode here is `deploy.type: GatewayNamespace`. Reviewed 2026-09-13 on PR #640 (v1.8.3 → v1.9.1).

## What a chart bump really changes

1. **Data-plane image.** The EnvoyProxy CR in `kubernetes/apps/network/envoy-gateway/app/envoy.yaml` overrides only `imageRepository`; tag and digest come from the controller's default (`api/v1alpha1/shared_types.go` at the new tag). Every proxy pod rolls on merge. Note the new Envoy version in the comment.
2. **Gateway API CRDs.** The chart bundles them under `charts/crds/crds/`. flux-local omits CRDs from its diff, so compare yourself: `yq` the bundle's `gateways.gateway.networking.k8s.io` versions against `kubectl get crd ... -o json | jq .spec.versions` (md5 both). Live CRDs matched the running chart on 2026-09-13, so CRD upgrades are applied here; re-check after merge that `bundle-version` moved.
3. **Policy validation tightening.** Check `ClientTrafficPolicy.clientIPDetection` (exactly one of `xForwardedFor`/`customHeader`/`directSourceIP` from 1.9), `SecurityPolicy` fields, and `BackendTrafficPolicy.mergeType` against `envoy.yaml`.

## Known rollout behaviour

- **JWT expiry wedge**: after a controller restart, proxies may pin stale xDS pod IPs and return 503 while the controller logs `service account token has expired`. Fix: rollout-restart `envoy-gateway`, then the proxy Deployments.
- **SDS cold-start race** ([envoyproxy/gateway#9918](https://github.com/envoyproxy/gateway/issues/9918)): readiness does not wait for certificates, so a mass proxy roll can serve TLS handshake errors until every pod has fetched SDS. Self-clears; merge when nobody is streaming.
- **Infra runner does not retry** ([#10000](https://github.com/envoyproxy/gateway/issues/10000)): a Gateway stuck `Programmed=False` after a transient error recovers with a controller restart.

## Health gate

Both Gateways `Programmed=True`, proxies 2/2 each, `kubectl -n network logs deploy/envoy-gateway --tail=300 | grep -i error` empty.
