#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "[AFI-OS] Không tìm thấy runtime. Hãy mở START-AFI-OS.command trước."
  read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

cd "$ROOT"
set +e
PYTHONPATH="$ROOT/src" "$PYTHON" "$ROOT/scripts/google_ads_setup.py"
STATUS=$?
set -e

if [[ "$STATUS" == "0" ]] && command -v launchctl >/dev/null 2>&1; then
  DOMAIN="gui/$(id -u)"
  if launchctl print "$DOMAIN/com.afi-os.maintenance" >/dev/null 2>&1; then
    launchctl kickstart -k "$DOMAIN/com.afi-os.maintenance" >/dev/null 2>&1 || true
    echo "[AFI-OS] Đã yêu cầu bảo trì 24/7 kiểm tra Google Ads API ngay."
  fi
fi

[[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
exit "$STATUS"
