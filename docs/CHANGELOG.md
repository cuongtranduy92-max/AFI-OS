# CHANGELOG

## 0.2.112 — Dot8 full project truth and true profit

- Crawl a bounded set of up to 12 official homepage, pricing, affiliate and Terms
  pages, preserving page role, source URL, quote and checked time.
- Extract a nine-item PPC checklist as proposal-only evidence; unsupported claims
  become `NOT_STATED` and never open a permission automatically.
- Show advertiser expansion inline in each Project, including known Projects, queued
  domains and `MỎ VÀNG` indicators without launching automatic recursive scans.
- Preserve exact Google Keyword Planner ranges and block a pass/fail decision when a
  range straddles the 2,000-search threshold.
- Add manual package pricing with source lineage so payback can be calculated while
  missing official pricing remains visible.
- Add Page 4 true-profit accounting for paid cash, on-web commission, ad spend,
  account rent and spend fees while retaining the existing CSV workflow.
- Require an explicit risk acknowledgement before saving a Search-Ads-prohibited
  Project to Step 2; Projects and campaigns remain warning-only and Google Ads read-only.

## 0.2.111 — Advertiser discovery and project propagation

- Connect SerpApi Google Ads Transparency Center through macOS Keychain only.
- Count active advertisers in the latest seven days and total advertisers ever seen,
  cache each domain for seven days and preserve truthful sourced zero results.
- Expand up to five advertiser IDs per request with pagination, show all target domains
  and mark advertisers with at least 15 domains as `MỎ VÀNG`.
- Let the operator watch an advertiser, rescan manually and queue newly discovered
  domains without automatically consuming more quota.
- Track the 250-call monthly quota, warn at 80% and block cleanly at 100%.
- Reuse queued appraisal jobs, preserve all existing data, keep Terms warning-only and
  retain Google Ads read-only behavior.

## 0.2.110 — Fixed modeled FX boundary

- Convert modeled payback and operational `$/ref` with the single editable
  `PAYBACK_FX_VND_PER_USD = 26000` constant.
- Prevent Camp Doctor from consuming Page 4 normalized amounts or FX ledger rows.
- Keep the Finance FX ledger unchanged and exclusive to actual cash reconciliation.
- Reject unsupported spend currencies transparently instead of borrowing a ledger rate.

## 0.2.109 — Progressive appraisal and truthful empty states

- `POST /api/appraise` trả cache và kết quả nhanh ngay, kèm job nền cho traffic,
  từ khoá và Terms; giao diện tự cập nhật mỗi giây mà không cần tải lại trang.
- Batch tối đa 50 domain trả ngay một batch ID, dùng một lượt Apify và bốn worker.
- Mỗi nguồn có trạng thái, nguồn gốc, ngày cache và nút thử lại độc lập.
- Mọi ô trống dùng nhãn rõ: chưa nối nguồn, không tìm thấy, cần đọc tay hoặc lỗi.
- Cache từ khoá 7 ngày; timeout Apify 45 giây, crawler 8/20 giây, Claude 30 giây.
- Job treo quá 10 phút được chuyển `FAILED` và có thể thử lại an toàn.
- Chuẩn hóa Customer ID có/không có dấu gạch khi Keyword Planner ghép tài khoản;
  phép tính tuổi tài nguyên không lệch một ngày quanh nửa đêm theo múi giờ máy.
- Google Ads vẫn chỉ đọc; PPC chưa đủ bằng chứng chỉ cảnh báo; LLM chỉ đề xuất.

## 0.2.108 — Camp Doctor and Vietnamese Terms summaries

- Add deterministic Camp Doctor diagnoses for CTR, real cost/ref, learning periods,
  keyword/search-term waste and the 20%/24-hour change rule.
- Extend Google Ads read-only reporting with keyword, search term, device, geography,
  demographic, ad and change-event views; no mutate/write operation is introduced.
- Store diagnosis/change history and expose campaign list/detail APIs plus Page 3 UI.
- Add Vietnamese summary/quote fields to Terms, commission and commercial proposals;
  translations are returned inside the existing single Claude call.
- Keep anti-fabrication verification on original quotes and force the exact support
  warning when source pages do not disclose PPC policy.
- Present Vietnamese first with “Xem bản gốc”, localize visible states/enums, and keep
  all Step 2 ad assets in English.

## 0.2.107 — Claude Terms extraction with human review

- Add Keychain-only Anthropic setup and a content-addressed Claude extraction cache.
- Extract commission, packages, payment, cookie and Ads terms only from bounded
  crawler text; reject every quote that is not present in the source text.
- Persist all extracted facts as proposals and require explicit operator review
  before economics or canonical permissions can use them.
- Keep upper-bound commission out of payback and preserve warning-only Projects,
  campaign state and Google Ads read-only behavior.
- Add migration, extraction, cache, anti-fabrication and updater/rollback coverage.

## 0.2.106 — Resource management and guarded Step 2 binding

- Add the Tài nguyên tab with email nurture stages, rotating manual checklists,
  resource KPIs, lineage and deterministic shortage/concentration alerts.
- Extend existing Google Ads account records with email, type, cost, state, health
  and one-current-Project binding; preserve historical assignment records.
- Expose secret-free CRUD APIs for emails, Ads accounts and ten resource types;
  reject password/token fields rather than silently storing them.
- Restrict Step 2 account selection to a mature clean email plus a free READY account,
  and bind it on internal deploy without any Google Ads write operation.
- Add an SQLite migration round-trip and complete updater/rollback coverage.

## 0.2.105 — Apify traffic and top countries

- Add Apify actor `trakk/similarweb-scraper` as the recommended traffic provider;
  its token stays in macOS Keychain and is absent from source, logs and database.
- Store monthly visits and top-five country shares as separate source-aware snapshots
  with observation period, 0.75 confidence and a 45-day validity window.
- Send up to 50 appraisal domains in one actor run (`maxConcurrency=10`) and reuse
  valid cache entries without reading the credential or making a paid request.
- Treat unsupported/junk domains as explicit `NO_DATA`, never a fabricated zero.

## 0.2.104 — Dot3 Step 2 campaign content builder

- Add one persisted `camp_plans` record per Project with DRAFT/DEPLOYED state,
  editable plan JSON, deterministic linter results and an audited deploy transition.
- Generate exactly 15 headlines, 4 descriptions, 4 ref-linked sitelinks and 4
  callouts for Projects whose current stored Step 1 score has `pass=true`.
- Re-lint operator edits line by line and block deploy while any error remains;
  warning-only findings remain visible without mutating Terms or PPC permissions.
- Expose only PASS Projects in the Step 2 UI, retain drafts, and hand clean plans to
  Step 3 without creating or changing a Google Ads campaign.

## 0.2.103 — Dot2 payback formula and appraisal scoring

- Match the operator's original sheet: low scenario `3×L`, high scenario `0.5×M`.
- Convert VND bids to USD package economics with the fixed `26,000 VND/USD` payback rate.
- Replace the `/api/appraise` score placeholder with a deterministic 0–100 engine.
- Preserve warning-only behavior for prohibited Ads, brand bidding restrictions and one-time commission.
- Add exact regression coverage for `170.4 / 126.5` day sheet results.

## 0.2.102 — Accepted maximum commission visibility

- Show an operator-accepted commission fact in the appraisal contract even when its
  wording is `up to`; add an explicit warning and continue excluding it from payback.
- Map contract `commission.packages` to sourced offer prices rather than commission
  percentages.
- Preserve all 0.2.101 backup, Legacy cleanup, endpoint and UI behavior.

## 0.2.101 — Dot1.1 appraisal contract and truthful Step 1

- Added `POST /api/appraise` with the stable Dot1.1 response contract for project,
  traffic, keyword/CPC, advertisers, commission, payment, Terms, payback and score.
- Rebuilt the first screen around one domain check plus batch paste. Ten source-aware
  cards now show either collected data or `Đang chờ nguồn`; missing data is never zero.
- Kept the score seam explicit for Claude's formula engine: `score.total` and
  `score.pass` stay null until that engine has sufficient sourced inputs.
- Hardened manual and scheduled backups: absent, empty, corrupt or wrong-schema
  databases fail loudly, incomplete backup directories are removed and every success
  is rechecked against SQLite integrity, foreign keys, schema head and SHA-256.
- Retired the obsolete Legacy navigation and its automatic `afi-data.json` request,
  eliminating the old 404 without introducing a second source of truth.
- Terms remain warning-only; commission proposals remain operator-controlled and all
  Google Ads access remains read-only.

## 0.2.100 — One-domain automatic Project Check

- Replaced Step 1 manual traffic entry with one domain action that runs every connected
  collector and returns a source card for every unavailable data group instead of a blank.
- Added Keychain-only setup for Similarweb API or Semrush Trends API and automatic monthly
  website-traffic snapshots with source URL, period, confidence, expiry and audit lineage.
- Added read-only Google Ads Keyword Planner enrichment for global English brand/domain
  search volume plus low/high top-of-page bid estimates.
- Kept website traffic, search demand and CPC as separate metrics. Missing providers remain
  `CONNECTION_REQUIRED`; no number is invented and no project is excluded.
- Terms remain proposal/warning-only, commission proposals are not accepted automatically,
  and all Google Ads operations remain read-only.

## 0.2.99 — Source-backed traffic entry and Google Ads Keychain hotfix

- Added a Step 1 traffic form that accepts a monthly website-traffic value, complete
  source URL, observation date, source name, geography and note.
- A small CSV can populate the same form with `website_traffic_monthly`, `source_url`
  and `observed_at`; missing or invalid sources are rejected and duplicates are not
  inserted twice.
- Manual/CSV traffic is stored as a versioned `MetricSnapshot`, expires after 45 days,
  is audited and immediately feeds the Step 1 traffic criterion. Missing traffic still
  reads `NOT_COLLECTED`, never zero.
- Similarweb/Semrush remains optional for automated collection and top-country data;
  Google Ads keyword volume/CPC stays semantically separate from whole-site traffic.

- Fixed one-click Google Ads setup on macOS Terminal: new Keychain items now receive
  password plus confirmation through a private stdin pipe while detached from the
  controlling TTY.
- Developer Token, OAuth client ID/secret, refresh token and optional manager ID remain
  absent from argv, database, UI and logs.
- OAuth and the SELECT-only Google Ads preflight still complete before the five-item
  atomic Keychain commit; partial failure still restores the previous bundle.
- Verified a real Keychain store/read/delete round trip from a PTY and a successful
  read-only sync for Customer ID `123-456-7890` through manager `987-654-3210`.
- No Google Ads write operation, PPC permission, commission decision, project or
  campaign state is changed.
- Updater now checks each LaunchAgent's `WorkingDirectory` before stopping it, so an
  update test or another AFI-OS copy cannot stop the live instance by label alone.

## 0.2.98 — Source-backed Project Check Step 1

- Opening a Project now shows the complete Step 1 cockpit: project/affiliate profile,
  advertisers, traffic, keyword demand, CPC range, Terms, payout fields, verified
  commission and estimated payback.
- The original AFI formula is reproduced as `30 × (150 clicks × CPC) ÷
  (average package price × accepted commission rate)`; package price is the average
  of sourced plan prices, not an assumption that one customer buys three plans.
- Missing values name the exact source or connection required (Similarweb/Semrush,
  Google Keyword Planner, affiliate portal or public evidence) instead of returning
  an empty project check or a fabricated zero.
- Commission proposals, `up to` rates and conflicts cannot feed payback. Currency
  mismatch also blocks the estimate.
- `Lưu và chuyển Bước 2` requires complete core inputs, records the full Step 1
  snapshot in audit, moves only the internal Project stage and exposes the Project
  in the Step 2 queue. PPC permissions, campaigns and Google Ads remain untouched.

## 0.2.97 — Relationship observation dates

- Project network links now expose the source observation timestamp separately from
  an advertiser's optional ad `first_seen`/`last_seen` activity fields.
- The UI labels that timestamp `kiểm tra/quan sát`, so a sourced snapshot no longer
  appears to have no date when ad activity dates were not supplied.

## 0.2.96 — Recursive project network journey

- `Tìm dự án` is now the first and initial workspace instead of the operations dashboard.
- Opening a Project automatically expands every known advertiser and every other
  sourced Project observed for that advertiser; no advertiser click is required.
- Clicking any related Project recenters the journey and automatically expands the
  next Project → advertiser → Project neighborhood.
- Relationship cards retain source URLs, observation dates and reported ad counts;
  absent observations remain `NOT_COLLECTED`, never a fabricated zero.
- Added focused relationship APIs without changing PPC permissions, commission facts,
  campaigns or Google Ads.

## 0.2.95 — Project trace entry point

- Added a dedicated `Truy vết dự án` form: entering a domain now retains the
  Project and immediately starts source-backed affiliate/Terms/commission research.
- Renamed the Portfolio query to `Lọc hồ sơ đã lưu`; it no longer looks like the
  action for discovering a new project.
- After tracing, all saved-list filters reset and the new/existing Project is shown.
- Research results report source count and status; canonical PPC permissions remain
  unchanged and no campaign or Google Ads write occurs.

## 0.2.94 — Domain intake from Portfolio

- A domain that is not yet in AFI-OS now gets an explicit `Thêm dự án và bắt đầu
  rà nguồn` action instead of an unexplained empty table.
- Intake immediately retains one idempotent Project, then enriches Terms,
  commission, advertiser and campaign data incrementally.
- New projects start at `INTAKE`; Terms stay `NOT_CHECKED`, commission and market
  metrics stay unknown, and no Program/Campaign is fabricated.
- Intake is audited, warning-only, preserves every project and performs no Google
  Ads write or permission change.

## 0.2.93 — Repair-v2 proposal preservation

- Preserve a valid `PAID_SEARCH = NON_BRAND_ONLY` proposal when the same official
  excerpt contains the required branded negative-keyword condition.
- Restore proposals incorrectly rejected by truth repair v1 only when they were
  automated, unreviewed, and carry the exact v1 repair marker.
- Canonical permissions remain `NOT_CHECKED`; no campaign or Google Ads write occurs.

## 0.2.92 — Truthful missing-state copy

- Project Radar now distinguishes `Chưa thu thập` from `Chưa đủ dữ liệu`.
- A missing 30-day activity window can no longer read like zero active advertisers.
- No Terms permission, commission decision, campaign state, or Google Ads write is changed.

## 0.2.91 — Truthful advertiser snapshots and scoped Snov facts

- Added an evidence-backed batch advertiser import with stable advertiser IDs,
  exact source URL, checked time, excerpt, reported ad count, audit and idempotency.
- Portfolio now distinguishes `NOT_COLLECTED`, `PARTIAL` and `AVAILABLE`; a missing
  advertiser value says `Chưa thu thập` and is never presented as zero.
- Activity for the last 30 days remains unknown unless last-seen coverage exists;
  importing a current result page cannot fabricate active-advertiser counts.
- Fixed conditional brand-bidding parsing: non-brand PPC and negative-brand-keyword
  requirements are separated from brand bidding that needs written permission.
- Commission facts are resolved by commercial subject, so Snov's 40% plan subscription
  rate and 20% LinkedIn Automation slot rate are a tiered schedule, not a conflict.
- Added an idempotent audited repair for prior automated proposal misclassification.
- No permission proposal is auto-accepted and no campaign or Google Ads write occurs.

## 0.2.90 — Program ↔ Project sync

- Mọi Program mới từ form hoặc Terms research tự được giữ lại thành một Project có thể lọc trong Portfolio.
- Maintenance tự chữa Program cũ bị thiếu Project; thao tác lặp lại idempotent.
- Khi domain đã có Project, chỉ ghép Program còn thiếu và tuyệt đối không ghi đè stage, đăng ký, owner hoặc next action của người vận hành.
- Đồng bộ chỉ thay đổi dữ liệu nội bộ: không mở PPC permission, không loại project và không ghi Google Ads.

## 0.2.89 — Command Center UI hotfix

- Sửa biến `job` bị dùng nhầm trong bảng Operations Inbox, khiến toàn bộ đợt tải giao diện báo `job is not defined`.
- Gắn định danh automation job vào đúng bảng hàng đợi để nút “Mở đúng job” vẫn hoạt động.
- Thêm khối “Bắt đầu từ đây” giải thích vòng lặp vận hành sáu bước ngay trên Command Center.
- Gắn version cho static assets để trình duyệt không giữ lại JavaScript lỗi của bản cũ sau update.
- Không thay đổi database, Terms/PPC permissions, commission decision, project hoặc campaign.

## 0.2.88 — Wake-safe 24/7

- Đổi lịch maintenance từ `StartInterval` sang hai mốc lịch phút 00/30 để launchd chạy bù sau khi máy Mac thức dậy.
- Giữ `RunAtLoad` và toàn bộ cơ chế lock/idempotency; không thay đổi Terms, PPC permission hoặc campaign.

## 0.2.87 — Exception Queue

- Đưa automation job đã hết lần thử vào Operations Inbox dưới dạng việc cần xử lý.
- Nút “Mở đúng job” chuyển thẳng tới hàng tương ứng và đặt focus vào nút thử lại.
- RETRY_WAIT vẫn tự thử lại; không thay đổi PPC permission, project hoặc campaign.

## 0.2.86 — Durable Automation Queue

### Added

- Persistent `automation_jobs` queue with atomic claim, worker lease, bounded exponential
  retry, expired-lease recovery, dead-letter and audited operator retry.
- Terms maintenance now records each due research operation as a durable job. A crash or
  transient exception keeps the job for retry instead of losing it between heartbeats.
- Command Center shows due/running/retry/dead-letter counts and the latest job state; only
  failed/deferred jobs expose a local `Thử lại ngay` action.
- Queue payload/result diagnostics recursively redact token, secret, credential, password,
  authorization and cookie fields and bound stored sizes.
- Job types are reserved for Ads import, commission import, campaign mapping, project
  discovery and advertiser refresh so later data sources can be added without redesigning
  the worker contract.

### Compatibility and safety

- Queue workers are data collection/processing only. They cannot open PPC permission,
  remove a project, change a remote campaign or create Google Ads writes.
- A stale worker token cannot finish another worker's job; only one concurrent claimant
  wins. Crashed jobs stop after the configured attempt limit instead of retrying forever.
- Migration is additive and rollback drops only the new queue table. Program, Project,
  Terms, commission, campaign, spend and advertiser data remain unchanged.

## 0.2.85 — Project Portfolio & Truth Drawer

### Added

- `Quản lý dự án` hợp nhất workflow, đăng ký, Terms, commission, advertiser,
  campaign, chi phí, CTR và cảnh báo vào một hồ sơ giữ lại lâu dài cho mỗi dự án.
- Mọi metric dùng chung envelope có quality, source, observed time, confidence,
  geography/language/date range, method version, previous value và lineage.
- `WHY THIS NUMBER?` hiển thị dấu vết nguồn; metric snapshot mới được version hóa
  để data advertiser/keyword/traffic/bid được bổ sung dần.
- Workflow có giai đoạn, trạng thái đăng ký, owner, next action và due time; mọi thay đổi
  được audit và không tạo Google Ads write.
- Migration tạo Project từ Program 0.2.x hiện có và liên kết campaign nội bộ qua mapping
  đã xác nhận, đồng thời giữ nguyên Program, permission, campaign status và dữ liệu cũ.

### Fixed

- Project chưa có observation không còn hiện advertiser `0`, top share `100%` hay score
  `0`; trạng thái đúng là `DATA_MISSING/UNKNOWN`.
- CTR dưới 40% tạo cảnh báo tối ưu nhưng không sửa hoặc dừng campaign.

### Compatibility and safety

- Pictory được giữ ở `PAUSED/BLOCKED_REGISTRATION`, commission 50% recurring đã chấp
  nhận; PPC vẫn `NOT_CHECKED` vì chưa có evidence công khai đủ điều kiện.
- Fliki giữ nguyên campaign, dữ liệu Google Ads Customer ID `123-456-7890` và commission
  proposal chưa được tự quyết.
- Update có checksum, verified SQLite backup, migration round trip, rollback tự động và
  không đóng gói thư mục `data/`, `backups/`, `.env` hay credential.

## 0.2.84 — Operations Capture Target Focus

### Added

- The Operations Inbox now carries the capture exception type and target ID into Ad Intelligence.
- Opening a capture-review exception scrolls to and highlights the exact oldest pending snapshot, then focuses the first missing review field.
- If the target was handled in another tab, the UI safely falls back to the next pending snapshot or reports that the queue is empty.

### Compatibility and safety

- The action performs navigation and read-only queue refresh only; it never accepts, rejects or materializes a capture.
- Existing Program, Finance and Exposure Operations actions keep their behavior.
- No schema migration, Google Ads write, PPC permission change, commission decision or campaign/project removal is introduced.

## 0.2.83 — Raw Ad Capture Review Queue

### Added

- Unstructured ad snapshots now enter a deterministic oldest-first review queue instead of creating advertiser/project records.
- Operators can add the advertiser and project domain, accept the capture into the graph, or reject it while retaining the raw audit record.
- Operations Inbox groups all pending captures into one actionable exception and links directly to Ad Intelligence.
- The web capture form and Chrome helper can save raw evidence without advertiser/domain; their labels make clear whether the snapshot updates the graph now or waits for review.
- Review rows expose the full evidence, lock all controls while a decision is saved, and require an operator-written rejection reason.

### Compatibility and safety

- Accept and reject decisions are audited and idempotent; a parsed capture cannot be rejected and a rejected capture cannot be accepted implicitly.
- A structured capture, or a pending capture explicitly accepted with advertiser and project domain, can materialize or link an observation.
- No schema migration, Google Ads write, PPC permission change, commission decision or campaign/project removal is introduced.

## 0.2.82 — Intraday Google Ads Snapshot Freshness

### Added

- Runtime reports the source-file timestamp separately from the recurring folder confirmation time.
- A same-day CSV snapshot older than six hours creates a warning-only Operations item and makes Runtime visible as `ATTENTION`.
- Command Center shows the source timestamp and next intraday refresh time.

### Compatibility and safety

- A successful read-only API result for today suppresses the CSV refresh warning.
- Legacy results without a trustworthy source timestamp do not create a new warning.
- No schema migration or Google Ads write is introduced; campaign/project retention, PPC evidence gates and commission separation are unchanged.

## 0.2.81 — Safe OAuth Desktop JSON Auto-detection

### Added

- `SETUP-GOOGLE-ADS-READ-ONLY.command` automatically selects a single valid OAuth Desktop JSON from the top level of Downloads.
- Candidates are validated with the same Desktop-app parser used by the real OAuth flow and ordered newest-first for deterministic review.

### Compatibility and safety

- Invalid JSON, web clients, oversized files, symlinks and non-JSON files are ignored without exposing client secrets.
- Multiple valid Desktop clients are never guessed; the operator must explicitly choose one. An explicit CLI path still bypasses discovery.
- Keychain remains untouched until OAuth refresh and SELECT-only Google Ads preflight succeed; CSV fallback, warning-only projects and PPC evidence gates are unchanged.

## 0.2.80 — Guard Every External UI Link

### Fixed

- Every external link rendered by Operations, ad captures, Terms evidence, commission facts, research attempts/source changes, signup metadata and FX now uses one HTTP(S)-only renderer.
- Malformed or legacy non-web URLs are rendered as escaped text instead of a clickable anchor and no longer throw while formatting a hostname.

### Compatibility and safety

- The UI contains a single dynamic anchor constructor, protected by URL parsing, an explicit HTTP(S) allowlist, hostname presence and `rel="noopener"`.
- Existing valid links keep the same destination and label; no database migration or data rewrite is required.
- Rendering changes cannot open PPC, decide commission, remove/stop projects or campaigns, or write to Google Ads.

## 0.2.79 — Self-contained Signup Provenance Pack

### Added

- Evidence Pack format 4 records `signup_url` and its conservative `OFFICIAL/PARTNER_PORTAL` provenance in `program-summary.json` and the human-readable README.
- A stored signup URL is included in the pack source inventory even when no research run, PPC evidence or commission fact exists yet.

### Compatibility and safety

- Program API and Evidence Pack share one source-authority classifier, preventing provenance drift between UI and exports.
- Export remains read-only and creates no audit/database writes; signup metadata cannot open PPC, decide commission or remove/stop a project or campaign.
- No database migration is required; format 3 packs remain immutable historical artifacts.

## 0.2.78 — Safe Signup Source Visibility

### Added

- Program API now returns the stored signup URL with conservative source provenance: same merchant domain is `OFFICIAL`, while an external host is `PARTNER_PORTAL`.
- Terms Evidence Center shows a safe “Mở link đăng ký” action and a Vietnamese source label, or an explicit missing-link warning.

### Compatibility and safety

- Program create/update accepts only complete HTTP(S) signup/dashboard URLs; non-web schemes are rejected before persistence.
- The UI independently scheme-checks every signup link, so malformed legacy values remain non-clickable text.
- Signup provenance is retrieval metadata only: PPC remains evidence-gated, commission remains separate, and warning-only projects/campaigns are retained.

## 0.2.77 — Existing Program Signup Source Backfill

### Fixed

- Live Terms collection now passes existing programs through the same safe source backfill used for newly created programs.
- A blank `signup_url` is filled from the authoritative evidence/commission source selected by the collector.
- Collector provenance advances to `official-web-v8`, and audit records whether a signup URL was discovered.

### Compatibility and safety

- Any existing signup URL, including an exact external partner portal, is immutable to automated discovery.
- Source backfill is metadata only: permission evidence remains proposal-first, commission remains separate, and PPC/campaign/project state is unchanged.
- Production-copy Fliki resolved to `https://fliki.ai/affiliate-program` with zero collection errors and all four PPC permissions still `NOT_CHECKED`.

## 0.2.76 — Manager-aware Google Ads OAuth Setup

### Added

- `SETUP-GOOGLE-ADS-READ-ONLY.command` nhận Manager Customer ID (MCC) tùy chọn và đưa ID đã chuẩn hóa vào chính truy vấn preflight Google Ads.
- Manager ID được lưu trong macOS Keychain cùng bốn OAuth credential sau khi mọi Customer ID đích đã qua kiểm tra đọc thật.
- Readiness/Runtime/Command Center chỉ hiện cờ “MCC đã cấu hình”, không trả ID hoặc secret.

### Compatibility and safety

- Tài khoản đăng nhập trực tiếp tiếp tục để trống MCC và hoạt động như trước.
- Manager ID sai định dạng bị chặn trước khi mở OAuth hoặc ghi Keychain.
- Bộ bốn hoặc năm credential được rollback nguyên tử nếu bất kỳ lần ghi nào lỗi; CSV fallback, PPC `NOT_CHECKED` và project/campaign warning-only không đổi.

## 0.2.75 — Verified Campaign ID Recovery

### Added

- Báo cáo đổi tên có `Customer ID` trực tiếp, ngày/chi phí/traffic và tên campaign có thể được tự nhận diện dù thiếu cột `Campaign ID`.
- Campaign ID chỉ được khôi phục bằng cặp `Customer ID + tên campaign chuẩn hoá` khớp đúng một campaign đã có.
- File result và Runtime ghi số dòng attempted/resolved/unresolved; Command Center hiện biên nhận số Campaign ID đã tự khôi phục.

### Compatibility and safety

- Sai Customer ID được chặn bởi account gate trước mọi write, kể cả khi dòng chưa resolve được Campaign ID.
- Tên campaign lạ, tên trùng trong cùng tài khoản hoặc Customer ID trống không bao giờ được đoán; tất cả ghi 0 dòng.
- Không tạo campaign mới từ tên, không ghi Google Ads từ xa, không mở PPC và không loại/dừng project/campaign warning-only.

## 0.2.74 — Preserve Omitted Campaign Metadata

### Added

- Mỗi dòng Google Ads ghi rõ trường nào thực sự có giá trị trong CSV.
- Báo cáo có `Customer ID` trực tiếp được phép thiếu metadata campaign; ngân sách, trạng thái, loại chiến dịch, tên tài khoản và tiền tệ cũ được giữ nguyên.
- Báo cáo dùng fallback tài khoản nhưng thiếu tiền tệ ở bất kỳ dòng nào bị chặn bằng `ACCOUNT_CURRENCY_REQUIRED` trước commit.

### Compatibility and safety

- Campaign mới vẫn nhận default tương thích; campaign hiện có chỉ đổi trường được cung cấp rõ ràng.
- Spend mới dùng tiền tệ hiệu lực của campaign thay vì default giả từ cột bị thiếu.
- Google Ads vẫn read-only; PPC giữ `NOT_CHECKED`, còn project/campaign rủi ro chỉ cảnh báo và không bị loại hoặc dừng.

## 0.2.73 — Pre-dedupe Customer ID Gate

### Added

- Account identity is evaluated against every successfully parsed campaign row before metric-key deduplication.
- Commit rows remain deduplicated independently, so data idempotency does not weaken identity evidence.
- A duplicate row with a blank Customer ID now blocks the complete file even when an earlier same-key row contains the correct ID.

### Compatibility and safety

- Metric dedupe behavior and legacy no-column single-account currency fallback are unchanged.
- The new regression proves the former bypass first returned `SUCCESS` and now writes zero campaign/spend rows.
- Google Ads remains read-only; PPC stays `NOT_CHECKED`, and warning-only projects/campaigns are never excluded or stopped.

## 0.2.72 — Explicit Customer ID Evidence

### Added

- Every parsed Google Ads row records whether its Customer ID came explicitly from the report or from the configured fallback.
- A report that contains a `Customer ID` column but leaves any parsed row blank is blocked as `CUSTOMER_ID_VALUE_REQUIRED` before commit.
- Account-identity audit metadata includes explicit-ID and fallback-ID row counts.

### Compatibility and safety

- Legacy exports with no Customer ID column remain compatible under the single-account currency gate.
- Correct explicit IDs continue to import, while wrong IDs and blank ID cells write zero campaign/spend rows.
- Google Ads remains read-only; PPC permissions remain `NOT_CHECKED`, and warning-only projects/campaigns are never excluded or stopped.

## 0.2.71 — Google Ads Import Safety Receipt

### Added

- Command Center displays the normalized Google Ads Customer ID target next to import health.
- The runtime response exposes configured Customer IDs and the count of account-mismatch files from the latest scan.
- Account-mismatch warnings state the exact Customer ID to sign into, confirm that the file was not imported, and confirm that existing campaign data was preserved.

### Compatibility and safety

- Older readiness payloads without `customer_ids` render safely with an empty fallback.
- This is a visibility-only safety improvement: rejected files still write zero campaign/spend rows.
- Google Ads remains read-only; PPC permissions remain `NOT_CHECKED`, and warning-only projects/campaigns are never excluded or stopped.

## 0.2.70 — Google Ads Account Identity Gate

### Added

- Every auto-imported campaign CSV is checked against configured Google Ads Customer IDs before any database write.
- Reports with an explicit Customer ID must match; legacy single-account exports without the column must match the configured account currency.
- Account mismatches produce a dedicated Operations warning with zero campaign/spend writes.
- Report Editor exports using `Day`, `Currency code` and `Campaign state` are supported; 10-digit Customer IDs are canonicalized to the existing dashed account ID.

### Compatibility and safety

- Existing Vietnamese exports without Customer ID remain compatible when their currency matches the single configured account.
- A cache-version bump rechecks prior CSVs through the new identity gate without changing confirmed historical data.
- Google Ads remains read-only; PPC permissions remain `NOT_CHECKED`, and warning-only projects/campaigns are never excluded or stopped.

## 0.2.69 — Terms Source Authority Visibility

### Added

- Every current research attempt records a normalized URL-to-authority map for `OFFICIAL`, `PARTNER_PORTAL`, `WRITTEN_CONFIRMATION`, `THIRD_PARTY` or `UNKNOWN`.
- Domain research responses and research-history responses expose the same provenance map; permission proposals also carry their own source authority.
- Terms Evidence Center renders Vietnamese authority labels beside each source URL and permission proposal.
- Evidence Pack format 3 exports source authority in `program-summary.json` and `research-attempts.csv`.

### Compatibility and safety

- No database migration is required. Older official collector snapshots without the field are recovered as `OFFICIAL`; invalid or unsupported labels are ignored.
- URLs without defensible provenance remain `UNKNOWN`; the UI never guesses from hostname alone.
- Provenance display is metadata only. It cannot accept evidence, open PPC, stop/exclude a campaign/project or write to Google Ads.
- Collector provenance advances to `official-web-v7`.

## 0.2.68 — Exact External Partner Signup Source

### Added

- Existing programs with a saved cross-domain signup URL can collect that exact public HTTPS page as `PARTNER_PORTAL`.
- Evidence, commission facts, proposal payloads, source snapshots and refresh audits preserve `OFFICIAL` versus `PARTNER_PORTAL` provenance.
- Official merchant pages and the external signup page share the same bounded eight-page research budget.

### Safety

- The partner portal collector never crawls links or guessed paths and rejects credentials, non-HTTPS URLs, private hosts and off-host redirects.
- External URLs in prior evidence/research history cannot leak into same-domain merchant discovery.
- Every extracted permission remains `PROPOSED`; canonical PPC stays `NOT_CHECKED` until operator review.
- Commission remains separate from PPC, and conflicting authoritative facts produce `CONFLICT` without excluding/stopping projects or campaigns.
- Collector provenance advances to `official-web-v6`; no database migration is required.

## 0.2.67 — Expected Probe Misses

### Fixed

- Candidate URLs now retain whether they came from stored sources, official page links or AFI-OS standard-path guesses.
- HTTP 404/410 from a guessed standard path is treated as an expected discovery miss instead of a collection error.
- A saved source or officially linked URL returning 404 remains auditable; 5xx/rate-limit/network failures still schedule retry.

### Safety

- Suppression applies only to never-confirmed standard probes and cannot hide the disappearance of a known source.
- Source snapshots, proposal extraction, commission conflict and warning-only PPC behavior are unchanged.
- Collector provenance advances to `official-web-v5`; no database migration is required.

## 0.2.66 — Truncated Source Change Stability

### Fixed

- Content hashes from bounded/truncated page prefixes no longer emit `CONTENT_CHANGED` when the byte prefix changes dynamically.
- A differing truncated hash produces source-change status `PARTIAL` with no source-change item; the truncation marker and both hashes remain auditable.
- Stable, complete official pages still produce `CONTENT_CHANGED` exactly as before.

### Preserved

- Truncated pages remain eligible for link discovery and PPC/commission proposal extraction.
- A changed semantic policy sentence still creates a separate proposal and can produce `WARNING_TERMS_CONFLICT` while canonical permission remains unchanged.
- Added, removed and temporarily unavailable sources are unaffected.
- Collector provenance advances to `official-web-v4`; no database migration is required.

## 0.2.65 — Terms Source URL Dedupe

### Fixed

- Known navigation and analytics fields (`nav`, `utm_*`, `gclid`, `fbclid`, `msclkid`) are removed before Terms URLs are queued, fetched or fingerprinted.
- The same official page no longer consumes multiple positions in the eight-page collection budget merely because it appears with tracking query variants.
- Existing source snapshots are normalized during comparison, preventing a one-time false removal warning when old tracking variants collapse.

### Preserved

- Business query parameters such as document IDs, signatures and affiliate references remain intact and can still identify distinct sources.
- HTTPS, same-domain, public-address, redirect and one-megabyte controls are unchanged.
- Collector provenance advances to `official-web-v3`; all old attempt audits remain immutable.
- URL cleanup only affects discovery identity. It cannot accept evidence, open PPC, or stop/exclude a campaign/project.

## 0.2.64 — Bounded Large Terms Pages

### Fixed

- Official HTML/text pages larger than 1 MB are no longer discarded in full.
- The collector reads only the first 1 MB, preserving relevant navigation links and policy excerpts found within the bounded prefix.
- Pictory's current large homepage can now contribute source discovery without a `Page exceeds the 1 MB safety limit` failure.

### Audit and export

- Every source snapshot records whether the page was truncated without storing the full page body.
- Evidence Pack format 2 includes the latest truncated-source URLs and per-attempt source-page count.
- Collector provenance advances to `official-web-v2`, keeping the new collection behavior distinguishable from old attempts.

### Safety

- The response read remains capped at 1 MB plus one detection byte; private hosts, off-domain redirects and unsupported content types remain blocked.
- Truncated sources only create proposals. No permission is opened, no campaign/project is stopped or excluded, and no Google Ads write is introduced.
- No database migration is required.

## 0.2.63 — Inbox Evidence Pack Shortcut

### Fixed

- Every program-level Operations item now offers `Tải pack` without first navigating through Terms tables.
- Inbox, Program Registry, domain research and review flows share one evidence-program selection state, so the export button cannot remain disabled after programmatic navigation.

### Safety

- The shortcut calls the same read-only 0.2.62 endpoint and introduces no alternate export path.
- It does not accept commission/evidence proposals, change PPC, or stop/exclude any campaign/project.
- No database migration or data write is introduced.

## 0.2.62 — Terms Evidence Pack Export

### Added

- Each saved program can download a read-only ZIP from Terms Evidence Center.
- The pack contains a human README, canonical program summary, Terms evidence, commission facts, research runs/attempts, review audit and a SHA-256 manifest.
- Pictory's real fixture exports five checked sources, separate conflicting commission facts and zero public PPC evidence while all canonical permissions stay `NOT_CHECKED`.

### Safety

- Fixed filenames and a sanitized domain prevent archive path injection.
- CSV cells beginning with formula characters are prefixed with an apostrophe before spreadsheet use.
- Audit payload export is allow-listed; internal/unrelated fields are not copied.
- Export creates no audit/database write, accepts no proposal, changes no PPC state and excludes/stops no project or campaign.

## 0.2.61 — Noninteractive Backup Exit Accuracy

### Fixed

- `BACKUP-AFI-OS.command` skips the final Enter prompt when `AFI_OS_NONINTERACTIVE=1`, returning exit code 0 after a verified backup succeeds.
- Interactive double-click behavior remains unchanged and still keeps Terminal open for the operator.

### Safety

- The command continues to delegate database backup, checksum, integrity, foreign-key and schema verification to the existing backup service.
- A shell integration regression uses a fake runtime so the exit behavior is tested without touching a real database.
- No database schema, PPC permission, campaign/project, commission or Google Ads state is changed.

## 0.2.60 — Snapshot Scope Cache Upgrade

### Fixed

- Cache-v8 confirmation upgrades now prefer a current result carrying real file modification time and account/date scopes over legacy metadata that only has a later scan timestamp.
- Snapshot ordering never treats `checked_at` as source freshness; only `source_modified_at` can protect data from an older file.

### Safety

- Existing confirmed rows remain available during the one-scan metadata upgrade.
- The regression fixture covers a legacy confirmation checked after the underlying file was modified.
- No spend, PPC permission, campaign/project inclusion, commission fact or remote Google Ads state is changed by the metadata correction.

## 0.2.59 — Google Ads Snapshot Ordering

### Fixed

- Campaign CSV snapshots from known and content-detected filename families are committed from oldest to newest, so the latest source modification always wins.
- Confirmed report metadata stores account/date snapshot scopes and Runtime counts overlapping scopes once instead of summing duplicate exports.
- A stale snapshot that returns after a newer confirmed snapshot is marked `SUPERSEDED` and cannot overwrite newer spend or campaign metrics.

### Safety

- Runtime exposes the number of blocked old snapshots for operator visibility.
- Cache-v8 rebuilds scope metadata once while preserving legacy confirmed rows through empty scans.
- No PPC permission, campaign/project inclusion, commission fact or remote Google Ads state is changed; no database migration is introduced.

## 0.2.58 — Last-known Google Ads Confirmation

### Added

- Every folder heartbeat stores current scan results separately from the last confirmed campaign report state.
- Runtime keeps the confirmed row count, metric date, source count and confirmation time through empty or rejected-only scans.
- Stale-data actions use the last confirmed metric date even when the newest scan sees no readable report.

### Safety

- A missing-column action remains the single root action when the confirmed data is also stale.
- Checksum memory survives empty scans, so a returning identical file is unchanged and creates no new spend or import audit.
- Legacy non-empty confirmation is recovered across a newer empty pre-0.2.58 run.
- No PPC, campaign/project, commission or remote Google Ads state is changed; no database migration is introduced.

## 0.2.57 — Google Ads CSV Missing-column Guidance

### Added

- A renamed campaign CSV that is strongly Ads-like but lacks Campaign ID or Date enters Operations Inbox instead of being silently ignored.
- The warning names every missing column and points to the exact Google Ads Columns or Segment menu needed to export it.
- Runtime reports missing-column candidates and same-heartbeat duplicate checksums.

### Safety

- Near-match detection requires campaign/cost, at least two traffic metrics and at least two Ads context columns.
- Commission-specific headers suppress the diagnostic, and an older near-match is ignored after a newer valid report arrives.
- Identical known/renamed files are parsed once per heartbeat with the known filename preferred.
- Warnings never mutate PPC permissions, campaign/project inclusion or remote Google Ads state; no database migration is introduced.

## 0.2.56 — Content-aware Google Ads CSV Discovery

### Added

- Google Ads campaign exports can be discovered from their column signature when the filename is renamed or localized unexpectedly.
- Content discovery requires campaign ID/name, metric date, cost and at least two traffic columns before a file becomes a candidate.
- Runtime reports how many files were recognized by content and records the detection method per file.

### Safety

- Content sniffing is bounded to 256 KiB and retains the existing stable-age, regular-file and 10 MiB gates.
- Commission-like CSV files without sufficient traffic columns are ignored; full campaign parsing remains authoritative.
- Import is idempotent, keeps PPC permissions `NOT_CHECKED`, retains all projects/campaigns and never writes to Google Ads.
- No database migration is introduced; 0.2.55 data and rollback points remain compatible.

## 0.2.55 — Latest-attempt Warning Context

### Fixed

- The no-public-PPC warning counts URLs from the newest research attempt audit instead of the immutable run's older source set.
- Manual/retry warnings link to the current attempt's checked source before stale run or priority sources.
- Operations keeps a safe fallback to run sources for legacy audit rows without current-attempt URLs.

### Safety

- Existing campaign/root-cause warning grouping remains unchanged.
- Attempt context is read-only presentation data; no research run, evidence, commission fact or campaign link is modified.
- PPC permissions remain `NOT_CHECKED` without accepted evidence and Google Ads write operations remain disabled.
- No database migration is introduced; 0.2.54 data and rollback points remain compatible.

## 0.2.54 — Current-attempt Source Accuracy

### Fixed

- `POST /api/programs/research` now returns the source URLs checked by the current attempt when an existing research run is reused.
- The immediate research result and `research-attempts` history now agree on the full current source set.
- Manual and fixture collector results expose the same explicit current-attempt source field.

### Safety

- The original research run remains immutable; attempt-specific observations stay in the audit trail.
- Reusing a run still creates no duplicate run, permission evidence or commission fact.
- The fix changes response accuracy only and never opens PPC, stops/excludes campaigns/projects or writes to Google Ads.
- No database migration is introduced; 0.2.53 data and rollback points remain compatible.

## 0.2.53 — Official Source Change Tracking

### Added

- Terms research fingerprints policy-relevant text for every official page actually read.
- Each attempt classifies official-source changes as added, removed, content-changed or temporarily unavailable.
- Research history exposes change status and affected URLs without exposing full-page content.
- Operations Inbox merges source changes into the existing Terms root warning or creates one warning-only tracking item when no root warning exists.

### Safety

- Only SHA-256 plus text lengths are stored; full page bodies are not copied into the database.
- Unrelated footer changes do not trigger a policy-change warning.
- A total temporary fetch failure is `UNAVAILABLE`, never a false source-removal claim.
- Source changes never accept evidence, open PPC, stop/exclude campaigns/projects or write to Google Ads.
- No database migration is introduced; existing data, backups and rollback behavior remain compatible.

## 0.2.52 — Terms Research Source Memory

### Added

- Every relevant official page actually read by Terms research is preserved in the research run, even when no permission or commission claim can be extracted.
- Later refreshes prioritize recent checked URLs for the same merchant domain after accepted/proposed evidence sources.
- Source memory survives research performed before an affiliate program record is created.
- Evidence-bearing URLs remain the program signup candidate; an informational root page cannot replace the more specific source.

### Safety

- A URL present only in rejected evidence/facts is excluded from research memory and cannot silently re-enter through run history.
- Stored URLs still pass the existing same-domain HTTPS, public-IP, redirect, port and size checks before network access.
- Remembering/rechecking a source creates no permission; canonical PPC stays `NOT_CHECKED` until explicit evidence review.
- No database migration, campaign/project mutation, commission decision or Google Ads write is introduced.

## 0.2.51 — Verified Backup Auto-Recovery

### Added

- Backup listing now recomputes SHA-256, SQLite integrity, foreign keys and actual schema before reporting a file as verified.
- Manual backup creation returns `database_status=OK` immediately after its write-time verification.
- Scheduled backups that fail verification no longer postpone the next automatic backup for 24 hours.
- Runtime uses only the latest verified scheduled backup, reports rejected backup count and requests immediate replacement when none is safe.
- System / Backup displays a clear verification status for every backup file.

### Safety

- Restore only considers backups whose current bytes pass every verification gate; invalid files remain visible for diagnosis but are never selected.
- A rejected scheduled backup triggers auto-recovery at the next 30-minute heartbeat without deleting the rejected artifact.
- The change does not modify campaign/project inclusion, Terms/PPC permissions, commission decisions or Google Ads remote state.
- No database migration is introduced; update and rollback preserve the existing SQLite file and all backup directories.

## 0.2.50 — Same-root Terms Warning Grouping

### Added

- Operations Inbox now merges a program-level Terms tracking exception with the campaign warning caused by that same missing evidence.
- The single item shows how many active campaigns are affected and includes their names for drilldown.
- Manual-source and temporary-retry Terms exceptions receive the same root-cause grouping.
- Risk & Exposure continues to retain every campaign, spend row and individual warning state.

### Safety

- Grouping changes presentation only; no evidence, research run, campaign link or permission row is modified.
- Explicit `PROHIBITED`/`CONFLICT` evidence-review decisions remain separate from campaign risk warnings.
- Missing evidence keeps canonical PPC permissions at `NOT_CHECKED` and never stops or excludes a campaign/project.
- No database migration or Google Ads write operation is introduced.

## 0.2.49 — Terms Research Visibility

### Added

- Program responses expose the latest actual research attempt, its status, next due time and freshness independently from accepted Terms evidence.
- The Terms table now says “đã rà” when automation recently checked official sources even if no public PPC permission was found.
- Programs with a successful commission-only scan receive one program-level `TERMS_PERMISSION_NOT_FOUND` tracking warning.
- The no-permission warning links to the research history and never asks the operator to approve an empty proposal.

### Safety

- A recent scan is never presented as verified PPC permission or accepted evidence.
- Missing public PPC language leaves every canonical permission at `NOT_CHECKED` and the gate at warning.
- The new fields and warning are read-only; no database migration, campaign/project mutation or Google Ads write is introduced.
- Existing manual/retry exceptions remain authoritative and are not duplicated by the new warning.

## 0.2.48 — Operator Inbox Triage

### Added

- Commission proposals are grouped into one operator decision per program.
- A commission conflict now shows every proposed rate/type in that single decision.
- Proposed `NOT_CHECKED` permission scopes collapse into one tracking warning per program.
- Repeated campaign Terms warnings collapse into one tracking warning per program.
- Operations counts distinguish real operator decisions from warnings automation keeps tracking.
- Research history now preserves whether each fixture/web attempt reused an existing run.
- Pricing phrases such as `SAVE MORE THAN 15%` are rejected as commission rates.

### Safety

- Grouping changes inbox presentation only; no evidence/fact row is merged or deleted.
- Pictory live refresh keeps only the sourced 40% and up-to-50% commission claims.
- `NOT_CHECKED` evidence remains auditable and refreshable but never opens a permission.
- Commission review still requires explicit per-fact accept/reject in Terms Evidence Center.
- Campaign/project inclusion, PPC permissions and Google Ads remote state never change.

## 0.2.47 — Semantic Permission Proposal Refresh

### Added

- Automated proposed permission evidence refreshes in place for the same URL/scope/decision.
- Every refresh updates the source snapshot and records a before/after audit.
- API responses expose `refreshed_terms_evidence` separately from imports/duplicates.
- Research UI separates new, refreshed and unchanged evidence/fact counts.
- Research-attempt history preserves the same counts for every automated run.
- A changed decision remains a new proposal so conflict detection keeps both claims.

### Safety

- Only official automated proposals are eligible for refresh.
- Accepted, rejected and manually collected evidence is immutable to automation.
- Semantic refresh never changes canonical PPC permissions or campaign/project state.
- Terms evidence and commission facts keep separate identity and review lifecycles.

## 0.2.46 — Semantic Commission Proposal Refresh

### Added

- Automated proposed commission facts refresh in place when the same official source/rate rewords its claim.
- Recurring-unspecified facts may be refined to recurring-lifetime without creating a second row.
- Every refresh stores a before/after audit and exposes `refreshed_commission_facts`.
- Research commission state now covers all non-rejected program facts, not only the current fetch.

### Safety

- Only official `AUTOMATED_FIXTURE`/`AUTOMATED_WEB` proposals are eligible for refresh.
- Accepted, rejected or manually collected facts are never overwritten.
- A genuinely new rate remains a new proposal and preserves `CONFLICT` warning behavior.
- PPC permissions, campaign/project inclusion and Google Ads remote state never change.

## 0.2.45 — Google Ads API Cadence Protection

### Added

- Google Ads API runs on a six-hour schedule while CSV and Terms keep the 30-minute heartbeat.
- Authentication failures wait 24 hours and remain an operator-login exception.
- Successful OAuth setup writes a secret-free one-shot sync request that bypasses an old wait window.
- Runtime exposes whether API sync is due and the next planned attempt.

### Safety

- A skipped fresh API cycle creates no duplicate SyncRun and performs no network request.
- The one-shot request is mode `0600`, contains only a timestamp and is cleared after an attempt.
- CSV fallback, campaign inclusion, PPC permissions and commission decisions remain unchanged.
- Google Ads write operations remain disabled; the connector still uses fixed SELECT-only queries.

## 0.2.44 — LaunchAgent Regeneration on Update/Rollback

### Added

- Updater invokes the installed version's `launchd_manager.py` after code/database verification.
- Both LaunchAgent plist files are regenerated from current code before bootstrap and health check.
- Rollback runs the restored version's manager, so service cadence also returns to that version.

### Safety

- A plist regeneration or health-check failure is reported as service-not-restored, never silent success.
- Database/code transactional verification remains complete before service regeneration starts.
- The live 30-minute interval is verified from both plist and launchctl state.
- No Terms/PPC/campaign/commission decision is changed by service configuration.

## 0.2.43 — 30-Minute Maintenance Heartbeat

### Added

- The maintenance LaunchAgent runs a lightweight heartbeat every 30 minutes instead of every six hours.
- Runtime ETA uses the same 30-minute cadence for the next maintenance and Terms attempt.
- Update/reload can delay newly due Terms by at most one heartbeat instead of nearly six hours.

### Safety

- Scheduled backup remains gated to once per 24 hours.
- Stable Terms remain gated to 24 hours and temporary web retries remain gated to six hours.
- CSV/API imports stay idempotent; maintenance lock still prevents overlapping cycles.
- Faster observation does not change PPC permissions or exclude/stop campaigns and projects.

## 0.2.42 — Google Ads Preflight Before Keychain Commit

### Added

- Setup refreshes an OAuth access token and runs one-day SearchStream for every stored Customer ID.
- The probe uses the same fixed read-only reporting query as the 24/7 connector.
- Keychain commit happens only after both OAuth refresh and Google Ads API access succeed.
- Setup reports only validated account count/date; access and refresh tokens never leave memory.

### Safety

- OAuth/developer-token/access errors leave the previous Keychain bundle untouched.
- Rate limits and network failures retry safely, then keep CSV fallback without a partial setup.
- The preflight performs no Google Ads mutate operation and writes no campaign/database row.
- Campaign inclusion, PPC permissions and Terms/commission warnings remain unchanged.

## 0.2.41 — Atomic Google Ads Credential Setup

### Added

- OAuth consent completes before any Google Ads credential is written to macOS Keychain.
- All four core credentials are committed as a bundle with rollback to previous values on write failure.
- A successful one-click setup asks the 24/7 maintenance LaunchAgent to test API sync immediately.
- Command Center explains that the operator provides only OAuth Desktop JSON and Developer Token.

### Safety

- Cancelling OAuth leaves every existing Keychain credential untouched.
- A partial first-time write removes new fragments; an update failure restores the complete old bundle.
- Secrets stay in memory/Keychain and are never returned by API, UI, result objects or logs.
- Google Ads remains read-only; CSV fallback, campaign inclusion and PPC warnings are unchanged.

## 0.2.40 — Quiesced Disaster Restore

### Added

- Restore pauses both macOS 24/7 LaunchAgents and verifies localhost is down before touching SQLite.
- The previous runtime mode is restarted after success, failure, interruption or an early safety stop.
- Expected schema heads are derived from the migration graph, so a corrupt live database can still be rescued.
- Pre-restore emergency snapshots preserve exact database, WAL and SHM bytes without opening them first.

### Safety

- A server that cannot be stopped cancels restore before any database mutation.
- WAL/SHM forensic copies use preserved filenames so later inventory reads cannot modify their bytes.
- Candidate checksum, integrity, foreign keys, declared schema and actual schema are still revalidated.
- No backup is deleted; PPC permissions, campaign/project inclusion and commission decisions are unchanged.

## 0.2.39 — Schema-Aware Backup Restore

### Added

- Every new backup records the actual Alembic schema head plus integrity and foreign-key checks.
- Backup inventory reads schema heads from both regular and transactional update backups.
- Restore scans newest-first and skips bad checksum, corrupt, foreign-key-invalid or wrong-schema copies.
- Restore revalidates the temporary copy and creates an emergency backup before replacing live data.

### Safety

- Existing backups are preserved; no retention deletion or database migration is introduced.
- A restore with no compatible healthy copy stops without changing the live database.
- Backup paths come from the controlled backup directory, not a path declared by a manifest.
- PPC permissions, campaign/project inclusion and commission decisions remain unchanged.

## 0.2.38 — Terms Fetch Error Classification

### Added

- Fetch failures are tagged as temporary only for network/timeout, HTTP 408/425/429 and 5xx.
- HTTP 404/410, reserved domains and safety/content validation failures are permanent misses.
- Only temporary failures create `RETRY_REQUIRED`; permanent no-evidence results use `MANUAL_INPUT_REQUIRED`.

### Safety

- Prevents endless retry loops caused by guessed policy paths returning 404.
- Retry/manual states remain warnings and never mutate PPC permissions or campaign/project inclusion.
- Error details remain bounded in audit/Inbox and no secret response body is stored.

## 0.2.37 — Terms Schedule Grace

### Added

- Terms due checks accept a five-minute scheduling grace around six-/24-hour boundaries.
- Runtime ETA uses the same grace when a maintenance schedule is available.
- A maintenance slot a few milliseconds before the nominal due timestamp is no longer skipped.

### Safety

- Grace can advance a recheck by at most five minutes and prevents a six-hour slip.
- No permission, campaign/project state, commission decision or external Ads state changes.
- No schema migration is required.

## 0.2.36 — Temporary Terms Failure Auto-Retry

### Added

- Temporary collection failures use a distinct `RETRY_REQUIRED` research state.
- Failed official-page access retries after six hours; stable results retain the 24-hour cadence.
- Runtime reports retry-pending programs and computes the next ETA from the state-specific interval.
- Operations Inbox classifies retries as system warnings that do not require user action.

### Safety

- A retry keeps permissions `NOT_CHECKED`/unchanged and never excludes or stops a campaign/project.
- `MANUAL_INPUT_REQUIRED` is reserved for a clear no-evidence result, not a network failure.
- Commission facts remain separate; no pending human decision is auto-resolved.

## 0.2.35 — Scheduled Terms Refresh ETA

### Added

- Runtime distinguishes the 24-hour eligibility time from the actual scheduled recheck.
- The next expected Terms attempt is aligned to the six-hour maintenance cadence.
- Command Center shows both timestamps so an overdue/due window is not mistaken for execution time.

### Safety

- ETA calculation is read-only and uses existing maintenance/research timestamps.
- The collector, permissions, campaign inclusion and commission review states are unchanged.
- No schema migration or external write is introduced.

## 0.2.34 — Terms Refresh Schedule Visibility

### Added

- Runtime reports how many programs are currently due for a Terms recheck.
- Runtime exposes the earliest next Terms refresh time across all programs.
- Command Center shows both values next to Terms freshness and verification state.

### Safety

- The schedule is computed read-only from existing research attempts; no migration is required.
- A due Terms check remains a warning and never changes PPC permissions or campaign inclusion.
- Commission facts remain separate and pending human decisions are not auto-resolved.

## 0.2.33 — Unmapped Google Ads Context Recovery

### Added

- Successful Google Ads CSV results with `unmapped_rows > 0` are re-analyzed each cycle.
- A stored `program_domain` can create the campaign-program mapping after that program appears.
- Runtime and Command Center expose retries caused by unresolved campaign mappings.

### Safety

- Existing spend and daily stats remain canonical and are not duplicated during retry.
- Manual mappings are still preserved and automatic mapping does not change PPC permissions.
- Fully mapped successful files remain checksum-cached and idempotent.

## 0.2.32 — Failed Commission CSV Auto-Recovery

### Added

- Unchanged commission CSV files previously marked `ERROR` or `MAPPING_REQUIRED` are re-analyzed.
- A report can recover automatically after its matching affiliate program is created.
- Runtime and Command Center expose retry counts for errors and missing mappings separately.

### Safety

- Successfully imported commission checksums remain cached and idempotent.
- Conflicts/errors never overwrite existing transactions and remain in Operations Inbox.
- Commission recovery never mutates PPC permissions, campaigns or Google Ads state.

## 0.2.31 — Failed Google Ads CSV Auto-Recovery

### Added

- Unchanged Google Ads CSV files previously marked `ERROR` are re-analyzed each maintenance cycle.
- A file can recover automatically after Customer ID or other database context becomes available.
- Sync metadata and Command Center expose how many failed files were retried.

### Safety

- Successfully imported checksums remain cached and idempotent.
- A repeated failure does not mutate existing campaign/spend data and stays in Operations Inbox.
- Recovery does not change PPC permissions, campaign inclusion or Google Ads remote state.

## 0.2.30 — Actionable Terms Exception Drilldown

### Added

- `TERMS_SOURCE_REQUIRED` Inbox items include the latest collector error and stored-source priority count.
- The item links to the best available official/stored URL when one exists.
- Opening a program-related Inbox item now loads evidence, commission facts and Terms attempt history together.

### Safety

- Error text is bounded and comes only from the existing sanitized collector audit payload.
- The item remains an operator warning; projects/campaigns stay included and permissions stay unchanged.
- No schema migration or Google Ads write is introduced.

## 0.2.29 — Terms Attempt Visibility

### Added

- A read-only program API exposes recent Terms collection attempts from the audit trail.
- Terms Evidence UI shows attempt time, state, collected/prioritized URLs, errors and duplicate heartbeats.
- The immediate domain research result now renders sanitized collection errors instead of hiding them.

### Safety

- History is program-scoped, bounded and read-only; unrelated program audits are not returned.
- Every row visibly reports whether permissions changed; normal automation rows show `PPC KHÔNG ĐỔI`.
- No schema migration, permission mutation, campaign exclusion or Google Ads write is introduced.

## 0.2.28 — Manual Attempt Audit Trail

### Added

- Every live `MANUAL_INPUT_REQUIRED` attempt now writes an audit event, including duplicate heartbeats.
- The audit records the domain, run time, collected URLs, prioritized stored URLs and collection errors.
- Pictory live-failure coverage verifies both stored official URLs are present in the audit trail.

### Safety

- Each audit explicitly records `permissions_changed=false`.
- No schema migration, permission mutation, campaign exclusion or Google Ads write is introduced.
- Existing research rows remain deduplicated while each actual attempt stays traceable.

## 0.2.27 — Fixture Seed-Only Live Recheck

### Added

- A fixture version is imported only when no matching seed research run exists.
- After seeding, Pictory uses the live same-domain collector and stored source priority queue.
- Live failure creates a real `MANUAL_INPUT_REQUIRED` attempt instead of refreshing the static fixture heartbeat.

### Safety

- Initial Pictory facts remain deterministic, sourced, proposed and separate from permissions.
- Live recheck never changes canonical permission or excludes a campaign/project.
- Fixture upgrades can still seed once under a new explicit fixture version.

## 0.2.26 — Stored Source Revalidation

### Added

- Existing accepted/proposed Terms and commission URLs are prioritized before guessed standard paths.
- Stored URLs still pass same-domain HTTPS, public-IP, redirect, port and size safety checks.
- The latest permission proposals are compared with the accepted scopes required for `TERMS_OK`.
- A commission-only successful scan can no longer hide lost paid-search/non-brand or brand sources.

### Safety

- Revalidated evidence remains proposal/review governed and never opens permission automatically.
- Missing sources only downgrade the warning classification; canonical permissions and project/campaign inclusion stay unchanged.
- Rejected sources are not automatically revisited.

## 0.2.25 — Terms Freshness vs Verification Clarity

### Added

- Runtime API exposes separate `programs_terms_ok` and `programs_terms_warnings` counts.
- Command Center labels recent automation checks as “Lần rà Terms còn mới”.
- A separate card reports “Terms đã xác minh” from the same evidence-backed gate used elsewhere.

### Safety

- A recent research heartbeat is never presented as verified PPC permission.
- Counts are read-only; evidence, permission, campaigns, projects and Google Ads are unchanged.
- Existing API fields remain available for compatibility.

## 0.2.24 — Consistent Terms Attempt Ordering

### Added

- One shared selector ranks research runs by `max(checked_at, updated_at)` and then stable row ID.
- Maintenance refresh scheduling, Runtime freshness, Operations Inbox and the Terms source-loss gate use the same selector.
- A recent unchanged-result heartbeat can no longer be hidden by another run with a newer source date but older actual attempt.

### Safety

- No database migration or canonical data mutation is required.
- Refresh cadence stays 24 hours from the true latest attempt.
- Terms remain warning-only; campaign/project inclusion and Google Ads settings are unchanged.

## 0.2.23 — Latest Terms Source Loss Guard

### Added

- The latest Terms research attempt is compared with the latest accepted-evidence/review event.
- A newer `MANUAL_INPUT_REQUIRED` attempt removes `TERMS_OK` and returns `WARNING_TERMS_UNVERIFIED`.
- Repeated identical scans use their `updated_at` heartbeat, so a newly lost source cannot hide behind an older `checked_at`.
- Programs, dashboard, compliance, exposure and Operations Inbox use the same classification.

### Safety

- No canonical permission, evidence row, campaign, project or Google Ads setting is mutated.
- Campaigns/projects remain included and the downgrade is warning-only.
- Stronger prohibited/conflict/approval warnings keep their existing priority.
- A later successful research attempt or intentional human review can restore the evidence-backed state.

## 0.2.22 — Official Terms Change Conflict Guard

### Added

- Fresh authoritative permission proposals are compared with accepted evidence by scope.
- A contradictory proposal immediately changes the warning classification to `WARNING_TERMS_CONFLICT`.
- Multiple contradictory unreviewed official proposals also produce a conflict warning.
- Permission extraction is sentence-scoped to prevent unrelated clauses from contaminating a decision.

### Safety

- Proposed evidence never mutates canonical permission fields.
- Campaigns and projects remain included; the result is a warning, not an exclusion or stop action.
- Rejecting an incorrect proposal restores the status derived from accepted evidence.
- Low-confidence, unknown-source, rejected and stale proposals cannot create this conflict guard.
- A direct-link prohibition cannot be inferred as a blanket paid-search prohibition.

## 0.2.21 — Campaign Auto-map Runtime Visibility

### Added

- Runtime API fields for the latest campaign auto-map total, scanned, mapped, unresolved and preserved counts.
- Command Center card showing new automatic mappings, unresolved campaigns and preserved mappings.

### Safety

- Visibility is read-only and derived from the latest maintenance report.
- Zero-value defaults keep older maintenance history and API consumers compatible.
- No mapping, PPC permission, campaign state or Google Ads setting is changed by this update.

## 0.2.20 — Historical Campaign Mapping Backfill

### Added

- Every maintenance cycle safely rechecks stored campaigns that still have no program mapping.
- Exact unique-domain matches are linked even when the downloaded report file has not changed.
- Maintenance report records total, unlinked scanned, mapped, unresolved and preserved counts.
- Audit record for every automatic backfill mapping.

### Safety

- Existing mappings are always preserved, regardless of their source.
- Ambiguous domains and substring matches remain unlinked for review.
- No PPC permission, campaign state, Google Ads setting or project-inclusion field is changed.

## 0.2.19 — Safe Campaign Domain Auto-mapping

### Added

- Automatic program mapping when a new or unlinked campaign name contains exactly one known merchant domain.
- Auto-map count in CSV preview, folder import result, Google Ads API result and sync metadata.
- Strict domain boundaries so `notfliki.ai` cannot match `fliki.ai`.

### Safety

- Domains with multiple programs remain unmapped for human review.
- Campaign-name inference never overwrites an existing manual or different mapping.
- Mapping affects analytics only: PPC permissions stay `NOT_CHECKED`, campaign inclusion stays enabled and the launch gate stays warning-only.

## 0.2.18 — Google Ads Resilience & Action Routing

### Added

- Up to three attempts for transient network, HTTP 429 and HTTP 5xx failures.
- Short deterministic 1s/2s exponential backoff for read-only token/report POSTs.
- Sanitized API failure `SyncRun` with `AUTH_FAILED`, `RATE_LIMITED` or `ERROR` status.
- Operations Inbox routing: auth failure requests login; transient failures are warning-only.

### Safety

- HTTP error bodies, credentials and request headers are never copied into error logs or SyncRun.
- OAuth invalid-grant HTTP 400 is treated as an auth action; permanent failures are not retried.
- Rate-limit/network warnings do not require the user and retry automatically next cycle.
- CSV fallback, stored campaign data, project inclusion and PPC permissions remain unchanged on failure.

## 0.2.17 — Automatic Google Ads SELECT-only Sync

### Added

- Google Ads API v25 `SearchStream` campaign/day metrics for the trailing seven completed days.
- Fixed GAQL fields for customer, campaign, date, cost, impressions, clicks and conversions.
- Pre-commit reconciliation against the canonical CSV-backed campaign/day row.
- Six-hour maintenance order: CSV fallback first, Google Ads API second, commission import third.
- Runtime visibility for API rows, writes and pre-commit differences.

### Safety

- The connector can construct only the fixed `SELECT` report query and a fixed `searchStream` URL.
- Customer IDs, date range, response size, response customer and every numeric field are validated.
- OAuth/Developer secrets remain memory-only and errors are sanitized.
- API updates the existing canonical Google Ads row instead of double-counting CSV and API spend.
- Fresh API data suppresses stale/broken CSV fallback actions; missing credentials perform no network call.
- PPC permissions and campaign inclusion remain warning-only and unchanged.

## 0.2.16 — Secure Google Ads OAuth Setup

### Added

- One-click `SETUP-GOOGLE-ADS-READ-ONLY.command` for a single local operator.
- Desktop OAuth JSON validation, loopback callback on random `127.0.0.1` port and PKCE S256.
- Direct macOS Keychain storage for Developer Token, OAuth client ID/secret and refresh token.
- Separate fake end-to-end loopback test that never contacts Google or a real Ads account.

### Safety

- Secret values never enter command arguments, database, API, UI or logs.
- OAuth state is validated and the consent flow explicitly requests offline access.
- The connector remains `READ_ONLY_REPORTING`; this update contains no campaign, bid, budget or status mutation.
- Partial setup is reported as missing credentials while automatic CSV ingest continues normally.

## 0.2.15 — Google Ads Read-only Readiness

### Added

- Google Ads API readiness endpoint and 24/7 Command Center card.
- Normalized detection of the stored 10-digit customer ID.
- Presence-only checks for Developer Token, OAuth client ID/secret and refresh token in macOS Keychain.
- Explicit CSV fallback and API Center setup link.

### Safety

- Credential values never enter the API response, UI, logs or process arguments.
- Unknown Keychain labels are rejected before any subprocess call.
- API mode is fixed to `READ_ONLY_REPORTING`; write operations are always disabled.
- Missing API access never degrades the healthy CSV ingest or changes campaigns.

## 0.2.14 — Terms Recheck Heartbeat

### Fixed

- Unchanged Terms research now records a separate automation recheck heartbeat.
- The original evidence/source `checked_at` remains unchanged and auditable.
- Maintenance and runtime freshness use the latest source check or recheck heartbeat.
- Duplicate content waits another full 24 hours instead of being retried every six hours.

### Safety

- No new evidence, commission fact or research run is created for unchanged content.
- Canonical PPC permissions and campaign state remain untouched.
- Pictory keeps its original fixture evidence date, commission `CONFLICT` and PPC `NOT_CHECKED`.

## 0.2.13 — Automatic Affiliate Commission Ingest

### Added

- Six-hour discovery of stable CSV files whose names explicitly contain commission or hoa hồng.
- Unique program matching from the merchant name/domain in the filename or a `program_domain` / `merchant` column.
- Stable per-domain source namespace, SHA-256 cache and existing transaction/state idempotency.
- Commission folder status in the 24/7 card plus Operations Inbox actions for mapping and file errors.

### Safety

- Generic, ambiguous, malformed or conflicting reports are never auto-committed.
- Only the newest numbered export in each filename family is considered; symlinks and oversized files are ignored.
- Imported rows use the existing reconciliation ledger; PPC permissions and campaign state are never changed.
- No affiliate report is currently present in production Downloads, so enabling the scanner changes no revenue data.

## 0.2.12 — Google Ads Data Freshness

### Added

- The 24/7 card shows the latest metric date contained in the confirmed Google Ads report.
- A report becomes stale only when its latest metric date is older than yesterday.
- Stale data creates one actionable Operations Inbox item with the exact Google Ads export path.

### Safety

- Freshness is derived from parsed daily rows, not the file modification time.
- A stale report never removes, pauses or changes any campaign, budget, bid or PPC permission.
- Unchanged-file caching is upgraded once to retain the confirmed report date and remains idempotent.

## 0.2.11 — Runtime Accuracy & Single Bootstrap

### Fixed

- The 24/7 card keeps showing the report's confirmed row count when a later scan skips the unchanged SHA-256.
- Maintenance is no longer explicitly kickstarted after a `RunAtLoad` bootstrap, preventing duplicate cycles during install/update.

### Safety

- Server still receives an explicit kickstart and remains auto-restarting.
- Maintenance still runs once immediately via `RunAtLoad`, then every six hours.
- Google Ads import idempotency, warning-only Terms behavior and all stored data remain unchanged.

## 0.2.10 — Automatic Google Ads Report Ingest

### Added

- Six-hour discovery of the newest stable Google Ads campaign CSV in `~/Downloads`.
- Unicode-safe Vietnamese filename matching and newest-file selection across numbered exports.
- Content-hash skip for unchanged reports plus existing campaign/day/source idempotency.
- Existing campaign-to-program mappings count as mapped and are never removed by folder imports.
- Google Ads folder status in the 24/7 Command Center card.
- Operations Inbox items for unreadable reports and newly imported campaigns without a program.

### Safety

- Only small, regular, non-symlink CSV files with allowlisted report-name patterns are read.
- A report with any row/header error is not auto-committed.
- Import changes only the local analytics ledger; it never calls Google Ads or changes campaign state/bids/budget.
- Terms and PPC permissions are not touched; warnings never exclude projects.

## 0.2.9 — In-app Runtime Status

### Added

- Command Center card for macOS server and maintenance service state.
- Latest maintenance result, expected next run, latest scheduled backup and next backup due time.
- Per-program 24-hour Terms freshness count without changing review or permission state.
- Clear `HEALTHY / STARTING / ATTENTION / NOT_CONFIGURED` operator language.

### Safety

- Runtime status is read-only and executes only fixed allowlisted `launchctl print` checks.
- Maintenance errors are visible but never stop or exclude campaigns/projects.
- Updater inherits 24/7-aware pause/restart and rollback handling from 0.2.8.

## 0.2.8 — Safe 24/7 Operations

### Added

- Two user-level macOS services: an auto-restarting AFI-OS server and a six-hour maintenance cycle.
- Daily scheduled SQLite backup and 24-hour stale Terms refresh.
- Maintenance lock, per-domain error isolation, finance normalization and Operations Inbox refresh summary.
- One-click enable, status and disable commands.

### Safety

- Maintenance collection remains proposal-only and records `permissions_changed=false`.
- Campaigns and projects remain included; warnings never stop or exclude them.
- Update/rollback logic detects loaded 24/7 services, pauses them before mutation and restores the prior service state when supported.
- A restored version without 24/7 support stays safely stopped; data and backups are never deleted.

## 0.2.7 — Exception-driven Operations Inbox

### Added

- One Command Center queue for proposed Terms Evidence, commission facts, FX rates, reconciliation issues and missing Terms/FX sources.
- Informational campaign terms warnings that explicitly state campaigns remain included and running.
- Severity, source link, program context and direct navigation to the correct review screen.
- Automatic inbox refresh after evidence, commission, FX, reconciliation and campaign-warning actions.

### Safety

- The inbox is a derived read model; it does not mutate canonical permissions or campaign state.
- Campaign warnings use `requires_user=false` and never become an exclusion gate.
- Only the latest research run per domain can request manual Terms input.
- Resolved/rejected/accepted items leave the queue deterministically.

### Production data result

- Current inbox derives four items: two Pictory conflict facts, one Fliki commission proposal and one non-blocking Fliki campaign warning.
- Exactly three items require a user decision; the campaign warning remains informational.

## 0.2.6 — Commission Fact Review Queue

### Added

- Accept/reject controls beside every proposed commission fact.
- Source authority, confidence, future-date and merchant-domain checks before acceptance.
- Persistent audit entries for commission review decisions.
- Immediate commission resolution state after each review.

### Safety

- Commission review always returns `permissions_changed=false` and never reconciles PPC fields.
- Conflicting qualified claims remain `CONFLICT` until the competing claim is rejected.
- Low-confidence, non-authoritative or off-domain official facts cannot be accepted.
- Rejection is always available so bad proposals can leave the active queue.

## 0.2.5 — Generic Official Terms Collection

### Added

- Domain research beyond the Pictory fixture using a bounded same-domain HTTPS collector.
- Official-page discovery from homepage links plus a small affiliate/partner/terms path set.
- Deterministic PPC, brand bidding, non-brand, direct-link and trademark-ad-copy proposal extraction.
- Commission percentage/cadence extraction kept in separate `CommissionFact` records.
- Source URL, exact excerpt, checked time, confidence, scope and collector identity on every proposal.
- Visible imported/duplicate evidence counts in the Terms Evidence screen.

### Safety

- Private/non-public IP addresses, credentials, non-HTTPS URLs, non-standard ports and redirects outside the merchant domain are rejected.
- Each page is limited to 1 MB; at most eight pages are fetched with short timeouts.
- Automation creates only `PROPOSED` evidence and never changes canonical permission fields.
- Duplicate page redirects, evidence and commission facts are collapsed deterministically.
- Missing explicit PPC text remains `MANUAL_INPUT_REQUIRED / NOT_CHECKED`, which is a warning and never excludes the project.

### Verified

- Fliki public discovery finds the official affiliate-program and terms pages.
- One sourced 30% lifetime-recurring commission proposal is extracted on a data copy.
- No public explicit PPC/brand/direct-link permission was extracted, so all Fliki permissions remain `NOT_CHECKED`.

## 0.2.4 — Currency Normalization & Reconciliation

### Added

- Finance settings with VND as the default reporting currency and configurable maximum FX age.
- Sourced FX proposal ledger with URL, checked date, confidence and `PROPOSED / ACCEPTED / REJECTED` lifecycle.
- Direct and inverse FX lookup using only accepted rates; original amounts and currencies are preserved.
- Normalized spend, commission and actual net-cash summary with missing-rate coverage.
- Persistent reconciliation queue for `ATTRIBUTED / PARTIAL / UNATTRIBUTED / DUPLICATE / CONFLICT`.
- Operator resolution notes and audit timestamps for open reconciliation exceptions.
- Finance & Reconciliation UI for settings, rate review, coverage and exception handling.

### Safety

- Confidence below `0.8` cannot be accepted for normalization.
- Conflicting accepted rates for the same pair/date are rejected.
- Duplicate or conflicting commission IDs do not overwrite stored transaction facts.
- Existing VND spend/commission rows are normalized 1:1 during migration.
- Existing data, warning-only terms behavior and the Pictory fixture are preserved.

## 0.2.3 — Direct Vietnamese Google Ads CSV Import

### Added

- Direct parsing of Google Ads campaign reports in Vietnamese or English.
- Automatic header discovery after Google Ads report title/date preamble rows.
- Vietnamese aliases for campaign ID, date, status, type, currency, cost and traffic metrics.
- Canonical mapping of `Đang bật` to `ENABLED` and `Tìm kiếm` to `SEARCH`.
- Automatic reuse of the only known Customer ID in the Risk & Exposure form.

### Fixed

- Google Ads “Tổng số” rows are ignored instead of being treated as campaigns or repeated spend.
- Google Ads CSV source labels are treated as one idempotency family, preventing duplicates when
  `GOOGLE_ADS_CSV` and `GOOGLE_ADS_CSV_VI` refer to the same campaign/day.
- Vietnamese `đ/Đ` is normalized correctly in CSV headers and state values.

### Preserved

- Existing accounts, campaign IDs, spend, metrics, program mappings and risk acknowledgements.
- Warning-only terms behavior: projects remain included even when evidence is missing or prohibited.
- Pictory commission conflict and `NOT_CHECKED` PPC permissions.

## 0.1.0 — 2026-08-10

### Added

- FastAPI local application.
- SQLite production schema and initial Alembic migration.
- Ad Intelligence & Advertiser Graph vertical slice.
- Manual Ads Transparency capture API and Chrome helper.
- Compliance gate with evidence-first blocking.
- Economics engine for one-time and recurring commissions.
- Commission finance summary that excludes pending from recognized/cash revenue.
- Modern dashboard shell.
- Automated tests and security baseline.

### Preserved

- Legacy v3 dashboard and generator under `legacy/v3/`.

### Not yet implemented

- Google Ads production connector.
- Affiliate network production connector.
- GCLID/SubID end-to-end attribution.
- Full terms registry UI.
- Backup/restore automation.

## 0.1.1 — Course baseline economics

- Restored the AFI course baseline as the default: 150 ad clicks per approved sale model input.
- Kept the production funnel model (outbound CTR × merchant CVR) as an alternate mode.
- Added explicit Total CVR and effective Clicks/Order outputs.
- Added a regression test for the 150-click baseline.


## 0.2.0 — Evidence, Commission Ledger & Backup

### Added

- Persistent Program Registry and Terms Evidence Center.
- Evidence freshness/confidence checks and separate `BRAND_READY` / `NON_BRAND_READY` gates.
- Flexible commission CSV preview/import with header aliases, delimiter detection and UTF-8 BOM support.
- Idempotent imports plus state updates for existing transactions.
- SubID/GCLID matching when click records exist; unmatched rows are explicit `UNATTRIBUTED`.
- Finance summaries separating pending forecast, recognized revenue, cash received and reversals.
- One-click SQLite backup with checksum/integrity verification.
- Restore-latest command with an emergency pre-restore backup.
- Sprint 1 UI tabs for Terms Evidence, Commission Ledger and Backup & Restore.

### Still blocked by owner access

- Google Ads read-only OAuth/Developer Token.
- First production affiliate-network connector.
- End-to-end live click → SubID → commission reconciliation.

## 0.2.2 — Warning-only Terms Risk & Campaign Exposure

### Added

- Google Ads campaign CSV preview/import with daily spend, impressions, clicks and conversions.
- Idempotent campaign/day updates, account and campaign upsert, and optional campaign → program mapping.
- `CampaignProgramLink` and `CampaignDailyStat` as additive migration tables.
- Risk & Exposure screen separating total spend, spend at terms risk, recognized revenue, cash received and actual net cash.
- Operator risk acknowledgement that records awareness without changing permissions.

### Changed

- Terms results are now `TERMS_OK` or explicit `WARNING_*` states.
- Projects and campaigns are always retained in Radar, Economics and tracking regardless of terms status.
- `CONFLICT`, `PROHIBITED` and missing evidence remain visible warnings; they no longer exclude a project.
- There is still no automatic launch, bid change, budget change or scale action.

### Preserved

- Existing 0.2.0/0.2.1 data, Pictory fixture, accepted/proposed evidence and commission facts.
- Pictory permissions remain `NOT_CHECKED`; its official commission claims remain `CONFLICT`.
- Commission facts remain separate from PPC permission evidence.

## 0.2.1 — Terms Evidence automation safety update

### Added

- Domain → sourced proposal workflow with deterministic, idempotent fixture imports.
- Explicit evidence review lifecycle: `PROPOSED / ACCEPTED / REJECTED`.
- `CONFLICT` resolution that takes precedence over any allowing evidence.
- Separate `CommissionFact` records with URL, excerpt, checked date, confidence and scope.
- Pictory fixture: 40% one-time first-payment claim versus up-to-50% recurring claim.
- Transactional updater with SQLite WAL checkpoint, integrity/checksum verification, code snapshot, automatic rollback and manual rollback command.

### Fixed

- Evidence now defaults to `NOT_CHECKED` with confidence `0` in UI, API schema and model.
- Saving evidence no longer writes directly into canonical Program permissions.
- Commission facts can no longer be interpreted as PPC permission evidence.
- Dashboard readiness and Compliance Gate now derive from stored, accepted, fresh,
  authoritative, correctly scoped evidence; client-supplied permission claims are ignored.
- Reviewing one proposal preserves unrelated migrated 0.2.0 permissions and timestamps.
- Updater accepts the standard internal Python symlink when the verified Alembic launcher
  is present, while payload and target file paths remain symlink-protected.

### Safety outcome

- Pictory PPC, brand keyword, non-brand and direct-link permissions remain `NOT_CHECKED`.
- Pictory commission resolution is `CONFLICT`; PPC remains `NOT_CHECKED`.
