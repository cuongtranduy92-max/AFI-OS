#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from afi_os.db import SessionLocal
from afi_os.models import AdsAccount
from afi_os.services.google_ads_api import refresh_access_token, search_campaign_metrics
from afi_os.services.google_ads_api_sync import request_google_ads_api_sync
from afi_os.services.google_ads_keychain import replace_core_credentials_atomically
from afi_os.services.google_ads_oauth import (
    authorize_desktop_app,
    load_desktop_credentials,
)


def _normalized_customer_id(value: str) -> str | None:
    normalized = value.replace("-", "").strip()
    return normalized if len(normalized) == 10 and normalized.isdigit() else None


def configured_customer_ids() -> list[str]:
    with SessionLocal() as db:
        values = list(db.scalars(select(AdsAccount.external_id)).all())
    customer_ids = sorted(
        {
            normalized
            for value in values
            if (normalized := _normalized_customer_id(value)) is not None
        }
    )
    if not customer_ids:
        raise ValueError("AFI-OS chưa có Google Ads Customer ID hợp lệ")
    return customer_ids


def discover_desktop_credentials(
    downloads_dir: Path | None = None,
    *,
    credentials_loader=load_desktop_credentials,
    candidate_limit: int = 200,
) -> list[Path]:
    root = (downloads_dir or Path.home() / "Downloads").expanduser()
    if root.is_symlink() or not root.is_dir():
        return []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    ranked: list[tuple[float, str, Path]] = []
    for path in entries:
        if path.suffix.lower() != ".json" or path.is_symlink() or not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > 128 * 1024:
            continue
        ranked.append((stat.st_mtime, path.name.lower(), path))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    valid = []
    for _mtime, _name, path in ranked[: max(1, candidate_limit)]:
        try:
            credentials_loader(path)
        except ValueError:
            continue
        valid.append(path)
    return valid


def select_credentials_path(
    explicit_path: str | None,
    *,
    downloads_dir: Path | None = None,
    input_reader=input,
    notifier=print,
    credentials_loader=load_desktop_credentials,
) -> Path:
    if explicit_path:
        return Path(explicit_path.strip().strip("'\""))
    candidates = discover_desktop_credentials(
        downloads_dir,
        credentials_loader=credentials_loader,
    )
    if len(candidates) == 1:
        notifier(f"[AFI-OS] Đã tự tìm thấy OAuth Desktop JSON: {candidates[0].name}")
        return candidates[0]
    if len(candidates) > 1:
        notifier(
            f"[AFI-OS] Có {len(candidates)} OAuth Desktop JSON hợp lệ trong Downloads; "
            "không tự chọn để tránh dùng nhầm client."
        )
    raw_path = input_reader(
        "Kéo file OAuth Desktop credentials.json vào đây rồi nhấn Enter: "
    ).strip()
    if not raw_path:
        raise ValueError("Chưa chọn OAuth Desktop credentials JSON")
    return Path(raw_path.strip().strip("'\""))


def configure_google_ads_api(
    credentials_path: Path,
    developer_token: str,
    customer_ids: list[str],
    login_customer_id: str | None = None,
    *,
    credentials_loader=load_desktop_credentials,
    authorizer=authorize_desktop_app,
    token_refresher=refresh_access_token,
    metrics_searcher=search_campaign_metrics,
    today_provider=lambda: datetime.now(UTC).date(),
    bundle_writer=replace_core_credentials_atomically,
) -> dict:
    developer_token = developer_token.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", developer_token):
        raise ValueError("Developer Token không đúng định dạng dự kiến")
    normalized_customer_ids = sorted(
        {
            normalized
            for value in customer_ids
            if (normalized := _normalized_customer_id(value)) is not None
        }
    )
    if len(normalized_customer_ids) != len(set(customer_ids)) or not normalized_customer_ids:
        raise ValueError("Danh sách Google Ads Customer ID không hợp lệ")
    normalized_login_customer_id = None
    if login_customer_id is not None and login_customer_id.strip():
        normalized_login_customer_id = _normalized_customer_id(login_customer_id)
        if normalized_login_customer_id is None:
            raise ValueError("Manager Customer ID phải có đúng 10 chữ số")
    client_id, client_secret = credentials_loader(credentials_path)
    refresh_token = authorizer(
        client_id=client_id,
        client_secret=client_secret,
    )
    access_token = token_refresher(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    preflight_today = today_provider()
    if not isinstance(preflight_today, date) or isinstance(preflight_today, datetime):
        raise ValueError("Ngày preflight Google Ads không hợp lệ")
    preflight_date = preflight_today - timedelta(days=1)
    for customer_id in normalized_customer_ids:
        metrics_searcher(
            customer_id=customer_id,
            access_token=access_token,
            developer_token=developer_token,
            start_date=preflight_date,
            end_date=preflight_date,
            login_customer_id=normalized_login_customer_id,
        )
    credentials = {
        "developer-token": developer_token,
        "oauth-client-id": client_id,
        "oauth-client-secret": client_secret,
        "refresh-token": refresh_token,
    }
    if normalized_login_customer_id is not None:
        credentials["login-customer-id"] = normalized_login_customer_id
    stored_labels = bundle_writer(credentials)
    return {
        "stored_labels": list(stored_labels),
        "validated_customer_count": len(normalized_customer_ids),
        "preflight_date": preflight_date.isoformat(),
        "mode": "READ_ONLY_REPORTING",
        "login_customer_id_configured": normalized_login_customer_id is not None,
        "write_operations_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Thiết lập Google Ads API chỉ-đọc")
    parser.add_argument("--credentials-json")
    parser.add_argument("--login-customer-id")
    args = parser.parse_args()

    print("[AFI-OS] GOOGLE ADS API · CHỈ ĐỌC")
    print("Credential sẽ vào macOS Keychain; không được in lại hoặc lưu vào database.")
    customer_ids = configured_customer_ids()
    print(f"[AFI-OS] Sẽ kiểm tra quyền đọc cho {len(customer_ids)} tài khoản đã lưu.")
    credentials_path = select_credentials_path(args.credentials_json)
    login_customer_id = getattr(args, "login_customer_id", None)
    if login_customer_id is None and not args.credentials_json:
        login_customer_id = input(
            "Manager Customer ID (MCC, để trống nếu đăng nhập trực tiếp): "
        ).strip()
    developer_token = getpass.getpass("Developer Token (nội dung sẽ không hiện): ").strip()
    print("[AFI-OS] Đang mở Google để đăng nhập và đồng ý quyền Google Ads…")
    result = configure_google_ads_api(
        credentials_path,
        developer_token,
        customer_ids,
        login_customer_id=login_customer_id,
    )
    print(
        "[AFI-OS] Hoàn tất. Đã lưu nguyên tử "
        f"{len(result['stored_labels'])} credential vào Keychain; không hiển thị bí mật."
    )
    print(
        "[AFI-OS] Google Ads đã chấp nhận truy vấn chỉ đọc cho "
        f"{result['validated_customer_count']} tài khoản."
    )
    if result.get("login_customer_id_configured"):
        print("[AFI-OS] Đã cấu hình tài khoản quản lý cho các truy vấn Google Ads.")
    try:
        request_google_ads_api_sync()
        print("[AFI-OS] Đã xếp một lần đồng bộ API ngay sau thiết lập.")
    except OSError:
        print(
            "[AFI-OS] Credential đã lưu an toàn; lịch 24/7 sẽ đồng bộ ở lần API kế tiếp."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"[AFI-OS] Không hoàn tất: {exc}")
        print("[AFI-OS] CSV fallback vẫn tiếp tục hoạt động; có thể chạy lại khi sẵn sàng.")
        raise SystemExit(1) from None
