#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pids=()

cleanup() {
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" || true
    fi
  done
}

trap cleanup EXIT

(
  cd "$root_dir/backend"
  python -m uvicorn app.main:app --reload --port 8000
) &
pids+=("$!")

(
  cd "$root_dir/ai_agent"
  python -m uvicorn app.main:app --reload --port 8100
) &
pids+=("$!")

(
  cd "$root_dir/realtime"
  npm run dev
) &
pids+=("$!")

(
  cd "$root_dir/frontend"
  npm run dev -- --host
) &
pids+=("$!")

wait
