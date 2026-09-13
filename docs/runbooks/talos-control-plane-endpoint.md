# Moving the Talos control-plane endpoint

`cluster.controlPlane.endpoint` is not only the address clients dial. Talos also
feeds it to kube-apiserver as `--service-account-issuer` and `--api-audiences`.
Change it naively and every service account token is re-issued under a new
issuer, while the old ones stop validating until they rotate.

This runbook covers how that coupling was broken, and the phases for moving the
issuer afterwards. Written for the 2026-09 move from `https://192.168.6.1:6443`
(master-01's own address) to `https://k8s.igas.dev:6443`, issue #736.

## Why the flags can be pinned

Read from the Talos v1.14.0 sources on 2026-09-13. Re-check against the tag the
cluster runs before trusting any of it.

Talos builds kube-apiserver's arguments in
`internal/app/machined/pkg/controllers/k8s/control_plane_final.go`. The derived
values come from the `secrets.KubernetesRoot` issuer URL, which on the v1alpha1
path is the control-plane endpoint verbatim (`serviceAccountShim.IssuerURL` in
`pkg/machinery/config/types/v1alpha1/v1alpha1_k8s_bridge.go`, whose
`AcceptedIssuers()` returns nil).

`KubeAPIServerConfig.extraArgs` is merged over that. Neither
`service-account-issuer` nor `api-audiences` is on that merge's denylist, and
`MergeOverwrite` is the zero value of the policy type in `pkg/argsbuilder`, so an
explicit value wins. A value list renders one `--flag=value` per entry
(`argsbuilder_args.go`), which is what both flags need: `--service-account-issuer`
is repeatable, the first entry signs new tokens and the rest stay accepted for
verification.

So pinning both flags in `patches/controller/kubernetes.yaml` decouples them
from the endpoint, which is what leaves the endpoint free to move.

### The purpose-built document, and why it is not used

Talos 1.14 ships `KubeServiceAccountConfig`
(`pkg/machinery/config/types/k8s/service_account.go`) with exactly these fields:
`issuer.issuerURL`, `accepted.issuers`, `accepted.audiences`, plus
`accepted.publicKeys` for signing-key rotation. It is the right home for this.

talhelper 3.1.17 cannot render it. It vendors Talos machinery `v1.14.0-alpha.2`,
which predates the type, and fails with
`error decoding document v1alpha1/KubeServiceAccountConfig/ (line 1): "KubeServiceAccountConfig" "v1alpha1": not registered`
(the same limitation as `KubeNodeConfig` and `KubeCoreDNSConfig`, see
`.claude/skills/merge-check/recipes/talos.md`). Adopting it also means deleting
the generated `.cluster.serviceAccount`, because the document refuses to load
next to it, and carrying the service account private key through
`talenv.sops.yaml`. Revisit when talhelper ships machinery >= 1.14.0.

## Why the DNS name, not the VIP

`k8s.igas.dev` resolves on the LAN to the three master addresses. Checked
2026-09-13 with `dig k8s.igas.dev`: three A records, 192.168.6.1/2/3, TTL 60,
answered authoritatively by the router at 192.168.1.1. The record is not managed
by this repo.

`192.168.6.9`, the `kube-api` LoadBalancer in
`kubernetes/apps/kube-system/cilium/app/networks.yaml`, was rejected:

- it depends on Cilium, its BGP session and LB-IPAM being up, which is a
  bootstrap circularity for the address nodes use to reach the API server;
- it is not in the apiserver certificate's SANs (the DNS name already is), so it
  would need a SAN change and a certificate roll first;
- `k8s.igas.dev` does not resolve to it today, so it buys nothing the name does
  not already give.

The DNS name adds one dependency. `StaticEndpointController` resolves the
endpoint hostname and returns an error if resolution fails, so node DNS
(192.168.1.1, per `patches/network/dns.yaml`) is now in the path of the
control-plane endpoint resource and KubePrism's upstream list. Node-local traffic
still goes through KubePrism on 127.0.0.1:7445, so a DNS outage does not by
itself cut kubelet off from the API server. `talosctl kubeconfig` also starts
emitting `server: https://k8s.igas.dev:6443`, which puts the same DNS in the
admin path.

## Phase 1: move the endpoint, pin the issuer (applied 2026-09-13, #736)

`talconfig.yaml` moves to `https://k8s.igas.dev:6443`, and
`patches/controller/kubernetes.yaml` pins both flags with
`https://192.168.6.1:6443` first and `https://k8s.igas.dev:6443` second. The only
change kube-apiserver sees is the second accepted issuer and audience. Every
existing token keeps validating, and newly minted tokens still carry the old
issuer.

```sh
task talos:generate-config
# expect two hunks per master: controlPlane.endpoint, and the two extraArgs
# lists under KubeAPIServerConfig. Worker nodes get the endpoint hunk only.
```

Maintenance window: each apply restarts kube-apiserver on that node, so the
cluster runs on two of three API servers for a minute or so per master. No
workload is interrupted, but avoid running it alongside a Talos or Kubernetes
upgrade, a Rook rebalance, or anything else that needs a full control plane.
Apply one node at a time, waiting for the previous one to come back.

```sh
task talos:apply-node IP=192.168.6.1     # then .2, then .3, then .12 (worker-02)
talosctl -n 192.168.6.1 get staticpodstatus            # kube-apiserver Ready
talosctl -n 192.168.6.1 get apiserverconfig -o yaml | grep -E 'service-account-issuer|api-audiences'
kubectl get --raw /readyz
```

`k8s-worker-02` (192.168.6.12) carries the endpoint too and has to be applied,
or the config on disk keeps disagreeing with `talconfig.yaml`. It runs no
control-plane static pod, so its apply only re-points kubelet's endpoint list.

Expected on every master afterwards:

```
- --api-audiences=https://192.168.6.1:6443
- --api-audiences=https://k8s.igas.dev:6443
- --service-account-issuer=https://192.168.6.1:6443
- --service-account-issuer=https://k8s.igas.dev:6443
```

Watch for auth fallout, of which there should be none: `flux get all -A`, plus
the Cilium, Rook and External Secrets pods. The apiserver exported no 401 series
at all on 2026-09-13, so any output here is a signal rather than a level to
compare:

```sh
kubectl get --raw /metrics | grep -E '^apiserver_request_total\{.*code="401"'
```

`talosctl get staticpodstatus` lags the apply: the READY column blanks while the
static pod re-renders, and `kubectl wait --for=condition=Ready` can return
against the pod that is about to be replaced. Confirm the node picked the change
up before moving on, then wait for READY to come back True:

```sh
talosctl -n 192.168.6.1 get staticpod kube-apiserver -o yaml | grep -c 'service-account-issuer=https://k8s.igas.dev'
```

Rollback: revert the commit, `task talos:generate-config`, re-apply the nodes.
Phase 1 never changes the issuer that tokens were signed with, so the rollback is
as inert as the change.

What the 2026-09-13 run saw: four nodes applied without a reboot, each master's
kube-apiserver restarting once and coming back Ready, all four nodes reporting
`endpoint: https://k8s.igas.dev:6443`, every Flux resource still ready, no pod
out of Running, and no `apiserver_request_total{code="401"}` series. The
`NotificationDispatchFailed` events carrying `401 Bad credentials` are a
flux-notification GitHub token problem against the wrong repo and predate the
apply.

## Phase 2: move the issuer (optional, not done)

Only when the issuer itself should follow the endpoint. Swap the order of both
lists in `patches/controller/kubernetes.yaml` so `https://k8s.igas.dev:6443` is
first, then apply the masters the same way. New tokens are signed with the new
issuer and default to the new audience; tokens signed with the old issuer keep
validating because it stays in the list.

Rollback: swap the order back and re-apply. Tokens minted in between stay valid
only as long as the new issuer stays listed, so do not drop entries as part of a
rollback.

## Phase 3: drop the pins (only after phase 2 has settled)

Deleting both `extraArgs` lists hands the flags back to Talos, which derives one
issuer and one audience from the endpoint. That is a narrowing, not a no-op: the
two-entry lists become single entries and the old issuer stops being accepted.
Anything still holding a token signed with it gets a 401. Hence the
prerequisites, each verified rather than assumed:

- Every projected token has rotated. kubelet refreshes at 80% of a token's TTL;
  allow at least 48h after phase 2 and confirm on a long-lived pod:
  ```sh
  kubectl exec -n <ns> <pod> -- cat /var/run/secrets/kubernetes.io/serviceaccount/token \
    | cut -d. -f2 | base64 -d 2>/dev/null | jq .iss
  ```
- No legacy Secret-backed service account tokens exist, because those never
  rotate:
  ```sh
  kubectl get secrets -A --field-selector type=kubernetes.io/service-account-token
  ```
  Empty on 2026-09-13. If any exist, delete them and let them be recreated, or
  keep the old issuer listed indefinitely.

Phase 3 also retires the prose that explains the pins. Update all of it together:
the comment above `endpoint:` in `talos/talconfig.yaml`, the pointer in
`talos/patches/README.md`, the `cluster.controlPlane.endpoint` paragraph in
`.claude/skills/merge-check/recipes/talos.md`, and this runbook.

Rollback: restore the lists with the old issuer second and re-apply.
