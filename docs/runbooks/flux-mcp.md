# Debugging Flux with the MCP server

The cluster runs the Flux MCP server (`flux-operator-mcp` in `flux-system`, added in #710). It lets Claude Code inspect Flux with the server's own tools: status of Kustomizations and HelmReleases, dependency traces, events, controller logs. Since #711 it is served on the internal gateway at `https://flux-mcp.igas.dev/mcp`, behind an API key.

## How requests reach it

- The chart's HTTPRoute attaches to the `https` listener of `envoy-internal` (`192.168.6.7`), so the name resolves only on the LAN and TLS comes from the wildcard certificate.
- The `flux-operator-mcp` SecurityPolicy enforces API-key auth on that route. Envoy reads the key from the `x-api-key` header and returns 401 when it is missing or wrong. It strips the header before forwarding.
- The key lives in the 1Password item `flux-operator-mcp` (vault `Kubernetes`, field `FLUX_MCP_API_KEY`). The ExternalSecret copies it into the Secret `flux-operator-mcp-secret` under the client ID `claude-code`.
- The chart's NetworkPolicy admits port 9090 only from `flux-system` and `network`, where the Envoy proxies run.

## Connect

1. Open a shell in the repo. mise sets `FLUX_MCP_API_KEY` from `.mise.toml` by running `op read 'op://Kubernetes/flux-operator-mcp/FLUX_MCP_API_KEY'`. It caches the result for a day, so 1Password asks once a day, not for every new tab. If `op` fails (locked, approval dismissed), the variable is empty and that empty value is also cached for the day. Clear it with `rm -rf ~/Library/Caches/mise/exec`, then `cd .` to reload. The cache is plaintext under `~/Library/Caches/mise/exec`.

2. Start Claude Code in the repo (or run `/mcp` in a running session to reconnect). `.mcp.json` points the `flux-operator-mcp` entry at the gateway URL and sends `x-api-key: ${FLUX_MCP_API_KEY}`. Approve the server the first time Claude Code asks.

3. Ask in plain terms, for example "which Kustomizations or HelmReleases are not Ready, and why?" or "trace the HelmRelease plex in media".

Without the variable, the header goes out empty, Envoy answers 401 and the entry shows as failed in `/mcp`. Every other server is unaffected.

## What it can and cannot do

The server runs with `--read-only=true`. Its ServiceAccount is bound to `cluster-admin`, so read-only mode is the only thing stopping writes: the reconcile, suspend, resume, apply, patch, delete and install-instance tools are not registered at all. To act on what it finds, run `flux` or `kubectl` yourself, or `task reconcile`.

Secret values come back masked (`--mask-secrets=true`).

## Rotate the key

Generate a new value in the 1Password item, force the sync, clear the cached key with `rm -rf ~/Library/Caches/mise/exec`, then open a new shell in the repo and reconnect with `/mcp`:

```sh
kubectl -n flux-system annotate externalsecret flux-operator-mcp force-sync="$(date +%s)" --overwrite
```

Envoy Gateway picks up the changed Secret on its own.

## When it does not connect

- Check auth from the shell. The first request should return 401, the second a JSON-RPC result:

  ```sh
  curl -si https://flux-mcp.igas.dev/mcp | head -1
  curl -si https://flux-mcp.igas.dev/mcp \
    -H "x-api-key: $FLUX_MCP_API_KEY" \
    -H 'content-type: application/json' \
    -H 'accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
  ```

- 401 with the header set: the key in your shell does not match the Secret. Check `kubectl -n flux-system get externalsecret flux-operator-mcp` is `SecretSynced`.
- 404 or 500: check `kubectl -n flux-system get httproute,securitypolicy flux-operator-mcp -o yaml` for `Accepted` conditions. A SecurityPolicy whose Secret is missing fails closed.
- 503 or timeouts: check the pod with `kubectl -n flux-system logs deploy/flux-operator-mcp`. If every route on the internal gateway fails, look at the Envoy Gateway controller logs.
- To bypass the gateway entirely, run `task flux-mcp` and send the curl above to `http://localhost:9090/mcp`.
