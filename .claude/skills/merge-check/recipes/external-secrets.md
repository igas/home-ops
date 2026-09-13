# external-secrets

This cluster uses the 1Password **Connect** provider (`onepassword`), not `onepasswordsdk`. Release notes about the SDK provider do not apply; notes about Connect do.

## CRD diff

The chart ships CRDs under `templates/crds/` behind `installCRDs`, so the raw files are templates, not valid YAML for `yq`. Diff rendered output instead:

```
helm template es <chart> --version <old> --include-crds > old.yaml
helm template es <chart> --version <new> --include-crds > new.yaml
```

Then extract `provider.properties.onepassword` from the `ClusterSecretStore` and `SecretStore` CRDs in each and diff those.

## Known noise

PushSecret `network/igas-dev-tls` logs a 1Password 400 on every reconcile while still reporting `Synced`. Not a regression from a bump.
