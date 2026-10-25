# External Envoy gateway BGP migration

Cutover and rollback for [#826](https://github.com/igas/home-ops/issues/826).
Only envoy-external moves, from `192.168.6.6` to `192.168.100.6`.
Ports 80/TCP, 443/TCP and 443/UDP remain unchanged.
Repository preparation is not evidence of deployment or external reachability.

## Before cutover

1. Confirm #821's wired and Wi-Fi gate passed. Keep both pools, legacy L2
   selection and the persistent UniFi policy in [lb-bgp-canary.md](lb-bgp-canary.md).
   That policy covers Default LAN TCP/UDP, not Internet inbound, IoT or VPN.
2. Complete the dependency inventory on #826 before deployment. Record each
   UniFi port forward targeting `192.168.6.6`, including enabled state, WAN,
   source restrictions, protocol, external port and translated port. Snapshot
   matching manual DNS records and other IP-based clients too. The operator
   must confirm the full inventory, including an explicit "none" where applicable.
   Schedule the forward/manual-record updates with the Service cutover.
3. Verify these repository-managed dependencies against their live state:

   | Dependency | Cutover action |
   | --- | --- |
   | Cloudflare Tunnel origin | Keep `https://envoy-external.network.svc.cluster.local:443` and TLS server name `external.igas.dev`; neither targets the LB IP. Confirm no remote override uses the old IP. |
   | Public `external.igas.dev` | Keep the CNAME to `9fb841ec-3985-4fc1-a40c-844270fb8151.cfargotunnel.com` from `cloudflare-tunnel/app/dnsendpoint.yaml`. |
   | Public route DNS | Keep Cloudflare external-dns targets at `external.igas.dev`. Verify no manually managed record targets the old IP. Proxied DNS may return Cloudflare edge A/AAAA answers; inspect record configuration to verify the CNAME. |
   | LAN DNS | UniFi external-dns watches the generated Service hostname and routes; k8s-gateway derives route addresses from Gateway status. Verify both paths update automatically, and update any manual overrides. |
   | Route backends and Gatus | Service DNS and Gateway parent references remain unchanged. No literal LB IP to update. |

4. Save `task check-lb` output and all LoadBalancer addresses/traffic policies
   from the LAN host used for verification. Record existing failures rather
   than treating an overall nonzero result as a new regression. Save DNS
   answers and browser results for external routes. At preparation time the
   live routes were `echo.igas.dev`, `home-assistant.igas.dev`, `ha.igas.dev`,
   `plex.igas.dev`, `flux-webhook.igas.dev`, `gatus.igas.dev`, `status.igas.dev`
   and `ci.igas.dev`. Refresh the list from live HTTPRoutes before cutover.
5. Confirm off-LAN browser access before the move using mobile data with
   Wi-Fi and VPN disabled. Arrange the same check after the move. Leave the
   ticket open if no independent off-LAN check is available.

## Cutover and verification

1. After inventory confirmation, deploy the envoy-gateway Kustomization through
   Flux and update each inventoried UniFi forward/manual DNS record in the same
   maintenance window. Change only the destination IP to `192.168.100.6`;
   preserve protocol, ports, source restrictions and enabled state. Record the
   read-back of each external change on #826. If none were needed, record the
   operator's confirmation. Keep the tunnel origin and public CNAMEs unchanged.
2. Confirm the Gateway is Accepted and Programmed with address `192.168.100.6`.
   Its generated Service must have that IP, label `igas.dev/lb-pool: bgp` and
   `externalTrafficPolicy: Local`. The Gateway-specific EnvoyProxy merges the
   policy with shared defaults without changing envoy-internal.

   ```bash
   kubectl -n network get gateway envoy-external -o yaml
   kubectl -n network get service -l gateway.envoyproxy.io/owning-gateway-name=envoy-external -o yaml
   kubectl -n network get endpointslices -l kubernetes.io/service-name=envoy-external -o yaml
   kubectl -n network get pods -l gateway.envoyproxy.io/owning-gateway-name=envoy-external -o wide
   ```

   Follow [the canary advertisement checks](lb-bgp-canary.md#check-advertisement-and-l2-exclusion).
   Only nodes with ready external Envoy endpoints should advertise
   `192.168.100.6/32`. No external Envoy L2 lease should remain after expiry.
   All BGP peers must stay established.
3. Verify split DNS using both the direct cluster resolver and normal LAN resolver:

   ```bash
   for host in external.igas.dev echo.igas.dev ha.igas.dev ci.igas.dev; do
     dig @192.168.100.8 "$host" A +noall +answer
     dig "$host" A +noall +answer
   done
   ```

   The final LAN address must be `192.168.100.6`. Expire or flush stale cached
   answers and retry. These commands use the post-#828 DNS address. Before that
   cutover, query `192.168.6.8` instead. No UniFi DNS-forwarder destination change
   belongs to #826; follow [k8s-gateway-bgp-migration.md](k8s-gateway-bgp-migration.md)
   for that Service move and its deployment status. Check public DNS using an external
   resolver separately; it must still use the tunnel, not a private address.
4. Run `task check-lb` from the same LAN host. envoy-external must pass TCP and
   HTTP/3 at its new IP. Every other Service's address, traffic policy and result
   must match baseline. Repeat from wired and Wi-Fi hosts where available.
   Exercise an HTTPS response, not just a TCP handshake:

   ```bash
   curl --noproxy '*' --fail --show-error --resolve echo.igas.dev:443:192.168.100.6 https://echo.igas.dev/
   ```

5. Check both cloudflared replicas remain ready and inspect recent logs for
   origin errors. Load public hostnames in a browser off the LAN, with Wi-Fi
   and VPN disabled. Verify actual pages or expected authentication responses,
   not only DNS or TCP. Check the previously inventoried routes, including
   Home Assistant and CI, and record the hostnames and results on #826.
   For each direct WAN port forward, test its specific protocol/port from
   outside the LAN separately. Tunnel success does not prove forwarding works;
   the canary policy does not authorize WAN traffic.
6. Record operator confirmation of every external change, DNS answers, assigned
   IP, Gateway conditions, BGP/L2 checks, before/after LAN checker output and
   off-LAN browser/forward results. Close #826 only when all acceptance checks
   pass. If WAN forwarding fails under DSR, roll back and diagnose it rather
   than broadening firewall permissions without approval.

## Rollback

1. Revert only #826's migration commit and reconcile envoy-gateway through Flux.
   Restore the external Gateway annotation to `192.168.6.6`, remove its
   infrastructure pool label and `parametersRef`, and remove the external-only
   EnvoyProxy. This restores shared `externalTrafficPolicy: Cluster` for
   envoy-external. Preserve envoy-internal's Local override and new IP.
2. In the same window, restore each changed UniFi port forward and manual DNS
   record from its pre-cutover snapshot. Confirm the read-back on #826. Leave
   the tunnel Service-DNS origin, TLS server name and public tunnel CNAMEs intact.
3. Confirm the Service/Gateway return to `192.168.6.6`, the new `/32` is
   withdrawn and legacy L2 eligibility returns. Keep both pools, legacy L2
   policy and the persistent UniFi policy needed by other migrated Services.
4. Verify LAN DNS returns the old IP after cache expiry. Repeat the LAN checker,
   HTTPS data check with the old IP, off-LAN browser checks and each WAN forward
   check. Other Services must match baseline. Use `task flux-mcp` to bypass
   Envoy for diagnostics if required.
