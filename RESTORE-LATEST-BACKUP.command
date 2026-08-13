#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

SERVER_LABEL="com.afi-os.server"
MAINTENANCE_LABEL="com.afi-os.maintenance"
DOMAIN="gui/$(id -u)"
SERVER_PLIST="$HOME/Library/LaunchAgents/$SERVER_LABEL.plist"
MAINTENANCE_PLIST="$HOME/Library/LaunchAgents/$MAINTENANCE_LABEL.plist"
SERVER_WAS_LOADED=0
MAINTENANCE_WAS_LOADED=0
RUNTIME_PAUSED=0
RESTART_COMPLETED=0

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[AFI-OS] Chưa có môi trường Python. Đang chuẩn bị..."
  "$ROOT/bootstrap.sh"
fi

echo "[AFI-OS] Hệ thống sẽ chọn backup mới nhất còn toàn vẹn và đúng schema."
echo "[AFI-OS] Trước khi thay database, AFI-OS luôn giữ thêm một bản khẩn cấp."
if [[ "${AFI_OS_ASSUME_YES:-0}" != "1" ]]; then
  read -r -p "Gõ RESTORE rồi nhấn Enter để tiếp tục: " answer
  if [[ "$answer" != "RESTORE" ]]; then
    echo "[AFI-OS] Đã hủy. Không thay đổi dữ liệu."
    [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
    exit 0
  fi
fi

if command -v launchctl >/dev/null 2>&1; then
  if launchctl print "$DOMAIN/$SERVER_LABEL" >/dev/null 2>&1; then
    SERVER_WAS_LOADED=1
  fi
  if launchctl print "$DOMAIN/$MAINTENANCE_LABEL" >/dev/null 2>&1; then
    MAINTENANCE_WAS_LOADED=1
  fi
fi

restart_runtime() {
  local restart_status=0
  if [[ "$SERVER_WAS_LOADED" == "1" ]]; then
    launchctl bootout "$DOMAIN" "$SERVER_PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "$DOMAIN" "$SERVER_PLIST" || restart_status=1
    launchctl enable "$DOMAIN/$SERVER_LABEL" || restart_status=1
  fi
  if [[ "$MAINTENANCE_WAS_LOADED" == "1" ]]; then
    launchctl bootout "$DOMAIN" "$MAINTENANCE_PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "$DOMAIN" "$MAINTENANCE_PLIST" || restart_status=1
    launchctl enable "$DOMAIN/$MAINTENANCE_LABEL" || restart_status=1
  fi
  if [[ "$SERVER_WAS_LOADED" == "1" ]]; then
    launchctl kickstart -k "$DOMAIN/$SERVER_LABEL" || restart_status=1
  elif [[ -x "$ROOT/START-AFI-OS.command" ]]; then
    "$ROOT/START-AFI-OS.command" || restart_status=1
  fi
  if [[ "$SERVER_WAS_LOADED" == "1" ]]; then
    local healthy=0
    for _ in {1..30}; do
      if curl -fsS "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
        healthy=1
        break
      fi
      sleep 1
    done
    if [[ "$healthy" != "1" ]]; then
      echo "[AFI-OS] CẢNH BÁO: dịch vụ đã nạp lại nhưng health check chưa đạt."
      restart_status=1
    fi
  fi
  return "$restart_status"
}

cleanup_runtime() {
  local original_status=$?
  trap - EXIT
  if [[ "$RUNTIME_PAUSED" == "1" && "$RESTART_COMPLETED" != "1" ]]; then
    echo "[AFI-OS] Đang khôi phục dịch vụ sau khi lệnh bị gián đoạn..."
    restart_runtime || true
  fi
  exit "$original_status"
}
trap cleanup_runtime EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

RUNTIME_PAUSED=1
echo "[AFI-OS] Đang tạm dừng toàn bộ dịch vụ trước khi chạm database..."
if [[ "$SERVER_WAS_LOADED" == "1" ]]; then
  launchctl bootout "$DOMAIN/$SERVER_LABEL"
fi
if [[ "$MAINTENANCE_WAS_LOADED" == "1" ]]; then
  launchctl bootout "$DOMAIN/$MAINTENANCE_LABEL"
fi
"$ROOT/STOP-AFI-OS.command" >/dev/null 2>&1 || true

RUNTIME_STOPPED=0
for _ in {1..75}; do
  if ! curl -fsS "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
    RUNTIME_STOPPED=1
    break
  fi
  sleep 0.2
done
if [[ "$RUNTIME_STOPPED" != "1" ]]; then
  echo "[AFI-OS] LỖI: server vẫn đang mở; Restore bị hủy trước khi chạm database."
  exit 1
fi

set +e
"$ROOT/.venv/bin/python" -m afi_os.backup_cli restore-latest
RESTORE_STATUS=$?
set -e

echo "[AFI-OS] Đang khởi động lại đúng chế độ chạy trước Restore..."
set +e
restart_runtime
RESTART_STATUS=$?
set -e
RESTART_COMPLETED=1
trap - EXIT INT TERM

if [[ "$RESTORE_STATUS" != "0" ]]; then
  echo "[AFI-OS] Restore không hoàn tất; database hiện tại không bị thay bằng backup lỗi."
  FINAL_STATUS="$RESTORE_STATUS"
elif [[ "$RESTART_STATUS" != "0" ]]; then
  echo "[AFI-OS] Restore đã hoàn tất nhưng dịch vụ cần được kiểm tra lại."
  FINAL_STATUS="$RESTART_STATUS"
else
  echo "[AFI-OS] Restore hoàn tất; dịch vụ đã chạy lại."
  FINAL_STATUS=0
  if [[ "${AFI_OS_SKIP_OPEN:-0}" != "1" ]]; then
    open "http://127.0.0.1:8765" || true
  fi
fi

[[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
exit "$FINAL_STATUS"
