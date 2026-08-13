# RUNBOOK

## Update 0.2.105 — Traffic tự động bằng Apify

1. Chạy `UPDATE-AFI-OS-0.2.105.command` một lần.
2. Nếu chưa kết nối traffic, chạy `SETUP-TRAFFIC-DATA.command`, nhập `1`, dán
   Apify API token rồi nhấn Enter. Token chỉ lưu trong macOS Keychain.
3. Vào **Bước 1 · Check dự án**, nhập một domain hoặc dán danh sách tối đa 50 domain.
4. AFI-OS tự lấy traffic tháng mới nhất và top 5 quốc gia. Kết quả còn hạn 45 ngày
   được dùng lại và không gọi Apify lần nữa.
5. Domain Apify không có dữ liệu hiện `NO_DATA`; hệ thống không tự điền số 0.

Rollback bằng `ROLLBACK-AFI-OS-0.2.105.command`. Update không thay đổi Terms,
commission, Project/campaign state và không ghi Google Ads.

## Update 0.2.104 — Bộ sinh content Bước 2

1. Chạy `UPDATE-AFI-OS-0.2.104.command` một lần.
2. Vào **Bước 2 · Chuẩn bị campaign** và chọn một dự án PASS.
3. Mở link đăng ký nếu cần lấy link ref, dán link ref rồi bấm **Sinh content**.
4. Sửa từng dòng. Dòng đỏ phải sửa; sau mỗi lần sửa bấm **Kiểm tra lại**.
5. Khi không còn lỗi, bấm **Triển khai sang Bước 3**.

Thao tác này chỉ lưu kế hoạch nội bộ và audit; không tạo, sửa, bật hoặc dừng Google Ads.
Rollback bằng `ROLLBACK-AFI-OS-0.2.104.command`.

## Update 0.2.103 — Hoàn vốn đúng sheet và chấm điểm

Chạy `UPDATE-AFI-OS-0.2.103.command` một lần. Công thức hoàn vốn dùng `3× bid thấp`,
`0,5× bid cao` và tỷ giá cố định `26.000 VND/USD`. Khi tỷ giá quy ước đổi, sửa
`PAYBACK_FX_VND_PER_USD` trong `src/afi_os/config.py` rồi phát hành update mới.

`POST /api/appraise` trả `score.total` 0–100, `score.pass` và flags thật. Cấm Ads,
cấm brand và one-time vẫn chỉ cảnh báo. Rollback bằng
`ROLLBACK-AFI-OS-0.2.103.command`.

## Update 0.2.102 — Hiển thị commission đã xác nhận

Chạy `UPDATE-AFI-OS-0.2.102.command` một lần. Pictory sẽ hiện `50% recurring`
kèm cảnh báo đây là mức tối đa; con số đó không được dùng để tính hoàn vốn.
Rollback bằng `ROLLBACK-AFI-OS-0.2.102.command`.

## Update 0.2.101 — Check dự án Dot1.1

1. Mở thư mục `AFI-OS-update-0.2.101` và chạy
   `UPDATE-AFI-OS-0.2.101.command` đúng một lần.
2. Mở AFI-OS, vào **Bước 1 · Check dự án**.
3. Nhập một domain rồi bấm **Check dự án**; hoặc bấm **Dán danh sách** để kiểm tra
   tối đa 25 domain theo từng dòng.
4. Xem đủ 10 thẻ dữ liệu. Thẻ chưa có nguồn hiện `Đang chờ nguồn`, không để trống
   và không biến thành số 0.
5. `Lưu và chuyển Bước 2` chỉ sáng khi engine chấm điểm trả `pass=true`.

API ổn định cho engine là `POST /api/appraise` với body `{"domain":"example.com"}`.
PPC chỉ cảnh báo, commission chưa được tự chấp nhận và Google Ads chỉ đọc.
Rollback bằng `ROLLBACK-AFI-OS-0.2.101.command`.

## Update 0.2.100 — Chỉ nhập domain, tự động lấy số liệu

1. Chạy `UPDATE-AFI-OS-0.2.100.command` một lần.
2. Nếu chưa có nguồn traffic, mở thư mục `AFI-OS` và chạy
   `SETUP-TRAFFIC-DATA.command`; chọn Similarweb hoặc Semrush rồi nhập API key.
3. Vào **Tìm dự án**, nhập đúng domain và bấm **Kiểm tra dự án**.
4. AFI-OS tự đọc Affiliate/Terms, traffic website, Keyword Planner và mọi nguồn đã kết nối.
   Mỗi nguồn thiếu hiện `CONNECTION_REQUIRED` kèm việc cần làm; không còn bảng trống.
5. API key chỉ nằm trong macOS Keychain. Số traffic được lưu kèm nguồn, tháng dữ liệu,
   confidence và thời hạn 45 ngày.

Traffic website không phải search volume. Keyword Planner lấy tiếng Anh/toàn cầu và chỉ đọc.
Terms chỉ cảnh báo, commission không được tự duyệt, Project/campaign không bị loại hoặc dừng.
Rollback bằng `ROLLBACK-AFI-OS-0.2.100.command`.

## Update 0.2.99 — Traffic có nguồn, không cần Similarweb API

1. Chạy `UPDATE-AFI-OS-0.2.99.command`.
2. Vào **Tìm dự án**, mở một dự án rồi tìm khối **Bổ sung traffic website có nguồn**.
3. Nhập traffic/tháng, ngày kiểm tra và URL trang đã dùng để tra; hoặc chọn CSV có
   ba cột bắt buộc `website_traffic_monthly,source_url,observed_at`.
4. Bấm **Lưu traffic có nguồn**. Số mới hiện ngay trong Check bước 1 và bảng chấm điểm.
5. Sau 45 ngày snapshot chuyển `STALE` và phải kiểm tra lại; không bị đổi thành 0.

Google Ads API tiếp tục tự đọc campaign và sẽ dùng cho Keyword Planner/CPC. Traffic
website thủ công không được gọi là traffic Google Search. Update không tạo Google Ads
write, không đổi PPC/commission/campaign. Rollback bằng
`ROLLBACK-AFI-OS-0.2.99.command`.

## Update 0.2.98 — Check dự án đầy đủ và chuyển Bước 2

1. Chạy `UPDATE-AFI-OS-0.2.98.command`.
2. Vào **Tìm dự án**, nhập domain rồi mở hồ sơ.
3. Bước 1 hiện mọi nhóm dữ liệu. Ô thiếu luôn ghi nguồn/API cần kết nối.
4. Xem phần **Hoàn vốn ước tính**. Hệ thống chỉ tính khi có giá gói cùng tiền tệ
   với CPC và commission đã được chấp nhận, không có conflict.
5. Khi nút sáng, bấm **Lưu và chuyển Bước 2**. Mở menu **Chuẩn bị campaign** để
   thấy dự án vừa lưu và mở lại toàn bộ snapshot Bước 1.

Cảnh báo Terms không loại Project. Update không đổi permission, không tạo/sửa/dừng
campaign và không ghi Google Ads. Rollback bằng `ROLLBACK-AFI-OS-0.2.98.command`.

## Update 0.2.97 — Ngày quan sát của mạng lưới

Chạy `UPDATE-AFI-OS-0.2.97.command` như một update một-bấm. Trong hồ sơ dự án,
nhánh nhà quảng cáo phải hiện ngày `kiểm tra`, còn từng dự án liên quan hiện ngày
`quan sát`. Đây là ngày snapshot nguồn, không bị gọi nhầm là ngày quảng cáo hoạt
động. Rollback bằng `ROLLBACK-AFI-OS-0.2.97.command`.

## Update 0.2.96 — Mạng lưới dự án tự mở rộng

1. Mở `AFI-OS-update-0.2.96` và chạy `UPDATE-AFI-OS-0.2.96.command`.
2. AFI-OS mở thẳng **Tìm dự án**. Tìm một domain đã lưu hoặc nhập domain mới.
3. Bấm **Mở hồ sơ** của dự án.
4. Khối **Mạng lưới tự mở rộng** tự hiện từng nhà quảng cáo và mọi dự án khác đã
   quan sát cho nhà quảng cáo đó; không cần bấm nhà quảng cáo.
5. Bấm một dự án ngoài ở nhánh để lấy nó làm trung tâm và tự bung tầng kế tiếp.

`Chưa thu thập` không có nghĩa là 0. Mỗi quan hệ có URL nguồn và ngày quan sát khi
có dữ liệu. Update không đổi PPC, commission, campaign hoặc Google Ads. Rollback
bằng `ROLLBACK-AFI-OS-0.2.96.command`.

## Update 0.2.95 — Truy vết dự án

1. Mở `AFI-OS-update-0.2.95` và chạy `UPDATE-AFI-OS-0.2.95.command`.
2. Vào **Quản lý dự án**.
3. Nhập domain ở khối màu xanh **Truy vết dự án** rồi bấm nút cùng tên.
4. Dùng **Lọc hồ sơ đã lưu** bên dưới chỉ khi cần tìm lại Project đã có.

Truy vết lưu Project trước, sau đó rà nguồn; PPC không tự đổi và không tạo Google
Ads write. Rollback bằng `ROLLBACK-AFI-OS-0.2.95.command`.

## Update 0.2.94 — Domain intake

1. Mở `AFI-OS-update-0.2.94`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.94.command` → **Open/Mở**.
3. Vào **Quản lý dự án**, nhập một domain chưa có rồi bấm **Lọc**.
4. Bấm **Thêm dự án và bắt đầu rà nguồn**; hồ sơ phải hiện ngay cả khi nguồn
   Terms/advertiser/campaign chưa thu thập xong.

Project không bị loại; PPC vẫn `NOT_CHECKED`, commission chưa được tự quyết và
không có Google Ads write. Rollback bằng `ROLLBACK-AFI-OS-0.2.94.command`.

## Update 0.2.93 — Maintenance proposal safety

1. Mở `AFI-OS-update-0.2.93`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.93.command` → **Open/Mở**.
3. Sau maintenance, Snov phải còn ba proposal chờ duyệt: `BRAND_KEYWORD`,
   `PAID_SEARCH`, `NON_BRAND`; mọi quyền chuẩn vẫn là `NOT_CHECKED`.

Rollback bằng `ROLLBACK-AFI-OS-0.2.93.command`.

## Update 0.2.92 — Missing-state copy hotfix

1. Mở `AFI-OS-update-0.2.92`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.92.command` → **Open/Mở**.
3. Chờ báo cập nhật thành công; dữ liệu SQLite và snapshot Snov được giữ nguyên.
4. Làm mới giao diện và xác nhận Project Radar dùng `Chưa thu thập` hoặc
   `Chưa đủ dữ liệu`, không dùng số 0 giả.

Rollback bằng `ROLLBACK-AFI-OS-0.2.92.command`.

## Update 0.2.91 — Truthful advertiser snapshots

1. Mở `AFI-OS-update-0.2.91`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.91.command` → **Open/Mở**.
3. Vào **Quản lý dự án**, lọc `snov.io`: advertiser phải hiện số có nguồn;
   Active 30d vẫn phải là `Chưa đủ dữ liệu` nếu nguồn không có last-seen đầy đủ.
4. Vào **Truy vết quảng cáo** để nhập batch mới bằng `ID | Tên | Số quảng cáo`.

PPC và commission vẫn là proposal chờ duyệt. Update không dừng/loại campaign và
không tạo Google Ads write. Rollback bằng `ROLLBACK-AFI-OS-0.2.91.command`.

## Update 0.2.90 — Program ↔ Project sync

1. Mở `AFI-OS-update-0.2.90`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.90.command` → **Open/Mở**.
3. Vào **Quản lý dự án**, nhập `snov.io` rồi bấm **Lọc**; Snov phải xuất hiện.

Maintenance tự tạo hồ sơ Project còn thiếu nhưng giữ nguyên mọi workflow đã nhập. Rollback bằng `ROLLBACK-AFI-OS-0.2.90.command`.

## Update 0.2.89 — Command Center UI hotfix

1. Mở `AFI-OS-update-0.2.89`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.89.command` → **Open/Mở**.
3. Sau khi cập nhật, luôn mở `http://127.0.0.1:8765/`; không thêm `/**` sau địa chỉ.

Giao diện phải hiện `UI HOTFIX · v0.2.89` và không còn dòng `Lỗi dữ liệu: job is not defined`. Rollback bằng `ROLLBACK-AFI-OS-0.2.89.command`.

## Update 0.2.88 — Wake-safe 24/7

1. Mở `AFI-OS-update-0.2.88`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.88.command` → **Open/Mở**.
3. Updater tạo backup, cài lịch maintenance mới và khởi động lại hai LaunchAgent.

Maintenance chạy lúc phút 00 và 30 mỗi giờ. Sau khi máy thức dậy, launchd sẽ chạy bù mốc lịch bị lỡ. Rollback bằng `ROLLBACK-AFI-OS-0.2.88.command`.

## Update 0.2.87 — Exception Queue

1. Mở thư mục `AFI-OS-update-0.2.87`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.87.command` → **Open/Mở**.
3. Chờ dòng xác nhận thành công; dữ liệu cũ và dịch vụ 24/7 được giữ nguyên.

Nếu Operations Inbox báo automation hết lần thử, bấm **Mở đúng job**, đọc lỗi và chỉ bấm **Thử lại ngay** sau khi nguyên nhân đã được xử lý. Rollback bằng `ROLLBACK-AFI-OS-0.2.87.command` và gõ `ROLLBACK`.

## Update 0.2.86 — Hàng đợi tự động bền vững

### Cập nhật một lần bấm

1. Mở thư mục `AFI-OS-update-0.2.86`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.86.command` → **Open/Mở**.
3. Chờ dòng `Cập nhật AFI-OS 0.2.86 thành công`; dịch vụ 24/7 tự chạy lại.
4. Mở **Command Center → Hàng đợi tự động**.

Trạng thái bình thường là `0 đến hạn · 0 chờ lại · 0 lỗi cuối`. Khi Terms đến hạn,
job `Rà Terms có nguồn` xuất hiện và được maintenance nhận bằng lease. Lỗi tạm thời chờ
retry tự động. Chỉ khi đã hết số lần thử, job mới hiện `Cần kiểm tra` và nút
`Thử lại ngay`.

Nút retry chỉ đổi trạng thái job local và ghi audit; không mở PPC, không loại dự án,
không sửa/dừng campaign và không tạo Google Ads write. Rollback bằng
`ROLLBACK-AFI-OS-0.2.86.command`, gõ `ROLLBACK`.

## Update 0.2.85 — Project Portfolio & Truth Drawer

### Cập nhật một lần bấm

1. Mở thư mục update `AFI-OS-update-0.2.85`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.85.command` → **Open/Mở**.
3. Giữ cửa sổ Terminal mở đến khi hiện `Cập nhật AFI-OS 0.2.85 thành công`.
4. AFI-OS tự mở; chọn menu **Quản lý dự án**.

Updater tự dừng service, checkpoint WAL, tạo verified backup + SHA-256, cài payload,
chạy migration, đối chiếu row counts/integrity/foreign keys và tự rollback nếu có lỗi.
Không chép database hoặc credential vào gói update.

### Kiểm tra sau update

- Góc trên hiện `PROJECT PORTFOLIO · v0.2.85`; API health cũng là `0.2.85`.
- Pictory hiện `Tạm dừng`, `Không đăng ký được`, commission `50%`, PPC chưa xác minh.
- Fliki hiện một campaign; bấm CTR/cost để xem nguồn Google Ads và Customer ID.
- Bấm bất kỳ metric nào để mở `WHY THIS NUMBER?`; missing data phải hiện `Chưa có`.
- Bấm `Mở` để đổi workflow. Thao tác này chỉ ghi local audit, không sửa Google Ads.

Rollback khi thật sự cần bằng `ROLLBACK-AFI-OS-0.2.85.command`, gõ `ROLLBACK`.
Rollback tạo emergency backup trước khi phục hồi code và database 0.2.84.

## Update 0.2.84 — Operations mở đúng snapshot cần duyệt

1. Mở `UPDATE-AFI-OS-0.2.84.command`; updater tự backup và giữ nguyên database.
2. Trong **Operations Inbox**, bấm `Mở hàng đợi` ở ngoại lệ snapshot quảng cáo.
3. AFI-OS chuyển sang **Truy vết quảng cáo**, cuộn tới đúng snapshot cũ nhất và làm nổi bật hàng cần xử lý.
4. Con trỏ vào ô advertiser/domain đầu tiên còn thiếu; nếu đã đủ thì vào nút `Chấp nhận`.
5. Nếu snapshot đã được xử lý ở tab khác, AFI-OS dùng snapshot tiếp theo hoặc báo hàng đợi đã trống.
6. Điều hướng này không tự chấp nhận/loại, không tạo graph, không ghi Google Ads và không đổi PPC/commission.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.84.command`.

## Update 0.2.83 — Hàng đợi duyệt snapshot quảng cáo

1. Mở `UPDATE-AFI-OS-0.2.83.command`; updater tự backup và giữ nguyên database.
2. Trong **Truy vết quảng cáo**, có thể lưu ngay URL + evidence khi chưa biết advertiser hoặc domain: nút hiện `Lưu để duyệt sau`, snapshot vào hàng đợi và chưa tạo graph.
3. Chrome Capture Helper cũng cho phép để trống hai trường này. Sau update, vào `chrome://extensions` và bấm **Reload** cho AFI-OS Capture Helper để nạp bản mới.
4. Mở **Operations Inbox → Mở hàng đợi** hoặc mục **Truy vết quảng cáo**. Bấm `Xem đầy đủ evidence` trước khi quyết định.
5. Nhập đúng cả tên advertiser + domain dự án rồi bấm `Chấp nhận` để tạo observation. Trong lúc lưu, cả hàng bị khóa để không gửi hai quyết định trái nhau.
6. Bấm `Loại` và nhập lý do cụ thể nếu snapshot không liên quan. Raw evidence, người duyệt, thời điểm và lý do vẫn được giữ để kiểm toán; quyết định không thể đổi ngược từ hàng đợi.
7. Nếu điền đủ advertiser + domain ngay khi capture, nút đổi thành `Lưu và cập nhật graph` và luồng có cấu trúc cũ vẫn hoạt động như trước.
8. Chưa duyệt thì snapshot không tạo advertiser/project; không có thao tác ghi Google Ads, thay đổi quyền PPC hoặc quyết định commission.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.83.command`.

## Update 0.2.82 — Độ mới snapshot Google Ads trong ngày

1. Mở `UPDATE-AFI-OS-0.2.82.command`; updater tự backup và giữ nguyên database.
2. Command Center hiện riêng thời điểm file nguồn và mốc làm mới sau 6 giờ.
3. Nếu snapshot của hôm nay quá 6 giờ, Operations Inbox tạo cảnh báo không chặn để automation ưu tiên xuất/nhập lại.
4. Kết quả API chỉ đọc của chính ngày hôm nay tự triệt tiêu cảnh báo CSV.
5. Không có thao tác ghi Google Ads; campaign và project không bị loại, sửa hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.82.command`.

## Update 0.2.81 — Tự tìm OAuth Desktop JSON

1. Mở `UPDATE-AFI-OS-0.2.81.command`; updater tự backup và giữ nguyên database.
2. Sau khi tải OAuth Desktop JSON từ Google Cloud vào Downloads, mở `SETUP-GOOGLE-ADS-READ-ONLY.command`.
3. Nếu chỉ có một Desktop JSON hợp lệ, AFI-OS tự dùng file đó; không cần kéo đường dẫn.
4. Nếu có nhiều file hợp lệ, hệ thống bắt buộc chọn rõ để không dùng nhầm client.
5. Nhập MCC `987-654-3210` khi được hỏi; Developer Token nhập ở ô ẩn, không dán vào chat.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.81.command`.

## Update 0.2.80 — Chặn link ngoài không an toàn

1. Mở `UPDATE-AFI-OS-0.2.80.command`; updater tự backup và giữ nguyên database.
2. Link signup, Terms, commission, research, capture và FX hợp lệ tiếp tục mở ở tab mới.
3. URL ngoài HTTP(S), thiếu hostname hoặc malformed chỉ hiện dạng chữ và không thể bấm.
4. Giao diện không còn bị vỡ khi lịch sử cũ chứa URL không parse được.
5. Thay đổi chỉ ở render; không mở PPC, quyết định commission hay loại/dừng project/campaign.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.80.command`.

## Update 0.2.79 — Evidence Pack tự chứa nguồn đăng ký

1. Mở `UPDATE-AFI-OS-0.2.79.command`; updater tự backup và giữ nguyên database.
2. Trong Terms Evidence Center, chọn chương trình rồi bấm `Xuất evidence pack`.
3. `program-summary.json` và README trong ZIP hiện signup URL cùng loại nguồn `OFFICIAL/PARTNER_PORTAL`.
4. Signup URL vẫn xuất hiện trong source inventory nếu chưa có research/evidence/fact nào.
5. Export chỉ đọc; không mở PPC, không quyết định commission và không loại/dừng project hoặc campaign.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.79.command`.

## Update 0.2.78 — Hiện nguồn đăng ký an toàn

1. Mở `UPDATE-AFI-OS-0.2.78.command`; updater tự backup và giữ nguyên database.
2. Vào Terms Evidence Center: mỗi chương trình có link đăng ký sẽ hiện “Mở link đăng ký” cùng nhãn nguồn.
3. Link cùng domain merchant hiện “Nguồn merchant chính thức”; link ngoài domain hiện “Cổng đối tác”.
4. URL ngoài HTTP(S) bị từ chối khi lưu và không thể trở thành link bấm được trên giao diện.
5. Nguồn đăng ký không mở PPC, không quyết định commission và không loại/dừng project hoặc campaign.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.78.command`.

## Update 0.2.77 — Điền nguồn đăng ký còn trống

1. Mở `UPDATE-AFI-OS-0.2.77.command`; updater tự backup và giữ nguyên database.
2. Lần rà Terms kế tiếp tự điền `signup_url` nếu chương trình đã tồn tại nhưng ô này còn trống.
3. Collector dùng URL evidence/commission cụ thể; URL đã lưu, gồm partner portal ngoài domain, không bị ghi đè.
4. Thay đổi metadata được ghi audit; commission vẫn là fact riêng và PPC không tự mở.
5. Fliki được kiểm chứng với `https://fliki.ai/affiliate-program`; bốn permission vẫn `NOT_CHECKED`.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.77.command`.

## Update 0.2.76 — OAuth qua tài khoản quản lý Google Ads

1. Mở `UPDATE-AFI-OS-0.2.76.command`; updater tự backup và giữ nguyên database.
2. Khi có Developer Token và OAuth Desktop JSON, mở `SETUP-GOOGLE-ADS-READ-ONLY.command`.
3. Kéo file JSON vào cửa sổ; nếu token thuộc MCC, nhập Manager Customer ID 10 chữ số, ví dụ `987-654-3210`; nếu truy cập trực tiếp thì để trống.
4. Manager ID được dùng ngay trong preflight và chỉ vào Keychain sau khi Google chấp nhận truy vấn chỉ đọc cho mọi tài khoản đã lưu.
5. Giao diện hiện “MCC đã cấu hình” nhưng không lộ ID/token; CSV fallback vẫn chạy nếu setup chưa hoàn tất.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.76.command`.

## Update 0.2.75 — Tự khôi phục Campaign ID đã biết

1. Mở `UPDATE-AFI-OS-0.2.75.command`; updater tự backup và giữ nguyên database.
2. CSV thiếu `Campaign ID` phải có `Customer ID` trực tiếp và tên campaign khớp duy nhất trong đúng tài khoản.
3. Nếu khớp, AFI-OS tự dùng ID đã lưu và hiện số dòng đã khôi phục trên Command Center.
4. Sai tài khoản, tên lạ, tên trùng hoặc Customer ID trống đều bị chặn và ghi 0 dòng.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.75.command`.

## Update 0.2.74 — Không xoá metadata khi báo cáo thiếu cột

1. Mở `UPDATE-AFI-OS-0.2.74.command`; updater tự backup và giữ nguyên database.
2. Báo cáo có `Customer ID` đúng vẫn nhập số liệu khi thiếu Budget/Status/Type/Currency.
3. Metadata campaign cũ chỉ đổi khi CSV thật sự cung cấp giá trị tương ứng.
4. CSV thiếu cả Customer ID lẫn Currency code bị chặn với `ACCOUNT_CURRENCY_REQUIRED` và ghi 0 dòng.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.74.command`.

## Update 0.2.73 — Kiểm Customer ID trước chống trùng

1. Mở `UPDATE-AFI-OS-0.2.73.command`; updater tự backup và giữ nguyên database.
2. Account identity gate đọc mọi dòng campaign parse hợp lệ trước khi metric được dedupe.
3. Nếu dòng trùng phía sau để trống Customer ID, cả file vẫn bị chặn và ghi 0 dòng.
4. Dedupe metric và CSV legacy không có cột Customer ID tiếp tục hoạt động như trước.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.73.command`.

## Update 0.2.72 — Customer ID phải có giá trị thật trong báo cáo

1. Mở `UPDATE-AFI-OS-0.2.72.command`; updater tự backup và giữ nguyên database.
2. Báo cáo có cột `Customer ID` phải có giá trị ở mọi dòng campaign được đọc.
3. Nếu một dòng để trống, file bị chặn với cảnh báo `CUSTOMER_ID_VALUE_REQUIRED`; không có campaign/spend nào được ghi.
4. CSV cũ hoàn toàn không có cột vẫn dùng được khi chỉ có một Ads account và tiền tệ khớp.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.72.command`.

## Update 0.2.71 — Hiện rõ biên nhận an toàn khi nhập Google Ads

1. Mở `UPDATE-AFI-OS-0.2.71.command`; updater tự backup và giữ nguyên database.
2. Command Center hiện Customer ID đích bên cạnh trạng thái tự nhập Google Ads.
3. Nếu báo cáo sai tài khoản, màn hình hiện số file bị chặn và Customer ID cần đăng nhập để xuất lại.
4. File mismatch không được nhập; campaign, spend và mapping cũ vẫn giữ nguyên.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.71.command`.

## Update 0.2.70 — Chặn nhập nhầm tài khoản Google Ads

1. Mở `UPDATE-AFI-OS-0.2.70.command`; updater tự backup và giữ nguyên database.
2. Báo cáo mới nên có thêm `Customer ID`; `Day`, `Campaign state` và `Currency code` được nhận tự động.
3. Nếu Customer ID khác tài khoản AFI-OS, file không được nhập và Operations chỉ hiện cảnh báo.
4. CSV cũ chưa có Customer ID vẫn dùng được khi chỉ có một Ads account và tiền tệ khớp.
5. Google Ads vẫn chỉ đọc; campaign/project không bị loại hoặc dừng, PPC không tự mở.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.70.command`.

## Update 0.2.69 — Hiện rõ loại nguồn Terms

1. Mở `UPDATE-AFI-OS-0.2.69.command`; updater tự backup và giữ nguyên database.
2. Trong Terms Evidence, mỗi URL hiện nhãn nguồn merchant/cổng đối tác/chưa xác định.
3. Lịch sử heartbeat và Evidence Pack format 3 dùng đúng cùng một bản đồ nguồn.
4. Audit cũ có snapshot từ collector chính thức vẫn đọc được; nhãn lạ không được tin cậy.
5. PPC vẫn `NOT_CHECKED`; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.69.command`.

## Update 0.2.68 — Đọc đúng trang đăng ký ở cổng đối tác

1. Mở `UPDATE-AFI-OS-0.2.68.command`; updater tự backup và giữ nguyên database.
2. Nếu chương trình đã lưu link đăng ký ngoài domain, collector `official-web-v6` chỉ đọc đúng URL đó.
3. Nguồn được gắn `PARTNER_PORTAL`; hệ thống không bò link khác, không dùng/gửi thông tin đăng nhập.
4. Evidence/commission chỉ là proposal; nguồn mâu thuẫn chuyển `CONFLICT`.
5. PPC vẫn `NOT_CHECKED`; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.68.command`.

## Update 0.2.67 — Không báo lỗi cho đường dẫn dò thử không tồn tại

1. Mở `UPDATE-AFI-OS-0.2.67.command`; updater tự backup và giữ nguyên database.
2. Collector `official-web-v5` đánh dấu nguồn URL trước khi fetch.
3. 404/410 của standard probe bị bỏ; stored/discovered URL bị 404 vẫn ghi lỗi.
4. 5xx, rate limit và lỗi mạng vẫn tự retry theo lịch 6 giờ.
5. PPC vẫn `NOT_CHECKED`; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.67.command`.

## Update 0.2.66 — Không báo đổi nguồn giả từ trang bị cắt

1. Mở `UPDATE-AFI-OS-0.2.66.command`; updater tự backup và giữ nguyên database.
2. Heartbeat kế tiếp dùng collector `official-web-v4`.
3. Hash khác trên trang `truncated=true` được ghi `PARTIAL`, không tạo source-change warning.
4. Câu PPC/commission thật đổi vẫn tạo proposal/conflict độc lập và không tự mở quyền.
5. PPC vẫn `NOT_CHECKED`; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.66.command`.

## Update 0.2.65 — Gộp URL nguồn bị gắn tracking

1. Mở `UPDATE-AFI-OS-0.2.65.command`; updater tự backup và giữ nguyên database.
2. Heartbeat kế tiếp dùng collector `official-web-v3` và gộp URL chỉ khác `nav`/`utm_*`/click ID.
3. Query nghiệp vụ, document ID, signature và affiliate ref vẫn được giữ nguyên.
4. Source-change comparison cũng gộp snapshot tracking cũ, không báo mất nguồn giả.
5. PPC vẫn `NOT_CHECKED`; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.65.command`.

## Update 0.2.64 — Không bỏ trang Terms lớn

1. Mở `UPDATE-AFI-OS-0.2.64.command`; updater tự backup và giữ nguyên database.
2. Heartbeat kế tiếp dùng collector `official-web-v2` và đọc tối đa 1 MB đầu mỗi nguồn.
3. Trang bị cắt ngắn vẫn có thể cung cấp link/proposal nhưng được đánh dấu trong audit.
4. Evidence Pack format 2 hiện `latest_truncated_source_urls` và số trang của lần rà gần nhất.
5. PPC vẫn `NOT_CHECKED` khi chưa review evidence; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.64.command`.

## Update 0.2.63 — Tải Evidence Pack ngay từ Inbox

1. Mở `UPDATE-AFI-OS-0.2.63.command`; updater tự backup và giữ nguyên database.
2. Trong Operations Inbox, bấm `Tải pack` ngay tại cảnh báo của chương trình.
3. `Xem commission`/`Xem lần rà` vẫn mở Terms và chọn đúng chương trình; nút export luôn đồng bộ.
4. Shortcut dùng đúng endpoint ZIP chỉ đọc của 0.2.62.
5. Không đổi PPC, evidence/commission decision, campaign/project hoặc Google Ads.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.63.command`.

## Update 0.2.62 — Xuất Terms Evidence Pack

1. Mở `UPDATE-AFI-OS-0.2.62.command`; updater tự backup và giữ nguyên database.
2. Vào Terms Evidence, chọn chương trình rồi bấm `Xuất evidence pack`.
3. ZIP có README, summary JSON, bốn CSV evidence/research/audit và manifest SHA-256.
4. Commission facts luôn ở file riêng; thiếu PPC evidence vẫn hiển thị `NOT_CHECKED`.
5. Export chỉ đọc, không xác nhận proposal, không loại/dừng campaign và không ghi Google Ads.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.62.command`.

## Update 0.2.61 — Backup tự động trả đúng trạng thái

1. Mở `UPDATE-AFI-OS-0.2.61.command`; updater tự backup và giữ nguyên database.
2. Khi automation chạy `BACKUP-AFI-OS.command` với `AFI_OS_NONINTERACTIVE=1`, backup thành công trả exit 0.
3. Khi mở file backup bằng tay, Terminal vẫn chờ Enter để người dùng đọc kết quả.
4. Checksum, integrity, foreign key và schema verification không đổi.
5. PPC, campaign/project, commission và Google Ads từ xa không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.61.command`.

## Update 0.2.60 — Nâng metadata snapshot legacy đúng thời điểm nguồn

1. Mở `UPDATE-AFI-OS-0.2.60.command`; updater tự backup và giữ nguyên database.
2. Lượt maintenance đầu tự thay confirmation legacy bằng metadata có mtime và phạm vi tài khoản/ngày.
3. Thời điểm quét không còn được dùng để quyết định snapshot nào mới hơn.
4. Runtime vẫn giữ đúng 9 dòng trong lúc nâng metadata; không cần xuất lại CSV.
5. PPC, campaign/project, commission và Google Ads từ xa không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.60.command`.

## Update 0.2.59 — Snapshot Google Ads mới nhất luôn thắng

1. Mở `UPDATE-AFI-OS-0.2.59.command`; updater tự backup và giữ nguyên database.
2. Có thể để đồng thời file tên chuẩn và file đổi tên; hệ thống xử lý bản cũ trước, bản mới sau.
3. Runtime chỉ đếm một lần cho cùng tài khoản/ngày dù nhiều snapshot chồng nhau.
4. Nếu snapshot cũ quay lại sau bản mới, Runtime hiện “chặn N snapshot cũ” và không ghi đè dữ liệu.
5. PPC, campaign/project, commission và Google Ads từ xa không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.59.command`.

## Update 0.2.58 — Giữ dữ liệu Ads đã xác nhận qua scan rỗng

1. Mở `UPDATE-AFI-OS-0.2.58.command`; updater tự backup và giữ nguyên database.
2. Runtime hiện số nguồn/ngày/giờ xác nhận Ads gần nhất độc lập với file đang có trong Downloads.
3. Scan rỗng hoặc chỉ có file thiếu cột không xóa last-known data và không che stale warning.
4. Khi file giống hệt quay lại, checksum được tái dùng nên không tạo thêm spend hoặc audit import.
5. PPC, campaign/project và Google Ads từ xa không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.58.command`.

## Update 0.2.57 — Báo đúng cột Google Ads CSV còn thiếu

1. Mở `UPDATE-AFI-OS-0.2.57.command`; updater tự backup và giữ nguyên database.
2. Nếu CSV đổi tên thiếu Date, Inbox hướng dẫn `Phân đoạn → Thời gian → Ngày`.
3. Nếu thiếu Campaign ID, Inbox hướng dẫn `Cột → Thuộc tính → ID chiến dịch`.
4. File commission không bị gắn nhầm; cảnh báo tự mất khi có báo cáo hợp lệ mới hơn.
5. Hai file cùng checksum chỉ được phân tích một lần; PPC/campaign/project không đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.57.command`.

## Update 0.2.56 — Tự nhận diện Google Ads CSV bị đổi tên

1. Mở `UPDATE-AFI-OS-0.2.56.command`; updater tự backup và giữ nguyên database.
2. Có thể giữ nguyên tên Google xuất hoặc đổi tên file; hệ thống nhận bằng cấu trúc cột chiến dịch.
3. File phải có ID/tên campaign, ngày, chi phí và ít nhất hai cột impressions/clicks/conversions.
4. Runtime hiện “tự nhận diện N file đổi tên”; cùng checksum vẫn chỉ nhập một lần.
5. CSV commission tương tự bị bỏ qua; PPC, campaign/project và Google Ads không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.56.command`.

## Update 0.2.55 — Cảnh báo dùng nguồn của attempt mới nhất

1. Mở `UPDATE-AFI-OS-0.2.55.command`; updater tự backup và giữ nguyên database.
2. Cảnh báo “đã đọc N URL” lấy N từ lần rà mới nhất, khớp với lịch sử attempt và kết quả research.
3. Cảnh báo manual/retry mở URL vừa kiểm tra thay vì URL cũ của research run.
4. Audit cũ chưa có source set vẫn tự fallback an toàn về run source.
5. Warning grouping, PPC, project, campaign và Google Ads không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.55.command`.

## Update 0.2.54 — Hiện đúng nguồn của lần rà hiện tại

1. Mở `UPDATE-AFI-OS-0.2.54.command`; updater tự backup và giữ nguyên database.
2. Khi kết quả trùng và research run cũ được tái sử dụng, màn hình vẫn hiện toàn bộ URL vừa đọc ở lần hiện tại.
3. Lịch sử run gốc không bị sửa; source set theo từng lần nằm trong audit trail.
4. Không có research run, evidence hoặc commission fact trùng được tạo vì thay đổi này.
5. PPC, project, campaign và Google Ads không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.54.command`.

## Update 0.2.53 — Theo dõi nguồn Terms thay đổi

1. Mở `UPDATE-AFI-OS-0.2.53.command`; updater tự backup và giữ nguyên database.
2. Sau lần rà đầu, hệ thống lưu SHA-256 của phần văn bản liên quan affiliate/PPC/commission cho từng URL.
3. Lần rà sau phân biệt nguồn mới, nguồn mất, nội dung chính sách đổi hoặc nguồn tạm thời không đọc được.
4. Lịch sử rà hiện thay đổi theo URL; Inbox gộp nó vào cảnh báo Terms cùng chương trình để không nhân việc.
5. Hệ thống không lưu toàn bộ trang và bỏ qua thay đổi footer không liên quan.
6. Đây chỉ là cảnh báo: PPC, project, campaign và Google Ads không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.53.command`.

## Update 0.2.52 — Nhớ nguồn Terms đã rà

1. Mở `UPDATE-AFI-OS-0.2.52.command`; updater tự backup và giữ nguyên database.
2. Mỗi lần rà lưu đầy đủ URL trang chính thức liên quan đã đọc, kể cả khi chưa trích được PPC/commission.
3. Lần rà sau tự ưu tiên các URL này nên đường dẫn Terms đặc biệt không phải tìm lại từ đầu.
4. Nguồn đã reject và không còn evidence/fact hợp lệ sẽ không được tái dùng qua lịch sử.
5. Mọi URL vẫn phải qua chặn HTTPS, cùng domain, public IP, redirect, port và giới hạn kích thước.
6. Việc nhớ nguồn không mở PPC; campaign/project vẫn được giữ và chỉ cảnh báo.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.52.command`.

## Update 0.2.51 — Backup lỗi tự bị loại và được tạo bản thay thế

1. Mở `UPDATE-AFI-OS-0.2.51.command`; updater tự backup và giữ nguyên database.
2. System / Backup hiện `ĐÃ XÁC MINH`, sai checksum, lỗi toàn vẹn, lỗi liên kết hoặc sai schema cho từng bản.
3. Chỉ backup `ĐÃ XÁC MINH` được tính vào lịch 24 giờ và được Restore cân nhắc.
4. Nếu backup lịch mới nhất bị lỗi, Runtime báo cần kiểm tra và heartbeat 30 phút tự tạo bản thay thế.
5. File lỗi vẫn được giữ để chẩn đoán; hệ thống không âm thầm xóa hoặc dùng nó để Restore.
6. PPC, campaign/project, commission facts và Google Ads remote state không thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.51.command`.

## Update 0.2.50 — Một nguyên nhân Terms, một cảnh báo Inbox

1. Mở `UPDATE-AFI-OS-0.2.50.command`; updater tự backup và giữ nguyên database.
2. Nếu một chương trình vừa thiếu evidence PPC vừa có campaign đang chạy, Inbox chỉ hiện một cảnh báo gốc.
3. Cảnh báo đó hiện số lượng và tên campaign liên quan; Risk & Exposure vẫn giữ chi tiết từng campaign.
4. Thiếu nguồn thủ công hoặc retry tạm thời cũng không tạo thêm cảnh báo campaign trùng nguyên nhân.
5. Quyết định evidence `PROHIBITED`/`CONFLICT` vẫn tách riêng để người vận hành xét đúng rủi ro.
6. PPC vẫn `NOT_CHECKED` khi chưa đủ bằng chứng; campaign/project không bị loại hoặc dừng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.50.command`.

## Update 0.2.49 — Tách lần rà khỏi evidence PPC

1. Mở `UPDATE-AFI-OS-0.2.49.command`; updater tự backup và giữ nguyên database.
2. Cột “Lần rà / evidence” hiện thời điểm automation đã kiểm tra và trạng thái nguồn.
3. “Không thấy quyền PPC công khai” nghĩa là đã rà nhưng chưa có bằng chứng để mở permission.
4. Operations Inbox theo dõi trường hợp này bằng warning, không tính là việc cần người dùng xác nhận.
5. `MANUAL_INPUT_REQUIRED` và `RETRY_REQUIRED` giữ luồng cũ, không bị nhân cảnh báo.
6. PPC vẫn `NOT_CHECKED`; campaign/project vẫn được giữ và Google Ads remote state không đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.49.command`.

## Update 0.2.48 — Inbox chỉ đếm quyết định thật

1. Mở `UPDATE-AFI-OS-0.2.48.command`; updater tự backup và giữ nguyên database.
2. Nhiều commission proposal của cùng chương trình hiện thành một việc cần quyết định.
3. Các scope `NOT_CHECKED` hiện thành một cảnh báo theo dõi, không bắt xác nhận vô nghĩa.
4. Nhiều campaign cùng chương trình hiện một cảnh báo; từng campaign vẫn còn ở Risk & Exposure.
5. Lịch sử lần rà hiện đúng lần nào tái dùng một research run đã có.
6. Pricing discount gần nội dung affiliate không được nhập nhầm thành commission fact.
7. Mở việc commission vẫn thấy từng fact để ACCEPT/REJECT riêng; không có fact nào bị gộp dữ liệu.
8. PPC, campaign/project và Google Ads remote state không tự thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.48.command`.

## Update 0.2.47 — không nhân permission proposal khi nguồn đổi câu chữ

1. Mở `UPDATE-AFI-OS-0.2.47.command`; updater tự backup và giữ nguyên database.
2. Cùng URL + scope + decision sẽ refresh proposal tự động đang có.
3. Evidence ACCEPTED/REJECTED hoặc nhập tay được giữ nguyên.
4. Decision mới tạo proposal riêng để cảnh báo conflict; không tự đổi canonical PPC.
5. Audit lưu before/after và xác nhận campaign/project vẫn warning-only.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.47.command`.

## Update 0.2.46 — không nhân commission proposal khi nguồn đổi câu chữ

1. Mở `UPDATE-AFI-OS-0.2.46.command`; updater tự backup và giữ nguyên database.
2. Cùng nguồn + rate + loại tương thích sẽ refresh proposal tự động đang có.
3. Fact đã ACCEPTED/REJECTED hoặc nhập tay được giữ nguyên; claim mới tạo proposal mới.
4. Audit lưu trước/sau, checked_at mới và xác nhận `permissions_changed=false`.
5. Pictory vẫn `CONFLICT`; PPC giữ `NOT_CHECKED` và dự án không bị loại.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.46.command`.

## Update 0.2.45 — bảo vệ quota Google Ads API

1. Mở `UPDATE-AFI-OS-0.2.45.command`; updater tự backup và giữ nguyên database.
2. CSV và Terms vẫn được kiểm tra mỗi 30 phút; Google Ads API chỉ chạy mỗi 6 giờ.
3. Lỗi mạng/rate limit tự thử lại sau 6 giờ; lỗi OAuth chờ 24 giờ và yêu cầu đăng nhập.
4. Sau khi `SETUP-GOOGLE-ADS-READ-ONLY.command` thành công, một lần API được xếp ngay.
5. Runtime hiện mốc API tiếp theo; API vẫn SELECT-only và write operations luôn tắt.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.45.command`.

## Update 0.2.44 — updater tự viết lại LaunchAgent đúng phiên bản

1. Mở `UPDATE-AFI-OS-0.2.44.command`; updater tự backup và giữ nguyên database.
2. Sau migration/hậu kiểm, updater chạy `launchd_manager.py` của code vừa cài.
3. Hai plist được viết lại rồi bootstrap; health check phải đạt mới báo runtime phục hồi.
4. Rollback cũng dùng manager của code cũ vừa khôi phục, nên cadence quay về đúng bản đó.
5. Có thể xem `StartInterval=1800` bằng lệnh STATUS; bình thường không cần thao tác tay.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.44.command`.

## Update 0.2.43 — heartbeat 30 phút, không lùi lịch Terms vì update

1. Mở `UPDATE-AFI-OS-0.2.43.command`; updater tự backup và giữ nguyên database.
2. Maintenance heartbeat chạy mỗi 30 phút để phát hiện file mới và Terms vừa đến hạn.
3. Backup vẫn tối đa một lần/24 giờ; Terms ổn định 24 giờ; lỗi web retry 6 giờ.
4. Import lặp lại vẫn idempotent và maintenance lock không cho hai chu kỳ chồng nhau.
5. Runtime hiển thị ETA Terms theo nhịp 30 phút mới; permission/campaign không tự đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.43.command`.

## Update 0.2.42 — kiểm tra quyền Google Ads trước khi lưu Keychain

1. Mở `UPDATE-AFI-OS-0.2.42.command`; updater tự backup và giữ nguyên database.
2. Khi chạy `SETUP-GOOGLE-ADS-READ-ONLY.command`, hoàn tất đăng nhập Google như bình thường.
3. AFI-OS đổi refresh token và thử SearchStream chỉ đọc cho ngày hôm qua.
4. Chỉ khi Customer ID được Google chấp nhận, đủ bốn credential mới vào Keychain.
5. Nếu preflight lỗi, Keychain cũ và CSV fallback giữ nguyên; chạy lại khi token/quyền đã sẵn sàng.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.42.command`.

## Update 0.2.41 — thiết lập Google Ads không ghi dở Keychain

1. Mở `UPDATE-AFI-OS-0.2.41.command`; updater tự backup và giữ nguyên database.
2. Khi có OAuth Desktop `credentials.json` và Developer Token, mở `SETUP-GOOGLE-ADS-READ-ONLY.command`.
3. Kéo JSON vào cửa sổ, nhập Developer Token ở ô ẩn rồi đăng nhập Google.
4. OAuth phải hoàn tất trước; sau đó đủ bốn credential mới được lưu cùng một bundle.
5. Hủy đăng nhập hoặc lỗi ghi Keychain không phá bộ credential cũ; CSV fallback tiếp tục chạy.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.41.command`.

## Update 0.2.40 — Restore an toàn khi chạy 24/7 hoặc database hỏng

1. Mở `UPDATE-AFI-OS-0.2.40.command`; updater tự backup và giữ nguyên database.
2. Chỉ khi thật sự cần cứu dữ liệu, mở `RESTORE-LATEST-BACKUP.command` và gõ `RESTORE`.
3. Lệnh tự dừng server + maintenance 24/7 và xác nhận localhost đã đóng.
4. Nếu database hiện tại hỏng, schema được lấy từ migration code; raw DB/WAL/SHM vẫn được giữ.
5. Dù Restore thành công hay lỗi, hệ thống tự nạp lại đúng chế độ chạy trước đó.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.40.command`.

## Update 0.2.39 — khôi phục đúng backup và đúng schema

1. Mở `UPDATE-AFI-OS-0.2.39.command`; updater tự backup và giữ nguyên database.
2. Vào **System / Backup** để xem schema database của từng bản sao lưu.
3. Khi thật sự cần restore, mở `RESTORE-LATEST-BACKUP.command` và gõ `RESTORE`.
4. Hệ thống tự bỏ qua backup SHA sai, hỏng, lỗi foreign key hoặc khác schema.
5. Nếu không có bản tương thích, restore dừng và database hiện tại không bị thay đổi.

Rollback update bằng `ROLLBACK-AFI-OS-0.2.39.command`.

## Update 0.2.38 — chỉ retry lỗi Terms thật sự tạm thời

1. Mở `UPDATE-AFI-OS-0.2.38.command`; updater tự backup và giữ nguyên database.
2. Timeout, lỗi mạng, 408/425/429 và 5xx tự retry sau 6 giờ.
3. 404/410 hoặc URL/content không hợp lệ không bị retry vô hạn.
4. No-evidence cố định mới hiện việc cần nguồn; dự án vẫn được giữ với cảnh báo.

Rollback bằng `ROLLBACK-AFI-OS-0.2.38.command`.

## Update 0.2.37 — không trượt chu kỳ Terms vì lệch vài giây

1. Mở `UPDATE-AFI-OS-0.2.37.command`; updater tự backup và giữ nguyên database.
2. Hệ thống cho phép chu kỳ bảo trì đến sớm tối đa 5 phút so với mốc Terms.
3. Retry 6 giờ vì vậy không bị bỏ qua rồi phải chờ thành 12 giờ.
4. Đây chỉ là lịch thu thập; permission, campaign/project và commission decisions không đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.37.command`.

## Update 0.2.36 — Terms lỗi web tự thử lại

1. Mở `UPDATE-AFI-OS-0.2.36.command`; updater tự backup và giữ nguyên database.
2. Lỗi truy cập nguồn tạo `RETRY_REQUIRED` và hệ thống tự thử lại sau 6 giờ.
3. Inbox ghi **Terms sẽ tự thử lại**; mục này là cảnh báo và không cần người dùng xử lý.
4. Chỉ kết quả truy cập được nhưng không có câu policy rõ ràng mới yêu cầu nhập nguồn.

Rollback bằng `ROLLBACK-AFI-OS-0.2.36.command`.

## Update 0.2.35 — phân biệt đến hạn và lần rà thực tế

1. Mở `UPDATE-AFI-OS-0.2.35.command`; updater tự backup và giữ nguyên database.
2. **Terms đủ 24 giờ** là mốc chương trình bắt đầu cần rà lại.
3. **Lần rà Terms dự kiến** là chu kỳ bảo trì 6 giờ đầu tiên sau mốc đó.
4. Hai mốc chỉ để theo dõi; PPC permission, campaign/project và commission decisions không đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.35.command`.

## Update 0.2.34 — xem lịch rà Terms tiếp theo

1. Mở `UPDATE-AFI-OS-0.2.34.command`; updater tự backup và giữ nguyên database.
2. Vào Command Center, xem **Lần rà Terms còn mới** để biết số chương trình đã đến hạn.
3. Xem **Rà Terms tiếp theo** để biết mốc tự động gần nhất theo chu kỳ 24 giờ.
4. Đây chỉ là lịch theo dõi: PPC permission, campaign/project và commission decisions không đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.34.command`.

## Update 0.2.33 — tự ghép lại campaign khi program xuất hiện sau

1. Mở `UPDATE-AFI-OS-0.2.33.command`; updater tự backup và giữ nguyên database.
2. File Ads còn campaign chưa ghép sẽ tự được phân tích lại ở chu kỳ kế tiếp.
3. Khi program từ cột `program_domain` xuất hiện, hệ thống tạo mapping nhưng không nhân spend.
4. Thẻ **Google Ads tự nhập** hiện số file được thử lại vì chưa ghép.

Rollback bằng `ROLLBACK-AFI-OS-0.2.33.command`.

## Update 0.2.32 — tự phục hồi commission file từng lỗi/thiếu mapping

1. Mở `UPDATE-AFI-OS-0.2.32.command`; updater tự backup và giữ nguyên database.
2. File commission đã thành công vẫn không tạo giao dịch trùng.
3. File lỗi/thiếu mapping được thử lại; khi program phù hợp xuất hiện, file tự được nhập.
4. Thẻ **Commission tự nhập** hiện số file retry lỗi và retry thiếu mapping.

Rollback bằng `ROLLBACK-AFI-OS-0.2.32.command`.

## Update 0.2.31 — tự phục hồi file Google Ads từng lỗi

1. Mở `UPDATE-AFI-OS-0.2.31.command`; updater tự backup và giữ nguyên database.
2. File Ads đã nhập thành công vẫn được nhận diện bằng checksum và không tạo dữ liệu trùng.
3. File từng lỗi được tự đọc lại mỗi chu kỳ; khi Customer ID/context đã đủ, lỗi tự biến mất.
4. Xem thẻ **Google Ads tự nhập** để biết số file lỗi vừa được hệ thống thử lại.

Rollback bằng `ROLLBACK-AFI-OS-0.2.31.command`.

## Update 0.2.30 — cảnh báo Terms mở đúng lỗi và lịch sử

1. Mở `UPDATE-AFI-OS-0.2.30.command`; updater tự backup và giữ nguyên database.
2. Khi Inbox có **Cần nguồn Terms**, đọc ngay lỗi gần nhất và số URL nguồn đã thử.
3. Bấm **Xem lần rà** để mở đúng chương trình và xem lịch sử, evidence, commission facts.
4. Nếu cảnh báo chưa gắn program, hệ thống điền domain vào ô thu thập để nhập nguồn mới.

Rollback bằng `ROLLBACK-AFI-OS-0.2.30.command`.

## Update 0.2.29 — xem lịch sử rà Terms trên giao diện

1. Mở `UPDATE-AFI-OS-0.2.29.command`; updater tự backup và giữ nguyên database.
2. Vào Terms Evidence, chọn một chương trình trong danh sách hoặc ô nhập proposal.
3. Xem bảng **Lịch sử rà Terms tự động** để biết nguồn đã thử, lỗi và thời điểm gần nhất.
4. Nhãn `PPC KHÔNG ĐỔI` xác nhận lần automation đó không sửa permission hay loại campaign.

Rollback bằng `ROLLBACK-AFI-OS-0.2.29.command`.

## Update 0.2.28 — audit mọi lần thiếu nguồn Terms

1. Mở `UPDATE-AFI-OS-0.2.28.command`; updater tự backup và giữ nguyên database.
2. Mỗi lần live collector không lấy đủ nguồn sẽ ghi một audit event, kể cả kết quả trùng.
3. Audit lưu URL đã thử, URL ưu tiên từ evidence cũ, lỗi và thời điểm automation chạy.
4. Đây chỉ là truy vết: permission, campaign, project và Google Ads không bị thay đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.28.command`.

## Update 0.2.27 — Pictory fixture chỉ seed một lần

1. Mở `UPDATE-AFI-OS-0.2.27.command`; updater tự backup và giữ nguyên database.
2. Fixture cũ tiếp tục giữ hai claims 40% one-time và up to 50% recurring làm dữ liệu khởi tạo.
3. Các lần rà Pictory sau đó đọc web thật và URL đã lưu; lỗi web được ghi là lần thử lỗi/thiếu nguồn thật.
4. Pictory và campaign không bị loại; mọi PPC permission vẫn cần accepted evidence riêng.

Rollback bằng `ROLLBACK-AFI-OS-0.2.27.command`.

## Update 0.2.26 — rà lại đúng URL evidence đã lưu

1. Mở `UPDATE-AFI-OS-0.2.26.command`; updater tự backup và giữ nguyên database.
2. Collector tự ưu tiên URL evidence/fact chưa bị loại, sau đó mới thử đường dẫn chuẩn từ website.
3. Nếu recheck chỉ thấy commission nhưng mất các scope PPC đã accept, chương trình chuyển về cảnh báo chưa xác minh.
4. Đây vẫn là warning-only: permission, campaign, project và Google Ads không bị thay đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.26.command`.

## Update 0.2.25 — phân biệt đã rà và đã xác minh Terms

1. Mở `UPDATE-AFI-OS-0.2.25.command`; updater tự backup và giữ nguyên database.
2. Xem **Lần rà Terms còn mới** để biết automation có chạy gần đây hay không.
3. Xem **Terms đã xác minh** để biết bao nhiêu chương trình thật sự đạt evidence-backed `TERMS_OK`.
4. Số đã rà cao không tự mở PPC và không làm mất cảnh báo của chương trình chưa xác minh.

Rollback bằng `ROLLBACK-AFI-OS-0.2.25.command`.

## Update 0.2.24 — chọn đúng lần rà Terms mới nhất

1. Mở `UPDATE-AFI-OS-0.2.24.command`; updater tự backup và giữ nguyên database.
2. Hệ thống tự dùng thời điểm mới nhất giữa ngày nguồn và heartbeat recheck.
3. Runtime, lịch bảo trì, Inbox và Terms warning vì vậy không còn lệch nhau khi có nhiều research run.
4. Không cần nhập lại evidence; quyền PPC, campaign và project không bị thay đổi.

Rollback bằng `ROLLBACK-AFI-OS-0.2.24.command`.

## Update 0.2.23 — hạ trạng thái xanh khi nguồn Terms biến mất

1. Mở `UPDATE-AFI-OS-0.2.23.command`; updater tự backup và giữ nguyên database.
2. Nếu lần rà mới nhất không còn nguồn rõ ràng và mới hơn lần review evidence gần nhất, chương trình chuyển sang `WARNING_TERMS_UNVERIFIED`.
3. Đây chỉ là cảnh báo: permission, campaign và project không bị sửa, dừng hoặc loại.
4. Lần rà thành công sau đó tự dùng lại accepted evidence; người vận hành cũng có thể review evidence sau cảnh báo để xác nhận chủ động.

Rollback bằng `ROLLBACK-AFI-OS-0.2.23.command`.

## Update 0.2.22 — cảnh báo khi official Terms mới đổi

1. Mở `UPDATE-AFI-OS-0.2.22.command`; updater tự backup và giữ nguyên database.
2. Nếu nguồn chính thức mới trái với evidence đã chấp nhận, chương trình hiện `WARNING_TERMS_CONFLICT` và proposal xuất hiện trong Operations Inbox.
3. Kiểm tra URL + excerpt. Chọn **Xác nhận** nếu nguồn mới đúng hoặc **Loại** nếu extractor nhận sai.
4. Trong lúc chờ xét, canonical permission không đổi; campaign vẫn chạy và không bị loại.

Rollback bằng `ROLLBACK-AFI-OS-0.2.22.command`.

## Update 0.2.21 — xem kết quả tự ghép trên Command Center

1. Mở `UPDATE-AFI-OS-0.2.21.command`; updater tự backup và giữ nguyên database.
2. Trong thẻ AFI-OS 24/7, xem mục **Tự ghép campaign**.
3. Số **mới** là campaign vừa được ghép trong chu kỳ gần nhất; dòng nhỏ hiện số chưa ghép và mapping cũ đã giữ.
4. Campaign chưa ghép vẫn ở Operations Inbox; đây là trạng thái cảnh báo, không dừng hoặc loại campaign.

Rollback bằng `ROLLBACK-AFI-OS-0.2.21.command`.

## Update 0.2.20 — rà lại campaign cũ chưa ghép

1. Mở `UPDATE-AFI-OS-0.2.20.command`; updater tự backup và giữ nguyên database.
2. Mỗi chu kỳ bảo trì rà tất cả campaign chưa ghép, không phụ thuộc file CSV có đổi hay không.
3. Chỉ tên chứa đúng một merchant domain duy nhất mới được tự ghép; chuỗi con và domain nhiều chương trình vẫn để cảnh báo.
4. Mapping đã có luôn được giữ nguyên. Luồng này không đổi quyền PPC, trạng thái campaign hay cài đặt Google Ads.

Rollback bằng `ROLLBACK-AFI-OS-0.2.20.command`.

## Update 0.2.19 — tự ghép campaign theo merchant domain

1. Mở `UPDATE-AFI-OS-0.2.19.command`; updater tự backup và giữ nguyên database.
2. CSV/API mới được nhập như trước. Nếu tên campaign chứa đúng một domain đã biết, AFI-OS tự ghép chương trình và hiện số **Tự map theo domain**.
3. Nếu domain chỉ là chuỗi con, không xuất hiện, hoặc merchant có nhiều chương trình, campaign vẫn ở mục chưa ghép trong Operations Inbox.
4. Mapping thủ công luôn được ưu tiên; tự ghép không thay đổi PPC permission, không loại campaign và không tác động Google Ads.

Rollback bằng `ROLLBACK-AFI-OS-0.2.19.command`.

## Update 0.2.18 — retry và cảnh báo Google Ads đúng người

1. Mở `UPDATE-AFI-OS-0.2.18.command`; updater tự backup và giữ nguyên database.
2. Lỗi mạng, 429 hoặc 5xx được thử tối đa ba lần. Nếu vẫn lỗi, Inbox chỉ hiện cảnh báo và hệ thống tự thử lại sau sáu giờ.
3. Chỉ khi Inbox hiện **Cần đăng nhập lại Google Ads**, mở `SETUP-GOOGLE-ADS-READ-ONLY.command` và cấp lại quyền.
4. Khi API lỗi, CSV fallback, campaign, spend cũ, mapping và Terms warning đều được giữ nguyên.

SyncRun chỉ lưu nhóm lỗi và thông báo đã làm sạch; không lưu response body, header hay credential. Rollback bằng `ROLLBACK-AFI-OS-0.2.18.command`.

## Update 0.2.17 — đồng bộ Google Ads tự động chỉ đọc

1. Mở `UPDATE-AFI-OS-0.2.17.command`; updater tự backup và giữ nguyên database.
2. Nếu credential chưa đủ, không cần làm gì: mỗi chu kỳ chỉ ghi `SKIPPED_CREDENTIALS` trong báo cáo bảo trì và CSV vẫn hoạt động.
3. Khi đã chạy xong `SETUP-GOOGLE-ADS-READ-ONLY.command`, bảo trì 6 giờ tự đọc bảy ngày gần nhất đến hôm qua.
4. Command Center hiện số dòng API, số dòng thay đổi và số khác biệt trước cập nhật. API mới sẽ thay thế yêu cầu xuất lại CSV cũ.

Connector dùng endpoint v25 `googleAds:searchStream` và một GAQL `SELECT` cố định; không có phương thức mutate. Dữ liệu API được đối chiếu với cùng Customer ID/campaign/ngày và cập nhật dòng Google Ads canonical, không cộng đôi với CSV. Rollback bằng `ROLLBACK-AFI-OS-0.2.17.command`.

## Update 0.2.16 — thiết lập OAuth Google Ads an toàn

1. Mở `UPDATE-AFI-OS-0.2.16.command`; updater tự backup và giữ nguyên database.
2. Chỉ khi đã có hai thứ này: OAuth Desktop `credentials.json` và Google Ads Developer Token, mở `SETUP-GOOGLE-ADS-READ-ONLY.command`.
3. Kéo file JSON vào cửa sổ, nhập Developer Token ở ô ẩn, rồi đăng nhập Google trong tab được mở.
4. Khi màn hình báo hoàn tất, đóng Terminal. Command Center sẽ chuyển readiness sang `READY` khi đủ bốn credential.

Không dán token vào chat. Credential được lưu trong macOS Keychain; database/UI/log không giữ giá trị. Scope Google Ads của Google là scope rộng, nhưng AFI-OS khóa code ở `READ_ONLY_REPORTING`, chưa có lệnh thay đổi campaign/bid/budget/status. CSV tự động vẫn chạy nếu setup chưa đủ. Rollback bằng `ROLLBACK-AFI-OS-0.2.16.command`.

## Update 0.2.15 — kiểm tra sẵn sàng Google Ads API chỉ-đọc

1. Mở `UPDATE-AFI-OS-0.2.15.command`; chưa cần nhập token vào AFI-OS.
2. Command Center hiện tài khoản Ads đã nhận và số credential còn thiếu.
3. Credential sau này được lưu trong macOS Keychain; API/UI chỉ thấy trạng thái có/thiếu.
4. Trong khi chưa kết nối, Google Ads CSV trong Downloads vẫn tự nhập mỗi 6 giờ.

Không có lệnh mutate campaign/bid/budget/status trong preflight. Rollback bằng `ROLLBACK-AFI-OS-0.2.15.command`.

## Update 0.2.14 — nhịp kiểm tra lại Terms chính xác

1. Mở `UPDATE-AFI-OS-0.2.14.command`; không cần nhập lại nguồn hoặc evidence.
2. AFI-OS giữ nguyên ngày bằng chứng gốc và chỉ cập nhật mốc automation đã kiểm tra lại.
3. Nếu kết quả không đổi, maintenance chờ đủ 24 giờ mới thử lại; dữ liệu không bị nhân đôi.

Không có permission nào được tự mở và campaign vẫn chỉ nhận cảnh báo. Rollback bằng `ROLLBACK-AFI-OS-0.2.14.command`.

## Update 0.2.13 — tự nhập báo cáo commission an toàn

1. Mở `UPDATE-AFI-OS-0.2.13.command`; không cần xuất file ngay.
2. Mỗi 6 giờ, AFI-OS chỉ tìm CSV có tên chứa `commission`, `commissions` hoặc `hoa hồng` trong Downloads.
3. Đặt tên có merchant, ví dụ `Fliki commissions.csv`, hoặc để file có cột `program_domain`/`merchant`. Cần tối thiểu ID giao dịch và số hoa hồng.
4. File hợp lệ được nhập idempotent; Pending → Approved cập nhật cùng giao dịch. File mơ hồ/lỗi/conflict vào Operations Inbox và chưa được ghi.

Luồng này không sửa Terms/PPC, không dừng campaign và không ghi đè số tiền xung đột. Rollback bằng `ROLLBACK-AFI-OS-0.2.13.command`.

## Update 0.2.12 — cảnh báo khi dữ liệu Google Ads đã cũ

1. Mở `UPDATE-AFI-OS-0.2.12.command`.
2. Thẻ **Google Ads tự nhập** hiện số dòng và ngày dữ liệu mới nhất trong CSV đã xác nhận.
3. Dữ liệu đến hôm qua vẫn được xem là mới. Chỉ khi cũ hơn, Operations Inbox mới tạo một việc cần anh xử lý.
4. Khi được yêu cầu: mở **Google Ads → Chiến dịch**, chọn báo cáo **theo ngày**, thêm cột **Campaign ID**, rồi tải CSV vào **Downloads**. AFI-OS tự nhận ở chu kỳ kế tiếp.

Cảnh báo dữ liệu cũ không dừng, không loại và không thay đổi campaign. Rollback bằng `ROLLBACK-AFI-OS-0.2.12.command`.

## Update 0.2.11 — trạng thái Ads chính xác, không chạy maintenance đôi

1. Mở `UPDATE-AFI-OS-0.2.11.command`.
2. Updater tự tạm dừng và nạp lại hai dịch vụ 24/7.
3. Thẻ Google Ads tự nhập vẫn hiện 9 dòng khi file không đổi và trạng thái là `SUCCESS`.
4. Maintenance chạy một lần khi nạp dịch vụ, sau đó mỗi 6 giờ.

Rollback bằng `ROLLBACK-AFI-OS-0.2.11.command`.

## Update 0.2.10 — tự nhập báo cáo Google Ads trong Downloads

1. Giải nén `AFI-OS-update-0.2.10.zip` và mở `UPDATE-AFI-OS-0.2.10.command`.
2. Không cần chọn lại file cũ. Mỗi 6 giờ AFI-OS chọn bản `Báo cáo chiến dịch*.csv` mới nhất trong Downloads.
3. File phải có Campaign ID, Campaign, Date và Cost; file có lỗi không được nhập.
4. Xem thẻ **Google Ads tự nhập** trên Command Center. File lỗi hoặc campaign chưa ghép xuất hiện trong Operations Inbox.

Import này chỉ đọc báo cáo và cập nhật sổ local. Nó không bật/tắt campaign, không đổi ngân sách/bid và không sửa PPC permission. Rollback bằng `ROLLBACK-AFI-OS-0.2.10.command`.

## Update 0.2.9 — xem 24/7 ngay trên Command Center

1. Giải nén `AFI-OS-update-0.2.9.zip` và mở `UPDATE-AFI-OS-0.2.9.command`.
2. Updater tự tạm dừng hai dịch vụ 24/7, backup, cập nhật rồi khởi động lại chúng.
3. Trên Command Center, thẻ **AFI-OS 24/7** phải hiện “24/7 đang hoạt động”.
4. Thẻ cho biết lần bảo trì, backup và số Terms còn mới; không cần mở Terminal.

Rollback: mở `ROLLBACK-AFI-OS-0.2.9.command`, gõ `ROLLBACK`. Hai dịch vụ được tạm dừng và khôi phục cùng phiên bản 0.2.8.

## Update 0.2.8 và bật chạy 24/7

1. Giải nén `AFI-OS-update-0.2.8.zip` và mở `UPDATE-AFI-OS-0.2.8.command`.
2. Sau khi AFI-OS mở lại, mở `ENABLE-AFI-OS-24-7.command` đúng một lần.
3. Từ đó server tự chạy lại sau đăng nhập/restart; bảo trì chạy ngay khi bật và sau mỗi 6 giờ.
4. Mở `STATUS-AFI-OS-24-7.command` để xem hai dịch vụ đã được nạp.

Bảo trì tự backup tối đa một lần mỗi 24 giờ, chỉ thu thập lại Terms đã quá 24 giờ, tiếp tục khi một domain lỗi và không tự duyệt evidence/commission. Tắt bằng `DISABLE-AFI-OS-24-7.command`; dữ liệu và backup không bị xóa.

Rollback: mở `ROLLBACK-AFI-OS-0.2.8.command`, gõ `ROLLBACK`. Updater sẽ tạm dừng dịch vụ trước khi khôi phục.

## Update 0.2.7 một lần bấm

1. Giải nén `AFI-OS-update-0.2.7.zip` và mở `UPDATE-AFI-OS-0.2.7.command`.
2. Khi AFI-OS mở lại, xem **Operations Inbox** ngay tại Command Center.
3. Chỉ xử lý dòng có nút hành động; nút sẽ mở đúng Terms, Commission, Finance hoặc Campaign.
4. Dòng `CAMPAIGN_TERMS_WARNING` chỉ là cảnh báo; campaign vẫn được giữ và không bị dừng.

Rollback: mở `ROLLBACK-AFI-OS-0.2.7.command` trong `~/Downloads/AFI-OS`, gõ `ROLLBACK`.

## Update 0.2.6 một lần bấm

1. Giải nén `AFI-OS-update-0.2.6.zip`.
2. Mở `UPDATE-AFI-OS-0.2.6.command` và chờ AFI-OS chạy lại.
3. Vào **Terms Evidence**, chọn chương trình để xem commission facts.
4. Mở nguồn rồi bấm **Xác nhận** hoặc **Loại**. Thao tác này không thay đổi PPC.

Rollback: mở `ROLLBACK-AFI-OS-0.2.6.command` trong `~/Downloads/AFI-OS`, gõ `ROLLBACK`.

## Update 0.2.5 một lần bấm

1. Giải nén `AFI-OS-update-0.2.5.zip`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.5.command` → **Mở**.
3. Chờ Terminal báo thành công và AFI-OS mở lại.
4. Trong **Terms Evidence**, nhập domain rồi bấm **Thu thập proposal**.

Hệ thống tự thử tối đa tám trang HTTPS chính thức cùng domain. Kết quả chỉ là proposal; anh chỉ cần xem khi có evidence mới hoặc conflict. Nếu hệ thống báo `MANUAL_INPUT_REQUIRED`, dự án vẫn được giữ và cảnh báo; không cần loại dự án.

Rollback khi cần: mở `ROLLBACK-AFI-OS-0.2.5.command` trong `~/Downloads/AFI-OS`, gõ `ROLLBACK`. Hệ thống tạo emergency backup trước khi khôi phục bản 0.2.4.

## Update 0.2.4 một lần bấm

1. Giải nén `AFI-OS-update-0.2.4.zip`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.4.command` → **Mở**.
3. Updater tự dừng app, checkpoint dữ liệu, backup, migrate, kiểm tra và mở lại AFI-OS.
4. Mở **Finance & Reconciliation** để xem VND, tỷ lệ dữ liệu đã chuẩn hóa và hàng đợi đối soát.

Khi có giao dịch ngoại tệ: nhập tỷ giá cùng URL nguồn. Tỷ giá được lưu ở `PROPOSED` và chưa ảnh hưởng số tiền. Chỉ bấm **Chấp nhận** khi nguồn đúng và confidence từ `0,8`; hệ thống sẽ chuẩn hóa lại dữ liệu. Không cần tỷ giá cho dữ liệu VND.

Rollback khi cần: mở `ROLLBACK-AFI-OS-0.2.4.command` trong `~/Downloads/AFI-OS`, gõ `ROLLBACK`. Hệ thống tạo emergency backup trước khi khôi phục bản 0.2.3.

## Update 0.2.3 một lần bấm

1. Giải nén `AFI-OS-update-0.2.3.zip`.
2. Nhấp chuột phải `UPDATE-AFI-OS-0.2.3.command` → **Mở**.
3. Chờ Terminal báo cập nhật thành công và AFI-OS mở lại.
4. Trong Risk & Exposure, chọn nguyên file báo cáo Google Ads vừa tải xuống; không cần sửa CSV.

Rollback khi cần: mở `ROLLBACK-AFI-OS-0.2.3.command` trong `~/Downloads/AFI-OS`,
gõ `ROLLBACK`. Hệ thống tạo emergency backup trước khi khôi phục.

## Khởi động lần đầu

```bash
./bootstrap.sh
make seed
./run.sh
```

## Chạy lại

```bash
./run.sh
```

## Kiểm tra sức khỏe

```bash
curl http://127.0.0.1:8765/api/health
```

## Migration

```bash
.venv/bin/alembic upgrade head
```

## Update 0.2.2 một lần bấm

1. Giữ nguyên bản chính tại `~/Downloads/AFI-OS`; không chép payload vào đó.
2. Mở thư mục update và nhấp chuột phải `UPDATE-AFI-OS-0.2.2.command` → **Mở**.
3. Updater tự dừng app, checkpoint WAL, backup database + file bị thay, migrate và kiểm tra dữ liệu cũ.
4. Thành công khi Terminal hiện `Cập nhật AFI-OS 0.2.2 thành công` và trình duyệt mở lại AFI-OS.

Rollback khi cần: trong `~/Downloads/AFI-OS`, mở `ROLLBACK-AFI-OS-0.2.2.command`, gõ `ROLLBACK`. Script tạo emergency backup của trạng thái 0.2.2 trước khi khôi phục.

## Nhập Google Ads CSV

1. Trong Google Ads, xuất báo cáo campaign theo ngày với tối thiểu Campaign ID, Campaign, Date và Cost; nên thêm Customer ID, status, currency, impressions, clicks và conversions.
2. Mở **Risk & Exposure** → chọn file → chọn chương trình mặc định nếu file không có cột Program domain.
3. Bấm **Xem trước**, kiểm tra số dòng/spend/lỗi, rồi mới bấm **Nhập dữ liệu**.
4. Nhập lại cùng campaign/ngày/source không tạo spend trùng; số thay đổi được cập nhật.
5. Terms đỏ/vàng không làm campaign biến mất. Nút **Tôi đã biết** chỉ lưu acknowledgement, không thay đổi permission.

## Test

```bash
make test
make lint
```

## Reset dữ liệu demo

```bash
rm -f data/afi_os.db
.venv/bin/alembic upgrade head
make seed
```

## Sự cố

### API không lên

- Kiểm tra port 8765: `lsof -i :8765`.
- Kiểm tra `.venv` đã được tạo.
- Chạy `make test` để tách lỗi code và lỗi môi trường.

### Extension không gửi được

- Xác nhận AFI-OS đang chạy tại `127.0.0.1:8765`.
- Reload extension sau khi đổi file.
- Kiểm tra extension có `host_permissions` cho localhost.

### Database lỗi

- Không xóa file trước khi sao lưu.
- Copy `data/afi_os.db` sang thư mục backup.
- Chạy migration và test trên bản copy.
## Update 0.2.99 — Google Ads Keychain Terminal hotfix

1. Run `UPDATE-AFI-OS-0.2.99.command`; the updater creates and verifies a database/code
   backup before changing the live installation.
2. Open `SETUP-GOOGLE-ADS-READ-ONLY.command` only when credentials must be replaced.
3. Enter the manager ID and Developer Token only in Terminal; secret input stays hidden.
4. Successful setup prints that five credentials were stored and queues an immediate
   read-only sync. Runtime must show `google_ads_api_status=READY` and sync `SUCCESS`.
5. Roll back with `ROLLBACK-AFI-OS-0.2.99.command`; the updater creates an emergency
   backup before restoring 0.2.98.
