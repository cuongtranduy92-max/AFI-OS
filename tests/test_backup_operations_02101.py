from datetime import UTC, datetime

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import SyncStatus
from afi_os.models import SyncRun
from afi_os.services.operations import operations_inbox


def setup_module() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_latest_maintenance_backup_failure_enters_operations_inbox() -> None:
    now = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
    with SessionLocal() as db:
        db.add(
            SyncRun(
                connector="AFI_OS_MAINTENANCE",
                started_at=now,
                ended_at=now,
                status=SyncStatus.PARTIAL,
                rows_read=0,
                rows_written=0,
                error_summary="backup: RuntimeError: schema database nguồn không trùng",
                metadata_json={},
            )
        )
        db.commit()

        inbox = operations_inbox(db, now=now)

    item = next(item for item in inbox["items"] if item["item_type"] == "BACKUP_FAILURE")
    assert item["severity"] == "HIGH"
    assert item["action_view"] == "system"
    assert item["requires_user"] is False
