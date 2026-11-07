# changedetection

The application and Browserless share a pod. Review their image PRs separately and avoid combining rollouts; use [browserless.md](browserless.md) for browser rendering changes. The app stores watch state in `/datastore` and connects to the browser over localhost.

Release 0.60.10 changes PDF fetching/checksums and retained originals, proxy credential handling, notification regex timeouts and Jinja validation. It also switches the image build to uv; do not infer a new runtime command from that build-tool change alone.

Read target-version issue bodies before dismissing notification behavior. On #895, upstream #4619 remained open for Markdown-to-HTML notifications with multiple destinations. Reports #4607 and #4620 concerned paused-watch reporting and failure counters. A closed issue is not proof its fix shipped in the target tag, and an issue reported on another container packaging is not a reproduction here. Keep actual watch/notification settings unverified unless they were inspected.

Inspect persisted settings without printing URLs or credentials. The running 0.60.9 installation keeps global settings in `/datastore/changedetection.json` and individual settings in `watch.json` below watch directories. Root-level version-named JSON files are backups, not the active watch inventory. A read-only JSON traversal can report notification-format counts, destination counts and ignore_status_codes booleans only. On the 2026-11-01 re-review, global format was htmlcolor, the single watch inherited the system format, no multi-destination configuration was found in those inspected files, and ignore_status_codes was not enabled. This excludes the reported combination for that snapshot, not for future watches. Sending a real notification or rechecking a watch is outside merge-check.

## 0.70 startup and MCP defaults

0.70.1 ships the #4619 per-destination notification fix, #4607 paused-watch reporting fix and #4620 failure-counter fix. 0.70.2 ships the hidden-checkbox fix for #4682. Verify release membership or source ancestry rather than treating issue closure as proof. The broad 0.60.9→0.70.2 compare caps at 300 files; separate release compares returned 130, 240 and 73 files.

The target restores `_after_load` for existing datastores. Read-only checks may additionally report presence booleans for `removepassword.lock`, app_guid, RSS/API tokens and proxies.json validity, never their contents. A stale reset lock would now remove the password on startup. On 2026-11-06 the lock/proxy file were absent and all three identifiers/tokens were present.

MCP's endpoint checks `settings.application.mcp_enabled` before handling requests; absence means off. Anonymous reads require a separate explicit `mcp_anonymous_read` setting. OAuth routes require both MCP enabled and a configured password. Inspect only enablement booleans and token/grant counts. This installation had MCP/anonymous reads off and zero tokens/grants. Schema 34 only preserves an existing OAuth grant's issuer; with no grants, upgrading our schema-33 store does not migrate watch data. Keep MCP enablement separate from the image bump, especially on installations without an app password.
