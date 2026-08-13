#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p logs data

if [[ ! -x .venv/bin/python ]]; then
  echo "[AFI-OS] Cài môi trường lần đầu..."
  ./bootstrap.sh
fi

if [[ -f logs/afi-os.pid ]] && kill -0 "$(cat logs/afi-os.pid)" 2>/dev/null; then
  echo "[AFI-OS] Đang chạy. Mở trình duyệt..."
  open "http://127.0.0.1:8765"
  exit 0
fi

nohup .venv/bin/uvicorn afi_os.main:app --host 127.0.0.1 --port 8765 \
  > logs/afi-os.log 2>&1 &
echo $! > logs/afi-os.pid

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
    echo "[AFI-OS] Đã khởi động."
    open "http://127.0.0.1:8765"
    exit 0
  fi
  sleep 1
done

echo "[AFI-OS] Khởi động thất bại. Xem logs/afi-os.log"
exit 1
