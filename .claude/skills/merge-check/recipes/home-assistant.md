# home-assistant

Deployment `default/home-assistant` (app-template), one replica. The `ghcr.io/home-operations/home-assistant` tag is pinned in `kubernetes/apps/default/home-assistant/app/helmrelease.yaml`. `/config` and `/config/.venv` sit on `ceph-block` PVCs, so a pending rook-ceph or Ceph `hold` is a lower-layer hold for every HA bump. Verify the `home-assistant` VolSync ReplicationSource's last successful sync before a storage migration. The separate venv cache has no ReplicationSource as of 2026-11; it is rebuilt by the image entrypoint.

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

When inspecting live storage, check its actual structure first. HTTP settings are under `data.stable`. Device records observed in 2026.10.4 use `config_entry_id`, not a `config_entries` list. Reading the wrong field can falsely report zero devices. UI scripts can use device actions with `type` and `domain`, without an `action` or `service` key. Inspect those too.

## MCP API permissions

For releases adding LLM APIs or tools, inspect only these non-secret fields in the live `mcp_server` config entry: `all_llm_apis`, `llm_hass_api`, `require_admin`, and `read_only`. Compare the exact target's `mcp_server/__init__.py`, `config_flow.py`, and the affected API's tool registration.

In 2026.11, the new Home Assistant API includes generic action calls, template reads, logs and integration management. An existing `all_llm_apis: true` entry automatically exposes newly registered APIs to its authorized clients. `require_admin: true` restricts who connects, not what their tools can do. Migration adds `read_only: false` to existing entries. To preserve the earlier control scope, the operator can turn off All LLM APIs and explicitly select Assist before merging; its API ID stays `assist`, while its display name becomes Device control. Read-only mode also removes the intended light/script controls, so it is not an equivalent replacement. Verify choices again after upgrade. Never change these settings during merge-check.

## Monthly migration checks

For 2026.11, compare the entity-name migration with stored dashboards. Unnamed cards now prepend device names; explicit card names preserve compact labels. Entity IDs stay unchanged. Check custom-card updates, templates using `friendly_name`, and the minimum frontend browser versions against registered mobile clients.

Check the complete changelog for installed integrations as well as the breaking-change section. For example, 2026.11 deprecates Overkiz low-speed cover entities outside that section; inspect their actual registry entries and callers before recommending migration. MQTT's no-`unique_id` change does not affect registered entities with unique IDs. A person startup-timeout report, core#190534, was traced to thousands of entries in `known_devices.yaml`; check that file rather than assuming every installation has the same regression.

## Rollback safety

A recorder schema bump makes rollback one-way. Compare between tags:

```
for t in OLD NEW; do gh api "repos/home-assistant/core/contents/homeassistant/components/recorder/db_schema.py?ref=$t" -H "Accept: application/vnd.github.raw" | grep -m1 '^SCHEMA_VERSION'; done
```

An unchanged recorder schema does not prove that `.storage` migrations can be downgraded. Keep a pre-upgrade `/config` backup. `kubectl exec -- python3` uses the system interpreter, even when HA runs inside `/config/.venv`; inspect the entrypoint and `/config/.venv/.image` before drawing conclusions about dependency-install behavior.

## Newer patch already out

Upstream often ships `.1` before the home-operations image does. Check the mirror before suggesting a wait:

```
T=$(curl -s "https://ghcr.io/token?scope=repository:home-operations/home-assistant:pull" | jq -r .token)
curl -s -H "Authorization: Bearer $T" "https://ghcr.io/v2/home-operations/home-assistant/tags/list?n=5000" | jq -r '.tags[]' | grep '^YYYY.M'
```

## Precedent

onedr0p bumps HA through `ghcr.io/home-operations/home-assistant` too, so `gh pr list -R onedr0p/home-ops --search home-assistant` matches. Check open PRs as well: he often leaves a `.0` open for days.
