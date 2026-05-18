import json

from src.parser import parse_spec
from src.versioner import build_entry

SOURCE = {
    "source_url": "https://example.com/demo/openapi.yaml",
    "repo": "demo",
    "path": "openapi.yaml",
}

BEFORE_SPEC = """
openapi: 3.0.0
info:
  title: Demo API
  version: 1.0.0
paths:
  /users:
    get: {}
  /orders:
    get: {}
"""

AFTER_SPEC = """
openapi: 3.0.0
info:
  title: Demo API
  version: 2.0.0
paths:
  /users:
    get: {}
  /teams:
    get: {}
"""


def main():
    before_parsed = parse_spec(BEFORE_SPEC, "openapi.yaml")
    after_parsed = parse_spec(AFTER_SPEC, "openapi.yaml")

    before_entry = build_entry(SOURCE, before_parsed, BEFORE_SPEC)
    after_entry = build_entry(SOURCE, after_parsed, AFTER_SPEC, existing_entry=before_entry)

    print("Before paths:", before_entry["path_keys"])
    print("After paths :", after_entry["path_keys"])
    print("\nHistory entry:")
    print(json.dumps(after_entry["history"][-1], indent=2))


if __name__ == "__main__":
    main()
