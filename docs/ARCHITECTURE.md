# ARCHITECTURE

## 1. Kiến trúc triển khai

```text
Browser UI / Chrome Capture Helper
              │
              ▼
      FastAPI local application
              │
     ┌────────┼─────────┐
     ▼        ▼         ▼
  SQLite   Domain     Connector
  Ledger   Services   Adapters
              │
              ▼
   Audit / Compliance / Economics
```

## 2. Technology baseline

- Python 3.11+
- FastAPI
- SQLAlchemy 2
- Alembic
- SQLite WAL mode
- Vanilla HTML/CSS/JavaScript
- Pytest + Ruff

## 3. Bounded contexts

### Ad Intelligence

`Advertiser`, `Project`, `RawCapture`, `AdObservation`.

### Program Governance

`Merchant`, `AffiliateNetwork`, `Program`, `Offer`, `TermsEvidence`, `TermsResearchRun`, `CommissionFact`.

Evidence is proposal-first. A collected or manually entered record never changes a Program permission. An operator review may accept high-confidence authoritative evidence; the reviewed canonical scope is then reconciled from fresh accepted evidence without erasing unrelated migrated values. Divergent accepted decisions resolve to `CONFLICT` and produce a red warning.

Dashboard terms status and Terms Warning evaluation do not trust canonical fields alone. Both require stored, accepted, fresh, authoritative evidence for every relevant scope, so legacy values or client-supplied claims cannot create `TERMS_OK`. A warning never removes the project from analysis.

Commission claims are stored in `CommissionFact`, not `TermsEvidence`, so economics facts cannot grant advertising permission. Divergent high-confidence official commission claims resolve to `CONFLICT` without selecting a winner.

### Paid Media

`AdsAccount`, `Campaign`, `CampaignProgramLink`, `CampaignDailyStat`, `Click`, `Spend`.

Google Ads CSV imports upsert by account/campaign and campaign/date/source. Campaign exposure is computed independently from terms permission: all campaigns remain visible while their risk status is green, amber or red.

### Affiliate Revenue

`Conversion`, `Commission`, `Payout`.

### Operations

`SyncRun`, `AuditLog`.

## 4. Data quality labels

- `OBSERVED`: lấy trực tiếp từ nguồn.
- `MATCHED`: gắn qua khóa tin cậy như GCLID/SubID.
- `MODELED`: ước lượng, không được hiển thị như actual.
- `UNKNOWN`: chưa đủ dữ liệu.

## 5. Connector contract

Mỗi connector phải:

1. Có unique external transaction ID.
2. Hỗ trợ pagination/cursor.
3. Idempotent khi chạy lại cùng khoảng thời gian.
4. Không nuốt lỗi.
5. Ghi `SyncRun` với status và freshness.
6. Giữ raw payload hash để kiểm toán.
7. Không để secrets trong static root.

## 6. Security baseline

- Bind mặc định `127.0.0.1`.
- Không CORS wildcard.
- Static server chỉ phục vụ `apps/web`.
- `.env`, token và database bị loại khỏi package/repository.
- Update payloads cannot contain `data/`, `backups/`, `.env`, `.venv`, `logs/` or `legacy/`.
- Update creates a SQLite API backup after WAL checkpoint, verifies row counts/checksum/integrity, then restores both database and overwritten files on failure.
- Giai đoạn tiếp theo dùng macOS Keychain cho OAuth refresh token.
