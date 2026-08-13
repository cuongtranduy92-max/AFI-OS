from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from afi_os.enums import (
    AutomationJobStatus,
    CaptureStatus,
    EvidenceReviewStatus,
    FxRateReviewStatus,
    PermissionStatus,
    ReconciliationStatus,
    ResearchStatus,
    SyncStatus,
    TermsWarningStatus,
)
from afi_os.models import (
    AdObservation,
    AuditLog,
    AutomationJob,
    Campaign,
    CampaignProgramLink,
    FxRate,
    Program,
    RawCapture,
    ReconciliationItem,
    SyncRun,
    TermsEvidence,
    TermsResearchRun,
)
from afi_os.services.ads_folder_import import (
    ads_report_intraday_refresh_due,
    ads_report_is_stale,
    confirmed_results_from_metadata,
    latest_metric_date,
    latest_report_source_at,
)
from afi_os.services.commission_folder_import import (
    CONNECTOR as COMMISSION_FOLDER_CONNECTOR,
)
from afi_os.services.currency import normalization_summary
from afi_os.services.google_ads_api_sync import CONNECTOR as GOOGLE_ADS_API_CONNECTOR
from afi_os.services.programs import (
    commission_resolution_status,
    latest_research_run,
    latest_research_runs_by_domain,
    program_gate_status,
    research_attempted_at,
)

SEVERITY_ORDER = {"HIGH": 0, "ACTION": 1, "WARNING": 2}


def _audit_payload(audit: AuditLog | None) -> dict:
    return audit.payload_json if audit is not None and isinstance(audit.payload_json, dict) else {}


def _attempt_source_urls(run: TermsResearchRun, audit: AuditLog | None) -> list[str]:
    payload = _audit_payload(audit)
    raw_sources = payload.get("source_urls", run.source_urls)
    if not isinstance(raw_sources, list):
        raw_sources = run.source_urls
    return sorted(
        {
            source_url
            for source_url in raw_sources
            if isinstance(source_url, str) and source_url.startswith("https://")
        }
    )


def _item(
    *,
    key: str,
    item_type: str,
    severity: str,
    title: str,
    detail: str,
    action_label: str,
    action_view: str,
    entity_id: str | None = None,
    program: Program | None = None,
    merchant_domain: str | None = None,
    source_url: str | None = None,
    created_at: datetime | None = None,
    requires_user: bool = True,
) -> dict:
    return {
        "key": key,
        "item_type": item_type,
        "severity": severity,
        "title": title,
        "detail": detail,
        "action_label": action_label,
        "action_view": action_view,
        "entity_id": entity_id,
        "program_id": program.id if program else None,
        "program_name": program.name if program else None,
        "merchant_domain": (
            merchant_domain
            if merchant_domain is not None
            else program.merchant.website_domain
            if program
            else None
        ),
        "source_url": source_url,
        "created_at": created_at,
        "requires_user": requires_user,
    }


def operations_inbox(
    db: Session,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    today = today or now.date()
    items: list[dict] = []

    latest_maintenance = db.scalar(
        select(SyncRun)
        .where(
            SyncRun.connector == "AFI_OS_MAINTENANCE",
            SyncRun.ended_at.is_not(None),
        )
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    if (
        latest_maintenance is not None
        and latest_maintenance.status == SyncStatus.PARTIAL
        and "backup:" in (latest_maintenance.error_summary or "")
    ):
        backup_errors = [
            line
            for line in (latest_maintenance.error_summary or "").splitlines()
            if line.startswith("backup:")
        ]
        items.append(
            _item(
                key=f"BACKUP_MAINTENANCE_FAILURE:{latest_maintenance.id}",
                item_type="BACKUP_FAILURE",
                severity="HIGH",
                title="Backup tự động không đạt hậu kiểm",
                detail=(backup_errors[0] if backup_errors else "Backup maintenance thất bại")[:500],
                action_label="Mở Backup",
                action_view="system",
                entity_id=str(latest_maintenance.id),
                created_at=latest_maintenance.ended_at,
                requires_user=False,
            )
        )

    for job in db.scalars(
        select(AutomationJob)
        .where(AutomationJob.status == AutomationJobStatus.DEAD_LETTER)
        .order_by(AutomationJob.updated_at.asc(), AutomationJob.id.asc())
    ).all():
        error = ": ".join(
            part
            for part in [job.last_error_code, (job.last_error_message or "")[:240]]
            if part
        )
        items.append(
            _item(
                key=f"AUTOMATION_DEAD_LETTER:{job.id}",
                item_type="AUTOMATION_DEAD_LETTER",
                severity="ACTION",
                title=f"Automation cần kiểm tra · {job.job_type.value}",
                detail=(
                    f"Job #{job.id} đã hết {job.attempts}/{job.max_attempts} lần thử. "
                    f"{error or 'Không có chi tiết lỗi.'} Kiểm tra nguyên nhân rồi mới "
                    "bấm thử lại; dự án, permission và campaign không bị thay đổi."
                ),
                action_label="Mở đúng job",
                action_view="command",
                entity_id=str(job.id),
                created_at=job.completed_at or job.updated_at,
            )
        )

    captures_needing_review = list(
        db.scalars(
            select(RawCapture)
            .where(RawCapture.status.in_({CaptureStatus.RAW, CaptureStatus.NEEDS_REVIEW}))
            .where(
                ~select(AdObservation.id)
                .where(AdObservation.raw_capture_id == RawCapture.id)
                .exists()
            )
            .order_by(RawCapture.captured_at.asc(), RawCapture.id.asc())
        ).all()
    )
    if captures_needing_review:
        first_capture = captures_needing_review[0]
        items.append(
            _item(
                key="AD_CAPTURE_REVIEW_QUEUE",
                item_type="AD_CAPTURE_REVIEW",
                severity="ACTION",
                title="Duyệt snapshot quảng cáo thô",
                detail=(
                    f"{len(captures_needing_review)} snapshot chưa đủ advertiser/domain. "
                    "Bổ sung hai trường này rồi chấp nhận, hoặc loại nếu không liên quan; "
                    "chưa duyệt thì không tạo advertiser, project hoặc observation."
                ),
                action_label="Mở hàng đợi",
                action_view="intelligence",
                entity_id=str(first_capture.id),
                source_url=(
                    first_capture.source_url if len(captures_needing_review) == 1 else None
                ),
                created_at=first_capture.captured_at,
            )
        )

    programs = list(
        db.scalars(
            select(Program).options(
                selectinload(Program.merchant),
                selectinload(Program.terms_evidence),
                selectinload(Program.commission_facts),
                selectinload(Program.terms_research_runs),
            )
        ).all()
    )
    program_by_id = {program.id: program for program in programs}
    terms_tracking_item_by_program: dict[int, dict] = {}
    latest_attempt_audit_by_run_id: dict[str, AuditLog] = {}
    for audit in db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "terms_research_run")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all():
        latest_attempt_audit_by_run_id.setdefault(audit.entity_id, audit)

    proposed_evidence = list(
        db.scalars(
            select(TermsEvidence)
            .where(TermsEvidence.review_status == EvidenceReviewStatus.PROPOSED)
            .order_by(TermsEvidence.checked_at.asc(), TermsEvidence.id.asc())
        ).all()
    )
    unverified_evidence_by_program: dict[int, list[TermsEvidence]] = {}
    for evidence in proposed_evidence:
        program = program_by_id.get(evidence.program_id)
        if evidence.decision == PermissionStatus.NOT_CHECKED:
            unverified_evidence_by_program.setdefault(evidence.program_id, []).append(evidence)
            continue
        severity = (
            "HIGH"
            if evidence.decision in {PermissionStatus.PROHIBITED, PermissionStatus.CONFLICT}
            else "ACTION"
        )
        items.append(
            _item(
                key=f"TERMS_EVIDENCE:{evidence.id}",
                item_type="TERMS_EVIDENCE_REVIEW",
                severity=severity,
                title=f"Xét Terms Evidence · {evidence.scope}",
                detail=(
                    f"{evidence.decision.value} · confidence {evidence.confidence:.0%}. "
                    "Chỉ xác nhận khi đoạn trích chứng minh đúng scope."
                ),
                action_label="Xem Terms",
                action_view="programs",
                entity_id=str(evidence.id),
                program=program,
                source_url=evidence.source_url,
                created_at=evidence.created_at,
            )
        )

    for program_id, evidence_items in sorted(unverified_evidence_by_program.items()):
        program = program_by_id.get(program_id)
        scopes = ", ".join(sorted({item.scope for item in evidence_items}))
        source_urls = sorted({item.source_url for item in evidence_items})
        tracking_item = _item(
            key=f"TERMS_UNVERIFIED:{program_id}",
            item_type="TERMS_PERMISSION_UNVERIFIED",
            severity="WARNING",
            title="Chưa tìm thấy quyền PPC rõ ràng",
            detail=(
                f"{len(evidence_items)} scope đang NOT_CHECKED: {scopes}. "
                "Đây là cảnh báo tự theo dõi, không cần xác nhận proposal; "
                "dự án và campaign vẫn được giữ nguyên."
            ),
            action_label="Xem evidence",
            action_view="programs",
            entity_id=str(program_id),
            program=program,
            source_url=source_urls[0] if len(source_urls) == 1 else None,
            created_at=min(item.created_at for item in evidence_items),
            requires_user=False,
        )
        items.append(tracking_item)
        terms_tracking_item_by_program[program_id] = tracking_item

    for program in programs:
        if program.terms_evidence:
            continue
        latest_run = latest_research_run(program.terms_research_runs)
        if latest_run is None or latest_run.status not in {
            ResearchStatus.PROPOSAL_READY,
            ResearchStatus.CONFLICT,
        }:
            continue
        source_urls = _attempt_source_urls(
            latest_run,
            latest_attempt_audit_by_run_id.get(str(latest_run.id)),
        )
        tracking_item = _item(
            key=f"TERMS_NO_PERMISSION_EVIDENCE:{program.id}",
            item_type="TERMS_PERMISSION_NOT_FOUND",
            severity="WARNING",
            title="Đã rà, chưa thấy quyền PPC công khai",
            detail=(
                f"Lần rà {latest_run.status.value} đã đọc {len(source_urls)} URL nguồn "
                "nhưng không trích được câu xác nhận paid search/brand bidding. "
                "PPC vẫn NOT_CHECKED; dự án và campaign vẫn được giữ nguyên."
            ),
            action_label="Xem lần rà",
            action_view="programs",
            entity_id=str(latest_run.id),
            program=program,
            source_url=source_urls[0] if len(source_urls) == 1 else None,
            created_at=research_attempted_at(latest_run),
            requires_user=False,
        )
        items.append(tracking_item)
        terms_tracking_item_by_program[program.id] = tracking_item

    for program in programs:
        facts = list(program.commission_facts)
        state = commission_resolution_status(facts)
        proposed_facts = [
            fact for fact in facts if fact.review_status == EvidenceReviewStatus.PROPOSED
        ]
        if not proposed_facts:
            continue
        claims = []
        for fact in sorted(proposed_facts, key=lambda item: item.id):
            rate = float(fact.commission_rate or 0) * 100
            maximum = " tối đa" if fact.rate_is_maximum else ""
            claims.append(f"{rate:.0f}%{maximum} {fact.commission_type.value}")
        source_urls = sorted({fact.source_url for fact in proposed_facts})
        items.append(
            _item(
                key=f"COMMISSION_REVIEW:{program.id}",
                item_type="COMMISSION_PROGRAM_REVIEW",
                severity="HIGH" if state == "CONFLICT" else "ACTION",
                title=(
                    "Xét xung đột commission" if state == "CONFLICT" else "Xét commission proposal"
                ),
                detail=(
                    f"{len(proposed_facts)} proposal · {' / '.join(claims)} · "
                    f"commission state {state}. Đây là một quyết định cấp chương trình; "
                    "PPC không bị thay đổi."
                ),
                action_label="Xem commission",
                action_view="programs",
                entity_id=str(program.id),
                program=program,
                source_url=source_urls[0] if len(source_urls) == 1 else None,
                created_at=min(fact.created_at for fact in proposed_facts),
            )
        )

    for rate in db.scalars(
        select(FxRate)
        .where(FxRate.review_status == FxRateReviewStatus.PROPOSED)
        .order_by(FxRate.rate_date.asc(), FxRate.id.asc())
    ).all():
        confidence = float(rate.confidence)
        items.append(
            _item(
                key=f"FX_RATE:{rate.id}",
                item_type="FX_RATE_REVIEW",
                severity="ACTION" if confidence >= 0.8 else "WARNING",
                title=f"Xét tỷ giá {rate.from_currency} → {rate.to_currency}",
                detail=(
                    f"{rate.rate_date.isoformat()} · {rate.rate} · "
                    f"confidence {confidence:.0%}. Chưa áp dụng vào số tiền."
                ),
                action_label="Xem tỷ giá",
                action_view="finance",
                entity_id=str(rate.id),
                source_url=rate.source_url,
                created_at=rate.created_at,
            )
        )

    for issue in db.scalars(
        select(ReconciliationItem)
        .where(
            ReconciliationItem.resolved_at.is_(None),
            ReconciliationItem.status != ReconciliationStatus.ATTRIBUTED,
        )
        .order_by(ReconciliationItem.created_at.asc(), ReconciliationItem.id.asc())
    ).all():
        items.append(
            _item(
                key=f"RECONCILIATION:{issue.id}",
                item_type="RECONCILIATION_REVIEW",
                severity=(
                    "HIGH"
                    if issue.status
                    in {
                        ReconciliationStatus.CONFLICT,
                        ReconciliationStatus.DUPLICATE,
                    }
                    else "ACTION"
                ),
                title=f"Đối soát · {issue.status.value}",
                detail=issue.reason,
                action_label="Mở đối soát",
                action_view="finance",
                entity_id=str(issue.id),
                created_at=issue.created_at,
            )
        )

    finance = normalization_summary(db)
    for pair, row_count in finance["missing_pairs"].items():
        items.append(
            _item(
                key=f"MISSING_FX:{pair}",
                item_type="MISSING_FX_RATE",
                severity="ACTION",
                title=f"Thiếu tỷ giá {pair}",
                detail=f"{row_count} dòng chưa thể quy đổi sang {finance['base_currency']}.",
                action_label="Thêm tỷ giá",
                action_view="finance",
                entity_id=pair,
            )
        )

    latest_research_by_domain = latest_research_runs_by_domain(
        db.scalars(select(TermsResearchRun)).all()
    )
    for run in latest_research_by_domain.values():
        if run.status not in {
            ResearchStatus.MANUAL_INPUT_REQUIRED,
            ResearchStatus.RETRY_REQUIRED,
        }:
            continue
        program = program_by_id.get(run.program_id) if run.program_id else None
        audit = latest_attempt_audit_by_run_id.get(str(run.id))
        payload = _audit_payload(audit)
        errors = payload.get("collection_errors", [])
        if not isinstance(errors, list):
            errors = []
        priority_urls = payload.get("priority_source_urls", [])
        if not isinstance(priority_urls, list):
            priority_urls = []
        source_candidates = list(
            dict.fromkeys(
                item
                for item in [*_attempt_source_urls(run, audit), *priority_urls]
                if isinstance(item, str) and item.startswith("https://")
            )
        )
        is_retry = run.status == ResearchStatus.RETRY_REQUIRED
        detail_parts = [
            (
                "Nguồn Terms tạm thời chưa truy cập được; hệ thống sẽ tự thử lại."
                if is_retry
                else "Automation không tìm thấy câu PPC/commission rõ ràng."
            )
        ]
        if errors:
            detail_parts.append(f"Lỗi gần nhất: {str(errors[0])[:240]}")
        if priority_urls:
            detail_parts.append(f"Đã ưu tiên {len(priority_urls)} URL nguồn đã lưu.")
        detail_parts.append("Dự án vẫn được giữ với cảnh báo.")
        tracking_item = _item(
            key=(f"TERMS_RETRY:{run.domain}" if is_retry else f"TERMS_MANUAL:{run.domain}"),
            item_type=("TERMS_RETRY_PENDING" if is_retry else "TERMS_SOURCE_REQUIRED"),
            severity="WARNING",
            title=(
                f"Terms sẽ tự thử lại · {run.domain}"
                if is_retry
                else f"Cần nguồn Terms · {run.domain}"
            ),
            detail=" ".join(detail_parts),
            action_label=(
                "Xem trạng thái" if is_retry else "Xem lần rà" if program else "Nhập nguồn"
            ),
            action_view="programs",
            entity_id=str(run.id),
            program=program,
            merchant_domain=run.domain,
            source_url=source_candidates[0] if source_candidates else None,
            created_at=audit.created_at if audit is not None else run.updated_at,
            requires_user=not is_retry,
        )
        items.append(tracking_item)
        if program is not None:
            terms_tracking_item_by_program.setdefault(program.id, tracking_item)

    source_change_labels = {
        "ADDED": "nguồn mới",
        "REMOVED": "nguồn không còn được tìm thấy",
        "CONTENT_CHANGED": "nguồn đổi nội dung",
        "UNAVAILABLE": "nguồn tạm thời không đọc được",
    }
    for program in programs:
        latest_run = latest_research_run(program.terms_research_runs)
        if latest_run is None:
            continue
        audit = latest_attempt_audit_by_run_id.get(str(latest_run.id))
        payload = _audit_payload(audit)
        raw_changes = payload.get("source_changes", [])
        if not isinstance(raw_changes, list):
            continue
        changes = [
            item
            for item in raw_changes
            if isinstance(item, dict)
            and isinstance(item.get("url"), str)
            and item.get("url", "").startswith("https://")
            and item.get("change_type") in source_change_labels
        ]
        if not changes:
            continue
        counts = Counter(item["change_type"] for item in changes)
        summary = ", ".join(
            f"{count} {source_change_labels[change_type]}"
            for change_type, count in sorted(counts.items())
        )
        detail = (
            f"So với lần rà trước: {summary}. Đây chỉ là cảnh báo theo dõi; "
            "PPC, dự án và campaign không bị thay đổi."
        )
        tracking_item = terms_tracking_item_by_program.get(program.id)
        if tracking_item is not None:
            tracking_item["title"] = f"{tracking_item['title']} · nguồn Terms thay đổi"
            tracking_item["detail"] = f"{tracking_item['detail']} {detail}"
            continue
        items.append(
            _item(
                key=f"TERMS_SOURCE_CHANGED:{program.id}",
                item_type="TERMS_SOURCE_CHANGED",
                severity="WARNING",
                title="Nguồn Terms chính thức đã thay đổi",
                detail=detail,
                action_label="Xem lần rà",
                action_view="programs",
                entity_id=str(latest_run.id),
                program=program,
                source_url=changes[0]["url"] if len(changes) == 1 else None,
                created_at=audit.created_at if audit is not None else latest_run.updated_at,
                requires_user=False,
            )
        )

    latest_ads_folder = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == "GOOGLE_ADS_FOLDER")
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    latest_ads_api = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == GOOGLE_ADS_API_CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    api_is_fresh = False
    api_has_today = False
    if latest_ads_api is not None and latest_ads_api.status.value == "SUCCESS":
        try:
            api_latest_date = date.fromisoformat(str(latest_ads_api.metadata_json.get("date_to")))
            api_is_fresh = api_latest_date >= today - timedelta(days=1)
            api_has_today = api_latest_date >= today
        except ValueError:
            pass
    if latest_ads_api is not None and latest_ads_api.status.value in {
        "AUTH_FAILED",
        "RATE_LIMITED",
        "ERROR",
    }:
        requires_user = latest_ads_api.status.value == "AUTH_FAILED"
        if requires_user:
            title = "Cần đăng nhập lại Google Ads"
            detail = (
                "OAuth/Google Ads từ chối credential. Mở "
                "SETUP-GOOGLE-ADS-READ-ONLY.command để cấp lại quyền. "
                "CSV fallback và campaign hiện có vẫn được giữ nguyên."
            )
        else:
            title = "Google Ads API sẽ tự thử lại"
            detail = (
                "API lỗi tạm thời sau ba lần thử. Hệ thống sẽ tự thử lại ở chu kỳ "
                "API 6 giờ tiếp theo; CSV fallback và campaign vẫn được giữ nguyên."
            )
        items.append(
            _item(
                key="GOOGLE_ADS_API_SYNC_ERROR",
                item_type="GOOGLE_ADS_API_SYNC_ERROR",
                severity="ACTION" if requires_user else "WARNING",
                title=title,
                detail=detail,
                action_label="Xem Google Ads",
                action_view="exposure",
                entity_id=str(latest_ads_api.id),
                created_at=latest_ads_api.ended_at or latest_ads_api.started_at,
                requires_user=requires_user,
            )
        )
    if latest_ads_folder is not None:
        file_results = latest_ads_folder.metadata_json.get("file_results", [])
        confirmed_file_results = confirmed_results_from_metadata(latest_ads_folder.metadata_json)
        rejected_candidates = latest_ads_folder.metadata_json.get(
            "rejected_candidates",
            [],
        )
        has_missing_column_action = False
        if not api_is_fresh:
            for rejected in rejected_candidates:
                if (
                    not isinstance(rejected, dict)
                    or rejected.get("status") != "MISSING_REQUIRED_COLUMNS"
                ):
                    continue
                filename = str(rejected.get("filename") or "Google Ads CSV")
                missing_fields = {str(field) for field in rejected.get("missing_fields", [])}
                missing_columns = (
                    ", ".join(str(column) for column in rejected.get("missing_columns", []))
                    or "cột bắt buộc"
                )
                instructions = []
                if "campaign_external_id" in missing_fields:
                    instructions.append("Cột → Thuộc tính → ID chiến dịch")
                if "metric_date" in missing_fields:
                    instructions.append("Phân đoạn → Thời gian → Ngày")
                export_steps = "; ".join(instructions) or ("thêm lại cột theo mẫu Google Ads")
                items.append(
                    _item(
                        key=f"GOOGLE_ADS_MISSING_COLUMNS:{filename}",
                        item_type="GOOGLE_ADS_REPORT_MISSING_COLUMNS",
                        severity="ACTION",
                        title=f"Báo cáo Ads thiếu cột · {filename}",
                        detail=(
                            f"Thiếu: {missing_columns}. Trong Google Ads mở Chiến dịch → "
                            f"{export_steps}, rồi tải CSV mới vào Downloads. File này chưa "
                            "được nhập; dữ liệu và campaign cũ vẫn được giữ nguyên."
                        ),
                        action_label="Xem nhập Ads",
                        action_view="exposure",
                        entity_id=filename,
                        created_at=(latest_ads_folder.ended_at or latest_ads_folder.started_at),
                    )
                )
                has_missing_column_action = True
            for result in file_results:
                if not isinstance(result, dict):
                    continue
                result_status = result.get("status")
                if result_status not in {"ERROR", "ACCOUNT_MISMATCH"}:
                    continue
                filename = str(result.get("filename") or "Google Ads CSV")
                if result_status == "ACCOUNT_MISMATCH":
                    item_type = "GOOGLE_ADS_ACCOUNT_MISMATCH"
                    title = f"Đã chặn báo cáo sai tài khoản · {filename}"
                    fallback_error = "Customer ID hoặc tiền tệ không khớp"
                    identity = result.get("account_identity")
                    expected_ids = (
                        identity.get("expected_customer_ids", [])
                        if isinstance(identity, dict)
                        else []
                    )
                    expected_label = (
                        ", ".join(str(value) for value in expected_ids if value)
                        or "đã cấu hình trong AFI-OS"
                    )
                    next_step = (
                        f"Đăng nhập đúng Customer ID {expected_label}, rồi xuất lại "
                        "báo cáo có cột Customer ID. "
                    )
                else:
                    item_type = "GOOGLE_ADS_IMPORT_ERROR"
                    title = f"Báo cáo Ads cần sửa · {filename}"
                    fallback_error = "Không đọc được báo cáo"
                    next_step = ""
                items.append(
                    _item(
                        key=f"GOOGLE_ADS_FILE:{result.get('sha256') or filename}",
                        item_type=item_type,
                        severity="ACTION",
                        title=title,
                        detail=(
                            f"{result.get('error') or fallback_error}. "
                            f"{next_step}"
                            "File chưa được nhập; campaign hiện có không bị thay đổi."
                        ),
                        action_label="Xem nhập Ads",
                        action_view="exposure",
                        entity_id=filename,
                        created_at=(latest_ads_folder.ended_at or latest_ads_folder.started_at),
                    )
                )
        if (
            not api_is_fresh
            and not has_missing_column_action
            and ads_report_is_stale(confirmed_file_results, today=today)
        ):
            latest_date = latest_metric_date(confirmed_file_results)
            items.append(
                _item(
                    key="GOOGLE_ADS_REPORT_STALE",
                    item_type="GOOGLE_ADS_REPORT_STALE",
                    severity="ACTION",
                    title="Cần xuất báo cáo Google Ads mới",
                    detail=(
                        f"Dữ liệu hiện chỉ đến {latest_date.isoformat()}. Mở Google Ads → "
                        "Chiến dịch → Báo cáo theo ngày, thêm Campaign ID và Customer ID "
                        "rồi tải CSV vào Downloads. Campaign hiện có vẫn được giữ nguyên."
                    ),
                    action_label="Xem nhập Ads",
                    action_view="exposure",
                    entity_id=latest_date.isoformat(),
                    created_at=latest_ads_folder.ended_at or latest_ads_folder.started_at,
                )
            )
        if (
            not api_has_today
            and not has_missing_column_action
            and ads_report_intraday_refresh_due(
                confirmed_file_results,
                now=now,
            )
        ):
            latest_source_at = latest_report_source_at(confirmed_file_results)
            items.append(
                _item(
                    key="GOOGLE_ADS_REPORT_INTRADAY_REFRESH",
                    item_type="GOOGLE_ADS_REPORT_INTRADAY_REFRESH",
                    severity="WARNING",
                    title="Báo cáo Google Ads hôm nay cần làm mới",
                    detail=(
                        "Snapshot hôm nay đã hơn 6 giờ. Hệ thống sẽ ưu tiên xuất/nhập "
                        "lại bằng phiên Google Ads đọc-chỉ; đây chỉ là cảnh báo và "
                        "campaign hiện có không bị loại, sửa hoặc dừng."
                    ),
                    action_label="Xem nhập Ads",
                    action_view="exposure",
                    entity_id=today.isoformat(),
                    created_at=latest_source_at,
                    requires_user=False,
                )
            )

    latest_commission_folder = db.scalar(
        select(SyncRun)
        .where(SyncRun.connector == COMMISSION_FOLDER_CONNECTOR)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
    )
    if latest_commission_folder is not None:
        for result in latest_commission_folder.metadata_json.get("file_results", []):
            if not isinstance(result, dict):
                continue
            status = result.get("status")
            if status not in {"ERROR", "MAPPING_REQUIRED"}:
                continue
            filename = str(result.get("filename") or "Commission CSV")
            if status == "MAPPING_REQUIRED":
                title = f"Cần xác định chương trình · {filename}"
                detail = (
                    "File chưa được nhập. Đổi tên theo dạng ‘fliki commissions.csv’ "
                    "hoặc thêm cột program_domain/merchant; doanh thu hiện có không bị đổi."
                )
                item_type = "COMMISSION_FILE_MAPPING_REQUIRED"
            else:
                title = f"Báo cáo commission cần sửa · {filename}"
                detail = (
                    f"{result.get('error') or 'Không đọc được báo cáo'}. "
                    "File chưa được nhập; commission hiện có không bị thay đổi."
                )
                item_type = "COMMISSION_IMPORT_ERROR"
            items.append(
                _item(
                    key=(f"COMMISSION_FILE:{status}:{result.get('sha256') or filename}"),
                    item_type=item_type,
                    severity="ACTION",
                    title=title,
                    detail=detail,
                    action_label="Xem nhập commission",
                    action_view="finance",
                    entity_id=filename,
                    created_at=(
                        latest_commission_folder.ended_at or latest_commission_folder.started_at
                    ),
                )
            )

    campaign_links = db.scalars(
        select(CampaignProgramLink).options(
            selectinload(CampaignProgramLink.campaign),
            selectinload(CampaignProgramLink.program).selectinload(Program.merchant),
            selectinload(CampaignProgramLink.program).selectinload(Program.terms_evidence),
            selectinload(CampaignProgramLink.program).selectinload(Program.terms_research_runs),
        )
    ).all()
    link_by_campaign = {link.campaign_id: link for link in campaign_links}
    for campaign in db.scalars(select(Campaign).order_by(Campaign.id.asc())).all():
        link = link_by_campaign.get(campaign.id)
        if link is not None and link.program_id is not None:
            continue
        items.append(
            _item(
                key=f"CAMPAIGN_UNMAPPED:{campaign.id}",
                item_type="CAMPAIGN_PROGRAM_REQUIRED",
                severity="ACTION",
                title="Campaign chưa ghép chương trình",
                detail=(
                    f"{campaign.name}. Dữ liệu Ads vẫn được giữ; chọn chương trình để "
                    "tính exposure và cảnh báo Terms đúng."
                ),
                action_label="Ghép chương trình",
                action_view="exposure",
                entity_id=str(campaign.id),
                created_at=campaign.created_at,
            )
        )
    warning_links_by_program: dict[int, list[CampaignProgramLink]] = {}
    for link in campaign_links:
        if link.program is None or link.risk_acknowledged_at is not None:
            continue
        warning = program_gate_status(link.program, list(link.program.terms_evidence))
        if warning == TermsWarningStatus.TERMS_OK.value:
            continue
        warning_links_by_program.setdefault(link.program.id, []).append(link)

    for program_id, warning_links in sorted(warning_links_by_program.items()):
        program = warning_links[0].program
        warning = program_gate_status(program, list(program.terms_evidence))
        campaign_names = sorted(link.campaign.name for link in warning_links)
        visible_names = ", ".join(campaign_names[:3])
        remaining = len(campaign_names) - 3
        if remaining > 0:
            visible_names = f"{visible_names} và {remaining} campaign khác"
        tracking_item = terms_tracking_item_by_program.get(program_id)
        if tracking_item is not None:
            tracking_item["title"] = (
                f"{tracking_item['title']} · {len(warning_links)} campaign đang chạy"
            )
            tracking_item["detail"] = (
                f"{tracking_item['detail']} Campaign liên quan: {visible_names}. "
                "Chỉ cảnh báo; campaign không bị loại hoặc dừng."
            )
            continue
        items.append(
            _item(
                key=f"CAMPAIGN_WARNING_PROGRAM:{program_id}",
                item_type="CAMPAIGN_TERMS_WARNING",
                severity="WARNING",
                title=f"{len(warning_links)} campaign đang chạy với {warning}",
                detail=(f"{visible_names}. Chỉ cảnh báo; campaign không bị loại hoặc dừng."),
                action_label="Xem campaign",
                action_view="exposure",
                entity_id=str(program_id),
                program=program,
                created_at=min(link.created_at for link in warning_links),
                requires_user=False,
            )
        )

    items.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            item["created_at"].isoformat() if item["created_at"] else datetime.max.isoformat(),
            item["key"],
        )
    )
    type_counts = Counter(item["item_type"] for item in items)
    severity_counts = Counter(item["severity"] for item in items)
    return {
        "open_count": len(items),
        "requires_user_count": sum(item["requires_user"] for item in items),
        "warning_count": sum(not item["requires_user"] for item in items),
        "counts_by_type": dict(sorted(type_counts.items())),
        "counts_by_severity": dict(sorted(severity_counts.items())),
        "items": items,
    }
