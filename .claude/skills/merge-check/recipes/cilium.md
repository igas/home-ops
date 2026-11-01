# cilium

## Upgrade one minor at a time

The [1.19](https://docs.cilium.io/en/v1.19/operations/upgrade/) and [1.20](https://docs.cilium.io/en/v1.20/operations/upgrade/) guides support consecutive-minor upgrades only and require the latest current-series patch first. #910 proposed 1.18.6 directly to 1.20.4. A passing render and onedr0p's 1.20.3 to 1.20.4 merge do not validate that skipped-minor path. Review staged 1.18, 1.19 and 1.20 rollouts separately.

## Case-sensitive values and effective configuration

The key is `cgroup.autoMount.enabled`, not `cgroup.automount.enabled`. Both charts in #910 silently accepted the lowercase spelling and still rendered the privileged mount-cgroup init container. [onedr0p #11970](https://github.com/onedr0p/home-ops/pull/11970) fixes the same typo. Compare the rendered init containers when correcting it on Talos. `localRedirectPolicy` remains a working deprecated alias in 1.20; prefer `localRedirectPolicies.enabled` when cleaning it up.

## Spegel topology dependency

1.20 adds PreferSameNode/PreferSameZone support, but `loadBalancer.serviceTopology` defaults false. The target render still disables it unless explicitly overridden. See [spegel.md](spegel.md) before combining this change with the hostPort-removal migration. The Cilium bump alone does not unblock Spegel.

## Policies and CNI compatibility

Compare live policy and BGP resources with both minor upgrade guides. 1.19 removes BGPv1 and FromRequires/ToRequires, changes DNS double-wildcard matching and disables legacy mesh authentication by default. 1.20 removes CiliumNodeConfig v2alpha1 and Kafka/proxylib, defaults CNI configuration to 1.0.0, and changes pod-to-NodePort policy evaluation with host-namespace-only SocketLB. This repo chains Multus, uses native routing, DSR, BGPv2 and `socketLB.hostNamespaceOnly: true`; disabled Cilium Gateway API is distinct from the separate Envoy Gateway installation.

## Recipe gap

No bounded single-Pod procedure validates the staged upgrade, chained CNI, DSR and BGP reachability. Upstream's preflight installs a DaemonSet and Deployment, outside merge-check's write allowance. Report the gap rather than installing them. Read target-version issues against the effective DSR dispatch/acceleration settings; a Geneve/XDP report is not proof that the default opt/disabled configuration reproduces it.
