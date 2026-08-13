# DECISION LOG — IMPLEMENTATION BASELINE

## Đã chốt

### D-001 — AFI-OS là sản phẩm độc lập

Không phụ thuộc, không tích hợp bắt buộc và không dùng kiến trúc Empire OS.

### D-002 — AFI-OS là dự án ưu tiên hiện tại

Empire OS tạm dừng; không xóa dữ liệu và không trộn mã nguồn.

### D-003 — Dùng máy Mac hiện tại

Local-first trong giai đoạn 1. Worker 24/7 chỉ xem xét sau khi hệ thống ổn định.

### D-004 — Replatform, không xóa toàn bộ sản phẩm cũ

Giữ legacy UI, generator và kiến thức nghiệp vụ. Viết lại data core, accounting, attribution, connectors, security và tests.

### D-005 — Deadline vận hành

Mục tiêu quản trị: beta dữ liệu thật khoảng ngày 30; Internal Production 1.0 khoảng ngày 45, với phạm vi khóa chặt.

### D-006 — Module ⓪ Truy vết quảng cáo là lõi

Ad Intelligence & Advertiser Graph đứng trước thẩm định. Mục tiêu là lần theo nhiều advertiser độc lập cùng chạy một project và các project khác của họ.

### D-007 — Browser-assisted capture trước, crawler sau hoặc không làm

MVP yêu cầu người dùng chủ động mở và bấm lưu. Không xây crawler vượt bảo vệ kỹ thuật.

### D-008 — Terms là cảnh báo, không phải bộ lọc loại dự án

`AMBIGUOUS`, `NOT_CHECKED`, `CONFLICT`, `PROHIBITED` và `APPROVAL_REQUIRED` không được suy diễn là cho phép. Hệ thống vẫn giữ dự án trong Radar, Economics và tracking, đồng thời hiển thị cảnh báo terms rõ ràng.

### D-009 — Pending không phải doanh thu thật

Pending chỉ là forecast; cash profit chỉ dùng tiền đã nhận.

### D-010 — Không phân bổ revenue theo spend

Không truy được campaign/click thì ghi `UNATTRIBUTED`.

### D-011 — Không tự launch hoặc thay bid/budget trong 1.0

Hệ thống tạo draft/change set, người dùng phê duyệt.

### D-012 — Không xây tính năng né policy

Không account farming, circumvention, giả bằng chứng, giả hành vi hoặc tự động vượt CAPTCHA.

## Quyền tự chủ của lead

Lead tự thực hiện: kiến trúc, code, test, tài liệu, nghiên cứu, UX và task breakdown.

Chỉ chuyển cho chủ dự án khi bắt buộc:

- OAuth/login/2FA.
- Developer Token và account permissions.
- Affiliate API credentials.
- KYC, hợp đồng và xác nhận policy mơ hồ.
- Nạp tiền hoặc quyết định rủi ro tài chính cao.

### D-013 — Quy trình vị trí file là bước bắt buộc trước mọi cài đặt/cập nhật

Mỗi artifact gửi cho người dùng phải ghi ngay ở đầu:

1. Đây là `RUNTIME`, `UPDATE`, `BACKUP` hay `REVIEW PACKAGE`.
2. File hiện có thể đang ở vùng preview tạm hay thư mục cố định.
3. Có cần di chuyển hay không; nếu có, ghi đường dẫn đích tuyệt đối.
4. File/thư mục nào được mở và file/thư mục nào tuyệt đối không chép đè.
5. Dấu hiệu xác nhận thao tác thành công.

Quy tắc cụ thể:

- `RUNTIME`: phải giải nén tại thư mục cố định trước khi chạy, mặc định `~/Downloads/AFI-OS`.
- `UPDATE`: phải chạy được từ bất kỳ thư mục nào, kể cả vùng preview tạm; updater tự tìm bản chính tại `~/Downloads/AFI-OS` hoặc yêu cầu chọn đường dẫn. Không được bắt người dùng chép payload vào thư mục ứng dụng.
- Trước khi phát hành, phải kiểm thử cả trường hợp chạy từ đường dẫn tạm và đường dẫn cố định.
- Không được đưa hướng dẫn kiểu “giải nén rồi mở” nếu chưa nói rõ vị trí file.


### D-014 — Evidence phải tồn tại dưới dạng bản ghi kiểm toán

Mỗi kết luận PPC/trademark phải lưu URL nguồn, đoạn trích nguyên văn, ngày kiểm tra, người kiểm tra, confidence, phạm vi áp dụng và ngày hết hiệu lực. Chỉ chọn trạng thái trong form là không đủ.

### D-015 — Import commission phải idempotent nhưng vẫn cho phép state transition

Nhập lại cùng giao dịch không tạo bản sao. Nếu cùng external ID chuyển từ `PENDING` sang `APPROVED/PAID/REJECTED`, hệ thống cập nhật bản ghi hiện có và giữ một transaction duy nhất.

### D-016 — Restore không chạy âm thầm trong trình duyệt

Backup có thể tạo từ UI. Restore phải dừng server và yêu cầu xác nhận rõ bằng `RESTORE-LATEST-BACKUP.command`; trước khi ghi đè database, hệ thống tạo backup khẩn cấp.

### D-017 — Automation chỉ tạo proposal

Thu thập theo domain và nhập evidence không được thay đổi canonical permission. Evidence bắt đầu ở `PROPOSED`; xác nhận là thao tác riêng. Chỉ nguồn có thẩm quyền, confidence tối thiểu 0,8 và còn mới mới được dùng để tạo `TERMS_OK`.

### D-018 — Conflict ưu tiên cảnh báo đỏ và commission tách khỏi permission

Hai kết luận chính thức khác nhau trong cùng scope phải resolve thành `CONFLICT`; không dùng “nguồn lưu sau cùng thắng”. Commission facts có bảng và lifecycle riêng, tuyệt đối không được suy ra paid-search, brand-bidding, non-brand hay direct-link permission từ mức hoa hồng.

### D-019 — Risk acknowledgement không thay đổi sự thật

Người vận hành có thể ghi nhận “đã biết rủi ro” cho campaign. Thao tác này chỉ lưu actor, thời gian và ghi chú; không thay đổi terms permission, không biến warning thành `TERMS_OK` và không tự launch/scale campaign.
