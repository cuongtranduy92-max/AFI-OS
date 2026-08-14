import re
from datetime import date, datetime
from decimal import Decimal
from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from afi_os.enums import (
    AdsAccountHealth,
    AdsAccountState,
    AdsAccountType,
    AdvertiserClassification,
    AutomationJobStatus,
    AutomationJobType,
    CampPlanStatus,
    CommissionState,
    CommissionType,
    DataQuality,
    EmailSource,
    EvidenceReviewStatus,
    FxRateReviewStatus,
    PermissionStatus,
    ProgramStatus,
    ProjectStage,
    ReconciliationStatus,
    RegistrationStatus,
    ResearchStatus,
    SourceAuthority,
    TermsWarningStatus,
    WatchStatus,
)

PERMISSION_SCOPES = {
    "PAID_SEARCH",
    "BRAND_KEYWORD",
    "NON_BRAND",
    "DIRECT_LINK",
    "TRADEMARK_AD_COPY",
}


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value.split("/")[0].split(":")[0].removeprefix("www.")


def validate_source_url(value: str) -> str:
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source_url must be a complete http(s) URL")
    return value


def normalize_capture_domain(value: str) -> str:
    """Normalize a web hostname without accepting labels that pollute the project graph."""

    raw = value.strip().lower()
    if not raw:
        raise ValueError("domain cannot be blank")
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlsplit(candidate)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("domain contains an invalid port") from exc
    if parsed.username or parsed.password:
        raise ValueError("domain must not contain credentials")
    host = (parsed.hostname or "").rstrip(".").removeprefix("www.")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("domain must be a hostname, not an IP address")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("domain is not a valid hostname") from exc
    labels = ascii_host.split(".")
    if len(labels) < 2 or len(ascii_host) > 253:
        raise ValueError("domain must contain a registrable-style hostname")
    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    if any(not label_pattern.fullmatch(label) for label in labels):
        raise ValueError("domain contains an invalid hostname label")
    return ascii_host


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class OperationsItem(BaseModel):
    key: str
    item_type: str
    severity: str
    title: str
    detail: str
    action_label: str
    action_view: str
    entity_id: str | None = None
    program_id: int | None = None
    program_name: str | None = None
    merchant_domain: str | None = None
    source_url: str | None = None
    created_at: datetime | None = None
    requires_user: bool = True


class OperationsInboxResponse(BaseModel):
    open_count: int
    requires_user_count: int
    warning_count: int
    counts_by_type: dict[str, int]
    counts_by_severity: dict[str, int]
    items: list[OperationsItem]


class RuntimeStatusResponse(BaseModel):
    status: str
    server_service_loaded: bool
    maintenance_service_loaded: bool
    maintenance_status: str | None = None
    maintenance_last_started_at: datetime | None = None
    maintenance_last_ended_at: datetime | None = None
    maintenance_next_due_at: datetime | None = None
    maintenance_overdue: bool
    maintenance_rows_read: int
    maintenance_rows_written: int
    maintenance_error: str | None = None
    campaign_auto_map_total: int = 0
    campaign_auto_map_unlinked_scanned: int = 0
    campaign_auto_map_mapped: int = 0
    campaign_auto_map_unresolved: int = 0
    campaign_auto_map_preserved_existing: int = 0
    ads_import_status: str | None = None
    ads_import_last_at: datetime | None = None
    ads_files_seen: int
    ads_files_content_detected: int = 0
    ads_files_duplicate_skipped: int = 0
    ads_files_superseded: int = 0
    ads_files_account_mismatch: int = 0
    ads_files_missing_columns: int = 0
    ads_confirmed_file_count: int = 0
    ads_last_confirmed_at: datetime | None = None
    ads_files_retried_after_error: int = 0
    ads_files_retried_after_mapping: int = 0
    ads_rows_read: int
    ads_rows_written: int
    ads_campaign_ids_recovered: int = 0
    ads_error_count: int
    ads_latest_metric_date: date | None = None
    ads_data_stale: bool
    ads_latest_report_source_at: datetime | None = None
    ads_intraday_refresh_due: bool = False
    ads_next_intraday_refresh_at: datetime | None = None
    commission_import_status: str | None = None
    commission_import_last_at: datetime | None = None
    commission_files_seen: int
    commission_files_retried_after_error: int = 0
    commission_files_retried_after_mapping: int = 0
    commission_rows_read: int
    commission_rows_written: int
    commission_error_count: int
    commission_mapping_required_count: int
    google_ads_api_status: str
    google_ads_customer_ids: list[str] = Field(default_factory=list)
    google_ads_api_customer_count: int
    google_ads_api_missing_credentials: list[str]
    google_ads_login_customer_id_configured: bool = False
    google_ads_api_write_operations_enabled: bool
    google_ads_api_sync_status: str | None = None
    google_ads_api_sync_last_at: datetime | None = None
    google_ads_api_sync_due: bool = False
    google_ads_api_next_attempt_at: datetime | None = None
    google_ads_api_sync_request_pending: bool = False
    google_ads_api_rows_read: int = 0
    google_ads_api_rows_written: int = 0
    google_ads_api_reconciliation_differences: int = 0
    latest_scheduled_backup_name: str | None = None
    latest_scheduled_backup_at: datetime | None = None
    latest_scheduled_backup_size_bytes: int | None = None
    scheduled_backup_due: bool = False
    scheduled_backup_invalid_count: int = 0
    next_backup_due_at: datetime | None = None
    programs_total: int
    terms_fresh: int
    terms_stale: int
    terms_due_count: int
    terms_retry_pending: int = 0
    terms_next_refresh_at: datetime | None = None
    terms_next_scheduled_refresh_at: datetime | None = None
    programs_terms_ok: int
    programs_terms_warnings: int


class GoogleAdsReadinessResponse(BaseModel):
    status: str
    mode: str
    customer_ids: list[str]
    customer_count: int
    credentials_present: dict[str, bool]
    missing_credentials: list[str]
    manager_customer_id_required_only_for_manager_access: bool
    login_customer_id_configured: bool = False
    two_step_verification_external_check: bool
    write_operations_enabled: bool
    csv_fallback_enabled: bool
    api_center_url: str


class AdvertiserCreate(BaseModel):
    verified_name: str = Field(min_length=1, max_length=255)
    verified_location: str | None = Field(default=None, max_length=255)
    external_key: str | None = Field(default=None, max_length=255)
    classification: AdvertiserClassification = AdvertiserClassification.UNKNOWN
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_url: str | None = None


class AdvertiserRead(ORMModel):
    id: int
    verified_name: str
    verified_location: str | None
    classification: AdvertiserClassification
    confidence: float
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    domain_count: int = 0
    is_goldmine: bool = False
    is_watchlisted: bool = False
    last_expanded_at: datetime | None = None


class ProjectCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    brand_name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=160)
    watch_status: WatchStatus = WatchStatus.NEW
    affiliate_program_found: bool = False
    stage: ProjectStage = ProjectStage.INTAKE
    registration_status: RegistrationStatus = RegistrationStatus.NOT_STARTED
    owner: str | None = Field(default=None, max_length=120)
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due_at: datetime | None = None

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        value = value.strip().lower()
        for prefix in ("https://", "http://"):
            if value.startswith(prefix):
                value = value[len(prefix) :]
        return value.split("/")[0].removeprefix("www.")


class ProjectRead(ORMModel):
    id: int
    domain: str
    brand_name: str
    category: str | None
    watch_status: WatchStatus
    affiliate_program_found: bool
    stage: ProjectStage
    registration_status: RegistrationStatus
    owner: str | None
    next_action: str | None
    next_action_due_at: datetime | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class ProjectIntakeRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=2000)
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    @field_validator("domain")
    @classmethod
    def normalize_intake_domain(cls, value: str) -> str:
        return normalize_capture_domain(value)

    @field_validator("actor")
    @classmethod
    def normalize_intake_actor(cls, value: str) -> str:
        return value.strip()


class ProjectWorkflowUpdate(BaseModel):
    stage: ProjectStage | None = None
    registration_status: RegistrationStatus | None = None
    owner: str | None = Field(default=None, max_length=120)
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due_at: datetime | None = None
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    @field_validator("owner", "next_action", "actor")
    @classmethod
    def normalize_workflow_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class MetricEnvelope(BaseModel):
    key: str
    label: str
    value: int | float | str | None
    unit: str | None = None
    quality: DataQuality = DataQuality.UNKNOWN
    source_name: str
    source_url: str | None = None
    observed_at: datetime | None = None
    valid_until: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    geography: str | None = None
    language: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    method_version: str
    collection_state: str = "NOT_COLLECTED"
    previous_value: int | float | str | None = None
    change_reason: str | None = None
    lineage: list[dict[str, Any]] = Field(default_factory=list)


class ProjectPortfolioItem(BaseModel):
    id: int
    domain: str
    brand_name: str
    category: str | None
    watch_status: WatchStatus
    stage: ProjectStage
    registration_status: RegistrationStatus
    owner: str | None
    next_action: str | None
    next_action_due_at: datetime | None
    program_id: int | None
    program_name: str | None
    program_status: ProgramStatus | None
    signup_url: str | None
    terms_gate_status: str
    commission_state: str
    opportunity_potential: int | None
    opportunity_state: str
    evidence_confidence: int
    confidence_components: dict[str, int]
    risk_badges: list[str]
    project_included: bool = True
    metrics: dict[str, MetricEnvelope]
    updated_at: datetime


class ProjectIntakeResponse(BaseModel):
    project: ProjectPortfolioItem
    created: bool
    warning_only: bool = True
    permissions_changed: bool = False
    campaign_state_changed: bool = False
    google_ads_write: bool = False


class ProjectCheckValue(BaseModel):
    key: str
    label: str
    value: Any = None
    unit: str | None = None
    collection_state: str = "NOT_COLLECTED"
    quality: DataQuality = DataQuality.UNKNOWN
    source_name: str = "Chưa có dữ liệu"
    source_url: str | None = None
    observed_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    note: str | None = None
    display_value: str | None = None
    range_low: int | None = None
    range_high: int | None = None
    is_estimate: bool = False
    verdict: bool | None = None


class ProjectCheckEvidence(BaseModel):
    evidence_id: int
    scope: str
    decision: PermissionStatus
    review_status: EvidenceReviewStatus
    excerpt: str
    summary_vi: str | None = None
    quote_vi: str | None = None
    source_url: str
    source_authority: SourceAuthority
    checked_at: datetime
    confidence: float = Field(default=0.0, ge=0, le=1)


class ProjectCheckCommission(BaseModel):
    commission_fact_id: int
    commission_type: CommissionType
    commission_rate: Decimal | None
    commission_flat: Decimal | None = None
    recurring_months: int | None = None
    rate_is_maximum: bool
    applies_to: str
    review_status: EvidenceReviewStatus
    excerpt: str
    summary_vi: str | None = None
    quote_vi: str | None = None
    source_url: str
    source_authority: SourceAuthority
    checked_at: datetime
    confidence: float = Field(default=0.0, ge=0, le=1)


class CommercialProposalRead(ORMModel):
    id: int
    program_id: int
    scope: str
    payload_json: dict[str, Any]
    source_url: str
    excerpt: str
    summary_vi: str | None = None
    quote_vi: str | None = None
    source_authority: SourceAuthority
    confidence: float = Field(ge=0, le=1)
    review_status: EvidenceReviewStatus
    collected_by: str
    reviewed_at: datetime | None
    reviewed_by: str | None
    notes: str | None


class ProjectTermsExtractionResponse(BaseModel):
    project_id: int
    program_id: int
    status: str
    cached: bool = False
    model: str
    source_urls: list[str] = Field(default_factory=list)
    commission_facts: list[ProjectCheckCommission] = Field(default_factory=list)
    terms_evidence: list[ProjectCheckEvidence] = Field(default_factory=list)
    commercial_proposals: list[CommercialProposalRead] = Field(default_factory=list)
    ppc_policy: dict[str, Any] | None = None
    rejected: list[str] = Field(default_factory=list)
    permissions_changed: bool = False
    campaign_state_changed: bool = False
    google_ads_write: bool = False


class ProjectCheckCriterion(BaseModel):
    key: str
    label: str
    status: str
    value: Any = None
    threshold: str
    explanation: str


class ProjectCheckCollectionNeed(BaseModel):
    group: str
    fields: list[str]
    source_required: str
    status: str


class ProjectStepOneResponse(BaseModel):
    project_id: int
    program_id: int | None = None
    project_name: str
    domain: str
    stage: ProjectStage
    registration_status: RegistrationStatus
    fields: dict[str, ProjectCheckValue]
    permissions: dict[str, PermissionStatus]
    terms_gate_status: str
    commission_state: str
    terms_evidence: list[ProjectCheckEvidence] = Field(default_factory=list)
    commission_facts: list[ProjectCheckCommission] = Field(default_factory=list)
    commercial_proposals: list[CommercialProposalRead] = Field(default_factory=list)
    ppc_policy: dict[str, Any] | None = None
    criteria: list[ProjectCheckCriterion] = Field(default_factory=list)
    passed_criteria: int = Field(ge=0)
    known_criteria: int = Field(ge=0)
    total_criteria: int = Field(ge=0)
    readiness: str
    decision_ready: bool = False
    blocking_fields: list[str] = Field(default_factory=list)
    collection_needs: list[ProjectCheckCollectionNeed] = Field(default_factory=list)
    warning_only: bool = True
    project_included: bool = True


class CommercialProposalReviewResponse(BaseModel):
    proposal: CommercialProposalRead
    applied_fields: list[str] = Field(default_factory=list)
    step_one: ProjectStepOneResponse
    permissions_changed: bool = False
    campaign_state_changed: bool = False
    google_ads_write: bool = False


class ManualPackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price_usd: Decimal = Field(gt=0)
    source_url: str | None = Field(default=None, max_length=1000)
    actor: str = Field(default="Tran", min_length=1, max_length=120)

    @field_validator("source_url")
    @classmethod
    def normalize_optional_source_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_source_url(value)


class ProjectCheckSourceResult(BaseModel):
    source: str
    status: str
    detail: str
    requires_user: bool = False
    fields: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    setup_command: str | None = None


class ProjectAutoCheckResponse(BaseModel):
    project: ProjectPortfolioItem
    step_one: ProjectStepOneResponse
    sources: list[ProjectCheckSourceResult] = Field(default_factory=list)
    decision_ready: bool = False
    blocking_fields: list[str] = Field(default_factory=list)
    permissions_changed: bool = False
    campaign_state_changed: bool = False
    google_ads_write: bool = False


class AppraiseRequest(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def normalize_appraise_domain(cls, value: str) -> str:
        return normalize_capture_domain(value)


class AppraiseBatchRequest(BaseModel):
    domains: list[str] = Field(min_length=1, max_length=50)

    @field_validator("domains")
    @classmethod
    def normalize_appraise_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            domain = normalize_capture_domain(value)
            if domain not in normalized:
                normalized.append(domain)
        if not normalized:
            raise ValueError("Cần ít nhất một domain hợp lệ")
        return normalized


class AppraisalTraffic(BaseModel):
    monthly: int | float | None = None
    top_countries: list[tuple[str, float]] | None = None
    source: str | None = None
    source_status: Literal["ready", "partial", "pending"] = "pending"


class AppraisalKeyword(BaseModel):
    term: str | None = None
    search_volume: int | float | None = None
    search_volume_low: int | None = None
    search_volume_high: int | None = None
    search_volume_display: str | None = None
    search_volume_is_estimate: bool = False
    search_volume_verdict: bool | None = None
    bid_low_vnd: int | float | None = None
    bid_high_vnd: int | float | None = None
    source: str | None = None


class AppraisalAdvertisers(BaseModel):
    count: int | None = None
    active_count: int | None = None
    total_ever: int | None = None
    also_running: list[str] | None = None
    source: str | None = None


class AppraisalCommission(BaseModel):
    type: str | None = None
    percent: float | None = None
    packages: list[tuple[str, float]] | None = None
    avg_package: float | None = None


class AppraisalPayment(BaseModel):
    gateways: list[str] | None = None
    min_payment: float | None = None
    clear_days: int | None = None
    cookie_days: int | None = None
    net: str | None = None


class AppraisalTerms(BaseModel):
    ads_allowed: bool | None = None
    brand_bid_restricted: bool | None = None
    summary: str | None = None
    source: str | None = None


class AppraisalPayback(BaseModel):
    days_low: float | None = None
    days_high: float | None = None
    mode: str | None = None


class AppraisalFlag(BaseModel):
    level: str
    msg: str


class AppraisalScore(BaseModel):
    total: int | None = Field(default=None, ge=0, le=100)
    pass_: bool | None = Field(default=None, alias="pass", serialization_alias="pass")
    flags: list[AppraisalFlag] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AppraisalFieldStatus(BaseModel):
    status: Literal["ready", "loading", "pending_source", "blocked", "error"]
    label: str
    detail: str | None = None
    color: Literal["green", "grey", "yellow", "red"] = "grey"
    retryable: bool = False
    source_urls: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None
    cache_date: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class AppraisalResponse(BaseModel):
    domain: str
    niche: str | None = None
    affiliate_link: str | None = None
    traffic: AppraisalTraffic
    keyword: AppraisalKeyword
    advertisers: AppraisalAdvertisers
    commission: AppraisalCommission
    payment: AppraisalPayment
    terms: AppraisalTerms
    payback: AppraisalPayback
    score: AppraisalScore
    job_id: int | None = None
    job_status: Literal["QUEUED", "RUNNING", "DONE", "FAILED"] | None = None
    field_statuses: dict[str, AppraisalFieldStatus] = Field(default_factory=dict)


class AppraisalJobResponse(BaseModel):
    job_id: int
    domain: str
    status: Literal["QUEUED", "RUNNING", "DONE", "FAILED"]
    progress_done: int = Field(ge=0)
    progress_total: int = Field(ge=0)
    created_at: datetime
    finished_at: datetime | None = None
    appraisal: AppraisalResponse


class AppraisalBatchResponse(BaseModel):
    batch_id: str
    total: int = Field(ge=1, le=50)
    done: int = Field(ge=0)
    jobs: list[AppraisalResponse] = Field(default_factory=list)


class ProjectStepOneDecisionRequest(BaseModel):
    decision: Literal["PREPARE_STEP_2", "KEEP_RESEARCHING"]
    actor: str = Field(default="local-user", min_length=1, max_length=120)
    risk_acknowledged: bool = False

    @field_validator("actor")
    @classmethod
    def normalize_step_one_actor(cls, value: str) -> str:
        return value.strip()


class ProjectStepOneDecisionResponse(BaseModel):
    project: ProjectPortfolioItem
    decision: Literal["PREPARE_STEP_2", "KEEP_RESEARCHING"]
    audit_written: bool = True
    project_included: bool = True
    campaign_state_changed: bool = False
    permissions_changed: bool = False
    google_ads_write: bool = False


class CampPlanSitelink(BaseModel):
    label: str = Field(max_length=500)
    final_url: str = Field(max_length=1000)


class CampPlanContent(BaseModel):
    headlines: list[str] = Field(default_factory=list, max_length=50)
    descriptions: list[str] = Field(default_factory=list, max_length=20)
    sitelinks: list[CampPlanSitelink] = Field(default_factory=list, max_length=20)
    callouts: list[str] = Field(default_factory=list, max_length=20)


class CampPlanLintIssue(BaseModel):
    level: Literal["error", "warning"]
    section: Literal["headlines", "descriptions", "sitelinks", "callouts", "plan"]
    index: int | None = None
    message: str


class CampPlanGenerateRequest(BaseModel):
    ref_url: str = Field(min_length=1, max_length=1000)
    existing_plan: CampPlanContent | None = None
    ads_account_id: int | None = Field(default=None, gt=0)

    @field_validator("ref_url")
    @classmethod
    def validate_ref_url(cls, value: str) -> str:
        normalized = validate_source_url(value)
        parsed = urlsplit(normalized)
        if parsed.username or parsed.password:
            raise ValueError("ref_url must not contain credentials")
        return normalized


class CampPlanDeployRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    @field_validator("actor")
    @classmethod
    def normalize_camp_plan_actor(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("actor cannot be blank")
        return normalized


class CampPlanResponse(BaseModel):
    id: int
    project_id: int
    domain: str
    brand_name: str
    signup_url: str | None = None
    ads_account_id: int | None = None
    ads_account_label: str | None = None
    ref_url: str
    plan: CampPlanContent
    linter: list[CampPlanLintIssue] = Field(default_factory=list)
    status: CampPlanStatus
    has_errors: bool
    created_at: datetime
    updated_at: datetime
    google_ads_write: bool = False


class CampPlanEligibleProject(BaseModel):
    project_id: int
    domain: str
    brand_name: str
    signup_url: str | None = None
    score_total: int | None = None
    score_pass: bool = True
    camp_plan_status: CampPlanStatus | None = None
    ref_url: str | None = None
    ads_account_id: int | None = None


class SecretFreeModel(BaseModel):
    """Reject undeclared fields so credentials cannot silently enter resource APIs."""

    model_config = ConfigDict(extra="forbid")


class EmailCreate(SecretFreeModel):
    address: str = Field(min_length=3, max_length=320)
    source: EmailSource = EmailSource.SELF
    created_at: datetime | None = None
    declared_done: bool = False
    device_changes: int = Field(default=0, ge=0, le=100)
    usage_history: list[str] = Field(default_factory=list, max_length=100)
    status_override: Literal["LOCKED"] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("address")
    @classmethod
    def normalize_email_address(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[1]:
            raise ValueError("Địa chỉ email không hợp lệ")
        return normalized

    @field_validator("usage_history")
    @classmethod
    def normalize_usage_history(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in output:
                output.append(item[:120])
        return output

    @field_validator("note")
    @classmethod
    def normalize_email_note(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class EmailUpdate(SecretFreeModel):
    source: EmailSource | None = None
    created_at: datetime | None = None
    declared_done: bool | None = None
    device_changes: int | None = Field(default=None, ge=0, le=100)
    usage_history: list[str] | None = Field(default=None, max_length=100)
    status_override: Literal["LOCKED"] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("usage_history")
    @classmethod
    def normalize_update_usage_history(cls, values: list[str] | None) -> list[str] | None:
        return EmailCreate.normalize_usage_history(values) if values is not None else None

    @field_validator("note")
    @classmethod
    def normalize_update_email_note(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class NurtureCheckRequest(SecretFreeModel):
    tasks_done: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("tasks_done")
    @classmethod
    def normalize_tasks(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in output:
                output.append(item[:300])
        if len(output) > 3:
            raise ValueError("Tối đa 3 tác vụ mỗi ngày")
        return output


class NurtureStatusResponse(BaseModel):
    stage: str
    age_days: int
    chin_eta_days: int
    is_chin: bool
    is_dirty: bool
    tasks_today: list[str] = Field(default_factory=list)
    tasks_done: list[str] = Field(default_factory=list)


class EmailResponse(BaseModel):
    id: int
    address: str
    source: EmailSource
    created_at: datetime
    declared_done: bool
    device_changes: int
    usage_history: list[str] = Field(default_factory=list)
    status_override: str | None = None
    note: str | None = None
    nurture_status: NurtureStatusResponse


class AdsAccountCreate(SecretFreeModel):
    email_id: int | None = Field(default=None, gt=0)
    type: AdsAccountType
    external_id: str | None = Field(default=None, max_length=32)
    display_name: str = Field(min_length=1, max_length=255)
    rent_cost: Decimal = Field(default=Decimal("0"), ge=0)
    spend_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    state: AdsAccountState = AdsAccountState.DANG_KY
    health: AdsAccountHealth = AdsAccountHealth.OK
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("display_name")
    @classmethod
    def normalize_ads_account_name(cls, value: str) -> str:
        normalized = normalize_optional_text(value)
        if normalized is None:
            raise ValueError("Tên tài khoản không được để trống")
        return normalized

    @field_validator("external_id", "note")
    @classmethod
    def normalize_ads_account_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class AdsAccountUpdate(SecretFreeModel):
    email_id: int | None = Field(default=None, gt=0)
    type: AdsAccountType | None = None
    display_name: str | None = Field(default=None, max_length=255)
    rent_cost: Decimal | None = Field(default=None, ge=0)
    spend_fee_pct: Decimal | None = Field(default=None, ge=0, le=100)
    state: AdsAccountState | None = None
    health: AdsAccountHealth | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("display_name")
    @classmethod
    def normalize_update_ads_account_name(cls, value: str | None) -> str | None:
        normalized = normalize_optional_text(value)
        if value is not None and normalized is None:
            raise ValueError("Tên tài khoản không được để trống")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_update_ads_account_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class AdsAccountResponse(BaseModel):
    id: int
    external_id: str
    email_id: int | None = None
    email_address: str | None = None
    type: AdsAccountType | None = None
    display_name: str
    rent_cost: Decimal
    spend_fee_pct: Decimal
    state: AdsAccountState
    health: AdsAccountHealth
    current_project_id: int | None = None
    current_project_domain: str | None = None
    camp_plan_id: int | None = None
    camp_plan_status: CampPlanStatus | None = None
    note: str | None = None
    selectable: bool = False


RESOURCE_TYPES = {
    "paypal", "payoneer", "wise", "card", "crypto_wallet",
    "exchange", "sim", "device", "website", "social",
}


class ResourceCreate(SecretFreeModel):
    type: str
    label: str = Field(min_length=1, max_length=255)
    monthly_in_usd: Decimal = Field(default=Decimal("0"), ge=0)
    linked_gateways: list[str] = Field(default_factory=list, max_length=50)
    owner_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("type")
    @classmethod
    def validate_resource_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in RESOURCE_TYPES:
            raise ValueError("Loại tài nguyên không được hỗ trợ")
        return normalized

    @field_validator("label")
    @classmethod
    def normalize_resource_label(cls, value: str) -> str:
        normalized = normalize_optional_text(value)
        if normalized is None:
            raise ValueError("Nhãn tài nguyên không được để trống")
        return normalized

    @field_validator("owner_name", "note")
    @classmethod
    def normalize_resource_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("linked_gateways")
    @classmethod
    def normalize_gateways(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in output:
                output.append(item[:120])
        return output


class ResourceUpdate(SecretFreeModel):
    type: str | None = None
    label: str | None = Field(default=None, max_length=255)
    monthly_in_usd: Decimal | None = Field(default=None, ge=0)
    linked_gateways: list[str] | None = Field(default=None, max_length=50)
    owner_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("type")
    @classmethod
    def validate_update_resource_type(cls, value: str | None) -> str | None:
        return ResourceCreate.validate_resource_type(value) if value is not None else None

    @field_validator("label")
    @classmethod
    def normalize_update_resource_label(cls, value: str | None) -> str | None:
        normalized = normalize_optional_text(value)
        if value is not None and normalized is None:
            raise ValueError("Nhãn tài nguyên không được để trống")
        return normalized

    @field_validator("owner_name", "note")
    @classmethod
    def normalize_update_resource_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("linked_gateways")
    @classmethod
    def normalize_update_gateways(cls, values: list[str] | None) -> list[str] | None:
        return ResourceCreate.normalize_gateways(values) if values is not None else None


class ResourceResponse(BaseModel):
    id: int
    type: str
    label: str
    monthly_in_usd: Decimal
    linked_gateways: list[str] = Field(default_factory=list)
    owner_name: str | None = None
    note: str | None = None


class ResourceAlertResponse(BaseModel):
    level: Literal["error", "warning", "info"]
    code: str
    subject: str
    message: str


class ResourceOverviewResponse(BaseModel):
    planned_camps_this_month: int
    planned_camps_source: Literal["database", "manual"]
    kpis: dict[str, int]
    type_counts: dict[str, int]
    alerts: list[ResourceAlertResponse]
    emails: list[EmailResponse]
    ads_accounts: list[AdsAccountResponse]
    resources: list[ResourceResponse]
    selectable_account_ids: list[int]
    stores_passwords: bool = False


class ProjectTrafficSnapshotRequest(BaseModel):
    website_traffic_monthly: Decimal = Field(gt=0, le=1_000_000_000_000)
    source_name: str = Field(default="Similarweb manual check", min_length=1, max_length=160)
    source_url: str = Field(min_length=1, max_length=1000)
    observed_at: datetime
    geography: str = Field(default="GLOBAL", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    @field_validator("source_name", "geography", "actor")
    @classmethod
    def normalize_traffic_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("note")
    @classmethod
    def normalize_traffic_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("source_url")
    @classmethod
    def normalize_traffic_source_url(cls, value: str) -> str:
        return validate_source_url(value)


class ProjectTrafficSnapshotResponse(BaseModel):
    snapshot_id: int
    created: bool
    step_one: ProjectStepOneResponse
    audit_written: bool = True
    google_ads_write: bool = False


class RawCaptureCreate(BaseModel):
    source_url: str = Field(min_length=1, max_length=2000)
    page_title: str | None = Field(default=None, max_length=500)
    selected_text: str | None = None
    visible_text: str | None = None
    advertiser_name: str | None = Field(default=None, max_length=255)
    advertiser_location: str | None = Field(default=None, max_length=255)
    project_domain: str | None = Field(default=None, max_length=255)
    brand_name: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=160)
    ad_format: str | None = Field(default=None, max_length=80)
    headline: str | None = Field(default=None, max_length=500)
    description: str | None = None
    display_url: str | None = Field(default=None, max_length=1000)
    landing_domain: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=2)
    language: str | None = Field(default=None, max_length=16)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    snapshot_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_url")
    @classmethod
    def normalize_capture_source_url(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("advertiser_name", "advertiser_location", "brand_name", "category")
    @classmethod
    def strip_capture_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("project_domain", "landing_domain")
    @classmethod
    def normalize_capture_domains(cls, value: str | None) -> str | None:
        return normalize_capture_domain(value) if value is not None else None

    @field_validator("country")
    @classmethod
    def normalize_capture_country(cls, value: str | None) -> str | None:
        normalized = normalize_optional_text(value)
        if normalized is None:
            return None
        if not re.fullmatch(r"[A-Za-z]{2}", normalized):
            raise ValueError("country must be a two-letter code")
        return normalized.upper()


class RawCaptureRead(ORMModel):
    id: int
    source_url: str
    page_title: str | None
    captured_at: datetime
    status: str
    parsed_payload: dict[str, Any]


class RawCaptureReviewItem(RawCaptureRead):
    selected_text: str | None
    visible_text: str | None


class RawCaptureReviewRequest(BaseModel):
    action: Literal["ACCEPT", "REJECT"]
    reviewed_by: str = Field(default="local-user", min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=1000)
    advertiser_name: str | None = Field(default=None, max_length=255)
    advertiser_location: str | None = Field(default=None, max_length=255)
    project_domain: str | None = Field(default=None, max_length=255)
    brand_name: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=160)
    ad_format: str | None = Field(default=None, max_length=80)
    headline: str | None = Field(default=None, max_length=500)
    description: str | None = None
    display_url: str | None = Field(default=None, max_length=1000)
    landing_domain: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=2)
    language: str | None = Field(default=None, max_length=16)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    snapshot_date: date | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("reviewed_by")
    @classmethod
    def normalize_capture_reviewer(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reviewed_by cannot be blank")
        return normalized

    @field_validator("advertiser_name", "advertiser_location", "brand_name", "category")
    @classmethod
    def strip_review_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("project_domain", "landing_domain")
    @classmethod
    def normalize_review_domains(cls, value: str | None) -> str | None:
        return normalize_capture_domain(value) if value is not None else None

    @field_validator("country")
    @classmethod
    def normalize_review_country(cls, value: str | None) -> str | None:
        normalized = normalize_optional_text(value)
        if normalized is None:
            return None
        if not re.fullmatch(r"[A-Za-z]{2}", normalized):
            raise ValueError("country must be a two-letter code")
        return normalized.upper()


class AdvertiserSnapshotCandidate(BaseModel):
    """One advertiser identity reported by a bounded external result set."""

    advertiser_name: str = Field(min_length=1, max_length=255)
    external_key: str | None = Field(default=None, max_length=255)
    advertiser_location: str | None = Field(default=None, max_length=255)
    advertiser_url: str | None = Field(default=None, max_length=2000)
    reported_ad_count: int | None = Field(default=None, ge=0)

    @field_validator("advertiser_name", "external_key", "advertiser_location")
    @classmethod
    def normalize_advertiser_snapshot_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("advertiser_url")
    @classmethod
    def normalize_advertiser_snapshot_url(cls, value: str | None) -> str | None:
        return validate_source_url(value) if value is not None else None


class AdvertiserSnapshotImport(BaseModel):
    """Evidence-backed batch import; it never writes Terms or Google Ads."""

    project_domain: str = Field(min_length=3, max_length=255)
    source_url: str = Field(min_length=1, max_length=2000)
    source_name: str = Field(min_length=1, max_length=160)
    checked_at: datetime
    evidence_excerpt: str = Field(min_length=3, max_length=4000)
    advertisers: list[AdvertiserSnapshotCandidate] = Field(min_length=1, max_length=500)
    geography: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=40)
    result_set_complete: bool = False
    confidence: float = Field(default=0.7, ge=0, le=1)
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    @field_validator("project_domain")
    @classmethod
    def normalize_advertiser_snapshot_domain(cls, value: str) -> str:
        return normalize_capture_domain(value)

    @field_validator("source_url")
    @classmethod
    def normalize_advertiser_snapshot_source(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("source_name", "evidence_excerpt", "geography", "language", "actor")
    @classmethod
    def normalize_advertiser_snapshot_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class AdvertiserSnapshotImportResponse(BaseModel):
    capture_id: int
    project_id: int
    duplicate: bool = False
    advertisers_created: int
    observations_created: int
    advertisers_in_snapshot: int
    reported_ads: int
    warning_only: bool = True
    google_ads_write: bool = False


class ProjectRadarItem(BaseModel):
    project_id: int
    domain: str
    brand_name: str
    category: str | None
    distinct_advertisers: int | None
    active_advertisers_30d: int | None
    top_advertiser_share: float | None
    new_advertisers_30d: int | None
    independent_advertiser_score: int | None
    score_label: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    weight: int = 1


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ProjectAdvertiserLink(BaseModel):
    advertiser_id: int
    advertiser_name: str
    advertiser_location: str | None
    classification: AdvertiserClassification
    confidence: float = Field(default=0.0, ge=0, le=1)
    observation_count: int = Field(ge=1)
    reported_ads: int | None = Field(default=None, ge=0)
    related_project_count: int = Field(ge=1)
    observed_at: datetime | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    source_urls: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    domain_count: int = Field(default=0, ge=0)
    is_goldmine: bool = False
    is_watchlisted: bool = False
    last_expanded_at: datetime | None = None


class ProjectAdvertisersResponse(BaseModel):
    project_id: int
    domain: str
    brand_name: str
    collection_state: str
    advertisers: list[ProjectAdvertiserLink] = Field(default_factory=list)


class AdvertiserProjectLink(BaseModel):
    project_id: int
    domain: str
    brand_name: str
    category: str | None
    observation_count: int = Field(ge=1)
    reported_ads: int | None = Field(default=None, ge=0)
    observed_at: datetime | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    source_urls: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)


class AdvertiserProjectsResponse(BaseModel):
    advertiser_id: int
    advertiser_name: str
    advertiser_location: str | None
    classification: AdvertiserClassification
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_url: str | None
    collection_state: str
    projects: list[AdvertiserProjectLink] = Field(default_factory=list)


class ProjectNetworkAdvertiser(ProjectAdvertiserLink):
    external_key: str | None = None
    projects: list[AdvertiserProjectLink] = Field(default_factory=list)
    expansion_domains: list[str] = Field(default_factory=list)
    expansion_project_ids: dict[str, int] = Field(default_factory=dict)
    expansion_state: Literal["AVAILABLE", "NOT_COLLECTED"] = "NOT_COLLECTED"
    expansion_checked_at: datetime | None = None


class ProjectNetworkResponse(BaseModel):
    project_id: int
    domain: str
    brand_name: str
    collection_state: str
    advertisers: list[ProjectNetworkAdvertiser] = Field(default_factory=list)


class AdvertiserExpandRequest(BaseModel):
    advertiser_ids: list[int] = Field(min_length=1, max_length=5)
    force_refresh: bool = False

    @field_validator("advertiser_ids")
    @classmethod
    def unique_advertiser_ids(cls, values: list[int]) -> list[int]:
        unique = list(dict.fromkeys(values))
        if len(unique) != len(values) or any(value <= 0 for value in values):
            raise ValueError("advertiser_ids phải là ID dương, không trùng")
        return unique


class AdvertiserExpansionItem(BaseModel):
    id: int
    external_key: str
    name: str
    domain_count: int = Field(ge=0)
    is_goldmine: bool = False
    reported_ads: int = Field(default=0, ge=0)
    domains: list[str] = Field(default_factory=list)


class AdvertiserExpansionResponse(BaseModel):
    status: str
    detail: str
    domains: list[str] = Field(default_factory=list)
    new_domains: list[str] = Field(default_factory=list)
    advertisers: list[AdvertiserExpansionItem] = Field(default_factory=list)
    cache_hit: bool = False
    checked_at: datetime
    source_urls: list[str] = Field(default_factory=list)
    quota: dict[str, Any]


class AdvertiserWatchRequest(BaseModel):
    watch: bool = True


class AdvertiserProviderStatusResponse(BaseModel):
    status: str
    provider: str
    api_key_present: bool
    setup_command: str
    secret_exposed: bool = False
    quota: dict[str, Any]


class DiscoveredDomainQueueRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    advertiser_id: int = Field(gt=0)

    @field_validator("domain")
    @classmethod
    def normalize_discovered_domain(cls, value: str) -> str:
        return normalize_capture_domain(value)


class EconomicsEvaluateRequest(BaseModel):
    price: Decimal = Field(ge=0)
    commission_type: CommissionType
    commission_rate: Decimal | None = Field(default=None, ge=0, le=1)
    commission_flat: Decimal | None = Field(default=None, ge=0)
    recurring_months: int | None = Field(default=None, ge=1, le=120)
    forecast_horizon_months: int = Field(default=24, ge=1, le=120)
    clicks_per_sale: Decimal | None = Field(default=None, gt=0)
    outbound_click_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    merchant_conversion_rate: Decimal = Field(default=Decimal("0.03"), ge=0, le=1)
    approval_rate: Decimal = Field(default=Decimal("0.85"), ge=0, le=1)
    refund_rate: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    monthly_churn_rate: Decimal = Field(default=Decimal("0.08"), ge=0, le=1)
    target_margin: Decimal = Field(default=Decimal("0.30"), ge=0, le=1)
    confidence_discount: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)


class EconomicsEvaluateResponse(BaseModel):
    commission_per_period: Decimal
    expected_active_periods: Decimal
    expected_commission_ltv: Decimal
    sale_probability_per_ad_click: Decimal
    effective_clicks_per_sale: Decimal | None
    break_even_cpc: Decimal
    safe_cpc: Decimal
    assumptions: dict[str, str]


class EvidenceInput(BaseModel):
    decision: PermissionStatus = PermissionStatus.NOT_CHECKED
    checked_at: datetime
    expires_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class ComplianceEvaluateRequest(BaseModel):
    program_id: int = Field(gt=0)
    wants_brand_keywords: bool = False
    wants_direct_link: bool = False
    max_evidence_age_days: int = Field(default=90, ge=1, le=365)


class ComplianceEvaluateResponse(BaseModel):
    allowed: bool
    status: str
    reasons: list[str]
    project_included: bool = True
    warning_only: bool = True


class DashboardSummary(BaseModel):
    projects: int
    advertisers: int
    observations: int
    programs: int
    programs_explicitly_allowed: int
    programs_blocked_pending_evidence: int
    programs_terms_ok: int
    programs_with_terms_warnings: int
    campaigns: int
    active_campaigns: int
    captures_needing_review: int
    last_capture_at: datetime | None


class ProgramCreate(BaseModel):
    merchant_name: str = Field(min_length=1, max_length=200)
    website_domain: str = Field(min_length=3, max_length=255)
    merchant_country: str | None = Field(default=None, min_length=2, max_length=2)
    program_name: str = Field(min_length=1, max_length=200)
    network_name: str | None = Field(default=None, max_length=160)
    signup_url: str | None = Field(default=None, max_length=1000)
    dashboard_url: str | None = Field(default=None, max_length=1000)
    status: ProgramStatus = ProgramStatus.DISCOVERED
    paid_search_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    brand_keyword_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    non_brand_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    direct_link_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    trademark_in_ad_copy_permission: PermissionStatus = PermissionStatus.NOT_CHECKED
    notes: str | None = None

    @field_validator("website_domain")
    @classmethod
    def normalize_website_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("merchant_country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("signup_url", "dashboard_url")
    @classmethod
    def validate_program_url(cls, value: str | None) -> str | None:
        return validate_source_url(value) if value is not None else None


class ProgramUpdate(BaseModel):
    status: ProgramStatus | None = None
    paid_search_permission: PermissionStatus | None = None
    brand_keyword_permission: PermissionStatus | None = None
    non_brand_permission: PermissionStatus | None = None
    direct_link_permission: PermissionStatus | None = None
    trademark_in_ad_copy_permission: PermissionStatus | None = None
    signup_url: str | None = Field(default=None, max_length=1000)
    dashboard_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = None

    @field_validator("signup_url", "dashboard_url")
    @classmethod
    def validate_program_url(cls, value: str | None) -> str | None:
        return validate_source_url(value) if value is not None else None


class ProgramRead(BaseModel):
    id: int
    merchant_name: str
    website_domain: str
    program_name: str
    network_name: str | None
    signup_url: str | None
    signup_source_authority: SourceAuthority | None
    status: ProgramStatus
    paid_search_permission: PermissionStatus
    brand_keyword_permission: PermissionStatus
    non_brand_permission: PermissionStatus
    direct_link_permission: PermissionStatus
    trademark_in_ad_copy_permission: PermissionStatus
    last_terms_checked_at: datetime | None
    last_research_attempted_at: datetime | None
    research_next_due_at: datetime | None
    research_status: ResearchStatus | None
    research_is_fresh: bool
    permission_evidence_found: bool
    evidence_count: int
    evidence_proposal_count: int
    commission_fact_count: int
    commission_state: str
    gate_status: str
    evidence_is_stale: bool


class TermsEvidenceCreate(BaseModel):
    source_url: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="TERMS_PAGE", min_length=1, max_length=80)
    excerpt: str = Field(min_length=3)
    summary_vi: str | None = None
    quote_vi: str | None = None
    checked_at: datetime
    expires_at: datetime | None = None
    reviewer: str = Field(default="Tran", min_length=1, max_length=120)
    confidence: float = Field(default=0.0, ge=0, le=1)
    decision: PermissionStatus = PermissionStatus.NOT_CHECKED
    scope: str = Field(
        default="PAID_SEARCH",
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("scope", "applies_to"),
    )
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN
    notes: str | None = None

    @field_validator("scope")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in PERMISSION_SCOPES:
            raise ValueError(f"scope must be one of {sorted(PERMISSION_SCOPES)}")
        return value

    @field_validator("source_url")
    @classmethod
    def normalize_source_url(cls, value: str) -> str:
        return validate_source_url(value)


class TermsEvidenceRead(ORMModel):
    id: int
    program_id: int
    source_url: str
    source_type: str
    excerpt: str
    summary_vi: str | None = None
    quote_vi: str | None = None
    checked_at: datetime
    expires_at: datetime | None
    reviewer: str
    confidence: float
    decision: PermissionStatus
    scope: str
    applies_to: str
    review_status: EvidenceReviewStatus
    source_authority: SourceAuthority
    collected_by: str
    reviewed_at: datetime | None
    reviewed_by: str | None
    notes: str | None


class TermsEvidenceCreateResponse(BaseModel):
    evidence: TermsEvidenceRead
    duplicate: bool = False
    updated: bool = False
    proposal_state: EvidenceReviewStatus
    program_gate_status: str


class EvidenceReviewRequest(BaseModel):
    action: str
    reviewed_by: str = Field(default="Tran", min_length=1, max_length=120)

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"ACCEPT", "REJECT"}:
            raise ValueError("action must be ACCEPT or REJECT")
        return value


class EvidenceReviewResponse(BaseModel):
    evidence: TermsEvidenceRead
    resolved_permission: PermissionStatus
    program_gate_status: str


class CommissionFactRead(ORMModel):
    id: int
    program_id: int
    scope: str
    source_url: str
    source_authority: SourceAuthority
    excerpt: str
    summary_vi: str | None = None
    quote_vi: str | None = None
    checked_at: datetime
    confidence: float
    commission_type: CommissionType
    commission_rate: Decimal | None
    commission_flat: Decimal | None = None
    recurring_months: int | None = None
    rate_is_maximum: bool
    applies_to: str
    review_status: EvidenceReviewStatus
    collected_by: str
    notes: str | None


class CommissionFactReviewResponse(BaseModel):
    fact: CommissionFactRead
    commission_state: str
    permissions_changed: bool = False


class PermissionProposal(BaseModel):
    scope: str
    decision: PermissionStatus = PermissionStatus.NOT_CHECKED
    confidence: float = Field(default=0.0, ge=0, le=1)
    reason: str
    source_authority: SourceAuthority = SourceAuthority.UNKNOWN


class DomainResearchRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255)

    @field_validator("domain")
    @classmethod
    def normalize_research_domain(cls, value: str) -> str:
        normalized = normalize_domain(value)
        if "." not in normalized:
            raise ValueError("domain must be a public hostname")
        return normalized


class DomainResearchResponse(BaseModel):
    run_id: int
    domain: str
    program_id: int | None
    status: ResearchStatus
    checked_at: datetime
    discovery_confidence: float
    source_urls: list[str]
    source_authorities: dict[str, SourceAuthority] = Field(default_factory=dict)
    permission_proposals: list[PermissionProposal]
    terms_evidence: list[TermsEvidenceRead] = Field(default_factory=list)
    imported_terms_evidence: int = 0
    duplicate_terms_evidence: int = 0
    refreshed_terms_evidence: int = 0
    commission_state: str
    commission_facts: list[CommissionFactRead]
    imported_commission_facts: int
    duplicate_commission_facts: int
    refreshed_commission_facts: int = 0
    gate_status: str
    summary: str
    duplicate_run: bool = False
    collection_errors: list[str] = Field(default_factory=list)
    source_change_status: str = "UNAVAILABLE"
    source_changes: list[dict[str, str]] = Field(default_factory=list)


class TermsResearchAttemptRead(BaseModel):
    audit_id: int
    run_id: int
    status: ResearchStatus
    source_checked_at: datetime
    attempted_at: datetime
    duplicate_run: bool = False
    source_urls: list[str] = Field(default_factory=list)
    priority_source_urls: list[str] = Field(default_factory=list)
    source_authorities: dict[str, SourceAuthority] = Field(default_factory=dict)
    collection_errors: list[str] = Field(default_factory=list)
    source_change_status: str = "UNAVAILABLE"
    source_changes: list[dict[str, str]] = Field(default_factory=list)
    imported_terms_evidence: int = 0
    duplicate_terms_evidence: int = 0
    refreshed_terms_evidence: int = 0
    imported_commission_facts: int = 0
    duplicate_commission_facts: int = 0
    refreshed_commission_facts: int = 0
    permissions_changed: bool = False
    actor: str
    summary: str


class BackupInfo(BaseModel):
    name: str
    created_at: datetime
    size_bytes: int
    sha256: str
    database_file: str
    version: str = "unknown"
    alembic_versions: list[str] = Field(default_factory=list)
    database_status: str = "UNKNOWN"


class BackupCreateResponse(BaseModel):
    backup: BackupInfo
    message: str


class CommissionImportError(BaseModel):
    row: int
    message: str


class CommissionImportPreview(BaseModel):
    source: str
    rows_read: int
    valid_rows: int
    duplicates_existing: int
    updates_existing: int
    duplicates_in_file: int
    conflict_count: int = 0
    error_count: int
    errors: list[CommissionImportError]
    totals_by_state: dict[str, str]
    totals_by_currency: dict[str, str]
    attributable_rows: int
    unattributed_rows: int


class CommissionImportCommitResponse(CommissionImportPreview):
    rows_written: int


class FinanceCurrencySummary(BaseModel):
    currency: str
    pending_nominal: Decimal
    forecast_revenue: Decimal
    recognized_revenue: Decimal
    cash_received: Decimal
    rejected_or_reversed: Decimal
    transaction_count: int
    unattributed_count: int


class FinanceSummaryResponse(BaseModel):
    currencies: list[FinanceCurrencySummary]
    total_transactions: int
    total_unattributed: int


class TrueProfitExpectedPayment(BaseModel):
    expected_on: date
    amount_usd: Decimal


class TrueProfitProjectRead(BaseModel):
    project_id: int
    project_name: str
    domain: str
    spend_usd: Decimal
    variable_cost_usd: Decimal
    total_cost_usd: Decimal
    on_web_usd: Decimal
    withdrawn_usd: Decimal
    real_profit_usd: Decimal
    expected_payments: list[TrueProfitExpectedPayment] = Field(default_factory=list)
    overdue_payments: list[TrueProfitExpectedPayment] = Field(default_factory=list)


class TrueProfitSummaryResponse(BaseModel):
    currency: str = "USD"
    total_spend_usd: Decimal
    total_variable_cost_usd: Decimal
    total_cost_usd: Decimal
    total_on_web_usd: Decimal
    total_withdrawn_usd: Decimal
    real_profit_usd: Decimal
    collection_rate: float | None = None
    projects_paid: int
    projects_with_earnings: int
    projects: list[TrueProfitProjectRead] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    excluded_non_usd_rows: int = 0


class CommissionRead(BaseModel):
    id: int
    external_id: str
    amount: Decimal
    currency: str
    state: CommissionState
    occurred_at: datetime
    source: str
    quality: DataQuality
    attributed: bool
    click_reference: str | None = None
    normalized_amount: Decimal | None = None
    normalized_currency: str | None = None
    reconciliation_status: ReconciliationStatus | None = None


def _currency_code(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("currency must be a three-letter code")
    return value


class FinanceSettingsRead(ORMModel):
    base_currency: str
    max_rate_age_days: int


class FinanceSettingsUpdate(BaseModel):
    base_currency: str = Field(default="VND", min_length=3, max_length=3)
    max_rate_age_days: int = Field(default=7, ge=0, le=31)
    actor: str = Field(default="Tran", min_length=1, max_length=120)

    @field_validator("base_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return _currency_code(value)


class FxRateCreate(BaseModel):
    rate_date: date
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)
    source_name: str = Field(min_length=1, max_length=120)
    source_url: str = Field(min_length=8, max_length=1000)
    checked_at: datetime
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    actor: str = Field(default="Tran", min_length=1, max_length=120)

    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currencies(cls, value: str) -> str:
        return _currency_code(value)

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_source_url(value)


class FxRateRead(ORMModel):
    id: int
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal
    source_name: str
    source_url: str
    checked_at: datetime
    confidence: Decimal
    review_status: FxRateReviewStatus
    reviewed_at: datetime | None
    reviewed_by: str | None


class FxRateProposalResponse(BaseModel):
    rate: FxRateRead
    duplicate: bool


class FxRateReviewRequest(BaseModel):
    action: str = Field(pattern="^(ACCEPT|REJECT)$")
    reviewed_by: str = Field(default="Tran", min_length=1, max_length=120)


class CurrencyNormalizationResult(BaseModel):
    settings: FinanceSettingsRead
    normalized_rows: int
    missing_rows: int
    missing_pairs: dict[str, int]


class FxRateReviewResponse(BaseModel):
    rate: FxRateRead
    normalization: CurrencyNormalizationResult


class CurrencyNormalizationSummary(BaseModel):
    base_currency: str
    max_rate_age_days: int
    normalized_spend: Decimal
    pending_nominal: Decimal
    forecast_revenue: Decimal
    recognized_revenue: Decimal
    cash_received: Decimal
    rejected_or_reversed: Decimal
    actual_net_cash: Decimal
    spend_rows: int
    spend_normalized: int
    spend_missing: int
    commission_rows: int
    commission_normalized: int
    commission_missing: int
    missing_pairs: dict[str, int]


class ReconciliationItemRead(ORMModel):
    id: int
    status: ReconciliationStatus
    entity_type: str
    entity_id: str | None
    reason: str
    payload_json: dict[str, Any]
    resolved_at: datetime | None
    resolved_by: str | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime


class ReconciliationSummaryResponse(BaseModel):
    status_counts: dict[str, int]
    open_issue_counts: dict[str, int]
    open_items: int
    items: list[ReconciliationItemRead]


class ReconciliationResolveRequest(BaseModel):
    resolved_by: str = Field(default="Tran", min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=1000)


class CampaignImportError(BaseModel):
    row: int
    message: str


class CampaignImportPreview(BaseModel):
    source: str
    rows_read: int
    valid_rows: int
    new_rows: int
    update_rows: int
    duplicates_existing: int
    duplicates_in_file: int
    error_count: int
    errors: list[CampaignImportError]
    mapped_rows: int
    unmapped_rows: int
    auto_mapped_rows: int = 0
    totals_by_currency: dict[str, str]
    total_impressions: int
    total_clicks: int
    total_conversions: Decimal
    metric_date_from: date | None = None
    metric_date_to: date | None = None


class CampaignImportCommitResponse(CampaignImportPreview):
    rows_written: int


class CampaignExposureRead(BaseModel):
    campaign_id: int
    account_external_id: str
    account_name: str
    campaign_external_id: str
    campaign_name: str
    campaign_status: str
    channel_type: str
    program_id: int | None
    program_name: str | None
    merchant_domain: str | None
    terms_warning_status: TermsWarningStatus
    warning_level: str
    project_included: bool
    risk_acknowledged: bool
    risk_acknowledged_at: datetime | None
    risk_acknowledged_by: str | None
    currency: str
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Decimal
    average_cpc: Decimal | None


class ExposureCurrencySummary(BaseModel):
    currency: str
    total_spend: Decimal
    spend_at_risk: Decimal
    pending_commission_at_risk: Decimal
    recognized_revenue: Decimal
    cash_received: Decimal
    actual_net_cash: Decimal


class ExposureSummaryResponse(BaseModel):
    currencies: list[ExposureCurrencySummary]
    campaign_count: int
    active_campaign_count: int
    warning_campaign_count: int
    acknowledged_warning_count: int
    campaigns: list[CampaignExposureRead]


class RiskAcknowledgementRequest(BaseModel):
    actor: str = Field(default="Tran", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class CampaignProgramMapRequest(BaseModel):
    program_id: int | None = Field(default=None, gt=0)
    actor: str = Field(default="Tran", min_length=1, max_length=120)


class AutomationJobRead(ORMModel):
    id: int
    job_type: AutomationJobType
    status: AutomationJobStatus
    dedupe_key: str
    priority: int
    payload_json: dict[str, Any]
    result_json: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    worker_id: str | None
    completed_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class AutomationQueueSummary(BaseModel):
    counts_by_status: dict[str, int]
    counts_by_type: dict[str, int]
    total: int
    due: int
    running: int
    retry_wait: int
    dead_letter: int
    oldest_due_at: datetime | None
    next_due_at: datetime | None


class AutomationJobRetryRequest(BaseModel):
    actor: str = Field(default="Tran", min_length=1, max_length=120)
    note: str = Field(default="Manual retry", min_length=1, max_length=500)
