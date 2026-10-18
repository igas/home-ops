"""Validate Woodpecker manifests without cluster changes or real credentials.

Run: python3 -m unittest discover -s scripts/tests -p 'test_woodpecker.py' -v
Set WOODPECKER_CHART to a local unpacked chart to also test Helm rendering.
Requires the repo's yq, kustomize, flux and helm tools.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "kubernetes/apps/woodpecker/woodpecker/app"
BUILDS = ROOT / "kubernetes/apps/woodpecker-builds/woodpecker/app"


def run(*args, input=None):
    return subprocess.check_output(args, input=input, text=True, cwd=ROOT)


def documents(text):
    return [doc for doc in json.loads(run("yq", "eval-all", "-o=json", "[.]", "-", input=text)) if doc]


def load(path):
    return documents(path.read_text())[0]


class WoodpeckerManifests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load(APP / "helmrelease.yaml")
        cls.values = cls.release["spec"]["values"]
        cls.builds = documents(run("kustomize", "build", str(BUILDS)))

    def test_forge_access_and_approval(self):
        env = self.values["server"]["env"]
        self.assertEqual(env["WOODPECKER_ADMIN"], "igas")
        self.assertEqual(env["WOODPECKER_REPO_OWNERS"], "igas,visiblelightio")
        self.assertEqual(env["WOODPECKER_OPEN"], "false")
        self.assertEqual(env["WOODPECKER_GITHUB_PUBLIC_ONLY"], "false")
        self.assertEqual(env["WOODPECKER_DEFAULT_APPROVAL_MODE"], "forks")
        self.assertEqual(env["WOODPECKER_PLUGINS_PRIVILEGED"], "")

    def test_workspace_scheduling_and_concurrency(self):
        agent = self.values["agent"]
        env = agent["env"]
        self.assertEqual(agent["replicaCount"] * int(env["WOODPECKER_MAX_WORKFLOWS"]), 4)
        self.assertEqual(env["WOODPECKER_BACKEND_K8S_STORAGE_CLASS"], "ceph-block")
        self.assertEqual(env["WOODPECKER_BACKEND_K8S_STORAGE_RWX"], "false")
        self.assertEqual(env["WOODPECKER_BACKEND_K8S_VOLUME_SIZE"], "10Gi")
        affinity = documents(env["WOODPECKER_BACKEND_K8S_POD_AFFINITY"])[0]
        term = affinity["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][0]
        self.assertEqual(term["matchLabelKeys"], ["woodpecker-ci.org/task-uuid"])
        self.assertEqual(term["topologyKey"], "kubernetes.io/hostname")
        selector = term.get("labelSelector", {})
        static_keys = set(selector.get("matchLabels", {}))
        static_keys.update(item["key"] for item in selector.get("matchExpressions", []))
        self.assertTrue(
            static_keys.isdisjoint(term["matchLabelKeys"]),
            "Kubernetes rejects a label key present in both labelSelector and matchLabelKeys",
        )
        self.assertNotIn("podAntiAffinity", affinity)

    def test_steps_cannot_override_isolation(self):
        env = self.values["agent"]["env"]
        self.assertEqual(env["WOODPECKER_BACKEND_K8S_NAMESPACE"], "woodpecker-builds")
        for option in (
            "ALLOW_NATIVE_SECRETS", "SERVICE_ACCOUNT_NAME_ALLOW_FROM_STEP",
            "POD_LABELS_ALLOW_FROM_STEP", "POD_ANNOTATIONS_ALLOW_FROM_STEP",
            "POD_NODE_SELECTOR_ALLOW_FROM_STEP", "POD_TOLERATIONS_ALLOW_FROM_STEP",
            "RUNTIME_CLASS_ALLOW_FROM_STEP", "POD_AFFINITY_ALLOW_FROM_STEP",
        ):
            with self.subTest(option=option):
                self.assertEqual(env[f"WOODPECKER_BACKEND_K8S_{option}"], "false")
        sa = next(doc for doc in self.builds if doc["kind"] == "ServiceAccount")
        self.assertFalse(sa["automountServiceAccountToken"])
        ns = load(BUILDS.parents[1] / "namespace.yaml")
        self.assertEqual(ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"], "baseline")

    def test_build_resource_limits(self):
        limit = next(doc for doc in self.builds if doc["kind"] == "LimitRange")["spec"]["limits"][0]
        self.assertEqual(limit["max"], {"cpu": "2", "memory": "4Gi"})
        self.assertEqual(limit["default"], limit["max"])
        quota = next(doc for doc in self.builds if doc["kind"] == "ResourceQuota")["spec"]["hard"]
        self.assertEqual(quota["persistentvolumeclaims"], "4")
        self.assertEqual(quota["requests.storage"], "40Gi")

    def test_build_network_boundaries(self):
        import ipaddress

        policy = next(doc for doc in self.builds if doc["kind"] == "NetworkPolicy")["spec"]
        self.assertEqual(policy["podSelector"], {})
        self.assertEqual(set(policy["policyTypes"]), {"Ingress", "Egress"})
        cidr = policy["egress"][-1]["to"][0]["ipBlock"]
        blocked = [ipaddress.ip_network(net) for net in cidr["except"]]
        for ip in ("192.168.3.5", "192.168.6.1", "10.42.1.2", "10.43.0.1", "169.254.169.254"):
            self.assertTrue(any(ipaddress.ip_address(ip) in net for net in blocked), ip)
        dns = policy["egress"][0]["to"][0]
        self.assertEqual(dns["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"], "kube-system")
        deny = next(doc for doc in self.builds if doc["kind"] == "CiliumNetworkPolicy")["spec"]
        self.assertEqual(set(deny["egressDeny"][0]["toEntities"]), {"host", "remote-node", "kube-apiserver"})

    def test_database_init_does_not_connect_to_missing_database(self):
        init = self.values["server"]["initContainers"][0]
        self.assertIn({"name": "PGDATABASE", "value": "postgres"}, init["env"])
        app_secrets = self.values["server"]["extraSecretNamesForEnvFrom"]
        self.assertNotIn("woodpecker-db-init-secret", app_secrets)
        self.assertNotIn("woodpecker-secret", self.values["agent"]["extraSecretNamesForEnvFrom"])

    def test_flux_build_includes_restorable_volume_and_backups(self):
        docs = documents(run(
            "flux", "build", "kustomization", "woodpecker", "--dry-run",
            "--path", str(APP), "--kustomization-file", str(APP.parent / "ks.yaml"),
        ))
        pvc = next(doc for doc in docs if doc["kind"] == "PersistentVolumeClaim")
        self.assertEqual(pvc["metadata"]["name"], "woodpecker")
        self.assertEqual(pvc["spec"]["dataSourceRef"]["kind"], "ReplicationDestination")
        source = next(doc for doc in docs if doc["kind"] == "ReplicationSource")
        self.assertEqual(source["spec"]["sourcePVC"], "woodpecker")
        self.assertEqual(source["spec"]["trigger"]["schedule"], "0 17 * * *")
        self.assertTrue(any(doc["kind"] == "CronJob" for doc in docs))
        for doc in docs:
            self.assertEqual(doc["metadata"]["namespace"], "woodpecker")


class DatabaseDump(unittest.TestCase):
    def test_dump_replacement_and_failure_preserve_last_good_backup(self):
        job = load(APP / "database-backup.yaml")
        pod = job["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(job["spec"]["timeZone"], "Australia/Sydney")
        self.assertEqual(job["spec"]["schedule"], "0 1 * * *")
        self.assertEqual(job["spec"]["concurrencyPolicy"], "Forbid")
        script = pod["containers"][0]["command"][-1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "backups"
            script = script.replace("dir=/data/database-backups", f"dir='{directory}'")
            for name, body in {
                "pg_dump": 'for arg do case "$arg" in --file=*) file=${arg#--file=};; esac; done\nprintf new > "$file"\nexit "$DUMP_STATUS"\n',
                "pg_restore": 'exit "$RESTORE_STATUS"\n',
            }.items():
                executable = root / name
                executable.write_text("#!/bin/sh\n" + body)
                executable.chmod(0o700)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", DUMP_STATUS="0", RESTORE_STATUS="0")
            subprocess.run(["/bin/sh", "-ec", script], env=env, check=True, capture_output=True)
            latest = directory / "woodpecker.dump"
            self.assertEqual(latest.read_text(), "new")
            latest.write_text("last-good")
            for variable in ("DUMP_STATUS", "RESTORE_STATUS"):
                failing = dict(env, **{variable: "1"})
                result = subprocess.run(["/bin/sh", "-ec", script], env=failing, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(latest.read_text(), "last-good")
                self.assertFalse((directory / "woodpecker.dump.tmp").exists())
            subprocess.run(["/bin/sh", "-ec", script], env=env, check=True, capture_output=True)
            self.assertEqual((directory / "woodpecker.previous.dump").read_text(), "last-good")
            self.assertEqual(latest.read_text(), "new")


@unittest.skipUnless(os.environ.get("WOODPECKER_CHART"), "set WOODPECKER_CHART for Helm rendering tests")
class WoodpeckerChart(unittest.TestCase):
    def test_cross_namespace_rbac_and_secret_wiring(self):
        values = run("yq", ".spec.values", str(APP / "helmrelease.yaml"))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as file:
            file.write(values)
            file.flush()
            rendered = run("helm", "template", "woodpecker", os.environ["WOODPECKER_CHART"], "-n", "woodpecker", "-f", file.name)
        # Exercise the same Kustomize patches that Flux applies after Helm renders.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "rendered.yaml").write_text(rendered)
            patches = load(APP / "helmrelease.yaml")["spec"]["postRenderers"][0]["kustomize"]["patches"]
            (directory / "kustomization.yaml").write_text(json.dumps({
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization", "resources": ["rendered.yaml"],
                "patches": patches,
            }))
            docs = documents(run("kustomize", "build", str(directory)))
        role = next(doc for doc in docs if doc["kind"] == "Role")
        binding = next(doc for doc in docs if doc["kind"] == "RoleBinding")
        self.assertEqual(role["metadata"]["namespace"], "woodpecker-builds")
        self.assertEqual(binding["metadata"]["namespace"], "woodpecker-builds")
        self.assertEqual(binding["subjects"][0]["namespace"], "woodpecker")
        self.assertFalse(any(doc["kind"] in ("ClusterRole", "ClusterRoleBinding", "Secret", "Ingress") for doc in docs))
        server = next(doc for doc in docs if doc["kind"] == "StatefulSet" and doc["metadata"]["name"] == "woodpecker-server")
        self.assertNotIn("volumeClaimTemplates", server["spec"])
        volumes = server["spec"]["template"]["spec"]["volumes"]
        self.assertIn({"name": "data", "persistentVolumeClaim": {"claimName": "woodpecker"}}, volumes)
        startup = server["spec"]["template"]["spec"]["containers"][0]["startupProbe"]
        self.assertEqual(startup["httpGet"]["path"], "/healthz")
        self.assertEqual(startup["failureThreshold"], 60)
        for doc in docs:
            if doc["kind"] == "StatefulSet":
                self.assertEqual(doc["metadata"]["annotations"]["reloader.stakater.com/auto"], "true")


if __name__ == "__main__":
    unittest.main()
