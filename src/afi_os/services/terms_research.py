from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import select
from sqlalchemy.orm import Session

from afi_os.enums import (
    AuditAction,
    CommissionType,
    EvidenceReviewStatus,
    PermissionStatus,
    ProgramStatus,
    ResearchStatus,
    SourceAuthority,
)
from afi_os.models import (
    AuditLog,
    CommissionFact,
    Merchant,
    Program,
    TermsEvidence,
    TermsResearchRun,
)
from afi_os.services.programs import commission_resolution_status, program_gate_status
from afi_os.services.project_sync import ensure_project_for_program

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
WEB_COLLECTOR_VERSION = "official-web-v9"
MAX_PAGE_BYTES = 1_000_000
MAX_FETCHED_PAGES = 8
FETCH_TIMEOUT_SECONDS = 4
RETRYABLE_ERROR_PREFIX = "Tạm thời · "
RESERVED_SUFFIXES = (".test", ".invalid", ".localhost", ".local", ".example")
STANDARD_PATHS = (
    "/affiliate-terms",
    "/affiliate-program-terms",
    "/legal/affiliate-terms",
    "/affiliate-program",
    "/affiliates",
    "/partners",
    "/partner-program",
    "/terms",
)
LINK_HINTS = ("affiliate", "partner", "referral", "publisher", "ppc", "terms", "policy")
SOURCE_TEXT_HINTS = LINK_HINTS + (
    "paid search",
    "pay-per-click",
    "brand",
    "trademark",
    "keyword",
    "bid",
    "direct link",
    "commission",
    "cookie",
    "payout",
    "advertis",
)
DISCOVERY_QUERY_KEYS = {"fbclid", "gclid", "msclkid", "nav"}
DISCOVERY_QUERY_PREFIXES = ("utm_",)

NEGATIVE = (
    r"(?:may\s+not|must\s+not|shall\s+not|"
    r"not\s+(?:be\s+)?(?:allowed|permitted)|prohibited|forbidden)"
)
ALLOWED = r"(?:is|are|be)?\s*(?:expressly\s+)?(?:allowed|permitted)"


def _rule(scope: str, decision: PermissionStatus, confidence: float, reason: str, pattern: str):
    return (scope, decision, confidence, reason, re.compile(pattern, re.IGNORECASE))


PERMISSION_RULES = (
    _rule(
        "PAID_SEARCH",
        PermissionStatus.PROHIBITED,
        0.90,
        "Trang chính thức có câu cấm paid search/PPC.",
        rf"(?:{NEGATIVE}.{{0,140}}(?:paid\s+search|ppc|pay[- ]per[- ]click)|"
        rf"(?:paid\s+search|ppc|pay[- ]per[- ]click).{{0,140}}{NEGATIVE})",
    ),
    _rule(
        "BRAND_KEYWORD",
        PermissionStatus.PROHIBITED,
        0.90,
        "Trang chính thức có câu cấm brand/trademark bidding.",
        rf"(?:{NEGATIVE}.{{0,180}}(?:bid(?:ding)?|keyword).{{0,100}}(?:brand|trademark|trade\s+name|company\s+name)|(?:bid(?:ding)?|keyword).{{0,100}}(?:brand|trademark|trade\s+name|company\s+name).{{0,180}}{NEGATIVE})",
    ),
    _rule(
        "TRADEMARK_AD_COPY",
        PermissionStatus.PROHIBITED,
        0.90,
        "Trang chính thức có câu cấm dùng trademark trong nội dung quảng cáo.",
        rf"(?:{NEGATIVE}.{{0,160}}(?:trademark|brand).{{0,100}}(?:ad\s+copy|advertis(?:ing|ement)|display\s+url)|(?:trademark|brand).{{0,100}}(?:ad\s+copy|advertis(?:ing|ement)|display\s+url).{{0,160}}{NEGATIVE})",
    ),
    _rule(
        "DIRECT_LINK",
        PermissionStatus.PROHIBITED,
        0.90,
        "Trang chính thức có câu cấm direct linking từ quảng cáo.",
        rf"(?:{NEGATIVE}.{{0,120}}(?:direct\s+link(?:ing)?|link\s+directly)|(?:direct\s+link(?:ing)?|link\s+directly).{{0,120}}{NEGATIVE})",
    ),
    _rule(
        "PAID_SEARCH",
        PermissionStatus.APPROVAL_REQUIRED,
        0.86,
        "Paid search/PPC cần phê duyệt trước.",
        r"(?:paid\s+search|ppc|pay[- ]per[- ]click).{0,140}"
        r"(?:prior|written|advance).{0,50}(?:approval|permission|consent)",
    ),
    _rule(
        "PAID_SEARCH",
        PermissionStatus.NON_BRAND_ONLY,
        0.84,
        "Nguồn cho phép rõ non-brand/generic keywords.",
        rf"(?:non[- ]brand(?:ed)?|generic\s+keywords?).{{0,120}}{ALLOWED}",
    ),
    _rule(
        "NON_BRAND",
        PermissionStatus.NON_BRAND_ONLY,
        0.84,
        "Nguồn cho phép rõ non-brand/generic keywords.",
        rf"(?:non[- ]brand(?:ed)?|generic\s+keywords?).{{0,120}}{ALLOWED}",
    ),
    _rule(
        "PAID_SEARCH",
        PermissionStatus.BRAND_ALLOWED,
        0.86,
        "Nguồn cho phép rõ brand/trademark bidding.",
        rf"(?:bid(?:ding)?|keyword).{{0,100}}(?:brand|trademark|trade\s+name).{{0,100}}{ALLOWED}",
    ),
    _rule(
        "BRAND_KEYWORD",
        PermissionStatus.BRAND_ALLOWED,
        0.86,
        "Nguồn cho phép rõ brand/trademark bidding.",
        rf"(?:bid(?:ding)?|keyword).{{0,100}}(?:brand|trademark|trade\s+name).{{0,100}}{ALLOWED}",
    ),
    _rule(
        "DIRECT_LINK",
        PermissionStatus.BRAND_ALLOWED,
        0.84,
        "Nguồn cho phép rõ direct linking.",
        rf"(?:direct\s+link(?:ing)?|link\s+directly).{{0,100}}{ALLOWED}",
    ),
    _rule(
        "PAID_SEARCH",
        PermissionStatus.AMBIGUOUS,
        0.70,
        "Nguồn nhắc paid search/PPC được phép nhưng chưa làm rõ brand scope.",
        rf"(?:paid\s+search|ppc|pay[- ]per[- ]click).{{0,100}}{ALLOWED}",
    ),
)

COMMISSION_PATTERNS = (
    re.compile(
        r"(?P<up_to>up\s+to\s+)?(?P<rate>\d{1,3}(?:\.\d+)?)\s*%[^.]{0,80}?commission",
        re.IGNORECASE,
    ),
    re.compile(
        r"commission(?:s)?[^.]{0,80}?(?P<up_to>up\s+to\s+)?(?P<rate>\d{1,3}(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
)


class _HTMLTextParser(HTMLParser):
    BLOCK_TAGS = {"p", "div", "li", "section", "article", "h1", "h2", "h3", "br", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self.parts.append(cleaned)
        self.parts.append(" ")
        if self._in_title:
            self.title_parts.append(cleaned)

    def result(self, base_url: str) -> dict:
        lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines()]
        text = "\n".join(line for line in lines if line)
        links = sorted({urljoin(base_url, href) for href in self.links})
        return {
            "url": base_url,
            "title": " ".join(self.title_parts).strip() or None,
            "text": text,
            "links": links,
        }


def _hash(parts: list[str]) -> str:
    normalized = "|".join(part.strip() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_fixture(domain: str) -> dict | None:
    fixture_path = FIXTURE_ROOT / f"{domain.split('.')[0]}.json"
    if not fixture_path.is_file():
        return None
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return payload if payload.get("domain") == domain else None


def _host_matches_domain(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def _page_source_authority(page: dict) -> SourceAuthority:
    """Return explicit provenance while keeping older/custom fetchers compatible."""

    raw = page.get("source_authority", SourceAuthority.OFFICIAL)
    return raw if isinstance(raw, SourceAuthority) else SourceAuthority(raw)


def _spec_source_authority(spec: dict) -> SourceAuthority:
    """Keep the signed 0.2.1 fixture compatible with authority-aware imports."""

    raw = spec.get("source_authority", SourceAuthority.OFFICIAL)
    return raw if isinstance(raw, SourceAuthority) else SourceAuthority(raw)


def _source_authorities_for_pages(pages: list[dict]) -> dict[str, str]:
    """Build a compact URL-to-provenance map for API, audit and export surfaces."""

    return {
        _normalize_discovery_url(page["url"]): _page_source_authority(page).value
        for page in pages
        if isinstance(page.get("url"), str)
    }


def source_authorities_from_audit_payload(payload: dict) -> dict[str, str]:
    """Read current provenance or recover it from older official source snapshots."""

    raw_mapping = payload.get("source_authorities")
    if isinstance(raw_mapping, dict):
        output: dict[str, str] = {}
        for raw_url, raw_authority in raw_mapping.items():
            if not isinstance(raw_url, str) or not isinstance(raw_authority, str):
                continue
            try:
                authority = SourceAuthority(raw_authority)
            except ValueError:
                continue
            output[_normalize_discovery_url(raw_url)] = authority.value
        if output:
            return output

    snapshots = payload.get("source_snapshots")
    if not isinstance(snapshots, list):
        return {}
    output = {}
    for item in snapshots:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        # Before 0.2.68, snapshots were produced only by the official,
        # same-domain collector. New snapshots always carry the explicit field.
        raw_authority = item.get("source_authority", SourceAuthority.OFFICIAL.value)
        try:
            authority = SourceAuthority(raw_authority)
        except (TypeError, ValueError):
            continue
        output[_normalize_discovery_url(item["url"])] = authority.value
    return output


@lru_cache(maxsize=256)
def _host_is_public(host: str) -> bool:
    try:
        literal = ipaddress.ip_address(host)
        return literal.is_global
    except ValueError:
        pass
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except OSError:
        return False
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False


def _validate_public_url(url: str, domain: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid HTTPS port") from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise ValueError("Only credential-free HTTPS URLs are allowed")
    if not _host_matches_domain(host, domain):
        raise ValueError("URL leaves the merchant domain")
    if not _host_is_public(host):
        raise ValueError("URL does not resolve only to public addresses")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


def _normalize_discovery_url(url: str) -> str:
    """Remove only known navigation/tracking query fields from a public source URL."""

    parsed = urlsplit(url)
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.lower()
        if normalized_key in DISCOVERY_QUERY_KEYS or normalized_key.startswith(
            DISCOVERY_QUERY_PREFIXES
        ):
            continue
        query_items.append((key, value))
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            urlencode(query_items, doseq=True),
            "",
        )
    )


def _discovery_url_key(url: str) -> str:
    return _normalize_discovery_url(url).rstrip("/")


class _MerchantRedirectHandler(HTTPRedirectHandler):
    def __init__(self, domain: str) -> None:
        super().__init__()
        self.domain = domain

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        safe_url = _normalize_discovery_url(_validate_public_url(newurl, self.domain))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def _fetch_page(url: str, domain: str) -> dict:
    safe_url = _normalize_discovery_url(_validate_public_url(url, domain))
    request = Request(
        safe_url,
        headers={
            "User-Agent": "AFI-OS-Terms-Evidence/0.2.99",
            "Accept": "text/html,text/plain;q=0.9",
        },
        method="GET",
    )
    opener = build_opener(_MerchantRedirectHandler(domain))
    with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        final_url = _normalize_discovery_url(
            _validate_public_url(response.geturl(), domain)
        )
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain"}:
            raise ValueError(f"Unsupported content type: {content_type}")
        raw = response.read(MAX_PAGE_BYTES + 1)
        truncated = len(raw) > MAX_PAGE_BYTES
        if truncated:
            # Keep the network and memory boundary while still using navigation
            # links and policy text found near the start of a large official page.
            # HTMLParser tolerates an incomplete final tag, and the marker is
            # preserved in audit metadata so the excerpt is never represented as
            # a complete copy of the source.
            raw = raw[:MAX_PAGE_BYTES]
        charset = response.headers.get_content_charset() or "utf-8"
        body = raw.decode(charset, errors="replace")
    if content_type == "text/plain":
        return {
            "url": final_url,
            "title": None,
            "text": body,
            "links": [],
            "truncated": truncated,
        }
    parser = _HTMLTextParser()
    parser.feed(body)
    page = parser.result(final_url)
    page["truncated"] = truncated
    return page


def _fetch_error_is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in {408, 425, 429} or 500 <= exc.code <= 599
    if isinstance(exc, (URLError, OSError)):
        return True
    return False


def _format_fetch_error(url: str, exc: Exception) -> str:
    prefix = RETRYABLE_ERROR_PREFIX if _fetch_error_is_retryable(exc) else ""
    return f"{prefix}{url}: {exc}"


def _errors_require_retry(errors: list[str]) -> bool:
    return any(error.startswith(RETRYABLE_ERROR_PREFIX) for error in errors)


def _is_expected_standard_probe_miss(candidate_kind: str, exc: Exception) -> bool:
    """Treat a missing guessed path as discovery absence, not a source failure."""

    return (
        candidate_kind == "STANDARD_PROBE"
        and isinstance(exc, HTTPError)
        and exc.code in {404, 410}
    )


def _link_is_relevant(url: str) -> bool:
    value = url.lower()
    return any(hint in value for hint in LINK_HINTS)


def _page_is_relevant(page: dict) -> bool:
    haystack = (
        f"{page.get('url', '')} {page.get('title', '')} "
        f"{page.get('text', '')[:12000]}"
    ).lower()
    return any(hint in haystack for hint in LINK_HINTS)


def _source_snapshots(pages: list[dict]) -> list[dict]:
    """Fingerprint policy-related text without storing a full public page copy."""

    snapshots: list[dict] = []
    for page in pages:
        text = re.sub(r"\s+", " ", str(page.get("text", ""))).strip()
        relevant_sentences: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            compact = re.sub(r"\s+", " ", sentence).strip().lower()
            if compact and any(hint in compact for hint in SOURCE_TEXT_HINTS):
                relevant_sentences.append(compact)
        policy_text = "\n".join(sorted(set(relevant_sentences)))
        snapshots.append(
            {
                "url": _normalize_discovery_url(page["url"]),
                "content_sha256": hashlib.sha256(
                    policy_text.encode("utf-8")
                ).hexdigest(),
                "text_chars": len(text),
                "relevant_chars": len(policy_text),
                "truncated": bool(page.get("truncated")),
                "source_authority": _page_source_authority(page).value,
            }
        )
    return sorted(snapshots, key=lambda item: item["url"])


def _previous_source_snapshots(db: Session, domain: str) -> list[dict]:
    """Return the newest usable source snapshot set for the same merchant domain."""

    audits = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "terms_research_run")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all()
    for audit in audits:
        payload = audit.payload_json if isinstance(audit.payload_json, dict) else {}
        if payload.get("domain") != domain:
            continue
        snapshots = payload.get("source_snapshots")
        if not isinstance(snapshots, list) or not snapshots:
            continue
        usable = [
            item
            for item in snapshots
            if isinstance(item, dict)
            and isinstance(item.get("url"), str)
            and isinstance(item.get("content_sha256"), str)
        ]
        if usable:
            return usable
    return []


def _compare_source_snapshots(
    db: Session,
    domain: str,
    current: list[dict],
    *,
    collection_errors: list[str],
) -> tuple[str, list[dict[str, str]]]:
    previous = _previous_source_snapshots(db, domain)
    if not previous:
        return "INITIAL", []
    if not current and collection_errors:
        return "UNAVAILABLE", []

    previous_by_url = _snapshots_by_discovery_url(previous)
    current_by_url = _snapshots_by_discovery_url(current)
    changes: list[dict[str, str]] = []
    comparison_incomplete = False
    for key in sorted(current_by_url.keys() - previous_by_url.keys()):
        changes.append({"url": current_by_url[key]["url"], "change_type": "ADDED"})
    for key in sorted(previous_by_url.keys() - current_by_url.keys()):
        changes.append(
            {
                "url": previous_by_url[key]["url"],
                "change_type": "UNAVAILABLE" if collection_errors else "REMOVED",
            }
        )
    for key in sorted(previous_by_url.keys() & current_by_url.keys()):
        if (
            previous_by_url[key]["content_sha256"]
            != current_by_url[key]["content_sha256"]
        ):
            if previous_by_url[key].get("truncated") or current_by_url[key].get(
                "truncated"
            ):
                # A bounded prefix is still valid for link/proposal extraction,
                # but dynamic content near the byte boundary is not a reliable
                # whole-page change signal. The truncated marker remains in the
                # audit/Evidence Pack and semantic evidence changes are handled
                # independently by the proposal import path.
                comparison_incomplete = True
                continue
            changes.append(
                {"url": current_by_url[key]["url"], "change_type": "CONTENT_CHANGED"}
            )

    if not changes:
        return ("PARTIAL" if comparison_incomplete else "UNCHANGED"), []
    if all(item["change_type"] == "UNAVAILABLE" for item in changes):
        return "PARTIAL", changes
    return "CHANGED", changes


def _snapshots_by_discovery_url(snapshots: list[dict]) -> dict[str, dict]:
    """Collapse known tracking variants while preferring the canonical source row."""

    output: dict[str, dict] = {}
    ranks: dict[str, tuple[bool, str]] = {}
    for item in snapshots:
        original_url = item["url"]
        normalized_url = _normalize_discovery_url(original_url)
        key = _discovery_url_key(normalized_url)
        rank = (original_url != normalized_url, original_url)
        if key in output and ranks[key] <= rank:
            continue
        output[key] = {**item, "url": normalized_url}
        ranks[key] = rank
    return output


def discover_official_pages(
    domain: str,
    *,
    priority_urls: list[str] | tuple[str, ...] = (),
) -> tuple[list[dict], list[str]]:
    """Fetch a small, same-domain HTTPS set; never crawl arbitrary links or private hosts."""

    if domain.endswith(RESERVED_SUFFIXES):
        return [], ["Reserved/non-public domain; automatic collection was skipped."]

    errors: list[str] = []
    pages: list[dict] = []
    root_url = f"https://{domain}/"
    try:
        root = _fetch_page(root_url, domain)
        pages.append(root)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        root = None
        errors.append(_format_fetch_error(root_url, exc))

    candidates: list[tuple[str, str]] = []
    for priority_url in priority_urls:
        try:
            candidates.append(
                (
                    _normalize_discovery_url(
                        _validate_public_url(priority_url, domain)
                    ),
                    "PRIORITY",
                )
            )
        except ValueError as exc:
            errors.append(f"Stored source was skipped: {exc}")
    if root is not None:
        for link in root.get("links", []):
            try:
                safe_link = _normalize_discovery_url(
                    _validate_public_url(link, domain)
                )
            except ValueError:
                continue
            if _link_is_relevant(safe_link):
                candidates.append((safe_link, "DISCOVERED"))
    candidates.extend(
        (f"https://{domain}{path}", "STANDARD_PROBE") for path in STANDARD_PATHS
    )

    unique_candidates: list[tuple[str, str]] = []
    seen = {_discovery_url_key(page["url"]) for page in pages}
    for candidate, candidate_kind in candidates:
        key = _discovery_url_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append((candidate, candidate_kind))
        if len(unique_candidates) >= MAX_FETCHED_PAGES - len(pages):
            break

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_page, candidate, domain): (candidate, candidate_kind)
            for candidate, candidate_kind in unique_candidates
        }
        for future in as_completed(futures):
            candidate, candidate_kind = futures[future]
            try:
                pages.append(future.result())
            except (HTTPError, URLError, OSError, ValueError) as exc:
                if _is_expected_standard_probe_miss(candidate_kind, exc):
                    continue
                errors.append(_format_fetch_error(candidate, exc))

    deduplicated: dict[str, dict] = {}
    for page in pages:
        normalized_page = {
            **page,
            "url": _normalize_discovery_url(page["url"]),
        }
        key = _discovery_url_key(normalized_page["url"])
        current = deduplicated.get(key)
        if current is None or len(page.get("text", "")) > len(current.get("text", "")):
            deduplicated[key] = normalized_page
    relevant = [page for page in deduplicated.values() if _page_is_relevant(page)]
    return sorted(relevant, key=lambda page: page["url"]), errors[:MAX_FETCHED_PAGES]


def _external_partner_signup_url(program: Program | None) -> str | None:
    """Return only a saved signup URL that is outside the merchant's domain."""

    if program is None or not program.signup_url:
        return None
    host = (urlsplit(program.signup_url).hostname or "").lower().rstrip(".")
    merchant_domain = program.merchant.website_domain.lower().rstrip(".")
    if not host or _host_matches_domain(host, merchant_domain):
        return None
    return program.signup_url


def discover_partner_portal_signup(signup_url: str) -> tuple[list[dict], list[str]]:
    """Fetch one exact saved external signup URL without crawling its portal."""

    parsed = urlsplit(signup_url)
    portal_host = (parsed.hostname or "").lower().rstrip(".")
    if not portal_host or portal_host.endswith(RESERVED_SUFFIXES):
        return [], [
            "External partner signup URL is missing a public host; collection was skipped."
        ]
    try:
        safe_url = _normalize_discovery_url(
            _validate_public_url(signup_url, portal_host)
        )
        page = _fetch_page(safe_url, portal_host)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        return [], [_format_fetch_error(signup_url, exc)]
    return [
        {
            **page,
            "url": _normalize_discovery_url(page["url"]),
            "source_authority": SourceAuthority.PARTNER_PORTAL.value,
        }
    ], []


def _excerpt(text: str, start: int, end: int, limit: int = 460) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    left = max(0, start - 180)
    right = min(len(compact), end + 220)
    snippet = compact[left:right].strip(" -–—|.;")
    if left:
        snippet = "…" + snippet
    if right < len(compact):
        snippet += "…"
    return snippet[:limit]


def _extract_permission_specs(pages: list[dict]) -> list[dict]:
    specs: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for page in pages:
        source_authority = _page_source_authority(page)
        raw_text = page.get("text", "")
        policy_sentences = [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", raw_text)
            if sentence.strip()
        ]
        for sentence_index, text in enumerate(policy_sentences):
            brand_bidding_requires_permission = bool(
                re.search(
                    r"(?:not\s+(?:be\s+)?allowed|may\s+not|must\s+not|shall\s+not)"
                    r".{0,100}(?:ppc\s+)?bid(?:ding)?\s+(?:on\s+)?brand\s+names?"
                    r".{0,180}without\s+prior\s+written\s+permission",
                    text,
                    re.IGNORECASE,
                )
            )
            if brand_bidding_requires_permission:
                # This is a conditional brand-bidding restriction, not a ban on
                # every PPC campaign and not a trademark-in-ad-copy rule. The
                # required negative brand keywords make the non-brand scope clear.
                context_sentences = policy_sentences[
                    sentence_index : sentence_index + 2
                ]
                policy_context = " ".join(context_sentences)
                negative_keyword_requirement = bool(
                    re.search(
                        r"brand(?:ed)?\s+(?:terms|keywords?).{0,80}negative\s+keywords?"
                        r"|negative\s+keywords?.{0,80}brand(?:ed)?\s+(?:terms|keywords?)",
                        policy_context,
                        re.IGNORECASE,
                    )
                )
                excerpt = _excerpt(policy_context, 0, len(policy_context))
                derived_items = [
                    {
                        "scope": "BRAND_KEYWORD",
                        "decision": PermissionStatus.APPROVAL_REQUIRED,
                        "confidence": 0.93,
                        "reason": "Brand bidding requires prior written permission.",
                    },
                ]
                if negative_keyword_requirement:
                    derived_items.extend(
                        [
                            {
                                "scope": "PAID_SEARCH",
                                "decision": PermissionStatus.NON_BRAND_ONLY,
                                "confidence": 0.90,
                                "reason": (
                                    "PPC is conditional: brand terms require written "
                                    "permission and must otherwise be negative keywords."
                                ),
                            },
                            {
                                "scope": "NON_BRAND",
                                "decision": PermissionStatus.NON_BRAND_ONLY,
                                "confidence": 0.90,
                                "reason": (
                                    "The official PPC policy requires excluding brand terms, "
                                    "which identifies the compliant non-brand scope."
                                ),
                            },
                        ]
                    )
                for derived in derived_items:
                    key = (
                        page["url"],
                        derived["scope"],
                        derived["decision"].value,
                        excerpt,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    specs.append(
                        {
                            **derived,
                            "source_url": page["url"],
                            "source_authority": source_authority,
                            "excerpt": excerpt,
                        }
                    )
            for scope, decision, confidence, reason, pattern in PERMISSION_RULES:
                if brand_bidding_requires_permission and (
                    (scope == "PAID_SEARCH")
                    or (scope == "BRAND_KEYWORD")
                    or (scope == "TRADEMARK_AD_COPY")
                ):
                    # The derived facts above have the correct conditional scope.
                    continue
                if decision in {
                    PermissionStatus.NON_BRAND_ONLY,
                    PermissionStatus.BRAND_ALLOWED,
                    PermissionStatus.AMBIGUOUS,
                } and re.search(NEGATIVE, text, re.IGNORECASE):
                    # Conservative extraction: a negative sentence must never be
                    # reinterpreted as permission merely because it contains
                    # words such as "allowed" or "permitted" elsewhere.
                    continue
                if (
                    scope == "PAID_SEARCH"
                    and decision == PermissionStatus.PROHIBITED
                    and re.search(
                        rf"direct\s+link(?:ing)?.{{0,120}}{NEGATIVE}",
                        text,
                        re.IGNORECASE,
                    )
                ):
                    # "Direct linking from PPC ads is prohibited" restricts the
                    # landing method, not paid search as a whole.
                    continue
                for match in pattern.finditer(text):
                    excerpt = _excerpt(text, match.start(), match.end())
                    key = (page["url"], scope, decision.value, excerpt)
                    if key in seen:
                        continue
                    seen.add(key)
                    specs.append(
                        {
                            "scope": scope,
                            "decision": decision,
                            "confidence": confidence,
                            "reason": reason,
                            "source_url": page["url"],
                            "source_authority": source_authority,
                            "excerpt": excerpt,
                        }
                    )
    return specs


def _commission_type(context: str) -> tuple[CommissionType, str] | None:
    value = context.lower()
    choices: set[tuple[CommissionType, str]] = set()
    if (
        "linkedin automation" in value
        and "slot" in value
        and "purchase price" in value
    ):
        return (CommissionType.ONE_TIME, "LINKEDIN_AUTOMATION_SLOT")
    if (
        ("lifetime" in value and "recurr" in value)
        or ("entire duration" in value and "subscription" in value)
    ):
        choices.add((CommissionType.RECURRING_LIFETIME, "LIFETIME_RECURRING"))
    elif "recurr" in value:
        choices.add((CommissionType.RECURRING_UNSPECIFIED, "RECURRING_UNSPECIFIED"))
    if any(
        token in value
        for token in ("one-time", "one time", "first payment", "first purchase")
    ):
        choices.add((CommissionType.ONE_TIME, "FIRST_PAYMENT_OR_ONE_TIME"))
    return next(iter(choices)) if len(choices) == 1 else None


def _commission_applies_to(context: str) -> str | None:
    """Identify distinct commercial products so tiered facts do not look contradictory."""

    value = context.lower()
    middle = len(value) // 2
    candidates: list[tuple[int, str]] = []
    for match in re.finditer(r"linkedin\s+automation.{0,40}?slot", value):
        candidates.append((abs(match.start() - middle), "LINKEDIN_AUTOMATION_SLOT"))
    for match in re.finditer(
        r"(?:plan\s+purchase|subscription|membership\s+purchase)", value
    ):
        candidates.append((abs(match.start() - middle), "PLAN_SUBSCRIPTION"))
    return min(candidates, default=(0, None))[1]


def _commission_rate_is_discount(text: str, match: re.Match[str]) -> bool:
    """Reject nearby pricing discounts that merely precede affiliate copy."""

    before = text[max(0, match.start() - 64) : match.start()].lower()
    return bool(
        re.search(
            r"(?:\bsave(?:\s+(?:more\s+than|up\s+to))?|"
            r"\bdiscount(?:ed)?|\boff)\s*$",
            before,
        )
    )


def _extract_commission_specs(pages: list[dict]) -> list[dict]:
    specs: list[dict] = []
    seen: set[tuple[str, str, str, str, bool]] = set()
    for page in pages:
        source_authority = _page_source_authority(page)
        text = re.sub(r"\s+", " ", page.get("text", "")).strip()
        page_cadence = _commission_type(text)
        for pattern in COMMISSION_PATTERNS:
            for match in pattern.finditer(text):
                if _commission_rate_is_discount(text, match):
                    continue
                rate = Decimal(match.group("rate"))
                if rate <= 0 or rate > 100:
                    continue
                context = _excerpt(text, match.start(), match.end())
                local_context = text[
                    max(0, match.start() - 100) : min(len(text), match.end() + 100)
                ]
                applies_to = _commission_applies_to(context)
                if applies_to == "LINKEDIN_AUTOMATION_SLOT":
                    cadence = (
                        CommissionType.ONE_TIME,
                        "LINKEDIN_AUTOMATION_SLOT",
                    )
                elif applies_to == "PLAN_SUBSCRIPTION" and re.search(
                    r"entire\s+duration.{0,40}subscription",
                    context,
                    re.IGNORECASE,
                ):
                    cadence = (
                        CommissionType.RECURRING_LIFETIME,
                        "PLAN_SUBSCRIPTION",
                    )
                else:
                    cadence = (
                        _commission_type(local_context)
                        or _commission_type(context)
                        or page_cadence
                    )
                if cadence is None:
                    continue
                commission_type, cadence_scope = cadence
                applies_to = applies_to or cadence_scope
                rate_is_maximum = bool(match.groupdict().get("up_to"))
                key = (
                    page["url"],
                    str(rate),
                    commission_type.value,
                    applies_to,
                    rate_is_maximum,
                )
                if key in seen:
                    continue
                seen.add(key)
                specs.append(
                    {
                        "source_url": page["url"],
                        "source_authority": source_authority,
                        "excerpt": context,
                        "confidence": 0.84,
                        "commission_type": commission_type,
                        "commission_rate": rate / Decimal("100"),
                        "rate_is_maximum": rate_is_maximum,
                        "applies_to": applies_to,
                    }
                )
    return specs


def _find_program(db: Session, domain: str) -> Program | None:
    return db.scalar(
        select(Program)
        .join(Merchant, Program.merchant_id == Merchant.id)
        .where(Merchant.website_domain == domain)
    )


def _stored_source_urls(db: Session, program: Program | None) -> list[str]:
    """Return non-rejected evidence plus recent checked URLs for this domain."""

    if program is None:
        return []
    all_evidence = list(
        db.scalars(
            select(TermsEvidence).where(TermsEvidence.program_id == program.id)
        ).all()
    )
    all_facts = list(
        db.scalars(
            select(CommissionFact).where(CommissionFact.program_id == program.id)
        ).all()
    )
    active_sources = [
        item
        for item in [*all_evidence, *all_facts]
        if item.review_status != EvidenceReviewStatus.REJECTED
    ]
    active_normalized_urls = {
        _discovery_url_key(item.source_url) for item in active_sources
    }
    rejected_only_urls = {
        _discovery_url_key(item.source_url)
        for item in [*all_evidence, *all_facts]
        if item.review_status == EvidenceReviewStatus.REJECTED
        and _discovery_url_key(item.source_url) not in active_normalized_urls
    }
    sourced = sorted(
        active_sources,
        key=lambda item: (
            item.review_status == EvidenceReviewStatus.ACCEPTED,
            item.checked_at,
            item.id or 0,
        ),
        reverse=True,
    )
    urls: list[str] = []
    seen: set[str] = set()
    candidates = [item.source_url for item in sourced]
    domain = program.merchant.website_domain
    recent_runs = db.scalars(
        select(TermsResearchRun)
        .where(TermsResearchRun.domain == domain)
        .order_by(
            TermsResearchRun.updated_at.desc(),
            TermsResearchRun.checked_at.desc(),
            TermsResearchRun.id.desc(),
        )
    ).all()
    for run in recent_runs:
        candidates.extend(
            source_url
            for source_url in run.source_urls
            if isinstance(source_url, str)
        )
    for source_url in candidates:
        normalized_url = _normalize_discovery_url(source_url)
        host = (urlsplit(normalized_url).hostname or "").lower().rstrip(".")
        if not host or not _host_matches_domain(host, domain):
            # External partner portals are collected only from the exact saved
            # signup URL. They must never enter same-domain discovery/crawling.
            continue
        key = _discovery_url_key(normalized_url)
        if key in seen or key in rejected_only_urls:
            continue
        seen.add(key)
        urls.append(normalized_url)
        if len(urls) >= MAX_FETCHED_PAGES - 1:
            break
    return urls[: MAX_FETCHED_PAGES - 1]


def _find_or_create_program(
    db: Session,
    domain: str,
    *,
    signup_url: str | None = None,
    merchant_name: str | None = None,
    program_name: str | None = None,
) -> Program:
    program = _find_program(db, domain)
    if program is not None:
        if signup_url and not program.signup_url:
            program.signup_url = signup_url
        ensure_project_for_program(db, program, actor=WEB_COLLECTOR_VERSION)
        return program

    merchant = db.scalar(select(Merchant).where(Merchant.website_domain == domain))
    display_name = merchant_name or domain.split(".")[0].replace("-", " ").title()
    if merchant is None:
        merchant = Merchant(name=display_name, website_domain=domain)
        db.add(merchant)
        db.flush()
    program = Program(
        merchant_id=merchant.id,
        name=program_name or f"{display_name} Affiliate Program",
        signup_url=signup_url,
        status=ProgramStatus.DISCOVERED,
        paid_search_permission=PermissionStatus.NOT_CHECKED,
        brand_keyword_permission=PermissionStatus.NOT_CHECKED,
        non_brand_permission=PermissionStatus.NOT_CHECKED,
        direct_link_permission=PermissionStatus.NOT_CHECKED,
        trademark_in_ad_copy_permission=PermissionStatus.NOT_CHECKED,
    )
    db.add(program)
    db.flush()
    ensure_project_for_program(db, program, actor=WEB_COLLECTOR_VERSION)
    return program


def _find_or_create_fixture_program(db: Session, fixture: dict) -> Program:
    return _find_or_create_program(
        db,
        fixture["domain"],
        signup_url=fixture.get("signup_url"),
        merchant_name=fixture["merchant_name"],
        program_name=fixture["program_name"],
    )


AUTOMATED_EVIDENCE_COLLECTORS = {
    "AUTOMATED_FIXTURE",
    "AUTOMATED_WEB",
    "ANTHROPIC_LLM",
}


def _semantic_evidence_candidate(
    db: Session,
    program: Program,
    spec: dict,
) -> TermsEvidence | None:
    source_url = spec["source_url"].rstrip("/")
    candidates = [
        evidence
        for evidence in db.scalars(
            select(TermsEvidence).where(
                TermsEvidence.program_id == program.id,
                TermsEvidence.review_status == EvidenceReviewStatus.PROPOSED,
            )
        ).all()
        if evidence.collected_by in AUTOMATED_EVIDENCE_COLLECTORS
        and evidence.source_authority == _spec_source_authority(spec)
        and evidence.source_url.rstrip("/") == source_url
        and evidence.scope == spec["scope"]
        and evidence.decision == spec["decision"]
    ]
    return candidates[0] if len(candidates) == 1 else None


def _refresh_automated_evidence(
    db: Session,
    evidence: TermsEvidence,
    spec: dict,
    checked_at: datetime,
    evidence_hash: str,
) -> None:
    before = {
        "source_url": evidence.source_url,
        "excerpt": evidence.excerpt,
        "checked_at": evidence.checked_at.isoformat(),
        "confidence": evidence.confidence,
        "decision": evidence.decision.value,
        "scope": evidence.scope,
        "collected_by": evidence.collected_by,
        "source_authority": evidence.source_authority.value,
        "evidence_hash": evidence.evidence_hash,
    }
    evidence.source_url = spec["source_url"]
    evidence.source_type = "AFFILIATE_TERMS_PAGE"
    evidence.excerpt = spec["excerpt"]
    evidence.evidence_hash = evidence_hash
    evidence.checked_at = checked_at
    evidence.reviewer = WEB_COLLECTOR_VERSION
    evidence.confidence = spec["confidence"]
    evidence.decision = spec["decision"]
    evidence.scope = spec["scope"]
    evidence.applies_to = spec["scope"]
    evidence.collected_by = "AUTOMATED_WEB"
    evidence.source_authority = _spec_source_authority(spec)
    evidence.notes = (
        "Automatically refreshed from the same authoritative source; proposal only."
    )
    db.add(
        AuditLog(
            entity_type="terms_evidence",
            entity_id=str(evidence.id),
            action=AuditAction.UPDATE,
            actor=WEB_COLLECTOR_VERSION,
            payload_json={
                "before": before,
                "after": {
                    "source_url": evidence.source_url,
                    "excerpt": evidence.excerpt,
                    "checked_at": checked_at.isoformat(),
                    "confidence": evidence.confidence,
                    "decision": evidence.decision.value,
                    "scope": evidence.scope,
                    "collected_by": evidence.collected_by,
                    "source_authority": evidence.source_authority.value,
                    "evidence_hash": evidence.evidence_hash,
                },
                "semantic_refresh": before["evidence_hash"] != evidence_hash,
                "permissions_changed": False,
                "campaign_state_changed": False,
            },
        )
    )


def _import_permission_specs(
    db: Session, program: Program, specs: list[dict], checked_at: datetime
) -> tuple[list[TermsEvidence], int, int, int]:
    evidence_items: list[TermsEvidence] = []
    imported = 0
    duplicates = 0
    refreshed = 0
    for spec in specs:
        hash_parts = [
            str(program.id),
            spec["source_url"].rstrip("/"),
            spec["scope"],
            spec["decision"].value,
            re.sub(r"\s+", " ", spec["excerpt"]).strip(),
        ]
        source_authority = _spec_source_authority(spec)
        if source_authority != SourceAuthority.OFFICIAL:
            hash_parts.append(source_authority.value)
        evidence_hash = _hash(hash_parts)
        evidence = db.scalar(
            select(TermsEvidence).where(TermsEvidence.evidence_hash == evidence_hash)
        )
        if evidence is None:
            evidence = _semantic_evidence_candidate(db, program, spec)
            if evidence is not None:
                _refresh_automated_evidence(
                    db,
                    evidence,
                    spec,
                    checked_at,
                    evidence_hash,
                )
                duplicates += 1
                refreshed += 1
            else:
                evidence = TermsEvidence(
                    program_id=program.id,
                    source_url=spec["source_url"],
                    source_type="AFFILIATE_TERMS_PAGE",
                    excerpt=spec["excerpt"],
                    evidence_hash=evidence_hash,
                    checked_at=checked_at,
                    reviewer=WEB_COLLECTOR_VERSION,
                    confidence=spec["confidence"],
                    decision=spec["decision"],
                    scope=spec["scope"],
                    applies_to=spec["scope"],
                    review_status=EvidenceReviewStatus.PROPOSED,
                    source_authority=source_authority,
                    collected_by="AUTOMATED_WEB",
                    notes="Automatically extracted; operator review is required.",
                )
                db.add(evidence)
                db.flush()
                imported += 1
        else:
            duplicates += 1
            if (
                evidence.review_status == EvidenceReviewStatus.PROPOSED
                and evidence.collected_by in AUTOMATED_EVIDENCE_COLLECTORS
                and evidence.source_authority == source_authority
            ):
                _refresh_automated_evidence(
                    db,
                    evidence,
                    spec,
                    checked_at,
                    evidence_hash,
                )
                refreshed += 1
        evidence_items.append(evidence)
    return evidence_items, imported, duplicates, refreshed


AUTOMATED_FACT_COLLECTORS = {
    "AUTOMATED_FIXTURE",
    "AUTOMATED_WEB",
    "ANTHROPIC_LLM",
}
RECURRING_COMMISSION_TYPES = {
    CommissionType.RECURRING_UNSPECIFIED,
    CommissionType.RECURRING_LIMITED,
    CommissionType.RECURRING_LIFETIME,
}


def _commission_types_compatible(
    existing: CommissionType,
    proposed: CommissionType,
) -> bool:
    if existing == proposed:
        return True
    return (
        existing in RECURRING_COMMISSION_TYPES
        and proposed in RECURRING_COMMISSION_TYPES
        and CommissionType.RECURRING_UNSPECIFIED in {existing, proposed}
    )


def _semantic_fact_candidate(
    db: Session,
    program: Program,
    spec: dict,
) -> CommissionFact | None:
    candidates = []
    source_url = spec["source_url"].rstrip("/")
    for fact in db.scalars(
        select(CommissionFact).where(
            CommissionFact.program_id == program.id,
            CommissionFact.review_status == EvidenceReviewStatus.PROPOSED,
        )
    ).all():
        if fact.collected_by not in AUTOMATED_FACT_COLLECTORS:
            continue
        if fact.source_authority != _spec_source_authority(spec):
            continue
        if fact.source_url.rstrip("/") != source_url:
            continue
        if fact.commission_rate != spec["commission_rate"]:
            continue
        if fact.commission_flat != spec.get("commission_flat"):
            continue
        if fact.recurring_months != spec.get("recurring_months"):
            continue
        if fact.rate_is_maximum != spec["rate_is_maximum"]:
            continue
        if not _commission_types_compatible(
            fact.commission_type,
            spec["commission_type"],
        ):
            continue
        candidates.append(fact)
    return candidates[0] if len(candidates) == 1 else None


def _refresh_automated_fact(
    db: Session,
    fact: CommissionFact,
    spec: dict,
    checked_at: datetime,
    evidence_hash: str,
) -> None:
    before = {
        "source_url": fact.source_url,
        "excerpt": fact.excerpt,
        "checked_at": fact.checked_at.isoformat(),
        "confidence": fact.confidence,
        "commission_type": fact.commission_type.value,
        "commission_rate": (
            str(fact.commission_rate) if fact.commission_rate is not None else None
        ),
        "commission_flat": (
            str(fact.commission_flat) if fact.commission_flat is not None else None
        ),
        "recurring_months": fact.recurring_months,
        "rate_is_maximum": fact.rate_is_maximum,
        "applies_to": fact.applies_to,
        "collected_by": fact.collected_by,
        "source_authority": fact.source_authority.value,
        "evidence_hash": fact.evidence_hash,
    }
    fact.source_url = spec["source_url"]
    fact.excerpt = spec["excerpt"]
    fact.checked_at = checked_at
    fact.confidence = spec["confidence"]
    fact.commission_type = spec["commission_type"]
    fact.commission_rate = spec["commission_rate"]
    fact.commission_flat = spec.get("commission_flat")
    fact.recurring_months = spec.get("recurring_months")
    fact.rate_is_maximum = spec["rate_is_maximum"]
    fact.applies_to = spec["applies_to"]
    fact.collected_by = "AUTOMATED_WEB"
    fact.source_authority = _spec_source_authority(spec)
    fact.evidence_hash = evidence_hash
    fact.notes = (
        "Automatically refreshed from the same authoritative source; proposal only."
    )
    db.add(
        AuditLog(
            entity_type="commission_fact",
            entity_id=str(fact.id),
            action=AuditAction.UPDATE,
            actor=WEB_COLLECTOR_VERSION,
            payload_json={
                "before": before,
                "after": {
                    "source_url": fact.source_url,
                    "excerpt": fact.excerpt,
                    "checked_at": checked_at.isoformat(),
                    "confidence": fact.confidence,
                    "commission_type": fact.commission_type.value,
                    "commission_rate": (
                        str(fact.commission_rate)
                        if fact.commission_rate is not None
                        else None
                    ),
                    "commission_flat": (
                        str(fact.commission_flat)
                        if fact.commission_flat is not None
                        else None
                    ),
                    "recurring_months": fact.recurring_months,
                    "rate_is_maximum": fact.rate_is_maximum,
                    "applies_to": fact.applies_to,
                    "collected_by": fact.collected_by,
                    "source_authority": fact.source_authority.value,
                    "evidence_hash": fact.evidence_hash,
                },
                "semantic_refresh": before["evidence_hash"] != evidence_hash,
                "permissions_changed": False,
                "campaign_state_changed": False,
            },
        )
    )


def _import_commission_specs(
    db: Session, program: Program, specs: list[dict], checked_at: datetime
) -> tuple[list[CommissionFact], int, int, int]:
    facts: list[CommissionFact] = []
    imported = 0
    duplicates = 0
    refreshed = 0
    for spec in specs:
        hash_parts = [
            str(program.id),
            spec["source_url"],
            spec["excerpt"],
            spec["commission_type"].value,
            str(spec["commission_rate"]),
            str(spec.get("commission_flat")),
            str(spec.get("recurring_months")),
            spec["applies_to"],
        ]
        source_authority = _spec_source_authority(spec)
        if source_authority != SourceAuthority.OFFICIAL:
            hash_parts.append(source_authority.value)
        evidence_hash = _hash(hash_parts)
        fact = db.scalar(
            select(CommissionFact).where(CommissionFact.evidence_hash == evidence_hash)
        )
        if fact is None:
            fact = _semantic_fact_candidate(db, program, spec)
            if fact is not None:
                _refresh_automated_fact(db, fact, spec, checked_at, evidence_hash)
                refreshed += 1
                duplicates += 1
            else:
                fact = CommissionFact(
                    program_id=program.id,
                    scope="COMMISSION",
                    source_url=spec["source_url"],
                    source_authority=source_authority,
                    excerpt=spec["excerpt"],
                    checked_at=checked_at,
                    confidence=spec["confidence"],
                    commission_type=spec["commission_type"],
                    commission_rate=spec["commission_rate"],
                    commission_flat=spec.get("commission_flat"),
                    recurring_months=spec.get("recurring_months"),
                    rate_is_maximum=spec["rate_is_maximum"],
                    applies_to=spec["applies_to"],
                    review_status=EvidenceReviewStatus.PROPOSED,
                    collected_by="AUTOMATED_WEB",
                    evidence_hash=evidence_hash,
                    notes="Automatically extracted; kept separate from PPC permissions.",
                )
                db.add(fact)
                db.flush()
                imported += 1
        else:
            duplicates += 1
            if (
                fact.review_status == EvidenceReviewStatus.PROPOSED
                and fact.collected_by in AUTOMATED_FACT_COLLECTORS
                and fact.source_authority == source_authority
            ):
                _refresh_automated_fact(db, fact, spec, checked_at, evidence_hash)
                refreshed += 1
        facts.append(fact)
    return facts, imported, duplicates, refreshed


def _manual_result(
    db: Session,
    domain: str,
    *,
    program: Program | None,
    source_urls: list[str] | None = None,
    priority_source_urls: list[str] | None = None,
    errors: list[str] | None = None,
    source_snapshots: list[dict] | None = None,
    source_authorities: dict[str, str] | None = None,
    source_change_status: str = "INITIAL",
    source_changes: list[dict[str, str]] | None = None,
    pages: list[dict] | None = None,
) -> dict:
    checked_at = datetime.now(UTC)
    source_urls = source_urls or []
    priority_source_urls = priority_source_urls or []
    errors = errors or []
    source_snapshots = source_snapshots or []
    source_authorities = source_authorities or {}
    source_changes = source_changes or []
    status = (
        ResearchStatus.RETRY_REQUIRED
        if _errors_require_retry(errors)
        else ResearchStatus.MANUAL_INPUT_REQUIRED
    )
    run_hash = _hash([domain, status.value.lower(), *source_urls])
    run = db.scalar(select(TermsResearchRun).where(TermsResearchRun.run_hash == run_hash))
    duplicate_run = run is not None
    if run is None:
        run = TermsResearchRun(
            program_id=program.id if program else None,
            domain=domain,
            fixture_version=WEB_COLLECTOR_VERSION,
            status=status,
            checked_at=checked_at,
            discovery_confidence=0.0,
            source_urls=source_urls,
            permission_proposals=[],
            imported_fact_ids=[],
            run_hash=run_hash,
            summary=(
                "Official sources were temporarily unavailable; automation will retry. "
                "Permissions remain NOT_CHECKED."
                if status == ResearchStatus.RETRY_REQUIRED
                else "No explicit official PPC/commission evidence was extracted. "
                "Permissions remain NOT_CHECKED; add an official URL manually if available."
            ),
        )
        db.add(run)
        db.flush()
    else:
        # ``checked_at`` remains the source/evidence timestamp. ``updated_at`` is
        # the automation heartbeat proving this unchanged result was checked again.
        run.updated_at = checked_at
    db.add(
        AuditLog(
            entity_type="terms_research_run",
            entity_id=str(run.id),
            action=AuditAction.IMPORT,
            actor=WEB_COLLECTOR_VERSION,
            payload_json={
                "domain": domain,
                "status": status.value,
                "rechecked_at": checked_at.isoformat(),
                "duplicate_run": duplicate_run,
                "source_urls": source_urls,
                "priority_source_urls": priority_source_urls,
                "collection_errors": errors,
                "source_snapshots": source_snapshots,
                "source_authorities": source_authorities,
                "source_change_status": source_change_status,
                "source_changes": source_changes,
                "permissions_changed": False,
            },
        )
    )
    db.commit()
    db.refresh(run)
    program_facts = (
        db.scalars(
            select(CommissionFact).where(CommissionFact.program_id == program.id)
        ).all()
        if program is not None
        else []
    )
    return {
        "run": run,
        "program": program,
        "facts": [],
        "evidence": [],
        "imported": 0,
        "duplicates": 0,
        "refreshed": 0,
        "commission_state": commission_resolution_status(list(program_facts)),
        "imported_evidence": 0,
        "duplicate_evidence": 0,
        "refreshed_evidence": 0,
        "duplicate_run": duplicate_run,
        "collection_errors": errors,
        "source_urls": source_urls,
        "source_authorities": source_authorities,
        "source_change_status": source_change_status,
        "source_changes": source_changes,
        "pages": pages or [],
    }


def _collect_fixture(db: Session, domain: str, fixture: dict) -> dict:
    program = _find_or_create_fixture_program(db, fixture)
    attempted_at = datetime.now(UTC)
    checked_at = datetime.fromisoformat(fixture["checked_at"])
    specs = []
    for item in fixture["commission_facts"]:
        specs.append(
            {
                "source_url": item["source_url"],
                "excerpt": item["excerpt"],
                "confidence": float(item["confidence"]),
                "commission_type": CommissionType(item["commission_type"]),
                "commission_rate": (
                    Decimal(item["commission_rate"])
                    if item.get("commission_rate") is not None
                    else None
                ),
                "rate_is_maximum": bool(item["rate_is_maximum"]),
                "applies_to": item["applies_to"],
            }
        )
    facts, imported, duplicates, refreshed = _import_commission_specs(
        db,
        program,
        specs,
        checked_at,
    )
    program_facts = db.scalars(
        select(CommissionFact).where(CommissionFact.program_id == program.id)
    ).all()
    commission_state = commission_resolution_status(list(program_facts))
    status = (
        ResearchStatus.CONFLICT
        if commission_state == "CONFLICT"
        else ResearchStatus.PROPOSAL_READY
    )
    source_authorities = {
        source_url: SourceAuthority.OFFICIAL.value
        for source_url in fixture["source_urls"]
    }
    run_hash = _hash([domain, fixture["fixture_version"]])
    run = db.scalar(select(TermsResearchRun).where(TermsResearchRun.run_hash == run_hash))
    duplicate_run = run is not None
    if run is None:
        run = TermsResearchRun(
            program_id=program.id,
            domain=domain,
            fixture_version=fixture["fixture_version"],
            status=status,
            checked_at=checked_at,
            discovery_confidence=float(fixture["discovery_confidence"]),
            source_urls=fixture["source_urls"],
            permission_proposals=fixture["permission_proposals"],
            imported_fact_ids=[fact.id for fact in facts],
            run_hash=run_hash,
            summary=fixture["summary"],
        )
        db.add(run)
        db.flush()
    else:
        run.updated_at = attempted_at
    db.add(
        AuditLog(
            entity_type="terms_research_run",
            entity_id=str(run.id),
            action=AuditAction.IMPORT,
            actor="terms-fixture-v1",
            payload_json={
                "domain": domain,
                "status": status.value,
                "imported_commission_facts": imported,
                "duplicate_commission_facts": duplicates,
                "refreshed_commission_facts": refreshed,
                "duplicate_run": duplicate_run,
                "rechecked_at": attempted_at.isoformat(),
                "source_urls": list(fixture["source_urls"]),
                "source_authorities": source_authorities,
                "permissions_changed": False,
            },
        )
    )
    db.commit()
    db.refresh(run)
    for fact in facts:
        db.refresh(fact)
    db.refresh(program)
    return {
        "run": run,
        "program": program,
        "facts": facts,
        "evidence": [],
        "imported": imported,
        "duplicates": duplicates,
        "refreshed": refreshed,
        "commission_state": commission_state,
        "imported_evidence": 0,
        "duplicate_evidence": 0,
        "refreshed_evidence": 0,
        "duplicate_run": duplicate_run,
        "collection_errors": [],
        "source_urls": list(fixture["source_urls"]),
        "source_authorities": source_authorities,
        "gate_status": program_gate_status(program, list(program.terms_evidence)),
    }


def _fixture_was_seeded(db: Session, domain: str, fixture: dict) -> bool:
    return (
        db.scalar(
            select(TermsResearchRun.id).where(
                TermsResearchRun.domain == domain,
                TermsResearchRun.fixture_version == fixture["fixture_version"],
            )
        )
        is not None
    )


def collect_domain_proposal(db: Session, domain: str, *, fetcher=None) -> dict:
    """Collect sourced proposals while leaving every canonical permission unchanged."""

    fixture = _load_fixture(domain)
    if fixture is not None and not _fixture_was_seeded(db, domain, fixture):
        return _collect_fixture(db, domain, fixture)

    existing_program = _find_program(db, domain)
    priority_urls = _stored_source_urls(db, existing_program)
    if fetcher is None:
        pages, errors = discover_official_pages(
            domain,
            priority_urls=priority_urls,
        )
        partner_signup_url = _external_partner_signup_url(existing_program)
        if partner_signup_url:
            partner_pages, partner_errors = discover_partner_portal_signup(
                partner_signup_url
            )
            if partner_pages:
                pages = [*pages[: MAX_FETCHED_PAGES - 1], *partner_pages]
            errors = [*errors, *partner_errors][:MAX_FETCHED_PAGES]
    else:
        pages, errors = fetcher(domain)
    permission_specs = _extract_permission_specs(pages)
    commission_specs = _extract_commission_specs(pages)
    source_snapshots = _source_snapshots(pages)
    source_authorities = _source_authorities_for_pages(pages)
    source_change_status, source_changes = _compare_source_snapshots(
        db,
        domain,
        source_snapshots,
        collection_errors=errors,
    )
    evidence_source_urls = {
        spec["source_url"] for spec in permission_specs + commission_specs
    }
    source_urls = sorted(evidence_source_urls | {page["url"] for page in pages})
    if not permission_specs and not commission_specs:
        return _manual_result(
            db,
            domain,
            program=existing_program,
            source_urls=source_urls,
            priority_source_urls=priority_urls,
            errors=errors,
            source_snapshots=source_snapshots,
            source_authorities=source_authorities,
            source_change_status=source_change_status,
            source_changes=source_changes,
            pages=pages,
        )

    signup_url = (
        sorted(evidence_source_urls)[0]
        if evidence_source_urls
        else source_urls[0] if source_urls else None
    )
    signup_url_before = existing_program.signup_url if existing_program is not None else None
    program = _find_or_create_program(db, domain, signup_url=signup_url)
    signup_url_discovered = not signup_url_before and bool(program.signup_url)
    checked_at = datetime.now(UTC)
    evidence, imported_evidence, duplicate_evidence, refreshed_evidence = (
        _import_permission_specs(db, program, permission_specs, checked_at)
    )
    facts, imported, duplicates, refreshed = _import_commission_specs(
        db, program, commission_specs, checked_at
    )
    proposals = [
        {
            "scope": spec["scope"],
            "decision": spec["decision"].value,
            "confidence": spec["confidence"],
            "reason": spec["reason"],
            "source_authority": spec["source_authority"].value,
        }
        for spec in permission_specs
    ]
    program_facts = db.scalars(
        select(CommissionFact).where(CommissionFact.program_id == program.id)
    ).all()
    commission_state = commission_resolution_status(list(program_facts))
    status = (
        ResearchStatus.CONFLICT
        if commission_state == "CONFLICT"
        else ResearchStatus.PROPOSAL_READY
    )
    signature_parts = sorted(
        [
            f"permission:{item['source_authority'].value}:{item['source_url']}:{item['scope']}:{item['decision'].value}:{item['excerpt']}"
            for item in permission_specs
        ]
        + [
            f"commission:{item['source_authority'].value}:{item['source_url']}:{item['commission_type'].value}:{item['commission_rate']}:{item['excerpt']}"
            for item in commission_specs
        ]
    )
    run_hash = _hash([domain, WEB_COLLECTOR_VERSION, *signature_parts])
    run = db.scalar(select(TermsResearchRun).where(TermsResearchRun.run_hash == run_hash))
    duplicate_run = run is not None
    if run is None:
        run = TermsResearchRun(
            program_id=program.id,
            domain=domain,
            fixture_version=WEB_COLLECTOR_VERSION,
            status=status,
            checked_at=checked_at,
            discovery_confidence=max(
                [item["confidence"] for item in permission_specs + commission_specs],
                default=0.0,
            ),
            source_urls=source_urls,
            permission_proposals=proposals,
            imported_fact_ids=[fact.id for fact in facts],
            run_hash=run_hash,
            summary=(
                f"Extracted {len(evidence)} permission proposal(s) and {len(facts)} "
                "commission fact(s) from authoritative pages. No permission was opened."
            ),
        )
        db.add(run)
        db.flush()
    else:
        # Keep the original source timestamp while recording a successful live
        # recheck so maintenance waits another full refresh interval.
        run.updated_at = checked_at
    db.add(
        AuditLog(
            entity_type="terms_research_run",
            entity_id=str(run.id),
            action=AuditAction.IMPORT,
            actor=WEB_COLLECTOR_VERSION,
            payload_json={
                "domain": domain,
                "status": status.value,
                "source_urls": source_urls,
                "imported_terms_evidence": imported_evidence,
                "duplicate_terms_evidence": duplicate_evidence,
                "refreshed_terms_evidence": refreshed_evidence,
                "imported_commission_facts": imported,
                "duplicate_commission_facts": duplicates,
                "refreshed_commission_facts": refreshed,
                "duplicate_run": duplicate_run,
                "collection_errors": errors,
                "priority_source_urls": priority_urls,
                "source_snapshots": source_snapshots,
                "source_authorities": source_authorities,
                "source_change_status": source_change_status,
                "source_changes": source_changes,
                "signup_url_discovered": signup_url_discovered,
                "signup_url": program.signup_url if signup_url_discovered else None,
                "permissions_changed": False,
            },
        )
    )
    db.commit()
    db.refresh(run)
    db.refresh(program)
    for item in evidence:
        db.refresh(item)
    for fact in facts:
        db.refresh(fact)
    return {
        "run": run,
        "program": program,
        "facts": facts,
        "evidence": evidence,
        "imported": imported,
        "duplicates": duplicates,
        "refreshed": refreshed,
        "commission_state": commission_state,
        "imported_evidence": imported_evidence,
        "duplicate_evidence": duplicate_evidence,
        "refreshed_evidence": refreshed_evidence,
        "duplicate_run": duplicate_run,
        "collection_errors": errors,
        "source_urls": source_urls,
        "source_authorities": source_authorities,
        "source_change_status": source_change_status,
        "source_changes": source_changes,
        "signup_url_discovered": signup_url_discovered,
        "gate_status": program_gate_status(program, list(program.terms_evidence)),
        "pages": pages,
    }
