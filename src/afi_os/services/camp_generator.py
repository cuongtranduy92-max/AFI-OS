# ruff: noqa: E501
"""Bộ sinh content camp Bước 2: 15 tiêu đề / 4 mô tả / 4 sitelink / 4 callout + linter.

Luật nghiệp vụ (từ giáo trình + spec Trang 2):
- 15 tiêu đề ≤30 ký tự; ĐÚNG 2–3 tiêu đề chứa tên miền đầy đủ (vd "fliki.ai");
  đa số tiêu đề chứa brand-keyword để từ khoá "nhảy xanh" (điểm chất lượng cao).
- 4 mô tả ≤90 ký tự; đúng 1 mô tả chứa tên miền.
- 4 sitelink: nhãn ≤25 ký tự, final_url = link ref của người dùng.
- 4 callout ≤25 ký tự.
- Linter chặn từ cấm (buổi 14): mua bán/lãi lời, free, membership, tài chính
  (crypto/trade/forex/profit), chất cấm/người lớn, so sánh nhất (best/cheapest/#1...),
  và lạm dụng VIẾT HOA (lỗi camp số 5, buổi 9).
Thuần deterministic — không gọi LLM, chạy offline được.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_HEADLINE = 30
MAX_DESCRIPTION = 90
MAX_SITELINK = 25
MAX_CALLOUT = 25
DOMAIN_HEADLINES_MIN, DOMAIN_HEADLINES_MAX = 2, 3

# Từ cấm — so khớp không phân biệt hoa thường, theo ranh giới từ.
BANNED_TERMS: dict[str, str] = {
    "free": "Từ 'free' dễ dính lỗi duyệt/bẫy free-tier",
    "buy": "Từ mua bán", "sell": "Từ mua bán", "sale": "Từ mua bán",
    "cheap": "So sánh giá", "cheapest": "So sánh nhất", "best": "So sánh nhất",
    "greatest": "So sánh nhất", "#1": "So sánh nhất", "top rated": "So sánh nhất",
    "guaranteed": "Cam kết tuyệt đối", "guarantee": "Cam kết tuyệt đối",
    "profit": "Ngách tài chính", "earn money": "Ngách tài chính",
    "crypto": "Ngách tài chính", "forex": "Ngách tài chính",
    "trading": "Ngách tài chính", "trade": "Ngách tài chính",
    "investment": "Ngách tài chính", "casino": "Ngách hạn chế",
    "membership": "Từ membership bị soi", "discount": "Từ giảm giá dễ dính duyệt",
}

_HEADLINE_TEMPLATES = [
    "{brand} Official Site",
    "{domain}",
    "Get Started with {brand}",
    "{brand} for Teams",
    "Try {brand} Today",
    "{brand} Made Simple",
    "Explore {brand} Features",
    "{brand} Pricing & Plans",
    "Start Using {brand}",
    "Why Choose {brand}",
    "{brand} Sign Up",
    "Visit {domain}",
    "Learn {brand} in Minutes",
    "{brand} Reviews & Demo",
    "All-in-One {brand} Tool",
    "{brand} Quick Setup",
    "New to {brand}? Start Here",
]

_DESCRIPTION_TEMPLATES = [
    "Discover what {brand} can do for you. Simple setup, works in minutes.",
    "{domain} - plans, features and demo. See how it fits your workflow.",
    "Join thousands of users already working with {brand} every day.",
    "Compare {brand} plans and pick the one that matches your needs.",
]

_SITELINK_LABELS = ["Pricing", "Features", "Get Started", "Sign Up"]
_CALLOUTS = ["Quick Setup", "Easy To Use", "24/7 Support", "No Long Contracts"]


@dataclass(frozen=True)
class LintIssue:
    level: str          # "error" | "warning"
    section: str        # headlines | descriptions | sitelinks | callouts | plan
    index: int | None
    message: str


@dataclass
class CampPlan:
    headlines: list[str]
    descriptions: list[str]
    sitelinks: list[dict]   # {"label": str, "final_url": str}
    callouts: list[str]
    issues: list[LintIssue] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "headlines": self.headlines,
            "descriptions": self.descriptions,
            "sitelinks": self.sitelinks,
            "callouts": self.callouts,
        }

    def issues_dict(self) -> list[dict]:
        return [i.__dict__ for i in self.issues]


def _brand_from(domain: str, brand_name: str | None) -> str:
    if brand_name and brand_name.strip():
        return brand_name.strip()
    stem = domain.lower().strip().split("/")[0]
    stem = re.sub(r"^www\.", "", stem).split(".")[0]
    return stem.capitalize()


def _norm_domain(domain: str) -> str:
    d = domain.lower().strip()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0]


def _contains_banned(text: str) -> list[str]:
    low = " " + re.sub(r"[^a-z0-9#+ ]", " ", text.lower()) + " "
    hits = []
    for term in BANNED_TERMS:
        pat = " " + term + " " if " " in term or term.startswith("#") else f" {term} "
        if pat in low:
            hits.append(term)
    return hits


def _caps_abuse(text: str) -> bool:
    words = [w for w in re.findall(r"[A-Za-z]{3,}", text)]
    if not words:
        return False
    caps = [w for w in words if w.isupper()]
    return len(caps) >= 2 or (len(caps) == 1 and len(caps[0]) >= 6)


def lint_plan(plan: CampPlan, domain: str, ref_url: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    dom = _norm_domain(domain)
    brand = dom.split(".")[0]

    def check_line(section: str, idx: int, text: str, max_len: int) -> None:
        if len(text) > max_len:
            issues.append(LintIssue("error", section, idx, f"Quá {max_len} ký tự ({len(text)})"))
        for term in _contains_banned(text):
            issues.append(LintIssue("error", section, idx, f"Từ cấm '{term}': {BANNED_TERMS[term]}"))
        if _caps_abuse(text):
            issues.append(LintIssue("warning", section, idx, "Lạm dụng VIẾT HOA (lỗi camp #5)"))
        if not text.isascii():
            issues.append(LintIssue("warning", section, idx, "Ký tự ngoài ASCII — kiểm tra lại ngôn ngữ"))

    for i, h in enumerate(plan.headlines):
        check_line("headlines", i, h, MAX_HEADLINE)
    for i, d in enumerate(plan.descriptions):
        check_line("descriptions", i, d, MAX_DESCRIPTION)
    for i, s in enumerate(plan.sitelinks):
        check_line("sitelinks", i, s.get("label", ""), MAX_SITELINK)
        if s.get("final_url") != ref_url:
            issues.append(LintIssue("error", "sitelinks", i, "final_url phải là link ref đã nhập"))
    for i, c in enumerate(plan.callouts):
        check_line("callouts", i, c, MAX_CALLOUT)

    # Số lượng
    if len(plan.headlines) != 15:
        issues.append(LintIssue("error", "plan", None, f"Cần đúng 15 tiêu đề (đang {len(plan.headlines)})"))
    if len(plan.descriptions) != 4:
        issues.append(LintIssue("error", "plan", None, f"Cần đúng 4 mô tả (đang {len(plan.descriptions)})"))
    if len(plan.sitelinks) != 4:
        issues.append(LintIssue("error", "plan", None, f"Cần đúng 4 sitelink (đang {len(plan.sitelinks)})"))
    if len(plan.callouts) != 4:
        issues.append(LintIssue("error", "plan", None, f"Cần đúng 4 callout (đang {len(plan.callouts)})"))

    # Tên miền trong tiêu đề: đúng 2–3
    dom_count = sum(1 for h in plan.headlines if dom in h.lower())
    if not DOMAIN_HEADLINES_MIN <= dom_count <= DOMAIN_HEADLINES_MAX:
        issues.append(LintIssue(
            "error", "plan", None,
            f"Tiêu đề chứa tên miền '{dom}' phải 2–3 (đang {dom_count})",
        ))
    # Đúng 1 mô tả chứa tên miền
    desc_dom = sum(1 for d in plan.descriptions if dom in d.lower())
    if desc_dom != 1:
        issues.append(LintIssue("error", "plan", None, f"Đúng 1 mô tả chứa tên miền (đang {desc_dom})"))
    # Brand-keyword "nhảy xanh": brand phải xuất hiện ở ≥60% tiêu đề
    brand_count = sum(1 for h in plan.headlines if brand in h.lower())
    if brand_count < 9:
        issues.append(LintIssue(
            "warning", "plan", None,
            f"Chỉ {brand_count}/15 tiêu đề chứa brand '{brand}' — từ khoá khó nhảy xanh, điểm chất lượng thấp",
        ))
    if not ref_url or not ref_url.startswith(("http://", "https://")):
        issues.append(LintIssue("error", "plan", None, "Link ref chưa nhập hoặc không hợp lệ"))
    return issues


def generate_camp_plan(
    domain: str,
    ref_url: str,
    brand_name: str | None = None,
    existing_plan: dict | None = None,
) -> CampPlan:
    """Sinh plan mới, hoặc lint lại plan người dùng đã sửa (existing_plan)."""
    dom = _norm_domain(domain)
    brand = _brand_from(dom, brand_name)

    if existing_plan:
        plan = CampPlan(
            headlines=list(existing_plan.get("headlines", [])),
            descriptions=list(existing_plan.get("descriptions", [])),
            sitelinks=list(existing_plan.get("sitelinks", [])),
            callouts=list(existing_plan.get("callouts", [])),
        )
        plan.issues = lint_plan(plan, dom, ref_url)
        return plan

    headlines: list[str] = []
    for tpl in _HEADLINE_TEMPLATES:
        h = tpl.format(brand=brand, domain=dom)
        if len(h) <= MAX_HEADLINE and h not in headlines:
            headlines.append(h)
        if len(headlines) == 15:
            break
    # Đảm bảo đúng 2–3 tiêu đề chứa tên miền đầy đủ
    dom_idx = [i for i, h in enumerate(headlines) if dom in h.lower()]
    while len(dom_idx) > DOMAIN_HEADLINES_MAX:
        i = dom_idx.pop()
        headlines[i] = f"{brand} Overview"[:MAX_HEADLINE]
    if len(dom_idx) < DOMAIN_HEADLINES_MIN and headlines:
        headlines[-1] = f"See {dom}"[:MAX_HEADLINE]

    descriptions = [t.format(brand=brand, domain=dom)[:MAX_DESCRIPTION] for t in _DESCRIPTION_TEMPLATES]
    sitelinks = [{"label": lb, "final_url": ref_url} for lb in _SITELINK_LABELS]
    callouts = list(_CALLOUTS)

    plan = CampPlan(headlines=headlines, descriptions=descriptions,
                    sitelinks=sitelinks, callouts=callouts)
    plan.issues = lint_plan(plan, dom, ref_url)
    return plan
