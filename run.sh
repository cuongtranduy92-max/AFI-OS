#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run ./bootstrap.sh first." >&2
  exit 1
fi
mkdir -p data logs
exec .venv/bin/uvicorn afi_os.main:app --host "${AFI_OS_HOST:-127.0.0.1}" --port "${AFI_OS_PORT:-8765}" --reload
