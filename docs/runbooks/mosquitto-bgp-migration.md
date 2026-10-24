# Mosquitto BGP migration

Migration and rollback for [#822](https://github.com/igas/home-ops/issues/822).
The broker moves from `192.168.6.124` to `192.168.100.124`, keeping TCP port 1883
and `externalTrafficPolicy: Local`.

## Before cutover

- Confirm #821's wired and Wi-Fi canary gate has passed. Keep both IP pools,
  the legacy L2 policy and the persistent UniFi policy described in
  [lb-bgp-canary.md](lb-bgp-canary.md).
- Run `task check-lb` from the wired and Wi-Fi LAN hosts and retain the output.
  On 2026-10-25, the pre-cutover Wi-Fi check reported Mosquitto and kube-api
  refused, with all other Services passing and all four BGP peers established.
- Inventory MQTT clients before changing the address. The live Home Assistant
  MQTT integration and the Zigbee2MQTT manifest both use
  `mosquitto.default.svc.cluster.local:1883`, so they need no change. On
  2026-10-25 the operator confirmed there are no other MQTT clients.
- For any future IP-based clients, coordinate the broker setting change from
  `192.168.6.124` to `192.168.100.124` with cutover. For hostname-based clients,
  verify `mosquitto.igas.dev` resolves to the new address and reconnect them.
  Do not edit Home Assistant's `.storage` files directly.
- The persistent gateway policy covers only the Default LAN `192.168.0.0/20`.
  IoT and VPN clients require a separately approved policy and validation.

## Cutover and verification

1. Deploy the Mosquitto HelmRelease change through Flux. The rendered Service
   must change the label `igas.dev/lb-pool: bgp` and annotation
   `lbipam.cilium.io/ips: 192.168.100.124` together, retaining `Local`.
   Do not change the broker, storage, ClusterIP or other Services.
2. Confirm the assigned IP and ready endpoint:

   ```bash
   kubectl -n default get service mosquitto -o yaml
   kubectl -n default get endpointslices -l kubernetes.io/service-name=mosquitto -o yaml
   kubectl -n default get pods -l app.kubernetes.io/name=mosquitto -o wide
   ```

3. Use the per-agent commands in [lb-bgp-canary.md](lb-bgp-canary.md#check-advertisement-and-l2-exclusion).
   Only the node with the ready broker endpoint may advertise
   `192.168.100.124/32`. There must be no Mosquitto L2 lease. Other Service
   addresses and policies must remain unchanged.
4. Run `task check-lb` from both LAN hosts. Mosquitto must pass at its new IP;
   every other result must match the baseline, including the existing kube-api
   refusal. The overall checker is not green while that unrelated failure remains.
5. Exercise MQTT application data, not just a TCP handshake. With Mosquitto
   client tools on a LAN host, start a subscriber, then publish a unique,
   non-retained message from another terminal:

   ```bash
   mosquitto_sub -h 192.168.100.124 -p 1883 -t home-ops/lb-check/822 -C 1 -W 15
   mosquitto_pub -h 192.168.100.124 -p 1883 -t home-ops/lb-check/822 -m "cutover-822-$(date +%s)"
   ```

   Confirm the subscriber receives the exact payload. Do not publish to device
   command topics or use retained messages for this probe.
6. Confirm Home Assistant's MQTT integration remains connected. Trigger a
   harmless MQTT-backed automation and confirm its expected result or trace.
   Record operator confirmation on #822. A successful synthetic MQTT probe is
   not proof that a Home Assistant automation ran.
7. Record both LAN checks, advertisement/L2 inspection, MQTT delivery and client
   confirmation on #822. Do not close the ticket with any acceptance check pending.

## Rollback

1. Revert only #822's migration commit and reconcile the `default/mosquitto`
   Flux Kustomization and HelmRelease. The Service must remove
   `igas.dev/lb-pool` and restore `lbipam.cilium.io/ips: 192.168.6.124` together.
   Keep `externalTrafficPolicy: Local`, its pre-migration value.
2. Restore any external clients changed during cutover to the old address.
   Home Assistant and Zigbee2MQTT's cluster-DNS settings remain unchanged.
   Verify DNS if any clients use `mosquitto.igas.dev`.
3. Confirm the old IP is assigned, the BGP-only `/32` is withdrawn and the
   Service is again eligible for legacy L2. Keep both pools and the UniFi policy;
   they are shared migration dependencies, not part of this rollback.
4. Rerun both LAN checks and MQTT/Home Assistant checks. Compare every other
   Service against baseline. Restoring the old IP and `Local` policy can restore
   the original intermittent L2 refusal; rollback does not fix that old fault.
