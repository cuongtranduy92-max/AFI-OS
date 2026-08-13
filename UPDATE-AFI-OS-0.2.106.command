#!/usr/bin/env bash
set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${AFI_OS_TARGET:-$HOME/Downloads/AFI-OS}"
MANIFEST="$PACKAGE_ROOT/payload-manifest.json"
PAYLOAD="$PACKAGE_ROOT/payload"
TOOL="$PACKAGE_ROOT/update_02106_tool.py"

if [[ -x "$TARGET/.venv/bin/python" ]]; then
  PYTHON="$TARGET/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "[AFI-OS] LỖI: Không tìm thấy Python để chạy updater."
  [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

if [[ ! -f "$TOOL" || ! -f "$MANIFEST" || ! -d "$PAYLOAD" ]]; then
  echo "[AFI-OS] LỖI: Update package thiếu tool, manifest hoặc payload."
  echo "[AFI-OS] Không có dữ liệu nào bị thay đổi."
  [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

echo "[AFI-OS] UPDATE 0.2.106"
echo "[AFI-OS] Bản chính: $TARGET"
echo "[AFI-OS] Updater sẽ tự dừng app, backup, kiểm tra và rollback nếu có lỗi."

set +e
"$PYTHON" "$TOOL" install --target "$TARGET" --manifest "$MANIFEST" --payload "$PAYLOAD"
STATUS=$?
set -e

if [[ "$STATUS" -eq 0 ]]; then
  echo
  echo "[AFI-OS] Cập nhật an toàn đã hoàn tất. Dịch vụ đã có được updater phục hồi."
  if [[ "${AFI_OS_SKIP_START:-0}" != "1" ]]; then
    if [[ "$TARGET" == "$HOME/Downloads/AFI-OS" ]] && \
      command -v launchctl >/dev/null 2>&1 && \
      launchctl print "gui/$(id -u)/com.afi-os.server" >/dev/null 2>&1; then
      open "http://127.0.0.1:8765"
    elif [[ -x "$TARGET/START-AFI-OS.command" ]]; then
      "$TARGET/START-AFI-OS.command"
    fi
  fi
else
  echo
  echo "[AFI-OS] Update không hoàn tất; updater đã rollback nếu đã chạm vào app."
fi

[[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
exit "$STATUS"
