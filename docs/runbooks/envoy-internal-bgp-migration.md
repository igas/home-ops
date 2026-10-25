# Internal Envoy gateway BGP migration

Cutover and rollback for [#827](https://github.com/igas/home-ops/issues/827).
Only envoy-internal moves, from `192.168.6.7` to `192.168.100.7`.
Ports 80/TCP, 443/TCP and 443/UDP remain unchanged.

## Before cutover

- Confirm #821's wired and Wi-Fi canary gate passed. Keep both pools, the
  legacy L2 policy and the persistent UniFi policy in
  [lb-bgp-canary.md](lb-bgp-canary.md). That policy covers the Default LAN
  `192.168.0.0/20`, not other VLANs or VPN clients.
- Save `task check-lb` output from a LAN host. The 2026-10-25 agent baseline
  passed for envoy-internal and every other Service except kube-api at
  `192.168.6.9:6443`, which refused connections. All four BGP peers were
  established. This baseline is not fully green.
- Record DNS answers and browser access for `flux-mcp.igas.dev`,
  `gitea.igas.dev` and `grafana.igas.dev`. Flux MCP requires an API key;
  an unauthenticated 401 is expected, not proof that authenticated MCP works.
- Keep `task flux-mcp` available to bypass the gateway during recovery.
  No UniFi DNS forwarding change belongs to #827. For the DNS Service
  move in #828 and its deployment status, see
  [k8s-gateway-bgp-migration.md](k8s-gateway-bgp-migration.md).

## Cutover and verification

1. Deploy the envoy-gateway Kustomization through Flux. The internal Gateway's
   infrastructure sets `lbipam.cilium.io/ips: 192.168.100.7` and
   `igas.dev/lb-pool: bgp` on the generated Service. Its Gateway-specific
   EnvoyProxy merges `externalTrafficPolicy: Local` with the shared
   GatewayClass configuration. Leave envoy-external and the shared proxy
   defaults unchanged.
2. Confirm the Gateway is Accepted and Programmed, its status address is
   `192.168.100.7`, and the generated Service has that address, label and
   `Local` policy:

   ```bash
   kubectl -n network get gateway envoy-internal -o yaml
   kubectl -n network get service -l gateway.envoyproxy.io/owning-gateway-name=envoy-internal -o yaml
   kubectl -n network get endpointslices -l kubernetes.io/service-name=envoy-internal -o yaml
   kubectl -n network get pods -l gateway.envoyproxy.io/owning-gateway-name=envoy-internal -o wide
   ```

   Follow [the canary advertisement checks](lb-bgp-canary.md#check-advertisement-and-l2-exclusion)
   to confirm only nodes with ready internal Envoy endpoints advertise
   `192.168.100.7/32`, and no internal Envoy L2 lease remains after expiry.
   All BGP peers must stay established.
3. Query k8s-gateway directly and the LAN client's normal resolver:

   ```bash
   for host in flux-mcp.igas.dev gitea.igas.dev grafana.igas.dev; do
     dig @192.168.100.8 "$host" A +noall +answer
     dig "$host" A +noall +answer
   done
   ```

   These commands use the post-#828 DNS address. Before that cutover, query
   `192.168.6.8` instead. All three names must resolve to `192.168.100.7`. k8s-gateway watches
   HTTPRoutes and derives their address from the parent Gateway status, so
   no hard-coded DNS address changes here. If only the normal resolver is
   stale, wait for its cached TTL or flush that client's DNS cache and retry.
4. Run `task check-lb` again from the same LAN host. envoy-internal must pass
   TCP and HTTP/3 probes at its new IP. Every other Service address and
   result must match the baseline. The known kube-api refusal still causes
   the overall command to exit non-zero and must not be reported as fixed.
5. In a browser on the LAN, load Gitea and Grafana, and open
   `https://flux-mcp.igas.dev/mcp` to verify TLS and the expected 401 without
   credentials. Run the authenticated initialization request in
   [flux-mcp.md](flux-mcp.md#when-it-does-not-connect) and confirm a JSON-RPC
   result. Repeat from wired and Wi-Fi LAN hosts where available. HTTP data
   and browser checks test the DSR return path beyond a TCP handshake.
6. Record assigned IP, Gateway conditions, advertisements, L2 exclusion,
   DNS answers, browser/authenticated MCP results and before/after checker
   output on #827. Leave it open until post-cutover acceptance checks pass.

## Rollback

1. Revert only #827's migration commit and reconcile envoy-gateway through
   Flux. Together restore the internal Gateway's IP annotation to
   `192.168.6.7`, remove its infrastructure `igas.dev/lb-pool` label and
   `parametersRef`, and remove the internal-only EnvoyProxy. This restores
   the shared `externalTrafficPolicy: Cluster` without changing envoy-external.
2. Confirm the Service and Gateway status return to `192.168.6.7`, the
   `192.168.100.7/32` advertisement is withdrawn and the Service is eligible
   for legacy L2 announcements again. Keep both pools, the legacy L2 policy
   and the shared UniFi policy intact.
3. Repeat direct k8s-gateway and normal-resolver queries until the sample
   names return `192.168.6.7`. Expire or flush stale client DNS caches.
   Repeat the LAN checker, browser checks and authenticated MCP request.
   Other Services must match baseline. Use `task flux-mcp` for diagnostics
   while gateway recovery is in progress.
