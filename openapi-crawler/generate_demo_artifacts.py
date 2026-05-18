import json
import os

from src.parser import parse_spec
from src.versioner import build_entry, utc_now

ARTIFACTS_DIR = "artifacts"
CATALOG_BEFORE = os.path.join(ARTIFACTS_DIR, "catalog_before.json")
CATALOG_AFTER = os.path.join(ARTIFACTS_DIR, "catalog_after.json")
RUN_REPORT_AFTER = os.path.join(ARTIFACTS_DIR, "run_report_after.json")

PRIMARY_SOURCE = {
    "source_url": "https://raw.githubusercontent.com/demo/company/main/openapi.yaml",
    "repo": "demo/company",
    "path": "openapi.yaml",
}
MIRROR_SOURCE = {
    "source_url": "https://raw.githubusercontent.com/demo/company-mirror/main/openapi.yaml",
    "repo": "demo/company-mirror",
    "path": "openapi.yaml",
}
STALE_SOURCE = {
    "source_url": "https://raw.githubusercontent.com/demo/legacy/main/swagger.yaml",
    "repo": "demo/legacy",
    "path": "swagger.yaml",
}

BEFORE_SPEC = """
openapi: 3.0.0
info:
  title: Demo Billing API
  version: 1.0.0
  description: Initial release of the billing API.
servers:
  - url: https://api.demo.example
tags:
  - name: Billing
paths:
  /users:
    get: {}
  /orders:
    get: {}
"""

AFTER_SPEC = """
openapi: 3.0.0
info:
  title: Demo Billing API
  version: 2.0.0
  description: Added teams support and retired legacy orders access.
servers:
  - url: https://api.demo.example
tags:
  - name: Billing
  - name: Teams
paths:
  /users:
    get: {}
  /teams:
    get: {}
"""

STALE_SPEC = """
swagger: "2.0"
info:
  title: Legacy Reports API
  version: 0.9.0
paths:
  /reports:
    get: {}
"""


def _save_json(path: str, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def main():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    before_parsed = parse_spec(BEFORE_SPEC, PRIMARY_SOURCE["source_url"])
    after_parsed = parse_spec(AFTER_SPEC, PRIMARY_SOURCE["source_url"])
    stale_parsed = parse_spec(STALE_SPEC, STALE_SOURCE["source_url"])

    before_entry = build_entry(PRIMARY_SOURCE, before_parsed, BEFORE_SPEC)
    before_entry["sources"] = [PRIMARY_SOURCE["source_url"]]
    before_entry["source_count"] = 1
    before_entry["last_checked_at"] = before_entry["fetched_at"]

    stale_before = build_entry(STALE_SOURCE, stale_parsed, STALE_SPEC)
    stale_before["sources"] = [STALE_SOURCE["source_url"]]
    stale_before["source_count"] = 1
    stale_before["last_checked_at"] = stale_before["fetched_at"]

    catalog_before = [before_entry, stale_before]

    after_entry = build_entry(PRIMARY_SOURCE, after_parsed, AFTER_SPEC, existing_entry=before_entry)
    after_entry["sources"] = sorted([PRIMARY_SOURCE["source_url"], MIRROR_SOURCE["source_url"]])
    after_entry["source_count"] = 2
    after_entry["last_checked_at"] = after_entry["fetched_at"]

    stale_after = dict(stale_before)
    stale_after["status"] = "stale"
    stale_after["stale_reason"] = "not_discovered"
    stale_after["last_checked_at"] = utc_now()

    catalog_after = [after_entry, stale_after]

    run_report_after = {
        "run_id": "demo-artifacts",
        "generated_at": utc_now(),
        "counts": {
            "discovered": 2,
            "new": 0,
            "updated": 1,
            "unchanged": 0,
            "fetched": 1,
            "not_modified": 0,
            "failed": 0,
            "rejected": 0,
            "duplicates_collapsed": 1,
            "format_only_changes": 0,
            "active": 1,
            "stale": 1,
            "invalid": 0,
        },
        "failed_urls": [],
        "rejected_urls": [],
    }

    _save_json(CATALOG_BEFORE, catalog_before)
    _save_json(CATALOG_AFTER, catalog_after)
    _save_json(RUN_REPORT_AFTER, run_report_after)

    print(f"Wrote {CATALOG_BEFORE}")
    print(f"Wrote {CATALOG_AFTER}")
    print(f"Wrote {RUN_REPORT_AFTER}")


if __name__ == "__main__":
    main()
