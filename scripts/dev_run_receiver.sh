#!/usr/bin/env bash
# Run the queue receiver locally against a localhost Redis.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate 2>/dev/null || true

export MYCASINO_REDIS_URL=${MYCASINO_REDIS_URL:-redis://localhost:6379/0}
export MYCASINO_QUEUE_STREAM=${MYCASINO_QUEUE_STREAM:-mycasino:updates}
export MYCASINO_RECEIVER_PORT=${MYCASINO_RECEIVER_PORT:-8200}

exec python -m runtime.queue_receiver
