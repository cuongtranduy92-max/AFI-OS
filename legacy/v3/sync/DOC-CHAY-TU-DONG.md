# AFI-OS · Chạy tự động

## Một lệnh duy nhất

```
cd sync
python3 afi_sync.py --serve
```

Rồi mở `http://localhost:8765/afi-os.html`.

Lệnh này làm ba việc cùng lúc: kéo số từ Google Ads và các nét, mở dashboard tại
máy, và cứ mỗi 60 phút tự kéo lại. Ô "Nguồn tự động" đã điền sẵn `afi-data.json`,
không phải gõ gì. Đổi chu kỳ bằng `--moi 30` (30 phút) hoặc `--moi 180` (3 tiếng).

Muốn xem thử trước khi có token thì thêm `--demo`: chạy toàn bộ đường ống bằng số giả.

Nếu mở file bằng cách nháy đúp (đường dẫn `file://`), trình duyệt sẽ chặn đọc
`afi-data.json` — đó là quy tắc bảo mật của Chrome, không phải lỗi. Phải mở qua
`http://localhost:8765`.

## Tự lưu

Dashboard tự lưu vào bộ nhớ trình duyệt sau mỗi thay đổi, hiện dòng "đã tự lưu HH:MM"
ở góc phải. Đóng tab, tắt máy, mở lại — mọi thứ còn nguyên: dự án, hồ sơ nét, sổ nạp
tiền, cấu hình nguồn. Nút "↓ Lưu" giờ chỉ dùng khi muốn mang sang máy khác hoặc sao lưu.

Xóa lịch sử trình duyệt sẽ xóa luôn dữ liệu này. Mỗi tuần bấm "↓ Lưu" một lần cất
file JSON ra ngoài là đủ an toàn.

## Bảng lệnh sáng nay

Ở đầu tầng ⑤. Đây là thứ thay cho việc ngồi đọc biểu đồ. Nó tự sinh từ số liệu, xếp
theo số tiền đang chảy mỗi ngày, và nói thẳng phải làm gì ở tài khoản nào:

- **Cắt camp** — camp đã đủ dữ liệu (≥100 click hoặc ≥14 ngày) mà chưa về đồng nào.
  Cột "tiền mỗi ngày" là số đang đốt.
- **Hạ giá thầu** — camp có doanh thu nhưng EPC < CPC. Ghi luôn mức giá thầu nên hạ về,
  bằng EPC × 0,3 theo nguyên tắc #67.
- **Nghẽn ngân sách** — camp mất trên 15% lượt hiển thị vì cạn ngân sách ngày. Đây là
  tiền để trên bàn, chỉ có khi kéo qua API (file CSV thường không có cột này).
- **Tăng ngân sách** — camp đạt ≥1,5× vốn. Nhắc kèm ngưỡng ≤20% và giãn 48–72h.
- **Nạp tiền Ads** — tài khoản còn dưới 5 ngày chi tiêu. Đỏ khi dưới 2 ngày.
- **Rút hoa hồng** — dự án có tiền đã duyệt vượt ngưỡng min payment.
- **Đẩy tiến trình** — dự án đứng ở bước đăng ký/chờ duyệt mà chưa có camp nào.

Không có dòng nào nghĩa là đang ổn. Làm từ trên xuống rồi đóng máy.

## Cái gì tự động, cái gì không

| Việc | Tình trạng |
|---|---|
| Chi phí, click, hiển thị, chuyển đổi theo camp | Tự động — Google Ads API |
| Tỉ lệ hiển thị và phần mất vì ngân sách / thứ hạng | Tự động — Google Ads API |
| Hoa hồng theo giao dịch | Tự động với Impact, PartnerStack, Rewardful |
| Ghép hoa hồng về đúng camp | Tự động khi SubID mang `{gclid}` |
| Hoa hồng ở nét không có API | Bán tự động — thả file CSV vào `csv_nets/` |
| Sổ nạp tiền vào tài khoản Ads | Bán tự động — thả file giao dịch vào `nap/` |
| Doanh thu chốt cuối cùng | Không thể — nét duyệt/hủy đơn theo lịch của họ |
| Bật/tắt camp, đổi giá thầu, đổi ngân sách | Cố ý không tự động (nguyên tắc #19) |

Google Ads API không trả số dư thẻ trả trước, nên sổ nạp tiền phải đi đường CSV:
Google Ads → Thanh toán → Giao dịch → Tải xuống, lưu vào `nap/<mã tài khoản>.csv`.
Sync tự lọc bỏ dòng trừ tiền quảng cáo, chỉ lấy khoản nạp vào.

## Vì sao không có "thời gian thực"

Google Ads chốt số theo múi giờ tài khoản và trễ khoảng 3 tiếng với chi phí, lâu hơn
với chuyển đổi. Các nét affiliate chốt hoa hồng sau 24–72 giờ, có nét theo tuần. Cookie
attribution còn kéo dài 30–90 ngày. Số "thời gian thực" trong affiliate là số sai được
làm mới liên tục — nhìn nó sẽ dẫn tới quyết định hoảng loạn.

Nhịp đúng là: kéo mỗi 1–3 tiếng để thấy tài khoản còn sống và ngân sách chưa nghẽn,
nhưng chỉ ra quyết định cắt/scale trên cửa sổ 7 hoặc 14 ngày.

## Ba việc chỉ Tran làm được

1. **Developer Token** — API Center **chỉ có trong tài khoản Người quản lý (MCC)**, tài khoản
   Google Ads thường không hiện mục này. Trình tự: tạo MCC miễn phí ở
   `ads.google.com/home/tools/manager-accounts` → liên kết các tài khoản Ads con vào MCC →
   mở `https://ads.google.com/aw/apicenter` bằng đúng tài khoản MCC → điền form (cần website
   công ty đang chạy được và email liên hệ thật) → nhận token.
   Mặc định được **Explorer Access**, đủ để đọc báo cáo hằng ngày, không phải chờ duyệt.
   Chỉ khi cần quy mô lớn hơn mới nộp đơn xin Basic/Standard.
   Quan trọng: API chỉ kéo được số của tài khoản **đã liên kết** vào MCC đó.
2. **OAuth Client** — Google Cloud Console: tạo project, bật Google Ads API, tạo OAuth
   Client kiểu Desktop, lấy refresh token. Đây là quyền vào tài khoản quảng cáo nên
   phải do chính chủ làm.
3. **API key của nét** — mỗi nét cấp trong phần cài đặt tài khoản affiliate.

Điền cả ba vào `config.json` (file tự sinh lần chạy đầu, có hướng dẫn ngay trong đó),
đổi `"bat": false` thành `true` ở nguồn nào muốn bật.

## Chạy nền không cần mở terminal

Linux/Mac, chạy lúc khởi động máy:

```
crontab -e
@reboot cd /duong/dan/toi/sync && /usr/bin/python3 afi_sync.py --serve --moi 60 >> sync.log 2>&1
```

Chỉ kéo số mà không mở web thì bỏ `--serve`:

```
0 7,13,19 * * * cd /duong/dan/toi/sync && /usr/bin/python3 afi_sync.py >> sync.log 2>&1
```
