import json
import os

from src.logger import get_logger

logger = get_logger("catalog")
VALID_CATALOG_EXTENSIONS = (".yaml", ".yml", ".json")


def _is_credible_catalog_entry(entry: dict) -> bool:
    source_url = entry.get("source_url")
    title = entry.get("title")
    latest_version = entry.get("latest_version")
    oas_version = entry.get("oas_version")
    path_keys = entry.get("path_keys")
    semantic_hash = entry.get("semantic_hash", entry.get("hash"))
    confidence_score = entry.get("confidence_score")

    if not isinstance(source_url, str) or not source_url.lower().endswith(VALID_CATALOG_EXTENSIONS):
        return False
    if not isinstance(title, str) or not title.strip():
        return False
    if not isinstance(latest_version, str) or not latest_version.strip():
        return False
    if not isinstance(oas_version, str) or not oas_version.startswith(("2.", "3.")):
        return False
    if not isinstance(path_keys, list) or not all(isinstance(path, str) for path in path_keys):
        return False
    if not isinstance(semantic_hash, str) or not semantic_hash:
        return False
    if confidence_score is not None and not isinstance(confidence_score, (int, float)):
        return False
    return True


def _is_migration_history_artifact(item: dict) -> bool:
    if not isinstance(item, dict):
        return False

    diff = item.get("diff", {})
    return (
        item.get("semantic_hash") == item.get("content_hash")
        and item.get("version") == item.get("replaced_by_version")
        and item.get("paths_delta") == 0
        and diff.get("added_count", 0) == 0
        and diff.get("removed_count", 0) == 0
    )


def _sanitize_entry(entry: dict) -> dict:
    sanitized = dict(entry)
    history = sanitized.get("history", [])
    if isinstance(history, list):
        sanitized["history"] = [item for item in history if not _is_migration_history_artifact(item)]
    return sanitized


def load_catalog(path: str) -> dict:
    """Load existing catalog from disk. Returns dict keyed by id."""
    if not os.path.exists(path):
        logger.info(f"No existing catalog at {path}, starting fresh.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            entries = json.load(handle)
            sanitized_entries = [_sanitize_entry(entry) for entry in entries]
            credible_entries = [entry for entry in sanitized_entries if _is_credible_catalog_entry(entry)]
            dropped_entries = len(entries) - len(credible_entries)
            if dropped_entries:
                logger.warning(f"Dropped {dropped_entries} legacy catalog entries that no longer pass validation.")
            return {entry["id"]: entry for entry in credible_entries}
    except Exception as exc:
        logger.error(f"Failed to load catalog: {exc}")
        return {}


def save_catalog(catalog: dict, path: str):
    """Save catalog to disk as a JSON array."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    entries = sorted(catalog.values(), key=lambda entry: entry["id"])
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, ensure_ascii=False)
        logger.info(f"Catalog saved to {path} with {len(entries)} entries.")
    except Exception as exc:
        logger.error(f"Failed to save catalog: {exc}")


def save_run_report(report: dict, path: str):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info(f"Run report saved to {path}.")


def print_summary(catalog: dict, summary: dict, failed: list[str], rejected: list[str]):
    """Print a run summary report."""
    print("\n" + "=" * 50)
    print("CRAWL SUMMARY")
    print("=" * 50)
    print(f"  Total in catalog : {len(catalog)}")
    print(f"  Discovered       : {summary['discovered']}")
    print(f"  New              : {summary['new']}")
    print(f"  Updated          : {summary['updated']}")
    print(f"  Unchanged        : {summary['unchanged']}")
    print(f"  Fetched          : {summary['fetched']}")
    print(f"  Not modified     : {summary['not_modified']}")
    print(f"  Failed           : {summary['failed']}")
    print(f"  Rejected         : {summary['rejected']}")
    print(f"  Duplicates merged: {summary['duplicates_collapsed']}")
    print(f"  Format-only      : {summary['format_only_changes']}")
    print("=" * 50)
    if failed:
        print("  Failed URLs:")
        for url in failed:
            print(f"    - {url}")
    if rejected:
        print("  Rejected URLs:")
        for url in rejected:
            print(f"    - {url}")
    print()
