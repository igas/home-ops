"""Exercise the operational check's CLI boundary without cluster access."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TalosApiCheck(unittest.TestCase):
    def test_successful_debug_exit_without_completed_probe_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "talosctl"
            cli.write_text("#!/bin/sh\necho 'debug stream ended before completion'\nexit 0\n")
            cli.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/talos-api-check.py")],
                env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]},
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("All Talos hosts passed", result.stdout)
        self.assertIn("debug stream ended without a completed probe", result.stderr)


class TalosClientApiCheck(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.calls = self.path / "calls.jsonl"
        for tool in ("talosctl", "kubectl"):
            cli = self.path / tool
            cli.write_text('''#!/usr/bin/env python3
import json, os, stat, sys
from pathlib import Path
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps([tool, *args]) + "\\n")
if tool == "talosctl":
    assert "kubeconfig" in args and "--merge=false" in args
    assert args[-1] == "-"
    if os.environ.get("FETCH_FAILURE") or (os.environ.get("FETCH_FIRST_FAILURE") and "192.168.6.1" in args):
        print("SECRET-KEY-MATERIAL", file=sys.stderr)
        sys.exit(1)
    print("fixture, not credentials")
else:
    path = Path(args[args.index("--kubeconfig") + 1])
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
if tool == "kubectl" and "config" in args:
    print(json.dumps({"clusters": [{"cluster": {
        "server": os.environ.get("SERVER", "https://k8s.igas.dev:6443"),
        "certificate-authority-data": "DATA+OMITTED",
        "insecure-skip-tls-verify": bool(os.environ.get("INSECURE"))
    }}]}))
elif tool == "kubectl":
    assert "--kubeconfig" in args
    assert not any(a.startswith("--server") or a.startswith("--insecure") for a in args)
    if os.environ.get("API_SUCCESS"):
        print(json.dumps({"metadata": {"name": args[args.index("node") + 1]}, "spec": {}}))
        sys.exit()
    print("lookup k8s.igas.dev: no such host", file=sys.stderr)
    sys.exit(1)
''')
            cli.chmod(0o755)

    def run_cli(self, *args, **env):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/talos-client-api-check.py"), *args],
            env={**os.environ, "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                 "CALLS": str(self.calls), **env},
            capture_output=True, text=True, timeout=10,
        )
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_caller_dns_failure_is_not_masked_by_operator_kubeconfig(self):
        result, calls = self.run_cli("--ip", "192.168.6.2", KUBECONFIG="/unused/operator-ip-endpoint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lookup k8s.igas.dev: no such host", result.stderr)
        self.assertNotIn("passed", result.stdout)
        node_get = next(c for c in calls if "get" in c)
        self.assertIn("k8s-master-02", node_get)
        config = Path(node_get[node_get.index("--kubeconfig") + 1])
        self.assertNotEqual(str(config), "/unused/operator-ip-endpoint")
        self.assertFalse(config.exists(), "downloaded admin credentials must be cleaned up")

    def test_all_four_nodes_are_read_without_changing_scheduling(self):
        result, calls = self.run_cli(API_SUCCESS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Workstation drain API checks passed", result.stdout)
        gets = [c for c in calls if "get" in c]
        self.assertEqual([c[c.index("node") + 1] for c in gets], [
            "k8s-master-01", "k8s-master-02", "k8s-master-03", "k8s-worker-02"
        ])
        self.assertEqual(len(calls), 6, "only kubeconfig fetch, config view and four GETs")
        self.assertFalse(Path(gets[0][gets[0].index("--kubeconfig") + 1]).exists())

    def test_ip_endpoint_cannot_mask_dns_failure(self):
        result, calls = self.run_cli(SERVER="https://192.168.6.1:6443")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must use the DNS endpoint", result.stderr)
        self.assertFalse(any("get" in c for c in calls))

    def test_insecure_tls_is_rejected(self):
        result, calls = self.run_cli(INSECURE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TLS verification", result.stderr)
        self.assertFalse(any("get" in c for c in calls))

    def test_credential_fetch_failure_does_not_print_secrets(self):
        result, calls = self.run_cli(FETCH_FAILURE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SECRET-KEY-MATERIAL", result.stdout + result.stderr)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(c[0] == "talosctl" for c in calls))

    def test_unavailable_first_master_does_not_block_healthy_control_plane(self):
        result, calls = self.run_cli("--ip", "192.168.6.2", FETCH_FIRST_FAILURE="1", API_SUCCESS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        fetches = [c for c in calls if c[0] == "talosctl"]
        self.assertEqual([c[c.index("--nodes") + 1] for c in fetches], ["192.168.6.1", "192.168.6.2"])
        self.assertIn("Workstation drain API checks passed", result.stdout)
        self.assertNotIn("SECRET-KEY-MATERIAL", result.stdout + result.stderr)

    def test_unknown_node_is_rejected_before_fetching_credentials(self):
        result, calls = self.run_cli("--ip", "192.168.6.11")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No configured Talos node", result.stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
