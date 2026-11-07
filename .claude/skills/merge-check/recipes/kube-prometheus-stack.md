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
