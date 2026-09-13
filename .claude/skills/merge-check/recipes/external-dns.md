# external-dns

Runs with `policy: sync`, so a change to what records it claims **deletes or retargets** live records. The chart release notes will not say this; the app's will. Caught 2026-09-12 on PR #697: chart 1.22.0 said only "policy is now required", app v0.22.0 changed the default annotation prefix to `external-dns.kubernetes.io/` with no fallback.

Two instances in `network`: Deployment `cloudflare-dns` (Cloudflare provider) and Deployment `unifi-dns` (UniFi webhook provider).

## Preflight: dry-run pod (Cloudflare instance)

Read-only. Cloudflare honours `--dry-run`.

1. `kubectl get deploy -n network cloudflare-dns -o json | jq '.spec.template'` to clone the pod template.
2. Build a bare `Pod` from it: `restartPolicy: Never`, fresh labels (`merge-check: preflight`), swap the image to the new tag, drop `--events`, append `--dry-run --once`.
3. Apply, `kubectl logs -f`, read what it *would* create, update, delete. Any delete or retarget of an existing record is a finding.
4. `kubectl delete pod`.

## UniFi webhook instance

The webhook does not honour dry-run. Static analysis only: compare the annotation and label selectors the new version reads against the Gateways and HTTPRoutes in `kubernetes/apps/network/`.
