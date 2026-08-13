AFI-OS 0.2.101 — CẬP NHẬT MỘT LẦN BẤM

1. Nhấp đúp UPDATE-AFI-OS-0.2.101.command.
2. Chờ Terminal báo CẬP NHẬT THÀNH CÔNG.
3. Mở http://127.0.0.1:8765 và làm mới trang.
4. Vào Bước 1 · Check dự án, nhập domain rồi bấm Check dự án.

Nếu cần quay lại bản cũ, nhấp đúp ROLLBACK-AFI-OS-0.2.101.command.

Update giữ nguyên database hiện tại, tự tạo backup trước khi thay đổi, kiểm tra
SHA-256, SQLite integrity, foreign keys và migration head. PPC chỉ cảnh báo,
commission không được tự duyệt và Google Ads không có thao tác ghi.
