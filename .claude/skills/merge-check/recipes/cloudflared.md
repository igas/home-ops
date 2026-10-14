# cloudflared

Deployment `network/cloudflare-tunnel` (app-template), 2 replicas, image `docker.io/cloudflare/cloudflared`. A locally-configured tunnel (`tunnel run` with `/etc/cloudflared/config.yaml` from a ConfigMap), QUIC with post-quantum on, `NO_AUTOUPDATE`. Traffic arrives over cloudflared's outbound connections, not the Service.

## Reading the release notes

The GitHub release body is only SHA256 checksums. The real notes are the `RELEASE_NOTES` file at the repo root. Read it, plus the source diff, from the compare API:

```
gh api repos/cloudflare/cloudflared/compare/<old>...<new> --jq '.commits[].commit.message | split("\n")[0]'
gh api repos/cloudflare/cloudflared/compare/<old>...<new> --jq '.files[] | select(.filename=="RELEASE_NOTES" or (.filename|startswith("cmd/cloudflared/"))) | .patch'
```

New flags show up in `cmd/cloudflared/flags/flags.go` and `cmd/cloudflared/tunnel/cmd.go`. Check each one's default and its `EnvVars`.

## Settings that decide which notes matter

- Ingress: one rule, `*.igas.dev` → `https://envoy-external.network.svc.cluster.local:443` with `http2Origin: true` and `originServerName: external.igas.dev`, then `http_status:404`. There are no path rules and no `originRequest.access` block, so notes about Access-protected rules or path matching (e.g. VULN-141859 path normalization in 2026.10.0) skip us.
- No WARP routing or private-network routes, and no quick tunnels. Notes about `tunnel route`, virtual DNS, ICMP or `--hello-world` skip us.
- Changes under `proxy/` and `connection/quic*` do reach us: every request goes through them.

## Cluster state gotcha

Graceful node shutdown leaves old-ReplicaSet pods in `Succeeded` (condition `DisruptionTarget=True`, `TerminationByKubelet`). Select by label and they look like a third, not-ready replica. Judge health from `kubectl -n network get deploy cloudflare-tunnel` instead. The leftover pod is harmless, and deleting it is optional.
