# Woodpecker CI research

Researched 2026-10-17. Research only. No deployment, credentials, OAuth application or cluster resources were created.

## Findings in brief

- Three current community repositories have concrete Kubernetes deployment configurations with GitOps wiring: `carldanley/homelab`, `jgrecu/home-lab` and `keiretsu-labs/kubernetes-manifests`. All three use the Kubernetes execution backend and a Gitea/Forgejo integration, not GitHub. Details and immutable source links follow.
- A fourth, `Rojikku/home-ops`, explicitly configures GitHub OAuth, but its Woodpecker subtree last changed in December 2023. It is a historical example, not a current installation recipe. `soulwhisper/home-ops` has another example under `.archived`.
- Current official releases are Helm chart **3.7.5** and Woodpecker **3.19.0**, both released 2026-10-07. The official chart uses Kubernetes step Pods, not a Docker socket. GitHub uses an OAuth application. [O1][O2][O3][O4][O11]
- The main local design constraint is workspace storage. This repo configures Ceph block storage but explicitly disables Ceph filesystems. Do not copy an example's `ceph-filesystem` class without a storage decision. [L1]

Public manifests establish deployment intent, not proof that a remote cluster is currently healthy or even running. No remote kubeconfig, CI login or runtime verification was available. Here, "current" means concrete manifests included by GitOps configuration at a recent repository HEAD, not an independently observed live deployment.

## Official Helm and application behavior

### Versions and distribution

The official installation page now points to `oci://ghcr.io/woodpecker-ci/helm/woodpecker`. Chart 3.7.5 declares `appVersion: 3.19.0`, with server subchart 3.0.1 and agent subchart 2.0.1. Chart and application versions are different version streams. Both components are enabled by default. The upstream README says the combined chart is normally sufficient; the agent subchart can also deploy agents in other clusters. [O1][O2][O3]

Source was inspected at Helm commit `e0e8434fc2badff018e8ff557d4d27a376dfa555`. The application release and Kubernetes security flags were checked at tag `v3.19.0`. Moving official documentation links describe the currently published docs; recheck them before implementation. [O2][O3][O8]

### Server and execution backend

The server provides the UI, forge integration and scheduling. Agents connect to `woodpecker-server:9000` by default. The chart explicitly sets `WOODPECKER_BACKEND=kubernetes`; application-level auto-detection is not the same as that chart default. Kubernetes runs each pipeline step in a standalone Pod and creates a temporary workspace PVC for the pipeline lifetime. No host Docker socket is required by this backend. Docker-in-Docker or privileged image-building plugins are separate, optional workload choices. [O3][O5][O7]

Default chart resources include a single server replica, two agent replicas, a 10Gi server data volume and a 1Gi persistent agent configuration volume. Agent configuration stores its registered identity. The default workflow workspace is another volume, with `10G` size and RWX enabled. These three storage purposes must not be confused. `WOODPECKER_MAX_WORKFLOWS` defaults to one per agent. [O3][O7]

### GitHub authentication and reachability

The official GitHub guide requires `WOODPECKER_GITHUB=true`, `WOODPECKER_GITHUB_CLIENT` and `WOODPECKER_GITHUB_SECRET` on the server. Register a **GitHub OAuth application**, with the instance URL as homepage and `https://<instance>/authorize` as callback. The guide explicitly warns against substituting a GitHub App because user access tokens are not automatically refreshed. `WOODPECKER_GITHUB_PUBLIC_ONLY=true` narrows OAuth to public repositories when that matches the intended scope. [O4]

Registration defaults closed. Configure actual administrator usernames rather than leaving the chart's sample `woodpecker,admin`. `WOODPECKER_REPO_OWNERS` filters allowed repository owners; it is distinct from login/registration controls. OAuth permissions determine which repositories the user can access. [O3][O6]

The chart supports an optional HTTP Ingress and a separate optional gRPC Ingress. For this cluster, an external `HTTPRoute` can target the server Service instead, as the community examples demonstrate. Keep agent gRPC internal unless agents actually run outside this cluster. GitHub webhook reachability needs an explicit public-routing decision. An interactive access proxy in front of webhook endpoints would prevent GitHub deliveries unless machine paths bypass it. The keiretsu example shows that split explicitly, although its forge is Forgejo. [O3][K3]

### Database, secrets and recovery

SQLite is the application's default database at `/var/lib/woodpecker/woodpecker.sqlite` in the container. PostgreSQL and MySQL are supported alternatives. With PostgreSQL, create the database and credentials first; Woodpecker creates/migrates its tables but does not create the database itself. Database size includes build logs, and archival is not provided by Woodpecker. [O6]

The chart can generate and retain `woodpecker-default-agent-secret` through a Kubernetes lookup. Its agent subchart references that Secret by default. To manage credentials outside Helm, inspect both server secret creation and agent secret mapping options, not just `server.extraSecretNamesForEnvFrom`. Existing Secret references or External Secrets avoid plaintext Helm values. Secret material was not collected for this research. [O3]

Back up the selected database, required persistent server state and externally managed credentials. Do not assume PostgreSQL makes every server file disposable: carldanley chooses ephemeral server directories, while jgrecu and keiretsu retain server PVCs. That difference needs a deliberate decision. Agents also have persistent registration identities unless explicitly configured otherwise. [C1][J1][K1][O7]

### Isolation and security

- The chart creates a namespaced Role and RoleBinding for ordinary Kubernetes execution. It grants Pod creation/log access and creation/deletion of workspace PVCs, Services and Secrets. Enabling per-organization namespaces changes this to a **ClusterRole and ClusterRoleBinding**, including namespace creation. It improves workload separation but broadens agent authority. [O9]
- Server/agent `securityContext` values default empty. Chart NetworkPolicies are optional and disabled by default. The agent policy selects agent Pods, not dynamically created pipeline step Pods. Enabling it alone does not isolate builds from home services or other builds. [O3][O10]
- In 3.19.0, native Kubernetes secret references and per-step service-account selection default disabled. Per-step labels, annotations, node selectors, runtime classes and affinity overrides also default disabled. **Per-step toleration overrides default enabled**, so this deserves attention if node taints are part of the isolation design. [O8]
- Non-root step execution and user namespaces are not enabled by default. Hardening the long-running agent container does not impose the same security context on generated step Pods. Enforce the intended policy on build workloads through backend settings and Kubernetes admission/security policy. [O5][O8]
- Keep privileged plugins opt-in. The server documentation recommends explicit image tags for privileged plugin matches. Whether the intended pipelines need Docker builds, deployment credentials or untrusted fork PRs changes the isolation requirements substantially. [O6]

## Verified community configurations

### 1. carldanley/homelab: current official chart and hardened control components

Inspected HEAD `bc665573c947efb3c3ce92131a6edfdfd6e2a551`, dated 2026-10-16. The latest Woodpecker subtree commit was 2026-10-08. Namespace Kustomization includes `woodpecker/ks.yaml`; that Flux Kustomization targets the real application directory, whose resource list includes the HelmRelease, routes, ExternalSecrets and quotas. This is deployable configuration, not a README mention. [C1][C2]

- **Version/backend:** OCI chart 3.7.5, Kubernetes backend, two agents with one workflow each. Builds run in `woodpecker-system`, without per-organization namespaces. [C1]
- **Authentication:** Gitea driver against its own Git service. Closed registration. This is not evidence of GitHub authentication. [C1]
- **Routing:** Gateway API HTTPRoute to `woodpecker-server:80`, attached to internal and external gateways. [C2]
- **Storage/database:** shared CloudNativePG PostgreSQL; database-init image creates the application's database. Server PVC disabled and server data/tmp use `emptyDir`. Agent identity PVCs use `ceph-block`, 1Gi. Workspaces use `openebs-hostpath`, 10Gi, RWO. RWO local storage is a different scheduling tradeoff from CephFS RWX. [C1][C2]
- **Secrets:** External Secrets Operator reads a 1Password ClusterSecretStore for OAuth, agent token, administrator and database settings. A separate agent Secret is included. Automatic chart agent-secret creation is disabled. [C1][C2]
- **Security:** non-root UID/GID 1000, read-only root filesystem, all capabilities dropped, no privilege escalation and RuntimeDefault seccomp for server/agents. Native Kubernetes secrets and per-step service-account selection explicitly disabled. Includes LimitRange and ResourceQuota. These are meaningful controls, but do not prove step isolation or network restrictions. [C1][C2]

Useful precedent for this repo's External Secrets, official OCI chart and Gateway API conventions. Its non-GitHub forge and local RWO workspaces must not be copied without adjustment.

### 2. jgrecu/home-lab: current app-template deployment with privileged build support

Inspected HEAD `6fcbbefe1b391307fbb42a27ebe0bd2160d71097`, dated 2026-10-17. The namespace Kustomization includes server, agent and backup Flux Kustomizations, and the server Flux Kustomization points to concrete generated manifests. The repository also has templates, but the findings below concern the generated `kubernetes/apps/woodpecker` files. [J1][J2]

- **Version/backend:** server and agent images `v3.19.0`, deployed through bjw-s app-template rather than the official Woodpecker chart. Agent OCI source pins app-template 5.3.0. One Kubernetes agent, one workflow, dedicated `woodpecker` namespace. [J1][J3][J4]
- **Authentication:** Forgejo using the Gitea integration variables, named administrator and Secret references for OAuth. No GitHub configuration. [J1]
- **Routing:** HTTPS HTTPRoute on `envoy-external`, targeting server HTTP port 8000. Internal agent connection uses server gRPC port 9000. [J1][J2]
- **Storage/database:** two-instance dedicated CloudNativePG cluster, 5Gi per instance on `longhorn-single`, S3 WAL archiving to SeaweedFS and 180-day retention. Server also retains a 2Gi Longhorn data PVC. Workspace PVCs use Longhorn RWX, 1Gi. [J1][J2]
- **Secrets:** Kubernetes Secret references, with the namespace's SOPS component and referenced encrypted-secret files. Database connection comes from the CNPG-generated application Secret. No secret values were inspected. [J1][J2]
- **Security:** server and agent run non-root with dropped capabilities. However, **namespace Pod Security enforcement, audit and warn are all set to `privileged`**, explicitly for Docker buildx. Privileged plugin allowlists include wildcard image tags. The custom agent Role grants broad read/write access to Secrets and ConfigMaps and `pods/exec`, beyond the current official chart Role. [J1][J2]

Useful example of an Envoy/Flux deployment and database recovery configuration. It is not a safe default for untrusted builds. Agent probe comments mention Docker unavailability despite the Kubernetes backend; treat those comments as unverified, not a backend requirement.

### 3. keiretsu-labs/kubernetes-manifests: current official chart, CephFS and split UI/API routing

Inspected HEAD `1dfa38629da608e1f988767789c6659df687c66d`, dated 2026-10-17. The Ottawa overlay includes a Flux Kustomization targeting the base Woodpecker application. Its resource list includes the primary HelmRelease, an additional image-runner release, database and routes. Comments record operational incidents, but these remain owner-authored accounts, not independently observed runtime evidence. [K1][K2][K4]

- **Version/backend:** official chart 3.7.5, five Kubernetes agents with `WOODPECKER_MAX_WORKFLOWS=4`. The main pool uses CephFS RWX workspaces, 32G. An additional image-runner pool and an agent-only configuration in another cluster are present. [K1][K2]
- **Authentication:** native Forgejo variables, closed registration and explicit administrator. API/status traffic uses an in-cluster Forgejo address; OAuth authorization uses its public canonical hostname through `WOODPECKER_EXPERT_FORGE_OAUTH_HOST`. This is forge-specific, not a GitHub recipe. [K1]
- **Routing:** private UI route protected by Envoy external authorization. Separate `/api`, `/hook`, `/healthz` and `/version` routes attach to private and public gateways without interactive auth. Agents use internal gRPC or Cilium ClusterMesh. [K3]
- **Storage/database:** two-instance dedicated CNPG PostgreSQL, 20Gi per instance on replicated Ceph block, Barman plugin backups to Garage with 14-day retention. Server retains a 10Gi PVC. Agent identity persistence is disabled; workspaces are separate CephFS claims. [K1][K2]
- **Secrets:** forge settings arrive through Flux Secret substitution; database URI comes from the CNPG application Secret. Chart-generated agent Secret is retained and also supplies `WOODPECKER_GRPC_SECRET` to keep signing material stable. That reuse is this operator's choice, not an independent recommendation to reuse secrets. [K1][K2]
- **Security/isolation:** dedicated namespace has `pod-security.kubernetes.io/warn: restricted`, which warns but is not enforcement. Agent and generated-step affinity exclude a sensitive node. Chart RBAC is enabled. The example documents Ceph workspace capacity and RWO multi-attach failures as reasons for using capped RWX workspaces. [K1][K2]

Useful evidence for separating build-node placement from agent placement, retaining stable server signing state, and avoiding interactive authentication on machine endpoints. Its multi-cluster and high-concurrency configuration exceeds this home cluster's likely initial requirements.

## Historical examples and limits

### Rojikku/home-ops: GitHub example, stale and incomplete

Repository HEAD `7bfd63c75b41036fccd9e0d55cce382e24dc06ae` is dated 2026-09-30, but the Woodpecker subtree's latest commit is `40758c638a4107542ee2e9a669f97cd908633a5e`, dated **2023-12-19**. A recently updated repository is not necessarily a recently maintained application. [R1][R2]

Its included Flux manifests configure chart **0.4.2**, digest-pinned `next` server/agent images, GitHub OAuth variables, explicit administrators/repository owner, Traefik TLS ingress, Kubegres PostgreSQL 15.4 with a 5Gi Ceph block database, server Ceph block persistence, and CephFS Kubernetes workspaces. It has two agents and the old `WOODPECKER_MAX_PROCS=4` setting. No explicit current non-root/network-isolation settings appear in its HelmRelease. [R1]

The app Kustomization references `woodpecker.sops.yaml`, but that file is absent from the inspected public tree. The inspected configuration therefore cannot establish a successful current build or deployment. Use it only as historical evidence of GitHub integration and storage separation. Do not copy its chart version, `next` images, concurrency setting or secret substitution pattern into a new installation. [R1][R2]

### soulwhisper/home-ops: explicitly archived

At commit `ca0837ca14856c497684595564bf9b44a6996195`, `.archived/woodpecker/k8s/app/helmrelease.yaml` configures a Kubernetes backend in `worker-apps`, CephFS RWX 10G workspaces, Ceph block server PVC and `WOODPECKER_OPEN=true`. OAuth settings are not shown in that HelmRelease. The archive location disqualifies it as evidence of a current intended deployment. [S1]

Other search hits included tutorial/blog text, copied chart source and migration plans. Those were not counted as verified deployments. This investigation found **three current GitOps configurations**, but **no current verified GitHub-backed home-ops example**. Official GitHub documentation is the stronger source for that part of the design.

## Fit for igas/home-ops

Read `CLAUDE.md`, `docs/agents/domain.md` and `CONTEXT.md` before writing this note. The following are local manifest facts, not live-cluster observations.

- Use `igas.dev`, the existing namespace/app Flux structure, OCI chart sources and External Secrets backed by 1Password. No Woodpecker credentials should be committed in plaintext. [L2]
- Envoy Gateway and Cloudflare Tunnel already exist. A Woodpecker HTTPRoute should follow those conventions rather than introduce Traefik or nginx just because an example uses them. Exact public webhook routing remains undecided. [L2]
- The existing shared CNPG `postgres-18` cluster has three instances, Ceph block data/WAL volumes and `max_connections: 100`. Reusing it is an option, not a reason to create another PostgreSQL cluster automatically. A dedicated application database/user, migrations, backups and connection budget still need design. [L3]
- `cephFileSystems: []` means the repo does not declare a CephFS filesystem. The enabled CephFS VolumeSnapshotClass does **not** establish that RWX storage is provisioned. Options include deliberately adding CephFS, using an existing verified NFS/RWX class, or choosing RWO workspaces with compatible scheduling. Confirm actual storage classes before implementation. [L1]
- Talos uses a Kubernetes container runtime; a host Docker socket is not part of this proposed Kubernetes-backend design. Image building is a separate decision. [L2][O5]

## Options to carry into the design interview

1. **Official combined chart with Kubernetes agents.** Closest to current upstream defaults and the carldanley/keiretsu examples. Keep an explicit workflow namespace, resource ceilings and build-Pod policy. Decide RWX storage before accepting defaults.
2. **App-template with separately managed server and agent.** Matches jgrecu and gives direct control of resources, routing and RBAC. It also requires maintaining wiring that the official chart already provides. No evidence here requires that extra maintenance.
3. **In-cluster server with agents elsewhere.** Supported by the agent subchart. Appropriate if untrusted or privileged builds should not run beside home workloads. Requires agent/server connectivity, transport security and another execution environment. [O3]

For the database, SQLite plus a backed-up PVC is the smallest installation; existing shared PostgreSQL reuses local infrastructure; a dedicated CNPG cluster buys a separate database lifecycle at additional resource cost. No choice is made here. [O6][L3]

## Confirmed scope

- Woodpecker will serve other work, including `visiblelightio/stdlib` on GitHub. It will not replace or migrate CI for `igas/home-ops`.
- Pull requests from external contributors must require operator approval before their code runs. Verify Woodpecker's approval controls during implementation rather than assuming a particular setting provides this guarantee.
- Initial pipelines are limited to tests and validation. Container-image publishing, privileged builders and deployment access are out of scope.
- GitHub integration must support both private and public repositories, rather than public-only OAuth access.
- Initial operator access is limited to GitHub user `igas`. Eligible repository owners are `igas` and `visiblelightio`, with each repository explicitly enabled. Organization membership does not implicitly authorize additional users to log in.
- After considering internal-only access and GitHub webhook reachability, user chose the original Q6 proposal: expose `https://ci.igas.dev` through the existing Cloudflare Tunnel and Envoy Gateway, with Woodpecker's GitHub login protecting the UI. Agent connections remain internal. This supersedes the earlier internal-only request.
- Use the official Woodpecker Helm chart with Kubernetes agents in a dedicated namespace. No host Docker socket is required.
- Use the existing shared PostgreSQL cluster with a dedicated Woodpecker database and credentials, rather than SQLite or another database cluster.
- Initial capacity should allow four concurrent workflows. Agent replica count and per-agent concurrency remain implementation choices, subject to storage and resource constraints.
- Manage OAuth, database and agent credentials through the existing 1Password and External Secrets integration. Do not commit plaintext credentials.
- Use a temporary 10Gi Ceph block workspace per workflow, with RWO-compatible scheduling so steps sharing a workspace run on the same node. Four concurrent workflows may run on different nodes. Verify backend scheduling behavior before implementation; do not add CephFS for this deployment.
- Isolate build Pods from the LAN and other application namespaces. Permit required DNS and internet access, plus only explicitly necessary Woodpecker control traffic. Apply policy to dynamically created build Pods, not just the long-running agents.
- Initial per-build-container limits are 2 CPU cores and 4Gi RAM. Namespace-wide resource ceilings still need to account for concurrent containers and control components.
- Build workloads must not use privileged containers, host mounts or Kubernetes API credentials. Pipelines requiring those capabilities are out of scope unless this isolation policy is explicitly revisited.
- Persist Woodpecker server state on a Ceph-backed volume protected by VolSync backups. Temporary build workspaces are not backed up. PostgreSQL database recovery must be verified separately; the server-volume backup does not cover it.
- User approved Woodpecker-specific database backups after preflight found no configured CNPG recovery path. Use daily logical dumps of only the Woodpecker database on the server volume, then protect those dumps with VolSync. Other database backup policies remain unchanged.
- Deployment design remains under discussion. No deployment changes are approved yet.

## Design interview and preflight

### Implementation preflight, 2026-10-18

- User approved implementing the agreed deployment in `home-ops`, without changing `visiblelightio/stdlib` pipelines.
- Live storage classes include `ceph-block`, `nfs-slow` and `openebs-hostpath`.
- Official Kubernetes backend documentation supports same-workflow Pod affinity using `woodpecker-ci.org/task-uuid` and `matchLabelKeys` for RWO workspaces. Verify the live Kubernetes version before using it.
- Official server configuration supports `WOODPECKER_DEFAULT_APPROVAL_MODE=forks`. Existing repository approval settings still require verification after activation.
- Database recovery was a design blocker. Read-only checks of the live `database/postgres-18` Cluster found no `spec.backup`, no `spec.plugins` and no `status.lastSuccessfulBackup`. No CNPG `Backup` or `ScheduledBackup` resources exist in namespace `database`. This does not rule out backups outside CNPG, but no verified database recovery path was found. User subsequently approved Woodpecker-specific logical dumps protected by VolSync. Actual backup and restore verification remain pending provisioning.
- No deployment manifests or live cluster resources were changed during these checks.

### Implementation status

Manifests now use the official chart, with control components in `woodpecker` and build Pods in `woodpecker-builds`. Namespace separation keeps build PVC references away from server data and credentials. Build admission, resource and network policies reconcile before the chart. A daily Woodpecker-only database dump precedes the VolSync snapshot.

Local checks passed: nine tests including chart/post-rendering and dump-failure behavior, Helm lint, Flux builds including root application discovery, and strict schema validation for 19 application/policy resources and seven chart resources. No live resources were changed. GitHub OAuth, the `woodpecker` 1Password item and live acceptance/restore checks are still required. See [the runbook](../runbooks/woodpecker.md).

### Original interview prompts

These were the questions raised by research. The agreed answers are recorded above, not pending decisions.

- Which repositories and owners are in scope, including private repositories? Will Woodpecker replace GitHub Actions or supplement it?
- Which pipeline events are needed? Will external fork PRs or other untrusted contributors execute code?
- Are builds limited to validation/tests, or do they build/push images, use privileged plugins, or deploy to the cluster?
- Should the UI be publicly accessible, LAN/VPN-only, or protected by another auth layer? Which endpoints must remain reachable by GitHub?
- Which hostname under `igas.dev`, administrator accounts and allowed repository owners should be used?
- Should execution remain in this cluster, be pinned to selected nodes, use a separate build namespace, or run on separate infrastructure?
- Which RWX or RWO workspace strategy, workspace size, concurrency and resource quotas fit the four-node cluster and available storage?
- SQLite, the existing shared PostgreSQL service, or a dedicated database? What backup/restore target and build-log retention are required?
- Should External Secrets manage OAuth credentials, agent registration secrets and persistent gRPC signing material? How will rotations and recovery work?
- Are private registry credentials, build caches, object storage, metrics and alerts part of the initial scope?

## Sources

[O1]: https://woodpecker-ci.org/docs/administration/installation/helm-chart
[O2]: https://github.com/woodpecker-ci/helm/releases/tag/3.7.5
[O3]: https://github.com/woodpecker-ci/helm/tree/e0e8434fc2badff018e8ff557d4d27a376dfa555/charts/woodpecker
[O4]: https://woodpecker-ci.org/docs/administration/configuration/forges/github
[O5]: https://woodpecker-ci.org/docs/administration/configuration/backends/kubernetes
[O6]: https://woodpecker-ci.org/docs/administration/configuration/server
[O7]: https://woodpecker-ci.org/docs/administration/configuration/agent
[O8]: https://github.com/woodpecker-ci/woodpecker/blob/v3.19.0/pipeline/backend/kubernetes/flags.go
[O9]: https://github.com/woodpecker-ci/helm/blob/e0e8434fc2badff018e8ff557d4d27a376dfa555/charts/woodpecker/charts/agent/templates/role.yaml
[O10]: https://github.com/woodpecker-ci/helm/blob/e0e8434fc2badff018e8ff557d4d27a376dfa555/charts/woodpecker/charts/agent/templates/networkpolicy.yaml
[O11]: https://github.com/woodpecker-ci/woodpecker/releases/tag/v3.19.0

[C1]: https://github.com/carldanley/homelab/blob/bc665573c947efb3c3ce92131a6edfdfd6e2a551/kubernetes/apps/woodpecker-system/woodpecker/app/helmrelease.yaml
[C2]: https://github.com/carldanley/homelab/tree/bc665573c947efb3c3ce92131a6edfdfd6e2a551/kubernetes/apps/woodpecker-system
[J1]: https://github.com/jgrecu/home-lab/tree/6fcbbefe1b391307fbb42a27ebe0bd2160d71097/kubernetes/apps/woodpecker
[J2]: https://github.com/jgrecu/home-lab/blob/6fcbbefe1b391307fbb42a27ebe0bd2160d71097/kubernetes/apps/woodpecker/namespace.yaml
[J3]: https://github.com/jgrecu/home-lab/blob/6fcbbefe1b391307fbb42a27ebe0bd2160d71097/kubernetes/apps/woodpecker/woodpecker-server/app/helmrelease.yaml
[J4]: https://github.com/jgrecu/home-lab/blob/6fcbbefe1b391307fbb42a27ebe0bd2160d71097/kubernetes/apps/woodpecker/woodpecker-agent/app/helmrelease.yaml
[K1]: https://github.com/keiretsu-labs/kubernetes-manifests/blob/1dfa38629da608e1f988767789c6659df687c66d/kubernetes/apps/base/woodpecker/woodpecker/app/helmrelease.yaml
[K2]: https://github.com/keiretsu-labs/kubernetes-manifests/tree/1dfa38629da608e1f988767789c6659df687c66d/kubernetes/apps
[K3]: https://github.com/keiretsu-labs/kubernetes-manifests/blob/1dfa38629da608e1f988767789c6659df687c66d/kubernetes/apps/base/woodpecker/woodpecker/app/httproute.yaml
[K4]: https://github.com/keiretsu-labs/kubernetes-manifests/blob/1dfa38629da608e1f988767789c6659df687c66d/kubernetes/apps/ottawa/woodpecker/woodpecker.yaml
[R1]: https://github.com/Rojikku/home-ops/tree/7bfd63c75b41036fccd9e0d55cce382e24dc06ae/cluster/apps/runners/woodpecker
[R2]: https://github.com/Rojikku/home-ops/commit/40758c638a4107542ee2e9a669f97cd908633a5e
[S1]: https://github.com/soulwhisper/home-ops/blob/ca0837ca14856c497684595564bf9b44a6996195/.archived/woodpecker/k8s/app/helmrelease.yaml

[L1]: ../../kubernetes/apps/rook-ceph/rook-ceph/cluster/helmrelease.yaml
[L2]: ../../CLAUDE.md
[L3]: ../../kubernetes/apps/database/cloudnative-pg/cluster/postgres-18.yaml
