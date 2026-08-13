from fastapi import APIRouter

from afi_os.schemas import BackupCreateResponse, BackupInfo
from afi_os.services.backups import create_backup, list_backups

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/backups", response_model=list[BackupInfo])
def backups() -> list[BackupInfo]:
    return [BackupInfo(**item) for item in list_backups()]


@router.post("/backups", response_model=BackupCreateResponse)
def backup_now() -> BackupCreateResponse:
    item = BackupInfo(**create_backup())
    return BackupCreateResponse(backup=item, message="Backup SQLite đã tạo và kiểm tra toàn vẹn.")
