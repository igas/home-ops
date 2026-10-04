# GitHub Actions

Minor, patch and digest bumps automerge after a 3-day `minimumReleaseAge`. Majors open a PR, and that soak period doesn't apply to them, so a major can show up minutes after the upstream release.

## Find out whether the workflow runs here

Look at the job's `if:` before you read any release notes. `.github/workflows/e2e.yaml` has `configure` gated on `github.repository == 'onedr0p/cluster-template'`, so it never runs in this repo, and a bump there changes nothing at runtime. Its check shows `SKIPPED` on every PR. Seen on PR #792 (mise-action v4.3.0 → v5.1.0, 2026-10-04).

## Static checks

1. Make sure the pinned digest is the tag's commit: `gh api repos/<owner>/<action>/git/ref/tags/<tag> --jq .object`. For an annotated tag, dereference the tag object to get the commit.
2. Diff the input keys: `gh api 'repos/<owner>/<action>/contents/action.yml?ref=<tag>' --jq .content | base64 -d | yq '.inputs|keys'`, old tag against new. Any input the workflow passes that has been removed or renamed is a finding.
3. Changed defaults matter only for inputs the workflow leaves unset. Compare them against the step's `with:` block.

No preflight. Actions never touch the cluster.
