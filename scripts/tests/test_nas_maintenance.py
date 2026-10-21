"""Exercise NAS maintenance through its CLI, without cluster access."""

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def resource(kind, name, namespace="default", **spec):
    return {"kind": kind, "metadata": {"name": name, "namespace": namespace}, "spec": spec}


class NasMaintenance(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.cluster = self.path / "cluster.json"
        self.state = self.path / "maintenance.json"
        self.log = self.path / "calls.jsonl"
        self.data = {
            "kustomizations.kustomize.toolkit.fluxcd.io": [
                resource("Kustomization", "flux-system", "flux-system"),
                resource("Kustomization", "already-paused", suspend=True),
            ],
            "helmreleases.helm.toolkit.fluxcd.io": [resource("HelmRelease", "plex")],
            "persistentvolumes": [],
            "persistentvolumeclaims": [],
            "deployments": [
                resource("Deployment", "plex", replicas=2, template={"spec": {"volumes": [
                    {"name": "media", "nfs": {"server": "192.168.3.5", "path": "/media"}}
                ]}}),
                resource("Deployment", "volsync", "volsync-system", replicas=1),
                resource("Deployment", "unrelated", replicas=3),
            ],
            "statefulsets": [], "cronjobs": [], "jobs": [], "pods": [],
        }
        cli = self.path / "kubectl"
        cli.write_text('''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
a = sys.argv[1:]
with open(os.environ["CALLS"], "a") as f: f.write(json.dumps(a) + "\\n")
if os.environ.get("FAIL_ON") and os.environ["FAIL_ON"] in " ".join(a): sys.exit(1)
if os.environ.get("BLOCK_ON") and os.environ["BLOCK_ON"] in " ".join(a): time.sleep(5)
if a[:2] == ["config", "current-context"]: print("home"); sys.exit()
if a[:3] == ["get", "namespace", "kube-system"]:
    print(json.dumps({"metadata": {"uid": os.environ.get("CLUSTER_UID", "cluster-1")}})); sys.exit()
if "amtool" in a:
    if "add" in a: print("silence-123")
    sys.exit()
data = json.loads(Path(os.environ["CLUSTER"]).read_text())
if a[0] == "get":
    if a[1] == "cronjobs" and os.environ.get("LATE_CRONJOB"):
        marker = Path(os.environ["CLUSTER"]).with_suffix(".seen")
        if marker.exists() and not data["cronjobs"]:
            data["cronjobs"].append(json.loads(os.environ["LATE_CRONJOB"]))
            Path(os.environ["CLUSTER"]).write_text(json.dumps(data))
        marker.touch()
    if os.environ.get("UNSUSPEND") == a[1]:
        for obj in data[a[1]]: obj["spec"]["suspend"] = False
    print(json.dumps({"items": data[a[1]]})); sys.exit()
if a[0] == "patch":
    kind, name = a[1].split("/", 1)
    ns = a[a.index("--namespace") + 1]
    for obj in data[kind]:
        if obj["metadata"]["name"] == name and obj["metadata"]["namespace"] == ns:
            obj["spec"].update(json.loads(a[-1])["spec"])
    Path(os.environ["CLUSTER"]).write_text(json.dumps(data))
sys.exit(0)
''')
        cli.chmod(0o755)

    def run_cli(self, action, **env):
        self.cluster.write_text(json.dumps(self.data))
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/nas-maintenance.py"), action,
             "--state", str(self.state), "--timeout", "0"],
            env={**os.environ, "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                 "CLUSTER": str(self.cluster), "CALLS": str(self.log), **env},
            capture_output=True, text=True, timeout=10,
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_down_saves_state_and_stops_only_nas_consumers_and_backup_controller(self):
        result = self.run_cli("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.state.exists())
        calls = self.calls()
        scales = [a for a in calls if a[0] == "scale"]
        self.assertTrue(any("deployments/plex" in a and "--replicas=0" in a for a in scales))
        self.assertTrue(any("deployments/volsync" in a for a in scales))
        self.assertFalse(any("deployments/unrelated" in a for a in scales))
        self.assertTrue(any("silence" in a and "add" in a for a in calls))
        self.assertIn("safe to update", result.stdout)

    def test_up_restores_replica_counts_and_original_suspension_states(self):
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.log.write_text("")
        result = self.run_cli("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertTrue(any("deployments/plex" in a and "--replicas=2" in a for a in calls))
        restored = {a[1]: json.loads(a[-1])["spec"]["suspend"]
                    for a in calls if a[0] == "patch"}
        self.assertIsNone(restored["kustomizations.kustomize.toolkit.fluxcd.io/flux-system"])
        self.assertTrue(restored["kustomizations.kustomize.toolkit.fluxcd.io/already-paused"])
        ready = next(i for i, a in enumerate(calls) if a[:2] == ["rollout", "status"])
        resumed = next(i for i, a in enumerate(calls) if "deployments/volsync" in a)
        expired = next(i for i, a in enumerate(calls) if "expire" in a)
        self.assertLess(ready, resumed)
        self.assertLess(resumed, expired)
        self.assertFalse(self.state.exists())

    def test_failed_silence_creation_can_retry_without_losing_restore_state(self):
        result = self.run_cli("down", FAIL_ON="name=~")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state.exists())
        self.assertFalse(any(a[0] == "scale" for a in self.calls()))
        self.log.write_text("")
        result = self.run_cli("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any("add" in a and any("name=~" in arg for arg in a) for a in self.calls()))

    def test_refuses_restore_to_different_cluster_with_same_context_name(self):
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.log.write_text("")
        result = self.run_cli("up", CLUSTER_UID="other-cluster")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state.exists())
        self.assertFalse(any(a[0] in ("patch", "scale") for a in self.calls()))

    def test_inflight_reconciliation_blocks_shutdown(self):
        self.data["helmreleases.helm.toolkit.fluxcd.io"][0]["status"] = {
            "conditions": [{"type": "Reconciling", "status": "True"}]}
        result = self.run_cli("down")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("safe to update", result.stdout)
        self.assertFalse(any(a[0] == "scale" for a in self.calls()))

    def test_statefulset_nfs_claim_templates_are_stopped(self):
        self.data["statefulsets"] = [resource(
            "StatefulSet", "archive", replicas=1, template={"spec": {}},
            volumeClaimTemplates=[{"metadata": {"name": "data"},
                                   "spec": {"storageClassName": "nfs-slow"}}])]
        result = self.run_cli("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(a[0] == "scale" and "statefulsets/archive" in a for a in self.calls()))

    def test_active_backup_job_blocks_safe_to_update_and_allows_restore(self):
        job = resource("Job", "volsync-src-plex", template={"spec": {}})
        job["status"] = {"active": 1}
        self.data["jobs"] = [job]
        result = self.run_cli("down")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("safe to update", result.stdout)
        self.assertIn("volsync-src-plex", result.stderr)
        self.assertTrue(self.state.exists())
        self.assertEqual(self.run_cli("up").returncode, 0)

    def test_nas_pvc_cronjob_is_paused_and_its_previous_state_restored(self):
        self.data["persistentvolumes"] = [resource("PersistentVolume", "media", nfs={"server": "192.168.3.5"})]
        self.data["persistentvolumeclaims"] = [resource("PersistentVolumeClaim", "media", volumeName="media")]
        self.data["cronjobs"] = [resource("CronJob", "index", suspend=False, jobTemplate={
            "spec": {"template": {"spec": {"volumes": [
                {"name": "data", "persistentVolumeClaim": {"claimName": "media"}}
            ]}}}})]
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.assertTrue(any(a[0] == "patch" and "cronjobs/index" in a
                            and json.loads(a[-1]) == {"spec": {"suspend": True}} for a in self.calls()))
        self.log.write_text("")
        self.assertEqual(self.run_cli("up").returncode, 0)
        self.assertTrue(any(a[0] == "patch" and "cronjobs/index" in a
                            and json.loads(a[-1]) == {"spec": {"suspend": False}} for a in self.calls()))

    def test_failed_restore_keeps_gitops_and_backups_paused_and_can_retry(self):
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.log.write_text("")
        result = self.run_cli("up", FAIL_ON="rollout status")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state.exists())
        self.assertFalse(any(a[0] == "patch" or "expire" in a or "deployments/volsync" in a
                             for a in self.calls()))
        self.assertNotEqual(self.run_cli("down").returncode, 0)
        self.assertEqual(self.run_cli("up").returncode, 0)

    def test_down_retry_preserves_original_replica_count(self):
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.data["deployments"][0]["spec"]["replicas"] = 0
        self.assertEqual(self.run_cli("down").returncode, 0)
        self.log.write_text("")
        self.assertEqual(self.run_cli("up").returncode, 0)
        self.assertTrue(any("deployments/plex" in a and "--replicas=2" in a for a in self.calls()))

    def test_unmanaged_nfs_pod_blocks_shutdown(self):
        pod = resource("Pod", "manual-copy", volumes=[{"nfs": {"server": "192.168.3.5"}}])
        pod["status"] = {"phase": "Running"}
        self.data["pods"] = [pod]
        result = self.run_cli("down")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manual-copy", result.stderr)
        self.assertNotIn("safe to update", result.stdout)

    def test_up_without_state_does_not_mutate_cluster(self):
        self.assertNotEqual(self.run_cli("up").returncode, 0)
        self.assertFalse(any(a[0] in ("patch", "scale") for a in self.calls()))

    def test_running_dependent_job_keeps_apis_running_until_it_finishes(self):
        self.data["cronjobs"] = [resource("CronJob", "kometa", jobTemplate={
            "spec": {"template": {"spec": {}}}})]
        job = resource("Job", "kometa-123", template={"spec": {}})
        job["metadata"]["ownerReferences"] = [{"kind": "CronJob", "name": "kometa"}]
        job["status"] = {"active": 1}
        self.data["jobs"] = [job]
        result = self.run_cli("down")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("deployments/plex" in a for a in self.calls()))

    def test_parent_overwriting_child_suspension_blocks_shutdown(self):
        result = self.run_cli("down", UNSUSPEND="helmreleases.helm.toolkit.fluxcd.io")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(a[0] == "scale" for a in self.calls()))
        self.assertNotIn("safe to update", result.stdout)

    def test_consumer_created_during_flux_shutdown_is_discovered_and_paused(self):
        cron = resource("CronJob", "late-copy", jobTemplate={"spec": {"template": {
            "spec": {"volumes": [{"nfs": {"server": "192.168.3.5"}}]}}}})
        result = self.run_cli("down", LATE_CRONJOB=json.dumps(cron))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(a[0] == "patch" and "cronjobs/late-copy" in a for a in self.calls()))

    def test_suspended_canceled_health_check_does_not_block_shutdown(self):
        obj = self.data["kustomizations.kustomize.toolkit.fluxcd.io"][0]
        obj["metadata"]["generation"] = 2
        obj["status"] = {"observedGeneration": 1, "conditions": [
            {"type": "Reconciling", "status": "True", "observedGeneration": 2,
             "reason": "ProgressingWithRetry"},
            {"type": "Ready", "status": "False", "observedGeneration": 2,
             "reason": "HealthCheckCanceled"},
        ]}
        result = self.run_cli("down")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("safe to update", result.stdout)

    def test_cancellation_of_older_generation_does_not_bypass_active_reconciliation(self):
        obj = self.data["kustomizations.kustomize.toolkit.fluxcd.io"][0]
        obj["metadata"]["generation"] = 3
        obj["status"] = {"conditions": [
            {"type": "Reconciling", "status": "True", "observedGeneration": 3},
            {"type": "Ready", "status": "False", "observedGeneration": 2,
             "reason": "HealthCheckCanceled"},
        ]}
        result = self.run_cli("down")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(a[0] == "scale" for a in self.calls()))
        self.assertIn("Waiting for Flux: flux-system/flux-system", result.stderr)

    def test_progress_is_visible_while_kubectl_is_still_running(self):
        self.cluster.write_text(json.dumps(self.data))
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/nas-maintenance.py"), "down",
             "--state", str(self.state)],
            env={**os.environ, "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                 "CLUSTER": str(self.cluster), "CALLS": str(self.log),
                 "BLOCK_ON": "config current-context"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            readable, _, _ = select.select([process.stderr], [], [], 2)
            self.assertTrue(readable, "No progress appeared while kubectl was waiting")
            self.assertIn("checking Kubernetes context and saved state", process.stderr.readline())
            self.assertIsNone(process.poll())
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=10)

    def test_cancellation_exception_is_limited_to_current_generation_kustomizations(self):
        for kind, observed in (("helmreleases.helm.toolkit.fluxcd.io", 2),
                               ("kustomizations.kustomize.toolkit.fluxcd.io", 1),
                               ("kustomizations.kustomize.toolkit.fluxcd.io", None)):
            with self.subTest(kind=kind, reconciling_generation=observed):
                for objects in self.data.values():
                    for obj in objects:
                        obj.pop("status", None)
                obj = self.data[kind][0]
                obj["metadata"]["generation"] = 2
                obj["status"] = {"conditions": [
                    {"type": "Reconciling", "status": "True", "observedGeneration": observed},
                    {"type": "Ready", "status": "False", "observedGeneration": 2,
                     "reason": "HealthCheckCanceled"},
                ]}
                result = self.run_cli("down")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(a[0] == "scale" for a in self.calls()))


if __name__ == "__main__":
    unittest.main()
