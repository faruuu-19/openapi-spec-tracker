from src.parser import parse_spec

VALID_OAS3_YAML = """
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
  description: A test API
servers:
  - url: https://api.example.com
tags:
  - name: Users
paths:
  /users:
    get:
      summary: Get users
  /posts:
    get:
      summary: Get posts
"""

VALID_SWAGGER2_YAML = """
swagger: "2.0"
info:
  title: Old API
  version: 2.0.0
host: api.example.com
basePath: /v1
schemes:
  - https
paths:
  /items:
    get:
      summary: Get items
"""

VALID_JSON = '{"openapi": "3.0.0", "info": {"title": "JSON API", "version": "1.0"}, "paths": {"/test": {}, "/users": {}}}'

INVALID_YAML = "this is not yaml: [{"
NOT_AN_OPENAPI_SPEC = """
info:
  title: Looks close
paths:
  /users:
    get: {}
"""


def test_parse_oas3_yaml():
    result = parse_spec(VALID_OAS3_YAML, "openapi.yaml")
    assert result is not None
    assert result["title"] == "Test API"
    assert result["oas_version"] == "3.0.0"
    assert result["latest_version"] == "1.0.0"
    assert result["paths_count"] == 2
    assert result["path_keys"] == ["/posts", "/users"]
    assert result["servers"] == ["https://api.example.com"]
    assert "Users" in result["tags"]
    assert result["confidence_score"] > 0.8
    assert any("Valid OpenAPI" in note for note in result["validation_notes"])
    assert '"openapi":"3.0.0"' in result["normalized_spec"]


def test_parse_swagger2_yaml_builds_servers_from_host_and_scheme():
    result = parse_spec(VALID_SWAGGER2_YAML, "swagger.yaml")
    assert result is not None
    assert result["title"] == "Old API"
    assert result["oas_version"] == "2.0"
    assert result["paths_count"] == 1
    assert result["servers"] == ["https://api.example.com/v1"]


def test_parse_json():
    result = parse_spec(VALID_JSON, "openapi.json")
    assert result is not None
    assert result["title"] == "JSON API"
    assert result["paths_count"] == 2
    assert result["path_keys"] == ["/test", "/users"]


def test_invalid_yaml_returns_none():
    assert parse_spec(INVALID_YAML, "openapi.yaml") is None


def test_missing_openapi_version_returns_none():
    assert parse_spec(NOT_AN_OPENAPI_SPEC, "openapi.yaml") is None


def test_missing_info_version_returns_none():
    spec = """
openapi: 3.1.0
info:
  title: Missing version
paths: {}
"""
    assert parse_spec(spec, "openapi.yaml") is None


def test_invalid_paths_object_returns_none():
    spec = """
openapi: 3.1.0
info:
  title: Bad Paths
  version: 1.0.0
paths:
  - /users
"""
    assert parse_spec(spec, "openapi.yaml") is None


def test_semantic_normalization_ignores_key_order():
    spec_a = """
openapi: 3.0.0
info:
  title: Ordered API
  version: 1.0.0
paths:
  /users: {}
"""
    spec_b = """
paths:
  /users: {}
info:
  version: 1.0.0
  title: Ordered API
openapi: 3.0.0
"""
    result_a = parse_spec(spec_a, "openapi.yaml")
    result_b = parse_spec(spec_b, "openapi.yaml")
    assert result_a["normalized_spec"] == result_b["normalized_spec"]


def test_semantic_normalization_handles_numeric_nested_keys():
    spec = """
openapi: 3.0.0
info:
  title: Response API
  version: 1.0.0
paths:
  /users:
    get:
      responses:
        200:
          description: ok
"""
    result = parse_spec(spec, "openapi.yaml")
    assert result is not None
    assert '"200"' in result["normalized_spec"]


def test_semantic_normalization_handles_yaml_timestamps():
    spec = """
openapi: 3.0.0
info:
  title: Timestamp API
  version: 1.0.0
  x-generated-at: 2026-05-16
paths:
  /users: {}
"""
    result = parse_spec(spec, "openapi.yaml")
    assert result is not None
    assert "2026-05-16" in result["normalized_spec"]
