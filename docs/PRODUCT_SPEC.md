# PRODUCT SPEC — AFI-OS Internal Production 1.0

## 1. Mục tiêu

Một người có thể tìm cơ hội affiliate, kiểm chứng điều khoản, đánh giá economics, tạo campaign draft, nối chi phí với commission và điều hành nhiều campaign mà không phải nhập tay lặp lại.

## 2. Phạm vi 1.0

- Single user, local-first trên Mac.
- SQLite làm nguồn dữ liệu chuẩn.
- Google Ads read-only trước; write qua approval workflow sau.
- Một affiliate connector production trước + CSV universal importer.
- Không xây SaaS/multi-tenant trong 1.0.
- Không tự launch, đổi bid hoặc đổi budget production trong 1.0.

## 3. Chu trình nghiệp vụ

```text
⓪ Truy vết quảng cáo
→ ① Khám phá và thẩm định
→ ② Compliance / đăng ký chương trình
→ ③ Economics và test plan
→ ④ Campaign draft
→ ⑤ Tracking và attribution
→ ⑥ Reconciliation và finance
→ ⑦ Command Center và alerts
```

## 4. Module ⓪ — Ad Intelligence & Advertiser Graph

### Mục đích

- Nhập domain hoặc advertiser làm seed.
- Lưu snapshot từ Google Ads Transparency Center bằng thao tác chủ động của người dùng.
- Xây graph `Advertiser ↔ Project`.
- Theo advertiser sang các project khác và tiếp tục mở rộng graph.
- Đếm **advertiser độc lập**, không nhầm với một advertiser tạo nhiều ad creatives.

### Chỉ số chính

- `distinct_advertisers`
- `active_advertisers_30d`
- `new_advertisers_30d`
- `top_advertiser_share`
- `independent_advertiser_score`
- `first_seen_at / last_seen_at`

### Ranh giới

- Không tự vượt CAPTCHA.
- Không crawl hàng loạt hoặc chạy nền trên dịch vụ Google.
- Mọi snapshot phải có URL nguồn, thời điểm và raw evidence.
- `AFFILIATE_OR_PUBLISHER` chỉ là phân loại có confidence; không mặc định mọi advertiser là affiliate.

## 5. Financial Truth Layer

### Commission state machine

```text
PENDING → APPROVED → LOCKED → PAID
    ↘ REJECTED / REFUNDED / CHARGEBACK
```

- `PENDING` chỉ dùng cho forecast sau khi nhân approval probability.
- Recognized revenue dùng `APPROVED + LOCKED + PAID` theo accounting policy.
- Cash received chỉ dùng `PAID`.
- Không phân bổ revenue campaign theo tỷ lệ spend.
- Không truy được click thì giữ `UNATTRIBUTED`, không tự bịa mapping.

## 6. Compliance gate

- `PROHIBITED`: block.
- `AMBIGUOUS`: block pending evidence.
- `NOT_CHECKED`: block pending evidence.
- `APPROVAL_REQUIRED`: block cho tới khi có chấp thuận bằng văn bản.
- Brand bidding cần bằng chứng tươi, confidence cao và đúng phạm vi.
- Non-brand, direct link, dùng trademark trong ad copy và geo được đánh giá riêng.

## 7. Economics engine

Không dùng một giả định cố định cho mọi offer. Hệ thống tính:

```text
P(sale | ad click)
= P(outbound click | ad click) × P(sale | merchant session)

Expected Commission LTV
= commission/period × expected active periods × approval × (1-refund)

Break-even CPC
= P(sale | ad click) × Expected Commission LTV

Safe CPC
= Break-even CPC × (1-target margin) × confidence discount
```

Hỗ trợ:

- One-time.
- Recurring giới hạn N tháng.
- Recurring lifetime với forecast horizon và churn.
- Flat commission hoặc commission rate.

## 8. Điều kiện nghiệm thu 1.0

1. Google Ads spend thật tự đồng bộ.
2. Ít nhất một affiliate source hoạt động end-to-end.
3. Transaction import idempotent.
4. Pending không đi vào realized/cash profit.
5. Không còn modeled revenue hiển thị như actual.
6. Program mơ hồ bị block.
7. Mỗi số tiền có amount, currency, state, source và timestamp.
8. Connector lỗi hiển thị `PARTIAL / STALE / AUTH_FAILED / ERROR`.
9. Credential không nằm trong web root hoặc Git.
10. Backup/restore được kiểm thử.
11. Shadow mode ít nhất 2 tuần.
12. Audit trail có thể truy lại quyết định quan trọng.
