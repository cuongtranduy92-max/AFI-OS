# TEST REPORT — AFI-OS 0.2.109

## 0.2.109 — Progressive appraisal + truthful empty states

- Full application regression before packaging: 440 passed, 1 skipped
  (441 tests collected), including a regression test for matching a hyphenated
  stored Google Ads Customer ID to the normalized Keyword Planner account ID.
- API tests verify immediate appraisal responses with persistent job IDs, one-second
  UI polling, isolated per-source retry and stale-job recovery after ten minutes.
- Batch tests verify one Apify collection for the batch, explicit per-domain states
  when a provider is not connected and cache reuse without a second provider call.
- Terms tests verify no blind second crawl on an empty result and exactly one retry
  only for a transient network exception.
- Migration and updater round-trip tests reach `82c6d4f1a9b7`, preserve database rows,
  maintain SQLite integrity and restore version 0.2.108 on rollback.
- Static checks confirm no Google Ads mutate/write operation was introduced; LLM
  facts remain proposals and warning-only Terms behavior is unchanged.

## 0.2.108 — Camp Doctor + Vietnamese Terms

- Full application regression before packaging: 436 passed, 1 skipped
  (437 tests collected).
- Camp Doctor unit/API tests cover learning protection, low CTR with competitors,
  click-fraud warning, real cost/ref bands, low-data protection, search-term waste
  and the 20%/24-hour rule.
- Static and request-contract tests confirm all new Google Ads queries use read-only
  searchStream reports and add no mutate/write endpoint.
- Vietnamese extraction tests prove original fake quotes are rejected, translations
  cannot rescue fabricated facts, missing PPC uses the exact support warning and
  Step 2 remains exactly 15/4/4/4 English assets.
- Migration upgrade/downgrade/re-upgrade reached `71e4a2b890c3`, kept SQLite
  integrity `ok`, zero foreign-key errors and nullable translation fields.
- Release checksum covers all 49 payload files. Production-copy update/rollback
  and live post-install checks are mandatory gates before this release is handed off.

## 0.2.107 — Claude Terms extraction

- Full application regression before packaging: 412 passed, 1 skipped
  (413 tests collected).
- Focused tests verify quote anti-fabrication, 15,000-character page bounds,
  upper-bound exclusion, exact Anthropic HTTP/model configuration, Keychain
  argument secrecy and unchanged-content cache.
- Human-review tests prove proposal data cannot affect payback or PPC before accept;
  accepted package/payment/commission data is then reflected in Step 1.
- SQLite migration round-trip preserves existing merchant/program data and adds
  content-addressed extraction runs plus package/payment proposal review records.
- Checksum validation passed for all 39 payload files. A production-data copy
  update `0.2.106 → 0.2.107` and rollback `0.2.107 → 0.2.106` preserved nine
  Projects, three Programs, five commission facts and six Terms evidence rows;
  SQLite integrity stayed `ok` with zero foreign-key errors.
- Live update completed with rollback point
  `update-0.2.107-20260813-124701`; API health reports `0.2.107`, runtime is
  `HEALTHY`, both LaunchAgents are loaded and Google Ads API remains read-only.
- Live database retains nine Projects, three Programs, five commission facts and
  six Terms evidence rows on schema `4f7c2a91d5e0`; SQLite integrity is `ok`
  with zero foreign-key errors. Scheduled maintenance completed `SUCCESS`.
- Browser QA verified the Claude action, faded proposal presentation, exact
  source excerpts, accept/reject controls and zero console warnings/errors.
- Post-install backup `manual-20260813-125225` is `OK` on version `0.2.107`,
  schema `4f7c2a91d5e0`, SHA-256
  `8aa5d0be2de7bd97158d7ea5f191cb0462cef7a151461fe2ebb8ed865bd59c6e`.
- Anthropic readiness is `CONNECTION_REQUIRED` until the operator stores one API
  key through `SETUP-LLM.command`; no key is stored in the repo, environment or
  database.

## 0.2.106 — Tài nguyên

- Full application regression before packaging: 400 passed, 1 skipped.
- Engine boundary tests cover 29-day maturity, device-change penalties, 48-hour
  SOAK, dirty email rejection, all seven alert families and at most three tasks/day.
- API tests cover email/account/resource CRUD, secret-field rejection, daily task
  persistence, PayPal $5,200 error and manual/database campaign plans.
- Step 2 tests prove only mature clean free accounts are selectable, internal deploy
  records one current Project plus history, and reuse by another Project is rejected.
- SQLite migration upgrade/downgrade/upgrade retains the existing Ads account,
  integrity and migration head `e91f4d7a2c18`.
- Release package checksum validation plus update/rollback on a production-data copy
  preserve nine Projects, three Programs and restore the exact prior schema.
- Live update completed with rollback point `update-0.2.106-20260813-111257`.
  API health reports `0.2.106`, runtime is `HEALTHY`, maintenance is `SUCCESS`,
  both LaunchAgents are loaded and Google Ads API remains read-only.
- Live database retains nine Projects, three Programs and the existing Google Ads
  account; integrity is `ok`, foreign keys have no errors and schema is `e91f4d7a2c18`.
- Browser QA opened tab Tài nguyên, verified all four KPIs, alerts, forms, fixed
  password-manager note and zero console errors. Post-install backup
  `manual-20260813-111453` is `OK` on schema `e91f4d7a2c18`.

## 0.2.105 — Apify traffic automation

- Full application regression: 393 passed, 1 skipped.
- Apify parser regression verifies latest valid month, sorted top-five countries,
  `confidence=0.75`, exact actor ID and absence of tokens from stored/source data.
- Junk/missing domains return `NO_DATA`, never zero; traffic and country snapshots
  remain separate, source-aware and valid for 45 days.
- Cache regression proves a second check inside 45 days does not read the credential
  or call Apify; stale data after day 45 triggers a fresh collection.
- Ten-domain batch regression proves one actor invocation and isolated per-domain
  failures; the UI/API accept up to 50 deduplicated domains.
- Application/new release-builder Ruff checks, JavaScript syntax, shell syntax and
  whitespace checks passed; the inherited standard-library updater passed its own tests.
- All 25 payload checksums passed. A production-data copy update `0.2.104 → 0.2.105`
  and rollback `0.2.105 → 0.2.104` both preserved 8 Projects and 3 Programs,
  SQLite integrity `ok`, zero foreign-key errors and migration head `b84d0e26c104`.
- Live update completed with rollback point
  `update-0.2.105-20260813-100236`. API health reports `0.2.105`, runtime is
  `HEALTHY`, the latest maintenance result is `SUCCESS`, and both LaunchAgents
  are loaded.
- Live data remained intact: 8 Projects, 3 Programs, SQLite integrity `ok`, zero
  foreign-key errors and migration head `b84d0e26c104`. Google Ads remains
  read-only and its latest sync is `SUCCESS`; Terms remain warning-only.
- Post-update manual backup `manual-20260813-100353` is `OK`, schema head
  `b84d0e26c104`, SHA-256
  `cd923a6fe23d135a83b70fd171291d74aa59f3aa979f1410bb6817c177e48c22`.
- Live traffic readiness returns `CONNECTION_REQUIRED` without exposing a secret.
  Real-domain acceptance remains pending only until the operator stores an Apify
  token through `SETUP-TRAFFIC-DATA.command`.

## 0.2.104 — Dot3 Step 2 campaign content builder

- Focused API/UI regression verifies exact 15/4/4/4 counts, limits, required domain
  placement, ref-linked sitelinks and public Step 2 controls.
- Edited `Free Best Fliki` is rejected on the exact headline row; deploy returns 409
  until the saved draft is re-linted cleanly.
- A non-PASS Project returns 409; clean deploy writes `DEPLOYED` plus AuditLog and
  records `google_ads_write=false`.
- Full application regression: 382 collected, 381 passed, 1 skipped.
- Touched-file Ruff checks, JavaScript syntax and whitespace checks: passed.
- Checksum verification passed for all 33 payload files.
- Temporary production-data copy update `0.2.103 → 0.2.104` and rollback
  `0.2.104 → 0.2.103` passed. Both directions kept 8 Projects and 3 Programs,
  SQLite integrity `ok`, zero foreign-key errors and exact migration heads
  `b84d0e26c104/a73c9e15b642`.
- Live postchecks are required immediately after installation.

## 0.2.103 — Dot2 payback and scoring

- Full application regression: 373 passed, 1 skipped.
- Sheet fixture `L=11,000 VND`, `M=49,000 VND`, `$111.70`, `30%`, FX `26,000`
  returns `170.4 / 126.5` days.
- `/api/appraise` returns deterministic score total/pass/flags and keeps prohibited
  Google Ads plus brand restrictions warning-only.
- Package verification and temporary-target update/rollback preserve database row
  counts, SQLite integrity, foreign keys and migration head.

## 0.2.102 — Commission truth hotfix

- Full application regression: 363 passed, 1 skipped.
- Pictory accepted `up to 50%` recurring fact is visible in the contract with a
  warning; payback remains null because a maximum is not a guaranteed rate.
- Package prices map to `commission.packages`; commission percentages are not
  mislabeled as prices.
- Temporary-target update `0.2.101 → 0.2.102` and rollback
  `0.2.102 → 0.2.101` passed with exact table-row preservation, SQLite integrity
  `ok`, zero foreign-key errors and verified backup manifests.
- Live update created verified rollback point `update-0.2.102-20260813-043515`,
  preserved all existing rows and returned health version `0.2.102`; both LaunchAgents
  remain loaded and the latest maintenance result is `SUCCESS`.
- Live Pictory API/UI QA rendered `50% · recurring`, the maximum-rate warning and a
  disabled Step 2 save while score inputs remain incomplete. No maximum rate was used
  to calculate payback.
- Post-update manual backup `manual-20260813-043757` is `OK`, schema head
  `a73c9e15b642`, SHA-256
  `b988b2b2d0e7a1d6e0f00e12e4a71491f2d69b7bb93883b03c2d9b63c315388e`.

## 0.2.101 — Dot1.1 appraisal and backup hardening

- Application regression: 363 collected, 362 passed, 1 skipped.
- Appraisal contract regression verifies the exact top-level structure, truthful null
  values, `source_status=pending`, score aliasing and invalid-domain rejection.
- Backup regression rejects absent, empty and wrong-schema databases, removes partial
  output and verifies explicit command/Operations Inbox failure reporting.
- UI contract verifies domain and batch intake, ten appraisal cards, pending-source
  copy, verdict/score and guarded Step 2 transition.
- Touched-file Ruff checks and `node --check apps/web/app.js`: passed.
- Package verification: 33 payload files with individual SHA-256 checksums.
- Temporary-target update `0.2.100 → 0.2.101` and rollback
  `0.2.101 → 0.2.100` passed; all table row counts were preserved, SQLite integrity
  was `ok`, foreign-key errors were 0 and migration head stayed `a73c9e15b642`.
- Live update created a verified rollback point, preserved 8 Projects and returned
  health version `0.2.101`; server and maintenance LaunchAgents are loaded and the
  latest maintenance result is `SUCCESS`.
- Live `POST /api/appraise` returned the exact 11-key contract for Pictory with
  missing providers as null/pending and PPC as warning-only. Browser QA rendered all
  10 cards, batch input, guarded Step 2 button and no console errors.
- Post-update manual backup `manual-20260813-041915` is `OK`, schema head
  `a73c9e15b642`, SHA-256
  `82d96ccadfbf6e0bf33908a4561fb22c3168357d8fdd902a90d7d3dfadd41c9e`.

## 0.2.100 — One-domain automatic Project Check

- Focused auto-check, Step 1, UI safety and updater regression: 18 passed.
- Similarweb/Semrush parser regression verifies exact domain source lineage and secret removal.
- Missing-provider regression verifies `CONNECTION_REQUIRED` and no fabricated snapshot.
- Source-card regression verifies every unavailable group is named instead of rendered blank.
- Automatic snapshot regression verifies source/date/confidence, exact deduplication and no write.
- Touched-file Ruff lint and format checks passed.
- Release updater, checksum, temporary-target update/rollback and live postchecks are required
  before deployment.

## 0.2.99 — Traffic fallback and Google Ads Keychain Terminal hotfix

- Traffic API regression covers source URL validation, immediate Step 1 visibility,
  exact duplicate suppression, audit and no Google Ads write.
- UI/JavaScript contract covers manual entry plus CSV columns and refreshed static
  asset versions.
- Updater regression proves LaunchAgents are considered only when their plist points
  to the selected target directory.
- Application regression: 349 collected, 348 passed, 1 skipped.
- Package verification: 22 payload files with SHA-256 checksums.
- Temporary-target update `0.2.98 → 0.2.99` and rollback `0.2.99 → 0.2.98` passed;
  SQLite integrity was `ok`, foreign-key errors were 0 and the live LaunchAgent stayed running.

- Focused Google Ads OAuth/setup/readiness/API suite: 40 tests passed.
- Real macOS PTY Keychain probe: store → read → delete passed without exposing the
  probe value in process arguments.
- Live credential presence check: five expected labels present; values were not read.
- Live API sync: Customer ID `123-456-7890`, status `SUCCESS`, 2 rows read and written,
  write operations disabled.
- Database integrity and foreign-key checks: `ok`; API health `ok`; server and
  maintenance LaunchAgents healthy.

## 0.2.98 — Project Check Step 1

- API regression covers complete and empty Projects, exact source/API requirements,
  accepted commission isolation, three-plan average and low/high CPC payback.
- Decision regression proves incomplete Projects cannot transition; complete Projects
  are exposed under `PREP`, with a full audit snapshot and no permission/campaign/
  Google Ads write.
- UI contract covers the Step 1 cockpit, source/API cards, disabled transition and
  Step 2 project queue.
- Application regression: 345 collected, 344 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- Touched-file lint and JavaScript syntax check: passed.

## 0.2.97 — Relationship observation dates

- Network regression verifies snapshot `checked_at` is returned as `observed_at` on
  advertiser and Project relationship records.
- JavaScript continues to render activity dates and source-observation dates as
  different concepts.
- Application regression: 341 collected, 340 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- JavaScript syntax check: passed.

## 0.2.96 — Recursive project network journey

- API regression covers one Project with multiple advertisers and one advertiser
  connected to multiple Projects, including source and reported-ad lineage.
- Missing relationship data returns `NOT_COLLECTED` with an empty list, not zero.
- UI contract starts at `Tìm dự án`, loads one complete network response and recenters
  automatically when a related Project is selected.
- Application regression: 341 collected, 340 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- JavaScript syntax check: passed.

## 0.2.95 — Project trace entry point

- UI contract verifies separate trace and saved-filter forms, inputs and actions.
- Trace submit normalizes domain, uses safe idempotent intake, then runs source research.
- Result handling focuses Portfolio on the traced domain and states that PPC is unchanged.
- Application regression: 337 collected, 336 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- JavaScript syntax check: passed.

## 0.2.94 — Domain intake

- Valid URL/domain normalization retains exactly one Project and derives its brand.
- Duplicate intake is idempotent; invalid hostnames, IPs and credentials are rejected.
- New records have no Program or Campaign, Terms are `NOT_CHECKED`, commission is
  unknown, and audit proves no permission/campaign/Google Ads mutation.
- Portfolio UI offers an explicit intake action for a domain not found in local data.
- Application regression: 334 collected, 333 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed; checksum verification: 107 payload files.
- JavaScript syntax check: passed.

## 0.2.93 — Maintenance proposal preservation

- A valid `NON_BRAND_ONLY` proposal survives repeated semantic repair runs.
- A v1-rejected, automated, unreviewed proposal is restored to `PROPOSED`.
- Old false `PROHIBITED/APPROVAL_REQUIRED` paid-search proposals remain rejected.
- Application regression: 327 collected, 326 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- JavaScript syntax and Python compile checks: passed.

## 0.2.92 — Missing-state UI consistency

- Project Radar renders missing advertiser collection as `Chưa thu thập`.
- Project Radar renders a missing activity window after advertiser collection as `Chưa đủ dữ liệu`.
- Application regression: 327 collected, 326 passed, 1 skipped.
- Safe updater/rollback regression: 11 passed.
- `node --check apps/web/app.js`: passed.

## 0.2.91 — Truthful advertiser and Snov semantics

- Full application regression: 325 passed, 1 loopback test skipped by default
  (326 collected).
- Snov Terms fixture verifies three independent proposals: paid search non-brand only,
  non-brand scope, and brand keyword approval required; canonical permissions remain
  `NOT_CHECKED` until review.
- Snov 40% plan subscription and 20% LinkedIn Automation slot facts remain separate
  proposals with program commission state `PROPOSED`, not `CONFLICT`.
- Advertiser snapshot tests verify source evidence, 2 advertisers / 75 reported ads,
  idempotent retry, stable identity, audit, and no Program/Campaign/Google Ads mutation.
- Activity-window regression keeps 30-day active advertiser value null when last-seen
  data is absent; Radar cannot score the incomplete window as zero.
- UI regression verifies `Chưa thu thập` and explicit collection state.
- JavaScript syntax, Python compileall and targeted Ruff checks: PASS.

## 0.2.90 — Program ↔ Project sync

Ngày kiểm tra: 2026-08-12

## 0.2.90 — Program ↔ Project sync

- Filter regression: tạo Snov Program rồi lọc `snov.io` trả đúng một Project.
- Terms discovery regression: Program được tạo tự động vẫn xuất hiện trong Portfolio.
- Existing-project regression: link Program không đổi stage, registration, owner hoặc next action.
- Self-heal regression: lượt đầu tạo đúng một Project, lượt sau chỉ PRESERVED và không nhân bản.

## 0.2.89 — Command Center UI hotfix

- Static UI regression xác nhận Portfolio và Operations không tham chiếu biến `job` ngoài scope.
- Automation queue giữ đúng `data-automation-job-row` để định vị job lỗi.
- Targeted UI/portfolio tests, full regression, updater/rollback suite và live browser QA được yêu cầu trước khi phát hành.

## 0.2.88 — Wake-safe 24/7

- Kiểm thử lịch calendar 00/30, plist round-trip, maintenance và runtime status.
- Full regression, updater/rollback rehearsal và live post-check ghi trong release receipt.

## 0.2.87 — Exception Queue

- Dead-letter job tạo đúng một Operations action và mở đúng hàng trong Command Center.
- Retry-wait không yêu cầu người dùng; dữ liệu campaign/program không bị thay đổi.
- Full regression, updater/rollback rehearsal và live post-check được ghi trong release receipt.

## 0.2.86 — Durable Automation Queue

- Full regression: 312 passed, 1 loopback test skipped by default (313 collected).
- Queue tests cover dedupe, recursive secret redaction, atomic concurrent claim, stale
  lease rejection, retry backoff, dead-letter, audited operator retry and expired-worker
  recovery with a hard maximum attempt count.
- Migration round trip `f21a58d9c341 → a73c9e15b642 → f21a58d9c341 →
  a73c9e15b642` preserves legacy rows and SQLite integrity/foreign keys.
- Terms maintenance regression passes through a persisted queue job while keeping all PPC
  scopes unchanged. Existing Ads import, finance, backup/restore and Portfolio regression
  remains green.
- Browser QA on a migrated production copy confirms API/UI 0.2.86, empty-worker state,
  dead-letter visibility and `Thử lại ngay → PENDING` without a remote write.
- Transactional updater suite: 11 passed. Rehearsal on a consistent live database copy
  completed `0.2.85 → 0.2.86 → rollback 0.2.85 → 0.2.86`.
- Every rehearsal point kept 2 Program, 2 Project, 10 Spend and 1 enabled Campaign;
  integrity was `ok`, foreign-key check clean, and all PPC scopes remained `NOT_CHECKED`.
  Update created only the empty queue table; rollback removed only that table.
- Live deployment receipt is appended after final post-check.

## 0.2.85 — Project Portfolio & Truth Drawer

- Full regression: toàn bộ test đạt, gồm Portfolio API/UI contract, capture identity v2,
  Terms, Google Ads import, Finance, backup/restore và maintenance.
- Migration test chạy `d8a6f4b20317 → f21a58d9c341 → d8a6f4b20317 →
  f21a58d9c341`, giữ Program/Project và SQLite integrity `ok` ở mọi điểm.
- Production-copy migration tạo đúng Pictory/Fliki Project và liên kết campaign
  `24116162130` với Fliki; không đổi permission hoặc remote campaign state.
- Browser QA xác nhận Portfolio, filter, Truth Drawer và workflow audit; Pictory 50%
  recurring có cả nguồn 40% rejected và 50% accepted trong lineage.
- Missing advertiser được trả `null/UNKNOWN/DATA_MISSING`, không phải `0`.
- CTR fixture 39% tạo `CTR_BELOW_40`; live-copy Fliki 44,13% không tạo cảnh báo đó.
- JavaScript syntax và Ruff đều đạt.
- Rehearsal trên bản sao nhất quán của database live đã chạy trọn vòng
  `0.2.84 → 0.2.85 → rollback 0.2.84 → 0.2.85`. Mỗi điểm đều có SQLite
  integrity `ok`, 2 Program, 10 Spend và 1 Campaign; migration tạo đúng 2 Project,
  rollback đưa Project về 0 rồi lần cài cuối tạo lại đúng 2.
- Rehearsal còn khóa điều kiện updater: chỉ Project backfill cộng thêm, tối đa bằng
  số Program cũ, được phép; giảm Project hoặc thay đổi row count ở bảng legacy vẫn
  bắt buộc auto-rollback.
- Live 0.2.85 post-check đạt: API `ok`, runtime `HEALTHY`, maintenance `SUCCESS`,
  LaunchAgents server/maintenance đã nạp và server đang chạy.
- Database live sau phát hành: head `f21a58d9c341`, integrity `ok`, foreign-key
  check sạch, 2 Program, 2 Project, 10 Spend và 1 Campaign. Cả bốn quyền PPC của
  Pictory/Fliki vẫn `NOT_CHECKED`; campaign Fliki vẫn `ENABLED` và được liên kết
  Project nội bộ mà không có Google Ads write.
- Backup rollback `update-0.2.85-20260812-032305` ở phase `INSTALLED`, checksum
  khớp và database backup integrity `ok` tại head cũ `d8a6f4b20317`.
- Browser QA trên live xác nhận menu Quản lý dự án, 2 Project, Pictory 50% recurring,
  Fliki CTR 44,13% / cost 297.211 VND, và thông báo “không dự án nào bị tự loại”.

## Kết quả tự động

```text
Application suite: 305 passed, 1 loopback test skipped by default
OAuth loopback integration (explicit local-port run): 1 passed
Transactional updater suite: 11 passed
Python compileall: PASS
JavaScript syntax (node --check apps/web/app.js): PASS
Chrome helper syntax (node --check tools/ads-transparency-capture/popup.js): PASS
Targeted Ruff checks for 0.2.84 application files: PASS
Shell syntax for Google Ads setup/restore/update/rollback/enable/status/disable commands: PASS
```

## Regression được khóa

- Operations action giữ `item_type` và capture `entity_id`, không làm mất target khi chuyển view.
- Capture-review action chỉ gọi GET queue/recent captures, không chứa POST hoặc tự accept/reject.
- Đúng row được scroll/highlight và focus advertiser/domain còn trống; đủ identity thì focus Chấp nhận.
- Target đã xử lý fallback sang row cũ nhất còn lại; queue trống làm mới Operations và báo rõ trạng thái.
- Backend Operations target tiếp tục khớp item đầu tiên của review queue và không tạo advertiser/project/observation/audit.
- Program, Finance và Exposure action giữ nguyên; PPC/commission/Google Ads/campaign/project không thay đổi.

- Snapshot thiếu advertiser/domain vào hàng đợi và không tạo graph trước khi được chấp nhận.
- Web capture và Chrome helper đều giữ được raw evidence thiếu cấu trúc; kết quả nói rõ `NEEDS_REVIEW` hay `PARSED`.
- ACCEPT/REJECT dùng claim nguyên tử; hai quyết định đua nhau chỉ một bên thắng và lần lặp khác nội dung trả conflict.
- Legacy `RAW` chưa materialize được hiện nhất quán ở queue, Operations và dashboard; `RAW` đã có observation không bị duyệt lại.
- Observation mặc định dùng ngày `captured_at` UTC; capture trùng trong ngày được dedupe nhưng ngày sau hoặc sau quyết định reject tạo record mới.
- Capture được chấp nhận luôn ghi `observation_id` và trạng thái created/deduplicated vào JSON + audit, không còn lineage mồ côi.
- Reviewer, lý do loại, full evidence preview và trạng thái khóa toàn hàng được kiểm thử; quyết định không mở PPC hoặc ghi Google Ads.

- Snapshot cùng ngày dùng `source_modified_at`, không dùng thời điểm maintenance quét lại folder.
- Nguồn mới nhất cùng metric date quyết định freshness; snapshot quá 6 giờ tạo đúng một cảnh báo warning-only.
- API chỉ đọc có dữ liệu hôm nay triệt tiêu cảnh báo CSV trong ngày.
- Runtime hiện source timestamp, mốc làm mới kế tiếp và `ATTENTION` khi snapshot đến hạn.
- Legacy metadata thiếu source timestamp không bị suy đoán là cũ; campaign/project vẫn được giữ nguyên.

- Downloads discovery chỉ nhận regular Desktop-app JSON hợp lệ, newest-first deterministic.
- Invalid JSON, web-client và symlink bị bỏ qua; unique candidate không prompt đường dẫn.
- Nhiều Desktop JSON hợp lệ tạo manual selection thay vì tự chọn; explicit CLI path vẫn bypass discovery.
- Discovery không in client ID/secret và không chạm Keychain; OAuth + SELECT-only preflight vẫn đi trước commit.

- Toàn bộ `app.js` chỉ còn một dynamic `<a href>` constructor nằm trong HTTP(S) guard chung.
- Signup, Terms evidence, commission fact, research/source change, capture và FX đều gọi shared renderer.
- `javascript:`, `data:`, malformed và URL thiếu hostname không tạo clickable anchor hoặc làm throw render.
- Link HTTP(S) hợp lệ vẫn mở tab mới với `rel="noopener"`; database/PPC/campaign/project không đổi.

- Evidence Pack format 4 ghi signup URL cùng authority trong JSON và README.
- Program chỉ có signup URL, chưa có research/evidence/fact, vẫn xuất URL trong source inventory.
- Shared classifier trả `OFFICIAL` cho same-domain và `PARTNER_PORTAL` cho external host ở cả API lẫn pack.
- Export không tạo audit/write và giữ mọi canonical permission `NOT_CHECKED`.

- Program API trả đúng signup URL cùng `OFFICIAL` cho same-domain và `PARTNER_PORTAL` cho host ngoài merchant.
- Create/PATCH chặn `javascript:`/`data:` trước database; giao diện chỉ tạo link cho HTTP(S).
- Terms Evidence Center hiện link đăng ký, nhãn nguồn tiếng Việt hoặc cảnh báo thiếu link.
- Signup provenance không đổi permission, commission, campaign/project hoặc Google Ads từ xa.

- Existing program có signup trống được điền bằng evidence source cụ thể sau live collection.
- Existing external partner signup không bao giờ bị source mới cùng merchant domain ghi đè.
- Kết quả và audit ghi `signup_url_discovered`; canonical PPC vẫn `NOT_CHECKED`.
- Production-copy Fliki dùng ba nguồn chính thức, 0 collection errors, signup `https://fliki.ai/affiliate-program` và commission vẫn `PROPOSED` riêng.

- Manager Customer ID `987-654-3210` được chuẩn hóa và truyền vào preflight cho target `123-456-7890`.
- Manager ID chỉ vào bundle Keychain sau OAuth, token refresh và truy vấn đọc thật; kết quả setup không trả ID/secret.
- Manager ID sai bị chặn trước credentials loader/OAuth/Keychain.
- Lỗi ghi giá trị thứ năm phục hồi toàn bộ bốn OAuth credential và Manager ID trước đó.
- Readiness/Runtime/UI chỉ hiện boolean “MCC đã cấu hình”; MCC không trở thành credential bắt buộc cho đăng nhập trực tiếp.

- Report đổi tên thiếu Campaign ID nhưng có Customer ID đúng và tên khớp duy nhất được nhận diện theo content signature và nhập đúng ID đã lưu.
- Sai Customer ID vẫn tạo `CUSTOMER_ID_MISMATCH` trước commit dù Campaign ID chưa resolve; AdsAccount/campaign/spend đều không tăng.
- Hai campaign cùng tên trong một tài khoản tạo lỗi mơ hồ và ghi 0 dòng; tên chưa biết cũng không được đoán.
- Customer ID trống không thể dùng fallback để khôi phục ID và bị chặn `CUSTOMER_ID_VALUE_REQUIRED`.
- Runtime/API/UI hiện số Campaign ID đã tự khôi phục; receipt giữ attempted/resolved/unresolved.
- Dry-run trên bản sao live khôi phục đúng 4/4 dòng, tổng 297.211 VND, 1.883 impressions, 831 clicks và 0 update.

- CSV có Customer ID trực tiếp nhưng thiếu Budget/Status/Type/Currency vẫn nhập metric bằng tiền tệ campaign hiện có.
- Account name, campaign status, channel type, daily budget và currency đã lưu không bị default giả ghi đè.
- Fallback single-account thiếu Currency ở bất kỳ dòng nào trả `ACCOUNT_CURRENCY_REQUIRED` và ghi 0 dòng.
- Bootstrap có Customer ID nhưng thiếu Currency cũng bị chặn; không tạo AdsAccount/campaign USD giả.
- Cả ba đường mới giữ launch gate `WARNING_ONLY`, Google Ads read-only và PPC `NOT_CHECKED`.

- Dòng đầu có Customer ID đúng và dòng trùng phía sau để trống từng trả `SUCCESS`; nay file bị chặn trước commit.
- Identity counts đọc hai parsed rows trước dedupe: một explicit và một fallback.
- Metric rows vẫn dedupe riêng, nên idempotency không thay đổi khi identity sạch.

- Cột Customer ID tồn tại nhưng có ô trống tạo `CUSTOMER_ID_VALUE_REQUIRED`, ghi 0 dòng.
- Customer ID đúng trong file ghi `explicit_customer_id_rows`; fallback không bị gắn nhầm là đã xác minh.
- CSV legacy không có cột Customer ID tiếp tục dùng single-account currency gate.
- Customer ID sai, trống hoặc đúng đều có regression riêng; mọi file bị chặn giữ nguyên campaign/spend.

- Runtime/API/UI hiện cùng Customer ID đích đã chuẩn hóa và số file account mismatch.
- Readiness payload cũ thiếu `customer_ids` không làm runtime status lỗi.
- Operations nêu đúng Customer ID cần đăng nhập, xác nhận file chưa nhập và dữ liệu cũ giữ nguyên.
- Cảnh báo chỉ tăng khả năng quan sát; không mở PPC, không dừng/loại project và không ghi Google Ads.

- Browser-style Google Ads CSV của Customer ID khác bị chặn trước commit; campaign, spend và Ads account cũ không đổi.
- CSV không có Customer ID nhưng dùng USD bị chặn khi tài khoản cấu hình là VND.
- Customer ID `1234567890` được chuẩn hóa về `123-456-7890`, không tạo AdsAccount trùng.
- `Campaign state=Paused` thắng `Campaign status=Eligible`, nên trạng thái vận hành campaign được lưu đúng.
- Account mismatch tạo đúng một Operations action và không mở PPC permission hoặc dừng/loại project.

- Current research response và attempt history trả cùng bản đồ URL → source authority.
- Permission proposal hiển thị đúng authority riêng; canonical permission không thay đổi.
- Audit cũ thiếu authority nhưng có official collector snapshot được phục hồi là `OFFICIAL`.
- Authority không hợp lệ bị bỏ; URL không có căn cứ hiển thị `UNKNOWN` thay vì suy đoán.
- Terms UI dịch rõ nguồn merchant/cổng đối tác/xác nhận văn bản/bên thứ ba/chưa xác định.
- Evidence Pack format 3 giữ provenance trong summary và attempt CSV; manifest SHA-256 vẫn khớp.
- Export provenance chỉ đọc, giữ commission tách riêng và mọi PPC scope `NOT_CHECKED`.

- Chỉ chương trình đã tồn tại với saved cross-domain signup URL mới bật lượt đọc partner portal.
- Portal collector fetch đúng một URL, bỏ tracking query đã biết và không đi theo link trong nội dung.
- URL có credentials, HTTP, private host hoặc redirect rời portal host bị chặn.
- Permission/commission proposal giữ `PARTNER_PORTAL` qua import, semantic refresh, dedupe và audit.
- Cùng claim nhưng authority khác không bị nhập nhầm thành một nguồn.
- Official 40% one-time và portal up-to-50% lifetime tạo commission `CONFLICT`.
- External source history không đi vào same-domain discovery; canonical PPC vẫn `NOT_CHECKED`.

- Standard probe 404/410 tạo 0 collection errors.
- Cùng URL ở priority hoặc link chính thức bị 404 vẫn xuất hiện trong errors.
- Standard probe 503 giữ tiền tố retry và làm `_errors_require_retry=true`.
- Production-copy Pictory có 7 nguồn, `collection_errors=[]`, `UNCHANGED`.
- Suppression không tạo evidence/fact mới và giữ PPC `NOT_CHECKED`.

- Hai truncated snapshots cùng URL nhưng khác hash trả `PARTIAL`, không có source change item.
- Operations Inbox không tạo `TERMS_SOURCE_CHANGED` cho hash prefix động.
- Câu PPC thật đổi trên trang truncated vẫn tạo hai proposal trái chiều và `WARNING_TERMS_CONFLICT`.
- Canonical paid-search/brand/non-brand/direct-link vẫn `NOT_CHECKED` sau semantic conflict.
- Production-copy forced hash difference của Pictory trả `PARTIAL` và 0 source changes.

- `nav`, `utm_*`, `gclid`, `fbclid`, `msclkid` bị bỏ; document/signature/ref vẫn giữ đúng.
- URL canonical và biến thể tracking chỉ được fetch một lần; query nghiệp vụ vẫn là nguồn riêng.
- Snapshot cũ chứa cả URL canonical và tracking không tạo cảnh báo removed giả khi nâng collector.
- Live-check bản sao Pictory còn 7 URL duy nhất, không còn `?nav=mega`, commission vẫn `CONFLICT`.
- URL normalization không tạo evidence mới và giữ toàn bộ canonical PPC `NOT_CHECKED`.

- Response lớn chỉ đọc `MAX_PAGE_BYTES + 1`, giữ đúng prefix 1 MB và đánh dấu `truncated=true`.
- HTML prefix vẫn trích được link điều khoản và proposal cấm PPC; phần dư không được tải vào bộ nhớ.
- Source snapshot chỉ giữ hash/độ dài/truncated, không lưu toàn bộ nội dung trang.
- Evidence Pack format 2 hiện source page count và URL bị cắt ngắn của attempt mới nhất.
- Export vẫn chỉ đọc; mọi canonical PPC giữ `NOT_CHECKED` và không tạo thêm audit/evidence.
- Live check trên database copy đọc 8 nguồn Pictory, không còn lỗi size, commission vẫn `CONFLICT`.

- Mỗi Operations item có program render nút `Tải pack` trỏ cùng endpoint evidence pack.
- Inbox/Registry/research/review đều gọi chung evidence-selection synchronizer.
- Chuyển chương trình bằng code cập nhật đúng trạng thái disabled của nút export.

- Pictory pack thật có commission `CONFLICT`, source list đầy đủ và canonical PPC vẫn `NOT_CHECKED`.
- ZIP chứa 8 file cố định; manifest SHA-256 khớp từng file và Content-Disposition dùng domain đã sanitize.
- Evidence CSV giữ URL, excerpt, checked_at, confidence, scope/review state và vô hiệu hóa formula prefix.
- Commission facts nằm riêng; research attempts và review audit chỉ xuất trường đã allow-list.
- Export không tạo audit mới, không đổi permission và không loại/dừng project/campaign.

- Backup command ở chế độ noninteractive thoát 0 ngay sau thông báo thành công, không chờ stdin.
- Bài test dùng runtime giả và không tạo/chạm database sản xuất.
- Chế độ double-click tương tác vẫn giữ prompt Enter cuối.

- Confirmation cache cũ có checked_at mới hơn mtime vẫn được thay bằng kết quả hiện tại có snapshot scopes.
- Chỉ `source_modified_at` được dùng để bảo vệ snapshot mới; thời điểm scan không thể làm file cũ trông mới hơn.
- Quá trình nâng metadata giữ nguyên confirmed row count, spend và bốn quyền PPC `NOT_CHECKED`.

- Hai snapshot khác tên được ghi từ cũ đến mới; spend cuối cùng lấy đúng bản có mtime mới hơn.
- Hai nguồn chồng cùng tài khoản/ngày vẫn chỉ tạo một số dòng đã xác nhận trên Runtime.
- Snapshot cũ quay lại sau bản mới nhận trạng thái `SUPERSEDED`, ghi 0 dòng và không đổi spend mới.
- Runtime hiện số snapshot cũ đã chặn; cache-v8 giữ tương thích với confirmation legacy.
- Cả bốn PPC scope vẫn `NOT_CHECKED`; không campaign/project nào bị dừng hoặc loại trừ.

- A valid import followed by rejected-only and empty scans keeps one confirmed source and the original metric date.
- Missing-column guidance suppresses a duplicate stale action while confirmed history remains available.
- An empty scan later exposes stale status from the confirmed metric date instead of losing freshness memory.
- Reintroducing the identical CSV after empty scans is unchanged, writes zero rows and creates no second import audit.
- The first cache-v8 scan finds legacy confirmation behind a newer empty cache-v6 run.
- Runtime shows confirmed source count/time and keeps confirmed rows/date when current `files_seen=0`.

- A renamed near-match missing Date points to Segment → Time → Day and enters one actionable Inbox item.
- A renamed near-match missing Campaign ID points to Columns → Attributes → Campaign ID.
- Commission markers suppress near-match diagnostics even when generic campaign/traffic headers overlap.
- A newer valid report removes the older missing-column warning; stale guidance is not duplicated for the same root cause.
- Identical known and renamed files are parsed once, preserve one spend row and keep all four PPC scopes `NOT_CHECKED`.
- A fresh read-only API result suppresses CSV missing-column actions as well as stale/error fallback actions.

- A valid renamed Google Ads campaign CSV is discovered by its column signature and imported idempotently.
- Only the newest stable renamed report is used; known filename families keep their existing behavior.
- A commission-like CSV with amount/date/campaign fields but insufficient traffic columns is ignored.
- Runtime records `CONTENT_SIGNATURE` versus `FILENAME` and shows the number of renamed files found.
- Bounded content detection preserves PPC `NOT_CHECKED`, campaign/project inclusion and read-only Google Ads.

- No-public-PPC warnings count the latest attempt's expanded source set rather than stale run sources.
- Manual-source warnings link to the current attempt URL before the immutable run's old URL.
- Existing attempt-less legacy audit rows safely fall back to run source URLs.
- Latest-attempt warning context preserves root-cause campaign grouping and all PPC/campaign state.

- A duplicate research run returns every URL checked in the current attempt, not the older run's source set.
- The immutable run keeps its original sources while the current result and attempt audit expose the expanded set.
- Manual collector results expose the same current-attempt source field.
- Current-source response accuracy creates no duplicate run/fact/evidence and changes no PPC permission.

- Policy-related text changes produce a deterministic `CONTENT_CHANGED` source event.
- Added and removed official URLs are reported separately and sorted deterministically.
- Footer/copyright changes outside affiliate/PPC/commission text remain `UNCHANGED`.
- Total temporary fetch failure is `UNAVAILABLE` and does not claim that a source was removed.
- Source snapshots store SHA-256 and lengths only; full page text is absent from audit payloads.
- Source changes merge with the existing Terms root warning; accepted-evidence programs get one standalone warning-only item.
- All source-change paths preserve canonical PPC permissions, project/campaign inclusion and Google Ads state.

- A relevant page with no extractable claim remains in the research run's checked source URLs.
- The next scheduled research passes recent same-domain run URLs back as priority sources.
- Domain source memory works when the original research run predates program creation.
- A URL present only in rejected evidence/facts cannot re-enter through research history.
- Research runs audit every checked relevant page while program signup prefers the evidence-bearing URL.
- Reused research sources still leave all canonical PPC permissions `NOT_CHECKED` and campaigns warning-only.
- Newly created manual/scheduled backups return and list as `database_status=OK` only after verification.
- Current bytes are rechecked against declared SHA-256; changed files become `CHECKSUM_MISMATCH`.
- SQLite integrity, foreign keys, declared schema and current-code schema each gate verified status.
- Invalid/unreadable backups remain visible but never become Restore candidates.
- A rejected scheduled backup does not delay auto-backup; maintenance treats replacement as immediately due.
- Runtime selects the latest verified scheduled backup, reports rejected count and enters `ATTENTION` when none is safe.
- Backup recovery does not mutate PPC permissions, campaign/project inclusion, commission decisions or Google Ads state.
- A program-level no-PPC-evidence warning absorbs the campaign warning caused by the same missing evidence.
- The grouped root warning exposes campaign count/names while Risk & Exposure keeps every campaign row.
- Manual-source and temporary-retry Terms exceptions use the same root-cause grouping.
- Explicit `PROHIBITED`/`CONFLICT` evidence review remains separate from campaign risk warning.
- Grouping does not change canonical permissions, research/evidence rows, campaign links or remote Google Ads state.
- A recent research heartbeat is exposed separately from accepted PPC evidence time.
- Program API returns latest attempt/status/next due/freshness without changing permissions.
- A successful commission-only scan produces one non-user `TERMS_PERMISSION_NOT_FOUND` warning.
- Manual/retry research keeps its existing exception and does not receive the new duplicate warning.
- UI says “Không thấy quyền PPC công khai” instead of labeling absent evidence as stale.
- Two or more proposed commission facts produce one program-level operator decision.
- The grouped conflict item exposes every proposed rate/type without collapsing fact rows.
- Four `NOT_CHECKED` scopes produce one warning and zero required-user decisions.
- Two campaigns linked to one warning program produce one tracking warning.
- Repeated fixture and live-web attempts preserve `duplicate_run=true` in history audit.
- `Annual SAVE MORE THAN 15%` is rejected while the nearby up-to-50% commission is retained.
- Pictory fixture-to-live refresh reuses both fact IDs and imports zero false discount facts.
- A PROHIBITED/CONFLICT permission proposal remains a separate explicit review action.
- Inbox triage changes no permission, evidence/fact review status or campaign/project state.
- Same URL/scope/decision with reworded text reuses all four existing permission IDs.
- Reword refresh updates checked_at/excerpt and writes before/after audit without opening PPC.
- Accepted permission evidence keeps its original excerpt and receives a separate new proposal.
- A changed PAID_SEARCH decision is not refreshed over the old one and produces conflict warning.
- `refreshed_terms_evidence` is separate from imported/duplicate counts.
- Research UI renders new/refreshed/unchanged counts for both evidence and commission facts.
- Research history maps missing legacy counters to zero and exposes current refresh counters.
- Canonical paid-search/brand/non-brand/direct-link fields remain `NOT_CHECKED` during refresh.
- Pictory fixture → live reuses the existing 40%/50% fact IDs and imports zero false 15% facts.
- Recurring unspecified may refine to lifetime on the same automated proposal row.
- Accepted fact keeps its original excerpt/status; changed live text becomes a separate proposal.
- Same live result refreshes checked_at/audit without multiplying commission rows.
- Manual/no-new-source research still reports the program's existing `CONFLICT` state.
- Commission refresh audit contains before/after plus `permissions_changed=false`.
- Pictory canonical PPC fields remain `NOT_CHECKED` after semantic refresh.
- API success/error/rate-limit chưa đủ 6 giờ đều bị skip; đúng mốc mới được chạy lại.
- AUTH_FAILED chưa đủ 24 giờ không gọi Google; setup request vẫn bypass đúng một lần.
- CSV/commission/campaign mapping tiếp tục chạy ở heartbeat khi API bị `SKIPPED_FRESH`.
- Skip API không tạo SyncRun giả và luôn trả `write_operations_enabled=false`.
- One-shot request chỉ chứa timestamp, mode `0600` và bị xóa sau lần thử.
- Runtime hiện đúng API due/ETA; request setup pending chuyển ETA thành ngay lập tức.
- Setup chỉ tạo request sau khi preflight và Keychain bundle đã commit thành công.
- Restore-services với đủ hai label gọi đúng manager `install --target` thay vì bootstrap plist cũ.
- Manager non-zero làm updater ném lỗi regeneration có kiểm soát; không ghi nhận runtime restored giả.
- Production live plist và launchctl cùng xác nhận `run interval = 1800 seconds` sau regeneration.
- LaunchAgent maintenance dùng `StartInterval=1800`, vẫn `RunAtLoad` và không chồng chu kỳ.
- Runtime next-maintenance/Terms ETA dùng đúng heartbeat 30 phút, không còn cộng mặc định 6 giờ.
- Terms đã quá hạn với heartbeat vừa chạy được xếp vào slot +20 phút trong fixture, thay vì +5h50.
- Backup gần và Terms fresh vẫn bị skip; retry 5h59/stable 23h56 chỉ chạy nhờ grace cũ.
- OAuth refresh preflight failure xảy ra trước SearchStream/Keychain và không gọi bundle writer.
- SearchStream AUTH_FAILED cho đúng Customer ID cũng không gọi bundle writer; bộ Keychain cũ giữ nguyên.
- Preflight query chỉ một ngày, dùng customer ID chuẩn hóa và kết quả không chứa access/refresh token.
- Keychain commit chỉ xuất hiện sau thứ tự load JSON → OAuth consent → refresh → SearchStream.
- OAuth authorizer hoàn tất trước bundle writer; cancel/timeout không gọi bất kỳ Keychain write nào.
- Bundle update lỗi ở credential thứ ba phục hồi byte-value của mọi credential cũ đã thay.
- Bundle first-time setup lỗi xóa hết credential fragment mới, không để readiness xanh giả.
- Kết quả setup chỉ trả tên bốn label + mode read-only, không trả client secret/refresh token.
- Setup command chỉ kickstart maintenance LaunchAgent khi Python setup thành công; lỗi giữ CSV fallback.
- UI hướng dẫn đúng hai đầu vào người dùng cung cấp và không trình bày bốn Keychain item như bốn việc tay.
- Restore command bootout cả server/maintenance LaunchAgent trước Python restore và bootstrap lại
  cả hai sau success lẫn failure; thứ tự dừng → restore → chạy lại được kiểm thử end-to-end.
- Restore từ chối chạm database nếu localhost chưa dừng thật; EXIT/INT/TERM cleanup vẫn nạp runtime lại.
- Migration graph có type annotation được đọc đúng để xác định Alembic head mà không mở live database.
- Database live mô phỏng bị corrupt vẫn restore từ backup đúng schema; raw DB/WAL/SHM trước restore
  được giữ bằng tên `.preserved` và byte-for-byte không đổi.
- Database corrupt nhưng không xác định được schema từ code bị từ chối và giữ nguyên dữ liệu lỗi để cứu hộ.
- Backup mới ghi actual Alembic head, integrity `ok`, foreign key `ok` và SHA-256.
- Restore bỏ qua bản mới hơn nếu sai schema và chọn bản tương thích gần nhất.
- SHA khai báo sai hoặc foreign-key violation làm backup bị bỏ qua; nếu không còn bản hợp lệ,
  database hiện tại giữ nguyên và không tạo emergency backup giả.
- Update backup chỉ có `update-manifest.json` vẫn hiện đúng schema thật và version nguồn.
- Bản tạm được kiểm tra lại trước atomic replace; emergency backup giữ đúng trạng thái trước restore.
- UI/API/model defaults: `NOT_CHECKED`, confidence `0`.
- Mỗi `MANUAL_INPUT_REQUIRED` attempt có audit riêng, kể cả duplicate heartbeat.
- Lỗi truy cập có `collection_errors` tạo `RETRY_REQUIRED`, tự retry sau 6 giờ và không yêu cầu người dùng.
- Kết quả không có evidence nhưng không có lỗi vẫn tạo `MANUAL_INPUT_REQUIRED` và yêu cầu nguồn.
- Runtime/Inbox nhận đúng retry pending; retry không đổi permission hoặc campaign/project inclusion.
- Biên lịch chấp nhận mốc retry 5h59 và refresh 23h56, nhưng chưa chạy ở 23h54.
- ETA chọn đúng maintenance slot nằm trong 5 phút trước due time thay vì trượt thêm 6 giờ.
- URLError/429/503 được đánh dấu tạm thời; 404 và validation error được giữ là permanent miss.
- Permanent 404 no-evidence tạo `MANUAL_INPUT_REQUIRED`, không tạo retry loop.
- Audit lưu source URLs, priority URLs, collection errors và `permissions_changed=false`.
- API lịch sử chỉ trả audit thuộc đúng program, mới nhất trước và có giới hạn số dòng.
- UI hiện source/error/heartbeat và nhãn `PPC KHÔNG ĐỔI`; research result hiện lỗi trực tiếp.
- Inbox Terms manual dùng audit mới nhất để hiện lỗi, số priority URLs và source link.
- Mở Inbox program item tải đồng thời evidence, commission facts và research attempts.
- Google Ads checksum `ERROR` được retry khi context thay đổi; cùng file phục hồi từ thiếu
  Customer ID sang SUCCESS và chỉ tạo đúng 1 campaign/1 spend row.
- Checksum đã thành công vẫn unchanged/idempotent; Runtime hiện số file retry.
- Commission checksum `MAPPING_REQUIRED` được retry; cùng file tự chuyển SUCCESS sau khi
  Fliki program xuất hiện và chỉ tạo đúng một commission/conversion.
- Commission checksum thành công vẫn unchanged; conflict/error không ghi đè dữ liệu cũ.
- Google Ads file thành công với `unmapped_rows=1` được retry sau khi program domain xuất hiện,
  tạo đúng một mapping, giữ đúng một spend row rồi chuyển sang unchanged ở lần kế tiếp.
- Campaign name có đúng một merchant domain được tự map; chuỗi con và domain mơ hồ không được map.
- Auto-map không ghi đè mapping thủ công và không thay đổi PPC permission hoặc campaign inclusion.
- Bảo trì backfill được campaign cũ chưa ghép ngay cả khi CSV không đổi; chạy lặp lại không nhân mapping/audit.
- Backfill giữ nguyên mọi mapping đã có, domain mơ hồ và chuỗi con vẫn chưa ghép.
- Runtime API/UI hiện mapped/unresolved/preserved của chu kỳ gần nhất; lịch sử cũ mặc định 0.
- Fresh official proposal trái accepted evidence hạ `TERMS_OK` thành conflict warning mà không đổi permission.
- Hai official proposals chưa xét trái nhau cũng cảnh báo; loại proposal sai khôi phục trạng thái accepted.
- `MANUAL_INPUT_REQUIRED` mới hơn accepted/review event hạ `TERMS_OK` thành `WARNING_TERMS_UNVERIFIED`.
- Duplicate research heartbeat mới được tính là lần rà mới; `checked_at` cũ không che nguồn vừa biến mất.
- Programs, Dashboard, Compliance, Exposure và Operations Inbox dùng cùng Terms warning mới.
- Source-loss warning giữ nguyên canonical permission, `project_included=true` và `warning_only=true`.
- Lần rà thành công mới hơn hoặc human review chủ động sau cảnh báo khôi phục evidence-backed `TERMS_OK`.
- Selector chung xếp research run theo `max(checked_at, updated_at)` rồi ID ổn định.
- Maintenance, Runtime, Operations Inbox và source-loss gate chọn cùng một latest attempt.
- Source date mới hơn nhưng heartbeat cũ hơn không thể che lần recheck thực sự mới nhất.
- Lịch refresh tiếp tục dùng đúng cửa sổ 24 giờ tính từ attempt/heartbeat mới nhất.
- Runtime tính đúng số chương trình đến hạn và mốc refresh sớm nhất; program chưa từng rà đến hạn ngay.
- Command Center hiện lịch rà Terms nhưng không tự đổi PPC permission, campaign/project hoặc commission facts.
- ETA Terms bỏ qua các chu kỳ bảo trì trước mốc đủ 24 giờ và chọn đúng chu kỳ 6 giờ đầu tiên sau đó.
- UI tách rõ “Terms đủ 24 giờ” khỏi “Lần rà Terms dự kiến”.
- Runtime tách số lần rà Terms còn mới khỏi số chương trình evidence-backed `TERMS_OK`.
- Chương trình có heartbeat mới nhưng không có accepted permission evidence vẫn nằm trong warning count.
- UI dùng hai nhãn riêng “Lần rà Terms còn mới” và “Terms đã xác minh”.
- Stored accepted/proposed source URLs được xếp trước homepage links và standard paths.
- Deep policy URL không có link từ homepage vẫn được fetch, nhưng phải qua toàn bộ SSRF guard.
- Rejected evidence/fact URLs không được tự đưa lại vào priority queue.
- Commission-only `PROPOSAL_READY` mới hơn không thể giữ `TERMS_OK` nếu thiếu proposal cho scope PPC bắt buộc.
- Revalidation đủ PAID_SEARCH/NON_BRAND hoặc PAID_SEARCH/BRAND scopes cho phép accepted evidence khôi phục xanh.
- Pictory fixture version chỉ seed một research run; lần kế tiếp không đi lại fixture path.
- Live recheck failure tạo `official-web-v1` manual run mới và không cập nhật fixture heartbeat.
- Fixture seed facts và toàn bộ PPC permission giữ nguyên qua live failure.
- Extractor từ cùng trang tạo đúng 4 scope và không biến cấm direct link thành cấm paid search.
- Evidence POST chỉ tạo `PROPOSED`, không đổi canonical permission.
- Low-confidence hoặc nguồn chưa xác minh không thể được accept.
- `TERMS_OK` non-brand cần cả PAID_SEARCH và NON_BRAND evidence chính thức đã accept.
- Hai evidence chính thức trái nhau resolve `CONFLICT` và `WARNING_TERMS_CONFLICT`.
- Pictory import hai commission facts idempotent; trạng thái commission là `CONFLICT`.
- Pictory giữ mọi quyền PPC ở `NOT_CHECKED` và terms ở `WARNING_TERMS_UNVERIFIED`.
- Commission facts không thể thay đổi PPC permissions.
- Dashboard chỉ tính `TERMS_OK` khi có accepted evidence hợp lệ; canonical permission legacy
  hoặc PATCH trực tiếp không thể làm tăng số terms-ok.
- Terms Warning chỉ đọc chương trình và evidence đã lưu; client không thể tự khai permission
  hoặc evidence để tạo `TERMS_OK`.
- Mọi warning trả `project_included=true`; `PROHIBITED`, `CONFLICT` và `NOT_CHECKED` không loại dự án.
- Google Ads CSV import idempotent theo campaign/ngày/source, hỗ trợ cập nhật spend và metrics.
- Báo cáo Google Ads tiếng Việt được đọc trực tiếp sau hai dòng mô tả đầu file.
- Các dòng “Tổng số” bị bỏ qua; trạng thái `Đang bật` và loại `Tìm kiếm` được chuẩn hóa.
- Nhãn nguồn `GOOGLE_ADS_CSV` / `GOOGLE_ADS_CSV_VI` không tạo spend trùng.
- Campaign acknowledgement không thay đổi warning hoặc PPC permission.
- Exposure tách total spend, spend at risk, commission at risk, recognized revenue, cash và actual net cash.
- Review một scope không ghi đè permission hoặc `last_terms_checked_at` legacy ở scope khác.
- Migration 0.2.1 → 0.2.2 và downgrade/upgrade lại giữ nguyên Pictory cùng row counts.
- Updater checkpoint SQLite WAL, kiểm tra checksum/integrity/Alembic head và row counts.
- Lỗi checksum xảy ra trước mutation; lỗi migration tự restore database + code.
- Rollback thủ công tạo emergency backup trước khi khôi phục.
- Runtime regression: symlink `.venv/bin/python` nội bộ không chặn Alembic launcher hợp lệ.
- Các regression economics, ledger, attribution, backup và ad intelligence của 0.2.0 vẫn pass.
- FX proposal mặc định chưa áp dụng; confidence dưới 0,8 không thể được accept.
- Accepted direct/inverse FX rates chuẩn hóa finance nhưng giữ nguyên amount/currency gốc.
- Hai accepted rate khác nhau cùng pair/date bị chặn; thiếu hoặc quá hạn rate được báo rõ.
- Dữ liệu VND cũ được chuẩn hóa 1:1; 9 dòng spend thật vẫn tổng cộng 149.291 VND.
- Commission ID trùng/xung đột đi vào reconciliation queue và không ghi đè facts đã lưu.
- ATTRIBUTED tự đóng; PARTIAL/UNATTRIBUTED cần xử lý và có ghi nhận resolution.
- Migration 0.2.3 → 0.2.4, downgrade và upgrade lại giữ integrity cùng row counts.
- Generic collector tạo sourced TermsEvidence ở `PROPOSED` nhưng giữ mọi canonical permission ở `NOT_CHECKED`.
- Collector nhận diện prohibited brand/direct-link, non-brand-only và commission cadence/rate.
- Generic official commission claims trái nhau resolve `CONFLICT` mà không ảnh hưởng PPC.
- Chạy lại cùng nội dung không tạo evidence, fact hoặc research run trùng.
- Private IP, redirect ngoài domain, credential URL, non-HTTPS và port khác 443 bị chặn.
- Redirect nhiều candidate về cùng URL được gộp; commission lặp trên một trang chỉ tạo một fact.
- Fliki live-page test trên database copy: 30% lifetime-recurring proposal; PPC vẫn `NOT_CHECKED`.
- Commission fact hợp lệ có thể ACCEPT và chuyển commission state thành `RESOLVED`.
- Conflict vẫn tồn tại sau khi accept một fact; chỉ resolve sau khi fact cạnh tranh bị REJECT.
- Low-confidence và off-domain official fact bị chặn khi accept nhưng vẫn có thể reject.
- Mọi commission review ghi audit với `permissions_changed=false`; PPC regression giữ `NOT_CHECKED`.
- Operations Inbox tổng hợp đúng Terms, commission, FX, reconciliation, missing source/rate và campaign warning.
- Accepted/rejected/resolved items rời inbox; research run mới hơn loại yêu cầu manual cũ.
- Campaign warning có `requires_user=false` và ghi rõ campaign không bị loại hoặc dừng.
- UI live-copy hiển thị 3 việc cần xử lý + 1 cảnh báo; nút Fliki mở đúng Commission Facts.
- Browser console không có lỗi trong luồng Command Center → Fliki commission review.
- Maintenance lock không cho hai chu kỳ chạy chồng nhau.
- Một domain thu thập lỗi tạo trạng thái `PARTIAL` nhưng Finance và Operations Inbox vẫn chạy.
- Terms còn mới được bỏ qua; Terms quá 24 giờ mới được thu thập lại và vẫn chỉ tạo proposal.
- Scheduled backup được giới hạn tối đa một lần mỗi 24 giờ.
- LaunchAgent server không dùng reload, tự phục hồi process và chỉ lắng nghe `127.0.0.1:8765`.
- Updater nhận biết dịch vụ 24/7, bootout trước mutation và bootstrap lại sau thành công.
- Maintenance trên production-copy: `SUCCESS`, integrity `ok`, 2 programs, 9 spend rows,
  4 Operations items, 0 collection errors và không thay đổi dữ liệu gốc.
- Runtime status phân biệt `HEALTHY / STARTING / ATTENTION / NOT_CONFIGURED`.
- Runtime status chỉ gọi `launchctl print` với hai label cố định và từ chối label lạ.
- Production-copy status: hai dịch vụ loaded, maintenance `SUCCESS`, 2/2 Terms còn mới.
- Runtime API và Command Center trả schema/markup 0.2.9 đúng trên desktop test client.
- Folder discovery chọn `Báo cáo chiến dịch (1).csv` mới hơn và bỏ bản cũ thiếu Campaign ID.
- Production-copy auto-ingest đọc 9 dòng, mapped 9, ghi 0 dòng trùng; lần hai bỏ qua theo SHA-256.
- Auto-ingest giữ 9 spend rows và tổng 149.291 VND; integrity `ok`, Operations Inbox vẫn 3 quyết định + 1 cảnh báo.
- File lỗi không commit; lỗi và campaign chưa ghép xuất hiện trong Operations Inbox.
- Audit phân biệt actor `auto-folder`; PPC permission regression vẫn `NOT_CHECKED`.
- Runtime status đọc 9 rows từ `file_results` kể cả khi cycle hiện tại bỏ file unchanged.
- LaunchAgent install và updater restore không kickstart maintenance lần hai; server vẫn kickstart.
- Preview và folder cache lưu đúng khoảng ngày metric trong báo cáo Google Ads.
- Dữ liệu đến hôm qua còn mới; dữ liệu cũ hơn tạo đúng một action trong Operations Inbox.
- Cảnh báo dữ liệu cũ không thay đổi, dừng hoặc loại bất kỳ campaign/PPC permission nào.
- Runtime status tiếp tục hiện ngày dữ liệu đã xác nhận khi SHA-256 của file không đổi.
- Commission discovery chỉ nhận tên commission/hoa hồng và chọn numbered export mới nhất.
- Tên file/cột domain khớp duy nhất mới được auto-map; file generic tạo action và không ghi.
- Đổi tên file generic theo merchant làm cùng SHA được phân tích lại và nhập đúng chương trình.
- Cùng transaction được cập nhật Pending → Approved bằng source domain ổn định, không nhân đôi.
- File thiếu cột hoặc conflict không auto-commit; commission/PPC/campaign cũ giữ nguyên.
- Runtime commission mapping/error chuyển sang ATTENTION và chỉ dẫn tới Finance/Operations.
- Duplicate generic/fixture research giữ nguyên source `checked_at` và tăng recheck heartbeat.
- Terms refresh dùng heartbeat: recheck một giờ trước là fresh, quá 24 giờ mới due.
- Pictory recheck không tạo run/fact mới, commission vẫn `CONFLICT`, PPC vẫn `NOT_CHECKED`.
- Google Ads preflight chuẩn hóa `123-456-7890` thành `1234567890`.
- Missing credentials chỉ trả tên trường; giá trị Keychain không xuất hiện trong API/UI.
- Đủ bốn Keychain entries chuyển readiness sang `READY` nhưng write operations vẫn `false`.
- Không có Ads account trả `ACCOUNT_REQUIRED`; CSV fallback luôn `true`.
- Keychain write truyền secret qua stdin, không đặt secret trong process arguments.
- Keychain read chỉ trả secret trong memory của connector và không đặt giá trị trong arguments/log.
- OAuth Desktop JSON từ chối symlink, file quá lớn, JSON sai hoặc client không phải Desktop app.
- Authorization URL dùng offline consent, random state, loopback `127.0.0.1` và PKCE S256.
- Callback sai state/thiếu code/bị từ chối bị chặn trước token exchange.
- Fake end-to-end loopback nhận callback trên random local port và trả refresh token mà không gọi Google thật.
- OAuth refresh và Google Ads request chỉ dùng hai endpoint HTTPS cố định; lỗi không chứa secret.
- SearchStream URL chỉ nhận Customer ID 10 chữ số và GAQL chỉ có `SELECT` fields cố định.
- Query từ chối khoảng ngày đảo hoặc quá 31 ngày; maintenance dùng đúng bảy ngày đến hôm qua.
- Response sai customer, ngoài khoảng ngày, âm, sai kiểu hoặc quá 25 MB bị từ chối trước commit.
- Customer ID local có dấu gạch khớp API ID chuẩn hóa mà không tạo AdsAccount trùng.
- Preview phân loại matched/different/new; secret không xuất hiện trong kết quả trả về.
- API cập nhật dòng `GOOGLE_ADS_CSV` canonical hiện có, giữ một Spend row và mapping manual.
- API sync không đổi PPC permission; audit actor là `auto-google-ads-api` và write flag luôn `false`.
- Missing credential bỏ qua trước Keychain read/token refresh/SearchStream; CSV fallback vẫn `true`.
- Maintenance production chạy CSV → API → commission; API skip không làm chu kỳ thành PARTIAL.
- API đến hôm qua giữ runtime `HEALTHY` và loại action sửa/xuất CSV fallback cũ khỏi Inbox.
- HTTP 429/5xx/network retry tối đa ba lần; delay deterministic 1s rồi 2s.
- HTTP 401/403 và OAuth invalid-grant 400 không retry, được phân loại `AUTH_FAILED`.
- Retry 429 thành công ở lượt ba trả đúng campaign row và không nhân request vượt giới hạn.
- Failure SyncRun chỉ giữ thông báo sạch, category, max attempts và hai safety flags.
- AUTH_FAILED tạo action cần người dùng chạy setup; token không xuất hiện trong error summary.
- RATE_LIMITED tạo warning không cần người dùng và ghi rõ sẽ tự thử lại chu kỳ sau.

## Chưa kiểm chứng production

- Live generic terms collection ngoài fixture Pictory; domain chưa có fixture chuyển sang manual input.
- Affiliate agreement bên trong Pictory Partner Portal hoặc xác nhận bằng văn bản về PPC.
- Google Ads OAuth thật (chờ OAuth Desktop JSON + Developer Token + người vận hành đăng nhập), affiliate-network API và click → SubID/GCLID → commission thật.
- CSV commission thật từ affiliate network của người vận hành (chưa có trong Downloads).

## Đã kiểm chứng với báo cáo thật

- File Google Ads của tài khoản người vận hành: 9 dòng campaign hợp lệ, 149.291 VND,
  851 impressions, 384 clicks, 0 conversions và Campaign ID `24116162130`.
- Parser trả 0 lỗi và không nhận bất kỳ dòng “Tổng số” nào.
- Bản sao production xác nhận dữ liệu từ 2026-08-02 đến 2026-08-10; tại ngày
  2026-08-11 trạng thái vẫn `HEALTHY`, không tạo nhắc xuất file và Inbox giữ nguyên 4 mục.
- Commission folder production-copy thấy 0 file phù hợp, ghi 0 giao dịch; runtime vẫn
  `HEALTHY`, 9 spend rows/149.291 VND và 4 mục Inbox được giữ nguyên.
- Production-copy ép Pictory overdue: chu kỳ đầu recheck 0 evidence/0 fact mới, chu kỳ
  kế tiếp skip; source date giữ nguyên, heartbeat mới, tổng facts vẫn 3 và integrity `ok`.
- Production-copy preflight nhận đúng Customer ID `1234567890`, báo thiếu đúng bốn
  credential, write operations `false`, CSV fallback `true`; runtime vẫn `HEALTHY`.
- Production-copy update 0.2.15 → 0.2.16, rollback về 0.2.15 và cài lại 0.2.16 đều
  thành công; mỗi trạng thái giữ integrity `ok`, 2 programs, 9 spend rows, 3 facts và 1 campaign.
- Production-copy API 0.2.16 trả health `ok`, 2/2 Terms còn mới, 4 Inbox items và
  Google Ads `CREDENTIALS_REQUIRED`; không có credential giả nào được ghi vào Keychain.
- Production-copy 0.2.17 maintenance chạy `SUCCESS`: CSV 9 rows, API v25
  `SKIPPED_CREDENTIALS`, commission 0 rows, normalization 9 rows và 0 errors.
- Production-copy API 0.2.17 trả health `ok`, runtime `HEALTHY`, 2/2 Terms còn mới,
  4 Inbox items, API rows/writes/differences đều 0 và write operations `false`.
- Production-copy update 0.2.16 → 0.2.17, rollback về 0.2.16 và cài lại 0.2.17 đều
  giữ integrity `ok`, 2 programs, 9 spend rows, 3 facts và 1 campaign.
- Production-copy 0.2.18 maintenance vẫn `SUCCESS` khi thiếu credential: API
  `SKIPPED_CREDENTIALS`, CSV 9 rows, 0 errors và write operations `false`.
- Production-copy update 0.2.17 → 0.2.18, rollback về 0.2.17 và cài lại 0.2.18 đều
  giữ integrity `ok`, 2 programs, 9 spend rows, 3 facts và 1 campaign.
- Production-copy update 0.2.18 → 0.2.19, rollback về 0.2.18 và cài lại 0.2.19 đều
  giữ integrity `ok`, migration head `d8a6f4b20317`, 2 programs và 9 spend rows.
- Production-copy 0.2.19 maintenance chạy `SUCCESS`, 2/2 Terms còn mới, normalization
  giữ 9 rows và Operations Inbox giữ 4 mục; chế độ bản sao không đọc/ghi Downloads.
- Production-copy 0.2.20 tự ghép campaign lịch sử `pictory.ai` từ 1 campaign chưa ghép,
  ghi `CAMPAIGN_NAME_DOMAIN` + 1 audit; mapping Fliki đã có vẫn giữ nguyên.
- Production-copy update 0.2.19 → 0.2.20, rollback về 0.2.19 và cài lại 0.2.20 đều
  giữ integrity `ok`; rollback khôi phục đúng 2 campaigns/1 link/0 backfill audit.
- Production-copy 0.2.21 đọc đúng kết quả chu kỳ gần nhất: 2 campaigns, 1 vừa map,
  0 unresolved và 1 mapping được giữ; Command Center có thẻ tiếng Việt tương ứng.
- Production-copy update 0.2.20 → 0.2.21, rollback về 0.2.20 và cài lại 0.2.21 đều
  giữ integrity `ok`, 2 programs, 9 spend rows, 2 campaigns và 2 mappings.
- Production-copy 0.2.22 xác nhận `TERMS_OK` → `WARNING_TERMS_CONFLICT` khi thêm
  official proposal trái chiều; canonical giữ `NON_BRAND_ONLY`, loại proposal trở lại `TERMS_OK`.
- Production-copy update 0.2.21 → 0.2.22, rollback về 0.2.21 và cài lại 0.2.22 đều
  giữ integrity `ok`; rollback loại đúng dữ liệu kiểm thử và khôi phục 2 programs/9 spend rows.
- Production-copy update 0.2.22 → 0.2.23, rollback về 0.2.22 và cài lại 0.2.23 đều
  giữ integrity `ok`, migration head `d8a6f4b20317`, 2 programs, 9 spend rows, 3 facts,
  1 campaign và 1 mapping trước khi thêm fixture kiểm thử.
- Production-copy 0.2.23 xác nhận source loss mới hạ `TERMS_OK` thành
  `WARNING_TERMS_UNVERIFIED`, canonical vẫn `NON_BRAND_ONLY`, project vẫn được giữ;
  lần rà thành công mới hơn tự khôi phục `TERMS_OK`.
- Production-copy update 0.2.23 → 0.2.24, rollback về 0.2.23 và cài lại 0.2.24 đều
  giữ integrity `ok`, migration head `d8a6f4b20317`, 2 programs, 9 spend rows, 3 facts,
  1 campaign và 1 mapping trước fixture.
- Production-copy 0.2.24 với hai run đảo thứ tự source/heartbeat xác nhận maintenance không
  refresh sớm, Runtime tính fresh và Inbox chọn đúng `MANUAL_INPUT_REQUIRED` mới nhất;
  heartbeat thành công mới hơn sau đó tự loại cảnh báo nguồn.
- Production-copy update 0.2.24 → 0.2.25, rollback về 0.2.24 và cài lại 0.2.25 đều
  giữ database và updater contract; Runtime trả chính xác 2 programs, 2 recent checks,
  0 verified Terms và 2 warnings; UI chứa hai nhãn tách biệt.
- Production-copy update 0.2.25 → 0.2.26, rollback về 0.2.25 và cài lại 0.2.26 đều
  giữ integrity `ok`, 2 programs, 9 spend rows, 3 facts, 1 campaign và 1 mapping trước fixture.
- Production-copy 0.2.26 xác nhận commission-only scan hạ xanh thành warning, collector recheck
  đúng deep stored URL, đủ hai permission scopes thì trở lại `TERMS_OK`; canonical permission không đổi.
- Production-copy update 0.2.26 → 0.2.27, rollback về 0.2.26 và cài lại 0.2.27 đều
  giữ integrity `ok`, 2 programs, 9 spend rows, 3 facts và 2 research runs trước fixture test.
- Production-copy Pictory live outage tạo run thứ ba `MANUAL_INPUT_REQUIRED`, không đổi fixture
  heartbeat, không nhân commission facts và giữ bốn PPC permission ở `NOT_CHECKED`.
- Snapshot dữ liệu production chạy bằng code 0.2.28 giữ integrity `ok`, 2 programs,
  9 spend rows và 3 commission facts; hai lần Pictory live outage chỉ tạo 1 research run.
- Hai lần thử đó tạo đúng 2 audit events (lần đầu + duplicate heartbeat), lưu đủ hai URL
  Pictory ưu tiên và `permissions_changed=false`; updater/rollback contract đạt 8/8 tests.
- Snapshot production chạy bằng API/UI 0.2.29 đọc đúng 1 attempt cho Pictory và 1 cho Fliki,
  mọi dòng đều `permissions_changed=false`; database giữ nguyên 2 programs, 9 spend rows,
  3 commission facts, 2 research runs và 6 audit events sau toàn bộ phép thử chỉ đọc.
- Snapshot production chạy bằng 0.2.30 giữ nguyên 4 Inbox items (3 cần người dùng, 1 cảnh báo)
  và giữ nguyên 2 programs, 9 spend rows, 3 facts, 2 research runs, 6 audits sau hậu kiểm.
- Production snapshot + hai Google Ads CSV thật chạy bằng 0.2.31: lần đầu nâng cache đọc lại
  đúng 9 rows/ghi 0, lần hai unchanged 1/ghi 0; canonical giữ 2 programs, 1 campaign,
  9 spend rows, 3 facts và integrity `ok`.
- Production snapshot + commission sample chạy bằng 0.2.32 nhập đúng 3 transactions lần đầu,
  lần hai unchanged/ghi 0 và giữ nguyên toàn bộ Pictory/Fliki PPC permissions; integrity `ok`.
- Production snapshot + Google Ads CSV thật chạy bằng 0.2.33 đọc 9 rows/ghi 0 với
  `unmapped_rows=0`, lần hai unchanged/ghi 0; giữ 2 programs, 1 campaign, 1 mapping,
  9 spend rows và integrity `ok`.
- Production snapshot chạy bằng 0.2.34 giữ nguyên 2 programs, 1 campaign, 1 mapping,
  9 spend rows và 3 commission facts; Runtime báo 0 chương trình đến hạn, mốc gần nhất
  `2026-08-11T13:41:20.760248Z`, 0/2 Terms đã xác minh, 2 cảnh báo và integrity `ok`.
- Production snapshot chạy bằng 0.2.35 giữ nguyên toàn bộ counts và integrity `ok`; mốc đủ
  24 giờ là `2026-08-11T13:41:20.760248Z`, còn ETA căn theo maintenance là
  `2026-08-11T17:50:39.801935Z`, không đổi 2 Terms warnings hoặc 3 commission facts.
- Production snapshot chạy bằng 0.2.36 xác nhận outage tạo `RETRY_REQUIRED`, Inbox vẫn chỉ
  có 3 việc cần người dùng và thêm một cảnh báo tự retry; kết quả không lỗi/no-evidence mới
  tăng lên 4 việc cần người dùng. Toàn bộ PPC permissions giữ nguyên và integrity `ok`.
- Production snapshot chạy bằng 0.2.37 xác nhận retry 5h59 và stable refresh 23h56 đã đến
  hạn trong grace, còn 23h54 chưa đến hạn; database copy giữ integrity `ok`.
- Production snapshot chạy bằng 0.2.38 xác nhận 404 tạo `MANUAL_INPUT_REQUIRED` và tăng việc
  cần người dùng từ 3 lên 4; timeout tạo `RETRY_REQUIRED`, giữ 3 việc người dùng và tăng
  cảnh báo hệ thống lên 2. PPC permissions không đổi và integrity `ok`.
- Production-copy 0.2.39 đọc đủ 47/47 backup hiện có, chọn đúng
  `update-0.2.38-20260811-061923`, tạo emergency backup trên bản sao rồi restore với schema
  `d8a6f4b20317`, integrity/foreign keys đều `ok`; database đang chạy không bị chạm vào.
- Disaster production-copy 0.2.40 đọc đủ 48/48 backup, dùng migration code để cứu database
  mô phỏng bị corrupt, chọn đúng `update-0.2.39-20260811-063243`, giữ raw DB/WAL/SHM,
  và khôi phục 2 programs/9 spend rows với integrity/foreign keys `ok`; live database không bị chạm.
