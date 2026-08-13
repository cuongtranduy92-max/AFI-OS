from __future__ import annotations

from urllib.error import HTTPError

from afi_os.services import terms_research


def _http_error(url: str, code: int) -> HTTPError:
    return HTTPError(url, code, "not available", None, None)


def test_only_missing_standard_probe_paths_are_suppressed(monkeypatch) -> None:
    domain = "merchant.example.org"
    root_url = f"https://{domain}/"

    def fake_fetch(url: str, _domain: str) -> dict:
        if url == root_url:
            return {
                "url": root_url,
                "title": "Merchant",
                "text": "Welcome",
                "links": [],
            }
        raise _http_error(url, 404)

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(terms_research, "_fetch_page", fake_fetch)

    pages, errors = terms_research.discover_official_pages(domain)

    assert pages == []
    assert errors == []


def test_saved_or_officially_linked_404_remains_a_source_error(monkeypatch) -> None:
    domain = "merchant.example.org"
    root_url = f"https://{domain}/"
    source_url = f"https://{domain}/affiliate-terms"

    def saved_fetch(url: str, _domain: str) -> dict:
        if url == root_url:
            return {
                "url": root_url,
                "title": "Merchant",
                "text": "Welcome",
                "links": [],
            }
        raise _http_error(url, 404)

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(terms_research, "_fetch_page", saved_fetch)

    _pages, saved_errors = terms_research.discover_official_pages(
        domain,
        priority_urls=[source_url],
    )

    assert saved_errors == [f"{source_url}: HTTP Error 404: not available"]

    def linked_fetch(url: str, _domain: str) -> dict:
        if url == root_url:
            return {
                "url": root_url,
                "title": "Merchant",
                "text": "Welcome",
                "links": [source_url],
            }
        raise _http_error(url, 404)

    monkeypatch.setattr(terms_research, "_fetch_page", linked_fetch)
    _pages, linked_errors = terms_research.discover_official_pages(domain)

    assert linked_errors == [f"{source_url}: HTTP Error 404: not available"]


def test_temporary_standard_probe_failure_still_schedules_retry(monkeypatch) -> None:
    domain = "merchant.example.org"
    root_url = f"https://{domain}/"
    temporary_url = f"https://{domain}{terms_research.STANDARD_PATHS[0]}"

    def fake_fetch(url: str, _domain: str) -> dict:
        if url == root_url:
            return {
                "url": root_url,
                "title": "Merchant",
                "text": "Welcome",
                "links": [],
            }
        if url == temporary_url:
            raise _http_error(url, 503)
        raise _http_error(url, 404)

    monkeypatch.setattr(terms_research, "_host_is_public", lambda _host: True)
    monkeypatch.setattr(terms_research, "_fetch_page", fake_fetch)

    _pages, errors = terms_research.discover_official_pages(domain)

    assert len(errors) == 1
    assert errors[0].startswith(terms_research.RETRYABLE_ERROR_PREFIX)
    assert temporary_url in errors[0]
    assert terms_research._errors_require_retry(errors) is True
