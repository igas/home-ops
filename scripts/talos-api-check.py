#!/usr/bin/env python3
"""Read-only API DNS, TLS and node GET checks through each Talos host.

Run with TALOSCONFIG set, or via task talos:check-api. Requires talosctl,
yq and permission to run short-lived Talos debug containers. No pods,
cordons, drains, upgrades or reboots are created.
"""

import base64
import csv
import io
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "docker.io/library/python:3.14-alpine@sha256:f6a589d43c42b9e7f7dc67a12d37132491f362859a5d750607710cc56da3bc72"

# Executed in a Talos debug container with host networking and host resolv.conf.
# Credentials stay on the node and are never printed or copied to the operator.
PROBE = '''
import base64
import json
from pathlib import Path
import socket
import ssl
import urllib.request

name = "k8s.igas.dev"
expected = {"192.168.6.1", "192.168.6.2", "192.168.6.3"}
addresses = {item[4][0] for item in socket.getaddrinfo(name, 6443, type=socket.SOCK_STREAM)}
if addresses != expected:
    raise RuntimeError(f"{name}: expected {sorted(expected)}, got {sorted(addresses)}")
print(f"host resolver: {name} -> {sorted(addresses)}", flush=True)
config = Path("/host/etc/kubernetes/kubeconfig-kubelet").read_text()
ca = next(line.split(":", 1)[1].strip() for line in config.splitlines() if line.strip().startswith("certificate-authority-data:"))
context = ssl.create_default_context(cadata=base64.b64decode(ca).decode())
cert = Path("/host/var/lib/kubelet/pki/kubelet-client-current.pem")
if cert.is_symlink():
    target = cert.readlink()
    cert = Path("/host") / target.relative_to("/") if target.is_absolute() else cert.parent / target
context.load_cert_chain(cert)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
with opener.open("https://k8s.igas.dev:6443/api/v1/nodes/" + NODE_NAME, timeout=15) as response:
    node = json.load(response)
if node["metadata"]["name"] != NODE_NAME:
    raise RuntimeError("API returned the wrong node")
print("TLS-verified node GET with kubelet credentials: OK; unschedulable=" + str(node["spec"].get("unschedulable", False)))
'''


def main():
    nodes = json.loads(subprocess.check_output([
        "yq", "-o=json", ".nodes", str(ROOT / "talos/talconfig.yaml")
    ], text=True))
    for node in nodes:
        print(f"Checking {node['hostname']} ({node['ipAddress']})", flush=True)
        code = f"NODE_NAME = {node['hostname']!r}\n" + PROBE
        encoded = base64.b64encode(code.encode()).decode()
        args = io.StringIO()
        csv.writer(args, lineterminator="").writerow([
            "python3", "-c", f"import base64, sys; sys.tracebacklimit=0; exec(base64.b64decode('{encoded}'))"
        ])
        subprocess.run([
            "talosctl", "--nodes", node["ipAddress"], "debug", IMAGE,
            "--args", args.getvalue(),
        ], check=True, timeout=120)
    print("All Talos hosts passed. Scheduling state was not changed.")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.SubprocessError, OSError) as error:
        print(f"API check failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
