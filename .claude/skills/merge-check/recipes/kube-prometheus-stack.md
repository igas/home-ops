# kube-prometheus-stack

## Effective apps differ from chart defaults

Read Chart.yaml appVersion for the Prometheus Operator and inspect changed bundled apps separately. This repo pins Prometheus to Prompp and disables bundled Grafana. Default Prometheus/Grafana image changes therefore do not describe the running upgrade.

Use the exact PR-head HelmRelease when the checkout and live pin differ. On #893 the checkout had Prompp 0.8.16, but both the PR head and live release used 0.8.17. That was checkout staleness, not cluster drift. Re-render with the exact head values before writing the verdict.

The later 92.17.0 target advances the disabled Grafana subchart to 14.3.0. Its new repository sidecar is opt-in. kube-state-metrics 8.6.0 → 8.8.0 and node-exporter 4.60.0 → 4.60.1 keep the same app images here; their kube-rbac-proxy defaults change only if those proxy containers are enabled. Compare rendered image lists before calling a subchart version change an app upgrade.

## Bootstrap and admission certificates

`bootstrap/helmfile.d/00-crds.yaml` renders this chart without values for CRDs. Check the no-values `helm template --include-crds --no-hooks` path as well as the repo overrides.

Chart 92.13 changes admission certificates from an Opaque Secret with ca/cert/key to kubernetes.io/tls with ca.crt/tls.crt/tls.key. The hook receives a secret-type argument and deletion RBAC. Read its compatibility notes and the existing Secret's type/key names without printing certificate/key data. Preserve the documented legacy-entry behavior when assessing conversion. Do not run the hook or mutate the Secret during merge-check.

## Alertmanager CORS

App 0.34.2 stops sending CORS headers by default. `--web.cors.origin` can restore cross-origin browser access. Same-origin UI access and in-cluster non-browser API callers are different cases; inspect consumers rather than enabling wildcard CORS. Security-fix requests such as alertmanager#5691 do not prove that all requested advisories are fixed by this release.

Read #5691's comments as well as its body. Maintainers say the BusyBox CVEs are not fixed by 0.34.2. They also document an initial image-publication failure and later repair. Verify availability at the exact registry used by the chart, not just the GitHub release or a successful pull from a different registry. On 2026-11-01 the Quay v0.34.2 manifest returned HTTP 200 and included linux/amd64; no candidate process was started.

## Alertmanager 0.35 delivery regression

[Alertmanager #5743](https://github.com/prometheus/alertmanager/issues/5743) reports dropped alert POST batches when the new 90-second HTTP idle timeout races the sender's resend cadence. For a target containing that change:

1. Read the live `/api/v1/status/flags` value for `rules.alert.resend-delay` and the effective configuration's evaluation interval. The combination of a one-minute resend delay and a 30-second evaluation interval can send long-firing alerts every 90 seconds because the resend comparison is strictly `Before`.
2. Check the actual sender implementation. Prompp v0.8.19 retains that comparison in `rules/alerting.go` and uses prometheus/common v0.60.0, whose HTTP client keeps idle connections for five minutes. Its source is [deckhouse/prompp](https://github.com/deckhouse/prompp), despite the `prompp/prompp` image name.
3. Check the target Alertmanager's `app/app.go` timeout and the issue's resolution. In #960, v0.35.0 still set `IdleTimeout: 90 * time.Second`, and the live settings matched the report.

This is a recurring alert-delivery risk after rollout. A healthy Pod, successful render or brief recovery does not resolve it under the accepted downtime budget. The report's 45-second resend-delay workaround was not validated here. A bounded repeated-POST/keep-alive check using the exact client and candidate remains a recipe gap. Keep test alerts and credentials isolated from production notification receivers if developing that preflight.

[Review #960](https://github.com/igas/home-ops/pull/960#issuecomment-6888535167) held chart 93.3.0 for this risk. Retaining `alertmanager.alertmanagerSpec.image.tag: v0.34.2` is a proposed way to separate the chart/operator upgrade from Alertmanager; the chart derives `spec.version` from that tag unless explicitly overridden. Re-review the resulting diff.

## Operator 0.95 applicability checks

- The new `alertmanagerConfigFileSystemMode` default follows the matcher strategy. Inspect Secret selectors versus filesystem references and whether each AlertmanagerConfig is the referenced global configuration. The CRD description misnames the strategy field in places; `pkg/alertmanager/operator.go` uses `AlertmanagerConfigMatcherStrategy.Type`. Our global Pushover configuration uses Secret selectors and keeps its `ttl: 86400s`; 0.95 fixes TTL conversion.
- Operator 0.95.1 had broken non-amd64 image publication. 0.95.2 fixes it. Check the operator and config-reloader manifests at the configured registry, as both can block rollout.
- Check actual StatefulSet owner UIDs, deletion timestamps and replica counts alongside CR status. Issues [#8960](https://github.com/prometheus-operator/prometheus-operator/issues/8960) and [#8982](https://github.com/prometheus-operator/prometheus-operator/issues/8982) describe misleading availability after CR deletion/recreation. An ordinary in-place upgrade does not establish that scenario.
- The operator's config-reloader image change can restart Prompp even when its application image is pinned. Include that workload in recovery checks.
- Inspect the live HelmRelease CRD policy before prescribing manual CRD updates. At #960, Flux already used `CreateReplace` for install and upgrade; the candidate no-values bootstrap render produced all ten monitoring CRDs.
