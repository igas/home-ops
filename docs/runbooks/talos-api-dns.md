# Talos API DNS checks

`k8s.igas.dev` is a LAN-only name served by the router at `192.168.1.1`.
It must return `192.168.6.1`, `192.168.6.2`, and `192.168.6.3`.
The persistent node resolver configuration is `talos/patches/network/dns.yaml`.
Do not add a public fallback unless it can return the same API records.
`NXDOMAIN` is a DNS answer, not a transport failure that triggers another lookup.

## Diagnosis of #860

On 2026-10-18, master-01's retained `dns-resolve-cache` log recorded queries
for both A and AAAA at `09:51:08.124Z` sent to `1.1.1.1:53`. Responses at
`09:51:08.142Z` and `09:51:08.151Z` were `NXDOMAIN` for `k8s.igas.dev`.
Its controller-runtime log then reported:

```text
09:51:16.339Z k8s.StaticEndpointController:
error resolving "k8s.igas.dev": lookup k8s.igas.dev on 127.0.0.53:53: no such host
09:51:16.732Z k8s.EndpointController:
Get "https://k8s.igas.dev:6443/apis/discovery.k8s.io/v1/namespaces/default/endpointslices?...":
dial tcp: lookup k8s.igas.dev on 127.0.0.53:53: no such host
```

A repeatable, non-disruptive reproduction at the selected upstream boundary:

```sh
export TALOSCONFIG="$PWD/talos/clusterconfig/talosconfig"
talosctl -n 192.168.6.2 debug docker.io/library/busybox:1.37.0 \
  --args nslookup,k8s.igas.dev,1.1.1.1
# server can't find k8s.igas.dev: NXDOMAIN; container exits 1
talosctl -n 192.168.6.2 debug docker.io/library/busybox:1.37.0 \
  --args nslookup,k8s.igas.dev,192.168.1.1
# returns all three masters
```

Normal host lookups passed during investigation, including a 150-query loop on
worker-02 spanning more than two 60-second A-record TTLs. The failure is not
continuous. The retained logs prove that the actual host cache selected the
incompatible upstream and returned the reported error. They are from the boot
after maintenance, not the original pre-reboot upgrade attempt. Why the LAN
resolver was unavailable or skipped at that moment remains unconfirmed.

The configuration error was mixing split-horizon and public DNS upstreams.
Talos v1.14.3 `internal/pkg/dns/handler.go` tries another upstream on transport
errors, SERVFAIL or REFUSED, but accepts NXDOMAIN. Removing `1.1.1.1` prevents
that public negative answer from entering the host cache. This does not provide
DNS redundancy: the router remains a single point of failure. A second upstream
must serve the same LAN records before it can be added safely. This fix does not
depend on the k8s-gateway migration in #828.

## Regression checks

```sh
task talos:render-check
task talos:check-api
# Run check-api again after at least 60 seconds to cross the A-record TTL.
```

The render check uses throwaway secrets and checks every generated node's
ResolverConfig for the LAN-only upstream list. It failed before the DNS patch
and passed afterwards. CI already runs this script for Talos changes.

The live check starts short-lived Talos debug containers, not workload pods.
Talos debug uses the host network namespace and host resolv.conf. The script
uses `getaddrinfo` without specifying a DNS server and requires exactly the
three intended control-plane addresses. It then GETs that node through
`https://k8s.igas.dev:6443` with the node's kubelet client certificate and
cluster CA. Certificate verification and hostname validation stay enabled.
Credentials remain on the node; no credential values are printed.

This checks the DNS, TLS, authentication and node-read prerequisites of
cordon/drain without changing scheduling. It does not test PATCH, eviction,
PodDisruptionBudgets, or a complete drain. Talos v1.14.3's
`NewClientFromKubeletKubeconfig` uses the same kubelet credentials for draining.
The check deliberately dials the DNS endpoint rather than KubePrism, which can
mask this failure. Do not upgrade or reboot solely to test DNS.

Talos debug containers are privileged and mount the host filesystem. Run only
the checked-in probe with trusted images and admin credentials. A registry pull
failure is a check failure, not evidence of an API DNS failure.

References:

- [Talos host DNS](https://docs.siderolabs.com/talos/v1.14/networking/host-dns)
- [DNS upstream handling](https://github.com/siderolabs/talos/blob/v1.14.3/internal/pkg/dns/handler.go)
- [Debug host networking and resolv.conf](https://github.com/siderolabs/talos/blob/v1.14.3/internal/app/debug/debug.go)
- [Drain client](https://github.com/siderolabs/talos/blob/v1.14.3/internal/app/machined/pkg/runtime/v1alpha1/v1alpha1_sequencer_tasks.go)

## Apply and rollback

The DNS change was applied to all four nodes on 2026-10-18 with
`apply-config --mode no-reboot`, replacing only the ResolverConfig nameservers
in a copy of each node's live `machineconfig v1alpha1`. Dry-run diffs showed only
removal of `1.1.1.1`. The endpoint, SANs, issuer/audience lists and hostDNS
settings were unchanged. Do not use a plain `patch mc` with the shortened
nameserver list: strategic merge appends entries instead of removing them.

For future deployment, generate configs and inspect the diff before applying:

```sh
task talos:generate-config
task talos:apply-node IP=192.168.6.1 MODE=no-reboot
# Repeat for .2, .3 and .12 after checking each node.
task talos:check-api
```

If unrelated changes appear, stop rather than applying them with this fix.
Live config contains secrets. Use private temporary files with `umask 077` and
delete them afterwards. Select `get mc v1alpha1` explicitly: listing all mc
resources can return multiple configurations. Suppress failed validation output
because Talos can include secret fields in decoding errors.

Rollback by restoring `1.1.1.1` in the owning patch, regenerating and applying
with `MODE=no-reboot` one node at a time. Revert the render assertion in the
same rollback. This restores the known DNS failure risk and is only appropriate
if the router-only configuration causes a worse outage. No endpoint or issuer
rollback is needed.

## Verification evidence, 2026-10-18

After apply, every node reported `ResolverStatus ["192.168.1.1"]` and one
healthy `DNSUpstream`, `192.168.1.1:53`. All four Kubernetes nodes were Ready.
The live probe returned the three master addresses and a TLS-authenticated node
GET on each node, with `unschedulable=False` before and after the change.
No cordon, drain, OS upgrade, reboot, or CoreDNS restart was performed.

Remaining human action: confirm a complete cordon/drain at the next planned
maintenance, restoring each node's original scheduling state. No extra
maintenance is required for this DNS-only change.
