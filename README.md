# OpenAPI Spec Crawler

A system for discovering, validating, versioning, and cataloging public OpenAPI/Swagger specifications from across the web using GitHub Code Search as the primary discovery source.

Built for the APIMatic AI Engineering Intern screening task.

---

# Repository Layout

```text
API_MATIC/
├── openapi-crawler/                  # Python crawler + catalog/versioning pipeline
└── OpenAPI-Dashboard/
    └── OpenAPI-Dashboard/            # frontend dashboard + backend API
```

The crawler is the core backend system responsible for:

- discovery
- validation
- version tracking
- diff generation
- catalog persistence
- reporting

The dashboard sits on top of that pipeline so crawl state, catalog entries, version history, and operational metrics can be visualized interactively instead of only through JSON files.

---

# Quick Start

## Requirements

- Python 3.10+
- Node.js + pnpm
- GitHub Personal Access Token (recommended for higher GitHub API rate limits)

---

# Running The Core Crawler

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configure GitHub token

Create a `.env` file:

```env
GITHUB_TOKEN=your_token_here
```

---

## Run the crawler

```bash
python main.py
```

---

## Run tests

```bash
pytest -q
```

---

## Run the demo update flow

```bash
python demo_update.py
```

---

## Generate deterministic proof artifacts

```bash
python generate_demo_artifacts.py
```

This writes:

- `artifacts/catalog_before.json`
- `artifacts/catalog_after.json`
- `artifacts/run_report_after.json`

---

# Running The Full Dashboard Stack

The dashboard runs separately from the crawler itself.

You need two terminals:

- Terminal 1 → backend API
- Terminal 2 → frontend dashboard

The API server bridges the React dashboard to the Python crawler workspace.

---

## Terminal 1 — Backend API

```powershell
cd "API_MATIC/OpenAPI-Dashboard/OpenAPI-Dashboard"

$env:CRAWLER_DIR="API_MATIC/openapi-crawler"

corepack pnpm --filter @workspace/api-server run dev:local
```

Expected output:

```text
Crawler API listening on http://localhost:3001
```

---

## Terminal 2 — Frontend Dashboard

```powershell
cd "API_MATIC/OpenAPI-Dashboard/OpenAPI-Dashboard"

corepack pnpm --filter @workspace/openapi-crawler-dashboard run dev
```

Vite will print a local URL, typically:

```text
http://localhost:5173
```

Open it in the browser and click:

```text
Run Crawler
```

---

## Verify Backend Connectivity

Before running a crawl, verify the frontend can reach the backend:

```powershell
Invoke-RestMethod http://localhost:3001/api/crawler/state
```

Expected response:

```json
{
  "crawler_dir": "...",
  "stats": {},
  "catalog": [],
  "running": false
}
```

---

## Smoke Test Mode

Real crawls can take time and may hit GitHub rate limits without a token configured.

For a quick no-risk smoke test:

```powershell
$env:CRAWL_LIMIT="0"
```

Then click:

```text
Run Crawler
```

The pipeline should execute almost immediately without performing a real external crawl.

---

# Architecture

```text
Crawler -> Parser -> Versioner -> Catalog
```

| Module | Responsibility |
| --- | --- |
| `src/crawler.py` | discovery, GitHub search, fetch pipeline, retry/backoff |
| `src/parser.py` | strict OpenAPI/Swagger validation + normalization |
| `src/versioner.py` | content hashing, semantic hashing, history tracking, diffs |
| `src/catalog.py` | catalog persistence + run reports |
| `src/logger.py` | structured JSON logging with run IDs |
| `main.py` | orchestration, deduplication, stale transitions |

---

# Requirement Coverage

| Requirement | Status |
| --- | --- |
| GitHub Code Search discovery | DONE |
| Configurable seed sources | DONE |
| OpenAPI 3.x support | DONE |
| Swagger 2.x support | DONE |
| YAML support | DONE |
| JSON support | DONE |
| Metadata extraction | DONE |
| JSON catalog persistence | DONE |
| Version tracking | DONE |
| Content hashing | DONE |
| Semantic hashing | DONE |
| Immutable history | DONE |
| Path-level diffs | DONE |
| ETag incremental fetch | DONE |
| Retry/backoff handling | DONE |
| Stale-state transitions | DONE |
| Structured JSON logs | DONE |
| Run reports | DONE |
| Tests | DONE |
| Deterministic demo artifacts | DONE |

---
Beyond The Requirements
The following were not required by the task but were added to improve correctness and real-world usefulness.
Semantic hashing — The task required content hashing. Semantic hashing was added on top so formatting-only YAML changes are not treated as real API updates. The system distinguishes three outcomes: real API change, formatting-only change, and no change.
Exact path-level diffs — The task required version tracking. Diffs here are computed from actual endpoint path sets, not just path counts, so the catalog records exactly which endpoints were added or removed between versions.
Duplicate collapse — Public specs are frequently mirrored across repositories. The crawler collapses semantically identical specs into one canonical entry rather than creating duplicate catalog records.
Confidence scoring — Each catalog entry carries a confidence_score and validation_notes so the trustworthiness of each entry is machine-readable, not just implied.
Stale-state transitions — Specs that repeatedly fail fetching, disappear from discovery, or regress from valid to invalid are transitioned to stale or invalid rather than silently dropped.
Interactive dashboard — A React frontend and Node.js backend API were built on top of the crawler pipeline so catalog state, version history, and run metrics are browsable interactively rather than only through raw JSON files.
Deterministic proof artifacts — generate_demo_artifacts.py produces a reproducible before/after catalog pair demonstrating all the harder behaviors (semantic updates, history, diffs, stale transitions, duplicate collapse) without requiring a live crawl.

# What The System Does

## 1. Discovery

The crawler searches GitHub for likely OpenAPI specifications using GitHub Code Search plus configurable seed URLs/repositories.

Queries include:

```text
filename:openapi.yaml
filename:openapi.json
filename:swagger.yaml
filename:swagger.json
extension:json openapi
extension:json swagger
```

The crawl limit is configurable so runs remain deterministic and API-friendly.

---

## 2. Validation

GitHub search returns plenty of noisy candidates, so every fetched document is validated before entering the catalog.

A document must:

- parse as YAML or JSON
- contain `openapi: 3.x` or `swagger: 2.x`
- contain a valid `info` object
- contain non-empty `info.title`
- contain non-empty `info.version`

This prevents unrelated YAML/JSON files from polluting the catalog.

---

## 3. Metadata Extraction

The parser extracts normalized metadata including:

- title
- version
- description
- servers
- tags
- path count
- full endpoint path list

Example:

```json
{
  "title": "Stripe API",
  "latest_version": "2024-06-20",
  "paths_count": 312
}
```

---

# Version Tracking

The crawler tracks changes using:

- `info.version`
- raw content hashing
- normalized semantic hashing

---

## Why semantic hashing?

A formatting-only YAML change should not count as a real API update.

Example:

```yaml
paths:
  /users:
    get: {}
```

vs

```yaml
paths: { /users: { get: {} } }
```

Same API semantics.

Different raw file content.

The system therefore computes both:

| Hash | Purpose |
| --- | --- |
| `content_hash` | detects any raw file change |
| `semantic_hash` | detects meaningful API changes only |

---

## Immutable History

Every semantic update stores a history snapshot.

Example:

```json
{
  "version": "1.0.0",
  "replaced_by_version": "2.0.0",
  "diff": {
    "added_paths": ["/teams"],
    "removed_paths": ["/orders"]
  }
}
```

That diff is computed from actual endpoint paths rather than path counts alone.

---

# Duplicate Collapse

Public specs are often mirrored across multiple repositories.

The crawler collapses semantically identical specs into one canonical catalog entry while preserving all discovered source URLs.

Example:

```json
{
  "source_count": 2,
  "sources": [
    "primary-source",
    "mirror-source"
  ]
}
```

---

# Freshness Model

Each fetch produces one of the following outcomes:

| State | Meaning |
| --- | --- |
| `fetched` | content downloaded and evaluated |
| `not_modified` | ETag matched existing state |
| `failed` | fetch exhausted retries |
| `rejected` | fetched successfully but failed validation |

State handling includes:

- ETag-based incremental fetch support
- retry/backoff behavior
- stale-state transitions after repeated failures
- invalidation of previously valid specs that now fail validation

---

# Quality Signals

Each catalog entry includes:

- `confidence_score`
- `validation_notes`

Examples:

```json
{
  "confidence_score": 0.95,
  "validation_notes": [
    "Valid OpenAPI document detected",
    "Resolved 3 server URL(s)"
  ]
}
```

---

# Catalog Schema

The catalog includes all required task fields plus operational metadata useful for long-term tracking.

Example:

```json
{
  "id": "github:stripe/openapi/master/openapi/spec3.yaml",
  "source_url": "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml",
  "title": "Stripe API",
  "oas_version": "3.0.0",
  "latest_version": "2024-06-20",
  "paths_count": 312,
  "status": "active",
  "history": []
}
```

Additional operational fields include:

- `semantic_hash`
- `content_hash`
- `etag`
- `failure_count`
- `path_keys`
- `validation_notes`
- `sources`
- `source_count`

---

# Proof Artifacts

The repository includes deterministic artifacts demonstrating the more difficult crawler behaviors:

- semantic updates
- immutable history
- path-level diffs
- stale-state transitions
- duplicate collapse
- operational metrics

Artifacts:

- `artifacts/catalog_before.json`
- `artifacts/catalog_after.json`
- `artifacts/run_report_after.json`

---

# Logging & Reporting

The crawler emits:

- structured JSON logs
- shared run IDs
- machine-readable run reports

Example metrics:

```json
{
  "updated": 3,
  "unchanged": 12,
  "stale": 1,
  "duplicates_collapsed": 2
}
```

---

# Design Decisions

## Why strict validation?

GitHub search returns noisy results. Rejecting near-matches early keeps the catalog trustworthy.

---

## Why store full path keys?

Path-level diffs require exact endpoint history rather than only aggregate counts.

---

## Why support seed repositories?

GitHub search is not perfectly stable. Reliable seeds help bootstrap deterministic crawls.

---

## Why JSON instead of a database?

The task scope favors portability and transparency over large-scale query optimization.

---

# Known Tradeoffs

- GitHub search results are not perfectly stable
- repo seed expansion uses heuristic path guesses
- some generated seed candidates may 404
- remote `$ref` dereferencing is intentionally out of scope
- JSON catalogs are not ideal for extremely large-scale crawls

---

# Suggested Loom Demo Flow

1. Run:

```bash
python main.py
```

2. Open:

```text
catalog.json
```

3. Show:
- valid OpenAPI entries
- metadata extraction
- version tracking

4. Run:

```bash
python generate_demo_artifacts.py
```

5. Open:
- `catalog_before.json`
- `catalog_after.json`

6. Highlight:
- immutable history
- path-level diffs
- stale records
- duplicate collapse

7. Open:

```text
run_report_after.json
```

8. Run:

```bash
pytest -q
```

---

# Final Notes

This project intentionally prioritizes:

- correctness
- deterministic behavior
- operational clarity
- maintainability

over maximizing crawler breadth.

The goal was not to build a giant internet crawler. The goal was to build a reliable OpenAPI cataloging pipeline that can track API specs as evolving assets over time.