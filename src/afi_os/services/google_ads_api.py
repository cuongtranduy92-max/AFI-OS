from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

API_VERSION = "v25"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_ROOT = f"https://googleads.googleapis.com/{API_VERSION}"
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
MAX_DATE_RANGE_DAYS = 31
MAX_ATTEMPTS = 3
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


class GoogleAdsApiError(RuntimeError):
    """A sanitized Google Ads read-only connector failure."""

    def __init__(self, message: str, *, category: str = "ERROR") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class GoogleAdsCampaignMetric:
    account_external_id: str
    account_name: str
    campaign_external_id: str
    campaign_name: str
    campaign_status: str
    channel_type: str
    currency: str
    metric_date: date
    cost: Decimal
    impressions: int
    clicks: int
    conversions: Decimal


@dataclass(frozen=True)
class GoogleAdsKeywordMetric:
    text: str
    average_monthly_searches: int
    bid_low: Decimal
    bid_high: Decimal


DETAIL_REPORT_NAMES = (
    "keywords",
    "search_terms",
    "devices",
    "geography",
    "ages",
    "genders",
    "ads",
    "change_events",
)


def _bounded_json_response(response, *, max_bytes: int = MAX_RESPONSE_BYTES):
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise GoogleAdsApiError("Google Ads trả dữ liệu vượt giới hạn an toàn")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleAdsApiError("Google Ads trả JSON không hợp lệ") from exc


def _request_json(
    request,
    *,
    opener,
    timeout: int,
    max_bytes: int,
    failure_message: str,
    sleeper=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
    auth_http_codes: frozenset[int] = frozenset({401, 403}),
):
    attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS))
    for attempt in range(attempts):
        try:
            with opener(request, timeout=timeout) as response:
                return _bounded_json_response(response, max_bytes=max_bytes)
        except GoogleAdsApiError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                category = "RATE_LIMITED"
            elif exc.code in auth_http_codes:
                category = "AUTH_FAILED"
            else:
                category = "ERROR"
            retryable = exc.code in TRANSIENT_HTTP_CODES
            if retryable and attempt + 1 < attempts:
                sleeper(2**attempt)
                continue
            raise GoogleAdsApiError(failure_message, category=category) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt + 1 < attempts:
                sleeper(2**attempt)
                continue
            raise GoogleAdsApiError(failure_message, category="ERROR") from exc
        except Exception as exc:
            raise GoogleAdsApiError(failure_message, category="ERROR") from exc
    raise GoogleAdsApiError(failure_message, category="ERROR")


def _required_secret(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 16384 or "\x00" in normalized:
        raise GoogleAdsApiError(f"{label} không hợp lệ")
    return normalized


def _customer_id(value: str, label: str = "Customer ID") -> str:
    normalized = value.replace("-", "").strip()
    if len(normalized) != 10 or not normalized.isdigit():
        raise GoogleAdsApiError(f"{label} phải có đúng 10 chữ số")
    return normalized


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": _required_secret(client_id, "OAuth Client ID"),
            "client_secret": _required_secret(client_secret, "OAuth Client Secret"),
            "refresh_token": _required_secret(refresh_token, "OAuth Refresh Token"),
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    payload = _request_json(
        request,
        opener=opener,
        timeout=20,
        max_bytes=128 * 1024,
        failure_message="Không đổi được OAuth refresh token",
        sleeper=sleeper,
        max_attempts=max_attempts,
        auth_http_codes=frozenset({400, 401, 403}),
    )
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        raise GoogleAdsApiError("Google không trả OAuth access token")
    return _required_secret(access_token, "OAuth Access Token")


def build_campaign_metrics_query(start_date: date, end_date: date) -> str:
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise GoogleAdsApiError("Khoảng ngày Google Ads không hợp lệ")
    if start_date > end_date:
        raise GoogleAdsApiError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")
    if (end_date - start_date).days + 1 > MAX_DATE_RANGE_DAYS:
        raise GoogleAdsApiError(
            f"Mỗi lần chỉ đọc tối đa {MAX_DATE_RANGE_DAYS} ngày Google Ads"
        )
    return " ".join(
        (
            "SELECT customer.id, customer.descriptive_name, customer.currency_code,",
            "campaign.id, campaign.name, campaign.status,",
            "campaign.advertising_channel_type, segments.date,",
            "metrics.cost_micros, metrics.impressions, metrics.clicks,",
            "metrics.conversions FROM campaign",
            f"WHERE segments.date BETWEEN '{start_date.isoformat()}'",
            f"AND '{end_date.isoformat()}'",
            "ORDER BY segments.date, campaign.id",
        )
    )


def _decimal(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else "0"))
    except InvalidOperation as exc:
        raise GoogleAdsApiError(f"Google Ads trả {field} không hợp lệ") from exc
    if not result.is_finite() or result < 0:
        raise GoogleAdsApiError(f"Google Ads trả {field} không hợp lệ")
    return result


def _integer(value, field: str) -> int:
    result = _decimal(value, field)
    if result != result.to_integral_value():
        raise GoogleAdsApiError(f"Google Ads trả {field} không phải số nguyên")
    return int(result)


def _metric_from_result(result: dict, *, requested_customer_id: str) -> GoogleAdsCampaignMetric:
    customer = result.get("customer")
    campaign = result.get("campaign")
    segments = result.get("segments")
    metrics = result.get("metrics")
    if not all(isinstance(item, dict) for item in (customer, campaign, segments, metrics)):
        raise GoogleAdsApiError("Google Ads thiếu cấu trúc campaign metrics")
    try:
        response_customer_id = _customer_id(str(customer.get("id") or requested_customer_id))
        campaign_id = str(campaign["id"]).strip()
        campaign_name = str(campaign["name"]).strip()
        campaign_status = str(campaign["status"]).strip().upper()
        channel_type = str(campaign["advertisingChannelType"]).strip().upper()
        metric_date = date.fromisoformat(str(segments["date"]))
        currency = str(customer["currencyCode"]).strip().upper()
    except (KeyError, TypeError, ValueError) as exc:
        raise GoogleAdsApiError("Google Ads thiếu trường campaign bắt buộc") from exc
    if response_customer_id != requested_customer_id:
        raise GoogleAdsApiError("Google Ads trả dữ liệu sai Customer ID")
    if not campaign_id.isdigit() or not campaign_name or not campaign_status or not channel_type:
        raise GoogleAdsApiError("Google Ads trả campaign không hợp lệ")
    if len(currency) != 3 or not currency.isalpha():
        raise GoogleAdsApiError("Google Ads trả mã tiền tệ không hợp lệ")
    cost_micros = _decimal(metrics.get("costMicros"), "cost_micros")
    return GoogleAdsCampaignMetric(
        account_external_id=requested_customer_id,
        account_name=str(customer.get("descriptiveName") or "Google Ads").strip(),
        campaign_external_id=campaign_id,
        campaign_name=campaign_name,
        campaign_status=campaign_status,
        channel_type=channel_type,
        currency=currency,
        metric_date=metric_date,
        cost=cost_micros / Decimal("1000000"),
        impressions=_integer(metrics.get("impressions"), "impressions"),
        clicks=_integer(metrics.get("clicks"), "clicks"),
        conversions=_decimal(metrics.get("conversions"), "conversions"),
    )


def search_campaign_metrics(
    *,
    customer_id: str,
    access_token: str,
    developer_token: str,
    start_date: date,
    end_date: date,
    login_customer_id: str | None = None,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
) -> list[GoogleAdsCampaignMetric]:
    normalized_customer_id = _customer_id(customer_id)
    query = build_campaign_metrics_query(start_date, end_date)
    endpoint = (
        f"{API_ROOT}/customers/{normalized_customer_id}/googleAds:searchStream"
    )
    headers = {
        "Authorization": f"Bearer {_required_secret(access_token, 'OAuth Access Token')}",
        "Content-Type": "application/json",
        "developer-token": _required_secret(developer_token, "Developer Token"),
    }
    if login_customer_id:
        headers["login-customer-id"] = _customer_id(
            login_customer_id,
            "Login Customer ID",
        )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps({"query": query}, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    payload = _request_json(
        request,
        opener=opener,
        timeout=60,
        max_bytes=MAX_RESPONSE_BYTES,
        failure_message="Không đọc được campaign metrics từ Google Ads",
        sleeper=sleeper,
        max_attempts=max_attempts,
    )
    if not isinstance(payload, list):
        raise GoogleAdsApiError("Google Ads SearchStream không trả JSON array")
    output: list[GoogleAdsCampaignMetric] = []
    for chunk in payload:
        results = chunk.get("results") if isinstance(chunk, dict) else None
        if not isinstance(results, list):
            raise GoogleAdsApiError("Google Ads SearchStream thiếu results")
        for result in results:
            if not isinstance(result, dict):
                raise GoogleAdsApiError("Google Ads trả campaign row không hợp lệ")
            metric = _metric_from_result(
                result,
                requested_customer_id=normalized_customer_id,
            )
            if metric.metric_date < start_date or metric.metric_date > end_date:
                raise GoogleAdsApiError("Google Ads trả metric ngoài khoảng ngày yêu cầu")
            output.append(metric)
    return output


def search_google_ads_rows(
    *,
    customer_id: str,
    access_token: str,
    developer_token: str,
    query: str,
    login_customer_id: str | None = None,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
) -> list[dict]:
    """Run one bounded GAQL SearchStream query. This helper never calls a mutate method."""

    normalized_customer_id = _customer_id(customer_id)
    if not isinstance(query, str) or not query.strip() or len(query) > 20000:
        raise GoogleAdsApiError("Truy vấn Google Ads không hợp lệ")
    endpoint = f"{API_ROOT}/customers/{normalized_customer_id}/googleAds:searchStream"
    headers = {
        "Authorization": f"Bearer {_required_secret(access_token, 'OAuth Access Token')}",
        "Content-Type": "application/json",
        "developer-token": _required_secret(developer_token, "Developer Token"),
    }
    if login_customer_id:
        headers["login-customer-id"] = _customer_id(login_customer_id, "Login Customer ID")
    request = urllib.request.Request(
        endpoint,
        data=json.dumps({"query": query.strip()}, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    payload = _request_json(
        request,
        opener=opener,
        timeout=60,
        max_bytes=MAX_RESPONSE_BYTES,
        failure_message="Không đọc được báo cáo chi tiết từ Google Ads",
        sleeper=sleeper,
        max_attempts=max_attempts,
    )
    if not isinstance(payload, list):
        raise GoogleAdsApiError("Google Ads SearchStream không trả JSON array")
    rows: list[dict] = []
    for chunk in payload:
        results = chunk.get("results") if isinstance(chunk, dict) else None
        if not isinstance(results, list):
            raise GoogleAdsApiError("Google Ads SearchStream thiếu results")
        if not all(isinstance(item, dict) for item in results):
            raise GoogleAdsApiError("Google Ads trả dòng báo cáo không hợp lệ")
        rows.extend(results)
    return rows


def _campaign_filter(campaign_external_id: str) -> str:
    value = str(campaign_external_id).strip()
    if not value.isdigit():
        raise GoogleAdsApiError("Campaign ID Google Ads không hợp lệ")
    return value


def build_campaign_detail_queries(
    *,
    customer_id: str,
    campaign_external_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, str]:
    """Build the ticket's eight read-only reports for one campaign."""

    normalized_customer_id = _customer_id(customer_id)
    campaign_id = _campaign_filter(campaign_external_id)
    if start_date > end_date or (end_date - start_date).days + 1 > MAX_DATE_RANGE_DAYS:
        raise GoogleAdsApiError(f"Mỗi lần chỉ đọc tối đa {MAX_DATE_RANGE_DAYS} ngày Google Ads")
    dates = f"segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
    campaign = f"campaign.id = {campaign_id}"
    since = datetime.combine(max(start_date, end_date - timedelta(days=29)), datetime.min.time())
    resource = f"customers/{normalized_customer_id}/campaigns/{campaign_id}"
    return {
        "keywords": " ".join((
            "SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,",
            "ad_group_criterion.status, metrics.ctr, metrics.average_cpc, metrics.cost_micros,",
            "metrics.impressions, metrics.clicks, metrics.search_impression_share",
            "FROM keyword_view WHERE", campaign, "AND", dates,
            "ORDER BY metrics.clicks DESC",
        )),
        "search_terms": " ".join((
            "SELECT search_term_view.search_term, search_term_view.status, metrics.cost_micros,",
            "metrics.impressions, metrics.clicks, metrics.conversions",
            "FROM search_term_view WHERE", campaign, "AND", dates,
            "ORDER BY metrics.clicks DESC",
        )),
        "devices": " ".join((
            "SELECT segments.device, metrics.ctr, metrics.cost_micros, metrics.impressions,",
            "metrics.clicks, metrics.conversions FROM campaign WHERE", campaign, "AND", dates,
            "ORDER BY metrics.clicks DESC",
        )),
        "geography": " ".join((
            "SELECT geographic_view.country_criterion_id, geographic_view.location_type,",
            "metrics.ctr, metrics.cost_micros, metrics.impressions, metrics.clicks,",
            "metrics.conversions FROM geographic_view WHERE", campaign, "AND", dates,
            "ORDER BY metrics.clicks DESC",
        )),
        "ages": " ".join((
            "SELECT ad_group_criterion.age_range.type, metrics.ctr, metrics.cost_micros,",
            "metrics.impressions, metrics.clicks, metrics.conversions FROM age_range_view",
            "WHERE", campaign, "AND", dates, "ORDER BY metrics.clicks DESC",
        )),
        "genders": " ".join((
            "SELECT ad_group_criterion.gender.type, metrics.ctr, metrics.cost_micros,",
            "metrics.impressions, metrics.clicks, metrics.conversions FROM gender_view",
            "WHERE", campaign, "AND", dates, "ORDER BY metrics.clicks DESC",
        )),
        "ads": " ".join((
            "SELECT ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad.type,",
            "ad_group_ad.ad.responsive_search_ad.headlines,",
            "ad_group_ad.ad.responsive_search_ad.descriptions, metrics.ctr,",
            "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions",
            "FROM ad_group_ad WHERE", campaign, "AND", dates,
            "ORDER BY metrics.impressions DESC",
        )),
        "change_events": " ".join((
            "SELECT change_event.resource_name, change_event.change_date_time,",
            "change_event.change_resource_type, change_event.changed_fields,",
            "change_event.old_resource, change_event.new_resource FROM change_event",
            f"WHERE change_event.change_date_time >= '{since:%Y-%m-%d %H:%M:%S}'",
            f"AND change_event.campaign = '{resource}'",
            "ORDER BY change_event.change_date_time DESC LIMIT 1000",
        )),
    }


def search_campaign_detail_reports(
    *,
    customer_id: str,
    campaign_external_id: str,
    access_token: str,
    developer_token: str,
    start_date: date,
    end_date: date,
    login_customer_id: str | None = None,
    row_searcher=search_google_ads_rows,
) -> dict[str, list]:
    """Fetch every diagnostic report; one unavailable view must not erase the others."""

    queries = build_campaign_detail_queries(
        customer_id=customer_id,
        campaign_external_id=campaign_external_id,
        start_date=start_date,
        end_date=end_date,
    )
    output: dict[str, list] = {}
    errors: list[dict[str, str]] = []
    for name, query in queries.items():
        try:
            output[name] = row_searcher(
                customer_id=customer_id,
                access_token=access_token,
                developer_token=developer_token,
                query=query,
                login_customer_id=login_customer_id,
            )
        except GoogleAdsApiError as exc:
            output[name] = []
            errors.append({"report": name, "message": str(exc), "category": exc.category})
    output["_errors"] = errors
    return output


def generate_domain_keyword_ideas(
    *,
    customer_id: str,
    domain: str,
    brand_name: str,
    access_token: str,
    developer_token: str,
    login_customer_id: str | None = None,
    opener=urllib.request.urlopen,
    sleeper=time.sleep,
    max_attempts: int = MAX_ATTEMPTS,
) -> list[GoogleAdsKeywordMetric]:
    """Read global English keyword metrics from a domain seed; never mutate Ads."""

    normalized_customer_id = _customer_id(customer_id)
    normalized_domain = domain.strip().lower()
    if not normalized_domain or len(normalized_domain) > 255 or "/" in normalized_domain:
        raise GoogleAdsApiError("Domain Keyword Planner không hợp lệ")
    seed = brand_name.strip() or normalized_domain.split(".", 1)[0]
    endpoint = f"{API_ROOT}/customers/{normalized_customer_id}:generateKeywordIdeas"
    headers = {
        "Authorization": f"Bearer {_required_secret(access_token, 'OAuth Access Token')}",
        "Content-Type": "application/json",
        "developer-token": _required_secret(developer_token, "Developer Token"),
    }
    if login_customer_id:
        headers["login-customer-id"] = _customer_id(
            login_customer_id,
            "Login Customer ID",
        )
    body = {
        "language": "languageConstants/1000",
        "includeAdultKeywords": False,
        "keywordPlanNetwork": "GOOGLE_SEARCH",
        "keywordAndUrlSeed": {
            "keywords": [seed],
            "url": f"https://{normalized_domain}",
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    payload = _request_json(
        request,
        opener=opener,
        timeout=60,
        max_bytes=MAX_RESPONSE_BYTES,
        failure_message="Không đọc được Keyword Planner từ Google Ads",
        sleeper=sleeper,
        max_attempts=max_attempts,
    )
    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        raise GoogleAdsApiError("Keyword Planner không trả danh sách kết quả")
    output: list[GoogleAdsKeywordMetric] = []
    for item in raw_results:
        metrics = item.get("keywordIdeaMetrics") if isinstance(item, dict) else None
        text = str(item.get("text") or "").strip() if isinstance(item, dict) else ""
        if not text or not isinstance(metrics, dict):
            continue
        output.append(
            GoogleAdsKeywordMetric(
                text=text,
                average_monthly_searches=_integer(
                    metrics.get("avgMonthlySearches"),
                    "avg_monthly_searches",
                ),
                bid_low=_decimal(
                    metrics.get("lowTopOfPageBidMicros"),
                    "low_top_of_page_bid_micros",
                )
                / Decimal("1000000"),
                bid_high=_decimal(
                    metrics.get("highTopOfPageBidMicros"),
                    "high_top_of_page_bid_micros",
                )
                / Decimal("1000000"),
            )
        )
    if not output:
        raise GoogleAdsApiError("Keyword Planner không có dữ liệu cho domain này")
    return output
