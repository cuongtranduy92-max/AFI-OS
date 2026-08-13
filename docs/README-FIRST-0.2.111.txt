AFI-OS 0.2.111 — NHÀ QUẢNG CÁO VÀ LAN TỎA DỰ ÁN

Cài đặt

1. Nhấp đúp UPDATE-AFI-OS-0.2.111.command.
2. Updater tự kiểm checksum, backup code/database, migrate, hậu kiểm và tự rollback nếu lỗi.
3. Nhấp đúp SETUP-ADVERTISER.command một lần, dán SerpApi API key rồi Enter.
4. Vào Bước 1, nhập một domain. Ô Nhà quảng cáo sẽ hiện số đang chạy trong 7 ngày
   và tổng từng thấy; cache 7 ngày không tốn thêm lượt.
5. Bấm Xem chi tiết rồi Còn chạy gì nữa để tìm các domain khác. Domain mới chỉ vào
   hàng đợi khi anh bấm; hệ thống không tự quét định kỳ.

Quota mặc định là 250 lượt/tháng: cảnh báo từ 80%, chặn lượt mới tại 100%.
API key chỉ nằm trong macOS Keychain. Google Ads vẫn chỉ đọc; Terms/PPC chỉ cảnh báo.

Rollback: chạy ROLLBACK-AFI-OS-0.2.111.command trong thư mục AFI-OS.
