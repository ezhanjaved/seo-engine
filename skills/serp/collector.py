"""SERP evidence collection: browser lifecycle and orchestration.

This module only collects evidence. It contains no search-intent
classification, analysis or interpretation logic, and it makes no attempt to
get past CAPTCHAs or other access controls: a block is reported as an error.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from . import bing, google
from .extractor import CONTENT_FIELDS, DEFAULT_MAX_TEXT_CHARS, extract_page
from .urls import unsafe_reason

# Engine name -> module providing READY_SELECTOR, search_url, blocked_reason, parse_results.
ENGINES = {"google": google, "bing": bing}

MAX_QUERY_LENGTH = 500
MAX_RESULTS_LIMIT = 20
MIN_TEXT_CHARS, MAX_TEXT_CHARS_LIMIT = 100, 200_000
DEFAULT_TIMEOUT, MAX_TIMEOUT = 20, 120  # Seconds, per navigation.
SETTLE_TIMEOUT_MS = 5000  # Extra wait for late content after the DOM is ready.
# Never fetched: not needed for text extraction.
BLOCKED_RESOURCE_TYPES = ("image", "media", "font")


class SerpError(Exception):
    """Base class for operational failures of the SERP collector."""


class BrowserStartupError(SerpError):
    """Playwright or Chromium could not be started."""


class SerpAcquisitionError(SerpError):
    """The search-results page could not be retrieved."""


class SerpBlockedError(SerpAcquisitionError):
    """The search engine refused automated access (CAPTCHA, consent wall, ...)."""


class SerpParseError(SerpError):
    """The search-results page was retrieved but no organic results were found."""


@dataclass
class _Loaded:
    final_url: str
    status: int | None
    content_type: str
    html: str


def _brief(exc: BaseException) -> str:
    """One-line description of an exception (Playwright messages are multi-line)."""
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    return f"{type(exc).__name__}: {lines[0][:300]}" if lines else type(exc).__name__


def _route_request(route: Any) -> None:
    """Abort requests for heavy resources and for local/private or non-HTTP(S) targets."""
    request = route.request
    if request.resource_type in BLOCKED_RESOURCE_TYPES or unsafe_reason(request.url):
        route.abort()
    else:
        route.continue_()


@contextmanager
def _browser_context(headless: bool) -> Iterator[Any]:
    """Yield a Chromium browser context, closing the browser on exit."""
    with ExitStack() as stack:
        try:
            from playwright.sync_api import sync_playwright

            playwright = stack.enter_context(sync_playwright())
            browser = playwright.chromium.launch(headless=headless)
            stack.callback(browser.close)
            context = browser.new_context(accept_downloads=False)
            context.route("**/*", _route_request)
        except ImportError as exc:
            raise BrowserStartupError(
                "Playwright is not installed. Run: pip install -r requirements.txt"
            ) from exc
        except Exception as exc:
            raise BrowserStartupError(
                f"could not start Chromium ({_brief(exc)}). "
                "If the browser is missing, run: python -m playwright install chromium"
            ) from exc
        yield context


def _load(context: Any, url: str, timeout_ms: int, ready_selector: str | None = None) -> _Loaded:
    """Navigate a fresh page to ``url`` and return its rendered HTML."""
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            if ready_selector:
                page.wait_for_selector(ready_selector, state="attached", timeout=SETTLE_TIMEOUT_MS)
            else:
                page.wait_for_load_state("load", timeout=SETTLE_TIMEOUT_MS)
        except Exception:  # Still settling: extract whatever has rendered so far.
            pass
        return _Loaded(
            final_url=page.url,
            status=response.status if response else None,
            content_type=(response.headers.get("content-type", "") if response else ""),
            html=page.content(),
        )
    finally:
        page.close()


def _collect_page(context: Any, url: str, timeout_ms: int, max_text_chars: int) -> dict[str, Any]:
    """Visit one ranking page. Never raises: a failure is recorded in the result."""
    page: dict[str, Any] = {"final_url": None, "status": None, **dict.fromkeys(CONTENT_FIELDS)}

    def failed(error: str) -> dict[str, Any]:
        return {**page, "extraction_status": "failed", "error": error}

    reason = unsafe_reason(url)
    if reason:
        return failed(f"unsafe URL: {reason}")
    try:
        loaded = _load(context, url, timeout_ms)
        page.update(final_url=loaded.final_url, status=loaded.status)
        if loaded.status is not None and loaded.status >= 400:
            return failed(f"HTTP {loaded.status}")
        if loaded.content_type and "html" not in loaded.content_type.lower():
            return failed(f"non-HTML content type: {loaded.content_type}")
        page.update(extract_page(loaded.html, loaded.final_url, max_text_chars))
    except Exception as exc:  # One broken page must not end the run.
        return failed(_brief(exc))
    return {**page, "extraction_status": "success", "error": None}


def _check_int(name: str, value: Any, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def collect(
    query: str,
    engine: str = "google",
    max_results: int = 10,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    timeout: int = DEFAULT_TIMEOUT,
    headless: bool = True,
) -> dict[str, Any]:
    """Collect first-page organic results for a query, and each ranking page's content.

    Args:
        query: The search query.
        engine: Search engine, any of ``ENGINES``.
        max_results: Maximum organic results to collect, 1 to 20.
        max_text_chars: Maximum characters of main text kept per page.
        timeout: Navigation timeout per page, in seconds.
        headless: Run Chromium without a window.

    Returns:
        A JSON-serializable dict with ``request``, ``serp`` and ``summary``.
        Each entry of ``serp.results`` has ``position``, ``title``, ``url``,
        ``snippet`` and ``page``; a ranking page that could not be collected
        has ``page.extraction_status == "failed"`` and a ``page.error``.

    Raises:
        ValueError: An input is invalid.
        BrowserStartupError: Playwright or Chromium could not be started.
        SerpBlockedError: The engine refused automated access.
        SerpAcquisitionError: The results page could not be retrieved.
        SerpParseError: No organic results could be parsed from the page.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    query = " ".join(query.split())
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"query must be at most {MAX_QUERY_LENGTH} characters")
    if engine not in ENGINES:
        raise ValueError(f"Unsupported engine {engine!r}. Supported: {sorted(ENGINES)}")
    _check_int("max_results", max_results, 1, MAX_RESULTS_LIMIT)
    _check_int("max_text_chars", max_text_chars, MIN_TEXT_CHARS, MAX_TEXT_CHARS_LIMIT)
    _check_int("timeout", timeout, 1, MAX_TIMEOUT)

    serp_engine = ENGINES[engine]
    serp_url = serp_engine.search_url(query)
    timeout_ms = timeout * 1000

    with _browser_context(headless) as context:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            loaded = _load(context, serp_url, timeout_ms, serp_engine.READY_SELECTOR)
        except Exception as exc:
            raise SerpAcquisitionError(
                f"could not load the {engine} results page: {_brief(exc)}"
            ) from exc

        reason = serp_engine.blocked_reason(loaded.final_url, loaded.html)
        if reason:
            raise SerpBlockedError(f"{reason}; no results were collected ({loaded.final_url})")
        if loaded.status is not None and loaded.status >= 400:
            raise SerpAcquisitionError(f"{engine} results page returned HTTP {loaded.status}")

        results = serp_engine.parse_results(loaded.html, max_results)
        if not results:
            raise SerpParseError(
                f"no organic results could be parsed from the {engine} results page; "
                "there may be none for this query, or the page markup has changed"
            )
        for result in results:
            result["page"] = _collect_page(context, result["url"], timeout_ms, max_text_chars)

    successful = sum(r["page"]["extraction_status"] == "success" for r in results)
    return {
        "request": {
            "query": query,
            "engine": engine,
            "max_results": max_results,
            "max_text_chars": max_text_chars,
        },
        "serp": {
            "url": serp_url,
            "fetched_at": fetched_at,
            "results_found": len(results),
            "results": results,
        },
        "summary": {
            "results_requested": max_results,
            "results_extracted": len(results),
            "pages_successful": successful,
            "pages_failed": len(results) - successful,
        },
    }
