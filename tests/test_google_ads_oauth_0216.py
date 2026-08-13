from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest

from afi_os.services import google_ads_keychain, google_ads_oauth


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_keychain_store_passes_secret_via_stdin_not_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_ads_keychain,
        "_security_path",
        lambda: Path("/usr/bin/security"),
    )
    captured = {}

    def runner(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    google_ads_keychain.store_credential(
        "developer-token",
        "super-secret-token-value",
        runner=runner,
    )
    assert "super-secret-token-value" not in " ".join(captured["args"])
    assert captured["args"][-1] == "-w"
    assert captured["kwargs"]["input"] == (
        "super-secret-token-value\nsuper-secret-token-value\n"
    )
    assert captured["kwargs"]["start_new_session"] is True


def test_keychain_rejects_unknown_label_before_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_ads_keychain,
        "_security_path",
        lambda: Path("/usr/bin/security"),
    )
    called = False

    def runner(*_args, **_kwargs):
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="không được hỗ trợ"):
        google_ads_keychain.store_credential("unknown", "value", runner=runner)
    assert called is False


def test_keychain_read_does_not_put_secret_in_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_ads_keychain,
        "_security_path",
        lambda: Path("/usr/bin/security"),
    )
    captured = {}

    def runner(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="refresh-secret-value\n")

    value = google_ads_keychain.read_credential("refresh-token", runner=runner)
    assert value == "refresh-secret-value"
    assert "refresh-secret-value" not in " ".join(captured["args"])
    assert captured["args"][-1] == "-w"
    assert captured["kwargs"]["stderr"] is not None


def test_desktop_credentials_file_and_pkce_authorization_url(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "123.apps.googleusercontent.com",
                    "client_secret": "client-secret",
                }
            }
        ),
        encoding="utf-8",
    )
    client_id, client_secret = google_ads_oauth.load_desktop_credentials(credentials)
    assert client_secret == "client-secret"
    url = google_ads_oauth.build_authorization_url(
        client_id=client_id,
        redirect_uri="http://127.0.0.1:54321/oauth2/callback",
        state="expected-state",
        code_verifier="verifier-value",
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == [google_ads_oauth.GOOGLE_ADS_SCOPE]
    assert "client_secret" not in query


def test_token_exchange_returns_only_refresh_token_to_caller() -> None:
    captured = {}

    def opener(request, timeout: int):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _Response({"access_token": "short-lived", "refresh_token": "long-lived"})

    result = google_ads_oauth.exchange_authorization_code(
        client_id="123.apps.googleusercontent.com",
        client_secret="client-secret",
        code="authorization-code",
        code_verifier="verifier",
        redirect_uri="http://127.0.0.1:54321/oauth2/callback",
        opener=opener,
    )
    assert result == "long-lived"
    assert captured["url"] == google_ads_oauth.TOKEN_ENDPOINT
    assert "grant_type=authorization_code" in captured["body"]


def test_oauth_callback_requires_matching_state_and_code() -> None:
    assert (
        google_ads_oauth.parse_oauth_callback(
            "/oauth2/callback?code=test-code&state=expected",
            expected_state="expected",
        )
        == "test-code"
    )
    with pytest.raises(RuntimeError, match="state"):
        google_ads_oauth.parse_oauth_callback(
            "/oauth2/callback?code=test-code&state=attacker",
            expected_state="expected",
        )
    with pytest.raises(RuntimeError, match="từ chối"):
        google_ads_oauth.parse_oauth_callback(
            "/oauth2/callback?error=access_denied&state=expected",
            expected_state="expected",
        )
