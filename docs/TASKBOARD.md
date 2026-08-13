# TASKBOARD

## 0.2.108 — Camp Doctor + Việt hóa

- [x] Add deterministic diagnoses and persistent diagnosis/change-event history.
- [x] Add all requested Google Ads detail reports without any write/mutate call.
- [x] Show Page 3 campaign list, benchmark, ordered actions and detail tables.
- [x] Keep real ref missing as null and protect new/low-data campaigns from early cuts.
- [x] Add Vietnamese fields in a rollback-safe migration with old data preserved.
- [x] Translate inside the same Claude call and verify only the original quote.
- [x] Force the exact missing-PPC warning and keep PPC summary proposal-only.
- [x] Show Vietnamese first plus “Xem bản gốc”; preserve Step 2 English ad assets.
- [x] Add regression, migration, package, updater and rollback verification.

## 0.2.107 — Claude Terms extraction

- [x] Store the Anthropic key only in macOS Keychain.
- [x] Crawl bounded source pages and call Claude with deterministic settings.
- [x] Reject fabricated/short quotes and keep unknown values null.
- [x] Persist commission, package, payment, cookie and Terms as proposals.
- [x] Require human accept/reject before applying facts or recalculating payback.
- [x] Cache unchanged source content and exclude `up to` commission from payback.
- [x] Preserve warning-only Projects, campaigns and Google Ads read-only behavior.
- [x] Add migration, regression, package, updater and rollback verification.

## 0.2.106 — Tài nguyên

- [x] Add email, resource, nurture-log and account-assignment schema with rollback.
- [x] Add deterministic SOAK/DECLARED/INTERACTING/CHÍN and dirty-email rules.
- [x] Add alerts for capacity, PayPal concentration, cards, owners and bad lineage.
- [x] Add secret-free CRUD, overview and daily nurture-check endpoints.
- [x] Add the complete tab 5 interface and Step 2 eligible-account selector.
- [x] Bind one account to one current Project without writing Google Ads.
- [x] Add regression, migration, package, updater and rollback verification.

## 0.2.105 — Apify traffic automation

- [x] Add APIFY to the Keychain-only traffic seam.
- [x] Parse latest monthly visits and top-five country shares with source lineage.
- [x] Cache both metrics for 45 days and skip the paid call on a cache hit.
- [x] Batch up to 50 domains in one actor run and preserve per-domain NO_DATA.
- [x] Show sourced traffic and countries in the Step 1 appraisal contract/UI.
- [x] Keep Terms warning-only, commission operator-controlled and Google Ads read-only.

## 0.2.104 — Dot3 Step 2 content builder

- [x] Add the one-plan-per-Project migration and DRAFT/DEPLOYED lifecycle.
- [x] Gate generation and deploy on the current stored Step 1 `score.pass`.
- [x] Generate exact 15/4/4/4 English content without an LLM or network call.
- [x] Render editable lines with row-level errors and a re-lint action.
- [x] Block deploy on errors, audit a clean deploy and expose the Step 3 handoff.
- [x] Keep Google Ads write disabled and preserve Terms/commission decisions.

## 0.2.103 — Dot2 scoring and sheet payback

- [x] Apply the fixed 26,000 VND/USD rate only to modeled payback.
- [x] Apply `3× low bid` and `0.5× high bid` scenarios.
- [x] Return real score total/pass/flags from `/api/appraise`.
- [x] Keep PPC prohibition warning-only.
- [x] Add regression, updater and rollback coverage.

## 0.2.102 — Commission truth hotfix

- [x] Show accepted maximum commission without treating it as guaranteed economics.
- [x] Keep maximum-rate facts out of payback and expose a warning flag.
- [x] Map package tuples to sourced offer prices.
- [x] Add regression coverage and release independently from 0.2.101.

## 0.2.101 — Dot1.1

- [x] Reject unsafe backup sources and verify every completed backup with SHA-256.
- [x] Surface backup failure explicitly in the command and Operations Inbox.
- [x] Remove the obsolete Legacy `afi-data.json` request and navigation entry.
- [x] Add the stable `POST /api/appraise` shell with truthful pending-source states.
- [x] Map all ten Step 1 groups without inventing traffic, commission, Terms or score.
- [x] Add one-domain and batch appraisal UI with ten cards and guarded Step 2 save.
- [x] Document the database mapping, Claude engine seam and Page 2/Page 3 status.
- [x] Add application, UI, backup and updater regression coverage.

## 0.2.100 — One-domain automatic Project Check

- [x] Replace manual traffic/date/source entry with one domain input.
- [x] Collect monthly website traffic from Similarweb or Semrush after one Keychain setup.
- [x] Collect global English search volume and CPC from Google Ads Keyword Planner read-only.
- [x] Return an explicit connection/source requirement for every missing Step 1 data group.
- [x] Store source, period, confidence and audit without storing API secrets.
- [x] Keep Terms warning-only, commission operator-controlled and Google Ads write disabled.
- [x] Add regression coverage for blank prevention, API parsers, deduplication and no writes.

## 0.2.99 — Source-backed traffic fallback

- [x] Add manual monthly website-traffic entry with URL and observation date.
- [x] Populate the same form from a minimal CSV without accepting missing provenance.
- [x] Store versioned snapshots, deduplicate exact imports and audit no Google Ads write.
- [x] Expire traffic after 45 days and prevent stale numbers from passing Step 1.
- [x] Keep Similarweb/Semrush optional until automated bulk collection is justified.
- [x] Harden updater LaunchAgent ownership checks and Keychain Terminal setup.

## 0.2.98 — Project Check Step 1

- [x] Aggregate all requested Step 1 fields into one source-aware API response.
- [x] Show a real number, an explicit missing state, or the exact source/API needed.
- [x] Calculate payback only from accepted commission, sourced plan price and CPC.
- [x] Keep PPC restrictions warning-only and keep every Project in the system.
- [x] Save the decision snapshot and show prepared Projects in the Step 2 queue.
- [x] Add regression coverage for formula, missing APIs, transition audit and no writes.

## 0.2.97 — Source observation date hotfix

- [x] Preserve snapshot `checked_at` as relationship `observed_at`.
- [x] Keep ad activity `first_seen/last_seen` semantically separate.
- [x] Show sourced dates on advertiser and related-project branches.
- [x] Re-run application, updater, checksum and live postchecks.

## 0.2.96 — Project network journey

- [x] Start the product at `Tìm dự án` and order the first three navigation steps.
- [x] Expand Project → advertisers → each advertiser's Projects automatically.
- [x] Recenter and continue expansion when a related Project is selected.
- [x] Preserve relationship URL/date/count lineage and truthful missing states.
- [x] Add API, UI, checksum installer and rollback regression coverage.

## 0.2.95 — Project trace UX

- [x] Separate new-project tracing from saved-project filtering.
- [x] Normalize a domain before starting a trace.
- [x] Run idempotent intake and source research from one explicit action.
- [x] Show research source count/status without opening PPC permission.
- [x] Keep Portfolio filters dedicated to existing records.

## 0.2.94 — Domain intake UX

- [x] Distinguish searching an existing Project from adding a new domain.
- [x] Retain a valid domain immediately with truthful unknown defaults.
- [x] Make intake idempotent and audit no permission/campaign mutation.
- [x] Start source research after intake while keeping every conclusion proposed.
- [x] Add API/UI regression and safe updater/rollback coverage.

## 0.2.93 — Maintenance proposal safety

- [x] Keep new non-brand PPC evidence in the operator review queue.
- [x] Restore the Snov proposal rejected by repair v1 without accepting it.
- [x] Add regression coverage for maintenance re-runs and operator-safe restoration.

## 0.2.92 — Radar missing-state consistency

- [x] Replace ambiguous `Chưa có` values in Project Radar.
- [x] Preserve the 18-advertiser Snov snapshot and partial 30-day state.
- [x] Ship with checksum, updater/rollback tests, backup, and live postcheck.

## 0.2.91 — Truthful Snov intelligence

- [x] Reproduce Snov mismatch against the operator-visible source page.
- [x] Separate never-collected advertiser data from a verified zero.
- [x] Keep active-30-day metrics unknown without complete last-seen coverage.
- [x] Add sourced, audited, idempotent batch advertiser snapshot import.
- [x] Deduplicate advertiser identities with stable external advertiser keys.
- [x] Correct conditional PPC brand-bidding scope without opening permission.
- [x] Treat distinct commission products as a tiered schedule, not a conflict.
- [x] Add semantic repair for prior automated proposals; preserve operator decisions.
- [x] Preserve every project/campaign and keep Google Ads read-only.

## DONE — 0.2.90 Program ↔ Project sync

- [x] Chẩn đoán Snov có Program nhưng thiếu Project nên bộ lọc trả 0.
- [x] Tự tạo Project ở cả API tạo Program và Terms discovery.
- [x] Thêm maintenance self-heal cho dữ liệu cũ bị lệch.
- [x] Giữ nguyên workflow người vận hành và khóa Google Ads write/PPC mutations.
- [x] Regression cho filter, Terms discovery, link bảo toàn workflow và idempotency.

## DONE — 0.2.89 Command Center UI hotfix

- [x] Sửa lỗi `job is not defined` trong Operations Inbox.
- [x] Giữ target row của automation queue ở đúng component.
- [x] Thêm regression test ngăn tham chiếu biến sai quay lại.
- [x] Thêm hướng dẫn sáu bước ngay trên màn hình đầu tiên.

## DONE — 0.2.88 Wake-safe 24/7

- [x] Phát hiện chu kỳ maintenance bị mất khi máy ngủ.
- [x] Chuyển sang lịch 00/30 có khả năng chạy bù sau wake.
- [x] Kiểm thử plist round-trip và regression runtime/maintenance.

## DONE — 0.2.87 Exception Queue

- [x] Dead-letter automation xuất hiện trong Operations Inbox.
- [x] Operations mở đúng job cần xử lý.
- [x] Retry-wait không tạo operator action; campaign và permissions giữ nguyên.

## DONE — 0.2.86 Durable Automation Queue

- [x] Lưu job bền vững với dedupe, priority, payload/result và provenance.
- [x] Claim nguyên tử, lease ownership và thu hồi worker hết hạn.
- [x] Retry tăng dần có giới hạn, dead-letter và manual retry có audit.
- [x] Redact credential/token/secret khỏi payload, result và lỗi hiển thị.
- [x] Đưa Terms research đến hạn qua queue mà không thay đổi permission.
- [x] Hiện trạng thái worker trên Command Center; đóng trình duyệt không mất việc.
- [x] Migration round trip, concurrency regression, full suite và browser QA.

## DONE — 0.2.85 Project Portfolio & Truth Drawer

- [x] Backfill mọi Program hiện có thành Project mà không đổi sự thật Program.
- [x] Thêm workflow dự án và trạng thái đăng ký bị chặn nhưng luôn giữ dự án.
- [x] Hợp nhất Terms, commission, advertiser, campaign, CTR và cost trong Portfolio.
- [x] Thêm metric envelope, versioned snapshot và `WHY THIS NUMBER?` lineage drawer.
- [x] Hiện missing data là `UNKNOWN`, không giả thành số 0 hoặc điểm thấp.
- [x] Cảnh báo CTR dưới 40% mà không sửa/dừng campaign.
- [x] Audit workflow và chứng minh không đổi PPC, Program hoặc Google Ads.
- [x] Migration/update/rollback/checksum/full regression và browser QA.

## NEXT — Product completion sequence

- [x] Queue worker persistent có dedupe/lease/retry/dead-letter; Terms đã nối vào queue.
- [ ] Discovery producer: domain → advertiser → dự án khác trên queue đã có.
- [ ] Advertiser Explorer: alias/identity, project breadth, activity và edge provenance.
- [ ] Commercial facts: fee/cookie/payout/cap/tier và conflict review tách khỏi PPC.
- [ ] Project scoring: range, safe CPC và payback days với mọi input có nguồn.
- [ ] Google Ads asset pack: 15 headline, 4 description, 4 sitelink ref, 4 callout.
- [ ] Optimization Cockpit: CTR target 40%, search terms, keyword demand quốc tế tiếng Anh.
- [ ] Revenue/Payout: ref, commission state, withdrawable, withdrawn và actual payback.
- [ ] Gmail/project workspace: tự nhận, note, tóm tắt và draft; không tự gửi.

## DONE — 0.2.84 Operations Capture Target Focus

- [x] Giữ capture item type và entity ID trên action của Operations Inbox.
- [x] Mở đúng snapshot cũ nhất, cuộn, highlight và focus trường còn thiếu.
- [x] Fallback an toàn khi target đã được xử lý hoặc queue vừa trống.
- [x] Giữ nguyên action Program/Finance/Exposure và không tạo POST ngoài ý muốn.
- [x] Giữ Google Ads read-only, PPC warning-only và không quyết định commission.

## DONE — 0.2.83 Raw Ad Capture Review Queue

- [x] Đưa snapshot thiếu advertiser/domain vào hàng đợi oldest-first.
- [x] Chỉ tạo advertiser/project/observation sau khi người vận hành chấp nhận.
- [x] Cho phép loại snapshot nhưng vẫn giữ raw evidence và audit trail.
- [x] Gộp toàn bộ capture chờ duyệt thành một Operations Inbox exception.
- [x] Cho web capture và Chrome helper lưu raw evidence thiếu advertiser/domain để duyệt sau.
- [x] Cho xem đầy đủ evidence, khóa toàn hàng khi gửi và yêu cầu lý do loại do người vận hành nhập.
- [x] Giữ Google Ads read-only, PPC warning-only và không loại campaign/project.

## DONE — 0.2.82 Intraday Google Ads Snapshot Freshness

- [x] Phân biệt thời điểm maintenance xác nhận file với thời điểm file nguồn được xuất.
- [x] Cảnh báo snapshot cùng ngày khi file nguồn đã quá 6 giờ.
- [x] API đọc được dữ liệu của hôm nay tự triệt tiêu cảnh báo CSV trong ngày.
- [x] Hiện thời điểm file nguồn và mốc làm mới kế tiếp trên Command Center.
- [x] Giữ Google Ads read-only; cảnh báo không loại, sửa hoặc dừng campaign.

## DONE — 0.2.81 Safe OAuth Desktop JSON Auto-detection

- [x] Tự tìm duy nhất OAuth Desktop JSON hợp lệ ở top-level Downloads.
- [x] Bỏ qua invalid/web client/oversized/symlink/non-JSON mà không lộ secret.
- [x] Sắp xếp deterministic; nhiều file hợp lệ thì bắt buộc chọn, không đoán.
- [x] Giữ explicit path cho CLI và Keychain commit sau OAuth + SELECT-only preflight.
- [x] Giữ CSV fallback, PPC evidence-gated và project/campaign warning-only.

## DONE — 0.2.80 Guard Every External UI Link

- [x] Dùng một HTTP(S) guard cho signup, Terms, commission, research, capture và FX links.
- [x] Render URL legacy/malformed thành escaped text, không tạo anchor và không throw hostname parser.
- [x] Khóa regression: toàn bộ `app.js` chỉ còn một dynamic anchor constructor.
- [x] Giữ link HTTP(S) hợp lệ, không migration hoặc database rewrite.
- [x] Giữ PPC evidence-gated, commission riêng và project/campaign warning-only.

## DONE — 0.2.79 Self-contained Signup Provenance Pack

- [x] Dùng chung classifier signup authority giữa Program API và Evidence Pack.
- [x] Ghi signup URL + authority vào `program-summary.json` và README trong pack.
- [x] Đưa signup URL vào source inventory dù chưa có research/evidence/fact.
- [x] Nâng pack format lên 4, giữ export read-only và không tạo audit/write.
- [x] Giữ PPC evidence-gated, commission riêng và project/campaign warning-only.

## DONE — 0.2.78 Safe Signup Source Visibility

- [x] Trả signup URL và provenance thận trọng qua Program API.
- [x] Hiện link đăng ký và nhãn nguồn ngay trong Terms Evidence Center.
- [x] Từ chối scheme ngoài HTTP(S) khi tạo/cập nhật chương trình.
- [x] Chặn link nguy hiểm lần hai ở giao diện và giữ legacy value dưới dạng chữ.
- [x] Giữ PPC evidence-gated, commission riêng và dự án/campaign warning-only.

## DONE — 0.2.77 Existing Program Signup Source Backfill

- [x] Điền source URL khi chương trình đã tồn tại nhưng `signup_url` còn trống.
- [x] Chọn nguồn evidence/commission chính thức, không dùng root chung khi có nguồn cụ thể.
- [x] Không ghi đè signup URL đã lưu hoặc exact partner portal.
- [x] Ghi audit `signup_url_discovered` bằng collector `official-web-v8`.
- [x] Production-copy Fliki giữ PPC `NOT_CHECKED`, commission riêng và warning-only.

## DONE — 0.2.76 Manager-aware Google Ads OAuth Setup

- [x] Nhận Manager Customer ID tùy chọn trong trình thiết lập một lần bấm.
- [x] Dùng MCC header ngay trong preflight của từng tài khoản quảng cáo đích.
- [x] Chỉ lưu MCC sau khi OAuth và truy vấn đọc thật thành công.
- [x] Rollback nguyên tử toàn bộ bốn/năm giá trị Keychain khi một bước ghi lỗi.
- [x] Chỉ hiện trạng thái MCC; giữ Google Ads read-only, PPC `NOT_CHECKED` và warning-only.

## DONE — 0.2.75 Verified Campaign ID Recovery

- [x] Nhận diện report đổi tên thiếu Campaign ID khi có Customer ID trực tiếp.
- [x] Resolve bằng đúng Customer ID và một tên campaign duy nhất đã lưu.
- [x] Chặn sai tài khoản, Customer ID trống, tên lạ và tên trùng trước commit.
- [x] Hiện attempted/resolved/unresolved trong receipt và số ID khôi phục trên Runtime/UI.
- [x] Giữ Google Ads read-only, PPC `NOT_CHECKED` và project/campaign warning-only.

## DONE — 0.2.74 Preserve Omitted Campaign Metadata

- [x] Ghi field-presence theo từng dòng Google Ads đã parse.
- [x] Giữ account/campaign metadata khi CSV rút gọn bỏ cột hoặc để placeholder.
- [x] Dùng tiền tệ campaign hiện có cho spend khi Customer ID đã xác minh trực tiếp.
- [x] Chặn fallback thiếu Currency code trước mọi database write.
- [x] Giữ Google Ads read-only, PPC `NOT_CHECKED` và project/campaign warning-only.

## DONE — 0.2.73 Pre-dedupe Customer ID Gate

- [x] Chứng minh dòng ID trống trùng key từng bị dedupe che khỏi gate.
- [x] Tách identity rows trước dedupe khỏi metric rows dùng commit.
- [x] Chặn toàn file khi bất kỳ parsed row nào dùng Customer ID fallback dưới header hiện hữu.
- [x] Giữ dedupe metric và CSV legacy no-column tương thích như cũ.
- [x] Ghi 0 campaign/spend; giữ Google Ads read-only, PPC `NOT_CHECKED` và warning-only.

## DONE — 0.2.72 Explicit Customer ID Evidence

- [x] Ghi nguồn Customer ID theo từng dòng: trực tiếp từ file hoặc fallback.
- [x] Chặn toàn file khi có cột Customer ID nhưng bất kỳ dòng nào để trống.
- [x] Lưu số dòng explicit/fallback trong account-identity audit.
- [x] Giữ tương thích CSV legacy không có cột qua single-account currency gate.
- [x] Ghi 0 campaign/spend khi chặn; giữ Google Ads read-only, PPC `NOT_CHECKED` và warning-only.

## DONE — 0.2.71 Google Ads Import Safety Receipt

- [x] Hiện Customer ID Google Ads đích trên Command Center.
- [x] Hiện riêng số file bị chặn do sai tài khoản.
- [x] Cảnh báo nói rõ đăng nhập tài khoản nào và xác nhận file chưa được nhập.
- [x] Tương thích trạng thái API cũ chưa có danh sách Customer ID.
- [x] Giữ campaign/spend cũ, Google Ads read-only, PPC `NOT_CHECKED` và dự án warning-only.

## DONE — 0.2.70 Google Ads Account Identity Gate

- [x] Chặn Customer ID không thuộc tài khoản AFI-OS trước mọi database write.
- [x] CSV cũ thiếu Customer ID chỉ được nhập khi tiền tệ khớp tài khoản duy nhất.
- [x] Đọc đúng `Day`, `Campaign state`, `Currency code` từ Google Ads Report Editor.
- [x] Hiện cảnh báo riêng cho báo cáo sai tài khoản; campaign/spend cũ giữ nguyên.
- [x] Giữ Google Ads read-only, PPC `NOT_CHECKED` và dự án warning-only.

## DONE — 0.2.69 Terms Source Authority Visibility

- [x] Ghi URL → authority vào audit mà không đổi database schema.
- [x] Trả provenance nhất quán qua research response và attempt history.
- [x] Hiển thị nhãn nguồn tiếng Việt trong Terms Evidence Center.
- [x] Nâng Evidence Pack format 3 với provenance trong JSON/CSV và SHA-256 manifest.
- [x] Giữ canonical PPC `NOT_CHECKED`, campaign/project và Google Ads từ xa nguyên vẹn.

## DONE — 0.2.68 Exact External Partner Signup Source

- [x] Chỉ đọc exact saved cross-domain signup URL qua HTTPS/public/same-host guard.
- [x] Gắn đúng `PARTNER_PORTAL` trong evidence, commission, snapshot, dedupe và audit.
- [x] Không đưa URL portal từ lịch sử vào merchant same-domain discovery.
- [x] Nguồn official/portal mâu thuẫn tạo commission `CONFLICT`; proposal không tự mở PPC.
- [x] Giữ mọi quyền PPC `NOT_CHECKED`, campaign/project và Google Ads từ xa nguyên vẹn.

## DONE — 0.2.67 Expected Probe Misses

- [x] Gắn PRIORITY/DISCOVERED/STANDARD_PROBE cho từng URL được xếp hàng.
- [x] Bỏ 404/410 chỉ cho standard probes chưa từng là nguồn.
- [x] Giữ 404 của stored/link chính thức và 5xx/timeout để audit/retry.
- [x] Production-copy Pictory: 7 nguồn, `collection_errors=[]`, `UNCHANGED`.
- [x] PPC `NOT_CHECKED`, campaign/project và Google Ads từ xa không đổi.

## DONE — 0.2.66 Truncated Source Change Stability

- [x] Không phát `CONTENT_CHANGED` khi một trong hai snapshot cùng URL bị truncated.
- [x] Trả `PARTIAL` khi hash prefix khác nhau nhưng không tạo Operations warning giả.
- [x] Vẫn trích proposal PPC/commission và tạo semantic conflict khi câu chính sách đổi.
- [x] Production-copy Pictory forced-difference: `PARTIAL`, 0 source changes.
- [x] Giữ PPC `NOT_CHECKED`, campaign/project và Google Ads từ xa nguyên vẹn.

## DONE — 0.2.65 Terms Source URL Dedupe

- [x] Bỏ chỉ các query navigation/tracking đã biết trước khi fetch và snapshot.
- [x] Giữ nguyên query nghiệp vụ như document/signature/ref.
- [x] Gộp URL tracking cũ trong source-change comparison để không tạo cảnh báo remove giả.
- [x] Live-check Pictory: 7 nguồn duy nhất thay vì 8 URL, commission vẫn `CONFLICT`.
- [x] Giữ mọi quyền PPC `NOT_CHECKED`, campaign/project và Google Ads từ xa nguyên vẹn.

## DONE — 0.2.64 Bounded Large Terms Pages

- [x] Đọc tối đa 1 MB đầu của trang chính thức lớn thay vì bỏ toàn bộ nguồn.
- [x] Giữ phát hiện link/policy trong phần đã đọc và không tăng giới hạn mạng/bộ nhớ.
- [x] Ghi `truncated` vào source snapshot, audit và Evidence Pack format 2.
- [x] Live-check bản sao Pictory: 8 nguồn, không lỗi size, commission vẫn `CONFLICT`.
- [x] Giữ mọi quyền PPC `NOT_CHECKED`, không đổi campaign/project hoặc Google Ads từ xa.

## DONE — 0.2.63 Inbox Evidence Pack Shortcut

- [x] Thêm `Tải pack` trực tiếp cho mọi Operations item có program.
- [x] Đồng bộ evidence selection cho Inbox, Registry, research và review.
- [x] Giữ một endpoint export duy nhất, không tạo đường ghi dữ liệu mới.
- [x] Không đổi permission, evidence/commission decision hoặc campaign/project.

## DONE — 0.2.62 Terms Evidence Pack Export

- [x] Xuất ZIP theo chương trình từ Terms Evidence Center.
- [x] Gồm canonical PPC, evidence, commission riêng, research, audit và SHA-256 manifest.
- [x] Chống CSV formula injection và chỉ xuất audit fields đã allow-list.
- [x] Xác minh trên bản sao Pictory thật: 5 nguồn, 2 commission conflict, 0 PPC evidence.
- [x] Export chỉ đọc; không đổi permission, campaign/project, commission decision hoặc Google Ads.

## DONE — 0.2.61 Noninteractive Backup Exit Accuracy

- [x] Bỏ prompt Enter cuối khi chạy với `AFI_OS_NONINTERACTIVE=1`.
- [x] Trả exit 0 sau khi backup đã xác minh thành công.
- [x] Giữ hành vi chờ Enter khi người dùng mở file bằng tay.
- [x] Kiểm thử bằng runtime giả, không chạm database thật.
- [x] Không đổi database, PPC, campaign/project, commission hoặc Google Ads.

## DONE — 0.2.60 Snapshot Scope Cache Upgrade

- [x] Không dùng thời điểm scan làm độ mới của source file.
- [x] Thay confirmation legacy bằng kết quả hiện tại có `source_modified_at` và account/date scopes.
- [x] Giữ last-known rows trong lúc nâng metadata một lượt.
- [x] Khóa regression khi legacy checked_at mới hơn mtime thật của file.
- [x] Không đổi spend, PPC, campaign/project, commission hoặc Google Ads từ xa.

## DONE — 0.2.59 Google Ads Snapshot Ordering

- [x] Xử lý snapshot khác tên theo thứ tự cũ đến mới để dữ liệu mới nhất luôn thắng.
- [x] Lưu phạm vi tài khoản/ngày và chỉ đếm một lần khi hai file chồng dữ liệu.
- [x] Chặn snapshot cũ quay lại ghi đè spend hoặc campaign metrics mới hơn.
- [x] Hiện số snapshot cũ đã chặn trên Runtime; giữ confirmation qua scan rỗng.
- [x] Giữ bốn quyền PPC `NOT_CHECKED`, mọi campaign/project và Google Ads từ xa nguyên vẹn.

## DONE — 0.2.58 Last-known Google Ads Confirmation

- [x] Tách kết quả scan hiện tại khỏi báo cáo Ads đã xác nhận gần nhất.
- [x] Giữ số dòng, ngày dữ liệu và thời điểm xác nhận qua scan rỗng/rejected-only.
- [x] Dùng last-known date cho stale warning nhưng không nhân với cảnh báo thiếu cột.
- [x] Giữ checksum memory để file quay lại không bị đọc/ghi/audit lại.
- [x] Khôi phục confirmation legacy qua lượt cache cũ trống; giữ PPC/campaign nguyên vẹn.

## DONE — 0.2.57 Google Ads CSV Missing-column Guidance

- [x] Phát hiện file đổi tên gần đúng nhưng thiếu Campaign ID hoặc Date.
- [x] Chỉ đúng menu Cột/Phân đoạn để người vận hành xuất lại.
- [x] Chặn file có dấu commission và bỏ cảnh báo cũ khi có file hợp lệ mới hơn.
- [x] Chỉ phân tích một lần khi tên chuẩn và tên đổi có cùng checksum.
- [x] Hiện số file thiếu cột/bản trùng trên Runtime; giữ bốn PPC `NOT_CHECKED`.

## DONE — 0.2.56 Content-aware Google Ads CSV Discovery

- [x] Tự nhận diện Google Ads CSV khi tên file bị đổi hoặc không còn theo mẫu cũ.
- [x] Bắt buộc đủ ID/tên campaign, ngày, chi phí và tối thiểu hai cột traffic.
- [x] Bỏ qua CSV commission tương tự và chỉ đọc tối đa 256 KiB khi nhận diện.
- [x] Lưu phương thức nhận diện từng file và hiện tổng số file đổi tên trên Runtime.
- [x] Giữ nhập lặp an toàn, PPC `NOT_CHECKED`, campaign/project và Google Ads remote state.

## DONE — 0.2.55 Latest-attempt Warning Context

- [x] Operations Inbox đếm URL từ attempt audit mới nhất thay vì immutable run cũ.
- [x] Cảnh báo manual/retry mở source URL của lần thử hiện tại trước nguồn cũ.
- [x] Giữ fallback tương thích cho audit cũ chưa có source_urls.
- [x] Giữ grouping cùng campaign warning và source-change warning.
- [x] Không đổi permission, evidence/fact, campaign/project hoặc Google Ads.

## DONE — 0.2.54 Current-attempt Source Accuracy

- [x] Trả source URLs của chính lần rà hiện tại khi research run được tái sử dụng.
- [x] Giữ research run gốc bất biến và dùng audit attempt làm nguồn sự thật theo thời điểm.
- [x] Áp dụng cho collector có proposal, manual result và fixture.
- [x] Đồng bộ POST research response với lịch sử research-attempts.
- [x] Không nhân run/evidence/fact và không đổi PPC, campaign/project hoặc Google Ads.

## DONE — 0.2.53 Official Source Change Tracking

- [x] Tạo SHA-256 từ phần văn bản liên quan affiliate/PPC/commission của từng nguồn đã đọc.
- [x] Phân biệt nguồn mới, mất, đổi nội dung và tạm thời không truy cập được.
- [x] Bỏ qua thay đổi footer/nội dung không liên quan để giảm cảnh báo giả.
- [x] Lưu dấu nguồn và so sánh trong audit trail mà không lưu toàn bộ trang web.
- [x] Hiện thay đổi trong lịch sử rà và Operations Inbox dưới dạng warning-only.
- [x] Giữ bốn quyền PPC, campaign/project và Google Ads remote state hoàn toàn không đổi.

## DONE — 0.2.52 Terms Research Source Memory

- [x] Lưu mọi URL trang chính thức liên quan đã đọc, kể cả khi chưa trích được evidence.
- [x] Ưu tiên URL evidence/fact còn hiệu lực rồi tới URL research gần nhất cùng domain.
- [x] Khôi phục nguồn từ lần rà xảy ra trước khi program được tạo.
- [x] Không dùng trang root chung làm signup URL khi có nguồn evidence cụ thể hơn.
- [x] Chặn URL chỉ còn trong evidence/fact đã reject quay lại qua lịch sử.
- [x] Giữ kiểm tra HTTPS/cùng domain/public IP và không tự mở PPC hoặc đổi campaign/project.

## DONE — 0.2.51 Verified Backup Auto-Recovery

- [x] Xác minh lại SHA-256, integrity, foreign key và schema thật khi liệt kê backup.
- [x] Trả `database_status=OK` ngay sau khi tạo backup thành công.
- [x] Không tính backup lịch lỗi là bản an toàn hoặc dùng nó để trì hoãn 24 giờ.
- [x] Runtime chỉ hiện backup lịch hợp lệ gần nhất và báo khi cần tự tạo bản thay thế.
- [x] Hiện trạng thái từng backup trên giao diện; giữ file lỗi để chẩn đoán, không tự xóa.
- [x] Restore chỉ chọn bản đã xác minh; không đổi PPC, campaign/project hoặc Google Ads.

## DONE — 0.2.50 Same-root Terms Warning Grouping

- [x] Gom cảnh báo program-level thiếu evidence với cảnh báo campaign cùng nguyên nhân.
- [x] Hiện số lượng và tên campaign liên quan ngay trên một việc theo dõi.
- [x] Áp dụng cùng quy tắc cho luồng thiếu nguồn thủ công và retry tạm thời.
- [x] Giữ quyết định evidence `PROHIBITED`/`CONFLICT` là việc riêng, không che mất rủi ro cần xét.
- [x] Giữ từng campaign/spend ở Risk & Exposure; không đổi permission hoặc dừng/loại dự án.
- [x] Không migration, không thay database schema và không ghi Google Ads.

## DONE — 0.2.49 Terms Research Visibility

- [x] Tách thời điểm automation đã rà khỏi thời điểm evidence PPC được xác nhận.
- [x] Hiện trạng thái lần rà, độ mới và lần đến hạn tiếp theo theo từng chương trình.
- [x] Ghi rõ “không thấy quyền PPC công khai” thay vì gắn nhãn evidence stale gây hiểu nhầm.
- [x] Thêm một cảnh báo program-level khi lần rà thành công chỉ tìm thấy commission.
- [x] Không nhân cảnh báo cho `MANUAL_INPUT_REQUIRED`/`RETRY_REQUIRED` đã có luồng riêng.
- [x] Giữ PPC `NOT_CHECKED`, gate warning-only, campaign/project và dữ liệu cũ nguyên vẹn.

## DONE — 0.2.48 Operator Inbox Triage

- [x] Gom mọi commission proposal của một program thành một quyết định trong Inbox.
- [x] Hiện đủ rate/type khi commission đang CONFLICT.
- [x] Gom các scope NOT_CHECKED thành một cảnh báo tự theo dõi, không yêu cầu xác nhận.
- [x] Gom cảnh báo Terms của nhiều campaign theo program; từng campaign vẫn còn ở Exposure.
- [x] Lưu đúng cờ duplicate run vào audit cho cả fixture và web live.
- [x] Chặn pricing discount “SAVE MORE THAN 15%” bị nhập nhầm thành commission.
- [x] Giữ từng evidence/fact nguyên vẹn để review và audit riêng.
- [x] Không đổi PPC, campaign/project, database schema hoặc Google Ads remote state.

## DONE — 0.2.47 Semantic Permission Proposal Refresh

- [x] Refresh cùng URL/scope/decision thay vì nhân proposal vì excerpt đổi.
- [x] Lưu audit before/after và refreshed evidence count.
- [x] Hiện riêng số mới/làm mới/không đổi cho evidence và commission.
- [x] Lưu và hiện các số này trong lịch sử từng lần rà tự động.
- [x] Không ghi đè evidence ACCEPTED/REJECTED hoặc nhập tay.
- [x] Decision mới vẫn tạo proposal riêng và kích hoạt conflict warning.
- [x] Giữ canonical PPC, campaign/project và commission facts không đổi.

## DONE — 0.2.46 Semantic Commission Proposal Refresh

- [x] Refresh proposal tự động cùng nguồn/rate thay vì nhân bản vì excerpt đổi.
- [x] Cho phép làm rõ recurring unspecified → lifetime trên cùng fact proposal.
- [x] Lưu audit before/after và trả refreshed count riêng.
- [x] Không ghi đè fact ACCEPTED/REJECTED hoặc nhập tay.
- [x] Tính commission state trên toàn chương trình; giữ PPC/campaign warning-only.

## DONE — 0.2.45 Google Ads API Cadence Protection

- [x] Giữ CSV/Terms heartbeat 30 phút nhưng chỉ gọi Google Ads API mỗi 6 giờ.
- [x] Lỗi tạm thời tự retry sau 6 giờ; lỗi xác thực giãn 24 giờ và yêu cầu đăng nhập.
- [x] OAuth thành công tạo one-shot request không chứa secret để đồng bộ ngay.
- [x] Xóa request sau lần thử và không tạo SyncRun giả khi API còn mới.
- [x] Hiện ETA API trên Runtime; giữ SELECT-only, CSV fallback và warning-only.

## DONE — 0.2.44 LaunchAgent Regeneration on Update/Rollback

- [x] Tái tạo plist từ code phiên bản vừa cài, không bootstrap file cũ.
- [x] Dùng manager của phiên bản được phục hồi khi rollback.
- [x] Chạy health check trong manager trước khi báo runtime đã phục hồi.
- [x] Báo lỗi rõ nếu regeneration thất bại.
- [x] Xác nhận live plist + launchctl cùng là 1.800 giây.

## DONE — 0.2.43 30-Minute Maintenance Heartbeat

- [x] Đổi LaunchAgent maintenance từ 6 giờ xuống heartbeat 30 phút.
- [x] Đồng bộ Runtime/Terms ETA theo đúng nhịp 30 phút.
- [x] Khóa regression: backup vẫn 24 giờ, Terms stable 24 giờ, retry 6 giờ.
- [x] Giữ maintenance lock, import idempotent và warning-only.
- [x] Update/reload không còn lùi Terms gần 6 giờ.

## DONE — 0.2.42 Google Ads Preflight Before Keychain Commit

- [x] Đổi refresh token mới thành access token hoàn toàn trong bộ nhớ.
- [x] Chạy SearchStream chỉ đọc một ngày cho mọi Customer ID đã lưu.
- [x] Chỉ commit Keychain sau khi OAuth và Google Ads API cùng chấp nhận.
- [x] Lỗi auth/network/rate limit giữ Keychain cũ và CSV fallback.
- [x] Không ghi campaign/database trong preflight; không trả hoặc log secret.

## DONE — 0.2.41 Atomic Google Ads Credential Setup

- [x] Hoàn tất OAuth trước khi ghi bất kỳ credential nào.
- [x] Ghi đủ bốn Keychain item theo bundle và tự rollback nếu lỗi giữa chừng.
- [x] OAuth bị hủy giữ nguyên toàn bộ bộ credential đang dùng.
- [x] Setup thành công yêu cầu maintenance kiểm tra API ngay.
- [x] UI nói rõ người dùng chỉ cung cấp JSON + Developer Token; CSV fallback vẫn chạy.

## DONE — 0.2.40 Quiesced Disaster Restore

- [x] Tạm dừng đúng server và maintenance LaunchAgent trước Restore.
- [x] Xác nhận localhost đã đóng trước khi chạm database.
- [x] Luôn khởi động lại chế độ cũ sau thành công, lỗi hoặc gián đoạn.
- [x] Suy ra schema từ migration graph khi database hiện tại không mở được.
- [x] Giữ nguyên raw database/WAL/SHM trong emergency snapshot trước khi thay dữ liệu.

## DONE — 0.2.39 Schema-Aware Backup Restore

- [x] Ghi Alembic schema head, integrity và foreign-key status trong backup mới.
- [x] Đọc schema thật của cả backup thường và backup trước update.
- [x] Restore bỏ qua SHA sai, database hỏng, foreign key lỗi và schema không tương thích.
- [x] Kiểm tra lại bản tạm, tạo emergency backup rồi mới thay database đang chạy.
- [x] Giữ nguyên toàn bộ backup cũ, permission, campaign/project và commission decisions.

## DONE — 0.2.38 Terms Fetch Error Classification

- [x] Phân loại timeout/network/429/5xx là tạm thời.
- [x] Phân loại 404/410 và lỗi safety/content là cố định.
- [x] Chỉ lỗi tạm thời mới tạo `RETRY_REQUIRED`.
- [x] 404/no-evidence chuyển đúng `MANUAL_INPUT_REQUIRED`, không retry vô hạn.
- [x] Giữ permission, campaign/project và commission decisions không đổi.

## DONE — 0.2.37 Terms Schedule Grace

- [x] Thêm biên lịch 5 phút cho mốc retry 6 giờ và refresh 24 giờ.
- [x] Không bỏ lỡ chu kỳ vì collector chạy sau maintenance vài mili-giây.
- [x] Đồng bộ ETA Runtime với cùng biên lịch.
- [x] Khóa biên 23h54/23h56 và 5h59 bằng regression tests.
- [x] Không đổi permission, campaign/project hoặc commission decisions.

## DONE — 0.2.36 Temporary Terms Failure Auto-Retry

- [x] Tách lỗi web tạm thời thành `RETRY_REQUIRED`.
- [x] Tự retry sau 6 giờ; kết quả ổn định giữ chu kỳ 24 giờ.
- [x] Chỉ dùng `MANUAL_INPUT_REQUIRED` khi đã truy cập nhưng không có evidence rõ ràng.
- [x] Retry vào Inbox dưới dạng cảnh báo, `requires_user=false`.
- [x] Đồng bộ Runtime/ETA và giữ permission/campaign/commission decisions không đổi.

## DONE — 0.2.35 Scheduled Terms Refresh ETA

- [x] Giữ riêng mốc đủ 24 giờ và ETA chạy thật.
- [x] Căn ETA vào chu kỳ bảo trì 6 giờ kế tiếp sau khi Terms đủ hạn.
- [x] Hiện cả hai mốc trên Command Center.
- [x] Kiểm thử chương trình quá hạn, còn mới và chưa từng rà.
- [x] Không đổi permission, campaign/project hoặc commission decisions.

## DONE — 0.2.34 Terms Refresh Schedule Visibility

- [x] Tính số chương trình đã đến hạn rà Terms từ lần thử thực tế gần nhất.
- [x] Tính mốc rà Terms gần nhất cho toàn hệ thống.
- [x] Hiện lịch và số đến hạn trên Runtime/Command Center.
- [x] Giữ Terms là cảnh báo, không đổi PPC permission hoặc loại campaign/project.
- [x] Không migration và không tự quyết ba commission facts đang chờ người dùng.

## DONE — 0.2.33 Unmapped Google Ads Context Recovery

- [x] Tự retry Google Ads file thành công nhưng còn `unmapped_rows`.
- [x] Dùng lại `program_domain` sau khi program tương ứng xuất hiện.
- [x] Tạo mapping mà không nhân spend/daily stats.
- [x] Giữ mapping thủ công và PPC permission không đổi.
- [x] Hiện số file retry vì chưa ghép trên Runtime/Command Center.

## DONE — 0.2.32 Failed Commission CSV Auto-Recovery

- [x] Không cache vĩnh viễn commission file từng `ERROR`/`MAPPING_REQUIRED`.
- [x] Tự phân tích lại sau khi affiliate program/mapping xuất hiện.
- [x] Giữ cache idempotent cho file commission đã thành công.
- [x] Hiện riêng retry lỗi và retry thiếu mapping trên Runtime/Command Center.
- [x] Không ghi đè conflict và không đổi PPC/campaign/Google Ads.

## DONE — 0.2.31 Failed Google Ads CSV Auto-Recovery

- [x] Không cache vĩnh viễn checksum của file Ads từng `ERROR`.
- [x] Tự phân tích lại file lỗi ở chu kỳ sau khi Customer ID/context đã có.
- [x] Giữ cache idempotent cho file đã thành công.
- [x] Hiện số file lỗi được tự thử lại trên Runtime/Command Center.
- [x] Không đổi PPC permission, campaign inclusion hoặc Google Ads remote state.

## DONE — 0.2.30 Actionable Terms Exception Drilldown

- [x] Thêm lỗi collector gần nhất vào cảnh báo thiếu nguồn Terms.
- [x] Hiện số URL nguồn đã ưu tiên và link nguồn tốt nhất nếu có.
- [x] Nút Inbox tải luôn lịch sử rà Terms của đúng chương trình.
- [x] Giới hạn nội dung lỗi, giữ cảnh báo và không đổi permission/campaign.
- [x] Không migration và không ghi Google Ads.

## DONE — 0.2.29 Terms Attempt Visibility

- [x] Thêm API chỉ đọc cho lịch sử rà Terms theo từng chương trình.
- [x] Hiện thời điểm, trạng thái, URL đã lấy/ưu tiên và lỗi trên giao diện.
- [x] Hiện duplicate heartbeat và nhãn `PPC KHÔNG ĐỔI` rõ ràng.
- [x] Hiện lỗi ngay trong kết quả khi người dùng chủ động rà domain.
- [x] Không migration, không đổi permission, campaign/project hoặc Google Ads.

## DONE — 0.2.28 Manual Attempt Audit Trail

- [x] Ghi audit cho mọi lần live collector cần nhập nguồn thủ công.
- [x] Ghi riêng cả lần chạy trùng/heartbeat thay vì mất dấu lần thử.
- [x] Lưu URL đã thử, URL ưu tiên, lỗi thu thập và thời điểm chạy.
- [x] Khóa bằng test Pictory và xác nhận `permissions_changed=false`.
- [x] Không đổi database schema, permission, campaign/project hoặc Google Ads.

## DONE — 0.2.27 Fixture Seed-Only Live Recheck

- [x] Chỉ seed fixture khi chưa có research run cùng fixture version.
- [x] Recheck Pictory sau seed dùng live collector + stored source URLs.
- [x] Không refresh heartbeat fixture khi live web lỗi.
- [x] Giữ commission facts, PPC permission và campaign/project an toàn.

## DONE — 0.2.26 Stored Source Revalidation

- [x] Ưu tiên URL Terms/commission đã lưu khi recheck.
- [x] Giữ mọi chặn SSRF, redirect, HTTPS, port và kích thước trang.
- [x] Bỏ qua nguồn đã bị reject.
- [x] Commission-only scan không thể giữ sai trạng thái xanh khi PPC source mất.
- [x] Không đổi canonical permission hoặc loại/dừng campaign/project.

## DONE — 0.2.25 Terms Freshness vs Verification Clarity

- [x] Runtime trả riêng số `TERMS_OK` và số chương trình còn cảnh báo.
- [x] Đổi nhãn freshness thành “Lần rà Terms còn mới”.
- [x] Thêm thẻ “Terms đã xác minh” dựa trên evidence-backed gate.
- [x] Giữ API cũ tương thích và không đổi dữ liệu/permission/campaign.

## DONE — 0.2.24 Consistent Terms Attempt Ordering

- [x] Tạo một selector chung dùng `max(checked_at, updated_at)` và ID ổn định.
- [x] Dùng cùng selector trong maintenance, Runtime, Operations Inbox và source-loss gate.
- [x] Kiểm thử tình huống source date mới hơn nhưng heartbeat thực tế cũ hơn.
- [x] Giữ nhịp recheck 24 giờ theo lần chạy thực sự mới nhất.
- [x] Không đổi database, PPC permission, campaign/project hoặc Google Ads.

## DONE — 0.2.23 Latest Terms Source Loss Guard

- [x] So sánh lần rà Terms mới nhất với sự kiện accepted/review evidence gần nhất.
- [x] `MANUAL_INPUT_REQUIRED` mới hơn tự hạ `TERMS_OK` thành cảnh báo chưa xác minh.
- [x] Dùng heartbeat `updated_at` cho lần rà trùng nội dung.
- [x] Đồng bộ trạng thái ở Programs, Dashboard, Compliance, Exposure và Operations Inbox.
- [x] Lần rà thành công hoặc review chủ động mới hơn có thể khôi phục trạng thái xanh.
- [x] Không đổi permission, không loại campaign/project và không tác động Google Ads.

## DONE — 0.2.22 Official Terms Change Conflict Guard

- [x] So sánh fresh official proposals với accepted evidence theo scope.
- [x] Proposal mới trái accepted evidence lập tức tạo `WARNING_TERMS_CONFLICT`.
- [x] Hai official proposals chưa xét trái nhau cũng cảnh báo conflict.
- [x] Tách từng câu policy; không suy lệnh cấm direct link thành cấm toàn bộ PPC.
- [x] Loại proposal sai khôi phục trạng thái từ accepted evidence.
- [x] Không đổi canonical permission, không loại project/campaign và không tác động Google Ads.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.21 Campaign Auto-map Runtime Visibility

- [x] Runtime API đọc số liệu campaign auto-map từ chu kỳ maintenance mới nhất.
- [x] Command Center hiện mapped/unresolved/preserved bằng tiếng Việt.
- [x] Maintenance cũ không có trường mới vẫn trả số 0 an toàn.
- [x] Không thay đổi mapping, PPC permission, campaign state hoặc Google Ads.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.20 Historical Campaign Mapping Backfill

- [x] Bảo trì rà lại campaign cũ chưa có program mapping.
- [x] Tự ghép khi có đúng một merchant domain rõ ràng, kể cả CSV không đổi.
- [x] Giữ nguyên mọi mapping đã có và để domain mơ hồ/chỉ là chuỗi con ở Inbox.
- [x] Ghi số lượng scanned/mapped/unresolved/preserved vào báo cáo bảo trì.
- [x] Ghi audit cho mỗi mapping backfill tự động.
- [x] Không đổi PPC permission, campaign state, Google Ads hoặc project inclusion.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.19 Safe Campaign Domain Auto-mapping

- [x] Tự ghép campaign mới/chưa ghép khi tên chứa đúng một merchant domain.
- [x] Kiểm tra ranh giới domain để không map nhầm chuỗi con.
- [x] Domain có nhiều chương trình vẫn để chưa ghép và tiếp tục cảnh báo.
- [x] Không ghi đè mapping thủ công hoặc mapping khác đã có.
- [x] Hiện số dòng tự ghép trong preview, auto-folder, API và SyncRun.
- [x] Không đổi PPC permission, không loại campaign và không gửi lệnh thay đổi Google Ads.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.18 Google Ads Resilience & Action Routing

- [x] Retry tối đa ba lần cho network/429/5xx với delay 1s/2s.
- [x] Không retry lỗi xác thực hoặc request vĩnh viễn.
- [x] Phân loại `AUTH_FAILED / RATE_LIMITED / ERROR` trong SyncRun.
- [x] Error summary không chứa token, header hoặc response body.
- [x] AUTH_FAILED mới yêu cầu người dùng chạy setup lại.
- [x] RATE_LIMITED/ERROR là warning-only và tự thử lại chu kỳ sau.
- [x] CSV fallback/campaign/project/PPC không đổi khi API lỗi.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.17 Automatic Google Ads SELECT-only Sync

- [x] OAuth refresh → access token chỉ ở memory.
- [x] Fixed API v25 SearchStream URL và fixed GAQL `SELECT` campaign/day metrics.
- [x] Giới hạn tối đa 31 ngày; lịch 24/7 dùng bảy ngày đã hoàn tất.
- [x] Đối chiếu matched/different/new trước khi commit.
- [x] Giữ một canonical Google Ads row, không cộng đôi API với CSV.
- [x] CSV chạy trước, API chạy sau và trở thành nguồn mới hơn khi sẵn sàng.
- [x] API mới loại yêu cầu sửa/xuất CSV fallback cũ khỏi Operations Inbox.
- [x] Missing credential không đọc secret, không gọi mạng và không làm maintenance lỗi.
- [x] Không thay đổi PPC permission, project inclusion hoặc campaign state trên Google.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.16 Secure Google Ads OAuth Setup

- [x] Một lệnh mở luồng nhập OAuth Desktop JSON + Developer Token.
- [x] OAuth loopback trên `127.0.0.1` random port, state validation và PKCE S256.
- [x] Lưu bốn credential vào macOS Keychain, không đưa secret vào process arguments.
- [x] Không lưu secret vào database/API/UI/log.
- [x] Kiểm thử callback end-to-end bằng dữ liệu giả, không gọi Google thật.
- [x] Giữ `READ_ONLY_REPORTING`, write operations `false` và CSV fallback `true`.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.15 Google Ads Read-only Readiness

- [x] Nhận và chuẩn hóa Customer ID đã lưu.
- [x] Kiểm tra presence-only bốn credential trong macOS Keychain.
- [x] Không trả hoặc log giá trị secret.
- [x] Endpoint + Command Center card cho readiness.
- [x] Khóa mode chỉ-đọc, write operations `false` và CSV fallback `true`.
- [x] Regression backup/rollback và production-copy.

## DONE — 0.2.14 Terms Recheck Heartbeat

- [x] Giữ `checked_at` của nguồn/bằng chứng gốc khi nội dung không đổi.
- [x] Cập nhật heartbeat riêng trên duplicate manual/web/fixture research.
- [x] Dùng heartbeat cho lịch refresh và thẻ Terms freshness.
- [x] Chờ đủ 24 giờ sau recheck thay vì lặp mỗi chu kỳ 6 giờ.
- [x] Regression Pictory `CONFLICT`, PPC `NOT_CHECKED` và không nhân evidence/facts.
- [x] Backup/rollback và production-copy.

## DONE — 0.2.13 Automatic Affiliate Commission Ingest

- [x] Chỉ phát hiện CSV có tên commission/hoa hồng và bỏ symlink/file quá lớn.
- [x] Chọn bản numbered export mới nhất trong mỗi nhóm tên.
- [x] Chỉ auto-map khi filename hoặc cột domain/merchant khớp duy nhất một chương trình.
- [x] Chống quét lại bằng SHA-256 và dùng source domain ổn định cho state update.
- [x] File lỗi/conflict/mapping mơ hồ không commit và vào Operations Inbox.
- [x] Hiện trạng thái commission auto-ingest trên Command Center.
- [x] Regression không thay đổi PPC/campaign, backup/rollback và production-copy.

## DONE — 0.2.12 Google Ads Data Freshness

- [x] Lưu khoảng ngày metric đã đọc từ báo cáo hợp lệ.
- [x] Hiện ngày dữ liệu mới nhất trên Command Center kể cả khi file không đổi.
- [x] Xem dữ liệu đến hôm qua là còn mới; cảnh báo từ ngày kế tiếp.
- [x] Chỉ tạo một việc Operations khi thật sự cần người dùng xuất báo cáo mới.
- [x] Giữ nguyên mọi campaign và PPC permission khi dữ liệu cũ.
- [x] Nâng cache an toàn, chống nhập trùng và regression updater/production copy.

## DONE — 0.2.11 Runtime Accuracy & Single Bootstrap

- [x] Giữ số dòng report trong runtime status khi SHA không đổi.
- [x] Bỏ kickstart maintenance trùng sau RunAtLoad bootstrap.
- [x] Giữ kickstart server và KeepAlive.
- [x] Regression updater/LaunchAgent và toàn bộ application suite.

## DONE — 0.2.10 Automatic Google Ads Report Ingest

- [x] Chọn bản campaign report mới nhất trong Downloads, hỗ trợ tên tiếng Việt Unicode.
- [x] Bỏ file cũ cùng nhóm và chờ file mới ổn định trước khi đọc.
- [x] Chống quét lại bằng SHA-256 và chống spend trùng theo campaign/ngày/source.
- [x] Giữ mapping hiện có; campaign mới chưa ghép vào Operations Inbox.
- [x] File thiếu cột/lỗi không tự commit và xuất hiện trong Inbox.
- [x] Hiện trạng thái quét Ads trên Command Center.
- [x] Kiểm chứng với hai file thật: chọn bản `(1)`, 9 dòng, 149.291 VND, 0 dòng ghi trùng.

## DONE — 0.2.9 In-app Runtime Status

- [x] Hiện server/maintenance LaunchAgent ngay trên Command Center.
- [x] Hiện lần maintenance gần nhất và thời điểm dự kiến chạy tiếp.
- [x] Hiện scheduled backup gần nhất và hạn backup tiếp theo.
- [x] Đếm Terms còn mới/quá 24 giờ theo từng chương trình.
- [x] Chỉ đọc trạng thái; không thay đổi permission hoặc campaign.
- [x] Regression tests cho HEALTHY, NOT_CONFIGURED và API schema.

## DONE — 0.2.8 Safe 24/7 Operations

- [x] Server tự chạy lại sau đăng nhập/restart và tự phục hồi khi process dừng.
- [x] Maintenance mỗi 6 giờ với khóa chống chạy chồng.
- [x] Backup tối đa một lần/ngày và làm mới Terms quá 24 giờ.
- [x] Lỗi một domain không chặn chuẩn hóa Finance hoặc Operations Inbox.
- [x] Updater tạm dừng/khôi phục LaunchAgent an toàn.
- [x] Lệnh một lần bấm để bật, xem trạng thái và tắt 24/7.
- [x] Kiểm thử trên bản sao dữ liệu production và giữ nguyên warning-only behavior.

## DONE — 0.2.7 Exception-driven Operations Inbox

- [x] Gom Terms Evidence, commission facts, FX và reconciliation exceptions.
- [x] Báo nguồn Terms/FX không tự lấy được.
- [x] Hiện campaign terms warning nhưng không biến thành exclusion gate.
- [x] Điều hướng một nút tới đúng màn hình xử lý.
- [x] Tự làm mới hàng đợi sau action.
- [x] Kiểm thử backend, UI và dữ liệu production copy.

## DONE — 0.2.6 Commission Fact Review Queue

- [x] Nút Xác nhận/Loại cho commission proposal.
- [x] Kiểm tra authority, confidence, date và official merchant domain.
- [x] Audit decision và commission resolution state.
- [x] Conflict cần xử lý rõ từng fact; không tự chọn nguồn.
- [x] Khóa regression: commission review không thay đổi PPC permission.

## DONE — 0.2.5 Generic Official Terms Collection

- [x] Domain ngoài fixture → bounded same-domain HTTPS discovery.
- [x] Trích PPC/brand/non-brand/direct-link/trademark thành sourced proposal.
- [x] Trích commission riêng khỏi PPC permission.
- [x] Chặn private host, redirect ngoài domain, port lạ và page quá 1 MB.
- [x] Không tự mở permission; không thấy bằng chứng rõ thì giữ `NOT_CHECKED`.
- [x] Idempotent evidence/fact/research run và gộp redirect trùng.
- [x] Kiểm chứng Fliki trên database copy và regression suite.

## DONE — 0.2.4 Currency Normalization & Reconciliation

- [x] Finance base currency settings; VND mặc định.
- [x] Sổ tỷ giá có nguồn và vòng đời đề xuất/duyệt/từ chối.
- [x] Giữ số tiền gốc; chuẩn hóa direct/inverse chỉ từ rate đã duyệt.
- [x] Báo coverage và cặp tiền tệ còn thiếu/quá hạn.
- [x] Reconciliation queue: ATTRIBUTED / PARTIAL / UNATTRIBUTED / DUPLICATE / CONFLICT.
- [x] Không ghi đè commission facts khi cùng ID nhưng khác amount/currency/date.
- [x] Giao diện Finance & Reconciliation và regression tests.
- [x] Migration giữ dữ liệu 0.2.3, backup/rollback và one-click updater.

## DONE — 0.2.3 Direct Google Ads report import

- [x] Đọc trực tiếp báo cáo campaign Google Ads tiếng Việt/Anh.
- [x] Tự tìm hàng tiêu đề sau phần mô tả báo cáo.
- [x] Bỏ dòng “Tổng số” để không cộng trùng spend/traffic.
- [x] Chuẩn hóa trạng thái và loại chiến dịch tiếng Việt.
- [x] Chống trùng giữa các nhãn nguồn Google Ads CSV.
- [x] Tự điền Customer ID khi hệ thống chỉ có một tài khoản.
- [x] Kiểm chứng bằng CSV thật của Fliki và regression tests.

## DONE — Sprint 0 / vertical slice

- [x] Đóng băng legacy v3.
- [x] Tạo repository structure mới.
- [x] SQLite schema 18 bảng.
- [x] Alembic initial migration.
- [x] Commission state model.
- [x] Compliance launch gate.
- [x] Economics engine one-time / limited / lifetime.
- [x] Module ⓪ entities và Independent Advertiser Score.
- [x] Manual capture API.
- [x] Advertiser graph API.
- [x] Chrome capture helper MVP.
- [x] Dashboard vertical slice.
- [x] Automated unit/API tests.
- [x] Security headers và localhost-only baseline.

## NEXT — Sprint 1

### P0 Data Integrity

- [x] Commission import service với idempotency.
- [x] Currency normalization ledger.
- [x] Reconciliation queue: ATTRIBUTED / PARTIAL / UNATTRIBUTED / DUPLICATE / CONFLICT.
- [x] TermsEvidence CRUD và expiry monitoring.
- [x] Backup/restore CLI.

### P0 Ad Intelligence

- [x] Parser review queue cho raw captures.
- [ ] Advertiser alias/dedupe workflow.
- [ ] Project/domain canonicalization.
- [ ] Watchlist và change detection.
- [x] Export evidence pack.

### P1 Connectors

- [x] Google Ads read-only adapter.
- [x] Universal CSV affiliate adapter.
- [ ] Chọn một network production đầu tiên.
- [x] SyncRun retry/backoff/freshness cho Google Ads và Terms.

### P1 UX

- [ ] Compliance Center đầy đủ.
- [ ] Program/Offer registry screens.
- [x] Finance reconciliation dashboard.
- [ ] Campaign draft approval queue.

## BLOCKED BY USER / EXTERNAL ACCESS

- [ ] Tạo hoặc xác nhận MCC.
- [ ] Developer Token.
- [ ] Google Cloud OAuth desktop client.
- [ ] Một affiliate-network credential hoặc report CSV thật.
- [ ] Một snapshot Ads Transparency Center thật để kiểm parser/capture flow.
## DONE — 0.2.99 Google Ads Keychain Terminal hotfix

- [x] Reproduce the double-prompt failure under a controlling TTY.
- [x] Feed password and confirmation through stdin without putting secrets in argv.
- [x] Detach the Keychain subprocess from Terminal's controlling TTY.
- [x] Preserve atomic five-item commit and prior-value rollback.
- [x] Verify focused tests, real PTY Keychain round trip and live Google Ads sync.
- [x] Preserve warning-only Terms behavior and disable every Google Ads write operation.
