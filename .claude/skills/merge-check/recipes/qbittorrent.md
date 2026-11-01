# qbittorrent

## Compare the libtorrent build

This repo uses `ghcr.io/home-operations/qbittorrent`. onedr0p uses `qbittorrent-libtorrentv1`, so his merged version is not exact binary precedent. Read the running build through the local WebAPI without changing torrent state:

```sh
kubectl -n default exec deploy/qbittorrent -c app -- curl -fsS http://localhost:80/api/v2/app/buildInfo
```

On #879 the running 5.2.4 image reported libtorrent 2.0.15.0. New 5.3.0 issue reports #25125, #25130 and #25123 used libtorrent 2.1.2; do not present them as reproduced in this container. Check the target build separately. The executable is not necessarily named `qbittorrent-nox` on PATH.

## Stateful changes

The 5.3.0 notes change torrent backup management, obsolete setting handling, cross-site/proxy-auth checks, and methods accepted by some WebAPI endpoints. Check API consumers as well as WebUI access. Sonarr#9211 fixes a longstanding single-file root_path import issue, not a proven 5.3-only regression.

Re-read issue comments before assigning headless-image exposure. #25125's later stack goes through `PropertiesWidget` and `TorrentContentModel`, a desktop GUI path, so it is not itself a demonstrated headless-container crash. Separate [#25158](https://github.com/qbittorrent/qBittorrent/issues/25158) reports a WebUI-container deadlock when TorrentBackupDirectory sits beneath a watched directory. Check that configuration relationship separately; different libtorrent versions do not dismiss the backup-directory report.

## Recipe gap

No validated single-Pod procedure exists for isolated target-build torrent-state compatibility. Never mount the production config or download volume into a test or start live torrent operations during merge-check. An isolated fixture and target build identification are needed before treating the version-specific state/crash concerns as verified.
