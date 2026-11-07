# spegel

## 0.7 to 0.8 removes the hostPort

The 0.8 chart ignores `service.registry.hostPort`. It replaces the host listener and the second mirror target with a NodePort Service using `trafficDistribution: PreferSameNode`. Review the generated mirror targets as well as the Service ports. This repo's old override is 29999; the new default NodePort is 30020.

[onedr0p/home-ops#11885](https://github.com/onedr0p/home-ops/pull/11885/files) removed that override and added Cilium `loadBalancer.serviceTopology: true` in the same PR. His successful upgrade is not precedent for an unchanged Cilium configuration. Check support in the installed Cilium version and the live topology setting before suggesting that value.

Read both app releases, 0.8.0 and 0.8.1. The latter also changes how mirror configuration removes conflicting hosts. Bootstrap `01-apps.yaml` reads the HelmRelease values; `00-crds.yaml` does not render Spegel. The chart has no values schema, so stale keys do not fail rendering.

## Recipe gap

As of the #859 review, there is no validated single-Pod preflight for the node-local NodePort/PreferSameNode path on this cluster. Do not run the chart's configuration init container against a host mount during merge-check: it rewrites node containerd configuration. A successful Helm render does not close this runtime verification gap. Hold until the migration and a bounded verification procedure are reviewed.
