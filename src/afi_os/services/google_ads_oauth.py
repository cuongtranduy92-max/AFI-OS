from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def load_desktop_credentials(path: Path) -> tuple[str, str]:
    path = path.expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError("OAuth credentials JSON không phải file thường hợp lệ")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Không đọc được OAuth credentials JSON") from exc
    installed = payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(installed, dict):
        raise ValueError("OAuth client phải có loại Desktop app")
    client_id = installed.get("client_id")
    client_secret = installed.get("client_secret")
    if (
        not isinstance(client_id, str)
        or not client_id.endswith(".apps.googleusercontent.com")
        or not isinstance(client_secret, str)
        or not client_secret
    ):
        raise ValueError("OAuth Desktop client ID/secret không hợp lệ")
    return client_id, client_secret


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_verifier: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_ADS_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZATION_ENDPOINT}?{query}"


def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    opener=urllib.request.urlopen,
) -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read(128 * 1024).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("OAuth token exchange thất bại") from exc
    refresh_token = payload.get("refresh_token") if isinstance(payload, dict) else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError("Google không trả refresh token; cần chạy consent lại")
    return refresh_token


def parse_oauth_callback(path: str, *, expected_state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if query.get("error", [""])[0]:
        raise RuntimeError("Người dùng hoặc Google đã từ chối OAuth consent")
    if query.get("state", [""])[0] != expected_state:
        raise RuntimeError("OAuth callback state không hợp lệ")
    code = query.get("code", [""])[0]
    if not code:
        raise RuntimeError("OAuth callback không có authorization code")
    return code


def authorize_desktop_app(
    *,
    client_id: str,
    client_secret: str,
    timeout_seconds: int = 300,
    browser_opener=webbrowser.open,
    token_opener=urllib.request.urlopen,
) -> str:
    callback: dict[str, str] = {}
    expected_state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            callback["path"] = self.path
            try:
                parse_oauth_callback(self.path, expected_state=expected_state)
                ok = True
            except RuntimeError:
                ok = False
            message = (
                "AFI-OS đã nhận quyền Google Ads. Có thể đóng tab này."
                if ok
                else "AFI-OS không nhận được quyền. Có thể đóng tab và thử lại."
            )
            content = message.encode("utf-8")
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, _format: str, *_args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = max(30, min(timeout_seconds, 600))
    redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth2/callback"
    authorization_url = build_authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=expected_state,
        code_verifier=code_verifier,
    )
    try:
        if not browser_opener(authorization_url):
            raise RuntimeError("Không mở được trình duyệt đăng nhập Google")
        server.handle_request()
    finally:
        server.server_close()
    if not callback.get("path"):
        raise RuntimeError("OAuth callback hết hạn hoặc state không hợp lệ")
    code = parse_oauth_callback(callback["path"], expected_state=expected_state)
    return exchange_authorization_code(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        opener=token_opener,
    )
