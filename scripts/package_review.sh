#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/AFI-OS-sprint-0-review.zip}"
cd "$ROOT"
rm -f "$OUT"
zip -qr "$OUT" . \
  -x '.git/*' '.venv/*' '__pycache__/*' '*/__pycache__/*' '*.pyc' \
     '.pytest_cache/*' '.ruff_cache/*' '.env' 'data/*.db' 'data/*.sqlite*' \
     'logs/*' 'AFI-OS-sprint-0-review.zip'
echo "$OUT"
