# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Talos Linux + Kubernetes + Flux GitOps cluster for home operations. It uses MakeJinja templating to generate cluster configurations, SOPS/AGE for secret encryption, and Flux CD for GitOps-driven deployments.

**Cluster**: 3 control plane nodes (k8s-master-01/02/03) + 2 worker nodes (k8s-worker-01/02) running Talos Linux with Kubernetes.

**Domain**: Use `igas.dev` for all hostnames and configurations. Do not use `turbo.ac`.

**Timezone**: Use `Australia/Sydney` for any time zone related code or configuration.

## Common Commands

All commands use the Task runner (`task`). Run `task --list` to see all available tasks.

### Bootstrap & Configuration
```bash
task init                    # Initialize config files from templates
task configure               # Render templates and validate configs
task reconcile               # Force Flux to reconcile all resources
```

### Talos Management
```bash
task bootstrap:talos         # Bootstrap new Talos cluster
task bootstrap:apps          # Bootstrap Flux and initial applications
task talos:generate-config   # Regenerate Talos node configs from talconfig.yaml
task talos:apply-node NODE=k8s-master-01   # Apply config to specific node
task talos:upgrade-node NODE=k8s-master-01 # Upgrade Talos on specific node
task talos:upgrade-k8s       # Upgrade Kubernetes version
task talos:reset             # Reset cluster to maintenance mode
```

### Template Management
```bash
task template:tidy           # Archive template files
task template:debug          # Gather cluster resources for debugging
```

## Architecture

### Directory Structure
- **`kubernetes/apps/`** - All Kubernetes applications organized by namespace
- **`kubernetes/components/`** - Reusable Kustomize components (alerts, volsync, sops)
- **`kubernetes/flux/`** - Flux GitOps configuration
- **`talos/`** - Talos Linux configuration (talconfig.yaml, patches, generated clusterconfig)
- **`templates/`** - Jinja2 templates for generating configs (uses MakeJinja)
- **`bootstrap/`** - Initial bootstrap resources (helmfile, 1Password secrets)
- **`.taskfiles/`** - Task runner includes for bootstrap, talos, and template tasks

### Application Pattern
Each application follows this structure:
```
kubernetes/apps/{namespace}/{app-name}/
├── ks.yaml              # Flux Kustomization
└── app/
    ├── helmrelease.yaml   # Flux HelmRelease
    ├── ocirepository.yaml # OCI chart source (or gitrepository.yaml)
    └── kustomization.yaml # Kustomize overlay
```

### Configuration Files
- **`cluster.yaml`** - Main cluster configuration (network CIDRs, domains, IPs)
- **`nodes.yaml`** - Node definitions (hostnames, IPs, disks, roles)
- **`talos/talconfig.yaml`** - Talos cluster configuration (generated from templates)
- **`talos/talenv.yaml`** - Talos and Kubernetes version specifications

### Secret Management
- Secrets are encrypted with SOPS using AGE encryption
- `.sops.yaml` defines encryption rules (Talos secrets fully encrypted, K8s secrets partial)
- 1Password integration via External Secrets Operator for runtime secrets
- Files ending in `.sops.yaml` are encrypted

### Template System
MakeJinja processes `.j2` files from `templates/` directory:
- Custom delimiters: `#{` `}#` for variables, `#%` `%#` for blocks
- Reads configuration from `cluster.yaml` and `nodes.yaml`
- Run `task configure` to regenerate all templated files

## Key Technologies
- **OS**: Talos Linux
- **CNI**: Cilium (with DSR load balancer mode, BGP)
- **GitOps**: Flux CD
- **Secrets**: SOPS/AGE + 1Password + External Secrets
- **Storage**: Rook-Ceph, OpenEBS, CSI-driver-nfs, VolSync
- **Ingress**: Envoy Gateway, Cloudflare Tunnel
- **DNS**: CoreDNS, k8s-gateway, external-dns (Cloudflare)
- **Observability**: kube-prometheus-stack, Grafana, Gatus

## CI/CD
- **flux-local.yaml** - Validates Flux manifests on PRs, generates diffs
- **e2e.yaml** - End-to-end validation (template rendering, CUE validation, Talos config)
- **Renovate** - Automated dependency updates (auto-merges patches/minor versions)

## Network Configuration
- Node CIDR: `192.168.6.0/24`
- Pod CIDR: `10.42.0.0/16`
- Service CIDR: `10.43.0.0/16`
- Internal Gateway (Envoy): `192.168.6.7`
- Cluster DNS Gateway: `192.168.6.8`
- Kube API: `192.168.6.9`
