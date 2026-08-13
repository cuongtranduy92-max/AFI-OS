# Dot1.1 Appraisal Contract

`POST /api/appraise` là ranh giới ổn định giữa lớp thu thập của AFI-OS, engine chấm
điểm và giao diện Bước 1.

## Request

```json
{"domain": "example.com"}
```

Domain được chuẩn hóa và kiểm tra như hostname. API tự chạy các collector đã kết
nối. Không nhận traffic, ngày kiểm tra hoặc URL nguồn do người dùng tự điền.

## Quy tắc dữ liệu

1. Không có nguồn thì trả `null`; traffic dùng thêm `source_status: "pending"`.
2. Không biến dữ liệu chưa thu thập thành `0`.
3. Permission PPC chỉ dùng evidence đã được chấp nhận; thiếu evidence trả `null`
   và cảnh báo, không loại dự án hay thay đổi campaign.
4. Commission chỉ dùng fact đã chấp nhận, tách khỏi permission PPC.
   Fact được người vận hành chấp nhận nhưng ghi `up to` vẫn được hiển thị kèm warning;
   nó không được dùng vào payback cho đến khi có mức hoa hồng bảo đảm.
5. Endpoint không thực hiện Google Ads write.

## Mapping database hiện tại

| Contract | Nguồn hiện tại |
|---|---|
| `domain` | `projects.domain` |
| `niche` | `projects.category` |
| `affiliate_link` | `projects.program_id → programs.signup_url` |
| `traffic.*` | `metric_snapshots` với key traffic và provenance |
| `keyword.*` | `metric_snapshots` do Google Ads Keyword Planner REST tạo |
| `advertisers.*` | `ad_observations`, `advertisers`, `projects` |
| `commission.*` | `commission_facts` đã ACCEPTED và `offers` |
| `payment.*` | snapshot payment, `offers.cookie_days`, affiliate network |
| `terms.*` | `terms_evidence` đã ACCEPTED và permission resolver |
| `payback.*` | trường dẫn xuất của Step 1 từ snapshot có nguồn |
| `score.*` | điểm nối engine Dot1.1; hiện trả `null` và flag `pending` |

Không thêm các cột appraisal chi tiết vào `projects`. Bảng `projects` chỉ giữ
identity và workflow; số liệu biến động phải tiếp tục vào `metric_snapshots` để
có source, ngày quan sát, confidence và lịch sử.

## Điểm nối engine

`afi_os.services.appraisal.build_appraisal_contract()` là adapter duy nhất. Engine
chấm điểm của Claude có thể thay phần tạo `score` hoặc bổ sung lớp engine trước
adapter, nhưng không được đổi shape JSON, không tự điền số thiếu và không mở PPC
permission.

## Trạng thái Page 2 và Google Ads

Page 2 hiện có queue PREP/LIVE, chức năng lưu snapshot quyết định Bước 1 và mở lại
nguồn. Bộ sinh asset 15 headline, 4 description, 4 sitelink, 4 callout chưa được
triển khai trong app mới; bản Legacy chỉ là tham chiếu, không phải generator production.

Google Ads đang dùng client REST bằng thư viện chuẩn tại
`services/google_ads_api.py`, không dùng Google Ads Python SDK. Campaign metrics gọi
`googleAds:searchStream`; keyword volume/bid gọi `generateKeywordIdeas`. OAuth và
Developer Token được đọc từ macOS Keychain, luồng chỉ đọc và không có mutate call.
