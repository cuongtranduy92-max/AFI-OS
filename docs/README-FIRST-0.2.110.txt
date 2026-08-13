AFI-OS 0.2.110 — TỶ GIÁ MÔ PHỎNG CỐ ĐỊNH

CẬP NHẬT MỘT LẦN
1. Nhấp đúp UPDATE-AFI-OS-0.2.110.command.
2. Updater tự kiểm checksum, backup code + SQLite, migrate và hậu kiểm.
3. Mở http://127.0.0.1:8765 rồi vào Tìm dự án.

CÁCH DÙNG
- Nhập một domain và bấm Kiểm tra: khung kết quả hiện ngay.
- Traffic, từ khoá và Terms tự cập nhật mỗi giây khi nguồn nền hoàn tất.
- Ô thiếu dữ liệu luôn nói rõ lý do và có nút thử lại riêng khi phù hợp.
- Dán tối đa 50 domain để chạy batch nền; bấm domain đã xong để mở tức thì.
- Làm mới dữ liệu sẽ ép bỏ cache; dữ liệu cũ vẫn được bảo toàn trong lịch sử.
- Hoàn vốn và $/ref dùng hằng 26.000 VND/USD trong config.py.
- FX ledger chỉ dùng đối soát tiền thật ở Trang 4, không đổi hai số mô phỏng trên.

AN TOÀN
- Google Ads chỉ đọc, không tạo/sửa/dừng campaign.
- LLM chỉ tạo proposal; không tự xác nhận commission hay mở permission PPC.
- Cảnh báo Terms không loại dự án.
- API key vẫn nằm trong macOS Keychain và không nằm trong gói cập nhật.

Nếu cần quay lại, chạy ROLLBACK-AFI-OS-0.2.110.command trong thư mục AFI-OS.
