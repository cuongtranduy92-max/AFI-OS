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

SYSTEM_PROMPT = """Bạn là bộ trích xuất dữ kiện chương trình affiliate. Chỉ trả về JSON đúng schema.
Luật sắt:
- CHỈ dùng thông tin có trong văn bản được cung cấp. KHÔNG dùng kiến thức ngoài.
- Field nào văn bản không nói rõ → null. TUYỆT ĐỐI không đoán.
- Mỗi field có giá trị PHẢI kèm "quote": câu NGUYÊN VĂN (copy đúng từng ký tự) từ văn bản chứng minh giá trị đó.
- Nếu hoa hồng ghi "up to"/"lên đến" → rate_is_upper_bound=true.
- commission_type: ONE_TIME | RECURRING_LIMITED (ghi số tháng) | RECURRING_LIFETIME | HYBRID | null.
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
    "quote": "câu nguyên văn về hoa hồng"
  }},
  "packages": [
    {{"name": "Standard", "price_usd": 28.0, "period": "month", "quote": "câu nguyên văn giá gói"}}
  ],
  "payment": {{
    "gateways": ["PayPal"], "min_payment_usd": 50.0, "clear_days": 30,
    "cookie_days": 30, "net_platform": "Rewardful",
    "quote": "câu nguyên văn về thanh toán"
  }},
  "terms": {{
    "ads_allowed": true, "brand_bid_restricted": false,
    "quote": "câu nguyên văn về quy định quảng cáo"
  }},
  "confidence": 0.0
}}"""


@dataclass(frozen=True)
class ExtractedFact:
    scope: str            # COMMISSION | PACKAGES | PAYMENT | TERMS
    payload: dict         # dữ liệu đã lọc
    quote: str            # trích dẫn ĐÃ kiểm chứng
    confidence: float


@dataclass
class ExtractionResult:
    facts: list[ExtractedFact] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)   # lý do loại từng phần
    raw: dict | None = None


def build_extraction_prompt(domain: str, pages: list[tuple[str, str]]) -> tuple[str, str]:
    """pages: [(url, text)] → (system, user). Mỗi trang cắt MAX_PAGE_CHARS."""
    blocks = []
    for url, text in pages:
        cleaned = re.sub(r"\s+", " ", text or "").strip()[:MAX_PAGE_CHARS]
        blocks.append(f"### URL: {url}\n{cleaned}")
    user = USER_PROMPT_TEMPLATE.format(domain=domain, pages_text="\n\n".join(blocks))
    return SYSTEM_PROMPT, user


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _quote_in_sources(quote: str, pages: list[tuple[str, str]]) -> bool:
    """Trích dẫn phải xuất hiện (chuẩn hoá khoảng trắng, bỏ hoa thường) trong ít nhất 1 trang."""
    q = _norm(quote)
    if len(q) < 15:          # trích dẫn quá ngắn = không đủ bằng chứng
        return False
    return any(q in _norm(text) for _, text in pages)


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


def parse_and_validate(llm_text: str, pages: list[tuple[str, str]]) -> ExtractionResult:
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
        payload = {k: v for k, v in obj.items() if k != "quote"}
        result.facts.append(ExtractedFact(scope, payload, quote.strip(), round(base_conf * 0.9, 3)))

    accept("COMMISSION", data.get("commission"), "type")
    accept("PAYMENT", data.get("payment"), "gateways")
    accept("TERMS", data.get("terms"), "ads_allowed")

    # PACKAGES: verify từng gói
    packages = data.get("packages") or []
    kept = []
    for pkg in packages:
        if not isinstance(pkg, dict) or pkg.get("price_usd") is None:
            continue
        if _quote_in_sources(pkg.get("quote") or "", pages):
            kept.append({k: v for k, v in pkg.items() if k != "quote"})
        else:
            result.rejected.append(f"PACKAGES[{pkg.get('name')}]: trích dẫn không khớp — loại")
    if kept:
        joined_quote = "; ".join((p.get("name") or "?") for p in kept)
        result.facts.append(ExtractedFact("PACKAGES", {"packages": kept}, joined_quote, round(base_conf * 0.9, 3)))

    # Cờ nghiệp vụ: up-to không được dùng tính payback (rule có sẵn phía appraisal)
    comm = next((f for f in result.facts if f.scope == "COMMISSION"), None)
    if comm and comm.payload.get("rate_is_upper_bound"):
        result.rejected.append("COMMISSION: rate dạng 'up to' — giữ làm tham khảo, KHÔNG dùng payback")
    return result
