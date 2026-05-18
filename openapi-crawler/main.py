import argparse
import time

from config import CATALOG_FILE, POLLING_INTERVAL_HOURS, RUN_REPORT_FILE, STALE_AFTER_FAILURES
from src.catalog import load_catalog, print_summary, save_catalog, save_run_report
from src.crawler import discover_all_specs, fetch_spec
from src.logger import RUN_ID, get_logger
from src.parser import parse_spec
from src.versioner import build_entry, generate_id, utc_now

logger = get_logger("main")


def _entry_sources(entry: dict) -> list[str]:
    sources = entry.get("sources")
    if isinstance(sources, list) and sources:
        return [source for source in sources if isinstance(source, str)]
    source_url = entry.get("source_url")
    return [source_url] if isinstance(source_url, str) and source_url else []


def _is_schema_complete(entry: dict) -> bool:
    return all([
        entry.get("semantic_hash"),
        entry.get("content_hash"),
        isinstance(entry.get("validation_notes"), list),
        isinstance(entry.get("confidence_score"), (int, float)),
    ])


def _index_existing_entries(catalog: dict) -> tuple[dict, dict]:
    source_index = {}
    semantic_index = {}

    for entry in catalog.values():
        for source_url in _entry_sources(entry):
            source_index[source_url] = entry

        semantic_hash = entry.get("semantic_hash", entry.get("hash"))
        if semantic_hash and semantic_hash not in semantic_index:
            semantic_index[semantic_hash] = entry

    return source_index, semantic_index


def _ensure_existing_tracker(tracker: dict, entry: dict) -> dict:
    return tracker.setdefault(entry["id"], {
        "discovered": False,
        "healthy": False,
        "invalid": False,
        "failure_errors": [],
    })


def _mark_fetch_failure(entry: dict, error_message: str):
    entry["failure_count"] = entry.get("failure_count", 0) + 1
    entry["last_error"] = error_message
    if entry["failure_count"] >= STALE_AFTER_FAILURES:
        entry["status"] = "stale"
        entry["stale_reason"] = "fetch_failed"


def _reactivate_existing_entry(entry: dict):
    entry["status"] = "active"
    entry["failure_count"] = 0
    entry.pop("last_error", None)
    entry.pop("stale_reason", None)


def _select_primary_source(cluster: list[dict]) -> str:
    ranked = sorted(
        (observation["source"] for observation in cluster),
        key=lambda source: (
            0 if source.get("repo") == "seeded" else 1,
            0 if "raw.githubusercontent.com" in source["source_url"] else 1,
            len(source["source_url"]),
            source["source_url"],
        ),
    )
    return ranked[0]["source_url"]


def _merge_cluster(cluster: list[dict], existing_by_semantic: dict) -> tuple[dict, dict | None]:
    semantic_hash = cluster[0]["entry"].get("semantic_hash", cluster[0]["entry"].get("hash"))
    existing_match = next((obs["existing_entry"] for obs in cluster if obs["existing_entry"]), None)
    if existing_match is None:
        existing_match = existing_by_semantic.get(semantic_hash)

    merged_entry = dict(cluster[0]["entry"])

    if existing_match:
        merged_entry["id"] = existing_match["id"]
        merged_entry["source_url"] = existing_match["source_url"]
        merged_semantic_hash = merged_entry.get("semantic_hash", merged_entry.get("hash"))
        if merged_semantic_hash == existing_match.get("semantic_hash", existing_match.get("hash")):
            merged_entry["history"] = list(existing_match.get("history", []))
        if "etag" not in merged_entry and existing_match.get("etag"):
            merged_entry["etag"] = existing_match["etag"]
        if "last_modified" not in merged_entry and existing_match.get("last_modified"):
            merged_entry["last_modified"] = existing_match["last_modified"]
    else:
        canonical_source = _select_primary_source(cluster)
        merged_entry["id"] = generate_id(canonical_source)
        merged_entry["source_url"] = canonical_source

    cluster_sources = set(_entry_sources(existing_match)) if existing_match else set()
    for observation in cluster:
        cluster_sources.add(observation["source"]["source_url"])
        cluster_sources.update(_entry_sources(observation["entry"]))

    merged_entry["sources"] = sorted(cluster_sources)
    merged_entry["source_count"] = len(merged_entry["sources"])

    primary_source_url = merged_entry["source_url"]
    primary_observation = next(
        (observation for observation in cluster if observation["source"]["source_url"] == primary_source_url),
        None,
    )
    if primary_observation and primary_observation["entry"].get("etag"):
        merged_entry["etag"] = primary_observation["entry"]["etag"]
    if primary_observation and primary_observation["entry"].get("last_modified"):
        merged_entry["last_modified"] = primary_observation["entry"]["last_modified"]

    return merged_entry, existing_match


def _build_run_report(
    catalog: dict,
    summary: dict,
    failed_urls: list[str],
    rejected_urls: list[str],
    report_path: str,
) -> dict:
    active_count = sum(1 for entry in catalog.values() if entry.get("status") == "active")
    stale_count = sum(1 for entry in catalog.values() if entry.get("status") == "stale")
    invalid_count = sum(1 for entry in catalog.values() if entry.get("status") == "invalid")

    return {
        "run_id": RUN_ID,
        "generated_at": utc_now(),
        "report_path": report_path,
        "counts": {
            **summary,
            "active": active_count,
            "stale": stale_count,
            "invalid": invalid_count,
        },
        "failed_urls": failed_urls,
        "rejected_urls": rejected_urls,
    }


def run_crawl(catalog_path: str = CATALOG_FILE, run_report_path: str = RUN_REPORT_FILE):
    logger.info("Starting crawl run")

    catalog = load_catalog(catalog_path)
    existing_by_source, existing_by_semantic = _index_existing_entries(catalog)
    existing_tracker = {}
    observations = []
    failed_urls = []
    rejected_urls = []
    new_entries = []
    updated_entries = []
    unchanged_entries = []

    summary = {
        "discovered": 0,
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "fetched": 0,
        "not_modified": 0,
        "failed": 0,
        "rejected": 0,
        "duplicates_collapsed": 0,
        "format_only_changes": 0,
    }

    sources = discover_all_specs()
    summary["discovered"] = len(sources)

    for source in sources:
        url = source["source_url"]
        existing = existing_by_source.get(url)
        logger.info(f"Fetching: {url}")

        if existing:
            _ensure_existing_tracker(existing_tracker, existing)["discovered"] = True

        existing_etag = (
            existing.get("etag")
            if existing and existing.get("source_url") == url and _is_schema_complete(existing)
            else None
        )
        existing_last_modified = (
            existing.get("last_modified")
            if existing and existing.get("source_url") == url and _is_schema_complete(existing)
            else None
        )
        fetch_result = fetch_spec(url, existing_etag, existing_last_modified)

        if fetch_result["outcome"] == "not_modified":
            summary["not_modified"] += 1
            if existing:
                observed_entry = dict(existing)
                _reactivate_existing_entry(observed_entry)
                observed_entry["last_checked_at"] = utc_now()
                observations.append({
                    "source": source,
                    "entry": observed_entry,
                    "existing_entry": existing,
                })
                _ensure_existing_tracker(existing_tracker, existing)["healthy"] = True
            logger.info(f"Skipped (ETag match): {url}")
            continue

        if fetch_result["outcome"] == "failed":
            summary["failed"] += 1
            failed_urls.append(url)
            if existing:
                _ensure_existing_tracker(existing_tracker, existing)["failure_errors"].append(
                    fetch_result["error"] or "Fetch failed"
                )
            continue

        content = fetch_result["content"]
        parsed = parse_spec(content, url)

        if not parsed:
            rejected_urls.append(url)
            summary["rejected"] += 1
            if existing:
                tracker = _ensure_existing_tracker(existing_tracker, existing)
                tracker["invalid"] = True
                tracker["discovered"] = True
            continue

        entry = build_entry(source, parsed, content, existing)
        if fetch_result.get("etag"):
            entry["etag"] = fetch_result["etag"]
        if fetch_result.get("last_modified"):
            entry["last_modified"] = fetch_result["last_modified"]
        entry["last_checked_at"] = entry["fetched_at"]
        summary["fetched"] += 1

        if existing:
            tracker = _ensure_existing_tracker(existing_tracker, existing)
            tracker["healthy"] = True
            old_semantic_hash = existing.get("semantic_hash", existing.get("hash"))
            old_content_hash = existing.get("content_hash", existing.get("hash"))
            if entry["semantic_hash"] == old_semantic_hash and entry["content_hash"] != old_content_hash:
                summary["format_only_changes"] += 1

        observations.append({
            "source": source,
            "entry": entry,
            "existing_entry": existing,
        })
        time.sleep(1)

    clusters = {}
    for observation in observations:
        semantic_hash = observation["entry"].get("semantic_hash", observation["entry"].get("hash"))
        clusters.setdefault(semantic_hash, []).append(observation)

    final_catalog = {}
    matched_existing_ids = set()

    for cluster in clusters.values():
        merged_entry, existing_match = _merge_cluster(cluster, existing_by_semantic)
        if merged_entry["source_count"] > 1:
            summary["duplicates_collapsed"] += merged_entry["source_count"] - 1

        if existing_match:
            matched_existing_ids.add(existing_match["id"])
            old_semantic_hash = existing_match.get("semantic_hash", existing_match.get("hash"))
            if merged_entry["semantic_hash"] != old_semantic_hash:
                updated_entries.append(merged_entry["id"])
            else:
                unchanged_entries.append(merged_entry["id"])
        else:
            new_entries.append(merged_entry["id"])

        final_catalog[merged_entry["id"]] = merged_entry

    final_semantic_hashes = {
        entry.get("semantic_hash", entry.get("hash"))
        for entry in final_catalog.values()
    }

    for existing_id, existing_entry in catalog.items():
        if existing_id in matched_existing_ids:
            continue
        if existing_entry.get("semantic_hash", existing_entry.get("hash")) in final_semantic_hashes:
            continue

        entry_copy = dict(existing_entry)
        tracker = existing_tracker.get(existing_id, {
            "discovered": False,
            "healthy": False,
            "invalid": False,
            "failure_errors": [],
        })

        if tracker["healthy"]:
            continue

        entry_copy["last_checked_at"] = utc_now()

        if tracker["invalid"]:
            entry_copy["status"] = "invalid"
            entry_copy["last_error"] = "Validation failed"
        elif tracker["failure_errors"]:
            _mark_fetch_failure(entry_copy, tracker["failure_errors"][-1])
        elif not tracker["discovered"]:
            entry_copy["status"] = "stale"
            entry_copy["stale_reason"] = "not_discovered"

        final_catalog[existing_id] = entry_copy

    summary["new"] = len(new_entries)
    summary["updated"] = len(updated_entries)
    summary["unchanged"] = len(unchanged_entries)
    save_catalog(final_catalog, catalog_path)
    run_report = _build_run_report(final_catalog, summary, failed_urls, rejected_urls, run_report_path)
    save_run_report(run_report, run_report_path)
    print_summary(final_catalog, summary, failed_urls, rejected_urls)

    logger.info("Crawl run complete")


def run_polling_loop(
    catalog_path: str = CATALOG_FILE,
    run_report_path: str = RUN_REPORT_FILE,
    interval_hours: float = POLLING_INTERVAL_HOURS,
    max_runs: int | None = None,
):
    """Run the crawler repeatedly for cron-like local polling."""
    runs_completed = 0
    interval_seconds = interval_hours * 60 * 60

    while max_runs is None or runs_completed < max_runs:
        run_crawl(catalog_path, run_report_path)
        runs_completed += 1

        if max_runs is not None and runs_completed >= max_runs:
            break

        logger.info(f"Sleeping {interval_hours} hour(s) before next crawl run")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover, version, and catalog public OpenAPI specs.")
    parser.add_argument("--watch", action="store_true", help="Run continuously with a polling interval.")
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=POLLING_INTERVAL_HOURS,
        help="Polling interval used with --watch. Defaults to POLLING_INTERVAL_HOURS or 24.",
    )
    args = parser.parse_args()

    if args.watch:
        run_polling_loop(interval_hours=args.interval_hours)
    else:
        run_crawl()
