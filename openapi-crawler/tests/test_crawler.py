import requests

from config import GITHUB_SEARCH_QUERIES
from src import crawler


def test_search_github_returns_empty_list_on_request_exception(monkeypatch):
    def raise_connection_error(*_args, **_kwargs):
        raise requests.ConnectionError("blocked")

    monkeypatch.setattr(crawler.requests, "get", raise_connection_error)
    assert crawler.search_github("filename:openapi.yaml", max_results=5) == []


def test_config_includes_broader_api_name_json_queries():
    assert "extension:json openapi" in GITHUB_SEARCH_QUERIES
    assert "extension:json swagger" in GITHUB_SEARCH_QUERIES
    assert "path:openapi extension:json" in GITHUB_SEARCH_QUERIES


def test_seed_repo_sources_expand_github_repo_urls(monkeypatch):
    monkeypatch.setattr(crawler, "SEED_REPO_URLS", ["https://github.com/example/payments"])
    monkeypatch.setattr(crawler, "SEED_SPEC_PATHS", ["openapi.json"])

    sources = crawler._seed_repo_sources()

    assert sources == [
        {
            "source_url": "https://raw.githubusercontent.com/example/payments/main/openapi.json",
            "repo": "example/payments",
            "path": "openapi.json",
            "seed_repo_url": "https://github.com/example/payments",
        },
        {
            "source_url": "https://raw.githubusercontent.com/example/payments/master/openapi.json",
            "repo": "example/payments",
            "path": "openapi.json",
            "seed_repo_url": "https://github.com/example/payments",
        },
    ]


def test_fetch_spec_sends_etag_and_last_modified_headers(monkeypatch):
    captured_headers = {}

    class Response:
        status_code = 304
        text = ""
        headers = {}

    def fake_get(_url, headers, timeout):
        captured_headers.update(headers)
        return Response()

    monkeypatch.setattr(crawler.requests, "get", fake_get)

    result = crawler.fetch_spec(
        "https://raw.githubusercontent.com/example/repo/main/openapi.yaml",
        existing_etag="etag-1",
        existing_last_modified="Wed, 14 May 2025 08:22:11 GMT",
    )

    assert result["outcome"] == "not_modified"
    assert captured_headers["If-None-Match"] == "etag-1"
    assert captured_headers["If-Modified-Since"] == "Wed, 14 May 2025 08:22:11 GMT"


def test_fetch_spec_returns_last_modified_on_success(monkeypatch):
    class Response:
        status_code = 200
        text = "openapi: 3.0.0"
        headers = {
            "ETag": "etag-2",
            "Last-Modified": "Thu, 15 May 2025 09:10:44 GMT",
        }

    monkeypatch.setattr(crawler.requests, "get", lambda *_args, **_kwargs: Response())

    result = crawler.fetch_spec("https://raw.githubusercontent.com/example/repo/main/openapi.yaml")

    assert result["outcome"] == "fetched"
    assert result["etag"] == "etag-2"
    assert result["last_modified"] == "Thu, 15 May 2025 09:10:44 GMT"


def test_fetch_spec_retries_rate_limit_then_succeeds(monkeypatch):
    calls = []

    class RateLimitedResponse:
        status_code = 429
        text = ""
        headers = {}

    class SuccessResponse:
        status_code = 200
        text = "openapi: 3.0.0"
        headers = {}

    def fake_get(*_args, **_kwargs):
        calls.append("called")
        return RateLimitedResponse() if len(calls) == 1 else SuccessResponse()

    monkeypatch.setattr(crawler.requests, "get", fake_get)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_args: None)

    result = crawler.fetch_spec("https://raw.githubusercontent.com/example/repo/main/openapi.yaml")

    assert result["outcome"] == "fetched"
    assert len(calls) == 2
