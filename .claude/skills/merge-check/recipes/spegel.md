# spegel

## 0.7 to 0.8 removes the hostPort

The 0.8 chart ignores `service.registry.hostPort`. It replaces the host listener and the second mirror target with a NodePort Service using `trafficDistribution: PreferSameNode`. Review the generated mirror targets as well as the Service ports. This repo's old override is 29999; the new default NodePort is 30020.

[onedr0p/home-ops#11885](https://github.com/onedr0p/home-ops/pull/11885/files) removed that override and added Cilium `loadBalancer.serviceTopology: true` in the same PR. His successful upgrade is not precedent for an unchanged Cilium configuration. Check support in the installed Cilium version and the live topology setting before suggesting that value.

Read both app releases, 0.8.0 and 0.8.1. The latter also changes how mirror configuration removes conflicting hosts. Bootstrap `01-apps.yaml` reads the HelmRelease values; `00-crds.yaml` does not render Spegel. The chart has no values schema, so stale keys do not fail rendering.

For Cilium, check tagged implementation as well as the Helm option. In `pkg/loadbalancer/reflectors/conversions.go`, v1.18.6 recognizes `PreferClose`, not `PreferSameNode`. The v1.20.4 implementation recognizes `PreferSameNode`, and `pkg/loadbalancer/writer/writer.go` gates same-node filtering on `EnableServiceTopology`. Enabling the Helm value alone on an older release does not establish support. Review a supported Cilium upgrade path separately.

## Startup checks and metrics

Spegel 0.8.1 calls `Containerd.Validate` before starting the registry. The tagged `pkg/oci/containerd/containerd.go` requires Containerd 2.2 or later and runs the additional exported configuration checks only on Containerd 2.4 or later. Read node runtime versions instead of equating the bundled Go client version with a required daemon version. On 2026-11-07 all four nodes ran Containerd 2.3.7, so the minimum was satisfied and the 2.4 introspection branch did not apply. The repo also configures `discard_unpacked_layers = false` and the Talos-specific registry path.

The 0.8 release replaces the three `spegel_advertised_images`, `spegel_advertised_image_tags` and `spegel_advertised_image_digests` metrics with `spegel_advertised_keys`, without a registry label. Check custom dashboards and alerts even when the removed bundled dashboard was disabled. Upstream #1570 reports zero response-size metrics on 0.8.0; the 0.8.1 `pkg/httpx/mux.go` diff and tests contain the response-writer fix. Report #1530 concerns advertisement filtering, so check actual filter settings before treating it as a new deployment blocker.

## Recipe gap

As of the #859 review, there is no validated single-Pod preflight for the node-local NodePort/PreferSameNode path on this cluster. Do not run the chart's configuration init container against a host mount during merge-check: it rewrites node containerd configuration. A successful Helm render does not close this runtime verification gap. Hold until the migration and a bounded verification procedure are reviewed.

## Completed operational migration

The operator-approved #859 rollout completed on 2026-11-07 after the staged Cilium upgrades in #921, #924 and #933. Cilium 1.20.4 had service topology enabled and selected the local backend on 32/32 isolated host-to-NodePort checks. Spegel now uses an explicit NodePort 30020; the obsolete hostPort value is removed. Read-only Talos API checks confirmed the new local mirror endpoint on all four nodes. Treat the 0.7-to-0.8 migration findings above as historical prerequisites, not an unresolved blocker for later 0.8 patch releases.

The operational pull check used an image absent from all nodes, a donor Pod on master-01 and a receiver Pod on master-02. Before creating the receiver, confirm its runtime image inventory is still missing the image and sample that node's Spegel metrics. After the pull, require the same donor/receiver image digest and an increase in `spegel_mirror_requests_total` with the test registry and `cache="hit"`; a Ready Pod alone can indicate upstream fallback. On #859 the receiver recorded 12 hits and zero misses without a Spegel Pod restart. The [deployment comment](https://github.com/igas/home-ops/pull/859#issuecomment-6701047989) records the evidence. Temporary test resources were removed. This was an explicitly authorized operational rollout with multiple Pods, not a single-Pod merge-check preflight.
