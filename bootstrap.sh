#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
mkdir -p data logs
alembic upgrade head
printf '\nAFI-OS ready. Run: ./run.sh\n'
