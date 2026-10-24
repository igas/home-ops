# BGP-only LoadBalancer canary

Gate for [#821](https://github.com/igas/home-ops/issues/821), before any real
Service moves in #820. Existing Service IPs and traffic policies do not change.

## Preconditions

- Confirm `192.168.100.0/24` against every UniFi network, DHCP range and route.
  Record evidence on #821 before applying the pool. The 2026-10-22 API inspection
  found no overlap. Recheck if the network configuration changes.
- Have a wired and a Wi-Fi host on the Default LAN `192.168.0.0/20`.
  A VPN host in `192.168.16.0/24` does not qualify.
- Confirm the controller-managed UniFi policy below is enabled and ordered
  before `Block Invalid Traffic`. Raw SSH-added iptables rules are not a
  persistent substitute.
- Run `task check-lb` on the wired host and save its complete output as the
  baseline. Existing failures are not a passing baseline, but must not increase
  during this expand step. Record every pre-existing failure explicitly.

## UniFi policy for DSR

The 2026-10-24 wired and Wi-Fi tests confirmed a gateway firewall failure.
Clients sent the initial connection packet through the gateway, but the node
replied directly to the client. The gateway kept the connection in
`SYN_SENT [UNREPLIED]` and dropped the client's acknowledgement and HTTP data.
Both hosts passed with a temporary scoped allow rule, then failed again when
that rule was removed.

The persistent fix is the UniFi Network policy `Allow LAN to BGP LoadBalancers`.
Its request body is recorded in
[`manifests/unifi-lan-bgp-policy.json`](manifests/unifi-lan-bgp-policy.json).
This file records the desired configuration. Flux does not apply it.

| Setting | Value |
| --- | --- |
| Site ID | `88f7af54-98f8-306a-a1c7-c9349722b1f6` |
| Policy ID | `2cb78313-3ef4-42ca-bea9-9a150b516267` |
| Source | Internal zone, IPv4 `192.168.0.0/20` |
| Destination | External zone, IPv4 `192.168.100.0/24` |
| Action | Allow TCP and UDP, all ports within that destination pool |
| Connection states | All, including invalid |
| Order | Before the built-in `Block Invalid Traffic` policy |
| Automatic reverse-zone policy | Disabled |

The destination uses the External zone because UniFi does not include the
BGP-only pool in its local network-zone sets. This does not send the traffic
to the Internet. The BGP route still forwards it to the serving node on `br0`.
Do not create an on-link VLAN or DHCP network for this range to change its zone.

The source CIDR excludes the IoT and VPN networks. IPv6, ICMP and other protocols
are not covered. No Internet-facing inbound permission was added. The global
invalid-packet drop remains enabled for other traffic. Matching all connection
states is intentional. Restricting this allow policy to new or established
connections would not fix the asymmetric DSR flow.

The policy was created through the documented UniFi Network integration API,
not by editing gateway firewall rules. The relevant endpoints, relative to
`https://192.168.1.1/proxy/network/integration/v1`, are:

- `GET /sites/{siteId}/firewall/policies/{policyId}` to inspect it.
- `POST /sites/{siteId}/firewall/policies` with the recorded JSON to recreate it,
  only after confirming no policy with this name exists.
- `GET` or `PUT /sites/{siteId}/firewall/policies/ordering` with query parameters
  `sourceFirewallZoneId` and `destinationFirewallZoneId` to inspect or set order.
  The policy ID must be in `orderedFirewallPolicyIds.beforeSystemDefined`.
  Preserve all existing policy IDs and their relative order.
- `DELETE /sites/{siteId}/firewall/policies/{policyId}` to remove this policy only.

The API key is in the `UNIFI_API_KEY` field of 1Password item
`w7rd7gdnoemjaunneg4jyhglsm`. Never put the key in this repository or captured
command output. If recreating the policy, record its new ID here and on #821.

In the UniFi UI, inspect the Internal-to-External zone pair in the Policy Table.
Verify the name, source and destination CIDRs, IPv4 TCP/UDP match and ordering.
On the gateway, `iptables -t filter -S UBIOS_LAN_WAN_USER` must show the
controller-generated TCP and UDP accepts before the invalid-state drop.
Do not persist the diagnostic `lb821-test-*` rules from the earlier experiment.

Both hosts passed the full stream under this controller-managed policy on
2026-10-24. Each received 3,932,160 bytes with the expected checksum in about
29.5 seconds. The server logged both real client IPs. This proves the tested
TCP path, not every UDP application or access from a different source network.

References:
- [UniFi zone-based firewall configuration and ordering](https://help.ui.com/hc/en-us/articles/115003173168-Zone-Based-Firewalls-in-UniFi)
- [UniFi Network create-firewall-policy API](https://developer.ui.com/network/v10.1.84/createfirewallpolicy)

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
any move ticket starts. Investigate the router's route, policy ordering and
firewall state. The scoped UniFi policy above fixes the observed DSR failure
with operator approval. Do not disable invalid filtering globally or switch
Cilium to SNAT without a separate decision and a repeat of both LAN tests.

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
4. Remove only `Allow LAN to BGP LoadBalancers` through the UniFi Policy Table or
   its policy-specific API DELETE endpoint. Do this only after no real Service
   uses the new range. Removing it while Services use the pool restores the
   observed LAN connection failure. Do not remove the built-in invalid drop.
5. Rerun `task check-lb` from the same LAN host. Compare against the saved
   baseline, including its pre-existing failures.

Normal canary cleanup does not remove the persistent UniFi policy. It must
remain enabled for later Service moves that use this DSR network path.

Do not close #821 or start a Service move while either host's test, advertisement
inspection, cleanup, or the baseline comparison remains unverified.
