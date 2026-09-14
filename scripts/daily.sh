#!/usr/bin/env bash
# Daily run: sweep, pull, resolve, render, and optionally publish.
#
# Pin this to a fixed hour and keep it there. A job that drifts from 02:00 to
# 04:00 turns a 24-hour reading into a 26-hour one and corrupts every rate
# derived from it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$REPO/src"
PY="${SHOPLEDGER_PYTHON:-python3}"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) shop-ledger daily ==="

# caffeinate keeps the machine awake for the run; without it a macOS dark-wake
# can kill a long network job halfway through and leave a partial day.
RUN="$PY -m shopledger"
if command -v caffeinate >/dev/null 2>&1; then
  RUN="caffeinate -i $PY -m shopledger"
fi

$RUN sweep
$RUN pull
$RUN resolve
$RUN render

# Publish only if the Vercel CLI is present and a project is already linked.
if [ "${SHOPLEDGER_DEPLOY:-0}" = "1" ] && command -v vercel >/dev/null 2>&1; then
  ( cd data/out && vercel deploy --prod --yes >/dev/null 2>&1 ) \
    && echo "published" || echo "publish failed, site still rendered locally"
fi

echo "=== done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
