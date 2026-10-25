"""Check LoadBalancer monitoring in the rendered Gatus configuration.

Run: python3 -m unittest discover -s scripts/tests -p 'test_gatus.py' -v
Requires kustomize and yq.
"""

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "kubernetes/apps/observability/gatus/app"


def documents(text):
    return json.loads(subprocess.check_output(
        ["yq", "eval-all", "-o=json", "[.]", "-"], input=text, text=True,
    ))


class GatusLoadBalancerMonitoring(unittest.TestCase):
    def test_each_final_service_ip_is_probed_and_alerted(self):
        rendered = documents(subprocess.check_output(
            ["kustomize", "build", str(APP)], text=True,
        ))
        configmap = next(doc for doc in rendered if doc["kind"] == "ConfigMap")
        config = documents(configmap["data"]["config.yaml"])[0]
        endpoints = [ep for ep in config["endpoints"] if ep["name"].endswith("-lb")]
        expected = {
            "envoy-external-lb": "tcp://192.168.100.6:443",
            "envoy-internal-lb": "tcp://192.168.100.7:443",
            "k8s-gateway-lb": "192.168.100.8:53",
            "kube-api-lb": "tcp://192.168.100.9:6443",
            "mosquitto-lb": "tcp://192.168.100.124:1883",
            "postgres-lb": "tcp://192.168.100.125:5432",
            "plex-lb": "tcp://192.168.100.210:32400",
        }
        self.assertEqual(len(endpoints), len(expected))
        self.assertEqual({ep["name"]: ep["url"] for ep in endpoints}, expected)
        rules = next(doc for doc in rendered if doc["kind"] == "PrometheusRule")
        down = next(rule for group in rules["spec"]["groups"] for rule in group["rules"]
                    if rule["alert"] == "GatusEndpointDown")
        alert_groups = re.search(r'group=~"([^"]+)"', down["expr"]).group(1)
        self.assertEqual(down["for"], "5m")
        self.assertTrue(config["metrics"])
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint["name"]):
                self.assertEqual(endpoint["group"], "services")
                self.assertIsNotNone(re.fullmatch(alert_groups, endpoint["group"]))
                self.assertEqual(endpoint["interval"], "1m")
                if endpoint["name"] == "k8s-gateway-lb":
                    self.assertEqual(endpoint["dns"], {
                        "query-name": "plex.igas.dev", "query-type": "A",
                    })
                    self.assertIn("[DNS_RCODE] == NOERROR", endpoint["conditions"])
                    self.assertIn("[BODY] == 192.168.100.6", endpoint["conditions"])
                else:
                    self.assertIn("[CONNECTED] == true", endpoint["conditions"])


if __name__ == "__main__":
    unittest.main()
