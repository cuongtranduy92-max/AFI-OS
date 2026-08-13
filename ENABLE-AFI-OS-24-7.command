#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p logs data

if [[ ! -x .venv/bin/python ]]; then
  echo "[AFI-OS] LỖI: Chưa có runtime. Hãy mở START-AFI-OS.command trước."
  exit 1
fi

echo "[AFI-OS] Đang bật chế độ 24/7…"
.venv/bin/python scripts/launchd_manager.py install --target "$ROOT"
echo "[AFI-OS] Đã bật 24/7. AFI-OS tự chạy lại sau đăng nhập/restart và bảo trì mỗi 6 giờ."
open "http://127.0.0.1:8765"
