# coredns

Chart `ghcr.io/coredns/charts/coredns`, pinned twice: `kubernetes/apps/kube-system/coredns/app/ocirepository.yaml` and `bootstrap/helmfile.d/01-apps.yaml`. Both must move together. The bootstrap release reads its values from the HelmRelease through `templates/values.yaml.gotmpl`, so values can't drift between them. `00-crds.yaml` doesn't render CoreDNS.

## Corefile exposure

Our Corefile uses `kubernetes ... { pods verified }`, `autopath @kubernetes` and `cache { prefetch 20; serve_stale }`, forwarding to `/etc/resolv.conf`, on an IPv4-only cluster. That combination is the one hit by coredns/coredns#8390: from 1.14.3 to 1.14.6, search-expanded A queries got NXDOMAIN or empty answers while AAAA was still cached, and Go and glibc clients silently fell back to IPv6-only. 1.14.7 fixed it. When reading app release notes, look closely at changes to `autopath`, `cache` (prefetch, serve_stale) and `forward`, and at changes to the order plugins run in. Bugs there show up as intermittent resolution failures, not crashes, and dig with an absolute name won't reproduce them.

## securityContext

The image runs as the distroless nonroot user (uid/gid 65532) since 1.11.0, numeric in the image config since 1.14.7. The binary has `cap_net_bind_service` as a file capability. Kubelet has `seccompDefault: true`. A chart that adds `runAsNonRoot`/`runAsUser: 65532`/`RuntimeDefault` changes nothing at runtime. To check the image user without pulling:

```
docker buildx imagetools inspect mirror.gcr.io/coredns/coredns:<tag> --format '{{json .Image}}' | jq '.["linux/amd64"].config.User // .config.User'
talosctl -n 192.168.6.2 get kubeletspec -o yaml | grep seccompDefault
```

A change of uid, or a dropped file capability, would need a preflight: a throwaway Pod with the new image and securityContext, serving a minimal `.:53 { whoami }` Corefile, then a `dig` against its pod IP.

## Precedent

onedr0p's Corefile is close to ours and he tracks CoreDNS closely, including holding it back for #8390 with a disabled Renovate rule. If his repo has a disabled CoreDNS package rule or a pinned image tag, find out why before merging.
