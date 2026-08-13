from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.config import get_settings
from afi_os.enums import (
    AuditAction,
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
    SourceAuthority,
)
from afi_os.models import (
    AuditLog,
    CommercialProposal,
    CommissionFact,
    LLMExtractionRun,
    Program,
    Project,
    TermsEvidence,
)
from afi_os.services.llm_extractor import (
    MAX_PAGE_CHARS,
    ExtractedFact,
    build_extraction_prompt,
    parse_and_validate,
)
from afi_os.services.llm_keychain import read_credential
from afi_os.services.terms_research import (
    _find_or_create_program,
    _import_commission_specs,
    _import_permission_specs,
    _page_source_authority,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
LLM_COLLECTOR = "ANTHROPIC_LLM"
EXTRACTION_SCHEMA_VERSION = "terms-vi-v2"


class LLMExtractionError(RuntimeError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _bounded_pages(pages: list[dict]) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    for page in pages:
        url = page.get("url")
        text = page.get("text")
        if not isinstance(url, str) or not isinstance(text, str):
            continue
        cleaned = re.sub(r"\s+", " ", text).strip()[:MAX_PAGE_CHARS]
        if cleaned:
            output.append((url, cleaned))
    return output


def _content_hash(domain: str, model: str, pages: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    digest.update(f"{domain}\0{model}\0{EXTRACTION_SCHEMA_VERSION}\0".encode())
    for url, text in pages:
        digest.update(url.encode())
        digest.update(b"\0")
        digest.update(text.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _response_text(payload: Any) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise LLMExtractionError("ERROR", "Claude trả response không đúng định dạng")
    chunks = [
        item.get("text", "")
        for item in payload["content"]
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    text = "".join(chunk for chunk in chunks if isinstance(chunk, str)).strip()
    if not text:
        raise LLMExtractionError("ERROR", "Claude không trả nội dung trích xuất")
    return text


def call_anthropic(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    *,
    post: Callable[..., httpx.Response] = httpx.post,
) -> str:
    try:
        response = post(
            ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2000,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise LLMExtractionError("RETRY_REQUIRED", "Không kết nối được Claude API") from exc
    if response.status_code in {401, 403}:
        raise LLMExtractionError("AUTH_FAILED", "Anthropic API key bị từ chối")
    if response.status_code == 429:
        raise LLMExtractionError("RATE_LIMITED", "Claude API đã hết hạn mức tạm thời")
    if response.status_code >= 400:
        raise LLMExtractionError("ERROR", f"Claude API trả HTTP {response.status_code}")
    try:
        return _response_text(response.json())
    except ValueError as exc:
        raise LLMExtractionError("ERROR", "Claude trả JSON response không hợp lệ") from exc


def _source_for_quote(quote: str, pages: list[dict]) -> tuple[str, SourceAuthority] | None:
    normalized_quote = _normalized(quote)
    for page in pages:
        if normalized_quote and normalized_quote in _normalized(str(page.get("text", ""))):
            return str(page["url"]), _page_source_authority(page)
    return None


def _decimal(value: Any, *, scale: Decimal = Decimal("1")) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value)) * scale
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _commission_spec(fact: ExtractedFact, pages: list[dict]) -> dict | None:
    try:
        commission_type = CommissionType(str(fact.payload.get("type")))
    except ValueError:
        return None
    source = _source_for_quote(fact.quote, pages)
    percent = _decimal(fact.payload.get("percent"), scale=Decimal("0.01"))
    flat = _decimal(fact.payload.get("flat_usd"))
    if source is None or (percent is None and flat is None):
        return None
    if percent is not None and percent > 1:
        return None
    recurring_months = _positive_int(fact.payload.get("recurring_months"))
    if commission_type == CommissionType.RECURRING_LIMITED and not recurring_months:
        return None
    return {
        "source_url": source[0],
        "source_authority": source[1],
        "excerpt": fact.quote,
        "summary_vi": fact.summary_vi or None,
        "quote_vi": fact.quote_vi or None,
        "confidence": fact.confidence,
        "commission_type": commission_type,
        "commission_rate": percent,
        "commission_flat": flat,
        "recurring_months": recurring_months,
        "rate_is_maximum": fact.payload.get("rate_is_upper_bound") is True,
        "applies_to": "AFFILIATE_PROGRAM",
    }


def _terms_specs(fact: ExtractedFact, pages: list[dict]) -> list[dict]:
    source = _source_for_quote(fact.quote, pages)
    ads_allowed = fact.payload.get("ads_allowed")
    brand_restricted = fact.payload.get("brand_bid_restricted")
    if source is None or not isinstance(ads_allowed, bool):
        return []
    common = {
        "source_url": source[0],
        "source_authority": source[1],
        "excerpt": fact.quote,
        "summary_vi": fact.summary_vi or None,
        "quote_vi": fact.quote_vi or None,
        "confidence": fact.confidence,
        "reason": "Đề xuất Claude có trích dẫn gốc đã được AFI-OS đối chiếu.",
    }
    if not ads_allowed:
        return [
            {
                **common,
                "scope": "PAID_SEARCH",
                "decision": PermissionStatus.PROHIBITED,
            }
        ]
    if brand_restricted is True:
        return [
            {
                **common,
                "scope": "PAID_SEARCH",
                "decision": PermissionStatus.NON_BRAND_ONLY,
            },
            {
                **common,
                "scope": "BRAND_KEYWORD",
                "decision": PermissionStatus.PROHIBITED,
            },
        ]
    if brand_restricted is False:
        return [
            {
                **common,
                "scope": "PAID_SEARCH",
                "decision": PermissionStatus.BRAND_ALLOWED,
            },
            {
                **common,
                "scope": "BRAND_KEYWORD",
                "decision": PermissionStatus.BRAND_ALLOWED,
            },
        ]
    return []


def _commercial_specs(
    fact: ExtractedFact,
    pages: list[dict],
) -> list[dict]:
    if fact.scope == "PAYMENT":
        source = _source_for_quote(fact.quote, pages)
        gateways = fact.payload.get("gateways")
        if source is None or not isinstance(gateways, list):
            return []
        normalized_gateways = [
            value.strip() for value in gateways if isinstance(value, str) and value.strip()
        ]
        if not normalized_gateways and all(
            fact.payload.get(key) is None
            for key in ("min_payment_usd", "clear_days", "cookie_days", "net_platform")
        ):
            return []
        payload = {
            "gateways": normalized_gateways,
            "min_payment_usd": float(value)
            if (value := _decimal(fact.payload.get("min_payment_usd"))) is not None
            else None,
            "clear_days": _positive_int(fact.payload.get("clear_days")),
            "cookie_days": _positive_int(fact.payload.get("cookie_days")),
            "net_platform": (
                fact.payload["net_platform"].strip()
                if isinstance(fact.payload.get("net_platform"), str)
                and fact.payload["net_platform"].strip()
                else None
            ),
        }
        return [
            {
                "scope": "PAYMENT",
                "payload": payload,
                "quote": fact.quote,
                "summary_vi": fact.summary_vi or None,
                "quote_vi": fact.quote_vi or None,
                "source_url": source[0],
                "source_authority": source[1],
                "confidence": fact.confidence,
            }
        ]

    output = []
    for package in fact.payload.get("packages", []):
        if not isinstance(package, dict):
            continue
        source = _source_for_quote(fact.quote, pages)
        name = package.get("name")
        price = _decimal(package.get("price_usd"))
        if source is None or not isinstance(name, str) or not name.strip() or price is None:
            continue
        output.append(
            {
                "scope": "PACKAGES",
                "payload": {
                    "packages": [
                        {
                            "name": name.strip(),
                            "price_usd": float(price),
                            "period": package.get("period"),
                        }
                    ]
                },
                "quote": fact.quote,
                "summary_vi": fact.summary_vi or None,
                "quote_vi": fact.quote_vi or None,
                "source_url": source[0],
                "source_authority": source[1],
                "confidence": fact.confidence,
            }
        )
    return output


def _import_commercial_proposals(
    db: Session,
    program: Program,
    specs: list[dict],
) -> list[CommercialProposal]:
    output = []
    for spec in specs:
        digest = hashlib.sha256(
            "|".join(
                [
                    str(program.id),
                    spec["scope"],
                    spec["source_url"],
                    spec["quote"],
                    json.dumps(spec["payload"], ensure_ascii=False, sort_keys=True),
                ]
            ).encode()
        ).hexdigest()
        proposal = db.scalar(
            select(CommercialProposal).where(CommercialProposal.proposal_hash == digest)
        )
        if proposal is None:
            proposal = CommercialProposal(
                program_id=program.id,
                scope=spec["scope"],
                payload_json=spec["payload"],
                source_url=spec["source_url"],
                excerpt=spec["quote"],
                summary_vi=spec.get("summary_vi"),
                quote_vi=spec.get("quote_vi"),
                source_authority=spec["source_authority"],
                confidence=spec["confidence"],
                review_status=EvidenceReviewStatus.PROPOSED,
                proposal_hash=digest,
                collected_by=LLM_COLLECTOR,
                notes="Đề xuất Claude; người vận hành phải duyệt trước khi áp dụng.",
            )
            db.add(proposal)
            db.flush()
        elif proposal.review_status == EvidenceReviewStatus.PROPOSED:
            proposal.summary_vi = spec.get("summary_vi")
            proposal.quote_vi = spec.get("quote_vi")
        output.append(proposal)
    return output


def _ids(run: LLMExtractionRun, key: str) -> list[int]:
    raw = run.result_json.get(key) if isinstance(run.result_json, dict) else None
    return [value for value in raw or [] if isinstance(value, int) and not isinstance(value, bool)]


def _cached_payload(db: Session, run: LLMExtractionRun) -> dict:
    commission_ids = _ids(run, "commission_fact_ids")
    evidence_ids = _ids(run, "evidence_ids")
    proposal_ids = _ids(run, "commercial_proposal_ids")
    return {
        "status": "PROPOSAL_READY",
        "cached": True,
        "model": run.model_name,
        "source_urls": list(run.source_urls),
        "commission_facts": list(
            db.scalars(select(CommissionFact).where(CommissionFact.id.in_(commission_ids))).all()
        ) if commission_ids else [],
        "terms_evidence": list(
            db.scalars(select(TermsEvidence).where(TermsEvidence.id.in_(evidence_ids))).all()
        ) if evidence_ids else [],
        "commercial_proposals": list(
            db.scalars(
                select(CommercialProposal).where(CommercialProposal.id.in_(proposal_ids))
            ).all()
        ) if proposal_ids else [],
        "rejected": list(run.rejected_json),
    }


def extract_terms_from_pages(
    db: Session,
    project: Project,
    pages: list[dict],
    *,
    credential_reader: Callable[[], str] = read_credential,
    sender: Callable[[str, str, str, str], str] = call_anthropic,
) -> dict:
    bounded = _bounded_pages(pages)
    if not bounded:
        raise LLMExtractionError("NO_DATA", "Crawler chưa lấy được trang affiliate/terms/pricing")
    model = get_settings().llm_model
    content_hash = _content_hash(project.domain, model, bounded)
    cached = db.scalar(
        select(LLMExtractionRun).where(LLMExtractionRun.content_hash == content_hash)
    )
    if cached is not None:
        return _cached_payload(db, cached)

    try:
        api_key = credential_reader()
    except (RuntimeError, ValueError) as exc:
        raise LLMExtractionError(
            "CONNECTION_REQUIRED",
            "Chưa kết nối Claude API; chạy SETUP-LLM.command một lần.",
        ) from exc
    system_prompt, user_prompt = build_extraction_prompt(project.domain, bounded)
    llm_text = sender(system_prompt, user_prompt, api_key, model)
    try:
        result = parse_and_validate(llm_text, bounded)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LLMExtractionError("ERROR", "Claude trả dữ liệu không đúng schema") from exc

    confidence_invalid = any(
        not math.isfinite(fact.confidence) or fact.confidence < 0 or fact.confidence > 1
        for fact in result.facts
    )
    if confidence_invalid:
        raise LLMExtractionError("ERROR", "Claude trả confidence không hợp lệ")

    program = project.program or _find_or_create_program(
        db,
        project.domain,
        signup_url=bounded[0][0],
    )
    project.program_id = program.id
    checked_at = datetime.now(UTC)
    commission_specs: list[dict] = []
    terms_specs: list[dict] = []
    commercial_specs: list[dict] = []
    rejected = list(result.rejected)
    for fact in result.facts:
        if fact.scope == "COMMISSION":
            spec = _commission_spec(fact, pages)
            if spec is None:
                rejected.append("COMMISSION: payload không hợp lệ — loại")
            else:
                commission_specs.append(spec)
        elif fact.scope == "TERMS":
            specs = _terms_specs(fact, pages)
            if not specs:
                rejected.append("TERMS: phạm vi Ads chưa đủ rõ — giữ NOT_CHECKED")
            terms_specs.extend(specs)
        elif fact.scope in {"PACKAGES", "PAYMENT"}:
            specs = _commercial_specs(fact, pages)
            if not specs:
                rejected.append(f"{fact.scope}: payload không hợp lệ — loại")
            commercial_specs.extend(specs)
        elif fact.scope == "PPC_POLICY_VI":
            summary = fact.summary_vi.strip()
            if not summary:
                rejected.append("PPC_POLICY_VI: thiếu tóm tắt tiếng Việt — loại")
            else:
                summary_page = next(
                    (
                        page
                        for page in pages
                        if page.get("url") == bounded[0][0]
                    ),
                    pages[0],
                )
                # Tóm tắt này chỉ là proposal hiển thị. Nó không map vào bất kỳ
                # permission canonical nào và không có nút chấp nhận mở quyền.
                terms_specs.append(
                    {
                        "source_url": bounded[0][0],
                        "source_authority": _page_source_authority(summary_page),
                        "excerpt": summary,
                        "summary_vi": summary,
                        "quote_vi": None,
                        "confidence": fact.confidence,
                        "reason": "Tóm tắt PPC tiếng Việt; chỉ hiển thị, không mở quyền.",
                        "scope": "PPC_POLICY_VI",
                        "decision": PermissionStatus.NOT_CHECKED,
                    }
                )

    facts, _, _, _ = _import_commission_specs(db, program, commission_specs, checked_at)
    evidence, _, _, _ = _import_permission_specs(db, program, terms_specs, checked_at)
    for fact in facts:
        spec = next(
            (
                item
                for item in commission_specs
                if item["source_url"] == fact.source_url and item["excerpt"] == fact.excerpt
            ),
            None,
        )
        if spec is not None:
            fact.commission_flat = spec["commission_flat"]
            fact.recurring_months = spec["recurring_months"]
            fact.summary_vi = spec["summary_vi"]
            fact.quote_vi = spec["quote_vi"]
            fact.collected_by = LLM_COLLECTOR
    for item in evidence:
        item.collected_by = LLM_COLLECTOR
        item.reviewer = LLM_COLLECTOR
        spec = next(
            (
                candidate
                for candidate in terms_specs
                if candidate["source_url"] == item.source_url
                and candidate["excerpt"] == item.excerpt
                and candidate["scope"] == item.scope
            ),
            None,
        )
        if spec is not None:
            item.summary_vi = spec.get("summary_vi")
            item.quote_vi = spec.get("quote_vi")
    commercial = _import_commercial_proposals(db, program, commercial_specs)
    run = LLMExtractionRun(
        program_id=program.id,
        domain=project.domain,
        content_hash=content_hash,
        model_name=model,
        source_urls=[url for url, _ in bounded],
        result_json={},
        rejected_json=rejected,
        checked_at=checked_at,
    )
    db.add(run)
    db.flush()
    run.result_json = {
        "commission_fact_ids": [item.id for item in facts],
        "evidence_ids": [item.id for item in evidence],
        "commercial_proposal_ids": [item.id for item in commercial],
    }
    db.add(
        AuditLog(
            entity_type="llm_extraction_run",
            entity_id=str(run.id),
            action=AuditAction.IMPORT,
            actor=LLM_COLLECTOR,
            payload_json={
                "domain": project.domain,
                "content_hash": content_hash,
                "model": model,
                "schema_version": EXTRACTION_SCHEMA_VERSION,
                "source_urls": list(run.source_urls),
                "commission_fact_ids": [item.id for item in facts],
                "evidence_ids": [item.id for item in evidence],
                "commercial_proposal_ids": [item.id for item in commercial],
                "rejected": rejected,
                "permissions_changed": False,
                "campaign_state_changed": False,
                "google_ads_write": False,
                "secret_stored": False,
                "full_page_text_stored": False,
            },
        )
    )
    db.commit()
    return {
        "status": "PROPOSAL_READY" if facts or evidence or commercial else "NO_FACTS",
        "cached": False,
        "model": model,
        "source_urls": list(run.source_urls),
        "commission_facts": facts,
        "terms_evidence": evidence,
        "commercial_proposals": commercial,
        "rejected": rejected,
    }
