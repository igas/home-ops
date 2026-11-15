# browserless

Browserless is the `browser` container in the changedetection pod, not a separate HelmRelease. Check that container's image and readiness alongside the app container. The application connects over `ws://localhost:3000`.

## Screen dimensions and browser libraries

Release 2.58.0 changes default headless screens to desktop dimensions. That can change rendered watch content without failing a container probe. Read intermediate releases for Playwright/browser library changes, launch-argument handling and WebSocket timeout behavior. Preserve the existing browser UID, writable root and shared-memory mount when judging compatibility.

The upstream screen-change tests in browserless#5638 explicitly distinguish `window.screen` from the page viewport. Setting a viewport alone does not preserve the old screen dimensions. The new default is at least 1920×1080 unless an explicit `--screen-info` is supplied. Both CDP and Playwright paths change. In the later range, 2.58.3 moves Node from 24 to 26 and 2.59.0 passes connection requests to opt-in context policies; the stock policy still returns null. A minor app bump therefore includes a major embedded runtime change.

## Client transport and 2.60

For 2.60.0, inspect the tagged `package.json` and lockfile as well as the generated release browser table. The table still lists the previous library versions, while the packages make Playwright 1.65 the default, retain 1.61 through 1.64, and retire 1.60. Upstream #5664 describes the actual package changes.

Check the application's connection method before treating different Playwright versions as a protocol mismatch. changedetection 0.70.2 uses `connect_over_cdp` at the configured root WebSocket URL, not native Playwright `connect`. The installed Python client was 1.56.0 during the 2026-11-07 review. The server's native Playwright version list alone therefore does not establish a broken connection. The browser/screen changes still need representative rendering verification. Read-only watch inspection can report fetch-backend counts and error presence without exposing watch URLs or content; this installation's single watch used `html_webdriver` and already had an error before the browser upgrade.

## Recipe gap

No validated single-Pod, read-only old/new rendering comparison exists as of #854. Use an isolated browser profile and representative page rather than production watch/config storage when designing one. Do not create or modify a real changedetection watch as a merge-check preflight. A healthy sidecar or a TCP probe does not establish unchanged rendering behavior.

## 2.61 through 2.63.1

- [#5667](https://github.com/browserless/browserless/pull/5667) adds admission and lifecycle accounting to browser launches, queues, request handlers and cleanup. New SDK workers start in `running`; withdrawal and deadline-free ordered shutdown require explicit SDK calls. The stock CLI still calls forced `stop()` on signals. Distinguish these paths before predicting an unbounded Kubernetes shutdown.
- [2.63.0 authentication changes](https://github.com/browserless/browserless/blob/v2.63.0/src/token.ts) retain tokenless operation when `TOKEN` is unset. Strict function-valued route policies are opt-in. Check effective container environment and the root CDP route before requiring new credentials. In #952, `TOKEN`, `TOKEN_HEADER` and `STRICT_TOKEN_USE` were unset.
- The [2.63.1 release body](https://github.com/browserless/browserless/releases/tag/v2.63.1) omits runtime dependency changes present in the tag comparison: Puppeteer 25.16.0 to 25.17.0, ws 8.22.1 to 8.22.2, and an Ubuntu base digest refresh. Node changes from 26.13.0 to 26.13.1 across the full range. Read package.json and its lockfile.
- Playwright stays at 1.65.0 across this range. The Chromium Dockerfile installs its browser through that pinned Playwright package, so a Puppeteer release's Chrome version alone does not establish a Chromium engine upgrade in this image.
- Extend the missing isolated comparison to cover the installed changedetection Python client's tokenless root-CDP connection, fresh context/page creation, representative DOM extraction, and session close followed by a second connection. This checks the new launch/cleanup path without touching watch state. As of #952, this candidate preflight remains unrun.
- In #952, Kubernetes and `/worker-health` were healthy, but the single unpaused `html_webdriver` watch retained an error mentioning a filter. Record this separately from browser health. A persisted error does not establish a transport failure or its cause; classify it before using the watch as a successful rendering baseline.
