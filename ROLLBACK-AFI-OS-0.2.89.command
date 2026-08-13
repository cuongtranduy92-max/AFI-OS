#!/usr/bin/env bash
set -euo pipefail

TARGET="${AFI_OS_TARGET:-$HOME/Downloads/AFI-OS}"
TOOL="$TARGET/scripts/update_0289_tool.py"

if [[ -x "$TARGET/.venv/bin/python" ]]; then
  PYTHON="$TARGET/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "[AFI-OS] LỖI: Không tìm thấy Python để rollback."
  [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

if [[ ! -f "$TOOL" ]]; then
  echo "[AFI-OS] LỖI: Không tìm thấy rollback tool tại $TOOL"
  [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
  exit 1
fi

echo "[AFI-OS] ROLLBACK UPDATE 0.2.89"
echo "[AFI-OS] Bản chính: $TARGET"
echo "[AFI-OS] Hệ thống sẽ tạo emergency backup trước khi khôi phục code và database cũ."

if [[ "${AFI_OS_ASSUME_YES:-0}" != "1" ]]; then
  read -r -p "Gõ ROLLBACK rồi nhấn Enter để tiếp tục: " answer
  if [[ "$answer" != "ROLLBACK" ]]; then
    echo "[AFI-OS] Đã hủy. Không thay đổi dữ liệu."
    [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
    exit 0
  fi
fi

set +e
"$PYTHON" "$TOOL" rollback --target "$TARGET"
STATUS=$?
set -e

if [[ "$STATUS" -eq 0 ]]; then
  echo
  echo "[AFI-OS] Rollback hoàn tất. Mở START-AFI-OS.command để chạy lại."
else
  echo
  echo "[AFI-OS] Rollback không hoàn tất. Không khởi động app; xem backup manifest để xử lý."
fi

[[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
exit "$STATUS"
