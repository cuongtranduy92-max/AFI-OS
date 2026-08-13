from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from afi_os.db import Base
from afi_os.enums import (
    AdsAccountHealth,
    AdsAccountState,
    AdsAccountType,
    AdvertiserClassification,
    AuditAction,
    AutomationJobStatus,
    AutomationJobType,
    CampPlanStatus,
    CaptureStatus,
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
    SyncStatus,
    WatchStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    website_domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(Text)

    programs: Mapped[list[Program]] = relationship(back_populates="merchant")


class AffiliateNetwork(TimestampMixin, Base):
    __tablename__ = "affiliate_networks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    platform_type: Mapped[str | None] = mapped_column(String(80))
    base_url: Mapped[str | None] = mapped_column(String(500))
    supports_api: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_subid: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    programs: Mapped[list[Program]] = relationship(back_populates="network")
    payouts: Mapped[list[Payout]] = relationship(back_populates="network")


class Program(TimestampMixin, Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    network_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliate_networks.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    signup_url: Mapped[str | None] = mapped_column(String(1000))
    dashboard_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ProgramStatus] = mapped_column(
        Enum(ProgramStatus, native_enum=False), default=ProgramStatus.DISCOVERED
    )
    paid_search_permission: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    brand_keyword_permission: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    non_brand_permission: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    direct_link_permission: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    trademark_in_ad_copy_permission: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    required_negative_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_geos: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocked_geos: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_terms_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_version: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    merchant: Mapped[Merchant] = relationship(back_populates="programs")
    network: Mapped[AffiliateNetwork | None] = relationship(back_populates="programs")
    offers: Mapped[list[Offer]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    terms_evidence: Mapped[list[TermsEvidence]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    commission_facts: Mapped[list[CommissionFact]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    terms_research_runs: Mapped[list[TermsResearchRun]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="program")
    campaign_links: Mapped[list[CampaignProgramLink]] = relationship(back_populates="program")

    __table_args__ = (UniqueConstraint("merchant_id", "name", name="uq_program_merchant_name"),)


class Offer(TimestampMixin, Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    commission_type: Mapped[CommissionType] = mapped_column(
        Enum(CommissionType, native_enum=False), default=CommissionType.ONE_TIME
    )
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    commission_flat: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    recurring_months: Mapped[int | None] = mapped_column(Integer)
    cookie_days: Mapped[int | None] = mapped_column(Integer)
    approval_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    refund_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="offers")

    __table_args__ = (
        UniqueConstraint("program_id", "external_id", name="uq_offer_program_external"),
    )


class TermsEvidence(TimestampMixin, Base):
    __tablename__ = "terms_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"))
    source_url: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(80), default="TERMS_PAGE")
    excerpt: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64), unique=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer: Mapped[str] = mapped_column(String(120), default="system")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    decision: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus, native_enum=False), default=PermissionStatus.NOT_CHECKED
    )
    scope: Mapped[str] = mapped_column(String(80), default="PAID_SEARCH")
    # Kept for 0.2.0 API/database compatibility. New code treats ``scope`` as canonical.
    applies_to: Mapped[str] = mapped_column(String(80), default="PAID_SEARCH")
    review_status: Mapped[EvidenceReviewStatus] = mapped_column(
        Enum(EvidenceReviewStatus, native_enum=False), default=EvidenceReviewStatus.PROPOSED
    )
    source_authority: Mapped[SourceAuthority] = mapped_column(
        Enum(SourceAuthority, native_enum=False), default=SourceAuthority.UNKNOWN
    )
    collected_by: Mapped[str] = mapped_column(String(80), default="MANUAL")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="terms_evidence")

    __table_args__ = (Index("ix_terms_program_checked", "program_id", "checked_at"),)


class CommissionFact(TimestampMixin, Base):
    """Source-backed commission claim, deliberately separate from PPC permissions."""

    __tablename__ = "commission_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(80), default="COMMISSION")
    source_url: Mapped[str] = mapped_column(String(1000))
    source_authority: Mapped[SourceAuthority] = mapped_column(
        Enum(SourceAuthority, native_enum=False), default=SourceAuthority.UNKNOWN
    )
    excerpt: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    commission_type: Mapped[CommissionType] = mapped_column(
        Enum(CommissionType, native_enum=False)
    )
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rate_is_maximum: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_to: Mapped[str] = mapped_column(String(120), default="UNKNOWN")
    review_status: Mapped[EvidenceReviewStatus] = mapped_column(
        Enum(EvidenceReviewStatus, native_enum=False), default=EvidenceReviewStatus.PROPOSED
    )
    collected_by: Mapped[str] = mapped_column(String(80), default="AUTOMATED_FIXTURE")
    evidence_hash: Mapped[str] = mapped_column(String(64), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="commission_facts")

    __table_args__ = (
        Index("ix_commission_fact_program_checked", "program_id", "checked_at"),
    )


class TermsResearchRun(TimestampMixin, Base):
    __tablename__ = "terms_research_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), index=True
    )
    domain: Mapped[str] = mapped_column(String(255), index=True)
    fixture_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[ResearchStatus] = mapped_column(Enum(ResearchStatus, native_enum=False))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    discovery_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    permission_proposals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    imported_fact_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    run_hash: Mapped[str] = mapped_column(String(64), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program | None] = relationship(back_populates="terms_research_runs")


class Advertiser(TimestampMixin, Base):
    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    verified_name: Mapped[str] = mapped_column(String(255), index=True)
    verified_location: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[AdvertiserClassification] = mapped_column(
        Enum(AdvertiserClassification, native_enum=False),
        default=AdvertiserClassification.UNKNOWN,
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    observations: Mapped[list[AdObservation]] = relationship(back_populates="advertiser")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    brand_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str | None] = mapped_column(String(160), index=True)
    affiliate_program_found: Mapped[bool] = mapped_column(Boolean, default=False)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"))
    watch_status: Mapped[WatchStatus] = mapped_column(
        Enum(WatchStatus, native_enum=False), default=WatchStatus.NEW
    )
    stage: Mapped[ProjectStage] = mapped_column(
        Enum(ProjectStage, native_enum=False), default=ProjectStage.INTAKE
    )
    registration_status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, native_enum=False),
        default=RegistrationStatus.NOT_STARTED,
    )
    owner: Mapped[str | None] = mapped_column(String(120))
    next_action: Mapped[str | None] = mapped_column(String(500))
    next_action_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program | None] = relationship(back_populates="projects")
    observations: Mapped[list[AdObservation]] = relationship(back_populates="project")
    campaigns: Mapped[list[Campaign]] = relationship(back_populates="project")
    metric_snapshots: Mapped[list[MetricSnapshot]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    camp_plan: Mapped[CampPlan | None] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    resource_ads_account: Mapped[AdsAccount | None] = relationship(
        back_populates="current_project",
        foreign_keys="AdsAccount.current_project_id",
        uselist=False,
    )


class CampPlan(TimestampMixin, Base):
    """Editable Step 2 campaign content with its latest deterministic lint report."""

    __tablename__ = "camp_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    ads_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("ads_accounts.id", ondelete="SET NULL"), unique=True, index=True
    )
    ref_url: Mapped[str] = mapped_column(String(1000))
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    linter_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[CampPlanStatus] = mapped_column(
        Enum(CampPlanStatus, native_enum=False), default=CampPlanStatus.DRAFT
    )

    project: Mapped[Project] = relationship(back_populates="camp_plan")
    ads_account: Mapped[AdsAccount | None] = relationship(
        back_populates="camp_plan",
        foreign_keys=[ads_account_id],
    )


class MetricSnapshot(TimestampMixin, Base):
    """Versioned project metric with explicit provenance and data quality."""

    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    metric_key: Mapped[str] = mapped_column(String(120), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.UNKNOWN
    )
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    geography: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(40))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    method_version: Mapped[str] = mapped_column(String(80), default="manual-v1")
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="metric_snapshots")

    __table_args__ = (
        Index(
            "ix_metric_snapshot_project_key_observed",
            "project_id",
            "metric_key",
            "observed_at",
        ),
    )


class AutomationJob(TimestampMixin, Base):
    """Durable, lease-based work item for safe background automation."""

    __tablename__ = "automation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[AutomationJobType] = mapped_column(
        Enum(AutomationJobType, native_enum=False), index=True
    )
    status: Mapped[AutomationJobStatus] = mapped_column(
        Enum(AutomationJobStatus, native_enum=False),
        default=AutomationJobStatus.PENDING,
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(64), index=True)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(120), default="system")

    __table_args__ = (
        Index(
            "ix_automation_job_due",
            "status",
            "run_after",
            "priority",
            "created_at",
        ),
        Index("ix_automation_job_lease", "status", "lease_expires_at"),
    )


class RawCapture(TimestampMixin, Base):
    __tablename__ = "raw_captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(2000))
    page_title: Mapped[str | None] = mapped_column(String(500))
    selected_text: Mapped[str | None] = mapped_column(Text)
    visible_text: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[CaptureStatus] = mapped_column(
        Enum(CaptureStatus, native_enum=False), default=CaptureStatus.RAW
    )
    parser_version: Mapped[str] = mapped_column(String(40), default="manual-v1")
    parsed_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    capture_hash: Mapped[str] = mapped_column(String(64), unique=True)


class AdObservation(TimestampMixin, Base):
    __tablename__ = "ad_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    advertiser_id: Mapped[int] = mapped_column(
        ForeignKey("advertisers.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    raw_capture_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_captures.id", ondelete="SET NULL")
    )
    source_url: Mapped[str] = mapped_column(String(2000))
    ad_format: Mapped[str | None] = mapped_column(String(80))
    headline: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    display_url: Mapped[str | None] = mapped_column(String(1000))
    landing_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    language: Mapped[str | None] = mapped_column(String(16))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    advertiser: Mapped[Advertiser] = relationship(back_populates="observations")
    project: Mapped[Project] = relationship(back_populates="observations")
    raw_capture: Mapped[RawCapture | None] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "advertiser_id",
            "project_id",
            "content_hash",
            "snapshot_date",
            name="uq_observation_snapshot",
        ),
        Index("ix_observation_project_date", "project_id", "snapshot_date"),
    )


class Email(TimestampMixin, Base):
    """Email nurture metadata only; credentials belong in a password manager."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    source: Mapped[EmailSource] = mapped_column(
        Enum(EmailSource, native_enum=False), default=EmailSource.SELF
    )
    declared_done: Mapped[bool] = mapped_column(Boolean, default=False)
    device_changes: Mapped[int] = mapped_column(Integer, default=0)
    usage_history: Mapped[list[str]] = mapped_column(JSON, default=list)
    status_override: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)

    ads_accounts: Mapped[list[AdsAccount]] = relationship(back_populates="email")
    nurture_logs: Mapped[list[NurtureLog]] = relationship(
        back_populates="email", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("device_changes >= 0", name="ck_emails_device_changes_nonnegative"),
        CheckConstraint(
            "status_override IS NULL OR status_override = 'LOCKED'",
            name="ck_emails_status_override",
        ),
    )


class AdsAccount(TimestampMixin, Base):
    __tablename__ = "ads_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(80), default="UNKNOWN")
    time_zone: Mapped[str | None] = mapped_column(String(80))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_id: Mapped[int | None] = mapped_column(
        ForeignKey("emails.id", ondelete="SET NULL"), index=True
    )
    account_type: Mapped[AdsAccountType | None] = mapped_column(
        "type", Enum(AdsAccountType, native_enum=False)
    )
    rent_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    spend_fee_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    resource_state: Mapped[AdsAccountState] = mapped_column(
        "resource_state",
        Enum(AdsAccountState, native_enum=False),
        default=AdsAccountState.CHAY,
    )
    current_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), unique=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255))
    health: Mapped[AdsAccountHealth] = mapped_column(
        Enum(AdsAccountHealth, native_enum=False), default=AdsAccountHealth.OK
    )
    note: Mapped[str | None] = mapped_column(Text)

    campaigns: Mapped[list[Campaign]] = relationship(back_populates="ads_account")
    email: Mapped[Email | None] = relationship(back_populates="ads_accounts")
    current_project: Mapped[Project | None] = relationship(
        back_populates="resource_ads_account",
        foreign_keys=[current_project_id],
    )
    camp_plan: Mapped[CampPlan | None] = relationship(
        back_populates="ads_account",
        foreign_keys="CampPlan.ads_account_id",
        uselist=False,
    )
    project_history: Mapped[list[AdsAccountProjectHistory]] = relationship(
        back_populates="ads_account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("rent_cost >= 0", name="ck_ads_accounts_rent_cost_nonnegative"),
        CheckConstraint(
            "spend_fee_pct >= 0 AND spend_fee_pct <= 100",
            name="ck_ads_accounts_spend_fee_pct_range",
        ),
    )


class AdsAccountProjectHistory(TimestampMixin, Base):
    __tablename__ = "ads_account_project_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    ads_account_id: Mapped[int] = mapped_column(
        ForeignKey("ads_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ads_account: Mapped[AdsAccount] = relationship(back_populates="project_history")
    project: Mapped[Project] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "ads_account_id", "project_id", name="uq_ads_account_project_history"
        ),
    )


class Resource(TimestampMixin, Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(255))
    monthly_in_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    linked_gateways: Mapped[list[str]] = mapped_column(JSON, default=list)
    owner_name: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("monthly_in_usd >= 0", name="ck_resources_monthly_nonnegative"),
        CheckConstraint(
            "type IN ('paypal','payoneer','wise','card','crypto_wallet','exchange',"
            "'sim','device','website','social')",
            name="ck_resources_type",
        ),
    )


class NurtureLog(TimestampMixin, Base):
    __tablename__ = "nurture_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    tasks_done: Mapped[list[str]] = mapped_column(JSON, default=list)

    email: Mapped[Email] = relationship(back_populates="nurture_logs")

    __table_args__ = (
        UniqueConstraint("email_id", "date", name="uq_nurture_log_email_date"),
    )


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    ads_account_id: Mapped[int] = mapped_column(
        ForeignKey("ads_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(80), default="PAUSED")
    channel_type: Mapped[str] = mapped_column(String(80), default="SEARCH")
    daily_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    launch_gate_status: Mapped[str] = mapped_column(String(80), default="DRAFT")

    ads_account: Mapped[AdsAccount] = relationship(back_populates="campaigns")
    project: Mapped[Project | None] = relationship(back_populates="campaigns")
    clicks: Mapped[list[Click]] = relationship(back_populates="campaign")
    spends: Mapped[list[Spend]] = relationship(back_populates="campaign")
    program_link: Mapped[CampaignProgramLink | None] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", uselist=False
    )
    daily_stats: Mapped[list[CampaignDailyStat]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("ads_account_id", "external_id", name="uq_campaign_account_external"),
    )


class CampaignProgramLink(TimestampMixin, Base):
    """Operator-visible campaign mapping; terms remain a warning, never an exclusion."""

    __tablename__ = "campaign_program_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, index=True
    )
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), index=True
    )
    link_source: Mapped[str] = mapped_column(String(80), default="MANUAL")
    risk_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_acknowledged_by: Mapped[str | None] = mapped_column(String(120))
    risk_note: Mapped[str | None] = mapped_column(Text)

    campaign: Mapped[Campaign] = relationship(back_populates="program_link")
    program: Mapped[Program | None] = relationship(back_populates="campaign_links")


class CampaignDailyStat(TimestampMixin, Base):
    __tablename__ = "campaign_daily_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(80), default="GOOGLE_ADS_CSV")
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.OBSERVED
    )

    campaign: Mapped[Campaign] = relationship(back_populates="daily_stats")

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "metric_date", "source", name="uq_campaign_daily_stats_source"
        ),
    )


class Click(TimestampMixin, Base):
    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)
    gclid: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    gbraid: Mapped[str | None] = mapped_column(String(255), index=True)
    wbraid: Mapped[str | None] = mapped_column(String(255), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    ad_group_external_id: Mapped[str | None] = mapped_column(String(64))
    criterion_id: Mapped[str | None] = mapped_column(String(64))
    keyword: Mapped[str | None] = mapped_column(String(500))
    match_type: Mapped[str | None] = mapped_column(String(40))
    device: Mapped[str | None] = mapped_column(String(40))
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    affiliate_subid: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(80), default="GOOGLE_ADS")
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.OBSERVED
    )

    campaign: Mapped[Campaign | None] = relationship(back_populates="clicks")
    conversions: Mapped[list[Conversion]] = relationship(back_populates="click")


class Conversion(TimestampMixin, Base):
    __tablename__ = "conversions"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    click_id: Mapped[int | None] = mapped_column(ForeignKey("clicks.id", ondelete="SET NULL"))
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"))
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    order_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(80), default="CONVERTED_PENDING")
    source: Mapped[str] = mapped_column(String(80))
    raw_hash: Mapped[str] = mapped_column(String(64), unique=True)
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.UNKNOWN
    )

    click: Mapped[Click | None] = relationship(back_populates="conversions")
    commissions: Mapped[list[Commission]] = relationship(
        back_populates="conversion", cascade="all, delete-orphan"
    )


class Commission(TimestampMixin, Base):
    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    conversion_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversions.id", ondelete="SET NULL")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    normalized_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    normalized_currency: Mapped[str | None] = mapped_column(String(3))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    fx_source: Mapped[str | None] = mapped_column(String(120))
    fx_rate_id: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[CommissionState] = mapped_column(
        Enum(CommissionState, native_enum=False), default=CommissionState.PENDING
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(80))
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.OBSERVED
    )

    conversion: Mapped[Conversion | None] = relationship(back_populates="commissions")


class Spend(TimestampMixin, Base):
    __tablename__ = "spend"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    spend_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    normalized_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    normalized_currency: Mapped[str | None] = mapped_column(String(3))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    fx_source: Mapped[str | None] = mapped_column(String(120))
    fx_rate_id: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80), default="GOOGLE_ADS")
    quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, native_enum=False), default=DataQuality.OBSERVED
    )

    campaign: Mapped[Campaign] = relationship(back_populates="spends")

    __table_args__ = (
        UniqueConstraint("campaign_id", "spend_date", "source", name="uq_spend_campaign_date"),
    )


class FinanceSettings(TimestampMixin, Base):
    __tablename__ = "finance_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    base_currency: Mapped[str] = mapped_column(String(3), default="VND")
    max_rate_age_days: Mapped[int] = mapped_column(Integer, default=7)


class FxRate(TimestampMixin, Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, index=True)
    from_currency: Mapped[str] = mapped_column(String(3), index=True)
    to_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 12))
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(1000))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    review_status: Mapped[FxRateReviewStatus] = mapped_column(
        Enum(FxRateReviewStatus, native_enum=False), default=FxRateReviewStatus.PROPOSED
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    __table_args__ = (
        Index(
            "ix_fx_rate_pair_date_status",
            "from_currency",
            "to_currency",
            "rate_date",
            "review_status",
        ),
    )


class ReconciliationItem(TimestampMixin, Base):
    __tablename__ = "reconciliation_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, native_enum=False), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(500))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_reconciliation_open_status", "resolved_at", "status"),
    )


class Payout(TimestampMixin, Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    network_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliate_networks.id", ondelete="SET NULL")
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)

    network: Mapped[AffiliateNetwork | None] = relationship(back_populates="payouts")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String(120), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, native_enum=False), default=SyncStatus.RUNNING
    )
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    cursor: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, native_enum=False))
    actor: Mapped[str] = mapped_column(String(120), default="system")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)
