# flux-operator group

The `flux-operator` Renovate group has three members, all in `kubernetes/apps/flux-system/` and all on the same version:

- `flux-operator` chart (CRDs and operator)
- `flux-instance` chart, plus the `flux-operator-manifests` artifact tag in its HelmRelease values
- `flux-operator-mcp` chart (the Flux MCP server, added in #710)

The group rule in `.renovaterc.json5` matches by substring (`/flux-operator/`), so the MCP chart joins the group without its own rule. A bump PR that changes only one or two of the three OCIRepository tags means the group split, which is a finding.

## The bump also moves Flux itself

`flux-instance` pins `distribution.artifact: oci://ghcr.io/controlplaneio-fluxcd/flux-operator-manifests:vX` with `version: 2.x`. A new manifests artifact can ship a newer Flux release, and the operator then upgrades every controller to it. The flux-local diff only shows the artifact tag, so check the Flux version separately:

```
kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}'     # running Flux
gh api 'repos/controlplaneio-fluxcd/flux-operator/contents/config/data/flux?ref=vNEW' --jq '[.[].name]|join(" ")'
```

If the newest `v2.*` directory differs from the running version, read the flux2 release notes for every version in between, plus the component changelogs they link. Then compare its Kubernetes compatibility table with `kubectl version`.

helm-controller CRD-policy changes (for example v1.6.5's fix that stops `Create` from reapplying CRDs under SSA) don't reach us. `kubernetes/flux/cluster/ks.yaml` patches every HelmRelease with `install.crds` and `upgrade.crds: CreateReplace`.

## What `readonly` guards

The MCP chart binds its ServiceAccount to `cluster-admin` (`rbac.create: true`, no narrower role on offer). `readonly: true` in the HelmRelease renders `--read-only=true`, which stops the server registering any tool not flagged read-only: reconcile, suspend, resume, apply, patch, delete, and install-instance never appear in the tool list (`cmd/mcp/toolbox/manager.go` at v0.60.0). With it off, anyone who can reach port 9090 holds cluster-admin through the MCP tools. The chart default is `false`.

On every bump:

1. Diff `values.yaml` for `readonly`, `rbac`, `networkPolicy`, and `transport`. A renamed or removed `readonly` key means the HelmRelease value stops rendering, so the verdict is `hold`.
2. In the flux-local diff, the Deployment args must still contain `--read-only=true` and `--mask-secrets=true`.
3. Read the app release notes for new tools. A new mutating tool that read-only mode does not cover is a finding.

## Checking it after merge

`task flux-mcp` opens the port-forward (see `docs/runbooks/flux-mcp.md`).

The repo's `.mcp.json` points Claude Code at `http://localhost:9090/mcp`. List the tools and check that none of the mutating ones appear. The chart's NetworkPolicy only admits traffic from `flux-system`. Port-forward enters the pod's network namespace directly, so it is not blocked.

## Flux 2.10 through operator 0.62

The 0.62.1 manifests artifact selects Flux 2.10.0 with `version: 2.x`; a chart render alone does not show the controller upgrade. Kubernetes 1.37.1 meets its compatibility table.

Check live Alert/Provider specs before accepting the notification v1 conversion. It drops `Alert.spec.summary`, `Provider.spec.interval`, and legacy proxy/TLS settings in `secretRef`. Use `eventMetadata.summary`, `proxySecretRef`, and `certSecretRef`. Object identity also becomes unconditional and the default RBAC loses TokenRequest permission. Inspect source `serviceAccountName`, remote kubeConfig references and cloud authentication before deciding whether an explicit token-creation binding is needed. Our #905 snapshot used generic OCI sources without object ServiceAccounts and controller-level age decryption. SPIFFE remains opt-in.

Read all four enabled controller changelogs, including 1.10.1 source/kustomize and 1.7.1 helm patches. The MCP chart keeps `readonly` and `maskSecrets`; verify their rendered arguments even when they are outside the Flux diff's context lines.
