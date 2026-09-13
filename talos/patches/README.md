# Talos Patching

This directory contains Kustomization patches that are added to the talhelper configuration file.

<https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/system-configuration/patching>

## Patch Directories

Under this `patches` directory, there are several sub-directories that can contain patches that are added to the talhelper configuration file.
Each directory is optional and therefore might not created by default.

- `global/`: patches that are applied to both the controller and worker configurations
- `controller/`: patches that are applied to the controller configurations
- `worker/`: patches that are applied to the worker configurations
- `${node-hostname}/`: patches that are applied to the node with the specified name

## Controller patches on Talos 1.14

- `controller/kubernetes.yaml`: multi-document Kubernetes kinds (API server, admission control, controller manager, scheduler, kube-proxy).
- `controller/kube-etcd-encryption.yaml`: re-adds `KubeEtcdEncryptionConfig` in the running cluster's shape; reads `${secretboxEncryptionSecret}` from `../talenv.sops.yaml`.
- `controller/cluster.yaml`: v1alpha1 fields that have no document kind yet, or whose kind the pinned talhelper cannot decode.

Patch files are env-substituted by talhelper, so a literal `$patch` is written `$$patch`.
