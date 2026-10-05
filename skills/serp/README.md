# SERP skill

Searches a query in a real browser (Playwright + Chromium), reads the organic results from the first results page, visits each ranking page, and returns everything it found as JSON.

**This skill collects SERP and ranking-page evidence. It does not determine search intent.** It contains no LLM, no classification, no recommendations and no summarising. Interpreting the evidence is the job of a methodology and of the agent (Hermes) that calls this skill.

## Architecture

| Module | Responsibility |
| --- | --- |
| `google.py` | Everything Google-specific: the search URL, block/CAPTCHA detection, and the selectors that find organic results. |
| `bing.py` | The same for Bing. |
| `extractor.py` | Ranking-page extraction from an HTML document. Knows nothing about search engines. |
| `urls.py` | URL safety check used before a URL is accepted as a result or visited. |
| `collector.py` | Browser lifecycle, orchestration, input validation, error types. |
| `__main__.py` | CLI. |

Parsing happens in Python on the HTML the browser rendered, so the engine modules and `extractor.py` are pure functions that are tested without a browser.

Each engine is one module (`google.py`, `bing.py`) registered in `collector.ENGINES`. Adding an engine means adding one module that provides `READY_SELECTOR`, `search_url(query)`, `blocked_reason(url, html)` and `parse_results(html, max_results)`, and registering it. Page extraction is shared by all engines and is not touched.

**Search-engine markup changes over time, so SERP parsing may require maintenance.** Each engine's selectors are constants at the top of its module. When an engine changes its markup the usual symptom is a `SerpParseError` (no results found) or missing snippets.

## Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

The second command downloads the Chromium build Playwright drives; it is needed once per machine. On a fresh Linux host or container, install the system libraries too:

```bash
python -m playwright install --with-deps chromium
```

## Usage

Run from the repository root.

### Command line

```bash
python -m skills.serp \
  --query "best local seo tools" \
  --engine google \
  --max-results 10
```

The same against Bing:

```bash
python -m skills.serp \n  --query "best local seo tools" \n  --engine bing \n  --max-results 10
```

| Flag | Required | Notes |
| --- | --- | --- |
| `--query` | yes | Search query, up to 500 characters. One query per invocation. |
| `--engine` | no | `google` or `bing`. Default `google`. |
| `--max-results` | no | Organic results to collect, 1 to 20. Default 10. A first results page usually holds about 10. |
| `--max-text-chars` | no | Main-text characters kept per page, 100 to 200000. Default 10000. |
| `--timeout` | no | Navigation timeout per page in seconds, 1 to 120. Default 20. |
| `--headed` | no | Show the browser window. For local debugging; the default is headless. |

Behaviour:

- **Success**: the result is written to stdout as JSON, exit code `0`. Nothing else is written to stdout. Individual ranking pages may have failed; check `summary.pages_failed`.
- **Failure**: a one-line `error: ...` message on stderr, nothing on stdout, and a non-zero exit code:

| Exit code | Meaning |
| --- | --- |
| `2` | Bad usage or invalid input (missing/unknown flag, empty query, unsupported engine, value out of range). |
| `3` | `BrowserStartupError`: Playwright or Chromium is missing or could not start. |
| `4` | The results page could not be collected: `SerpBlockedError` (CAPTCHA, unusual-traffic or consent page), `SerpAcquisitionError` (navigation failure or HTTP error), or `SerpParseError` (page loaded but no organic results were found). |
| `1` | Any other unexpected error. |

### Python

```python
from skills.serp import collect

result = collect(query="best local seo tools", engine="google", max_results=10)
```

Returns the same structure the CLI prints, and raises `ValueError`, `BrowserStartupError`, `SerpAcquisitionError`, `SerpBlockedError` or `SerpParseError` instead of exiting.

## Output

```json
{
  "request": {
    "query": "best local seo tools",
    "engine": "google",
    "max_results": 10,
    "max_text_chars": 10000
  },
  "serp": {
    "url": "https://www.google.com/search?q=best+local+seo+tools",
    "fetched_at": "2026-10-05T10:15:00+00:00",
    "results_found": 2,
    "results": [
      {
        "position": 1,
        "title": "10 Best Local SEO Tools",
        "url": "https://www.example.com/local-seo-tools",
        "snippet": "A comparison of the tools we use for local rankings ...",
        "page": {
          "final_url": "https://www.example.com/local-seo-tools/",
          "status": 200,
          "title": "10 Best Local SEO Tools | Example",
          "meta_description": "We tested local SEO tools for rank tracking and citations.",
          "canonical": "https://www.example.com/local-seo-tools/",
          "h1": "10 Best Local SEO Tools",
          "h1_count": 1,
          "headings": [
            {"level": 2, "text": "How we tested"},
            {"level": 3, "text": "Rank tracking"}
          ],
          "headings_truncated": false,
          "main_text": "10 Best Local SEO Tools We tested ...",
          "main_text_source": "main",
          "main_text_truncated": false,
          "word_count": 1834,
          "extraction_status": "success",
          "error": null
        }
      },
      {
        "position": 2,
        "title": "Local SEO Software",
        "url": "https://www.example.org/software",
        "snippet": null,
        "page": {
          "final_url": null,
          "status": null,
          "title": null,
          "meta_description": null,
          "canonical": null,
          "h1": null,
          "h1_count": null,
          "headings": null,
          "headings_truncated": null,
          "main_text": null,
          "main_text_source": null,
          "main_text_truncated": null,
          "word_count": null,
          "extraction_status": "failed",
          "error": "TimeoutError: Page.goto: Timeout 20000ms exceeded."
        }
      }
    ]
  },
  "summary": {
    "results_requested": 10,
    "results_extracted": 2,
    "pages_successful": 1,
    "pages_failed": 1
  }
}
```

### Fields

`serp`:

- `url`: the results-page URL that was requested. `fetched_at`: UTC time of that request.
- `results_found`: number of organic results extracted. It can be lower than `max_results`; results are never invented.
- `results[].position`: 1-based rank among **organic** results only, in page order. `title`, `url` and `snippet` are as shown on the results page; `snippet` is `null` when none was found.

`results[].page`:

| Field | Meaning |
| --- | --- |
| `final_url` | URL after redirects. |
| `status` | HTTP status of the page's main response. |
| `title` | `<title>` text. |
| `meta_description` | Content of `<meta name="description">`. Open Graph descriptions are not used as a substitute. |
| `canonical` | `<link rel="canonical">`, resolved to an absolute URL. |
| `h1`, `h1_count` | Text of the first non-empty `<h1>`, and how many there are. |
| `headings` | H2–H6 in document order as `{"level", "text"}`. At most 100; `headings_truncated` is `true` if there were more. |
| `main_text` | Main textual content, whitespace-normalised to single spaces. |
| `main_text_source` | Which container the text came from: `main`, `article` or `body` (the fallback). |
| `main_text_truncated` | `true` if `main_text` was cut to `max_text_chars`. |
| `word_count` | Whitespace-separated words in the full main text, **before** truncation. |
| `extraction_status` | `success` or `failed`. |
| `error` | `null` on success; a one-line reason on failure. |

### Null and empty values

- `extraction_status: "failed"`: every content field is `null`, meaning "not collected". `final_url` and `status` are filled only if the page responded (e.g. `status: 403`, `error: "HTTP 403"`).
- `extraction_status: "success"`: a `null` field means the page does not have that element; `headings: []` means it has no H2–H6; `main_text: ""` with `word_count: 0` means no text was found.

Non-ASCII text is `\u`-escaped in the CLI output, which any JSON parser decodes back.

## Extraction behaviour

**Results page (Google).** Organic results are links that wrap an `<h3>` title inside the results column. Skipped: ad blocks, People Also Ask, carousels, the side panel, related searches, Google's own search/navigation/cache/account links, links with an unsafe URL, and any destination already seen (compared without the `#fragment`). Google redirect links (`/url?q=...`) are unwrapped to their destination.

**Results page (Bing).** Organic results are the `li.b_algo` items of the results column; the title and URL come from the item's `h2` link and the snippet from its caption. Skipped: ads (`.b_ad`), answer boxes such as People Also Ask and related searches (`.b_ans`), pagination, the sidebar, items without a title link, links that stay on `bing.com`, links with an unsafe URL, and any destination already seen (compared without the `#fragment`). Bing click-tracking links (`bing.com/ck/a?...&u=a1...`) are decoded to their destination; one that cannot be decoded is skipped rather than guessed.

**Ranking pages (all engines).** Each result is opened in its own tab, one at a time, and the rendered DOM is parsed:

1. `title`, `meta_description` and `canonical` are read from the document.
2. Non-content elements are removed: `script`, `style`, `noscript`, `template`, `svg`, `iframe`, `nav`, `footer`, `aside`, `form`, `button`, `select`, `dialog`, and elements with an ARIA role of `navigation`, `banner`, `contentinfo`, `complementary`, `search`, `dialog`, `alertdialog`, `menu` or `menubar`.
3. `h1` and `headings` are read from what remains.
4. The main container is chosen: the `<main>` / `role="main"` element with the most text; otherwise the page's single top-level `<article>`; otherwise `<body>` with site-level `<header>` elements removed. A `<main>` or `<article>` holding under 200 characters is treated as an empty shell and `<body>` is used instead.
5. The container's text is whitespace-normalised, counted, and truncated to `max_text_chars` on a word boundary.

No class-name heuristics and no readability scoring are used, so menus or cookie banners built from plain `<div>`s can end up in `main_text`, most often when `main_text_source` is `body`.

## Text limits

`main_text` is capped at `--max-text-chars` per page (default 10000 characters, roughly 2,500 tokens of English), so a 10-result run carries at most about 100,000 characters of page text. Truncation is always reported through `main_text_truncated`, and `word_count` still reflects the full text. Headings are capped at 100 per page (`headings_truncated`).

## Error behaviour

- **A ranking page fails** (timeout, DNS/connection error, HTTP 4xx/5xx, non-HTML response such as a PDF, download, unsafe URL): the failure is recorded in that result's `page` and collection continues. The run still exits `0`.
- **The results page fails** (see exit code `4`): nothing is written to stdout. A block by the search engine is reported, never worked around.
- Stack traces are never printed.

## Network and safety behaviour

- Default Chromium, headless, with its normal user agent. No stealth or fingerprint changes, no proxies, no CAPTCHA solving, no cookies or logins. Each run uses a fresh, empty browser profile.
- Only absolute `http`/`https` URLs are visited. URLs with embedded credentials, `localhost`, `.local`/`.internal` names, and private, loopback or link-local IP addresses are rejected, both as results and as requests made by a page (including redirects). Hostnames are not resolved, so a public name pointing at a private address is not caught.
- Downloads are disabled. Images, media and fonts are not fetched.
- Pages are visited sequentially, one at a time. `robots.txt` is not consulted.

## Supported engines and verification status

| Engine | Mocked tests | Live verification |
| --- | --- | --- |
| `google` | Parsing, block detection and collection covered with static HTML. | Block detection confirmed live: a headed run was served Google's CAPTCHA page and reported `SerpBlockedError`. Result parsing has **not** been verified against a live results page. |
| `bing` | Parsing, block detection and collection covered with static HTML. | Verified live on 2026-10-05: first-page organic results were successfully collected and ranking-page extraction worked, including graceful handling of an individual HTTP 418 page failure. |

The automated tests run against simplified, hand-written HTML. They prove the parsing logic does what it is written to do; they do not prove that the selectors or block markers match what Google or Bing serve today.

## Known V1 limitations

- **Google is likely to block this.** Headless Chromium from a server IP is frequently sent to a CAPTCHA or "unusual traffic" page. That surfaces as `SerpBlockedError` (exit `4`). Automated querying is also against Google's Terms of Service; decide whether that is acceptable before scheduling this.
- **Bing may block this too.** Its CAPTCHA/challenge markers in `bing.py` are written from knowledge of Bing's pages, not observed live; an unrecognised challenge page would surface as `SerpParseError` instead of `SerpBlockedError`. Check Microsoft's terms of use before scheduling automated queries.
- **Consent pages are not handled.** From EU/UK IP addresses Google shows a cookie-consent page first; this is reported as a block. A Bing cookie banner is an overlay on the results page and is ignored.
- **Results depend on where it runs.** No language, country or location is set, so results reflect the machine's IP address and Chromium's default locale (`en-US`).
- First page only; no pagination.
- Organic results only: no ads, featured snippets, AI Overviews, People Also Ask, images, videos, local pack, shopping or related searches. `position` therefore is not the visual position on the page.
- A featured snippet or other special block that is marked up like a normal result may be counted as organic, and a legitimately ranking `google.com` page (or, on Bing, any `bing.com` page) is excluded.
- A zero-result query and a markup change both produce `SerpParseError`; they cannot be told apart.
- No retries, no caching, no concurrency. Worst case a run takes about `(timeout + 5s) × (results + 1)`.
- Content that only appears after interaction (tabs, "read more", infinite scroll) or that loads more than 5 seconds after the DOM is ready is not captured.
- Pages that soft-block bots with a `200` status (challenge or "enable JavaScript" pages) are recorded as `success`; a very low `word_count` is the hint.

## Tests

```bash
python -m pytest
```

The browser is faked and the HTML is static; the tests make no network calls, need no installed browser, and do not depend on Google's or Bing's current markup. Passing tests are not live verification; see [Supported engines and verification status](#supported-engines-and-verification-status).
