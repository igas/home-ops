# flux-operator group

The `flux-operator` Renovate group has three members, all in `kubernetes/apps/flux-system/` and all on the same version:

- `flux-operator` chart (CRDs and operator)
- `flux-instance` chart, plus the `flux-operator-manifests` artifact tag in its HelmRelease values
- `flux-operator-mcp` chart (the Flux MCP server, added in #710)

The group rule in `.renovaterc.json5` matches by substring (`/flux-operator/`), so the MCP chart joins the group without its own rule. A bump PR that changes only one or two of the three OCIRepository tags means the group split, which is a finding.

## What `readonly` guards

The MCP chart binds its ServiceAccount to `cluster-admin` (`rbac.create: true`, no narrower role on offer). `readonly: true` in the HelmRelease renders `--read-only=true`, which stops the server registering any tool not flagged read-only: reconcile, suspend, resume, apply, patch, delete, and install-instance never appear in the tool list (`cmd/mcp/toolbox/manager.go` at v0.60.0). With it off, anyone who can reach port 9090 holds cluster-admin through the MCP tools. The chart default is `false`.

On every bump:

1. Diff `values.yaml` for `readonly`, `rbac`, `networkPolicy`, and `transport`. A renamed or removed `readonly` key means the HelmRelease value stops rendering, so the verdict is `hold`.
2. In the flux-local diff, the Deployment args must still contain `--read-only=true` and `--mask-secrets=true`.
3. Read the app release notes for new tools. A new mutating tool that read-only mode does not cover is a finding.

## Checking it after merge

`task flux-mcp` opens the port-forward (see `docs/runbooks/flux-mcp.md`).

The repo's `.mcp.json` points Claude Code at `http://localhost:9090/mcp`. List the tools and check that none of the mutating ones appear. The chart's NetworkPolicy only admits traffic from `flux-system`. Port-forward enters the pod's network namespace directly, so it is not blocked.
