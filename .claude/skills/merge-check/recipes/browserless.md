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
