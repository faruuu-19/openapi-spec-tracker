import json
from datetime import date, datetime
from typing import Any

import yaml

from src.logger import get_logger

logger = get_logger("parser")


def _coerce_nonempty_string(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_swagger_servers(data: dict) -> list[str]:
    host = _coerce_nonempty_string(data.get("host"))
    if not host:
        return []

    base_path = data.get("basePath", "")
    if not isinstance(base_path, str):
        base_path = ""
    if base_path and not base_path.startswith("/"):
        base_path = f"/{base_path}"

    schemes = data.get("schemes")
    if not isinstance(schemes, list) or not schemes:
        schemes = ["https"]

    servers = []
    for scheme in schemes:
        scheme_text = _coerce_nonempty_string(scheme)
        if scheme_text:
            servers.append(f"{scheme_text}://{host}{base_path}")
    return servers


def _extract_servers(data: dict, oas_version: str) -> list[str]:
    if oas_version.startswith("2."):
        return _extract_swagger_servers(data)

    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return []

    return sorted({
        url
        for url in (_coerce_nonempty_string(server.get("url")) for server in servers if isinstance(server, dict))
        if url
    })


def _extract_paths(data: dict) -> list[str] | None:
    paths = data.get("paths", {})
    if paths is None:
        return []
    if not isinstance(paths, dict):
        return None

    path_keys = []
    for path_key in paths.keys():
        if not isinstance(path_key, str):
            return None
        normalized = path_key.strip()
        if normalized.startswith("/"):
            path_keys.append(normalized)

    return sorted(set(path_keys))


def _canonicalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize_for_hash(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, list):
        return [_canonicalize_for_hash(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _build_validation_notes(
    source_url: str,
    oas_version: str,
    description: str,
    servers: list[str],
    tags: list[str],
    path_keys: list[str],
) -> tuple[list[str], float]:
    notes = [f"Valid {'OpenAPI' if oas_version.startswith('3.') else 'Swagger'} document detected"]
    score = 0.7

    if path_keys:
        notes.append(f"Discovered {len(path_keys)} path(s)")
        score += 0.1
    else:
        notes.append("No paths declared")

    if description:
        notes.append("info.description is populated")
        score += 0.05
    else:
        notes.append("No info.description provided")

    if servers:
        notes.append(f"Resolved {len(servers)} server URL(s)")
        score += 0.05
    else:
        notes.append("No explicit servers declared")

    if tags:
        notes.append(f"Discovered {len(tags)} top-level tag(s)")
        score += 0.05
    else:
        notes.append("No top-level tags declared")

    if oas_version.startswith("2.") and servers:
        notes.append("Swagger 2.x server URLs inferred from host/basePath/schemes")

    if "/.speakeasy/" in source_url or "/Generated/" in source_url:
        notes.append("Source path suggests a generated artifact")
        score -= 0.05

    return notes, round(max(0.0, min(score, 1.0)), 2)


def parse_spec(content: str, source_url: str) -> dict | None:
    """Parse a credible OpenAPI/Swagger spec and extract normalized metadata."""
    try:
        data = json.loads(content) if source_url.endswith(".json") else yaml.safe_load(content)
    except Exception as exc:
        logger.error(f"Failed to parse spec at {source_url}: {exc}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"Invalid spec structure at {source_url}")
        return None

    openapi_version = _coerce_nonempty_string(data.get("openapi"))
    swagger_version = _coerce_nonempty_string(data.get("swagger"))

    if openapi_version:
        if not openapi_version.startswith("3."):
            logger.warning(f"Unsupported OpenAPI version at {source_url}: {openapi_version}")
            return None
        oas_version = openapi_version
    elif swagger_version:
        if not swagger_version.startswith("2."):
            logger.warning(f"Unsupported Swagger version at {source_url}: {swagger_version}")
            return None
        oas_version = swagger_version
    else:
        logger.warning(f"Missing OpenAPI/Swagger version at {source_url}")
        return None

    info = data.get("info")
    if not isinstance(info, dict):
        logger.warning(f"Missing info object at {source_url}")
        return None

    title = _coerce_nonempty_string(info.get("title"))
    version = _coerce_nonempty_string(info.get("version"))
    if not title or not version:
        logger.warning(f"Missing required info.title/info.version at {source_url}")
        return None

    path_keys = _extract_paths(data)
    if path_keys is None:
        logger.warning(f"Invalid paths object at {source_url}")
        return None

    description = info.get("description", "")
    if not isinstance(description, str):
        description = str(description)
    description = description.strip()

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tag_names = sorted({
        tag_name
        for tag_name in (_coerce_nonempty_string(tag.get("name")) for tag in tags if isinstance(tag, dict))
        if tag_name
    })

    servers = _extract_servers(data, oas_version)
    validation_notes, confidence_score = _build_validation_notes(
        source_url,
        oas_version,
        description,
        servers,
        tag_names,
        path_keys,
    )

    normalized_spec = json.dumps(
        _canonicalize_for_hash(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    return {
        "title": title,
        "oas_version": oas_version,
        "latest_version": version,
        "description": description,
        "paths_count": len(path_keys),
        "path_keys": path_keys,
        "servers": servers,
        "tags": tag_names,
        "normalized_spec": normalized_spec,
        "validation_notes": validation_notes,
        "confidence_score": confidence_score,
    }
