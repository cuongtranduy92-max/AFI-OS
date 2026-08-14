"""Trích xuất dữ kiện affiliate từ text trang web bằng LLM — đề xuất, người duyệt.

Chống bịa 3 lớp: (1) temperature=0 + JSON schema chặt; (2) mọi field bắt buộc kèm
trích dẫn nguyên văn; (3) code verify trích dẫn tồn tại trong text nguồn —
không khớp thì loại field. Không biết = null, không đoán.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MAX_PAGE_CHARS = 15_000
PPC_UNDISCLOSED_VI = "Trang không nêu quy định PPC — cần hỏi support trước khi chạy."
PPC_CHECKLIST_KEYS = (
    "search_ads_allowed",
    "brand_keyword_bidding",
    "direct_linking",
    "brand_in_ad_copy",
    "brand_in_display_url",
    "trademark_plus_coupon",
    "own_landing_page_required",
    "geo_restrictions",
    "penalty_if_violated",
)
PPC_CHECKLIST_SCHEMA = """
  "ppc_policy": {
    "search_ads_allowed":        {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "brand_keyword_bidding":     {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "direct_linking":            {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "brand_in_ad_copy":          {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "brand_in_display_url":      {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "trademark_plus_coupon":     {"status": "ALLOWED|BANNED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "own_landing_page_required": {"status": "REQUIRED|NOT_REQUIRED|NOT_STATED", "quote": "...", "quote_vi": "...", "note_vi": "..."},
    "geo_restrictions":          {"status": "YES|NO|NOT_STATED", "detail_vi": "...", "quote": "...", "quote_vi": "..."},
    "penalty_if_violated":       {"detail_vi": "hậu quả nếu vi phạm", "quote": "...", "quote_vi": "..."},
    "overall_verdict_vi": "Kết luận 2–3 câu: có nên chạy Google Ads cho dự án này không, cần tránh gì."
  }
"""

SYSTEM_PROMPT = """Bạn là bộ trích xuất dữ kiện chương trình affiliate. Chỉ trả về JSON đúng schema.
Luật sắt:
- CHỈ dùng thông tin có trong văn bản được cung cấp. KHÔNG dùng kiến thức ngoài.
- Field nào văn bản không nói rõ → null. TUYỆT ĐỐI không đoán.
- Mỗi field có giá trị PHẢI kèm "quote": câu NGUYÊN VĂN (copy đúng từng ký tự) từ văn bản chứng minh giá trị đó.
- Nếu hoa hồng ghi "up to"/"lên đến" → rate_is_upper_bound=true.
- commission_type: ONE_TIME | RECURRING_LIMITED (ghi số tháng) | RECURRING_LIFETIME | HYBRID | null.
- "quote" giữ NGUYÊN VĂN ngôn ngữ gốc, KHÔNG dịch, KHÔNG sửa.
- Thêm "quote_vi": bản dịch tiếng Việt của quote, dịch sát nghĩa, giữ nguyên số/tên riêng.
- Thêm "summary_vi": tóm tắt tiếng Việt dễ hiểu cho người không giỏi tiếng Anh.
- Với mỗi mục trong ppc_policy: nếu văn bản KHÔNG nói rõ → status "NOT_STATED" và quote để rỗng.
  TUYỆT ĐỐI KHÔNG suy diễn "không cấm nghĩa là được phép".
- "note_vi": giải thích ngắn bằng tiếng Việt cho người không rành tiếng Anh, nói rõ điều này ảnh hưởng gì tới việc chạy Google Ads.
- Trả về DUY NHẤT JSON, không giải thích."""

USER_PROMPT_TEMPLATE = """Văn bản các trang của dự án "{domain}" (đã cắt gọn):

<pages>
{pages_text}
</pages>

Trích xuất theo schema JSON sau (giá trị null nếu không chắc):
{{
  "commission": {{
    "type": "...", "percent": 30.0, "rate_is_upper_bound": false,
    "recurring_months": null, "flat_usd": null,
    "quote": "câu nguyên văn (KHÔNG dịch)",
    "quote_vi": "bản dịch tiếng Việt của câu trên",
    "summary_vi": "tóm tắt tiếng Việt về hoa hồng"
  }},
  "packages": [
    {{"name": "Standard", "price_usd": 28.0, "period": "month",
      "quote": "câu nguyên văn", "quote_vi": "bản dịch"}}
  ],
  "payment": {{
    "gateways": ["PayPal"], "min_payment_usd": 50.0, "clear_days": 30,
    "cookie_days": 30, "net_platform": "Rewardful",
    "quote": "câu nguyên văn", "quote_vi": "bản dịch",
    "summary_vi": "tóm tắt tiếng Việt: trả qua đâu, tối thiểu bao nhiêu, bao lâu nhận tiền"
  }},
  "terms": {{
    "ads_allowed": true, "brand_bid_restricted": false,
    "direct_link_allowed": null, "trademark_plus_coupon_banned": null,
    "quote": "câu nguyên văn về quy định quảng cáo", "quote_vi": "bản dịch",
    "summary_vi": "tóm tắt tiếng Việt quy định quảng cáo"
  }},
{ppc_checklist_schema},
  "confidence": 0.0
}}"""


@dataclass(frozen=True)
class ExtractedFact:
    scope: str            # COMMISSION | PACKAGES | PAYMENT | TERMS
    payload: dict         # dữ liệu đã lọc
    quote: str            # trích dẫn ĐÃ kiểm chứng
    confidence: float
    quote_vi: str = ""
    summary_vi: str = ""


@dataclass
class ExtractionResult:
    facts: list[ExtractedFact] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)   # lý do loại từng phần
    raw: dict | None = None


def _page_parts(page: tuple[str, ...]) -> tuple[str, str, str]:
    url, text = page[0], page[1]
    role = page[2] if len(page) > 2 else "other"
    return url, text, role


def build_extraction_prompt(domain: str, pages: list[tuple[str, ...]]) -> tuple[str, str]:
    """pages: [(url, text, role)] → (system, user). Backward-compatible with pairs."""
    blocks = []
    for page in pages:
        url, text, role = _page_parts(page)
        cleaned = re.sub(r"\s+", " ", text or "").strip()[:MAX_PAGE_CHARS]
        blocks.append(f"### URL: {url} [role: {role}]\n{cleaned}")
    user = USER_PROMPT_TEMPLATE.format(
        domain=domain,
        pages_text="\n\n".join(blocks),
        ppc_checklist_schema=PPC_CHECKLIST_SCHEMA.strip().rstrip(","),
    )
    return SYSTEM_PROMPT, user


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _quote_in_sources(quote: str, pages: list[tuple[str, ...]]) -> bool:
    """Trích dẫn phải xuất hiện (chuẩn hoá khoảng trắng, bỏ hoa thường) trong ít nhất 1 trang."""
    q = _norm(quote)
    if len(q) < 15:          # trích dẫn quá ngắn = không đủ bằng chứng
        return False
    return any(q in _norm(_page_parts(page)[1]) for page in pages)


def _quote_source_url(quote: str, pages: list[tuple[str, ...]]) -> str | None:
    q = _norm(quote)
    if len(q) < 15:
        return None
    return next(
        (
            _page_parts(page)[0]
            for page in pages
            if q in _norm(_page_parts(page)[1])
        ),
        None,
    )


def _first_json(text: str) -> dict | None:
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_and_validate(llm_text: str, pages: list[tuple[str, ...]]) -> ExtractionResult:
    result = ExtractionResult()
    data = _first_json(llm_text)
    if data is None:
        result.rejected.append("LLM không trả JSON hợp lệ")
        return result
    result.raw = data
    base_conf = float(data.get("confidence") or 0.5)
    base_conf = min(max(base_conf, 0.0), 1.0)

    def accept(scope: str, obj: dict | None, required_key: str) -> None:
        if not isinstance(obj, dict) or obj.get(required_key) is None:
            result.rejected.append(f"{scope}: thiếu dữ liệu — bỏ qua")
            return
        quote = obj.get("quote") or ""
        if not _quote_in_sources(quote, pages):
            result.rejected.append(f"{scope}: trích dẫn không khớp nguồn — LOẠI (chống bịa)")
            return
        payload = {
            key: value
            for key, value in obj.items()
            if key not in ("quote", "quote_vi", "summary_vi")
        }
        result.facts.append(
            ExtractedFact(
                scope,
                payload,
                quote.strip(),
                round(base_conf * 0.9, 3),
                quote_vi=(obj.get("quote_vi") or "").strip(),
                summary_vi=(obj.get("summary_vi") or "").strip(),
            )
        )

    accept("COMMISSION", data.get("commission"), "type")
    accept("PAYMENT", data.get("payment"), "gateways")
    accept("TERMS", data.get("terms"), "ads_allowed")

    # PACKAGES: verify từng gói
    packages = data.get("packages") or []
    for pkg in packages:
        if not isinstance(pkg, dict) or pkg.get("price_usd") is None:
            continue
        quote = pkg.get("quote") or ""
        if not _quote_in_sources(quote, pages):
            result.rejected.append(f"PACKAGES[{pkg.get('name')}]: trích dẫn không khớp — loại")
            continue
        payload = {
            key: value
            for key, value in pkg.items()
            if key not in ("quote", "quote_vi", "summary_vi")
        }
        result.facts.append(
            ExtractedFact(
                "PACKAGES",
                {"packages": [payload]},
                quote.strip(),
                round(base_conf * 0.9, 3),
                quote_vi=(pkg.get("quote_vi") or "").strip(),
                summary_vi=(pkg.get("summary_vi") or "").strip(),
            )
        )

    # Cờ nghiệp vụ: up-to không được dùng tính payback (rule có sẵn phía appraisal)
    comm = next((f for f in result.facts if f.scope == "COMMISSION"), None)
    if comm and comm.payload.get("rate_is_upper_bound"):
        result.rejected.append("COMMISSION: rate dạng 'up to' — giữ làm tham khảo, KHÔNG dùng payback")

    ppc = data.get("ppc_policy")
    if isinstance(ppc, dict):
        allowed_statuses = {
            "own_landing_page_required": {"REQUIRED", "NOT_REQUIRED", "NOT_STATED"},
            "geo_restrictions": {"YES", "NO", "NOT_STATED"},
        }
        items: dict[str, dict] = {}
        for key in PPC_CHECKLIST_KEYS:
            raw_item = ppc.get(key) if isinstance(ppc.get(key), dict) else {}
            if key == "penalty_if_violated":
                detail = str(raw_item.get("detail_vi") or "").strip()
                status = "STATED" if detail else "NOT_STATED"
            else:
                statuses = allowed_statuses.get(key, {"ALLOWED", "BANNED", "NOT_STATED"})
                status = str(raw_item.get("status") or "NOT_STATED").upper()
                if status not in statuses:
                    status = "NOT_STATED"
                detail = str(raw_item.get("detail_vi") or "").strip()
            quote = str(raw_item.get("quote") or "").strip()
            source_url = _quote_source_url(quote, pages) if status != "NOT_STATED" else None
            if status != "NOT_STATED" and source_url is None:
                result.rejected.append(
                    f"PPC_POLICY.{key}: trích dẫn không khớp nguồn — hạ về NOT_STATED"
                )
                status, quote, detail = "NOT_STATED", "", ""
            items[key] = {
                "status": status,
                "quote": quote if status != "NOT_STATED" else "",
                "quote_vi": str(raw_item.get("quote_vi") or "").strip()
                if status != "NOT_STATED" else "",
                "note_vi": str(raw_item.get("note_vi") or detail).strip(),
                "detail_vi": detail,
                "source_url": source_url,
            }
        result.facts.append(
            ExtractedFact(
                "PPC_CHECKLIST",
                {
                    "items": items,
                    "overall_verdict_vi": str(ppc.get("overall_verdict_vi") or "").strip(),
                },
                "",
                round(base_conf * 0.9, 3),
            )
        )

    # Đây là bản tóm tắt cũ, chỉ giữ tương thích với extraction đã cache/test cũ.
    # được kiểm chứng độc lập; bản dịch không bao giờ có thể cứu một quote bịa.
    terms_fact = next((fact for fact in result.facts if fact.scope == "TERMS"), None)
    ppc_vi = (
        (data.get("ppc_policy_vi") or "").strip()
        if terms_fact is not None
        else PPC_UNDISCLOSED_VI
    )
    if ppc_vi and not isinstance(ppc, dict):
        result.facts.append(
            ExtractedFact(
                "PPC_POLICY_VI",
                {"text": ppc_vi},
                "",
                round(base_conf * 0.9, 3),
                summary_vi=ppc_vi,
            )
        )
    return result
