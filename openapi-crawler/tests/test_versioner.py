from src.versioner import build_entry, compute_hash, compute_semantic_hash, generate_id

MOCK_SOURCE = {
    "source_url": "https://raw.githubusercontent.com/test/repo/main/openapi.yaml",
    "repo": "test/repo",
    "path": "openapi.yaml",
}
MOCK_PARSED = {
    "title": "Test API",
    "oas_version": "3.0.0",
    "latest_version": "1.0.0",
    "paths_count": 2,
    "path_keys": ["/orders", "/users"],
    "servers": [],
    "tags": [],
    "description": "",
    "normalized_spec": '{"info":{"title":"Test API","version":"1.0.0"},"openapi":"3.0.0","paths":{"/orders":{},"/users":{}}}',
    "validation_notes": ["Valid OpenAPI document detected"],
    "confidence_score": 0.9,
}
MOCK_CONTENT = "openapi: 3.0.0\ninfo:\n  title: Test API\n  version: 1.0.0\n"


def test_compute_hash_is_deterministic():
    assert compute_hash("hello") == compute_hash("hello")


def test_compute_hash_differs_for_different_content():
    assert compute_hash("hello") != compute_hash("world")


def test_compute_semantic_hash_is_deterministic():
    normalized = '{"openapi":"3.0.0","paths":{"/users":{}}}'
    assert compute_semantic_hash(normalized) == compute_semantic_hash(normalized)


def test_compute_hash_length():
    assert len(compute_hash("test")) == 64


def test_generate_id_strips_raw_prefix():
    url = "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml"
    assert generate_id(url).startswith("github:")


def test_build_entry_new_spec():
    entry = build_entry(MOCK_SOURCE, MOCK_PARSED, MOCK_CONTENT, existing_entry=None)
    assert entry["title"] == "Test API"
    assert entry["status"] == "active"
    assert entry["history"] == []
    assert entry["content_hash"] == compute_hash(MOCK_CONTENT)
    assert entry["semantic_hash"] == compute_semantic_hash(MOCK_PARSED["normalized_spec"])
    assert entry["path_keys"] == ["/orders", "/users"]
    assert entry["confidence_score"] == 0.9


def test_build_entry_unchanged_spec_keeps_empty_history():
    existing = build_entry(MOCK_SOURCE, MOCK_PARSED, MOCK_CONTENT, existing_entry=None)
    entry = build_entry(MOCK_SOURCE, MOCK_PARSED, MOCK_CONTENT, existing_entry=existing)
    assert entry["history"] == []


def test_build_entry_format_only_change_does_not_create_history():
    existing = build_entry(MOCK_SOURCE, MOCK_PARSED, MOCK_CONTENT, existing_entry=None)
    reformatted_content = "openapi: 3.0.0\ninfo: {title: Test API, version: 1.0.0}\n"
    entry = build_entry(MOCK_SOURCE, MOCK_PARSED, reformatted_content, existing_entry=existing)
    assert entry["semantic_hash"] == existing["semantic_hash"]
    assert entry["content_hash"] != existing["content_hash"]
    assert entry["history"] == []


def test_build_entry_updated_spec_stores_real_path_diff():
    existing = build_entry(MOCK_SOURCE, MOCK_PARSED, MOCK_CONTENT, existing_entry=None)
    new_content = MOCK_CONTENT + "\npaths:\n  /users: {}\n  /teams: {}\n"
    new_parsed = {
        **MOCK_PARSED,
        "paths_count": 2,
        "path_keys": ["/teams", "/users"],
        "latest_version": "2.0.0",
        "normalized_spec": '{"info":{"title":"Test API","version":"2.0.0"},"openapi":"3.0.0","paths":{"/teams":{},"/users":{}}}',
    }

    entry = build_entry(MOCK_SOURCE, new_parsed, new_content, existing_entry=existing)

    assert len(entry["history"]) == 1
    history_item = entry["history"][0]
    assert history_item["version"] == "1.0.0"
    assert history_item["replaced_by_version"] == "2.0.0"
    assert history_item["diff"]["added_paths"] == ["/teams"]
    assert history_item["diff"]["removed_paths"] == ["/orders"]
    assert history_item["diff"]["net_paths_delta"] == 0
