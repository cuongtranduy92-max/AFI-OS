#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
PYTHON="$ROOT/.venv/bin/python"

echo "[AFI-OS] KẾT NỐI CLAUDE · CHỈ TRÍCH XUẤT PROPOSAL"
echo "Claude chỉ đề xuất dữ kiện có trích dẫn; anh vẫn phải bấm xác nhận."
"$PYTHON" - <<'PY'
from getpass import getpass

from afi_os.services.llm_keychain import store_credential

store_credential(getpass("Anthropic API key (sẽ không hiển thị): "))
print("[AFI-OS] Đã lưu Anthropic API key trong macOS Keychain.")
print("[AFI-OS] Không lưu key vào database, .env hoặc file cấu hình.")
PY
echo "[AFI-OS] Xong. Vào Tìm dự án và bấm Kiểm tra lại tự động."
read "?Nhấn Enter để đóng..."
