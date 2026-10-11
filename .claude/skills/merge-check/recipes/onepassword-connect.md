# onepassword-connect

`kubernetes/apps/external-secrets/onepassword` runs 1Password Connect on app-template: one pod with two containers, `connect-api` and `connect-sync`, talking over a local bus (`OP_BUS_PEERS`). External Secrets' `onepassword` ClusterSecretStore reads through it, so a broken pod stalls every ExternalSecret refresh. For the ESO side, see [external-secrets.md](external-secrets.md).

## api and sync move together

The `1password-connect` group rule in `.renovaterc.json5` opens one PR for both images, titled `update 1password-connect group`. It needs both to have an update (`minimumGroupSize: 2`). If a single-image PR still shows up, review the pair together and name the other image's pending bump in **Prep**. Check image config for **both** images; they're built separately.

## Release notes

1Password publishes notes in several places, and none of them is complete:

- `CHANGELOG.md` in `1Password/connect` (stopped at v1.8.0)
- https://releases.1password.com/developers/connect/ (stopped at 1.8.1)
- GitHub releases (none)
- the official chart's `CHANGELOG.md`: `helm pull oci://ghcr.io/1password/connect --version <v> --untar`. Its `appVersion` maps a chart version to a Connect version.
- maintainer replies on `1Password/connect` issues (1.8.3's only description is on #115)

## Precedent

onedr0p uses the official chart (`ghcr.io/1password/connect`), not the raw images. Find the chart version whose `appVersion` matches the target and search his merged PRs for that.

## UID and base image

Our pod forces UID/GID 999 with `readOnlyRootFilesystem: true`. When an image changes base (1.8.3 moved to Chainguard), compare the image config instead of running a preflight:

```
docker buildx imagetools inspect ghcr.io/1password/connect-api:<v> --format '{{json .Image}}' \
  | jq '.["linux/amd64"].config | {User, Entrypoint, WorkingDir}'
```

Then confirm the official chart's `connect-deployment.yaml` still sets `runAsUser: 999`.
