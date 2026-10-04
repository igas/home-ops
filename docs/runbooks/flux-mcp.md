# Debugging Flux with the MCP server

The cluster runs the Flux MCP server (`flux-operator-mcp` in `flux-system`, added in #710). It lets Claude Code inspect Flux with the server's own tools: status of Kustomizations and HelmReleases, dependency traces, events, controller logs. It is reachable only by port-forward. There is no HTTPRoute.

## Connect

1. In one terminal, from the repo root:

   ```sh
   task flux-mcp
   ```

   This forwards `localhost:9090` to the server's Service and stays in the foreground. Stop it with Ctrl-C when you are done.

2. Start Claude Code in the repo (or run `/mcp` in a running session to reconnect). `.mcp.json` points the `flux-operator-mcp` entry at `http://localhost:9090/mcp`. Approve the server the first time Claude Code asks.

3. Ask in plain terms, for example "which Kustomizations or HelmReleases are not Ready, and why?" or "trace the HelmRelease plex in media".

Without the port-forward, the `flux-operator-mcp` entry shows as failed in `/mcp`. Every other server is unaffected.

## What it can and cannot do

The server runs with `--read-only=true`. Its ServiceAccount is bound to `cluster-admin`, so read-only mode is the only thing stopping writes: the reconcile, suspend, resume, apply, patch, delete and install-instance tools are not registered at all. To act on what it finds, run `flux` or `kubectl` yourself, or `task reconcile`.

Secret values come back masked (`--mask-secrets=true`).

## When it does not connect

- `task flux-mcp` fails with `service "flux-operator-mcp" not found`: check `flux get hr -n flux-system flux-operator-mcp` and `flux get ks flux-operator-mcp`. The Kustomization waits on `flux-operator`.
- The port-forward is up but Claude Code reports a connection error: check the pod with `kubectl -n flux-system logs deploy/flux-operator-mcp`. It logs `read-only mode set to true` on start.
- Port 9090 is already in use locally: free it. `.mcp.json` hard-codes the port, so forwarding elsewhere needs a matching edit there.
