"""Google SERP acquisition details and organic-result parsing.

Everything that depends on Google's URLs or markup lives in this module, so a
markup change is fixed here and nowhere else. Google's markup is not a stable
interface: expect the selectors below to need maintenance.

An engine module exposes ``READY_SELECTOR``, ``search_url``, ``blocked_reason``
and ``parse_results``; see ``collector.ENGINES``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urldefrag, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from .urls import unsafe_reason

SEARCH_URL = "https://www.google.com/search"

# --- Selectors (maintenance point) -------------------------------------------

# Present once the results page (or a block page) has rendered.
READY_SELECTOR = "#search a h3, #rso a h3, #captcha-form"
# Containers holding the results column, most specific first. First match wins.
RESULTS_ROOT_SELECTORS = ("#rso", "#search", "#main")
# An organic result is a link wrapping its <h3> title.
RESULT_LINK_SELECTOR = "a[href]:has(h3)"
# Links inside any of these are not organic results: ads, People Also Ask,
# carousels, and local/knowledge panels.
NON_ORGANIC_SELECTOR = ", ".join(
    (
        "#tads",
        "#tadsb",
        "#bottomads",
        "[data-text-ad]",
        "[aria-label='Ads']",
        ".related-question-pair",
        "[data-initq]",
        "g-scrolling-carousel",
        "g-inner-card",
        "#rhs",
        "#botstuff",
    )
)
# Where a result's snippet text lives, tried in order.
SNIPPET_SELECTORS = ("div.VwiC3b", "[data-sncf]", "div[style*='-webkit-line-clamp']", ".st")

# --- Block detection ---------------------------------------------------------

_BLOCK_URL_MARKERS = {
    "/sorry/": "Google served its automated-traffic (CAPTCHA) page",
    "consent.google.": "Google served a cookie-consent page instead of results",
}
_BLOCK_HTML_MARKERS = {
    'id="captcha-form"': "Google served a CAPTCHA",
    "unusual traffic from your computer network": "Google reported unusual traffic (CAPTCHA)",
}

_GOOGLE_SEARCH_HOST = re.compile(r"^(www\.)?google\.[a-z]{2,3}(\.[a-z]{2})?$")
# Google-owned hosts that are search utilities rather than ranking pages.
_GOOGLE_UTILITY_HOSTS = (
    "webcache.googleusercontent.com",
    "accounts.google.com",
    "policies.google.com",
    "translate.google.com",
    "maps.google.com",
)


def search_url(query: str) -> str:
    """Build the first-page results URL for ``query``."""
    return f"{SEARCH_URL}?{urlencode({'q': query})}"


def blocked_reason(url: str, html: str) -> str | None:
    """Return why Google refused to serve results, or ``None`` if it did not."""
    for marker, reason in _BLOCK_URL_MARKERS.items():
        if marker in url:
            return reason
    for marker, reason in _BLOCK_HTML_MARKERS.items():
        if marker in html:
            return reason
    return None


def _destination(href: str) -> str | None:
    """Resolve a result link to the URL it leads to, or ``None`` if not a result."""
    try:
        url = urljoin(SEARCH_URL, href.strip())
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None

    if _GOOGLE_SEARCH_HOST.match(host):
        if parts.path != "/url":
            return None  # Search navigation, settings, more-results links, etc.
        # Redirect wrapper: /url?q=<destination>
        params = parse_qs(parts.query)
        url = (params.get("q") or params.get("url") or [""])[0]
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return None
        if _GOOGLE_SEARCH_HOST.match(host):
            return None

    if host in _GOOGLE_UTILITY_HOSTS or unsafe_reason(url):
        return None
    return url


def _snippet(link: Any, root: Any) -> str | None:
    """Find the snippet belonging to ``link`` without straying into another result."""
    for ancestor in link.parents:
        if ancestor is root or len(ancestor.select(RESULT_LINK_SELECTOR)) > 1:
            return None
        for selector in SNIPPET_SELECTORS:
            node = ancestor.select_one(selector)
            if node:
                text = " ".join(node.get_text(" ").split())
                if text:
                    return text
    return None


def parse_results(html: str, max_results: int) -> list[dict[str, Any]]:
    """Parse organic results from a Google results page, in ranking order.

    Returns at most ``max_results`` dicts with ``position`` (1-based, counting
    organic results only), ``title``, ``url`` and ``snippet`` (``None`` when
    Google shows none). Ads, Google's own navigation links and repeated
    destination URLs are skipped. Returns an empty list if nothing matched.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = next(
        (node for selector in RESULTS_ROOT_SELECTORS if (node := soup.select_one(selector))),
        soup,
    )
    non_organic = {id(node) for node in root.select(NON_ORGANIC_SELECTOR)}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in root.select(RESULT_LINK_SELECTOR):
        if len(results) >= max_results:
            break
        if any(id(ancestor) in non_organic for ancestor in link.parents):
            continue
        title = " ".join(link.find("h3").get_text(" ").split())
        url = _destination(link["href"])
        if not title or not url:
            continue
        key = urldefrag(url).url  # Same page reached via a different #fragment.
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "position": len(results) + 1,
                "title": title,
                "url": url,
                "snippet": _snippet(link, root),
            }
        )
    return results
