#!/usr/bin/env bash
# run_server.sh — activate the project's virtualenv and run the Flask app
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Virtualenv not found at $VENV — please create it with: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
# Activate and run
source "$VENV/bin/activate"
python "$ROOT_DIR/app.py"
