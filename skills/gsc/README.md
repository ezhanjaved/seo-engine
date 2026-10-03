# GSC skill

Retrieves Google Search Console performance data (Search Analytics API). It does not analyse or interpret anything; see `methodologies/gsc_monitoring.md` for that.

## Usage

Run from the repository root.

### Command line

```bash
python -m skills.gsc \
  --site example \
  --start-date 2026-07-01 \
  --end-date 2026-09-30 \
  --dimensions date device \
  --filter country equals gbr \
  --row-limit 1000
```

| Flag | Required | Notes |
| --- | --- | --- |
| `--site` | yes | Alias from `config/sites.yaml`, or an exact property (`sc-domain:...` / `https://...`). |
| `--start-date` | yes | `YYYY-MM-DD`, inclusive. |
| `--end-date` | yes | `YYYY-MM-DD`, inclusive. |
| `--dimensions` | no | Space- or comma-separated. Any of `date`, `page`, `query`, `country`, `device`. Omit for one aggregated row. |
| `--filter` | no | `DIMENSION OPERATOR EXPRESSION`. Repeatable; all filters must match (AND). |
| `--row-limit` | no | 1 to 25000. Default 1000. |

Filter operators: `equals`, `notEquals`, `contains`, `notContains`, `includingRegex`, `excludingRegex`.

Behaviour:

- **Success**: the result is written to stdout as JSON, exit code `0`. Nothing else is written to stdout.
- **Failed query** (invalid input, missing config or credentials, API error): a one-line `error: ...` message on stderr, nothing on stdout, exit code `1`.
- **Bad command-line usage** (missing or unknown flag): argparse usage message on stderr, exit code `2`.

### Python

```python
from skills.gsc import query_search_analytics

result = query_search_analytics(
    site="example",
    start_date="2026-07-01",
    end_date="2026-09-30",
    dimensions=["date", "device"],
    filters=[{"dimension": "country", "operator": "equals", "expression": "gbr"}],
    row_limit=1000,
)
```

The function returns the same structure the CLI prints, and raises `ValueError`, `FileNotFoundError` or `RuntimeError` instead of exiting.

## Output

```json
{
  "request": {
    "site": "example",
    "property": "sc-domain:example.com",
    "start_date": "2026-07-01",
    "end_date": "2026-09-30",
    "dimensions": ["date", "device"],
    "filters": [
      {"dimension": "country", "operator": "equals", "expression": "gbr"}
    ],
    "row_limit": 1000
  },
  "row_count": 1,
  "rows": [
    {
      "date": "2026-07-01",
      "device": "MOBILE",
      "clicks": 100,
      "impressions": 2000,
      "ctr": 0.05,
      "position": 8.4
    }
  ]
}
```

Values are returned exactly as the API provides them: `ctr` is a fraction (0 to 1), `position` is the average position, and countries are ISO 3166-1 alpha-3 codes. Non-ASCII text (e.g. queries) is `\u`-escaped in the CLI output, which any JSON parser decodes back.

## Not handled in V0

- Pagination: a single request returns at most `row_limit` rows (API maximum 25000). If `row_count == row_limit`, the result may be truncated.
- Search type (always the API default, `web`) and data freshness options.
- Retries. API errors propagate to the caller.

## Authentication

Uses a service account with the read-only scope `webmasters.readonly`. The key path comes from `GSC_SERVICE_ACCOUNT_FILE` (read from the environment or `.env`). The service account's email must be added as a user on each GSC property. The key's contents are never printed.

## Tests

```bash
python -m pytest
```

The Google API is mocked; the tests make no network calls and need no credentials.
