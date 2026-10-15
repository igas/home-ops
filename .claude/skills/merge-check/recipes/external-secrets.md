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

## Bootstrap

`bootstrap/helmfile.d/01-apps.yaml` installs this chart with `templates/values.yaml.gotmpl`, which reads the HelmRelease's own `spec.values`. A key that becomes required only needs adding to the HelmRelease, not to the helmfile.
