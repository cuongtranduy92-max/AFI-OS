#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f logs/afi-os.pid ]]; then
  PID="$(cat logs/afi-os.pid)"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "[AFI-OS] Đã dừng process $PID."
  else
    echo "[AFI-OS] Process không còn chạy."
  fi
  rm -f logs/afi-os.pid
else
  echo "[AFI-OS] Không tìm thấy PID file."
fi
