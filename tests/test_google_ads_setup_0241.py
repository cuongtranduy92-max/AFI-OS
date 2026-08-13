from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from afi_os.services import google_ads_keychain
from afi_os.services.google_ads_api import GoogleAdsApiError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPOSITORY_ROOT / "scripts" / "google_ads_setup.py"
SPEC = importlib.util.spec_from_file_location("google_ads_setup_0241", SETUP_PATH)
assert SPEC is not None and SPEC.loader is not None
GOOGLE_ADS_SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GOOGLE_ADS_SETUP)


def _new_values() -> dict[str, str]:
    return {
        "developer-token": "new-developer-token-value",
        "oauth-client-id": "new.apps.googleusercontent.com",
        "oauth-client-secret": "new-client-secret",
        "refresh-token": "new-refresh-token",
    }


def _desktop_json(path: Path, client_id: str = "test.apps.googleusercontent.com") -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": "client-secret",
                }
            }
        ),
        encoding="utf-8",
    )


def test_discovers_only_regular_desktop_oauth_json_sorted_newest_first(
    tmp_path: Path,
) -> None:
    older = tmp_path / "credentials.json"
    newer = tmp_path / "client_secret_new.json"
    invalid = tmp_path / "unrelated.json"
    web_client = tmp_path / "web-client.json"
    symlink = tmp_path / "client_secret_link.json"
    _desktop_json(older, "older.apps.googleusercontent.com")
    _desktop_json(newer, "newer.apps.googleusercontent.com")
    invalid.write_text("not-json", encoding="utf-8")
    web_client.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "web.apps.googleusercontent.com",
                    "client_secret": "secret",
                }
            }
        ),
        encoding="utf-8",
    )
    symlink.symlink_to(newer)
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))

    assert GOOGLE_ADS_SETUP.discover_desktop_credentials(tmp_path) == [newer, older]


def test_unique_downloaded_oauth_json_is_selected_without_prompt(tmp_path: Path) -> None:
    credentials = tmp_path / "client_secret_download.json"
    _desktop_json(credentials)
    notices = []

    selected = GOOGLE_ADS_SETUP.select_credentials_path(
        None,
        downloads_dir=tmp_path,
        input_reader=lambda _prompt: pytest.fail("unique valid JSON must not prompt"),
        notifier=notices.append,
    )

    assert selected == credentials
    assert notices == [
        "[AFI-OS] Đã tự tìm thấy OAuth Desktop JSON: client_secret_download.json"
    ]


def test_multiple_oauth_json_files_require_explicit_selection(tmp_path: Path) -> None:
    first = tmp_path / "client_secret_first.json"
    second = tmp_path / "client_secret_second.json"
    _desktop_json(first, "first.apps.googleusercontent.com")
    _desktop_json(second, "second.apps.googleusercontent.com")
    notices = []

    selected = GOOGLE_ADS_SETUP.select_credentials_path(
        None,
        downloads_dir=tmp_path,
        input_reader=lambda _prompt: f"'{first}'",
        notifier=notices.append,
    )

    assert selected == first
    assert len(notices) == 1
    assert "không tự chọn" in notices[0]


def test_explicit_oauth_json_path_bypasses_download_discovery(tmp_path: Path) -> None:
    explicit = tmp_path / "chosen.json"
    assert GOOGLE_ADS_SETUP.select_credentials_path(
        f'"{explicit}"',
        downloads_dir=tmp_path / "missing",
        input_reader=lambda _prompt: pytest.fail("explicit path must not prompt"),
    ) == explicit


def test_oauth_finishes_before_any_keychain_write() -> None:
    events = []
    captured = {}

    def loader(path: Path) -> tuple[str, str]:
        events.append(("load", str(path)))
        return "123.apps.googleusercontent.com", "client-secret"

    def authorizer(**kwargs) -> str:
        assert [event[0] for event in events] == ["load"]
        assert kwargs["client_secret"] == "client-secret"
        events.append(("oauth", "complete"))
        return "refresh-secret"

    def token_refresher(**kwargs) -> str:
        assert [event[0] for event in events] == ["load", "oauth"]
        assert kwargs["refresh_token"] == "refresh-secret"
        events.append(("refresh", "complete"))
        return "access-secret"

    def metrics_searcher(**kwargs) -> list:
        assert [event[0] for event in events] == ["load", "oauth", "refresh"]
        assert kwargs["customer_id"] == "1234567890"
        assert kwargs["access_token"] == "access-secret"
        assert kwargs["start_date"] == date(2026, 8, 10)
        assert kwargs["end_date"] == date(2026, 8, 10)
        assert kwargs["login_customer_id"] is None
        events.append(("preflight", "complete"))
        return []

    def bundle_writer(values: dict[str, str]) -> tuple[str, ...]:
        assert [event[0] for event in events] == [
            "load",
            "oauth",
            "refresh",
            "preflight",
        ]
        captured.update(values)
        events.append(("keychain", "committed"))
        return google_ads_keychain.CORE_CREDENTIAL_LABELS

    result = GOOGLE_ADS_SETUP.configure_google_ads_api(
        Path("credentials.json"),
        "developer-token-value-123",
        ["123-456-7890"],
        credentials_loader=loader,
        authorizer=authorizer,
        token_refresher=token_refresher,
        metrics_searcher=metrics_searcher,
        today_provider=lambda: date(2026, 8, 11),
        bundle_writer=bundle_writer,
    )

    assert [event[0] for event in events] == [
        "load",
        "oauth",
        "refresh",
        "preflight",
        "keychain",
    ]
    assert captured["refresh-token"] == "refresh-secret"
    assert result["stored_labels"] == list(google_ads_keychain.CORE_CREDENTIAL_LABELS)
    assert "refresh-secret" not in str(result)
    assert "access-secret" not in str(result)
    assert result["validated_customer_count"] == 1
    assert result["preflight_date"] == "2026-08-10"
    assert result["write_operations_enabled"] is False


def test_manager_customer_id_is_preflighted_and_stored_atomically() -> None:
    searches = []
    stored = {}

    def metrics_searcher(**kwargs) -> list:
        searches.append(kwargs)
        return []

    def bundle_writer(values: dict[str, str]) -> tuple[str, ...]:
        stored.update(values)
        return tuple(values)

    result = GOOGLE_ADS_SETUP.configure_google_ads_api(
        Path("credentials.json"),
        "developer-token-value-123",
        ["123-456-7890"],
        login_customer_id="987-654-3210",
        credentials_loader=lambda _path: (
            "123.apps.googleusercontent.com",
            "client-secret",
        ),
        authorizer=lambda **_kwargs: "refresh-secret",
        token_refresher=lambda **_kwargs: "access-secret",
        metrics_searcher=metrics_searcher,
        today_provider=lambda: date(2026, 8, 11),
        bundle_writer=bundle_writer,
    )

    assert searches[0]["customer_id"] == "1234567890"
    assert searches[0]["login_customer_id"] == "9876543210"
    assert stored["login-customer-id"] == "9876543210"
    assert result["login_customer_id_configured"] is True
    assert "9876543210" not in str(result)


def test_invalid_manager_customer_id_fails_before_oauth_or_keychain() -> None:
    reached = []

    with pytest.raises(ValueError, match="Manager Customer ID"):
        GOOGLE_ADS_SETUP.configure_google_ads_api(
            Path("credentials.json"),
            "developer-token-value-123",
            ["1234567890"],
            login_customer_id="181-609",
            credentials_loader=lambda _path: reached.append("loader") or ("id", "secret"),
            authorizer=lambda **_kwargs: reached.append("oauth") or "refresh",
            bundle_writer=lambda _values: reached.append("keychain") or (),
        )

    assert reached == []


def test_oauth_cancel_keeps_keychain_writer_unreached() -> None:
    writer_called = False

    def authorizer(**_kwargs) -> str:
        raise RuntimeError("consent cancelled")

    def bundle_writer(_values: dict[str, str]) -> tuple[str, ...]:
        nonlocal writer_called
        writer_called = True
        return ()

    with pytest.raises(RuntimeError, match="cancelled"):
        GOOGLE_ADS_SETUP.configure_google_ads_api(
            Path("credentials.json"),
            "developer-token-value-123",
            ["1234567890"],
            credentials_loader=lambda _path: (
                "123.apps.googleusercontent.com",
                "client-secret",
            ),
            authorizer=authorizer,
            bundle_writer=bundle_writer,
        )

    assert writer_called is False


def test_successful_setup_requests_immediate_sync_after_keychain_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        GOOGLE_ADS_SETUP,
        "configured_customer_ids",
        lambda: ["1234567890"],
    )
    monkeypatch.setattr(
        GOOGLE_ADS_SETUP.getpass,
        "getpass",
        lambda _prompt: "developer-token-value-123",
    )
    monkeypatch.setattr(
        GOOGLE_ADS_SETUP,
        "configure_google_ads_api",
        lambda *_args, **_kwargs: events.append("keychain-committed")
        or {
            "stored_labels": list(google_ads_keychain.CORE_CREDENTIAL_LABELS),
            "validated_customer_count": 1,
        },
    )
    monkeypatch.setattr(
        GOOGLE_ADS_SETUP,
        "request_google_ads_api_sync",
        lambda: events.append("sync-requested"),
    )
    monkeypatch.setattr(
        GOOGLE_ADS_SETUP.argparse.ArgumentParser,
        "parse_args",
        lambda _parser: type("Args", (), {"credentials_json": "credentials.json"})(),
    )

    assert GOOGLE_ADS_SETUP.main() == 0
    assert events == ["keychain-committed", "sync-requested"]


@pytest.mark.parametrize("failure_stage", ["refresh", "search"])
def test_preflight_failure_keeps_keychain_writer_unreached(failure_stage: str) -> None:
    writer_called = False

    def token_refresher(**_kwargs) -> str:
        if failure_stage == "refresh":
            raise GoogleAdsApiError("OAuth preflight rejected", category="AUTH_FAILED")
        return "access-secret"

    def metrics_searcher(**_kwargs) -> list:
        raise GoogleAdsApiError("Ads preflight rejected", category="AUTH_FAILED")

    def bundle_writer(_values: dict[str, str]) -> tuple[str, ...]:
        nonlocal writer_called
        writer_called = True
        return ()

    with pytest.raises(GoogleAdsApiError, match="preflight rejected"):
        GOOGLE_ADS_SETUP.configure_google_ads_api(
            Path("credentials.json"),
            "developer-token-value-123",
            ["1234567890"],
            credentials_loader=lambda _path: (
                "123.apps.googleusercontent.com",
                "client-secret",
            ),
            authorizer=lambda **_kwargs: "refresh-secret",
            token_refresher=token_refresher,
            metrics_searcher=metrics_searcher,
            today_provider=lambda: date(2026, 8, 11),
            bundle_writer=bundle_writer,
        )

    assert writer_called is False


def test_bundle_write_failure_restores_every_previous_value() -> None:
    previous = {label: f"old-{label}" for label in google_ads_keychain.CORE_CREDENTIAL_LABELS}
    state = previous.copy()

    def writer(label: str, value: str) -> None:
        if label == "oauth-client-secret" and value == "new-client-secret":
            raise RuntimeError("simulated write failure")
        state[label] = value

    with pytest.raises(RuntimeError, match="đã được phục hồi"):
        google_ads_keychain.replace_core_credentials_atomically(
            _new_values(),
            presence_checker=lambda label: label in state,
            credential_reader=lambda label: state[label],
            credential_writer=writer,
            credential_deleter=lambda label: state.pop(label),
        )

    assert state == previous


def test_bundle_write_failure_removes_new_partial_values() -> None:
    state = {}

    def writer(label: str, value: str) -> None:
        if label == "oauth-client-secret":
            raise RuntimeError("simulated write failure")
        state[label] = value

    with pytest.raises(RuntimeError, match="đã được phục hồi"):
        google_ads_keychain.replace_core_credentials_atomically(
            _new_values(),
            presence_checker=lambda label: label in state,
            credential_reader=lambda label: state[label],
            credential_writer=writer,
            credential_deleter=lambda label: state.pop(label),
        )

    assert state == {}


def test_manager_id_is_part_of_same_keychain_rollback() -> None:
    previous = {
        label: f"old-{label}" for label in google_ads_keychain.ALLOWED_CREDENTIAL_LABELS
    }
    state = previous.copy()
    values = _new_values() | {"login-customer-id": "9876543210"}
    failed = False

    def writer(label: str, value: str) -> None:
        nonlocal failed
        state[label] = value
        if label == "login-customer-id" and not failed:
            failed = True
            raise RuntimeError("simulated manager write failure")

    with pytest.raises(RuntimeError, match="đã được phục hồi"):
        google_ads_keychain.replace_core_credentials_atomically(
            values,
            presence_checker=lambda label: label in state,
            credential_reader=lambda label: previous[label],
            credential_writer=writer,
            credential_deleter=lambda label: state.pop(label),
        )

    assert state == previous


def _executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.parametrize("setup_status", [0, 7])
def test_one_click_command_kickstarts_maintenance_only_after_success(
    tmp_path: Path, setup_status: int
) -> None:
    target = tmp_path / "AFI-OS"
    target.mkdir()
    command = target / "SETUP-GOOGLE-ADS-READ-ONLY.command"
    shutil.copy2(REPOSITORY_ROOT / command.name, command)
    command.chmod(0o755)
    log = tmp_path / "calls.log"
    fake_bin = tmp_path / "fake-bin"
    _executable(
        target / ".venv" / "bin" / "python",
        '#!/bin/sh\necho "python:$*" >> "$AFI_TEST_LOG"\nexit "$AFI_TEST_STATUS"\n',
    )
    _executable(target / "scripts" / "google_ads_setup.py", "#!/bin/sh\nexit 0\n")
    _executable(
        fake_bin / "launchctl",
        '#!/bin/sh\necho "launchctl:$*" >> "$AFI_TEST_LOG"\nexit 0\n',
    )
    environment = os.environ.copy()
    environment.update(
        {
            "AFI_OS_NONINTERACTIVE": "1",
            "AFI_TEST_LOG": str(log),
            "AFI_TEST_STATUS": str(setup_status),
            "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        }
    )

    result = subprocess.run(
        ["bash", str(command)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == setup_status
    calls = log.read_text(encoding="utf-8")
    assert "google_ads_setup.py" in calls
    assert ("kickstart -k" in calls) is (setup_status == 0)
