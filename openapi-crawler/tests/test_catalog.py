import json

from src.catalog import load_catalog


def test_load_catalog_drops_legacy_non_openapi_entries(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    entries = [
        {
            "id": "github:valid/repo/main/openapi.yaml",
            "source_url": "https://raw.githubusercontent.com/valid/repo/main/openapi.yaml",
            "sources": ["https://raw.githubusercontent.com/valid/repo/main/openapi.yaml"],
            "title": "Valid API",
            "oas_version": "3.0.0",
            "latest_version": "1.0.0",
            "path_keys": ["/users"],
            "semantic_hash": "abc123",
            "confidence_score": 0.9,
        },
        {
            "id": "github:legacy/repo/main/openapi.yaml.license",
            "source_url": "https://raw.githubusercontent.com/legacy/repo/main/openapi.yaml.license",
            "title": "Untitled",
            "oas_version": "unknown",
            "latest_version": "unknown",
            "path_keys": [],
        },
    ]

    with open(catalog_path, "w", encoding="utf-8") as handle:
        json.dump(entries, handle)

    loaded = load_catalog(str(catalog_path))

    assert list(loaded.keys()) == ["github:valid/repo/main/openapi.yaml"]


def test_load_catalog_strips_schema_migration_history_artifacts(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    entry = {
        "id": "github:valid/repo/main/openapi.yaml",
        "source_url": "https://raw.githubusercontent.com/valid/repo/main/openapi.yaml",
        "sources": ["https://raw.githubusercontent.com/valid/repo/main/openapi.yaml"],
        "title": "Valid API",
        "oas_version": "3.0.0",
        "latest_version": "1.0.0",
        "path_keys": ["/users"],
        "semantic_hash": "new-hash",
        "confidence_score": 0.9,
        "history": [
            {
                "version": "1.0.0",
                "replaced_by_version": "1.0.0",
                "semantic_hash": "old-hash",
                "content_hash": "old-hash",
                "paths_delta": 0,
                "diff": {
                    "added_count": 0,
                    "removed_count": 0,
                },
            }
        ],
    }

    with open(catalog_path, "w", encoding="utf-8") as handle:
        json.dump([entry], handle)

    loaded = load_catalog(str(catalog_path))

    assert loaded["github:valid/repo/main/openapi.yaml"]["history"] == []
