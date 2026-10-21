"""Exercise reboot ordering and safety through the CLI without cluster access."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TalosRebootNode(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.log = self.path / "calls.jsonl"
        self.data = {
            "nodes": [{"metadata": {"name": "worker"}, "status": {
                "addresses": [{"type": "InternalIP", "address": "192.168.6.12"}]}}],
            "clusters.postgresql.cnpg.io": [{
                "metadata": {"name": "pg", "namespace": "database"},
                "status": {"currentPrimary": "pg-1", "targetPrimary": "pg-1",
                           "phase": "Cluster in healthy state"}}],
            "pods": [self.pod("pg-1", "worker"), self.pod("pg-2", "other")],
        }
        for tool in ("kubectl", "talosctl"):
            cli = self.path / tool
            cli.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps([Path(sys.argv[0]).name, *args]) + "\\n")
if os.environ.get("FAIL_ON") and os.environ["FAIL_ON"] in " ".join(args): sys.exit(1)
if Path(sys.argv[0]).name == "talosctl": sys.exit()
path = Path(os.environ["CLUSTER"])
data = json.loads(path.read_text())
if args[:2] == ["cnpg", "promote"]:
    if not os.environ.get("STUCK"):
        for c in data["clusters.postgresql.cnpg.io"]:
            if c["metadata"]["name"] == args[2]:
                c["status"]["currentPrimary"] = args[3]
                c["status"]["targetPrimary"] = args[3]
                if os.environ.get("UNHEALTHY"): c["status"]["phase"] = "Switchover in progress"
        path.write_text(json.dumps(data))
    sys.exit()
if args[:2] == ["cnpg", "version"]: print("1.30.1"); sys.exit()
if args[0] == "get":
    if args[1] == "clusters.postgresql.cnpg.io" and os.environ.get("PRIMARY_RETURNS"):
        marker = path.with_suffix(".seen")
        if marker.exists():
            data["clusters.postgresql.cnpg.io"][0]["status"]["currentPrimary"] = "pg-1"
        marker.touch()
    if args[1] == "node": print("True"); sys.exit()
    if args[1] in data: print(json.dumps({"items": data[args[1]]})); sys.exit()
    if args[1] == "cluster.postgresql.cnpg.io":
        print(json.dumps(next(c for c in data["clusters.postgresql.cnpg.io"]
                              if c["metadata"]["name"] == args[2]))); sys.exit()
if "ceph" in args:
    if "health" in args: print('{"status":"HEALTH_OK"}')
    elif "osd" in args and "stat" in args: print('{"num_up_osds":3,"num_in_osds":3,"num_osds":3}')
    elif "pg" in args: print('{"pg_summary":{"num_pg_by_state":[{"name":"active+clean"}]}}')
    sys.exit()
if "amtool" in args:
    if "add" in args: print("silence-1")
    sys.exit()
sys.exit("unexpected command: " + repr(args))
''')
            cli.chmod(0o755)

    @staticmethod
    def pod(name, node):
        return {"metadata": {"name": name, "namespace": "database",
                             "labels": {"cnpg.io/cluster": "pg", "cnpg.io/podRole": "instance",
                                        "cnpg.io/instanceRole": "replica"}},
                "spec": {"nodeName": node}, "status": {"phase": "Running", "conditions": [
                    {"type": "Ready", "status": "True"}]}}

    def run_cli(self, **env):
        cluster = self.path / "cluster.json"
        cluster.write_text(json.dumps(self.data))
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/talos-reboot-node.sh"), "--ip", "192.168.6.12",
             "--timeout", "0"],
            env={**os.environ, "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                 "CLUSTER": str(cluster), "CALLS": str(self.log), **env},
            capture_output=True, text=True, timeout=10,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def test_primary_is_promoted_and_verified_before_reboot(self):
        result, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        promotion = calls.index(["kubectl", "cnpg", "promote", "pg", "pg-2", "--namespace", "database"])
        verification = next(i for i, c in enumerate(calls) if c[1:3] == ["get", "cluster.postgresql.cnpg.io"])
        reboot = next(i for i, c in enumerate(calls) if c[0] == "talosctl")
        self.assertLess(promotion, verification)
        self.assertLess(verification, reboot)

    def assert_reboot_blocked(self, **env):
        result, calls = self.run_cli(**env)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[0] == "talosctl" for c in calls), calls)
        self.assertFalse(any("amtool" in c for c in calls), calls)

    def test_no_replica_on_another_node_blocks_reboot(self):
        self.data["pods"][1]["spec"]["nodeName"] = "worker"
        self.assert_reboot_blocked()

    def test_unready_replica_blocks_reboot(self):
        self.data["pods"][1]["status"]["conditions"][0]["status"] = "False"
        self.assert_reboot_blocked()

    def test_terminating_replica_blocks_reboot(self):
        self.data["pods"][1]["metadata"]["deletionTimestamp"] = "2026-10-22T00:00:00Z"
        self.assert_reboot_blocked()

    def test_promotion_failure_blocks_reboot(self):
        self.assert_reboot_blocked(FAIL_ON="cnpg promote")

    def test_missing_plugin_blocks_reboot(self):
        self.assert_reboot_blocked(FAIL_ON="cnpg version")

    def test_old_healthy_status_does_not_allow_reboot(self):
        self.assert_reboot_blocked(STUCK="1")

    def test_new_primary_must_also_be_healthy(self):
        self.assert_reboot_blocked(UNHEALTHY="1")

    def test_inventory_failure_blocks_reboot(self):
        self.assert_reboot_blocked(FAIL_ON="get clusters.postgresql.cnpg.io")

    def test_primary_on_other_node_is_not_promoted(self):
        self.data["pods"][0]["spec"]["nodeName"] = "other"
        result, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[0] == "talosctl" for c in calls))
        self.assertFalse(any(c[1:3] == ["cnpg", "promote"] for c in calls))

    def test_no_cnpg_clusters_reboots_normally(self):
        self.data["clusters.postgresql.cnpg.io"] = []
        self.data["pods"] = []
        result, calls = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[0] == "talosctl" for c in calls))

    def test_primary_moving_back_after_switchover_blocks_reboot(self):
        result, calls = self.run_cli(PRIMARY_RETURNS="1")
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[0] == "talosctl" for c in calls), calls)


if __name__ == "__main__":
    unittest.main()
