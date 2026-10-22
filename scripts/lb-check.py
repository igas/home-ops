#!/usr/bin/env python3
"""Check LoadBalancer reachability from this host and BGP on every node.

Run on the LAN with KUBECONFIG set, or use task check-lb. Requires kubectl,
dig and curl built with HTTP3 support.
Only reads cluster state and opens short-lived probe sockets.

TCP ports use a two-second connect timeout. UDP/53 uses a UDP-only DNS query
for plex.igas.dev. UDP/443 uses HTTP/3 only, with no TCP fallback. Other
protocols fail as unsupported, never as reachable. HTTP/3 checks reachability,
not certificate validity or application health, so TLS verification is disabled
and any HTTP status counts. A wildcard igas.dev gateway listener must accept SNI
lb-check.igas.dev; --resolve pins that name to the discovered Service IP.
Nodes and Services are checked concurrently. Each Service line includes all
its advertised IPs and ports. Missing IPs, agents or peers fail the check.
An off-LAN route source produces a warning and qualifies the final summary;
the exit status still reflects probe failures. LAN source detection cannot
prove the path is on-link if a VPN uses an address inside the LAN range.
"""

from concurrent.futures import ThreadPoolExecutor
import errno
import ipaddress
import json
import re
import socket
import subprocess
import sys


PROBE_TIMEOUT = 2
COMMAND_TIMEOUT = 8
LAN = ipaddress.ip_network("192.168.0.0/20")


def kubectl(*args):
    result = subprocess.run(
        ["kubectl", "--request-timeout=5s", *args],
        capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=True,
    )
    return json.loads(result.stdout)


def failure(error):
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return "timeout"
    if isinstance(error, ConnectionRefusedError):
        return "refused"
    if isinstance(error, OSError) and error.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
        return "no route"
    return str(error)


def check_node(item):
    name, pods = item
    try:
        if len(pods) != 1:
            raise ValueError(f"expected one Cilium agent, found {len(pods)}")
        peers = kubectl("-n", "kube-system", "exec", pods[0], "-c", "cilium-agent",
                        "--", "cilium-dbg", "bgp", "peers", "-o", "json")
        if not peers:
            raise ValueError("no BGP peers")
        states = ", ".join(f"{peer['peer-address']}={peer['session-state']}" for peer in peers)
        passed = all(peer["session-state"].lower() == "established" for peer in peers)
        return passed, f"{'PASS' if passed else 'FAIL'} Node {name} BGP {states}"
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        return False, f"FAIL Node {name} BGP {failure(error)}"


def check_dns(ip):
    # +ignore prevents dig from retrying a truncated UDP response over TCP.
    result = subprocess.run(
        ["dig", f"@{ip}", "-p", "53", "plex.igas.dev", "A", "+notcp", "+ignore",
         f"+time={PROBE_TIMEOUT}", "+tries=1", "+noall", "+comments"],
        capture_output=True, text=True, timeout=PROBE_TIMEOUT + 1,
    )
    output = result.stdout + result.stderr
    for needle, kind in [("refused", "refused"), ("timed out", "timeout"),
                         ("no route", "no route"), ("network is unreachable", "no route")]:
        if needle in output.lower():
            raise ValueError(kind)
    status = re.search(r"status: ([A-Z]+)", output)
    if result.returncode or not status:
        raise ValueError("invalid DNS response")
    if status[1] != "NOERROR":
        raise ValueError(f"DNS {status[1]}")
    return "DNS NOERROR"


def check_http3(ip):
    address = f"[{ip}]" if ":" in ip else ip
    result = subprocess.run(
        ["curl", "--http3-only", "--insecure", "--noproxy", "*",
         "--connect-timeout", str(PROBE_TIMEOUT), "--max-time", str(PROBE_TIMEOUT + 1),
         "--silent", "--show-error", "--output", "/dev/null", "--write-out", "%{http_version}",
         "--resolve", f"lb-check.igas.dev:443:{address}", "https://lb-check.igas.dev/"],
        capture_output=True, text=True, timeout=PROBE_TIMEOUT + 2,
    )
    if result.returncode == 28:
        raise ValueError("timeout")
    if result.returncode:
        output = (result.stdout + result.stderr).lower()
        for needle, kind in [("refused", "refused"), ("no route", "no route"),
                             ("network is unreachable", "no route")]:
            if needle in output:
                raise ValueError(kind)
        raise ValueError("HTTP/3 probe failed: " + (result.stderr.strip() or result.stdout.strip()))
    if result.stdout.strip() != "3":
        raise ValueError("expected HTTP/3 response")
    return "HTTP/3 response"


def check_service(service):
    name = service["metadata"]["namespace"] + "/" + service["metadata"]["name"]
    results = []
    passed = True
    addresses = service.get("status", {}).get("loadBalancer", {}).get("ingress", [])
    ports = service["spec"].get("ports", [])
    if not addresses or not ports:
        return False, f"FAIL Service {name} no LoadBalancer IP or ports"
    for address in addresses:
        ip = address.get("ip")
        for port in ports:
            number, protocol = port["port"], port.get("protocol", "TCP")
            endpoint = f"{ip or '<no IP>'}:{number}/{protocol}"
            try:
                if not ip:
                    raise ValueError("no LoadBalancer IP")
                if protocol == "UDP" and number == 53:
                    outcome = check_dns(ip)
                elif protocol == "UDP" and number == 443:
                    outcome = check_http3(ip)
                elif protocol == "TCP":
                    with socket.create_connection((ip, number), timeout=PROBE_TIMEOUT):
                        pass
                    outcome = "connected"
                else:
                    raise ValueError("unsupported protocol")
                results.append(f"{endpoint} {outcome}")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                passed = False
                results.append(f"{endpoint} {failure(error)}")
    return passed, f"{'PASS' if passed else 'FAIL'} Service {name} " + "; ".join(results)


def warn_non_lan(services):
    """Inspect the source selected by the host's route, without sending packets."""
    warnings = []
    addresses = sorted({entry["ip"] for service in services
                        for entry in service.get("status", {}).get("loadBalancer", {}).get("ingress", [])
                        if entry.get("ip")})
    for ip in addresses:
        try:
            family = socket.AF_INET6 if ipaddress.ip_address(ip).version == 6 else socket.AF_INET
            with socket.socket(family, socket.SOCK_DGRAM) as route:
                route.connect((ip, 53))
                source = route.getsockname()[0]
            if ipaddress.ip_address(source) not in LAN:
                warnings.append(f"route to {ip} uses source {source}, outside LAN {LAN}")
        except (OSError, ValueError) as error:
            warnings.append(f"cannot verify LAN route to {ip}: {failure(error)}")
    for warning in warnings:
        print(f"WARNING: {warning}; not a LAN validation")
    return bool(warnings)


def main():
    with ThreadPoolExecutor(max_workers=16) as pool:
        service_future = pool.submit(kubectl, "get", "services", "-A", "-o", "json")
        node_future = pool.submit(kubectl, "get", "nodes", "-o", "json")
        pod_future = pool.submit(kubectl, "-n", "kube-system", "get", "pods", "-l", "k8s-app=cilium", "-o", "json")
        services = [s for s in service_future.result()["items"] if s["spec"]["type"] == "LoadBalancer"]
        non_lan = warn_non_lan(services)
        nodes = sorted(n["metadata"]["name"] for n in node_future.result()["items"])
        pods = pod_future.result()["items"]
        agents = [(node, [p["metadata"]["name"] for p in pods
                          if p.get("spec", {}).get("nodeName") == node
                          and not p["metadata"].get("deletionTimestamp")]) for node in nodes]
        results = list(pool.map(check_node, agents))
        results.extend(pool.map(check_service, sorted(services, key=lambda s: (
            s["metadata"]["namespace"], s["metadata"]["name"]))))
    for _, line in results:
        print(line)
    if not nodes or not services:
        results.append((False, "empty discovery"))
        print("FAIL discovery: no nodes or no LoadBalancer Services")
    failures = sum(not passed for passed, _ in results)
    qualification = "; not a LAN validation" if non_lan else ""
    print(f"{'FAIL' if failures else 'PASS'}: {len(nodes)} nodes, {len(services)} Services, {failures} failures{qualification}")
    return int(bool(failures))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        print(f"FAIL: cluster discovery: {failure(error)}", file=sys.stderr)
        sys.exit(1)
