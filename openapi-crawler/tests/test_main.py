import json

import pytest

import main


def _write_catalog(path, entries):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(entries, handle)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _existing_entry(url, **overrides):
    entry = {
        "id": "github:test/repo/main/openapi.yaml",
        "source_url": url,
        "sources": [url],
        "source_count": 1,
        "title": "Test API",
        "oas_version": "3.0.0",
        "latest_version": "1.0.0",
        "paths_count": 1,
        "path_keys": ["/users"],
        "servers": [],
        "tags": [],
        "description": "",
        "validation_notes": ["Valid OpenAPI document detected"],
        "confidence_score": 0.9,
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "status": "active",
        "hash": "semantic-1",
        "semantic_hash": "semantic-1",
        "content_hash": "content-1",
        "history": [],
        "failure_count": 0,
    }
    entry.update(overrides)
    return entry


def test_run_crawl_reactivates_not_modified_entry(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"

    _write_catalog(catalog_path, [
        _existing_entry(
            url,
            status="stale",
            failure_count=2,
            etag="etag-1",
            stale_reason="not_discovered",
        )
    ])

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda _fetch_url, etag, last_modified=None: {
            "outcome": "not_modified",
            "content": None,
            "etag": etag,
            "last_modified": last_modified,
            "status_code": 304,
            "error": None,
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)[0]
    report = _read_json(report_path)

    assert saved["status"] == "active"
    assert saved["failure_count"] == 0
    assert "stale_reason" not in saved
    assert "last_checked_at" in saved
    assert report["counts"]["not_modified"] == 1


def test_run_crawl_marks_failed_entry_stale_after_threshold(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"

    _write_catalog(catalog_path, [
        _existing_entry(url, failure_count=2)
    ])

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda *_args: {
            "outcome": "failed",
            "content": None,
            "etag": None,
            "last_modified": None,
            "status_code": 503,
            "error": "HTTP 503",
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)[0]

    assert saved["status"] == "stale"
    assert saved["failure_count"] == 3
    assert saved["stale_reason"] == "fetch_failed"
    assert saved["last_error"] == "HTTP 503"


def test_run_crawl_marks_undiscovered_entries_stale(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"

    _write_catalog(catalog_path, [_existing_entry(url)])

    monkeypatch.setattr(main, "discover_all_specs", lambda: [])
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)[0]

    assert saved["status"] == "stale"
    assert saved["stale_reason"] == "not_discovered"


def test_run_crawl_collapses_duplicate_mirrors(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    primary_url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"
    mirror_url = "https://raw.githubusercontent.com/test/repo-mirror/main/openapi.yaml"
    spec = """
openapi: 3.0.0
info:
  title: Mirror API
  version: 1.0.0
paths:
  /users: {}
"""

    monkeypatch.setattr(
        main,
        "discover_all_specs",
        lambda: [
            {"source_url": primary_url, "repo": "seeded", "path": "openapi.yaml"},
            {"source_url": mirror_url, "repo": "mirror/repo", "path": "openapi.yaml"},
        ],
    )
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda url, _etag, _last_modified=None: {
            "outcome": "fetched",
            "content": spec,
            "etag": f"etag-{1 if url == primary_url else 2}",
            "last_modified": f"last-modified-{1 if url == primary_url else 2}",
            "status_code": 200,
            "error": None,
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)
    report = _read_json(report_path)

    assert len(saved) == 1
    assert sorted(saved[0]["sources"]) == sorted([primary_url, mirror_url])
    assert saved[0]["source_count"] == 2
    assert report["counts"]["duplicates_collapsed"] == 1


def test_run_crawl_stores_last_modified_and_uses_it_on_next_run(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"
    captured = {}
    spec = """
openapi: 3.0.0
info:
  title: Conditional API
  version: 1.0.0
paths:
  /users: {}
"""

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])

    def fake_fetch(_url, etag, last_modified=None):
        captured["etag"] = etag
        captured["last_modified"] = last_modified
        return {
            "outcome": "fetched",
            "content": spec,
            "etag": "etag-1",
            "last_modified": "Wed, 14 May 2025 08:22:11 GMT",
            "status_code": 200,
            "error": None,
        }

    monkeypatch.setattr(main, "fetch_spec", fake_fetch)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)[0]

    assert saved["etag"] == "etag-1"
    assert saved["last_modified"] == "Wed, 14 May 2025 08:22:11 GMT"

    main.run_crawl(str(catalog_path), str(report_path))

    assert captured["etag"] == "etag-1"
    assert captured["last_modified"] == "Wed, 14 May 2025 08:22:11 GMT"


def test_run_crawl_counts_rejected_without_failed_or_fetched(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda *_args: {
            "outcome": "fetched",
            "content": "not an openapi spec",
            "etag": None,
            "last_modified": None,
            "status_code": 200,
            "error": None,
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    report = _read_json(report_path)

    assert report["counts"]["fetched"] == 0
    assert report["counts"]["failed"] == 0
    assert report["counts"]["rejected"] == 1
    assert report["rejected_urls"] == [url]
    assert report["failed_urls"] == []


def test_run_crawl_marks_existing_rejected_spec_invalid(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"
    _write_catalog(catalog_path, [_existing_entry(url)])

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda *_args: {
            "outcome": "fetched",
            "content": "still not an openapi spec",
            "etag": None,
            "last_modified": None,
            "status_code": 200,
            "error": None,
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))
    saved = _read_json(catalog_path)[0]

    assert saved["status"] == "invalid"
    assert saved["last_error"] == "Validation failed"


def test_run_crawl_counts_format_only_changes(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    url = "https://raw.githubusercontent.com/test/repo/main/openapi.yaml"
    original = """
openapi: 3.0.0
info:
  title: Format API
  version: 1.0.0
paths:
  /users: {}
"""
    reformatted = '{"paths":{"/users":{}},"info":{"version":"1.0.0","title":"Format API"},"openapi":"3.0.0"}'

    monkeypatch.setattr(main, "discover_all_specs", lambda: [{"source_url": url, "repo": "seeded", "path": "openapi.yaml"}])
    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda *_args: {
            "outcome": "fetched",
            "content": original,
            "etag": None,
            "last_modified": None,
            "status_code": 200,
            "error": None,
        },
    )
    monkeypatch.setattr(main.time, "sleep", lambda _: None)
    monkeypatch.setattr(main, "print_summary", lambda *args, **kwargs: None)

    main.run_crawl(str(catalog_path), str(report_path))

    monkeypatch.setattr(
        main,
        "fetch_spec",
        lambda *_args: {
            "outcome": "fetched",
            "content": reformatted,
            "etag": None,
            "last_modified": None,
            "status_code": 200,
            "error": None,
        },
    )

    main.run_crawl(str(catalog_path), str(report_path))
    report = _read_json(report_path)
    saved = _read_json(catalog_path)[0]

    assert report["counts"]["format_only_changes"] == 1
    assert saved["history"] == []


def test_run_polling_loop_runs_until_max_runs(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "run_report.json"
    calls = []
    sleeps = []

    monkeypatch.setattr(main, "run_crawl", lambda *_args: calls.append("run"))
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleeps.append(seconds))

    main.run_polling_loop(str(catalog_path), str(report_path), interval_hours=0.001, max_runs=2)

    assert calls == ["run", "run"]
    assert sleeps == [pytest.approx(3.6)]
