import hashlib
from datetime import datetime, timezone

from src.logger import get_logger

logger = get_logger("versioner")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_hash(content: str) -> str:
    """Backward-compatible helper for hashing raw content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_semantic_hash(normalized_spec: str) -> str:
    """Hash a canonicalized parsed spec to ignore formatting-only changes."""
    return hashlib.sha256(normalized_spec.encode("utf-8")).hexdigest()


def _compute_path_diff(old_paths: list[str], new_paths: list[str]) -> dict:
    old_set = set(old_paths)
    new_set = set(new_paths)
    added_paths = sorted(new_set - old_set)
    removed_paths = sorted(old_set - new_set)
    return {
        "added_paths": added_paths,
        "removed_paths": removed_paths,
        "added_count": len(added_paths),
        "removed_count": len(removed_paths),
        "net_paths_delta": len(added_paths) - len(removed_paths),
    }


def build_entry(source: dict, parsed: dict, content: str, existing_entry: dict | None = None) -> dict:
    """Build or update a catalog entry for a spec."""
    now = utc_now()
    content_hash = compute_hash(content)
    semantic_hash = compute_semantic_hash(parsed["normalized_spec"])
    version = parsed["latest_version"]

    canonical_source_url = existing_entry.get("source_url", source["source_url"]) if existing_entry else source["source_url"]
    entry = {
        "id": existing_entry.get("id", generate_id(canonical_source_url)) if existing_entry else generate_id(canonical_source_url),
        "source_url": canonical_source_url,
        "sources": list(existing_entry.get("sources", [canonical_source_url])) if existing_entry else [canonical_source_url],
        "source_count": len(existing_entry.get("sources", [canonical_source_url])) if existing_entry else 1,
        "title": parsed["title"],
        "oas_version": parsed["oas_version"],
        "latest_version": version,
        "paths_count": parsed["paths_count"],
        "path_keys": parsed["path_keys"],
        "servers": parsed["servers"],
        "tags": parsed["tags"],
        "description": parsed["description"],
        "validation_notes": parsed["validation_notes"],
        "confidence_score": parsed["confidence_score"],
        "fetched_at": now,
        "status": "active",
        "hash": semantic_hash,
        "semantic_hash": semantic_hash,
        "content_hash": content_hash,
        "history": [],
        "failure_count": 0,
    }

    if existing_entry:
        old_semantic_hash = existing_entry.get("semantic_hash", existing_entry.get("hash"))
        old_content_hash = existing_entry.get("content_hash", existing_entry.get("hash"))
        old_version = existing_entry.get("latest_version")
        old_paths = existing_entry.get("paths_count", 0)
        old_path_keys = existing_entry.get("path_keys", [])
        history = list(existing_entry.get("history", []))

        if semantic_hash != old_semantic_hash:
            path_diff = _compute_path_diff(old_path_keys, parsed["path_keys"])
            logger.info(
                f"Update detected for {parsed['title']}: {old_version} -> {version}, "
                f"+{path_diff['added_count']} / -{path_diff['removed_count']}"
            )

            history.append({
                "version": old_version,
                "replaced_by_version": version,
                "content_hash": old_content_hash,
                "semantic_hash": old_semantic_hash,
                "paths_count": old_paths,
                "recorded_at": existing_entry.get("fetched_at"),
                "paths_delta": path_diff["net_paths_delta"],
                "diff": path_diff,
            })
        else:
            logger.info(f"No semantic change detected for {parsed['title']}")

        entry["history"] = history

    return entry


def generate_id(source_url: str) -> str:
    """Generate a readable ID from the source URL."""
    url = source_url.replace("https://raw.githubusercontent.com/", "github:")
    url = url.replace("https://", "").replace("http://", "")
    return url.strip("/")
