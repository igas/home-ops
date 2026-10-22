# BGP-only LoadBalancer canary

Gate for [#821](https://github.com/igas/home-ops/issues/821), before any real
Service moves in #820. Existing Service IPs and traffic policies do not change.

## Preconditions

- Confirm `192.168.100.0/24` against every UniFi network, DHCP range and route.
  Record evidence on #821 before applying the pool. The 2026-10-22 API inspection
  found no overlap. Recheck if the network configuration changes.
- Have a wired and a Wi-Fi host on the Default LAN `192.168.0.0/20`.
  A VPN host in `192.168.16.0/24` does not qualify.
- Run `task check-lb` on the wired host and save its complete output as the
  baseline. Existing failures are not a passing baseline, but must not increase
  during this expand step. Record every pre-existing failure explicitly.

## Apply the expand configuration

Reconcile the `kube-system/cilium` Flux Kustomization after merging the pool
change. Do not change BGP configuration or Cilium's DSR mode.

The Service label `igas.dev/lb-pool: bgp` selects the new `bgp` pool and excludes
the Service from both the old `pool` and L2 announcements. Unlabeled Services
remain eligible only for the old pool and L2. A later move must change both the
Service label and `lbipam.cilium.io/ips` annotation together.

```bash
kubectl get ciliumloadbalancerippools
kubectl apply --dry-run=server -f docs/runbooks/manifests/lb-bgp-canary.yaml
kubectl apply -f docs/runbooks/manifests/lb-bgp-canary.yaml
kubectl -n lb-bgp-canary rollout status deployment/canary --timeout=120s
kubectl -n lb-bgp-canary get service canary -o wide
kubectl -n lb-bgp-canary get pods -o wide
kubectl -n lb-bgp-canary get endpointslices -l kubernetes.io/service-name=canary -o yaml
```

The Service must have `192.168.100.254`, `externalTrafficPolicy: Local`, and
exactly one ready endpoint on one node. The manifest is deliberately outside
Flux, so the canary cannot return after manual cleanup.

## Check advertisement and L2 exclusion

```bash
kubectl -n kube-system get pods -l k8s-app=cilium -o wide
kubectl -n kube-system get leases | grep cilium-l2announce
```

There must be no `cilium-l2announce-lb-bgp-canary-canary` lease. Inspect **every**
Cilium agent, replacing `AGENT_POD` below with each pod name:

```bash
kubectl -n kube-system exec AGENT_POD -c cilium-agent -- cilium-dbg bgp peers
kubectl -n kube-system exec AGENT_POD -c cilium-agent -- cilium-dbg bgp routes advertised ipv4 unicast
```

All peers must be established. Only the agent on the node with the ready canary
endpoint may advertise `192.168.100.254/32`. There must be no aggregate route for
the new pool. Record the per-node results on #821.

## Exercise the LAN return path

Run `task check-lb` from both LAN hosts. Then run this sustained probe on each
host. It checks one response on one TCP connection, not repeated handshakes.
The server sends 60 chunks over about 30 seconds. The declared content length
makes an interrupted transfer fail.

```bash
python3 - <<'PY'
import hashlib
import time
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
start = time.monotonic()
with opener.open("http://192.168.100.254:8080/stream", timeout=40) as response:
    body = response.read()
elapsed = time.monotonic() - start
assert len(body) == 3932160, f"incomplete response: {len(body)} bytes"
assert hashlib.sha256(body).hexdigest() == "5add149c531b5c93ca4a70384b174a738f10d80c19fb55de502b15947e836e3b"
assert 28 <= elapsed < 40, f"unexpected transfer duration: {elapsed:.1f}s"
print(f"PASS: {len(body)} bytes in {elapsed:.1f}s on one TCP connection")
PY
```

Confirm the canary logs show each LAN client's real source IP:

```bash
kubectl -n lb-bgp-canary logs deployment/canary
```

Record each host's IP, wired/Wi-Fi connection, checker output and transfer result.
Compare the real Services' addresses and results with the baseline. Their IPs
must not change, and there must be no new failures.

If the connection or transfer fails, stop. Record the failure on #821 before
any move ticket starts. Investigate the router's route and firewall state. If
DSR's asymmetric return path is blocked, the choices are a gateway firewall
rule or SNAT for affected Services. Neither change belongs in this canary step.

## Cleanup and rollback

After both hosts pass, remove the canary and rerun `task check-lb` on the baseline
host. Confirm its route is withdrawn from every agent and no canary lease exists.

```bash
kubectl delete -f docs/runbooks/manifests/lb-bgp-canary.yaml
```

If testing must pause, leave the canary only with an explicit note on #821 that
#821 owns its removal and that the migration gate remains pending.

To roll back the expand step:

1. Remove the canary first. Confirm no real Service uses the new range.
2. Revert only #821's configuration commit, then reconcile `kube-system/cilium`.
   Flux restores the original legacy pool and unfiltered L2 policy and prunes
   the `bgp` pool. No existing Service annotation needs changing in this ticket.
3. For a pre-merge manual apply, restore the `pool` and `l2-policy` specs from
   the pre-change revision, then delete `ciliumloadbalancerippool/bgp`.
4. Rerun `task check-lb` from the same LAN host. Compare against the saved
   baseline, including its pre-existing failures.

Do not close #821 or start a Service move while either host's test, advertisement
inspection, cleanup, or the baseline comparison remains unverified.
