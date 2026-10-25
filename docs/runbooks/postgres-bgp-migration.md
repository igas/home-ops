# Postgres BGP migration

Migration and rollback for [#823](https://github.com/igas/home-ops/issues/823).
`database/postgres-lb` moves from `192.168.6.125:5432` to
`192.168.100.125:5432`. Traffic policy changes from the default `Cluster`
to `Local`; the selector still targets only the `postgres-18` primary.

## Before cutover

- Confirm #821's canary gate passed. Retain both pools, the legacy L2 policy
  and the persistent UniFi policy in [lb-bgp-canary.md](lb-bgp-canary.md).
  The policy covers only the Default LAN `192.168.0.0/20`, not IoT or VPN.
- Retain `task check-lb` output from LAN hosts and an authenticated read-only
  database query through the old IP. Record any existing failures separately.
- Inventory connection settings without publishing passwords. The repository's
  only old-IP reference was this Service. Autopulse and Woodpecker explicitly
  use `postgres-18-rw.database.svc.cluster.local`.
- On 2026-10-25, inspection of live secret host fields confirmed Radarr,
  Sonarr and Autobrr also use that cluster DNS name, including their init
  clients. Prowlarr uses `192.168.3.5`, a different database address, and is
  outside this migration. The operator confirmed no external IP-based clients.
  No client settings need changing for this cutover.
- For future IP-based clients, coordinate changing their connection host to
  `192.168.100.125` at cutover. Check desktop database tools, scripts, backup
  jobs and 1Password entries outside the repo. For hostname-based clients,
  verify `postgres.igas.dev` resolves to the new IP, then reconnect them.

## Cutover and verification

1. Deploy only the Postgres Service change through the
   `database/cloudnative-pg-cluster` Flux Kustomization. Change the pool label
   `igas.dev/lb-pool: bgp`, IP annotation and `Local` policy together.
   Keep the ClusterIP, port, primary selector, database cluster and other
   Services unchanged. If validating before pushing, suspend only this
   Kustomization, patch only these Service fields, and resume after Flux can
   read the matching commit. Record any temporary suspension on #823.
2. Confirm assignment and primary endpoint:

   ```bash
   kubectl -n database get service postgres-lb -o yaml
   kubectl -n database get endpointslices -l kubernetes.io/service-name=postgres-lb -o yaml
   kubectl -n database get pods -l cnpg.io/cluster=postgres-18 -o wide
   ```

3. Follow [the advertisement checks](lb-bgp-canary.md#check-advertisement-and-l2-exclusion).
   Only the ready primary endpoint's node may advertise
   `192.168.100.125/32`. There must be no active Postgres L2 lease. All peers
   must remain established, with other Service IPs and policies unchanged.
4. Run `task check-lb` again from the same LAN hosts. Postgres must pass at
   its new address; every other Service must match the baseline.
5. Open an authenticated database session from the LAN, not from a Pod or a
   port-forward. Use an existing approved credential through a password prompt
   or protected password file, never a password in shell arguments:

   ```bash
   PGCONNECT_TIMEOUT=8 PGSSLMODE=require psql -X -W \
     -h 192.168.100.125 -p 5432 -U DATABASE_USER -d DATABASE_NAME \
     -v ON_ERROR_STOP=1 \
     -c 'SELECT current_database(), inet_client_addr(), inet_server_addr(), pg_is_in_recovery();'
   dig @192.168.1.1 postgres.igas.dev A +short
   ```

   The query must succeed, report the real LAN client address and return
   `false` for recovery. Use the cluster CA and `verify-ca` when available;
   `require` alone does not establish server identity. Repeat the session
   using `postgres.igas.dev` after DNS converges. A TCP handshake alone does
   not prove the DSR application-data path.
6. Record LAN results, query results, DNS, route/lease checks and operator
   client confirmation on #823. Leave acceptance checks pending until their
   evidence exists. No schema changes, database writes or restarts are needed.

## Cutover record

Flux applied `c381428` on 2026-10-25 without suspending reconciliation.
Before and after cutover, the Wi-Fi LAN checker passed all seven Services
and four BGP peers. CA-verified authenticated queries through both old and
new IPs succeeded from `192.168.15.173`, reaching primary `10.42.2.243` with
the real client IP preserved and recovery `false`. ClusterIP `10.43.43.80`
and the primary endpoint were unchanged. Only `k8s-master-01`, the primary's
node, advertised the new `/32`; no Postgres L2 lease remained.

Router DNS at `192.168.1.1` returned `192.168.100.125`. This Mac's scoped
resolver queries k8s-gateway, which returns NXDOMAIN for the name, as with
the [API resolver issue](talos-control-plane-endpoint.md#kube-api-loadbalancer-migration).
A hostname session with `PGHOSTADDR` set to the router-resolved address
passed CA verification and authentication. This is not a claim that native
macOS hostname resolution is fixed. No workstation DNS settings changed.
The wired host lacks kubectl and psql; no wired full-check or database-session
result is claimed for this migration. Ticket #823 holds the acceptance evidence.

## Rollback

1. Revert only #823's Service migration and reconcile
   `database/cloudnative-pg-cluster`. Restore annotation
   `lbipam.cilium.io/ips: 192.168.6.125`, remove only the `igas.dev/lb-pool`
   label, and restore `externalTrafficPolicy: Cluster`, its original default.
   Keep the primary selector, ClusterIP and database unchanged.
2. For a pre-merge manual cutover, restore those same fields in one Service
   patch before resuming reconciliation against the old Git revision.
3. Restore any external clients changed during cutover. Existing cluster-DNS
   clients need no change. Verify `postgres.igas.dev` returns the old address.
4. Confirm the old IP is assigned, the new `/32` is withdrawn, and Postgres
   is eligible for legacy L2 again. Keep both pools and the shared UniFi
   policy, which other migrated Services still require.
5. Repeat the LAN checker and authenticated query through the old IP. Compare
   every other Service with baseline and record rollback results on #823.
