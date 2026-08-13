#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

backup_failed() {
  status=$?
  printf '\n[AFI-OS] LỖI: Backup không được tạo vì kiểm tra an toàn không đạt.\n' >&2
  printf '[AFI-OS] Database hiện tại không bị thay đổi. Mở Command Center để xem chi tiết.\n' >&2
  [[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
  exit "$status"
}
trap backup_failed ERR

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[AFI-OS] Chưa có môi trường Python. Đang chuẩn bị..."
  "$ROOT/bootstrap.sh"
fi

echo "[AFI-OS] Đang tạo backup database..."
"$ROOT/.venv/bin/python" -m afi_os.backup_cli create
printf '\n[AFI-OS] Backup thành công. File nằm trong: %s/backups\n' "$ROOT"
[[ "${AFI_OS_NONINTERACTIVE:-0}" == "1" ]] || read -r -p "Nhấn Enter để đóng..." _
