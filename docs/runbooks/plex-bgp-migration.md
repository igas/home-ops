# Plex BGP migration

Migration and rollback for [#824](https://github.com/igas/home-ops/issues/824).
Plex moves from `192.168.6.210` to `192.168.100.210`, keeping TCP port 32400
and returning from the interim `Cluster` traffic policy to `Local`.

## Before cutover

- Confirm #821's wired and Wi-Fi canary gate has passed. Keep both IP pools,
  the legacy L2 policy and the persistent UniFi policy described in
  [lb-bgp-canary.md](lb-bgp-canary.md).
- Run `task check-lb` from wired and Wi-Fi hosts on the Default LAN and save
  the complete output. The 2026-10-25 pre-cutover check from the agent host
  passed for Plex and every other Service except kube-api at
  `192.168.6.9:6443`, which refused connections. All four BGP peers were
  established. This is not a fully green baseline or proof from both hosts.
- The UniFi policy covers only `192.168.0.0/20`. Confirm the TV is on this
  Default LAN. IoT and VPN clients need separate policy approval and testing.
- In Plex Web, open Settings > Server > Network, show advanced settings,
  and record the current Custom server access URLs for rollback. Arrange
  an operator to update this setting and test the TV during cutover.
- Schedule the rescheduling check outside playback. Confirm another node can
  satisfy Plex's GPU resource claim and mount its config volume before moving
  the pod. If no other node is eligible, record the blocked check on #824.

## Cutover and verification

1. Deploy the Plex HelmRelease change through Flux. The rendered Service must
   change `igas.dev/lb-pool: bgp`, `lbipam.cilium.io/ips: 192.168.100.210` and
   `externalTrafficPolicy: Local` together. The container's
   `PLEX_ADVERTISE_URL` must use `http://192.168.100.210:32400`, preserving
   `https://plex.igas.dev:443` and the cluster-DNS URL. Do not change other
   Services, storage, GPU claims, probes or Plex authentication networks.
2. In Plex's Custom server access URLs, replace only
   `http://192.168.6.210:32400` with `http://192.168.100.210:32400`, or add the
   new LAN URL if the old one is absent. Preserve other valid entries and save.
   Reopen the setting after the rollout to confirm it persisted. Record
   explicit operator confirmation on #824. The HelmRelease environment value
   alone is not confirmation of this Plex setting.
3. Confirm the assigned address and ready endpoint:

   ```bash
   kubectl -n default get service plex -o yaml
   kubectl -n default get endpointslices -l kubernetes.io/service-name=plex -o yaml
   kubectl -n default get pods -l app.kubernetes.io/name=plex -o wide
   ```

   Using the per-agent commands in
   [lb-bgp-canary.md](lb-bgp-canary.md#check-advertisement-and-l2-exclusion),
   verify only the node with the ready Plex endpoint advertises
   `192.168.100.210/32`. There must be no Plex L2 lease. Every BGP peer must
   remain established.
4. Run `task check-lb` on both LAN hosts. Plex must pass at its new address and
   all other Service addresses and results must match their baselines. The
   known kube-api refusal still makes the overall checker fail. Exercise HTTP
   data from both hosts as well, since a TCP handshake alone does not prove
   that the DSR return path works:

   ```bash
   curl --noproxy '*' --fail --max-time 15 http://192.168.100.210:32400/identity
   ```

5. Reconnect the TV's Plex app and play a title. In Plex Dashboard, expand the
   active session and confirm a direct connection, not Relay or an indirect
   connection. Confirm Plex reports the TV's actual LAN IP and treats the
   session as local, not remote. Direct Play describes media transcoding and
   is not proof of a direct local network connection. Record the operator's
   result on #824.
6. In the maintenance window, record the current Plex node, cordon that node,
   and delete only the Plex pod so its controller schedules a replacement on
   another eligible node. Use the exact recorded node and pod names:

   ```bash
   kubectl cordon OLD_NODE
   kubectl -n default delete pod PLEX_POD
   kubectl -n default get pods -l app.kubernetes.io/name=plex -o wide -w
   ```

   Wait for readiness and verify the node actually changed. Repeat the
   endpoint, per-node advertisement, both LAN checks, HTTP and TV checks.
   The old node must withdraw the `/32`; only the new ready endpoint's node
   may advertise it. Uncordon the old node even if the test fails:

   ```bash
   kubectl uncordon OLD_NODE
   ```

   If the replacement remains Pending, uncordon the old node to let Plex
   recover. Record the scheduling blocker rather than claiming this check
   passed. A restart on the same node does not meet this criterion.
7. Record the settings confirmation, TV result, before/after node names,
   advertisement/L2 inspection and both hosts' checker output on #824.
   Leave the ticket open while any acceptance check is pending.

## Rollback

1. Revert only #824's migration commit and reconcile `default/plex` through
   Flux. Together, remove the Service's `igas.dev/lb-pool` label, restore
   `lbipam.cilium.io/ips: 192.168.6.210` and restore
   `externalTrafficPolicy: Cluster`, the pre-migration interim workaround.
   Restore `http://192.168.6.210:32400` in `PLEX_ADVERTISE_URL`.
2. Restore the recorded Plex Custom server access URLs, removing the new LAN
   IP and restoring the old one as appropriate. Reopen the setting to verify.
3. Confirm the old IP is assigned, the new `/32` is withdrawn and Plex is
   eligible for legacy L2 announcements again. Keep both pools, the legacy
   L2 policy and the shared UniFi policy. Uncordon any node left cordoned
   during testing.
4. Repeat both LAN checks and TV playback. Other Services must match baseline.
   The interim `Cluster` policy avoids the original Local/L2 refusal but may
   hide the TV's real source IP. Rollback is not proof of local-client handling.
