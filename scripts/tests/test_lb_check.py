"""Test the LAN check CLI with a fake API and real host-side sockets."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Any
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("task"), "Task runner required")
class LoadBalancerTask(unittest.TestCase):
    def test_checkout_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="lb check ") as directory:
            root = Path(directory)
            shutil.copy(ROOT / "Taskfile.yaml", root)
            shutil.copytree(ROOT / ".taskfiles", root / ".taskfiles")
            (root / "kubeconfig").touch()
            (root / "scripts").mkdir()
            (root / "scripts/lb-check.py").write_text("print('LAN probe started')\n")
            (root / "bin").mkdir()
            for name in ("kubectl", "dig", "curl"):
                binary = root / "bin" / name
                binary.write_text("#!/bin/sh\nexit 0\n")
                binary.chmod(0o755)
            result = subprocess.run(
                ["task", "--dir", str(root), "check-lb"],
                env={**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"]},
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LAN probe started", result.stdout)


class LoadBalancerCheck(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.services: list[dict[str, Any]] = [{
            "metadata": {"namespace": "media", "name": "plex"},
            "spec": {"type": "LoadBalancer", "ports": [{"port": 32400}]},
            "status": {"loadBalancer": {"ingress": [{"ip": "127.0.0.1"}]}},
        }]
        self.nodes = [{"metadata": {"name": "worker"}}]
        self.pods = [{"metadata": {"name": "cilium-worker"}, "spec": {"nodeName": "worker"}}]
        self.peers = [{"peer-address": "192.168.1.1", "session-state": "established"}]
        cli = self.path / "kubectl"
        cli.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
data = json.loads((pathlib.Path(os.environ['FIXTURES']) / 'cluster.json').read_text())
args = sys.argv[1:]
if 'exec' in args:
    print(json.dumps(data['peers']))
else:
    resource = args[args.index('get') + 1]
    print(json.dumps({'items': data[resource]}))
''')
        cli.chmod(0o755)

    def check(self):
        (self.path / "cluster.json").write_text(json.dumps({
            "services": self.services, "nodes": self.nodes,
            "pods": self.pods, "peers": self.peers,
        }))
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/lb-check.py")],
            env={**os.environ, "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                 "FIXTURES": str(self.path)},
            capture_output=True, text=True, timeout=15,
        )

    def test_refused_service_fails_and_names_endpoint(self):
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            port = closed.getsockname()[1]
        self.services[0]["spec"]["ports"][0]["port"] = port
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"FAIL Service media/plex 127.0.0.1:{port}/TCP refused", result.stdout)
        self.assertIn("PASS Node worker", result.stdout)
        self.assertIn("FAIL:", result.stdout)

    def test_new_service_all_ports_and_ips_are_discovered(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(8)
            port = server.getsockname()[1]
            self.services[0]["metadata"]["name"] = "new-service"
            self.services[0]["spec"]["ports"] = [{"port": port}, {"port": port, "protocol": "TCP"}]
            self.services[0]["status"]["loadBalancer"]["ingress"] *= 2
            result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS Service media/new-service", result.stdout)
        self.assertEqual(result.stdout.count(f"127.0.0.1:{port}/TCP connected"), 4)
        self.assertIn("WARNING", result.stdout)
        self.assertIn("not a LAN validation", result.stdout)
        self.assertIn("192.168.0.0/20", result.stdout)

    def test_each_node_fails_for_missing_or_unestablished_peers(self):
        self.services[0]["spec"]["ports"] = [{"port": 9, "protocol": "SCTP"}]
        for peers, message in [([], "no BGP peers"),
                               ([*self.peers, {"peer-address": "192.168.1.2", "session-state": "active"}], "192.168.1.2=active")]:
            with self.subTest(peers=peers):
                self.peers = peers
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn("FAIL Node worker", result.stdout)
                self.assertIn(message, result.stdout)
        self.pods = []
        result = self.check()
        self.assertIn("FAIL Node worker BGP expected one Cilium agent, found 0", result.stdout)

    def test_udp_dns_uses_query_instead_of_tcp(self):
        self.services[0]["metadata"]["name"] = "k8s-gateway"
        self.services[0]["spec"]["ports"] = [{"port": 53, "protocol": "UDP"}]
        dig = self.path / "dig"
        dig.write_text(f"#!{sys.executable}\n" + '''
import sys
assert '@127.0.0.1' in sys.argv
assert 'plex.igas.dev' in sys.argv
assert '+notcp' in sys.argv
assert '+ignore' in sys.argv
print(';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1234')
''')
        dig.chmod(0o755)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("127.0.0.1:53/UDP DNS NOERROR", result.stdout)
        for output, kind in [("connection refused", "refused"),
                             ("communications error: timed out", "timeout"),
                             ("no route to host", "no route"),
                             ("status: SERVFAIL", "DNS SERVFAIL"),
                             ("garbage", "invalid DNS response")]:
            with self.subTest(output=output):
                dig.write_text(f"#!{sys.executable}\nprint({output!r})\n")
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"FAIL Service media/k8s-gateway 127.0.0.1:53/UDP {kind}", result.stdout)

    def test_dns_process_timeout_is_reported_as_timeout(self):
        self.services[0]["spec"]["ports"] = [{"port": 53, "protocol": "UDP"}]
        dig = self.path / "dig"
        dig.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(10)\n")
        dig.chmod(0o755)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("127.0.0.1:53/UDP timeout", result.stdout)

    def test_pending_service_and_empty_discovery_cannot_pass(self):
        self.services[0]["status"] = {}
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL Service media/plex no LoadBalancer IP", result.stdout)
        self.services = []
        self.nodes = []
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL discovery", result.stdout)

    def test_udp_443_requires_http3_without_tcp_fallback_or_proxy(self):
        self.services[0]["spec"]["ports"] = [{"port": 443, "protocol": "UDP"}]
        curl = self.path / "curl"
        curl.write_text(f"#!{sys.executable}\n" + '''
import sys
assert '--http3-only' in sys.argv
assert '--noproxy' in sys.argv and '*' in sys.argv
assert '--resolve' in sys.argv and 'lb-check.igas.dev:443:127.0.0.1' in sys.argv
assert '--max-time' in sys.argv
assert '--fail' not in sys.argv
print('3', end='')
''')
        curl.chmod(0o755)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("127.0.0.1:443/UDP HTTP/3 response", result.stdout)
        for code, output, kind in [(28, "", "timeout"),
                                   (7, "Connection refused", "refused"),
                                   (7, "No route to host", "no route"),
                                   (0, "2", "expected HTTP/3"),
                                   (2, "curl lacks HTTP3", "HTTP/3 probe failed")]:
            with self.subTest(code=code, output=output):
                curl.write_text(f"#!{sys.executable}\nimport sys\nprint({output!r})\nsys.exit({code})\n")
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"127.0.0.1:443/UDP {kind}", result.stdout)


if __name__ == "__main__":
    unittest.main()
