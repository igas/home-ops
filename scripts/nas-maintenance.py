#!/usr/bin/env python3
"""Stop NAS consumers for maintenance and restore their recorded state.

Uses kubectl's current context. The Task wrapper supplies this repo's kubeconfig.
State is local: keep it until `up` succeeds. No NAS update is performed here.
"""

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


NAS = "192.168.3.5"
DEPENDENTS = {"autobrr", "kometa", "recyclarr"}
KUSTOMIZATIONS = "kustomizations.kustomize.toolkit.fluxcd.io"
FLUX = (KUSTOMIZATIONS, "helmreleases.helm.toolkit.fluxcd.io")


def log(message):
    timestamp = datetime.now(ZoneInfo("Australia/Sydney")).strftime("%H:%M:%S %Z")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def kubectl(*args):
    return subprocess.check_output(["kubectl", *args], text=True).strip()


def items(kind):
    return json.loads(kubectl("get", kind, "--all-namespaces", "-o", "json"))["items"]


def identity(kind, obj):
    return {"kind": kind, "name": obj["metadata"]["name"],
            "namespace": obj["metadata"].get("namespace", "default")}


def target(entry):
    return [f'{entry["kind"]}/{entry["name"]}', "--namespace", entry["namespace"]]


def patch(entry, value):
    kubectl("patch", *target(entry), "--type=merge", "-p", json.dumps({"spec": value}))


def scale(entry, replicas):
    kubectl("scale", *target(entry), f"--replicas={replicas}")


def amtool(*args):
    return kubectl("--namespace", "observability", "exec",
                   "alertmanager-kube-prometheus-stack-0", "--container", "alertmanager",
                   "--", "amtool", "--alertmanager.url=http://localhost:9093", *args)


def uses_nas(spec, namespace, claims):
    return any(
        volume.get("nfs", {}).get("server") == NAS
        or (namespace, volume.get("persistentVolumeClaim", {}).get("claimName")) in claims
        for volume in spec.get("volumes", [])
    )


def snapshot(context):
    volumes = {pv["metadata"]["name"] for pv in items("persistentvolumes")
               if pv["spec"].get("nfs", {}).get("server") == NAS
               or (pv["spec"].get("csi", {}).get("driver") == "nfs.csi.k8s.io"
                   and pv["spec"].get("csi", {}).get("volumeAttributes", {}).get("server") == NAS)}
    claims = [[pvc["metadata"]["namespace"], pvc["metadata"]["name"]]
              for pvc in items("persistentvolumeclaims")
              if pvc["spec"].get("volumeName") in volumes
              or pvc["spec"].get("storageClassName") == "nfs-slow"]
    claim_set = {tuple(claim) for claim in claims}
    state = {"version": 1, "context": context, "claims": claims, "flux": [],
             "workloads": [], "cronjobs": [], "silences": [], "phase": "preparing"}
    for kind in FLUX:
        for obj in items(kind):
            state["flux"].append({**identity(kind, obj), "suspend": obj["spec"].get("suspend")})
    for kind in ("deployments", "statefulsets", "cronjobs"):
        for obj in items(kind):
            entry = identity(kind, obj)
            spec = obj["spec"]
            pod_spec = (spec["jobTemplate"]["spec"]["template"]["spec"] if kind == "cronjobs"
                        else spec.get("template", {}).get("spec", {}))
            backup_controller = entry["namespace"] == "volsync-system" and entry["name"] == "volsync"
            nas_template = any(
                template["spec"].get("storageClassName") == "nfs-slow"
                or any(ns == entry["namespace"] and claim.startswith(
                    f'{template["metadata"]["name"]}-{entry["name"]}-') for ns, claim in claims)
                for template in spec.get("volumeClaimTemplates", []))
            if not (uses_nas(pod_spec, entry["namespace"], claim_set) or backup_controller
                    or nas_template
                    or (entry["namespace"] == "default" and entry["name"] in DEPENDENTS)):
                continue
            if kind == "cronjobs":
                state["cronjobs"].append({**entry, "suspend": spec.get("suspend")})
            else:
                state["workloads"].append({**entry, "replicas": spec.get("replicas", 1),
                                          "selector": spec.get("selector", {}).get("matchLabels", {}),
                                          "backup_controller": backup_controller})
    if not any(w["backup_controller"] for w in state["workloads"]):
        raise RuntimeError("VolSync controller not found; cannot safely pause NAS backups")
    return state


def save(path, state):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        json.dump(state, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def pending(state, draining=False):
    claims = {tuple(claim) for claim in state["claims"]}
    busy = []
    for pod in items("pods"):
        meta = pod["metadata"]
        if pod.get("status", {}).get("phase") in ("Succeeded", "Failed"):
            continue
        selected = any((not draining or w["backup_controller"])
                       and w["selector"] and w["namespace"] == meta["namespace"]
                       and all(meta.get("labels", {}).get(k) == v for k, v in w["selector"].items())
                       for w in state["workloads"])
        if selected or (not draining and uses_nas(pod["spec"], meta["namespace"], claims)):
            busy.append(f'pod/{meta["namespace"]}/{meta["name"]}')
    for job in items("jobs"):
        meta = job["metadata"]
        if any(c.get("type") in ("Complete", "Failed") and c.get("status") == "True"
               for c in job.get("status", {}).get("conditions", [])):
            continue
        backup = any(o["kind"] in ("ReplicationSource", "ReplicationDestination")
                     for o in meta.get("ownerReferences", [])) or meta["name"].startswith("volsync-")
        cron = any(o["kind"] == "CronJob" and any(
            c["namespace"] == meta["namespace"] and c["name"] == o["name"] for c in state["cronjobs"])
                   for o in meta.get("ownerReferences", []))
        if backup or cron or uses_nas(job["spec"]["template"]["spec"], meta["namespace"], claims):
            busy.append(f'job/{meta["namespace"]}/{meta["name"]}')
    return busy


def wait_for_quiet(state, timeout, draining=False):
    log("Waiting for backup controller and scheduled jobs to finish" if draining
        else "Waiting for NAS consumer pods to stop")
    deadline = time.monotonic() + timeout
    while True:
        busy = pending(state, draining=draining)
        if not busy:
            return
        log("Still waiting for: " + ", ".join(busy))
        if time.monotonic() >= deadline:
            raise RuntimeError("Still using NAS or finishing backups: " + ", ".join(busy))
        time.sleep(5)


def down(args, path, state):
    if state["phase"] == "restoring":
        raise RuntimeError("Restore already started; retry up before starting another maintenance window")
    # Save the complete restore plan before the first cluster mutation.
    log(f'Suspending Flux reconciliation for {len(state["flux"])} resources')
    for entry in state["flux"]:
        patch(entry, {"suspend": True})
    deadline = time.monotonic() + args.timeout
    while True:
        reconciling = []
        unsuspended = []
        recorded = {(e["kind"], e["namespace"], e["name"]) for e in state["flux"]}
        for kind in FLUX:
            for obj in items(kind):
                entry = identity(kind, obj)
                key = (kind, entry["namespace"], entry["name"])
                if key not in recorded:
                    state["flux"].append({**entry, "suspend": obj["spec"].get("suspend")})
                    save(path, state)
                if not obj["spec"].get("suspend"):
                    unsuspended.append(entry)
                if any(c.get("type") == "Reconciling" and c.get("status") == "True"
                       for c in obj.get("status", {}).get("conditions", [])):
                    conditions = {c["type"]: c for c in obj["status"]["conditions"]}
                    ready = conditions.get("Ready", {})
                    generation = obj["metadata"].get("generation")
                    # kustomize-controller cancels health checks on a new
                    # reconcile request, including suspension, but leaves
                    # Reconciling=True when Ready=False/HealthCheckCanceled.
                    # Only accept explicit cancellation for this generation.
                    canceled = (kind == KUSTOMIZATIONS and obj["spec"].get("suspend")
                                and generation is not None
                                and ready.get("status") == "False"
                                and ready.get("reason") == "HealthCheckCanceled"
                                and ready.get("observedGeneration") == generation
                                and conditions["Reconciling"].get("observedGeneration") == generation)
                    if not canceled:
                        reconciling.append(f'{entry["namespace"]}/{entry["name"]}')
        if not reconciling and not unsuspended:
            break
        # A parent that was already running may have overwritten a child's
        # suspension. Reapply it and verify again after reconcilers are idle.
        for entry in unsuspended:
            patch(entry, {"suspend": True})
        log("Waiting for Flux: " + ", ".join(
            reconciling + [f'{e["namespace"]}/{e["name"]} suspension' for e in unsuspended]))
        if time.monotonic() >= deadline:
            raise RuntimeError("Flux not quiescent; retry down: " + ", ".join(reconciling))
        time.sleep(5)
    # In-flight reconciliation may have added consumers after the first
    # snapshot. Discover again once GitOps is idle without losing original
    # restore values, including on retries after workloads were scaled down.
    log("Flux suspended; refreshing NAS consumer discovery")
    refreshed = snapshot(state["context"])
    state["claims"] = [list(claim) for claim in sorted(
        {tuple(claim) for claim in state["claims"] + refreshed["claims"]})]
    for group in ("flux", "workloads", "cronjobs"):
        recorded = {(e["kind"], e["namespace"], e["name"]): e for e in state[group]}
        for entry in refreshed[group]:
            key = (entry["kind"], entry["namespace"], entry["name"])
            if key not in recorded:
                state[group].append(entry)
            elif group == "workloads":
                recorded[key]["selector"] = entry["selector"]
    save(path, state)
    names = sorted({w["name"] for w in state["workloads"] + state["cronjobs"]} | {"nas", "gitea"})
    pattern = "|".join(re.escape(name) for name in names)
    matchers = ['instance=~"192[.]168[.]3[.]5(:.*)?"',
                f'name=~{json.dumps(f".*({pattern}).*")}',
                'alertname=~".*[Vv]ol[Ss]ync.*"']
    for label in ("deployment", "statefulset", "pod", "job"):
        matchers.append(f'{label}=~{json.dumps(f"({pattern}|volsync)(-.*)?")}')
    # A retry also renews coverage if the previous silences have expired.
    log(f"Creating maintenance alert silences for {args.duration}")
    for matcher in matchers:
        silence = amtool("silence", "add", f"--duration={args.duration}",
                         f"--author={os.environ.get('USER', 'nas-maintenance')}",
                         "--comment=NAS maintenance", matcher)
        state["silences"].append(silence)
        save(path, state)
    for entry in state["cronjobs"]:
        log(f'Suspending CronJob {entry["namespace"]}/{entry["name"]}')
        patch(entry, {"suspend": True})
    for entry in state["workloads"]:
        if entry["backup_controller"]:
            log(f'Stopping backup controller {entry["namespace"]}/{entry["name"]}')
            scale(entry, 0)
    # Drain scheduled work while Plex and the other APIs are still available.
    wait_for_quiet(state, args.timeout, draining=True)
    for entry in state["workloads"]:
        if not entry["backup_controller"]:
            log(f'Stopping {entry["kind"]}/{entry["namespace"]}/{entry["name"]}')
            scale(entry, 0)
    wait_for_quiet(state, args.timeout)
    state["phase"] = "down"
    save(path, state)
    print(f"NAS consumers stopped; safe to update the NAS. Silences last {args.duration}.")
    print(f"After NAS storage and S3 are healthy, run nas:up. Keep {path}.")


def up(args, path, state):
    state["phase"] = "restoring"
    save(path, state)
    for backup in (False, True):
        workloads = [entry for entry in state["workloads"] if entry["backup_controller"] == backup]
        for entry in workloads:
            log(f'Restoring {entry["kind"]}/{entry["namespace"]}/{entry["name"]} to {entry["replicas"]} replicas')
            scale(entry, entry["replicas"])
        for entry in workloads:
            if entry["replicas"]:
                log(f'Waiting for {entry["namespace"]}/{entry["name"]} rollout')
                kubectl("rollout", "status", *target(entry), f"--timeout={max(1, args.timeout)}s")
    for entry in state["cronjobs"]:
        patch(entry, {"suspend": entry["suspend"]})
    # Restore Helm releases before their parent Kustomizations.
    log("Restoring original Flux suspension settings")
    for entry in reversed(state["flux"]):
        patch(entry, {"suspend": entry["suspend"]})
    for silence in state["silences"]:
        amtool("silence", "expire", silence)
    path.unlink()
    print("NAS consumers and original reconciliation settings restored.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("down", "up"))
    parser.add_argument("--state", default=str(Path(__file__).resolve().parents[1] / ".private/nas-maintenance.json"))
    parser.add_argument("--duration", default="2h", help="Alertmanager silence duration")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds to wait for workloads")
    args = parser.parse_args()
    if args.timeout < 0:
        parser.error("--timeout must not be negative")
    path = Path(args.state).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log(f"Starting NAS maintenance {args.action}; checking Kubernetes context and saved state")
        context = kubectl("config", "current-context")
        cluster_uid = json.loads(kubectl("get", "namespace", "kube-system", "-o", "json"))["metadata"]["uid"]
        if path.exists():
            state = json.loads(path.read_text())
            if state["context"] != context or state["cluster_uid"] != cluster_uid:
                raise RuntimeError("Current Kubernetes context/cluster does not match saved maintenance state")
        else:
            if args.action == "up":
                raise RuntimeError("No saved maintenance state; refusing to guess original settings")
            log("Discovering NAS consumers and recording original settings")
            state = snapshot(context)
            state["cluster_uid"] = cluster_uid
            save(path, state)
        if args.action == "down":
            down(args, path, state)
        else:
            up(args, path, state)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f"NAS maintenance failed: {error}. Keep the state file and retry down or up.", file=sys.stderr)
        sys.exit(1)
