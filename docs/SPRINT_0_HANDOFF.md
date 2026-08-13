# SPRINT 0 HANDOFF

## Hoàn thành

- Legacy v3 được đóng băng ở Git tag `legacy-v3`.
- Nhánh triển khai mới: `replatform-v1`.
- Data core có migration, constraints và audit entities.
- Module ⓪ Truy vết quảng cáo đã có vertical slice chạy được.
- Compliance gate và economics engine đã có API + UI + tests.
- Capture Helper cho Chrome đã được tạo.

## Phần giữ lại từ legacy

- `legacy/v3/afi-os.html`
- Campaign/asset generator làm nguồn tham chiếu.
- Tài liệu nghiệp vụ và các thẩm định.

## Phần không dùng làm production core

- `localStorage` là database.
- `afi_sync.py` connector demo.
- Pending + approved + paid gộp thành một revenue.
- Revenue campaign chia theo spend.
- `config.json` plaintext trong static directory.

## Blocker ngoài code

1. Google Ads Developer Token và OAuth.
2. Một network thật hoặc CSV report thật.
3. Snapshot Ads Transparency thật.

## Đề xuất Sprint 1

Thứ tự bắt buộc:

1. `TermsEvidence` CRUD + review queue.
2. Universal CSV commission importer với idempotency.
3. Attribution/reconciliation states.
4. Backup/restore.
5. Google Ads read-only adapter bằng fixture/contract test trước, credential thật sau.
