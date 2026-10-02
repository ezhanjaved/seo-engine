"""Google Search Console Search Analytics retrieval.

This module only retrieves data. It contains no analysis or interpretation
logic; see ``methodologies/`` for how the returned data should be read.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
VALID_DIMENSIONS = ("date", "page", "query", "country", "device")
VALID_FILTER_OPERATORS = (
    "equals",
    "notEquals",
    "contains",
    "notContains",
    "includingRegex",
    "excludingRegex",
)
MAX_ROW_LIMIT = 25000  # Search Analytics API maximum per request.

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITES_CONFIG = REPO_ROOT / "config" / "sites.yaml"


def resolve_property(site: str) -> str:
    """Resolve a site alias to its GSC property identifier.

    ``site`` may be an alias defined in the sites config, or an exact GSC
    property (``sc-domain:example.com`` or ``https://www.example.com/``),
    which is returned unchanged.
    """
    if site.startswith(("sc-domain:", "http://", "https://")):
        return site

    load_dotenv(REPO_ROOT / ".env")
    config_path = Path(os.environ.get("SEO_ENGINE_SITES_CONFIG") or DEFAULT_SITES_CONFIG)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Sites config not found at {config_path}. "
            "Copy config/sites.example.yaml to config/sites.yaml."
        )

    with config_path.open(encoding="utf-8") as f:
        sites = (yaml.safe_load(f) or {}).get("sites") or {}

    if site not in sites:
        known = ", ".join(sorted(sites)) or "(none)"
        raise ValueError(f"Unknown site alias '{site}'. Known aliases: {known}")
    gsc_property = (sites[site] or {}).get("gsc_property")
    if not gsc_property:
        raise ValueError(f"Site alias '{site}' has no gsc_property in {config_path}")
    return gsc_property


def _build_service() -> Any:
    """Build an authenticated Search Console API client from a service account."""
    load_dotenv(REPO_ROOT / ".env")
    key_file = os.environ.get("GSC_SERVICE_ACCOUNT_FILE")
    if not key_file:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_FILE is not set. See .env.example.")

    key_path = Path(key_file)
    if not key_path.is_absolute():
        key_path = REPO_ROOT / key_path
    if not key_path.is_file():
        raise FileNotFoundError(f"Service account key not found at {key_path}")

    credentials = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def query_search_analytics(
    site: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    filters: list[dict[str, str]] | None = None,
    row_limit: int = 1000,
) -> dict[str, Any]:
    """Retrieve GSC performance data for a site.

    Args:
        site: Site alias from the sites config, or an exact GSC property.
        start_date: Inclusive start date, ``YYYY-MM-DD``.
        end_date: Inclusive end date, ``YYYY-MM-DD``.
        dimensions: Dimensions to group by, any of ``VALID_DIMENSIONS``.
            Omit for a single aggregated row.
        filters: Dimension filters, all of which must match (AND). Each is
            ``{"dimension": ..., "operator": ..., "expression": ...}`` and is
            passed to the API as-is. Operators: ``equals``, ``notEquals``,
            ``contains``, ``notContains``, ``includingRegex``, ``excludingRegex``.
        row_limit: Maximum rows to return, 1 to 25000.

    Returns:
        A JSON-serializable dict with ``request`` (the resolved inputs),
        ``row_count`` and ``rows``. Each row has one key per requested
        dimension, plus ``clicks``, ``impressions``, ``ctr`` and ``position``.
        Row order is the API's (clicks descending, or date ascending when
        grouping by date alone).

    Raises:
        ValueError: An input is invalid or the site alias is unknown.
        FileNotFoundError: The sites config or service account key is missing.
        RuntimeError: ``GSC_SERVICE_ACCOUNT_FILE`` is not set.
    """
    dimensions = list(dimensions or [])
    filters = list(filters or [])

    invalid = [d for d in dimensions if d not in VALID_DIMENSIONS]
    if invalid:
        raise ValueError(f"Invalid dimensions {invalid}. Valid: {list(VALID_DIMENSIONS)}")
    if len(set(dimensions)) != len(dimensions):
        raise ValueError(f"Duplicate dimensions: {dimensions}")
    for f in filters:
        if not isinstance(f, dict) or set(f) != {"dimension", "operator", "expression"}:
            raise ValueError(
                f"Malformed filter {f!r}. Expected keys: dimension, operator, expression"
            )
        if f["dimension"] not in VALID_DIMENSIONS:
            raise ValueError(
                f"Invalid filter dimension '{f['dimension']}'. Valid: {list(VALID_DIMENSIONS)}"
            )
        if f["operator"] not in VALID_FILTER_OPERATORS:
            raise ValueError(
                f"Invalid filter operator '{f['operator']}'. Valid: {list(VALID_FILTER_OPERATORS)}"
            )
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        try:
            # Round-trip so only the strict YYYY-MM-DD form the API accepts passes.
            ok = date.fromisoformat(value).isoformat() == value
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError(f"{name} must be a valid YYYY-MM-DD date, got {value!r}")
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    if isinstance(row_limit, bool) or not isinstance(row_limit, int):
        raise ValueError(f"row_limit must be an integer, got {row_limit!r}")
    if not 1 <= row_limit <= MAX_ROW_LIMIT:
        raise ValueError(f"row_limit must be between 1 and {MAX_ROW_LIMIT}")

    gsc_property = resolve_property(site)

    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    if filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]

    response = (
        _build_service()
        .searchanalytics()
        .query(siteUrl=gsc_property, body=body)
        .execute()
    )

    rows = [
        {
            **dict(zip(dimensions, row.get("keys", []))),
            "clicks": row["clicks"],
            "impressions": row["impressions"],
            "ctr": row["ctr"],
            "position": row["position"],
        }
        for row in response.get("rows", [])
    ]

    return {
        "request": {
            "site": site,
            "property": gsc_property,
            "start_date": start_date,
            "end_date": end_date,
            "dimensions": dimensions,
            "filters": filters,
            "row_limit": row_limit,
        },
        "row_count": len(rows),
        "rows": rows,
    }
