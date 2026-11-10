# external-dns

Runs with `policy: sync`, so a change to what records it claims **deletes or retargets** live records. The chart release notes will not say this; the app's will. Caught 2026-09-12 on PR #697: chart 1.22.0 said only "policy is now required", app v0.22.0 changed the default annotation prefix to `external-dns.kubernetes.io/` with no fallback.

Two instances in `network`: Deployment `cloudflare-dns` (Cloudflare provider) and Deployment `unifi-dns` (UniFi webhook provider).

## Preflight: dry-run pod (Cloudflare instance)

Read-only. Cloudflare honours `--dry-run`.

1. `kubectl get deploy -n network cloudflare-dns -o json | jq '.spec.template'` to clone the pod template.
2. Build a bare `Pod` from it: `restartPolicy: Never`, fresh labels (`merge-check: preflight`), swap the image to the new tag, drop `--events`, append `--dry-run --once`.
   One-liner that worked on PR #788:
   ```
   kubectl get deploy -n network cloudflare-dns -o json | jq '{apiVersion:"v1",kind:"Pod",metadata:{name:"merge-check-edns-<pr>",namespace:"network",labels:{"merge-check":"preflight"}},spec:(.spec.template.spec|.restartPolicy="Never"|.containers|=map(.image="registry.k8s.io/external-dns/external-dns:<new>"|.args=([.args[]|select(.!="--events")]+["--dry-run","--once"])|del(.livenessProbe,.readinessProbe)))}'
   ```
   Wait with `kubectl wait --for=jsonpath='{.status.phase}'=Succeeded`. Under `policy: sync`, a source that returns nothing would show up as planned deletes, so `All records are already up to date` really does mean no change.
3. Apply, `kubectl logs -f`, read what it *would* create, update, delete. Any delete or retarget of an existing record is a finding.
4. `kubectl delete pod`.

## UniFi webhook instance

The webhook does not honour dry-run. It sets no `--gateway-name`, so it reads every Gateway, and it also has the `service` source. Because it can't be dry-run, a source-side change in the app release notes earns a **Prep** line: read its logs for `DELETE` after rollout. Static analysis only: compare the annotation and label selectors the new version reads against the Gateways and HTTPRoutes in `kubernetes/apps/network/`.

Webhook 0.10.13 adds `UNIFI_REQUEST_TIMEOUT`, default zero, so existing deployments keep the old unbounded per-attempt behavior. If enabling it separately, budget attempts plus retry backoff below ExternalDNS's read-plus-write timeout. The upstream example uses 4s for three attempts within the default 15s call budget. Versions before 0.11.0 fetch pages sequentially, so more than one page adds request budgets. Version 0.11.0 fetches one unpaginated array instead.

### Webhook 0.11.0 API migration

Caught on PR #927, 2026-11-08. [Upstream #384](https://github.com/home-operations/external-dns-unifi-webhook/pull/384) replaces Integration API DNS Policies with undocumented `/proxy/network/v2/api/site/{site}/static-dns` endpoints for reads, creates and deletes. The wire format changes, including the ID field from `id` to `_id`. Both APIs expose the same store according to upstream, but that is not a live comparison of this controller's records.

[Upstream #387](https://github.com/home-operations/external-dns-unifi-webhook/pull/387) removes the site lookup. `UNIFI_SITE` still defaults to `default`; an override must now be the console URL's site name, not a UUID. Startup lists records and fails on API errors. The advertised Network minimum drops to 9.0.0, but upstream documents testing only on Network 10.x. The ExternalDNS controller itself does not change when only this webhook image changes.

The retry/rate-limit metric `operation` value changes from `dns_policies` to `static_dns`. Check selectors when reviewing this range. The cloud connector may refuse these non-public paths; a direct local `UNIFI_HOST` without `UNIFI_CONSOLE_ID` avoids that cloud-specific risk. The underscore-label fix is not a reason to add `_dns.resolver.arpa`, the `crd` source or a new domain filter to an unrelated cluster.

Recipe gap: there is no validated read-only UniFi API-migration preflight. The Cloudflare procedure above does not cover it. A future bounded procedure needs an isolated webhook without a reconciling ExternalDNS controller, protected credentials, GET-only checks, and old/new normalized endpoint parity including ownership TXT records. Candidate startup/readiness alone cannot establish parity, and a Pod with the production controller can apply DNS writes. Until the procedure is validated and run, report the migration risk as unverified and hold. The initial PR #927 review ran only live health/image/log inspection, with no throwaway Pod or DNS writes.

The operator then explicitly chose to merge #927 and monitor, with rollback if needed. Production 0.11.0 connected to site `default`, read 59 records, and became Ready with zero container restarts. Five observed syncs through 2026-11-08 02:35:11 UTC reported all records up to date; webhook logs showed successful reads/adjustments and no record-write calls. No rollback was needed during that window. This rollout is cluster-specific evidence, not a validated isolated preflight or proof of create/delete compatibility.

## Settings that decide which release notes matter

TXT registry (not `crd`), no `--txt-encrypt-enabled`, Cloudflare proxying through `--cloudflare-proxied` rather than `providerSpecific`. The one DNSEndpoint (`network/cloudflare-tunnel`) has no `providerSpecific`. Registry, encryption, and Cloudflare provider-specific changes therefore skip us; source changes (gateway, service, crd) do not.
