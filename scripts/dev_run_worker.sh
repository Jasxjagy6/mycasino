#!/usr/bin/env bash
# Run a single worker locally.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate 2>/dev/null || true

export MYCASINO_REDIS_URL=${MYCASINO_REDIS_URL:-redis://localhost:6379/0}
export MYCASINO_QUEUE_STREAM=${MYCASINO_QUEUE_STREAM:-mycasino:updates}
export MYCASINO_QUEUE_GROUP=${MYCASINO_QUEUE_GROUP:-mycasino-workers}
export MYCASINO_QUEUE_CONSUMER=${MYCASINO_QUEUE_CONSUMER:-worker-local-1}

exec python -m runtime.queue_worker
