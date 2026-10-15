#!/usr/bin/env bash
# Starts the seed apps and the sandbox in the background, waits until both are healthy, runs a Makefile
# target (default: demo), and stops everything on exit. Usage: scripts/run_all.sh [make-target ...]
set -euo pipefail
cd "$(dirname "$0")/.."
LOG_DIR=results/logs
mkdir -p "$LOG_DIR"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

wait_for() { # url, name
  for _ in $(seq 1 120); do curl -sf -o /dev/null "$1" && return 0; sleep 0.5; done
  echo "timed out waiting for $2 at $1 (see $LOG_DIR)" >&2; exit 1
}

(cd platform && exec node scripts/start-apps.mjs) >"$LOG_DIR/apps.log" 2>&1 & pids+=($!)
wait_for http://127.0.0.1:5101/login shop
wait_for http://127.0.0.1:5102/login admin
(cd platform && exec npx tsx src/sandbox/server.ts) >"$LOG_DIR/sandbox.log" 2>&1 & pids+=($!)
wait_for http://127.0.0.1:4000/health sandbox
echo "apps :5101 :5102 and sandbox :4000 are up; running: make ${*:-demo}"
make "${@:-demo}"
