# Isolate Woodpecker builds from home services

Woodpecker serves projects owned by `igas` and `visiblelightio`; it does not replace CI for this infrastructure repository. We chose Kubernetes agents in the home cluster for tests and validation, rather than privileged builders or separate execution infrastructure. Fork pull requests require approval before running.

Build Pods run in `woodpecker-builds`, separate from server data and credentials in `woodpecker`. Namespace policy blocks LAN and other application access except cluster DNS. Build containers have no Kubernetes API credentials, privileged mode or host mounts. This is network and namespace isolation, not a hardened sandbox against container-runtime vulnerabilities.

We use temporary RWO Ceph block workspaces with same-workflow Pod affinity instead of provisioning CephFS. Workflow steps must fit on one node. Four workflows can run concurrently subject to resource quotas and scheduling capacity.

Woodpecker reuses the shared PostgreSQL cluster. Because no CNPG backup configuration was found, this deployment includes Woodpecker-only logical database dumps on its VolSync-protected server volume. These backups do not protect other databases and do not provide point-in-time recovery.
