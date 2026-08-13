from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

import pytest

from afi_os.services import google_ads_oauth

pytestmark = pytest.mark.skipif(
    os.environ.get("AFI_OS_RUN_LOOPBACK_TEST") != "1",
    reason="requires permission to bind a localhost callback port",
)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return json.dumps({"refresh_token": "refresh-from-google"}).encode("utf-8")


def test_real_loopback_callback_uses_random_local_port_and_validates_state() -> None:
    callback_thread: threading.Thread | None = None

    def browser_opener(auth_url: str) -> bool:
        nonlocal callback_thread
        query = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
        redirect_uri = query["redirect_uri"][0]
        state = query["state"][0]

        def callback() -> None:
            time.sleep(0.05)
            url = f"{redirect_uri}?code=test-code&state={urllib.parse.quote(state)}"
            with urllib.request.urlopen(url, timeout=2) as response:
                assert response.status == 200

        callback_thread = threading.Thread(target=callback, daemon=True)
        callback_thread.start()
        return True

    def token_opener(request, timeout: int):
        body = urllib.parse.parse_qs(request.data.decode("utf-8"))
        assert body["code"] == ["test-code"]
        assert body["redirect_uri"][0].startswith("http://127.0.0.1:")
        assert timeout == 20
        return _Response()

    token = google_ads_oauth.authorize_desktop_app(
        client_id="123.apps.googleusercontent.com",
        client_secret="client-secret",
        timeout_seconds=30,
        browser_opener=browser_opener,
        token_opener=token_opener,
    )
    assert token == "refresh-from-google"
    assert callback_thread is not None
    callback_thread.join(timeout=2)
