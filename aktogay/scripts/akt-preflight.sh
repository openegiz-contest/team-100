#!/usr/bin/env bash
#
# Ports of the Aktogay overlay: the web interface (AKT_WEB_PORT, 8000) and the
# Thing Model server (AKT_MODELS_PORT, 8092). The template's preflight checks
# only the platform ports; without this check a busy port fails late, inside
# `docker compose up`, with "port is already allocated". Same method as
# scripts/compose-preflight.sh (a connect to 127.0.0.1:<port> with a 2 s cap).
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
set -a; . "$ROOT/deploy/compose/.env"; set +a

die() { printf '\033[31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null &
  local pid=$!
  for _ in $(seq 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid"
      return
    fi
    sleep 0.1
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  return 1
}

# A port is a problem only if something other than this stack holds it.
ours="$(docker compose -f "$ROOT/deploy/compose/docker-compose.yml" -f "$ROOT/aktogay/compose.yml" \
        ps -q akt-web akt-models 2>/dev/null || true)"
if [ -z "$ours" ]; then
  busy=()
  for pair in "AKT_WEB_PORT=${AKT_WEB_PORT:-8000}" "AKT_MODELS_PORT=${AKT_MODELS_PORT:-8092}"; do
    if port_busy "${pair#*=}"; then
      busy+=("$pair")
    fi
  done
  if [ "${#busy[@]}" -gt 0 ]; then
    die "Ports already in use on this machine: ${busy[*]}. Stop whatever uses them, or set these variables in deploy/compose/.env."
  fi
fi
