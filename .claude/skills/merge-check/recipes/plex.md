# plex

## Actual application release notes

The pms-docker GitHub releases are not the Plex application changelog. Read the official announcement thread, including intermediate builds, and the official downloads payload. Useful read-only endpoints:

- `https://forums.plex.tv/t/plex-media-server/30447/last.json`
- `https://plex.tv/api/downloads/5.json`

The forum's base URL starts with 2013 releases. Its last-page JSON exposed both 1.43.5.11029 and 1.43.5.11079 during #891. The Linux object in the downloads payload uses the capitalized key `computer.Linux`.

## Proxy changes need more than identity health

Plex 1.43.5 changes request locality and security on proxied requests; 11079 also fixes photo transcoding through a proxy. This repo exposes both an external Envoy HTTPRoute and a direct LoadBalancer. A successful `/identity` probe does not verify authenticated proxy playback or locality classification.

No validated read-only proxy/authentication compatibility preflight exists yet. Keep this recipe gap explicit instead of modifying user sessions or initiating real playback during merge-check. Do not copy onedr0p's earlier proxy tuning without checking this repo's route and client behavior.
