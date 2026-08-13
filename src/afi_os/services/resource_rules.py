"""Rule engine module Tài nguyên (tab 5): nuôi email + cảnh báo tài nguyên.

Luật nghiệp vụ (buổi 1, 2, 4, 14 + thiết kế module-quan-ly-tai-nguyen.md):
- Nuôi email: SOAK 48h → DECLARED (khai thật + 2FA + payment) → INTERACTING
  (≤3 tác vụ/ngày) → CHÍN ở 21 ngày; mỗi lần đổi thiết bị +2 ngày.
- Email "bẩn": từng chạy ngách tài chính/casino/forex/crypto → Google dễ gắn nhãn,
  camp không phân phối (case Ngân) → cấm gắn cho dự án mới.
- Thiếu tài nguyên: 1 email chín nối được 2–3 tài khoản invoice (tính thận trọng = 2);
  kế hoạch camp tháng vượt sức chứa → cảnh báo (case Nghĩa).
- Concentration PayPal: ≥$4.000/tháng cảnh báo, ≥$5.000 nguy cơ limit 6 tháng (lỗi).
- 1 thẻ ↔ 1 cổng; thông tin phải ĐỒNG NHẤT.
- 1 tài khoản Ads = 1 camp = 1 dự án (enforce cứng).
Thuần deterministic, không chạm DB — mọi hàm nhận dữ liệu vào, trả kết quả ra.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

SOAK_HOURS = 48
CHIN_DAYS = 21
DEVICE_CHANGE_PENALTY_DAYS = 2
MAX_TASKS_PER_DAY = 3
ACCOUNTS_PER_EMAIL = 2
PAYPAL_WARN_USD = 4000
PAYPAL_LIMIT_USD = 5000
MIN_EMAIL_POOL = 15

STAGE_SOAK = "SOAK"
STAGE_DECLARED = "DECLARED"
STAGE_INTERACTING = "INTERACTING"
STAGE_CHIN = "CHIN"

RESTRICTED_NICHES = {
    "finance", "tài chính", "casino", "forex", "crypto", "coin",
    "trading", "betting", "cờ bạc", "gambling",
}

NURTURE_TASK_POOL = [
    "Xem YouTube 10–15 phút (đăng nhập email này)",
    "Mở Google Drive, tạo/sửa 1 tài liệu",
    "Đọc tin trên CoinMarketCap 5 phút",
    "Gửi 1 mail qua lại với email khác trong hệ thống",
    "Tìm kiếm Google vài chủ đề thường ngày",
    "Xem Google Maps, lưu 1 địa điểm",
    "Mở Google Photos / Calendar tạo 1 sự kiện",
]


@dataclass(frozen=True)
class EmailInfo:
    email_id: int
    address: str
    created_at: datetime
    declared_done: bool
    device_changes: int = 0
    usage_history: tuple[str, ...] = ()
    status_override: str | None = None


@dataclass(frozen=True)
class AdsAccountInfo:
    account_id: int
    email_id: int | None
    project_ids: tuple[int, ...] = ()
    state: str = "READY"
    display_name: str | None = None


@dataclass(frozen=True)
class ResourceInfo:
    resource_id: int
    type: str
    label: str = ""
    monthly_in_usd: float = 0.0
    linked_gateways: tuple[str, ...] = ()
    owner_name: str | None = None


@dataclass(frozen=True)
class ResourceAlert:
    level: str
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class NurtureStatus:
    stage: str
    age_days: int
    chin_eta_days: int
    is_chin: bool
    is_dirty: bool
    tasks_today: tuple[str, ...]


def _age_days(created_at: datetime, today: date) -> int:
    timestamp = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=UTC)
    created_date = timestamp.astimezone().date()
    return max(0, (today - created_date).days)


def is_dirty(email: EmailInfo) -> bool:
    history = {h.strip().lower() for h in email.usage_history}
    return any(h in RESTRICTED_NICHES for h in history)


def nurture_status(email: EmailInfo, today: date) -> NurtureStatus:
    """Tính giai đoạn nuôi + tác vụ hôm nay cho 1 email."""
    age = _age_days(email.created_at, today)
    required = CHIN_DAYS + email.device_changes * DEVICE_CHANGE_PENALTY_DAYS
    dirty = is_dirty(email)

    if age * 24 < SOAK_HOURS:
        stage = STAGE_SOAK
        tasks: tuple[str, ...] = ("Ngâm yên — KHÔNG thao tác gì",)
    elif not email.declared_done:
        stage = STAGE_DECLARED
        tasks = ("Khai báo thông tin THẬT + bật 2FA + thêm payment method",)
    elif age < required:
        stage = STAGE_INTERACTING
        seed = (email.email_id * 7 + today.toordinal()) % len(NURTURE_TASK_POOL)
        picked = [
            NURTURE_TASK_POOL[(seed + i * 2) % len(NURTURE_TASK_POOL)]
            for i in range(MAX_TASKS_PER_DAY)
        ]
        seen: list[str] = []
        for task in picked:
            if task not in seen:
                seen.append(task)
        tasks = tuple(seen[:MAX_TASKS_PER_DAY])
    else:
        stage = STAGE_CHIN
        tasks = ()

    return NurtureStatus(
        stage=stage,
        age_days=age,
        chin_eta_days=max(0, required - age),
        is_chin=stage == STAGE_CHIN,
        is_dirty=dirty,
        tasks_today=tasks,
    )


def eligible_for_campaign(email: EmailInfo, today: date) -> bool:
    """Email đủ điều kiện gắn tài khoản Ads lên camp: CHÍN + KHÔNG bẩn + không khoá."""
    if email.status_override == "LOCKED":
        return False
    status = nurture_status(email, today)
    return status.is_chin and not status.is_dirty


def build_alerts(
    emails: list[EmailInfo],
    accounts: list[AdsAccountInfo],
    resources: list[ResourceInfo],
    planned_camps_this_month: int,
    today: date,
) -> list[ResourceAlert]:
    """Toàn bộ cảnh báo tài nguyên — chạy mỗi lần mở tab 5 hoặc trước khi lên camp."""
    alerts: list[ResourceAlert] = []
    email_by_id = {email.email_id: email for email in emails}

    for account in accounts:
        if len(account.project_ids) > 1:
            alerts.append(ResourceAlert(
                "error", "ONE_ACCOUNT_ONE_PROJECT",
                account.display_name or f"TK Ads #{account.account_id}",
                f"Đang gắn {len(account.project_ids)} dự án — vi phạm 1 TK = 1 camp = 1 dự án. "
                "Chủ 1 dự án đổi web → Google quét lại → CHẾT CẢ HAI.",
            ))

    for account in accounts:
        email = email_by_id.get(account.email_id) if account.email_id else None
        if email and is_dirty(email):
            alerts.append(ResourceAlert(
                "error", "DIRTY_EMAIL_IN_USE", email.address,
                "Email từng chạy ngách hạn chế (tài chính/casino...) — Google dễ gắn nhãn, "
                "camp không phân phối. Không dùng cho dự án mới.",
            ))

    chin_clean = [email for email in emails if eligible_for_campaign(email, today)]
    capacity = len(chin_clean) * ACCOUNTS_PER_EMAIL
    if planned_camps_this_month > capacity:
        need = -(-max(0, planned_camps_this_month - capacity) // ACCOUNTS_PER_EMAIL)
        alerts.append(ResourceAlert(
            "warning", "EMAIL_SHORTAGE", "kho email",
            f"Kế hoạch {planned_camps_this_month} camp nhưng sức chứa chỉ "
            f"{capacity} ({len(chin_clean)} email chín × {ACCOUNTS_PER_EMAIL}). "
            f"Cần nuôi thêm ~{need} email (chín mất {CHIN_DAYS} ngày — bắt đầu ngay).",
        ))
    if len(emails) < MIN_EMAIL_POOL:
        alerts.append(ResourceAlert(
            "info", "EMAIL_POOL_SMALL", "kho email",
            f"Tổng {len(emails)} email < chuẩn {MIN_EMAIL_POOL}–20 theo giáo trình.",
        ))

    for resource in resources:
        if resource.type.lower() == "paypal":
            if resource.monthly_in_usd >= PAYPAL_LIMIT_USD:
                alerts.append(ResourceAlert(
                    "error", "PAYPAL_CONCENTRATION",
                    resource.label or f"PayPal #{resource.resource_id}",
                    f"Nhận ${resource.monthly_in_usd:,.0f}/tháng ≥ ${PAYPAL_LIMIT_USD:,} — "
                    "nguy cơ LIMIT 6 tháng. Chia tiền sang tài khoản khác NGAY.",
                ))
            elif resource.monthly_in_usd >= PAYPAL_WARN_USD:
                alerts.append(ResourceAlert(
                    "warning", "PAYPAL_CONCENTRATION",
                    resource.label or f"PayPal #{resource.resource_id}",
                    f"Nhận ${resource.monthly_in_usd:,.0f}/tháng — gần ngưỡng limit "
                    f"(${PAYPAL_LIMIT_USD:,}). Chuẩn bị chia dòng tiền.",
                ))

    for resource in resources:
        if resource.type.lower() == "card" and len(resource.linked_gateways) > 1:
            alerts.append(ResourceAlert(
                "warning", "CARD_MULTI_GATEWAY",
                resource.label or f"Thẻ #{resource.resource_id}",
                f"Thẻ đang gắn {len(resource.linked_gateways)} cổng "
                f"({', '.join(resource.linked_gateways)}) — quy tắc 1 thẻ ↔ 1 cổng.",
            ))

    owners = {resource.owner_name.strip().lower() for resource in resources if resource.owner_name}
    if len(owners) > 1:
        alerts.append(ResourceAlert(
            "warning", "CONSISTENCY", "hồ sơ",
            f"Phát hiện {len(owners)} tên chủ khác nhau trên các tài nguyên — "
            "thông tin phải ĐỒNG NHẤT mọi nơi.",
        ))

    return alerts


def selectable_accounts(
    emails: list[EmailInfo],
    accounts: list[AdsAccountInfo],
    today: date,
) -> list[int]:
    """Tài khoản được phép hiện ở Bước 2: email chín sạch, account trống và sẵn sàng."""
    email_by_id = {email.email_id: email for email in emails}
    ready_states = {"READY", "CHỌN DỰ ÁN", "CHON_DU_AN"}
    output: list[int] = []
    for account in accounts:
        if account.project_ids or account.state.upper() not in ready_states:
            continue
        email = email_by_id.get(account.email_id) if account.email_id else None
        if email is None or not eligible_for_campaign(email, today):
            continue
        output.append(account.account_id)
    return output
