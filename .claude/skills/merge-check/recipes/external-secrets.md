# external-secrets

This cluster uses the 1Password **Connect** provider (`onepassword`), not `onepasswordsdk`. Release notes about the SDK provider do not apply; notes about Connect do.

## CRD diff

The chart ships CRDs under `templates/crds/` behind `installCRDs`, so the raw files are templates, not valid YAML for `yq`. Diff rendered output instead:

```
helm template es <chart> --version <old> --include-crds > old.yaml
helm template es <chart> --version <new> --include-crds > new.yaml
```

Then extract `provider.properties.onepassword` from the `ClusterSecretStore` and `SecretStore` CRDs in each and diff those.

## Pushing several keys to one item

PushSecret `network/igas-dev-tls` pushes `tls.crt` and `tls.key` to separate 1Password items, because two back-to-back updates to one item get a Connect 400 (#707). A 400 from it now is a real failure, not background noise. If a release note says the Connect provider waits for the item version after an update, merging back to one item becomes an option.

The upstream twin of #707 is external-secrets/external-secrets#7053, which is open. Check its state when reviewing a bump.

## Template and Secret-type features we rely on

Template-engine changes can break ExternalSecrets silently, because the operator stays healthy while individual ExternalSecrets go `SecretSyncedError`. When notes remove a sprig/template function or restrict Secret types, grep for it:

```
grep -rn '<function>' $(grep -rl 'kind: ExternalSecret' kubernetes)
```

As of 2.12.0, no template uses `fail` (removed in 2.12.0), and none templates a `kubernetes.io/service-account-token` or bootstrap-token Secret (blocked in 2.12.0). After merge, `kubectl get externalsecrets -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | sort | uniq -c` should show only `True`.

Version 2.13.0 extends validation to manifest Secret candidates and restricts v1beta1 `templateFrom.target` to Data, Annotations, or Labels. Check manifest targets and templateFrom entries, not just Secret types. On #858 the repo used v1 and autopulse's only templateFrom omitted the target, which keeps the supported Data default. Versions 2.13.0 and 2.14.0 do not fix the Connect PushSecret issue above.

### Template allocation limits in 2.15.0

[Upstream #7212](https://github.com/external-secrets/external-secrets/pull/7212) bounds allocating functions, including `replace`, and rejects rendered values of 1 MiB or more. Sequences have endpoints within ±10,000. See the [exact limits](https://github.com/external-secrets/external-secrets/blob/v2.15.0/runtime/template/v2/sprig/limits.go).

When reviewing these limits:

1. Read live ExternalSecret and PushSecret templates and rewrites, plus referenced `templateFrom` ConfigMaps. Repo-only searches miss generated or separately stored templates.
2. Check every bounded function against its arguments. Woodpecker's database connection string uses `replace` to escape its password; this function is easy to miss when searching only for sequence generators.
3. For affected output-size limits, fetch each ExternalSecret's target Secret by namespace and `spec.target.name`, falling back to the ExternalSecret name. Calculate decoded field lengths in memory and report only lengths. Check PushSecret source lengths after the configured transformation; base64 expands TLS fields.
4. Complete the check only when all relevant templates and outputs fit. Existing output sizes establish compatibility of current inputs, not execution of the candidate controller. A missing target or unresolved expression needs further investigation.

On #953, all 44 ExternalSecret targets were readable; the largest field was 5,651 bytes. Woodpecker's password was 64 bytes and its connection string 182 bytes. TLS PushSecret outputs were 7,536 and 2,236 bytes after base64. Recheck these measurements on later reviews.

### ClusterSecretStore processing in 2.15.0

[Upstream #7217](https://github.com/external-secrets/external-secrets/pull/7217) makes PushSecrets skip reconciliation when cluster-store processing is disabled and a ClusterSecretStore appears in spec or saved status. Check effective `processClusterStore` and controller arguments, not just Pod readiness. On #953 the unchanged default was `true`, with no disabling argument or controller-class restriction. The remote-key deletion fix #7165 does not fix the Connect stale-item race; retain the separate-item workaround.

## Bootstrap

`bootstrap/helmfile.d/01-apps.yaml` installs this chart with `templates/values.yaml.gotmpl`, which reads the HelmRelease's own `spec.values`. A key that becomes required only needs adding to the HelmRelease, not to the helmfile.
