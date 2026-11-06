#!/usr/bin/env python3
"""Check the workstation API path used by Talos v1.14 cordon/drain.

Fetch the Talos admin kubeconfig, as talosctl's drain caller does, rather than
using the operator's possibly IP-based KUBECONFIG. Only node GETs are performed.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://k8s.igas.dev:6443"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", help="Check only this configured node IP")
    args = parser.parse_args()
    nodes = json.loads(subprocess.check_output([
        "yq", "-o=json", ".nodes", str(ROOT / "talos/talconfig.yaml")
    ], text=True, timeout=10))
    targets = [node for node in nodes if not args.ip or node["ipAddress"] == args.ip]
    if not targets:
        raise RuntimeError("No configured Talos node matches --ip")
    # The drain client downloads this config via a control-plane Talos endpoint.
    # Never merge it with, or overwrite, the operator's kubeconfig.
    for control_plane in (node for node in nodes if node.get("controlPlane")):
        try:
            result = subprocess.run([
                "talosctl", "--nodes", control_plane["ipAddress"], "kubeconfig", "--merge=false", "-"
            ], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            break
    else:
        # Do not echo credential-fetch output, even on errors.
        raise RuntimeError("Could not fetch admin kubeconfig from any Talos control plane")
    with tempfile.TemporaryDirectory(prefix="talos-client-api-") as directory:
        config = Path(directory) / "kubeconfig"
        config.touch(mode=0o600)
        config.write_bytes(result.stdout)
        command = ["kubectl", "--kubeconfig", str(config), "--request-timeout=10s"]
        view = subprocess.run([
            *command, "config", "view", "--minify", "-o", "json"
        ], capture_output=True, text=True, timeout=15)
        if view.returncode:
            raise RuntimeError("Could not read Talos admin kubeconfig")
        cluster = json.loads(view.stdout)["clusters"][0]["cluster"]
        if (cluster.get("server") != ENDPOINT or cluster.get("insecure-skip-tls-verify")
                or not cluster.get("certificate-authority-data")):
            raise RuntimeError("Talos kubeconfig must use the DNS endpoint and cluster CA with TLS verification")

        for node in targets:
            name = node["hostname"]
            print(f"Checking workstation drain API path for {name}", flush=True)
            result = subprocess.run([
                *command, "get", "node", name, "-o", "json"
            ], capture_output=True, text=True, timeout=20)
            if result.returncode:
                print(result.stderr, end="", file=sys.stderr)
                raise RuntimeError(f"{name}: workstation drain API node GET failed")
            data = json.loads(result.stdout)
            if data["metadata"]["name"] != name:
                raise RuntimeError("API returned the wrong node")
            print(f"{name}: TLS-verified admin node GET OK; "
                  f"unschedulable={data['spec'].get('unschedulable', False)}", flush=True)
    print("Workstation drain API checks passed. Scheduling state was not changed.")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError, RuntimeError) as error:
        # Subprocess exception strings can contain captured credential material.
        if isinstance(error, RuntimeError):
            print(error, file=sys.stderr)
        print(f"Workstation drain API check failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
