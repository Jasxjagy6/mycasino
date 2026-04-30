#!/usr/bin/env bash
# Quick local install for development.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
. .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install -r requirements-runtime.txt
pip install -r requirements-dev.txt
echo "==> dev install complete; activate with: source $ROOT/.venv/bin/activate"
