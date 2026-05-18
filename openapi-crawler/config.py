import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

GITHUB_SEARCH_QUERIES = [
    "filename:openapi.yaml",
    "filename:openapi.json", 
    "filename:swagger.yaml",
    "filename:swagger.json",
    "extension:json openapi",
    "extension:json swagger",
    "path:openapi extension:json",
]

SEED_REPO_URLS = [
    "https://github.com/stripe/openapi",
    "https://github.com/twilio/twilio-oai",
    "https://github.com/github/rest-api-description",
    "https://github.com/kubernetes/kubernetes",
]

SEED_SPEC_PATHS = [
    "openapi.yaml",
    "openapi.json",
    "swagger.yaml",
    "swagger.json",
    "openapi/spec3.yaml",
    "spec/yaml/twilio_api_v2010.yaml",
    "descriptions/api.github.com/api.github.com.yaml",
    "api/openapi-spec/swagger.json",
]

SEED_URLS = [
    "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml",
    "https://raw.githubusercontent.com/twilio/twilio-oai/main/spec/yaml/twilio_api_v2010.yaml",
    "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.yaml",
    "https://raw.githubusercontent.com/kubernetes/kubernetes/master/api/openapi-spec/swagger.json",
    "https://api.apis.guru/v2/specs/twitter.com/2.0/openapi.yaml",
]

MAX_RESULTS_PER_QUERY = _int_env("MAX_RESULTS_PER_QUERY", 100)  # how many specs to fetch per search query
CRAWL_LIMIT = _int_env("CRAWL_LIMIT", 50)             # total specs limit across all queries
MAX_SEED_REPO_CANDIDATES = _int_env("MAX_SEED_REPO_CANDIDATES", 20)
FETCH_RETRIES = _int_env("FETCH_RETRIES", 3)
REQUEST_TIMEOUT = _int_env("REQUEST_TIMEOUT", 10)
STALE_AFTER_FAILURES = 3
POLLING_INTERVAL_HOURS = float(os.getenv("POLLING_INTERVAL_HOURS", "24"))
CATALOG_FILE = os.getenv("CATALOG_FILE", "catalog.json")
RUN_REPORT_FILE = os.getenv("RUN_REPORT_FILE", "run_report.json")
LOG_FILE = os.getenv("LOG_FILE", "logs/crawler.log")

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
