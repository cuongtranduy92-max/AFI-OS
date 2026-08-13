AFI-OS 0.2.108 — CHẨN ĐOÁN CAMPAIGN + TIẾNG VIỆT

CÀI ĐẶT MỘT LẦN
1. Nhấp đúp UPDATE-AFI-OS-0.2.108.command.
2. Chờ dòng “Cập nhật an toàn đã hoàn tất”.
3. Nếu đã kết nối Claude ở bản trước thì không cần thiết lập lại.
4. Nếu chưa kết nối, nhấp đúp SETUP-LLM.command, dán Anthropic API key rồi Enter.

CÁCH DÙNG
1. Vào Tìm dự án và nhập domain.
2. Bấm Kiểm tra lại tự động hoặc Trích Terms bằng Claude.
3. Đọc tóm tắt tiếng Việt; bấm Xem bản gốc để đối chiếu nguyên văn.
4. Bấm ✓ Chấp nhận khi đúng hoặc ✗ Bỏ khi sai.
5. Vào Bước 3 Chẩn đoán campaign để xem CTR, $/ref, từ khóa, cụm từ,
   thiết bị, vị trí, nhân khẩu học, thay đổi 20% và việc tối ưu theo thứ tự.
6. Chỉ dữ kiện đã chấp nhận mới được dùng tính hoàn vốn/chấm điểm.

AN TOÀN
API key chỉ nằm trong macOS Keychain, không nằm trong database, .env hoặc repo.
Claude không tự mở quyền PPC, không loại dự án, không dừng campaign và không ghi
Google Ads. Trang không nêu PPC luôn cảnh báo cần hỏi support. Hoa hồng “up to”
chỉ để tham khảo, không dùng tính hoàn vốn. Camp Doctor cũng hoàn toàn chỉ đọc.

Nếu cần quay lại, chạy ROLLBACK-AFI-OS-0.2.108.command trong thư mục AFI-OS.
