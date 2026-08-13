#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
.venv/bin/python scripts/launchd_manager.py uninstall
echo "[AFI-OS] Đã tắt tự khởi động 24/7. Dữ liệu và backup không bị xóa."
