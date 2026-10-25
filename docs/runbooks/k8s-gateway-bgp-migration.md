# k8s-gateway BGP migration

DNS Service cutover and rollback for
[#828](https://github.com/igas/home-ops/issues/828).
Only k8s-gateway moves, from `192.168.6.8` to `192.168.100.8`, retaining UDP/53.
Its Service becomes BGP-only with `externalTrafficPolicy: Local`.
Repository preparation does not confirm deployment. UniFi DNS records stay unchanged.

## Verified cutover

Deployed on 2026-10-25 through Flux at revision `c2d9430` after operator
approval. The Service has `192.168.100.8`, the BGP label and `Local` policy.
Its ready endpoint is on `k8s-worker-02`, the only node advertising the new
`/32`; no node advertises the old `/32` and no gateway L2 lease remains.

The same LAN Mac passed all four BGP peer checks and all seven Service probes
before and after the move. DNS passed at the new IP; all six other Service
addresses, policies and ports were unchanged. Direct gateway, router and normal
system resolver queries returned `192.168.100.7` for Flux MCP, Gitea and Grafana.
Normal-resolver HTTPS requests returned 401 for Flux MCP and 200 for Gitea and
Grafana. The API hostname still resolves to the three masters. All 59 UniFi DNS
policies matched the pre-cutover snapshot exactly. These were CLI checks from
one LAN host, not manual browser or independent wired and Wi-Fi checks.

## DNS dependency discovery

The original ticket assumed UniFi forwarded `igas.dev` to k8s-gateway.
Read-only API and SSH inspection on 2026-10-25 disproved that assumption:

- The UniFi integration API returned 59 DNS policies, with no `FORWARD_DOMAIN`
  policy and no destination `192.168.6.8`.
- The active dnsmasq configurations in `/run/dnsmasq.dns.conf.d/` contain
  controller-managed CNAMEs to `internal.igas.dev` and `external.igas.dev`,
  with A records `192.168.100.7` and `192.168.100.6`. No `igas.dev` forwarder
  or reference to `192.168.6.8` was found in the inspected dnsmasq paths.
- The three `k8s.igas.dev` master A records are served locally by UniFi.
- This Mac uses `192.168.1.1` as its system resolver and no longer has
  `/etc/resolver/igas.dev`.

The operator approved preserving this DNS design. The forwarding criterion
in #828 is not applicable; neither create a forwarder nor edit generated
dnsmasq files. API access uses `UNIFI_API_KEY` from 1Password item `unifi` in
vault `kubernetes`; gateway SSH uses item `Ui SSH` in vault `Private`.
Keep credentials out of command output and repository files.

For later verification, list policies with
`GET /proxy/network/integration/v1/sites/88f7af54-98f8-306a-a1c7-c9349722b1f6/dns/policies`,
following pagination. Inspect active dnsmasq configurations over SSH if needed.
If a forwarder or another old-IP dependency appears before cutover, stop and
agree its coordinated migration rather than applying this Service-only plan.

## Before cutover

1. Confirm #821's wired and Wi-Fi canary gate and #827's internal gateway move
   passed. Keep both pools, legacy L2 selection and the persistent UniFi DSR
   policy in [lb-bgp-canary.md](lb-bgp-canary.md). That policy covers the Default
   LAN `192.168.0.0/20`, not IoT or VPN networks. DNS uses UDP; the earlier TCP
   canary is not proof that DNS works through this path.
2. Recheck the DNS dependency discovery above and record the absence of
   forwarding on #828. Preserve the external-dns-managed policies, local
   control-plane records and their existing management. No UniFi write is needed.
3. Save `task check-lb` output from the same Default LAN host used after the move.
   The 2026-10-25 preparation baseline passed all four BGP peers and all seven
   Services, with DNS at `192.168.6.8:53/UDP`. Refresh this baseline at cutover.
   Save the LoadBalancer Service addresses and policies too.
4. Record direct DNS and normal-resolver answers for `flux-mcp.igas.dev`,
   `gitea.igas.dev` and `grafana.igas.dev`. They should return `192.168.100.7`.
   Record `plex.igas.dev` as the LAN checker's UDP probe name as well.
   Inventory client-specific DNS overrides such as macOS
   `/etc/resolver/igas.dev`. A direct gateway override must be updated or removed
   with operator approval; moving the Service does not update it.
5. Keep a master-IP kubeconfig available if DNS fails. The control-plane
   endpoint and router's three master A records do not change. See
   [talos-control-plane-endpoint.md](talos-control-plane-endpoint.md).

## Cutover and verification

1. After deployment approval, deploy the `network/k8s-gateway` Flux Kustomization.
   The HelmRelease changes its Service annotation to
   `lbipam.cilium.io/ips: 192.168.100.8`, adds Service label
   `igas.dev/lb-pool: bgp`, and sets `externalTrafficPolicy: Local` together.
   Keep `domain`, `ttl`, watched resources and UDP port unchanged.
2. Keep UniFi DNS policies unchanged. Update any separately approved direct
   client overrides immediately after the new status IP is assigned. The
   router's normal DNS path does not depend on the moved IP.
3. Inspect the Service and ready endpoints:

   ```bash
   kubectl -n network get service k8s-gateway -o yaml
   kubectl -n network get endpointslices -l kubernetes.io/service-name=k8s-gateway -o yaml
   kubectl -n network get pods -l app.kubernetes.io/instance=k8s-gateway -o wide
   ```

   Require the new status IP, BGP label, `Local` policy and ready DNS endpoints.
   Follow [the advertisement checks](lb-bgp-canary.md#check-advertisement-and-l2-exclusion)
   on every Cilium agent. Only nodes with ready DNS endpoints may advertise
   `192.168.100.8/32`. All peers must remain established; no
   `cilium-l2announce-network-k8s-gateway` lease should remain after expiry.
4. From a LAN host, query the new DNS address, the router, and the normal resolver:

   ```bash
   for host in flux-mcp.igas.dev gitea.igas.dev grafana.igas.dev; do
     dig @192.168.100.8 "$host" A +notcp +ignore +time=2 +tries=1
     dig @192.168.1.1 "$host" A +notcp +ignore +time=2 +tries=1
     dig "$host" A +time=2 +tries=1
   done
   ```

   Require `NOERROR` and `192.168.100.7` for each query, not merely exit code 0.
   On macOS, `dig` does not exercise scoped system resolvers. Also run
   `dscacheutil -q host -a name gitea.igas.dev` and open Gitea in a browser using
   normal DNS. Retry after cache expiry or an operator-approved cache flush.
   Confirm `k8s.igas.dev` still resolves through the router to the three masters.
5. Run `task check-lb` from the baseline LAN host. Require
   `PASS Service network/k8s-gateway 192.168.100.8:53/UDP DNS NOERROR`.
   All other Service addresses, policies and results must match baseline;
   all four BGP peers and all seven Services must pass. Repeat normal-resolver
   checks from wired and Wi-Fi hosts where available.
6. Record the Service IP, BGP advertisements, L2 exclusion, the approved
   forwarding exception, DNS answers, host/network identity and before/after
   checker output on #828. Leave the ticket open until every acceptance check
   is confirmed. Keep both pools and the legacy L2 policy; cleanup is separate.

## Rollback

1. Revert only #828's configuration change and reconcile `network/k8s-gateway`
   through Flux. Restore `lbipam.cilium.io/ips: 192.168.6.8`, remove the Service's
   `igas.dev/lb-pool: bgp` label, and restore `externalTrafficPolicy: Cluster`.
   Do not roll back any other migrated Service or remove either pool.
2. Leave UniFi DNS unchanged, since no forwarding rule was changed or added.
   Restore any direct client overrides changed during cutover to their saved
   settings as soon as the old Service IP is assigned. If discovery found a
   forwarding dependency, use its separately agreed rollback instead.
3. Confirm withdrawal of `192.168.100.8/32`, legacy L2 eligibility and an active
   L2 lease for k8s-gateway. Keep the persistent UniFi policy needed by all other
   BGP Services. Query `@192.168.6.8`, the router and the host's normal resolver.
4. Repeat `task check-lb` and browser/system-resolver checks after cache expiry.
   Require DNS at the old IP and every other Service unchanged from baseline.
   Record the rollback and results on #828.
