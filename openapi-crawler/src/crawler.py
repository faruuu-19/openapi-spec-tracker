import time

import requests

from config import (
    CRAWL_LIMIT,
    FETCH_RETRIES,
    GITHUB_SEARCH_QUERIES,
    HEADERS,
    MAX_SEED_REPO_CANDIDATES,
    MAX_RESULTS_PER_QUERY,
    REQUEST_TIMEOUT,
    SEED_REPO_URLS,
    SEED_SPEC_PATHS,
    SEED_URLS,
)
from src.logger import get_logger

logger = get_logger("crawler")

VALID_EXTENSIONS = (".yaml", ".yml", ".json")
DEFAULT_BRANCH_CANDIDATES = ("main", "master")


def search_github(query: str, max_results: int = 30) -> list[dict]:
    """Search GitHub code search API for OpenAPI spec files."""
    results = []
    page = 1
    per_page = min(max_results, 30)

    while len(results) < max_results:
        url = f"https://api.github.com/search/code?q={query}&per_page={per_page}&page={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error(f"GitHub search request failed for {query}: {exc}")
            break

        if response.status_code == 403:
            logger.warning("Rate limit hit, sleeping 60s...")
            time.sleep(60)
            continue

        if response.status_code != 200:
            logger.error(f"GitHub search failed: {response.status_code} for query: {query}")
            break

        data = response.json()
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            path = item["path"]
            if not path.lower().endswith(VALID_EXTENSIONS):
                logger.warning(f"Skipping non-spec file: {path}")
                continue

            branch = item["repository"].get("default_branch") or "main"
            raw_url = f"https://raw.githubusercontent.com/{item['repository']['full_name']}/{branch}/{path}"
            results.append({
                "source_url": raw_url,
                "repo": item["repository"]["full_name"],
                "path": path,
            })

        page += 1
        time.sleep(2)

        if len(items) < per_page:
            break

    return results[:max_results]


def _parse_github_repo_url(url: str) -> str | None:
    prefix = "https://github.com/"
    if not url.startswith(prefix):
        return None

    parts = url.removeprefix(prefix).strip("/").split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _seed_repo_sources() -> list[dict]:
    sources = []
    for repo_url in SEED_REPO_URLS:
        repo = _parse_github_repo_url(repo_url)
        if not repo:
            logger.warning(f"Skipping invalid GitHub seed repo URL: {repo_url}")
            continue

        for branch in DEFAULT_BRANCH_CANDIDATES:
            for path in SEED_SPEC_PATHS:
                sources.append({
                    "source_url": f"https://raw.githubusercontent.com/{repo}/{branch}/{path}",
                    "repo": repo,
                    "path": path,
                    "seed_repo_url": repo_url,
                })
    return sources


def fetch_spec(url: str, existing_etag: str = None, existing_last_modified: str = None) -> dict:
    """Fetch a spec and return an explicit outcome: fetched, not_modified, or failed."""
    headers = {**HEADERS, "Accept": "application/vnd.github.v3.raw"}
    if existing_etag:
        headers["If-None-Match"] = existing_etag
    if existing_last_modified:
        headers["If-Modified-Since"] = existing_last_modified

    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 304:
                logger.info(f"Not modified (conditional request): {url}")
                return {
                    "outcome": "not_modified",
                    "content": None,
                    "etag": existing_etag,
                    "last_modified": existing_last_modified,
                    "status_code": 304,
                    "error": None,
                }

            if response.status_code == 200:
                return {
                    "outcome": "fetched",
                    "content": response.text,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "status_code": 200,
                    "error": None,
                }

            if response.status_code in (429, 403) and attempt < FETCH_RETRIES:
                wait = 2 ** attempt * 10
                logger.warning(
                    f"Rate limited on {url}, retrying in {wait}s (attempt {attempt}/{FETCH_RETRIES})"
                )
                time.sleep(wait)
                continue

            logger.warning(f"Failed to fetch {url}: {response.status_code}")
            return {
                "outcome": "failed",
                "content": None,
                "etag": None,
                "last_modified": None,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }

        except Exception as exc:
            if attempt < FETCH_RETRIES:
                wait = 2 ** attempt * 5
                logger.error(
                    f"Exception fetching {url} (attempt {attempt}/{FETCH_RETRIES}): {exc}, retrying in {wait}s"
                )
                time.sleep(wait)
                continue

            logger.error(f"All retries exhausted for {url}: {exc}")
            return {
                "outcome": "failed",
                "content": None,
                "etag": None,
                "last_modified": None,
                "status_code": None,
                "error": str(exc),
            }

    logger.error(f"All retries exhausted for {url}")
    return {
        "outcome": "failed",
        "content": None,
        "etag": None,
        "last_modified": None,
        "status_code": None,
        "error": "Retries exhausted",
    }


def discover_all_specs() -> list[dict]:
    """Run seeded URLs first, then GitHub search until the crawl limit is reached."""
    all_sources = []
    seen_urls = set()

    for url in SEED_URLS:
        if len(all_sources) >= CRAWL_LIMIT:
            break
        if url not in seen_urls:
            seen_urls.add(url)
            all_sources.append({"source_url": url, "repo": "seeded", "path": url})

    repo_seed_count = 0
    for source in _seed_repo_sources():
        if len(all_sources) >= CRAWL_LIMIT or repo_seed_count >= MAX_SEED_REPO_CANDIDATES:
            break
        if source["source_url"] not in seen_urls:
            seen_urls.add(source["source_url"])
            all_sources.append(source)
            repo_seed_count += 1

    for query in GITHUB_SEARCH_QUERIES:
        if len(all_sources) >= CRAWL_LIMIT:
            break

        remaining = CRAWL_LIMIT - len(all_sources)
        query_limit = min(MAX_RESULTS_PER_QUERY, remaining)
        logger.info(f"Searching GitHub: {query}")
        results = search_github(query, max_results=query_limit)

        for result in results:
            if len(all_sources) >= CRAWL_LIMIT:
                break
            if result["source_url"] not in seen_urls:
                seen_urls.add(result["source_url"])
                all_sources.append(result)

    logger.info(f"Total sources discovered: {len(all_sources)}")
    return all_sources
