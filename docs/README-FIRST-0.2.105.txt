AFI-OS 0.2.105 — TRAFFIC TỰ ĐỘNG BẰNG APIFY

1. Nhấp đúp UPDATE-AFI-OS-0.2.105.command.
2. Nếu chưa kết nối, vào AFI-OS và nhấp đúp SETUP-TRAFFIC-DATA.command.
3. Nhập số 1, dán Apify API token, nhấn Enter.
4. Vào Bước 1, nhập một domain hoặc dán tối đa 50 domain.

AFI-OS sẽ tự lấy traffic tháng mới nhất và top 5 quốc gia. Kết quả được cache
45 ngày để không tốn lượt Apify lần hai. Domain không có dữ liệu hiện NO_DATA,
không bị giả thành số 0. Token chỉ nằm trong macOS Keychain.

Rollback bằng ROLLBACK-AFI-OS-0.2.105.command.
