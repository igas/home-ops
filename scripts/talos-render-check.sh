#!/usr/bin/env bash
# Render the Talos machine config with talhelper against throwaway secrets.
#
# Proves that talos/talconfig.yaml, talos/talenv.yaml and talos/patches/ still
# render for the Talos and Kubernetes versions they declare. Needs talhelper
# and yq only: no AGE key, no cluster access. CI runs this on pull requests that touch
# talos/; locally it is the preflight for a Talos or kubelet bump.
#
# Usage:
#   scripts/talos-render-check.sh [--talos-version vX.Y.Z] [--kubernetes-version vX.Y.Z] [--out-dir DIR]
#
# Exit code is talhelper's, so a contract conflict fails the run with
# talhelper's message on stderr.
set -euo pipefail

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 2
}

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TALOS_DIR="$ROOT_DIR/talos"
TALOS_VERSION=""
KUBERNETES_VERSION=""
OUT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --talos-version) TALOS_VERSION="${2:?}"; shift 2 ;;
    --kubernetes-version) KUBERNETES_VERSION="${2:?}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:?}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

for tool in talhelper yq; do command -v "$tool" >/dev/null || { echo "$tool not found on PATH" >&2; exit 127; }; done
[[ -f "$TALOS_DIR/talconfig.yaml" ]] || { echo "no talconfig.yaml in $TALOS_DIR" >&2; exit 2; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# Copy the config only: drop rendered output and every real secret so talhelper
# cannot pick up talsecret.sops.yaml or talenv.sops.yaml by default.
cp -R "$TALOS_DIR"/. "$WORK_DIR"
rm -rf "$WORK_DIR/clusterconfig" "$WORK_DIR"/talsecret*.y*ml "$WORK_DIR"/talenv.sops.y*ml

set_env() {
  local key="$1" value="$2"
  grep -q "^${key}:" "$WORK_DIR/talenv.yaml" || { echo "talenv.yaml has no ${key}" >&2; exit 2; }
  sed -i.bak "s|^${key}: .*|${key}: ${value}|" "$WORK_DIR/talenv.yaml" && rm -f "$WORK_DIR/talenv.yaml.bak"
}
[[ -n "$TALOS_VERSION" ]] && set_env talosVersion "$TALOS_VERSION"
[[ -n "$KUBERNETES_VERSION" ]] && set_env kubernetesVersion "$KUBERNETES_VERSION"

echo "talhelper: $(talhelper --version)"
echo "talenv.yaml:"
grep -E '^(talosVersion|kubernetesVersion):' "$WORK_DIR/talenv.yaml" | sed 's/^/  /'

talhelper gensecret > "$WORK_DIR/talsecret.yaml"

# talenv.sops.yaml carries the secretbox key for the pinned
# KubeEtcdEncryptionConfig patch; envsubst rejects unset variables, so feed the
# throwaway bundle's key in its place.
echo "secretboxEncryptionSecret: $(yq '.secrets.secretboxencryptionsecret' "$WORK_DIR/talsecret.yaml")" >> "$WORK_DIR/talenv.yaml"

(
  cd "$WORK_DIR"
  talhelper genconfig --offline-mode --secret-file talsecret.yaml --out-dir ./clusterconfig
)

if [[ -n "$OUT_DIR" ]]; then
  mkdir -p "$OUT_DIR"
  cp -R "$WORK_DIR/clusterconfig/." "$OUT_DIR"
  echo "rendered config copied to $OUT_DIR"
fi
