# VIỆC CHỈ CHỦ DỰ ÁN LÀM ĐƯỢC

Không có việc nào trong danh sách dưới đây chặn Sprint 0. Chúng chỉ chặn kết nối production.

## Ưu tiên 1 — Google Ads

1. Tạo/xác nhận tài khoản MCC.
2. Mở API Center trong MCC và xin Developer Token.
3. Tạo Google Cloud project + OAuth Desktop Client.
4. Khi có token, cung cấp credential qua `.env`/Keychain, không gửi trong chat hoặc commit Git.

## Ưu tiên 2 — dữ liệu affiliate thật

Bản 0.2.0 đã có Commission CSV Import. Khi bạn có báo cáo thật, chỉ cần một trong hai:

- Một affiliate network có API và tài khoản đang hoạt động; hoặc
- Một file CSV report thật. Có thể xóa tên/email khách hàng; cần giữ ID giao dịch, amount, state, date và SubID/GCLID nếu có.

Không cần làm việc này ngay nếu bạn chưa chạy campaign thật.

## Ưu tiên 3 — Ads Transparency Center

Sau khi chạy app và nạp Chrome extension:

1. Mở một project bạn thường theo dõi.
2. Lưu tối thiểu 5 advertiser khác nhau của project đó.
3. Theo một advertiser sang ít nhất 2 project khác.
4. Gửi lại package/database review sau khi có dữ liệu mẫu thật.

## Quy tắc credential

- Không dán token/password vào tài liệu project.
- Không để `.env` trong ZIP review.
- Không gửi OAuth refresh token trong chat.
