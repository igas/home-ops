# intel-gpu-resource-driver

DRA driver for the Intel iGPU (`kube-system`, layer 2). Chart `oci://ghcr.io/intel/intel-gpu-resource-driver-chart`, bundling NFD as a subchart.

## Release notes

- Upstream tags are prefixed per driver: `gpu-vX.Y.Z` in `intel/intel-resource-drivers-for-kubernetes`. Gaudi and QAT releases share the repo; ignore them.
- Release bodies are short "Highlights". Read the commits with `gh api repos/intel/intel-resource-drivers-for-kubernetes/compare/gpu-v<old>...gpu-v<new>`.
- Check the NFD subchart version in `Chart.yaml` dependencies. A bump there is a separate app to read.

## Cluster-specific settings

- `kubeletPlugin.healthMonitoring.enabled: false`: changes to xpumd (socket name, health taints driven by xpumd) do not apply here.
- No VFIO or adminAccess claims. Changes to driver rebinding and VFIO only matter if that changes.
- The kubelet-plugin runs only on GPU nodes (k8s-master-01, k8s-worker-02). NFD runs on all four.

## Cluster state

```bash
kubectl -n kube-system get helmrelease intel-gpu-resource-driver
kubectl -n kube-system get pods -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.containers[*].image}{"\n"}{end}' | grep intel-gpu
kubectl get resourceclaims -A   # consumers; Plex is the only one today
```

Restarting the plugin leaves running containers alone, because CDI injection already happened. Changes to claim preparation take effect the next time a consumer restarts, so check Plex hardware transcoding after its next rollout.
