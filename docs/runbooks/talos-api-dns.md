# Talos API DNS checks

`k8s.igas.dev` is a LAN-only name served by the router at `192.168.1.1`.
It must return `192.168.6.1`, `192.168.6.2`, and `192.168.6.3`.
The persistent node resolver configuration is `talos/patches/network/dns.yaml`.
Do not add a public fallback unless it can return the same API records.
`NXDOMAIN` is a DNS answer, not a transport failure that triggers another lookup.

There are two resolver paths to check. Talos host DNS is used by node services.
Talos v1.14.3's normal `talosctl upgrade` and `reboot --drain=true` instead run
cordon/drain in the CLI process on the operator workstation. Passing a host
probe does not establish that this caller can reach the API.

## Initial host DNS finding, 2026-10-18

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

The host configuration error was mixing split-horizon and public DNS upstreams.
Talos v1.14.3 `internal/pkg/dns/handler.go` tries another upstream on transport
errors, SERVFAIL or REFUSED, but accepts NXDOMAIN. Removing `1.1.1.1` prevents
that public negative answer from entering the host cache. This does not provide
DNS redundancy: the router remains a single point of failure. A second upstream
must serve the same LAN records before it can be added safely. This fix does not
depend on the k8s-gateway migration in #828.

## Drain caller finding, 2026-11-06

During later master-02 maintenance, the host probe passed but
`talosctl reboot --drain=true` still failed before reboot with:

```text
error cordoning node: failed to get node k8s-master-02:
Get https://k8s.igas.dev:6443/api/v1/nodes/k8s-master-02:
dial tcp: lookup k8s.igas.dev: no such host
```

The earlier attribution of this message to node-side DNS was wrong.
In Talos v1.14.3, `cmd/talosctl/cmd/talos/drain.go` fetches an admin kubeconfig
from the Talos API through `kubeclient.FromTalosClient`, then runs
`nodedrain.CordonAndDrain` locally. This uses the workstation resolver and the
fetched config's `https://k8s.igas.dev:6443` endpoint. An operator kubeconfig
using a master IP can work while this separate client fails. The normal upgrade
path installs first, then calls this same local drain code before rebooting.
The legacy upgrade path is different.

The workstation had a separate `/etc/resolver/igas.dev` override pointing at
k8s-gateway, documented during #825. That resolver does not serve the API name.
The operator confirmed that the override was removed after the failed drain.
On this investigation's baseline, `/etc/resolver` was already empty,
`scutil --dns` selected `192.168.1.1`, and `dscacheutil` returned all three
masters. Direct queries still distinguished the DNS ownership boundary:

```sh
dig @192.168.100.8 k8s.igas.dev A +noall +comments +answer
# NXDOMAIN from k8s-gateway
dig @192.168.1.1 k8s.igas.dev A +noall +comments +answer
# NOERROR; 192.168.6.1, 192.168.6.2, 192.168.6.3, TTL 60
```

The persistent workstation fix is to use the router's LAN DNS instead of a
domain-wide override to k8s-gateway. That OS configuration is not managed by
this repo and was already corrected by the operator. No workstation settings
were changed during this investigation. The old CLI failure no longer
reproduces; the source trace and resolver history explain the discrepancy,
but no packet capture of that failed maintenance call exists. The retained
Talos host NXDOMAIN logs establish a separate host-side defect, not the source
of the CLI's lookup error.

Do not restore the override just to reproduce a failure. On another affected
Mac, inspect `scutil --dns` and the domain override before changing it. Back up
the override and remove only the confirmed stale entry with operator approval.
Do not change the API endpoint, disable TLS validation, or force a different
resolver with `GODEBUG` to make the regression check pass.

## Regression checks

```sh
task talos:render-check
python3 -m unittest discover -s scripts/tests -p test_talos_api_check.py -v
task talos:check-api
# Run check-api again after at least 60 seconds to cross the A-record TTL.
# To distinguish a failing boundary:
task talos:check-client-api IP=192.168.6.2
task talos:check-host-api
```

The render check uses throwaway secrets and checks every generated node's
ResolverConfig for the LAN-only upstream list. It failed before the DNS patch
and passed afterwards. CI already runs this script for Talos changes.

`check-api` checks the workstation first, then all Talos hosts.
`check-client-api` fetches a fresh admin kubeconfig through Talos, trying another
configured control-plane node if the first fetch fails. It does not merge the
download into the operator config. It requires the DNS endpoint and cluster CA with
TLS verification, then GETs the configured nodes from the workstation with
`kubectl`'s Go/client-go client. No server, TLS-name, or DNS override is used.
The admin config is held in a private temporary directory with a mode-0600
file and removed when the check exits. Do not terminate it with SIGKILL, which
can prevent cleanup. Credential-fetch error output is suppressed.

This exercises the failing caller's DNS endpoint, credentials and node GET
boundary, but is not the talosctl drain implementation itself. The two binaries
may use different Go resolver builds. It does not PATCH the node or evict pods.
`upgrade-node` and `reboot-node` run this preflight before staging an upgrade,
switching database primaries, or setting maintenance flags and silences. A
failure stops the task. Direct `talosctl` invocations bypass this safeguard.

The separate host check starts short-lived Talos debug containers, not workload pods.
Talos debug uses the host network namespace and host resolv.conf. The script
uses `getaddrinfo` without specifying a DNS server and requires exactly the
three intended control-plane addresses. It then GETs that node through
`https://k8s.igas.dev:6443` with the node's kubelet client certificate and
cluster CA. Certificate verification and hostname validation stay enabled.
Credentials remain on the node; no credential values are printed.
Each node must emit a completion marker. A zero `talosctl debug` exit status
alone is insufficient because some stream failures do not set a nonzero status.

This checks host DNS, TLS and kubelet-authenticated node reads without changing
scheduling. It does not cover the CLI drain caller's admin credentials or
workstation resolver. The host check deliberately dials the DNS endpoint rather
than KubePrism, which can mask a host resolver failure. Neither check tests PATCH,
eviction, PodDisruptionBudgets, or a complete drain. Do not upgrade or reboot
solely to test DNS.

Talos debug containers are privileged and mount the host filesystem. Run only
the checked-in probe with trusted images and admin credentials. A registry pull
failure is a check failure, not evidence of an API DNS failure.

References:

- [Talos host DNS](https://docs.siderolabs.com/talos/v1.14/networking/host-dns)
- [DNS upstream handling](https://github.com/siderolabs/talos/blob/v1.14.3/internal/pkg/dns/handler.go)
- [Debug host networking and resolv.conf](https://github.com/siderolabs/talos/blob/v1.14.3/internal/app/debug/debug.go)
- [Drain client](https://github.com/siderolabs/talos/blob/v1.14.3/internal/app/machined/pkg/runtime/v1alpha1/v1alpha1_sequencer_tasks.go)
- [CLI drain caller](https://github.com/siderolabs/talos/blob/v1.14.3/cmd/talosctl/cmd/talos/drain.go)
- [CLI admin kubeconfig client](https://github.com/siderolabs/talos/blob/v1.14.3/cmd/talosctl/pkg/talos/kubeclient/kubeclient.go)
- [Normal upgrade ordering](https://github.com/siderolabs/talos/blob/v1.14.3/cmd/talosctl/cmd/talos/upgrade.go)

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

The workstation/preflight change needs no Talos apply. To roll back the new
checks, remove the `check-client-api` calls from `check-api`, `upgrade-node` and
`scripts/talos-reboot-node.sh`; retain `check-host-api` and the existing LAN-only
node resolver patch. Removing a guard does not fix DNS. Restoring the stale
workstation override can reintroduce the drain failure and is not a useful
rollback. If an unrelated client depends on it, arrange a resolver that serves
both sets of names before restoring domain-wide routing.

## Verification evidence, 2026-10-18

After apply, every node reported `ResolverStatus ["192.168.1.1"]` and one
healthy `DNSUpstream`, `192.168.1.1:53`. All four Kubernetes nodes were Ready.
The live probe returned the three master addresses and a TLS-authenticated node
GET on each node, with `unschedulable=False` before and after the change.
No cordon, drain, OS upgrade, reboot, or CoreDNS restart was performed.

Remaining human action: confirm a complete cordon/drain at the next planned
maintenance, restoring each node's original scheduling state. No extra
maintenance is required for this DNS-only change.

## Verification evidence, 2026-11-06

- All four live ResolverStatus resources listed only `192.168.1.1`.
- `task talos:check-api` passed on all four nodes. Each host resolved exactly
  `192.168.6.1`, `.2`, `.3` through its actual host resolver and completed a
  CA-verified kubelet node GET. Workstation admin node GETs through the fetched
  DNS-endpoint kubeconfig passed on all four nodes too.
- Both checks reported `unschedulable=False` for every node. All nodes were Ready.
- Offline CLI tests reproduced `lookup k8s.igas.dev: no such host` and proved
  that this error blocks reboot maintenance before CNPG promotion, Ceph changes
  or alert silences, even if the operator kubeconfig uses an IP endpoint.

No cordon, drain, upgrade, reboot or live config apply was performed. The
previously failing initial node GET now succeeds through the caller-side
preflight; complete Talos cordon/drain remains unverified. At the next planned
maintenance, record the original scheduling state, run both checks, then use
the normal Talos drain path and verify recovery. Restore the recorded state
afterward, not an unconditional uncordon of a previously cordoned node. Leave
#860 open until that maintenance evidence is recorded.
