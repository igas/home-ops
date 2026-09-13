---
name: merge-check
description: Decide whether a Renovate bump PR is safe to merge, post the verdict on the PR.
disable-model-invocation: true
---

# Merge check

Review Renovate dependency bumps to this repo and post a **verdict** on each PR. The skill exists because CI only proves manifests render: the misses it catches are runtime behaviour changes hidden in *app* release notes, values a chart newly requires, and upgrades that touch every node.

Read `CONTEXT.md` first for the vocabulary (verdict, preflight, recipe, precedent, layer order).

## Invocation

- `/merge-check 656` or `/merge-check 656 654`: review those PRs, in **layer order**.
- `/merge-check all`: review every open Renovate PR without a current verdict, in layer order.
- `/merge-check` with no argument: list open Renovate PRs, mark which have a current verdict, stop.

A verdict is **current** when the newest merge-check comment on the PR names the PR's head SHA. Renovate rebases often, so a stale verdict is reviewed again.

Terminal output is one line per PR: number, verdict, comment URL. Everything else goes in the PR comment.

## Layer order

Sort by the lowest layer a PR touches, ties oldest first:

1. **Node**: `talos/`, `kubernetes/apps/system-upgrade/` (Talos installer, kubelet). Also follow [UPGRADES.md](UPGRADES.md).
2. **Platform**: `kubernetes/apps/kube-system/`, `kubernetes/apps/flux-system/`, and shared charts many HelmReleases consume (`app-template`).
3. **Operators**: `rook-ceph`, `openebs-system`, `volsync-system`, `external-secrets`, `cert-manager`, `database`, `network`.
4. **Apps**: everything else.

A `hold` on a lower layer never blocks the layers above, but every later comment names any pending lower-layer hold that could affect it.

## Verdicts

Three, and only three:

- `safe`: merge as is.
- `safe with prep`: merge, but the **Prep** line says what to do first or straight after.
- `hold`: a real risk found, **or** a mandatory check could not be completed. Unverified is never `safe`.

Labels follow the verdict: `safe` and `safe with prep` set `ready-for-human`; `hold` sets `needs-info`. Remove whichever of the two the PR carried before.

## Review one PR

Work through every step. The **Checked** line of the comment lists exactly what was done, so a step skipped is a step visibly missing, and a missing mandatory step forces `hold`.

1. **Read the PR.** `gh pr view <n> --json title,body,headRefOid,labels,statusCheckRollup,comments,files`. Extract dependency name, old and new version, update type from the title, and the labels. Note which files change; that decides the layer and whether [UPGRADES.md](UPGRADES.md) applies.

2. **Classify independently.** Compute the semver delta yourself. Compare to the title's type and the `type/*` label; a mismatch is a finding. Then read `.renovaterc.json5`: if a `packageRules` entry with `automerge: true` matches this package and update type, the PR should not exist as an open PR. That is a finding too: automerge failed or the config is stale.

3. **CI.** Every check in `statusCheckRollup` is `SUCCESS` or `SKIPPED` (the `configure` job always skips in this fork). Read the flux-local diff comments from `github-actions`. Every changed line must be explained by the version bump. Any other line is a finding.

4. **App release notes, every intermediate version.** For a Helm chart: `helm pull <oci-or-repo>/<chart> --version <new> --untar` into the scratchpad, read `Chart.yaml` for `appVersion`, then read the *app's* releases from the old appVersion to the new one, not only the chart's. For an image: the image's upstream releases across the whole range. Hunt for changed defaults, removed flags, renamed annotations or labels, migrations, and new required config. The Renovate body usually holds only "Compare Source" links; follow them. A release you cannot read is a mandatory check not completed.

5. **Values and schema diff.** Diff `values.yaml` and `values.schema.json` (when present) between old and new chart. Check every changed or newly required key against this repo's HelmRelease values **and** against `bootstrap/helmfile.d/00-crds.yaml`, which renders charts with no values. Follow [recipes/bootstrap-helmfile.md](recipes/bootstrap-helmfile.md) when a key becomes required.

6. **Cluster state.** The component is healthy and running the version the PR claims to replace: `kubectl get helmrelease -n <ns> <name>` and the running image tag, or node versions for layer 1. A component already unhealthy, or already on a different version than the repo says, is a finding.

7. **Precedent and known issues.** We do not run onedr0p's exact stack, but we trust his call on the parts we share.
   - Precedent: `gh pr list -R onedr0p/home-ops --state merged --search "<depName>" --limit 10`. A merged bump to this version or later, with no revert or follow-up fix touching the component since, is positive evidence. A revert or fix commit is negative evidence. When his bump PR carried config changes beyond the version line, surface them under Findings as a suggestion.
   - Known issues: `gh search issues --repo onedr0p/cluster-template "<depName>"`, plus the dependency's own issue tracker for the new version, plus cluster-template discussions (GraphQL `search(type: DISCUSSION)`).
   - This repo: `gh issue list --search "<component>"`. Link any open issue about the component; if the release notes plausibly fix it, say so.

8. **Preflight, when earned.** Static review names a specific runtime risk, and a [recipe](recipes/) exists for it. Write the risk in one sentence before touching the cluster. The only cluster writes allowed are creating and deleting a single throwaway Pod in the component's namespace, with fresh labels so no controller adopts it. Record command and result under **Preflight**. A named risk with no recipe is a **recipe gap**: verdict `hold`, and the gap goes in the comment.

9. **Post.** Write the comment in the shape below, `gh pr comment <n> --body-file`, then swap the label. A new comment every run; history stays on the PR.

10. **Grow the recipes.** When the review taught something reusable about a component (a preflight that worked, a gotcha the release notes hid, a cluster-specific setting), add or extend its file under `recipes/` before moving to the next PR.

## Comment shape

```
**Verdict: safe with prep** · reviewed at <head sha, short> · <YYYY-MM-DD>

**Change**: <dep> <old> → <new> (<type>), running <old> in cluster, healthy.

**Prep**: <only when the verdict needs it>

**Findings**:
1. <finding, with the release-note or diff link it came from>

**Checked**: CI diff · app release notes vX..vY · values diff · cluster state · onedr0p precedent (#NNN) · issues
**Preflight**: <what ran, result> | none needed
**Recipe gaps**: <what was missing> | none
**Lower-layer holds**: #NNN <dep> | none

> *This was generated by AI during review.*
```

`Findings` says `none` when empty. `Change` for layer 1 reads the node versions instead of a HelmRelease.
