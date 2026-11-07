# qbittorrent

## Compare the libtorrent build

This repo uses `ghcr.io/home-operations/qbittorrent`. onedr0p uses `qbittorrent-libtorrentv1`, so his merged version is not exact binary precedent. Read the running build through the local WebAPI without changing torrent state:

```sh
kubectl -n default exec deploy/qbittorrent -c app -- curl -fsS http://localhost:80/api/v2/app/buildInfo
```

On #879 the running 5.2.4 image reported libtorrent 2.0.15.0. New 5.3.0 issue reports #25125, #25130 and #25123 used libtorrent 2.1.2; do not present them as reproduced in this container. Check the target build separately. The executable is not necessarily named `qbittorrent-nox` on PATH.

The 2026-11-07 review identified the pinned #879 candidate, not just its mutable tag. Index `sha256:5a858e61f94cf2712391db32ed03556576c700858f3e62c4c6fcde262443ebd8` selects amd64 manifest `sha256:32727336d90bc43a1bda5e7107e33abff81ef21057f3bfcbf8a2106682a36ccf`. Its `/app/qbittorrent-nox` has SHA256 `006071fb46f4223de042d1b7fed877e5d8ea9ed11066779c92ab889a658cc30b` and contains `libtorrent/2.1.2.0`. This changes libtorrent from 2.0 to 2.1 as well as qBittorrent. The [build Dockerfile](https://github.com/home-operations/containers/blob/78ea8291f0cda5c09fc99673038f8efc84807942/apps/qbittorrent/Dockerfile) selects `libtorrent_2_1`. Inspect OCI config/history and read the binary from its verified layer locally; execution is unnecessary for build identification. Select the install layer by its history, not a fixed layer offset. OCI layers can use zstd rather than gzip.

Read [libtorrent 2.1.0](https://github.com/arvidn/libtorrent/releases/tag/v2.1.0) through the candidate's version too. The new default pread disk backend, disk-cache behavior and resume-data changes matter on this repo's NFS downloads. [qBittorrent #25202](https://github.com/qbittorrent/qBittorrent/issues/25202) reports download-time OOM with 5.3.0/libtorrent 2.1.2 and improvement with a 2.0.15 build. This is relevant build-family evidence, not reproduction in our image or proof that our 18Gi limit is insufficient. Re-read [#25130](https://github.com/qbittorrent/qBittorrent/issues/25130) comments: a later reporter also tried lt12, while a maintainer distinguishes preallocation behavior from a separate 2.1.x issue. Do not reduce the whole report to its original build version.

## Stateful changes

The 5.3.0 notes change torrent backup management, obsolete setting handling, cross-site/proxy-auth checks, and methods accepted by some WebAPI endpoints. Check API consumers as well as WebUI access. Sonarr#9211 fixes a longstanding single-file root_path import issue, not a proven 5.3-only regression.

Re-read issue comments before assigning headless-image exposure. #25125's later stack goes through `PropertiesWidget` and `TorrentContentModel`, a desktop GUI path, so it is not itself a demonstrated headless-container crash. Separate [#25158](https://github.com/qbittorrent/qBittorrent/issues/25158) reports a WebUI-container deadlock when TorrentBackupDirectory sits beneath a watched directory. Check that configuration relationship separately; different libtorrent versions do not dismiss the backup-directory report.

Use a filtered read-only preferences query to check the current backup/watch relationship without exposing credentials:

```sh
kubectl -n default exec deploy/qbittorrent -c app -- sh -c 'curl -fsS --max-time 10 http://localhost:80/api/v2/app/preferences | jq "with_entries(select(.key | test(\"export|backup|watch|scan\")))"'
```

In 5.2.4 the relevant keys are `export_dir`, `export_dir_fin` and `scan_dirs`, not `torrent_export_dir`. On 2026-11-07 both export paths were empty and `scan_dirs` was `{}`, so #25158's watched-directory precondition was absent. This excludes that specific configuration, not all candidate backup/state behavior.

[#25199](https://github.com/qbittorrent/qBittorrent/issues/25199) documents Basic-auth session churn after restart for *arr clients holding stale cookies. It already affects 5.2, but 5.3's default 15-session limit can evict other clients. API keys avoid that path; [#25207](https://github.com/qbittorrent/qBittorrent/pull/25207) was still open on 2026-11-07. Inspect client authentication before assigning exposure. Do not send login requests or change production client settings during review.

## Recipe gap

No validated single-Pod procedure exists for isolated target-build active-download memory, completion accounting and resume-state compatibility. Never mount the production config or download volume into a test or start live torrent operations during merge-check. Build identification is now complete for the pinned #879 amd64 image, but a startup/version query alone cannot validate download behavior or NFS performance. An isolated fixture and bounded memory/completion checks are still needed.
