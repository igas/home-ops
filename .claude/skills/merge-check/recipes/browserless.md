# browserless

Browserless is the `browser` container in the changedetection pod, not a separate HelmRelease. Check that container's image and readiness alongside the app container. The application connects over `ws://localhost:3000`.

## Screen dimensions and browser libraries

Release 2.58.0 changes default headless screens to desktop dimensions. That can change rendered watch content without failing a container probe. Read intermediate releases for Playwright/browser library changes, launch-argument handling and WebSocket timeout behavior. Preserve the existing browser UID, writable root and shared-memory mount when judging compatibility.

## Recipe gap

No validated single-Pod, read-only old/new rendering comparison exists as of #854. Use an isolated browser profile and representative page rather than production watch/config storage when designing one. Do not create or modify a real changedetection watch as a merge-check preflight. A healthy sidecar or a TCP probe does not establish unchanged rendering behavior.
