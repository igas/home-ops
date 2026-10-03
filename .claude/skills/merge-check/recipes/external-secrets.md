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
