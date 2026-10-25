# k8s-gateway BGP migration

Coordinated DNS cutover and rollback for
[#828](https://github.com/igas/home-ops/issues/828).
Only k8s-gateway moves, from `192.168.6.8` to `192.168.100.8`, retaining UDP/53.
Its Service becomes BGP-only with `externalTrafficPolicy: Local`.
Repository preparation does not confirm deployment or the UniFi change.

## Before cutover

1. Confirm #821's wired and Wi-Fi canary gate and #827's internal gateway move
   passed. Keep both pools, legacy L2 selection and the persistent UniFi DSR
   policy in [lb-bgp-canary.md](lb-bgp-canary.md). That policy covers the Default
   LAN `192.168.0.0/20`, not IoT or VPN networks. DNS uses UDP; the earlier TCP
   canary is not proof that DNS works through this path.
2. Have the operator open UniFi Network at `https://192.168.1.1/network` and
   locate the existing `igas.dev` DNS forwarding rule. UI paths vary by version.
   Record its rule identity, domain, enabled state, old destination and any
   additional forwarders on #828. Confirm the current destination is
   `192.168.6.8`, save the rollback settings, and keep the edit ready. Preserve
   every setting except the destination IP. Do not deploy unattended.
3. Save `task check-lb` output from the same Default LAN host used after the move.
   The 2026-10-25 preparation baseline passed all four BGP peers and all seven
   Services, with DNS at `192.168.6.8:53/UDP`. Refresh this baseline at cutover.
   Save the LoadBalancer Service addresses and policies too.
4. Record direct DNS and normal-resolver answers for `flux-mcp.igas.dev`,
   `gitea.igas.dev` and `grafana.igas.dev`. They should return `192.168.100.7`.
   Record `plex.igas.dev` as the LAN checker's UDP probe name as well.
   Inventory client-specific DNS overrides such as macOS
   `/etc/resolver/igas.dev`. A direct gateway override must be updated or removed
   with operator approval; changing UniFi does not update it.
5. Keep a master-IP kubeconfig available if DNS fails. The control-plane
   endpoint and router's three master A records do not change. See
   [talos-control-plane-endpoint.md](talos-control-plane-endpoint.md).

## Cutover and verification

1. With the operator ready, deploy the `network/k8s-gateway` Flux Kustomization.
   The HelmRelease changes its Service annotation to
   `lbipam.cilium.io/ips: 192.168.100.8`, adds Service label
   `igas.dev/lb-pool: bgp`, and sets `externalTrafficPolicy: Local` together.
   Keep `domain`, `ttl`, watched resources and UDP port unchanged.
2. As soon as the Service has the new status IP, the operator must immediately
   change the existing UniFi `igas.dev` forwarding destination to
   `192.168.100.8`, save, and read the rule back. Record the timestamp, rule
   identity, destination and explicit operator confirmation on #828. Do not
   delay the forwarding change until after the remaining cluster diagnostics.
   These two systems cannot change atomically. Minimize the interval where the
   old destination is dead; if the new DNS path fails, roll both settings back.
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
6. Record the Service IP, BGP advertisements, L2 exclusion, UniFi read-back and
   operator confirmation, DNS answers, host/network identity and before/after
   checker output on #828. Leave the ticket open until every acceptance check
   is confirmed. Keep both pools and the legacy L2 policy; cleanup is separate.

## Rollback

1. Revert only #828's configuration change and reconcile `network/k8s-gateway`
   through Flux. Restore `lbipam.cilium.io/ips: 192.168.6.8`, remove the Service's
   `igas.dev/lb-pool: bgp` label, and restore `externalTrafficPolicy: Cluster`.
   Do not roll back any other migrated Service or remove either pool.
2. As soon as the old Service IP is assigned, immediately restore UniFi's
   `igas.dev` forwarding destination to `192.168.6.8` from the saved settings.
   Read the rule back and record operator confirmation on #828. Restore any
   changed client overrides too. The repository revert alone does not restore
   UniFi forwarding.
3. Confirm withdrawal of `192.168.100.8/32`, legacy L2 eligibility and an active
   L2 lease for k8s-gateway. Keep the persistent UniFi policy needed by all other
   BGP Services. Query `@192.168.6.8`, the router and the host's normal resolver.
4. Repeat `task check-lb` and browser/system-resolver checks after cache expiry.
   Require DNS at the old IP and every other Service unchanged from baseline.
   Record the rollback and results on #828.
