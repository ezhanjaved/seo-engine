---
name: gsc
description: Retrieve Google Search Console performance data (clicks, impressions, CTR, average position) by date, page, query, country or device. Use for organic search performance questions, SEO monitoring, page or query performance, and investigating organic performance changes or declines.
version: 1.0.0
metadata:
  hermes:
    tags: [seo, gsc, google-search-console, organic-search, monitoring, clicks, impressions, ctr, position]
    category: seo
    requires_toolsets: [terminal]
---

# Google Search Console

A deterministic CLI that retrieves Google Search Console (Search Analytics) performance data as JSON. It retrieves evidence only; it does not analyse or interpret anything.

| Need | Where |
| --- | --- |
| Exact CLI syntax, flags, output example | `skills/gsc/README.md` |
| How to investigate and interpret the data | `methodologies/gsc_monitoring.md` |
| Site aliases | `config/sites.yaml` (local, not committed; template at `config/sites.example.yaml`) |

## When to Use

Use this skill when a question needs organic search evidence from Google Search Console, for example:

- how a site is performing in organic search;
- whether clicks or impressions changed between two periods;
- how specific pages or queries are performing;
- CTR or average position for a site, page or query;
- investigating an organic performance decline or growth.

For monitoring or any question about a performance change, read `methodologies/gsc_monitoring.md` before deciding which calls to make.

## Tool Location / Execution

Run from the repository root, in a Python environment that has `requirements.txt` installed (if the project uses a virtualenv, activate it first):

```bash
python -m skills.gsc --site <alias-or-property> --start-date YYYY-MM-DD --end-date YYYY-MM-DD [--dimensions ...] [--filter DIMENSION OPERATOR EXPRESSION] [--row-limit N]
```

- Success: JSON on stdout, exit code `0`.
- Failed query (invalid input, missing config or credentials, API error): one line `error: ...` on stderr, nothing on stdout, exit code `1`.
- Bad command-line usage: argparse usage message on stderr, exit code `2`.

Authentication is a read-only service account configured through `GSC_SERVICE_ACCOUNT_FILE` (environment or `.env`). Never print or read out the key file's contents.

## Inputs / Capabilities

| Input | Flag | Notes |
| --- | --- | --- |
| Site | `--site` (required) | An alias from `config/sites.yaml`, or an exact property (`sc-domain:example.com` or `https://www.example.com/`). |
| Start date | `--start-date` (required) | `YYYY-MM-DD`, inclusive. |
| End date | `--end-date` (required) | `YYYY-MM-DD`, inclusive. Must not be before the start date. |
| Dimensions | `--dimensions` | Space- or comma-separated, no duplicates. Omit for a single aggregated row. |
| Filters | `--filter` | `DIMENSION OPERATOR EXPRESSION`. Repeatable; all filters must match (AND). |
| Row limit | `--row-limit` | 1 to 25000. Default 1000. |

Dimensions, and the evidence each one gives:

- none: one aggregated row of totals for the period (site-wide, or for whatever the filters select);
- `date`: trend over time, one row per day;
- `page`: page-level evidence, one row per URL;
- `query`: query-level evidence, one row per search query;
- `country`: segmentation by country (ISO 3166-1 alpha-3 codes, e.g. `gbr`);
- `device`: segmentation by device (e.g. `MOBILE`).

Dimensions can be combined (e.g. `page query`); each combination becomes one row.

Filters can target any of the same five dimensions, whether or not that dimension is requested. Operators: `equals`, `notEquals`, `contains`, `notContains`, `includingRegex`, `excludingRegex`.

Each call covers one date range. To compare two periods, make one call per period with otherwise identical arguments.

Not supported: pagination beyond the row limit, search types other than the API default (web), data freshness options, retries.

## How to Use During an Investigation

1. Work out from the user's question what evidence is needed before calling anything.
2. For monitoring or interpreting a performance change, follow `methodologies/gsc_monitoring.md`. It owns the comparison periods, thresholds, order of investigation and stopping rules.
3. Start at the level the question is about. A site-wide question starts with an aggregated call, not a page or query breakdown.
4. Make further calls only when the methodology or the evidence so far justifies drilling down. Multiple calls in one investigation are expected.
5. Do not request every dimension by default. More dimensions means more rows, a higher chance of truncation, and no extra insight unless that breakdown is needed.
6. Narrow with filters rather than pulling everything, e.g. `--dimensions query --filter page equals <url>` for the queries of one page.
7. Stop when the methodology says enough evidence has been gathered.

## Output

```json
{
  "request": {
    "site": "...", "property": "...",
    "start_date": "...", "end_date": "...",
    "dimensions": ["..."], "filters": [{"dimension": "...", "operator": "...", "expression": "..."}],
    "row_limit": 1000
  },
  "row_count": 0,
  "rows": []
}
```

- `request`: the inputs as resolved, including the actual GSC `property` an alias mapped to. Check it to confirm the call was what you intended.
- `row_count`: the number of rows returned.
- `rows`: each row has one key per requested dimension, plus `clicks`, `impressions`, `ctr` (a fraction from 0 to 1, not a percentage) and `position` (average position; lower is better).
- Row order is the API's: clicks descending, or date ascending when grouping by `date` alone.

Truncation: if `row_count` equals `request.row_limit`, the result may be truncated. Treat it as incomplete: do not sum the rows as totals or treat absent pages/queries as having no data. Raise `--row-limit` (maximum 25000), narrow with filters or a shorter date range, or use an aggregated call for totals. If it still cannot be made complete, say so.

## Interpretation Boundary

This tool retrieves evidence. It does not establish SEO root causes.

Use `methodologies/gsc_monitoring.md` to interpret GSC monitoring evidence. Do not apply thresholds or interpretation rules of your own in its place.

GSC can show whether performance changed and where the change is concentrated. When it cannot show why, state what the evidence shows, what remains unknown, and what additional evidence would be needed. Do not guess.

## Failure / Data Quality Rules

- A non-zero exit code is a tool failure, not data. Report the stderr message as it is and do not draw SEO conclusions from it.
- Exit code `0` with `row_count: 0` is a valid empty dataset. It is not a tool failure, and it is not proof of an SEO problem. Check the date range, filters and `request.property` before concluding anything.
- Low traffic is not evidence that the integration is broken.
- Common failure causes: unknown site alias, missing `config/sites.yaml`, `GSC_SERVICE_ACCOUNT_FILE` unset or pointing at a missing file, the service account not being a user on the property, invalid dates, dimensions or filters. Fix the input if it was yours; otherwise report it.
- Failed calls are not retried automatically. Retry once if the error looks transient; do not loop.
- Never fabricate, estimate or fill in missing data. If a needed call failed or was truncated, say which evidence is missing.
- GSC data for the most recent days may be incomplete or not yet available, and this tool has no freshness options. Be cautious about periods that end on very recent dates, and say so when it could affect a comparison.
