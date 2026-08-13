#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
PYTHON="$ROOT/.venv/bin/python"

echo "[AFI-OS] KẾT NỐI TRAFFIC WEBSITE · CHỈ ĐỌC"
echo "Sau bước này, màn hình Tìm dự án chỉ cần nhập domain."
echo "Chọn provider:"
echo "  1) Apify Similarweb Scraper (khuyên dùng)"
echo "  2) Similarweb API chính chủ"
echo "  3) Semrush Trends API"
read "CHOICE?Nhập 1, 2 hoặc 3: "
case "$CHOICE" in
  1) PROVIDER="APIFY" ;;
  2) PROVIDER="SIMILARWEB" ;;
  3) PROVIDER="SEMRUSH" ;;
  *) echo "Lựa chọn không hợp lệ."; read "?Nhấn Enter để đóng..."; exit 1 ;;
esac
read -s "API_KEY?API token/key (sẽ không hiển thị): "
echo
if [[ -z "$API_KEY" ]]; then
  echo "API key không được để trống."
  read "?Nhấn Enter để đóng..."
  exit 1
fi
"$PYTHON" - "$PROVIDER" "$API_KEY" <<'PY'
import sys
from afi_os.services.traffic_keychain import store_credential

store_credential("provider", sys.argv[1])
store_credential("api-key", sys.argv[2])
print(f"[AFI-OS] Đã kết nối {sys.argv[1]} trong macOS Keychain.")
print("[AFI-OS] Không lưu API key vào database hoặc file cấu hình.")
PY
unset API_KEY
echo "[AFI-OS] Xong. Vào Tìm dự án và chỉ nhập domain."
read "?Nhấn Enter để đóng..."
