#!/usr/bin/env bash
# Reboot one Talos node without paging on the Ceph and node alerts it causes.
#
# Before the reboot: refuse unless Ceph is HEALTH_OK (muted checks excluded),
# set the Ceph noout flag so the node's OSDs are not marked out and rebalanced,
# and create Alertmanager silences for every Ceph* alert plus alerts labelled
# with this node's name or IP. After the reboot: wait for the node to be Ready,
# every OSD up and every PG active+clean, unset noout, wait for HEALTH_OK and
# expire the silences.
#
# If the run fails before the OSDs are back, noout is left set on purpose (the
# alternative is a rebalance onto the surviving OSDs) and the cleanup commands
# are printed. The silences expire on their own after --duration.
#
# Usage:
#   scripts/talos-reboot-node.sh --ip 192.168.6.2 [--duration 30m] [--timeout 1800] [--force]
#
#   --duration  Alertmanager silence length (amtool duration), default 30m
#   --timeout   seconds to wait for the node and Ceph to recover, default 1800
#   --force     skip the HEALTH_OK precheck
set -euo pipefail

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 2
}

IP=""
DURATION="30m"
TIMEOUT=1800
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip) IP="${2:?}"; shift 2 ;;
    --duration) DURATION="${2:?}"; shift 2 ;;
    --timeout) TIMEOUT="${2:?}"; shift 2 ;;
    --force) FORCE=true; shift ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$IP" ]] || { echo "--ip is required" >&2; usage; }
for tool in kubectl talosctl jq; do command -v "$tool" >/dev/null || { echo "$tool not found on PATH" >&2; exit 127; }; done

AM_NS="observability"
AM_POD="alertmanager-kube-prometheus-stack-0"

log() { printf '\033[1m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
ceph() { kubectl --namespace rook-ceph exec deploy/rook-ceph-tools -- ceph "$@"; }
amtool() {
  kubectl --namespace "$AM_NS" exec "$AM_POD" --container alertmanager -- \
    amtool --alertmanager.url=http://localhost:9093 "$@"
}

# wait_for DESCRIPTION COMMAND...: poll COMMAND every 10s until it succeeds or TIMEOUT passes.
wait_for() {
  local desc="$1"; shift
  local deadline=$((SECONDS + TIMEOUT))
  log "waiting for $desc"
  until "$@" >/dev/null 2>&1; do
    ((SECONDS < deadline)) || { log "timed out after ${TIMEOUT}s waiting for $desc"; return 1; }
    sleep 10
  done
}

NODE="$(kubectl get nodes -o json | jq -r --arg ip "$IP" \
  '.items[] | select(any(.status.addresses[]; .type == "InternalIP" and .address == $ip)) | .metadata.name')"
[[ -n "$NODE" ]] || { echo "no Kubernetes node has InternalIP $IP" >&2; exit 2; }

health_ok() { [[ "$(ceph health -f json | jq -r .status)" == "HEALTH_OK" ]]; }
node_ready() {
  [[ "$(kubectl get node "$NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" == "True" ]]
}
osds_up() { ceph osd stat -f json | jq -e '.num_up_osds == .num_osds and .num_in_osds == .num_osds' >/dev/null; }
pgs_clean() {
  ceph pg stat -f json | jq -e '[.pg_summary.num_pg_by_state[] | select(.name != "active+clean")] | length == 0' >/dev/null
}

log "node $NODE ($IP)"
if ! health_ok; then
  if $FORCE; then
    log "Ceph is not HEALTH_OK, continuing because of --force"
  else
    ceph health detail >&2 || true
    echo "Ceph is not HEALTH_OK; rebooting now could make data unavailable. Re-run with --force to override." >&2
    exit 1
  fi
fi

SILENCES=()
NOOUT_SET=false
DONE=false

cleanup() {
  $DONE && return
  if $NOOUT_SET; then
    if osds_up 2>/dev/null; then
      log "all OSDs are up, unsetting noout"
      ceph osd unset noout || log "failed to unset noout: run 'kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd unset noout'"
    else
      log "OSDs are not all up, so noout stays set. Once they are, run:"
      log "  kubectl -n rook-ceph exec deploy/rook-ceph-tools -- ceph osd unset noout"
    fi
  fi
  if ((${#SILENCES[@]})); then
    log "silences ${SILENCES[*]} stay active until they expire (${DURATION}); expire them early with:"
    log "  kubectl -n $AM_NS exec $AM_POD -c alertmanager -- amtool --alertmanager.url=http://localhost:9093 silence expire ${SILENCES[*]}"
  fi
}
trap cleanup EXIT

COMMENT="talos reboot of $NODE by $(whoami)"
for matcher in 'alertname=~"Ceph.*"' "node=\"$NODE\"" "instance=~\"$IP:.*\""; do
  SILENCES+=("$(amtool silence add --duration="$DURATION" --author="$(whoami)" --comment="$COMMENT" "$matcher")")
done
log "created silences ${SILENCES[*]} for $DURATION"

ceph osd set noout
NOOUT_SET=true
log "set noout"

log "rebooting $NODE"
talosctl --nodes "$IP" reboot --wait --timeout "${TIMEOUT}s"

wait_for "node $NODE Ready" node_ready
wait_for "all OSDs up and in" osds_up
wait_for "all PGs active+clean" pgs_clean

ceph osd unset noout
NOOUT_SET=false
log "unset noout"

wait_for "Ceph HEALTH_OK" health_ok

amtool silence expire "${SILENCES[@]}"
log "expired silences ${SILENCES[*]}"
SILENCES=()
DONE=true
log "$NODE rebooted and Ceph is HEALTH_OK"
