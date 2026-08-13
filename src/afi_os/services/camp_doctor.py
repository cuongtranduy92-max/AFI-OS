"""Camp Doctor — chẩn đoán camp, benchmark, khuyến nghị tối ưu, canh quy tắc 20%.

Nguồn luật: giáo trình buổi 9 (8 lỗi camp), 13 (CTR/$-ref bands, tối ưu 5 bước),
14 (bid thấp + đối thủ = vòng xoáy chết camp), 15 (4 trạng thái từ khoá), spec Trang 3.
Thuần deterministic — nhận số liệu, trả chẩn đoán. Không gọi API, không chạm DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ---- Ngưỡng chốt (spec Tran + giáo trình) ----
CTR_WARN = 40.0          # spec Tran: CTR < 40% phải cảnh báo
CTR_ABNORMAL_LOW = 15.0  # buổi 13: <15% là bất thường
CTR_CLICK_FRAUD = 80.0   # buổi 15: >80% nghi click tặc
COST_PER_REF_GOOD = 4.0  # spec Tran: <$4/ref là đạt
COST_PER_REF_MID = 7.0
COST_PER_REF_HIGH = 10.0
MIN_CLICKS_FOR_JUDGMENT = 150   # buổi 13: 150 click mới đủ cơ sở kết luận
LEARNING_DAYS = 7               # tuần đầu Google học — không can thiệp
MAX_CHANGE_PCT = 20.0           # quy tắc 20%/24h
NEW_CAMP_HOURS = 24

# 4 trạng thái từ khoá (buổi 15)
KW_SHOWING = "SHOWING"                 # "Quảng cáo của bạn đang hiển thị"
KW_SOMETIMES = "SOMETIMES"             # "Đôi khi có thể hiển thị"
KW_URL_COMPETITION = "URL_COMPETITION" # "Cạnh tranh URL"
KW_UNKNOWN = "UNKNOWN"                 # "Không rõ nguyên nhân"

KEYWORD_STATE_ADVICE = {
    KW_SHOWING: ("ok", "Đang hiển thị tốt — không cần làm gì."),
    KW_SOMETIMES: ("warning",
        "Đối thủ trả giá thầu cao hơn hoặc camp chưa học xong → TĂNG GIÁ THẦU."),
    KW_URL_COMPETITION: ("warning",
        "Cạnh tranh URL: tăng lần lượt (1) giá thầu → (2) ngân sách ngày → (3) tiền nạp."),
    KW_UNKNOWN: ("error",
        "Không rõ nguyên nhân: thường là đang review camp / hồ sơ thanh toán yếu / hết tiền nạp. "
        "Xử lý: lên 1 cam mồi kích hoạt sau 48h, hoặc đổi 1 chi tiết content để ép duyệt lại."),
}


@dataclass(frozen=True)
class CampaignSnapshot:
    campaign_id: int
    name: str
    started_at: datetime
    impressions: int
    clicks: int
    cost_usd: float
    refs: int | None = None                 # None = chưa có dữ liệu ref
    keyword_states: tuple[str, ...] = ()    # trạng thái các từ khoá
    competitors_on_keyword: bool = False    # có đối thủ chạy cùng từ khoá
    avg_cpc_usd: float | None = None
    top_page_bid_low_usd: float | None = None
    device_stats: tuple[dict, ...] = ()     # {"device","clicks","ctr","cost"}
    geo_stats: tuple[dict, ...] = ()        # {"country","clicks","ctr","cost","refs"}
    search_terms: tuple[dict, ...] = ()     # {"term","clicks","cost","refs"}


@dataclass(frozen=True)
class ChangeEvent:
    field_name: str        # budget | bid | deposit
    old_value: float
    new_value: float
    changed_at: datetime


@dataclass(frozen=True)
class Finding:
    level: str      # ok | info | warning | error
    code: str
    message: str
    action: str = ""


@dataclass
class Diagnosis:
    campaign_id: int
    status: str                      # HEALTHY | LEARNING | NEEDS_ATTENTION | CRITICAL
    ctr_pct: float | None
    cost_per_ref: float | None
    age_days: int
    findings: list[Finding] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "status": self.status,
            "ctr_pct": self.ctr_pct,
            "cost_per_ref": self.cost_per_ref,
            "age_days": self.age_days,
            "findings": [f.__dict__ for f in self.findings],
            "next_actions": self.next_actions,
        }


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 2) if whole else None


def check_twenty_percent_rule(events: list[ChangeEvent], now: datetime) -> list[Finding]:
    """Quy tắc 20%: mọi thay đổi (ngân sách/giá thầu/nạp tiền) ≤20% mỗi 24h."""
    findings: list[Finding] = []
    window = now - timedelta(hours=24)
    recent = [e for e in events if e.changed_at >= window]
    by_field: dict[str, list[ChangeEvent]] = {}
    for e in recent:
        by_field.setdefault(e.field_name, []).append(e)

    for field_name, items in by_field.items():
        items.sort(key=lambda x: x.changed_at)
        start = items[0].old_value
        end = items[-1].new_value
        if start <= 0:
            continue
        change_pct = (end - start) / start * 100
        if abs(change_pct) > MAX_CHANGE_PCT:
            findings.append(Finding(
                "error", "TWENTY_PCT_VIOLATION",
                f"{field_name} đổi {change_pct:+.0f}% trong 24h "
                f"(giới hạn ±{MAX_CHANGE_PCT:.0f}%) — "
                "Google dễ đưa camp vào review.",
                f"Đưa {field_name} về mức ≤{MAX_CHANGE_PCT:.0f}% so với {start:g} và chờ 24h.",
            ))
        if len(items) >= 4:
            findings.append(Finding(
                "warning", "CHANGE_CHURN",
                f"{field_name} bị chỉnh {len(items)} lần trong 24h — "
                "Google thích ổn định, tránh giật cục.",
                "Giảm tần suất chỉnh; mỗi lần chỉnh chờ đủ 24h xem kết quả.",
            ))
    return findings


def diagnose_campaign(
    snap: CampaignSnapshot,
    changes: list[ChangeEvent] | None = None,
    now: datetime | None = None,
) -> Diagnosis:
    now = now or datetime.now(snap.started_at.tzinfo)
    age_days = max(0, (now - snap.started_at).days)
    age_hours = (now - snap.started_at).total_seconds() / 3600
    ctr = _pct(snap.clicks, snap.impressions)
    cpr = round(snap.cost_usd / snap.refs, 2) if snap.refs else None

    findings: list[Finding] = []
    actions: list[str] = []

    # --- Camp mới: đang học, KHÔNG can thiệp (buổi 14) ---
    if age_hours < NEW_CAMP_HOURS:
        findings.append(Finding("info", "LEARNING_24H",
            "Camp mới <24h — Google đang học, cắn ít là bình thường.",
            "Chưa can thiệp. Đợi đủ 24–48h."))
        return Diagnosis(snap.campaign_id, "LEARNING", ctr, cpr, age_days, findings,
                         ["Để yên, kiểm tra lại sau 24–48h"])
    if age_days < LEARNING_DAYS:
        findings.append(Finding("info", "LEARNING_WEEK",
            f"Camp mới {age_days} ngày — tuần đầu Google còn học, chỉ số chưa ổn định.",
            "Hạn chế chỉnh sửa; chờ hết tuần đầu."))

    # --- Trạng thái từ khoá (buổi 15) ---
    for state in set(snap.keyword_states):
        level, msg = KEYWORD_STATE_ADVICE.get(state, ("info", ""))
        if state != KW_SHOWING and msg:
            findings.append(Finding(level, f"KEYWORD_{state}", msg))

    # --- CTR bands ---
    if ctr is None:
        findings.append(Finding("info", "NO_IMPRESSIONS",
            "Chưa có lượt hiển thị — kiểm tra trạng thái từ khoá & duyệt camp."))
    else:
        if ctr >= CTR_CLICK_FRAUD:
            findings.append(Finding("error", "CLICK_FRAUD_SUSPECT",
                f"CTR {ctr:.0f}% ≥{CTR_CLICK_FRAUD:.0f}% + lượt nhấp bất thường → nghi CLICK TẶC.",
                "Gửi khiếu nại Google kèm lịch sử; Google hoàn tiền nếu xác nhận."))
        elif ctr < CTR_ABNORMAL_LOW:
            findings.append(Finding("error", "CTR_ABNORMAL",
                f"CTR {ctr:.1f}% < {CTR_ABNORMAL_LOW:.0f}% — bất thường với brand keyword.",
                "Soát: từ khoá có nằm trong tiêu đề không (nhảy xanh)? "
                "Nội dung có đúng thương hiệu không?"))
        elif ctr < CTR_WARN:
            findings.append(Finding("warning", "CTR_LOW",
                f"CTR {ctr:.1f}% < {CTR_WARN:.0f}% (ngưỡng cảnh báo).",
                "Kiểm tra vị trí hiển thị và giá thầu."))
        else:
            findings.append(Finding("ok", "CTR_OK", f"CTR {ctr:.1f}% — tốt."))

        # Bid thấp + có đối thủ = vòng xoáy chết camp (buổi 14)
        if ctr < CTR_WARN and snap.competitors_on_keyword:
            findings.append(Finding("error", "LOW_BID_WITH_COMPETITOR",
                "CTR thấp VÀ có đối thủ chạy cùng từ khoá: khách bấm top 1 → CTR tụt → "
                "Google giảm hiển thị → vòng xoáy chết camp.",
                "NÂNG GIÁ THẦU (đây không phải camp hỏng). Mỗi lần ≤20%/24h."))
            actions.append("Nâng giá thầu ≤20% để giành vị trí trên")

    # --- Chi phí / ref ---
    if snap.refs is None:
        findings.append(Finding("info", "NO_REF_DATA",
            "Chưa có dữ liệu ref — chưa kết luận được hiệu quả."))
    elif snap.refs == 0:
        if snap.clicks >= MIN_CLICKS_FOR_JUDGMENT:
            findings.append(Finding("warning", "NO_REF_AFTER_CLICKS",
                f"{snap.clicks} click chưa ra ref (chuẩn ~150 click/sale).",
                "Soát lại chất lượng traffic + bẫy free-tier của dự án. "
                "Nhớ: conversion có thể trễ ~nửa tháng."))
        else:
            findings.append(Finding("info", "TOO_EARLY",
                f"Mới {snap.clicks}/{MIN_CLICKS_FOR_JUDGMENT} click — chưa đủ cơ sở kết luận.",
                "Chạy tiếp cho đủ dữ liệu."))
    else:
        if cpr <= COST_PER_REF_GOOD:
            findings.append(Finding(
                "ok", "CPR_GOOD", f"${cpr}/ref — đạt (<${COST_PER_REF_GOOD:.0f})."
            ))
        elif cpr <= COST_PER_REF_MID:
            findings.append(Finding("warning", "CPR_MID", f"${cpr}/ref — trung bình.",
                "Tối ưu: thêm từ khoá phủ định, cắt thiết bị/vị trí kém."))
        elif cpr <= COST_PER_REF_HIGH:
            findings.append(Finding("warning", "CPR_HIGH", f"${cpr}/ref — cao.",
                "Ép giá thầu xuống + lọc mạnh nguồn click rác."))
        else:
            findings.append(Finding("error", "CPR_CRITICAL", f"${cpr}/ref — quá cao.",
                "Cân nhắc dừng camp hoặc xem lại dự án (hoa hồng có bù nổi không?)."))

    # --- Gợi ý ép thầu khi cắn quá đắt so với top-page (buổi 14) ---
    if snap.avg_cpc_usd and snap.top_page_bid_low_usd:
        target = round(snap.top_page_bid_low_usd * 0.5, 3)
        if snap.avg_cpc_usd > snap.top_page_bid_low_usd:
            findings.append(Finding("warning", "BID_ABOVE_TOPPAGE",
                f"CPC thực ${snap.avg_cpc_usd} > top-page thấp ${snap.top_page_bid_low_usd}.",
                f"Thử ép thầu về ~50% top-page thấp (${target}); "
                "vẫn cắn nhiều thì chia đôi tiếp, sàn $0,01."))
            actions.append(f"Ép giá thầu về ~${target}")

    # --- Tối ưu theo dữ liệu: từ khoá rác / thiết bị / vị trí (chỉ khi ĐỦ dữ liệu) ---
    if snap.clicks >= MIN_CLICKS_FOR_JUDGMENT:
        waste = [t for t in snap.search_terms
                 if (t.get("clicks") or 0) >= 5 and not (t.get("refs") or 0)]
        if waste:
            names = ", ".join(f'"{t["term"]}"' for t in waste[:5])
            findings.append(Finding("warning", "WASTE_SEARCH_TERMS",
                f"{len(waste)} cụm từ tốn click không ra ref: {names}.",
                "Thêm vào từ khoá PHỦ ĐỊNH (dạng cụm)."))
            actions.append("Thêm từ khoá phủ định cho các cụm rác")

        bad_dev = [d for d in snap.device_stats
                   if (d.get("clicks") or 0) >= 20 and (d.get("ctr") or 0) < CTR_ABNORMAL_LOW]
        for d in bad_dev:
            findings.append(Finding("warning", "WEAK_DEVICE",
                f"Thiết bị {d['device']}: CTR {d['ctr']:.1f}% với {d['clicks']} click.",
                f"Cân nhắc tắt/giảm giá thầu cho {d['device']}."))

        bad_geo = [g for g in snap.geo_stats
                   if (g.get("cost") or 0) >= 10 and not (g.get("refs") or 0)]
        for g in bad_geo[:5]:
            findings.append(Finding("warning", "WEAK_GEO",
                f"{g['country']}: chi ${g['cost']:.0f} chưa ra ref.",
                f"Cân nhắc loại {g['country']} khỏi vị trí target."))
    else:
        findings.append(Finding("info", "OPTIMIZE_TOO_EARLY",
            "Chưa đủ dữ liệu để cắt thiết bị/vị trí — cắt sớm dễ giết camp đang học."))

    # --- Quy tắc 20% ---
    findings.extend(check_twenty_percent_rule(changes or [], now))

    # --- Kết luận trạng thái ---
    if any(f.level == "error" for f in findings):
        status = "CRITICAL"
    elif any(f.level == "warning" for f in findings):
        status = "NEEDS_ATTENTION"
    elif age_days < LEARNING_DAYS:
        status = "LEARNING"
    else:
        status = "HEALTHY"

    for f in findings:
        if f.action and f.action not in actions:
            actions.append(f.action)

    return Diagnosis(snap.campaign_id, status, ctr, cpr, age_days, findings, actions)
