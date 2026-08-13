#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
PYTHON="$ROOT/.venv/bin/python"

echo "[AFI-OS] KẾT NỐI NHÀ QUẢNG CÁO · CHỈ ĐỌC"
echo "Nguồn: SerpApi · Google Ads Transparency Center."
echo "Token chỉ được lưu trong macOS Keychain."
read -s "API_KEY?SerpApi API key (sẽ không hiển thị): "
echo
if [[ -z "$API_KEY" ]]; then
  echo "API key không được để trống."
  read "?Nhấn Enter để đóng..."
  exit 1
fi
print -rn -- "$API_KEY" | "$PYTHON" -c '
import sys
from afi_os.services.advertiser_keychain import store_credential

store_credential(sys.stdin.read())
print("[AFI-OS] Đã kết nối SerpApi trong macOS Keychain.")
print("[AFI-OS] Không lưu API key vào database, .env hoặc file cấu hình.")
'
unset API_KEY
echo "[AFI-OS] Xong. Vào Tìm dự án và nhập domain để kiểm tra."
read "?Nhấn Enter để đóng..."
