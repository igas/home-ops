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

## Settings that decide which release notes matter

TXT registry (not `crd`), no `--txt-encrypt-enabled`, Cloudflare proxying through `--cloudflare-proxied` rather than `providerSpecific`. The one DNSEndpoint (`network/cloudflare-tunnel`) has no `providerSpecific`. Registry, encryption, and Cloudflare provider-specific changes therefore skip us; source changes (gateway, service, crd) do not.
