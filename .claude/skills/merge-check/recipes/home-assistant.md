# home-assistant

Deployment `default/home-assistant` (app-template), one replica. The `ghcr.io/home-operations/home-assistant` tag is pinned in `kubernetes/apps/default/home-assistant/app/helmrelease.yaml`. `/config` and `/config/.venv` sit on `ceph-block` PVCs backed up by VolSync, so a pending rook-ceph or Ceph `hold` is a lower-layer hold for every HA bump.

HA is CalVer: `YYYY.M.x` → `YYYY.(M+1).0` arrives as `type/minor`, but each monthly `.0` ships a "Backward-incompatible changes" section. Treat it as a major for review purposes.

## Release notes

The GitHub release body links to the blog. WebFetch truncates the blog, so read the raw source instead:

```
f=$(gh api "repos/home-assistant/home-assistant.io/contents/source/_posts?ref=current" --jq '.[].name' | grep 'release-YYYYMM')
gh api "repos/home-assistant/home-assistant.io/contents/source/_posts/$f?ref=current" -H "Accept: application/vnd.github.raw" > ha.md
awk '/Backward-incompatible changes/,0' ha.md | grep '^{% details'
```

Then check the regressions people reported against the new version, and the next patch release's fixes:

```
gh search issues --repo home-assistant/core "YYYY.M" --created ">=<release date>" --sort reactions --limit 20
gh api repos/home-assistant/core/releases/tags/YYYY.M.1 --jq .body
```

## Which notes touch us

Read the live config, not the repo; integrations are UI-configured and live in `/config/.storage`. `kubectl exec` needs `-i` for a heredoc:

```
P=$(kubectl -n default get pod -l app.kubernetes.io/name=home-assistant --field-selector=status.phase=Running -o name)
kubectl -n default exec -i $P -- python3 - <<'EOF'
import json; s='/config/.storage/'
print(sorted({e['domain'] for e in json.load(open(s+'core.config_entries'))['data']['entries']}))
print([i['issue_id'] for i in json.load(open(s+'repairs.issue_registry'))['data']['issues'] if not i.get('dismissed_version')])
EOF
```

As of 2026-10, there are no `custom_components`. The setup has one admin user and one non-admin user, and no camera entities. The `unifiprotect` config entry exists but has zero devices, so stream and camera regressions skip us. YAML is limited to `automations.yaml` (17 lines) and `scripts.yaml` (143 lines), so grep them for any condition or action a breaking change names. `http` was migrated to `.storage/http` (`yaml_migration_done: true`); its leftover YAML only raises a repair.

## Rollback safety

A recorder schema bump makes rollback one-way. Compare between tags:

```
for t in OLD NEW; do gh api "repos/home-assistant/core/contents/homeassistant/components/recorder/db_schema.py?ref=$t" -H "Accept: application/vnd.github.raw" | grep -m1 '^SCHEMA_VERSION'; done
```

## Newer patch already out

Upstream often ships `.1` before the home-operations image does. Check the mirror before suggesting a wait:

```
T=$(curl -s "https://ghcr.io/token?scope=repository:home-operations/home-assistant:pull" | jq -r .token)
curl -s -H "Authorization: Bearer $T" "https://ghcr.io/v2/home-operations/home-assistant/tags/list?n=5000" | jq -r '.tags[]' | grep '^YYYY.M'
```

## Precedent

onedr0p bumps HA through `ghcr.io/home-operations/home-assistant` too, so `gh pr list -R onedr0p/home-ops --search home-assistant` matches. Check open PRs as well: he often leaves a `.0` open for days.
