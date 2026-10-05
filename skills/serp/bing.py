"""Bing SERP acquisition details and organic-result parsing.

Everything that depends on Bing's URLs or markup lives in this module, so a
markup change is fixed here and nowhere else. Bing's markup is not a stable
interface: expect the selectors below to need maintenance.

An engine module exposes ``READY_SELECTOR``, ``search_url``, ``blocked_reason``
and ``parse_results``; see ``collector.ENGINES``.
"""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import parse_qs, urldefrag, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from .urls import unsafe_reason

SEARCH_URL = "https://www.bing.com/search"

# --- Selectors (maintenance point) -------------------------------------------

# Present once the results page (or a block page) has rendered.
READY_SELECTOR = "#b_results .b_algo h2 a, #b_captcha, .cf-turnstile"
# Container holding the results column. Falls back to the whole document.
RESULTS_ROOT_SELECTORS = ("#b_results",)
# One organic result.
RESULT_SELECTOR = "li.b_algo"
# The result's title link, inside a result.
TITLE_LINK_SELECTOR = "h2 a[href]"
# Results inside (or that are) any of these are not organic: ads, answer
# boxes (People Also Ask, related searches, carousels), pagination, sidebar.
NON_ORGANIC_SELECTOR = ", ".join(
    (
        ".b_ad",
        ".b_adTop",
        ".b_adBottom",
        ".b_ans",
        ".b_pag",
        ".b_msg",
        "#b_context",
        "#b_topw",
    )
)
# Where a result's snippet text lives, inside a result, tried in order.
SNIPPET_SELECTORS = (".b_caption p", "p[class*='b_lineclamp']", ".b_algoSlug", ".b_snippet")

# --- Block detection ---------------------------------------------------------

_BLOCK_URL_MARKERS = {
    "/turing/captcha": "Bing served its CAPTCHA challenge page",
}
_BLOCK_HTML_MARKERS = {
    'id="b_captcha"': "Bing served a CAPTCHA",
    "Please solve the challenge below to continue": "Bing served a CAPTCHA challenge",
    "challenges.cloudflare.com/turnstile": "Bing served a verification challenge",
}

_BING_HOST = re.compile(r"^([a-z0-9-]+\.)*bing\.com$")
# Click-tracking wrapper: /ck/a?...&u=a1<base64url destination>
_REDIRECT_PATH = "/ck/a"
_REDIRECT_PREFIX = "a1"


def search_url(query: str) -> str:
    """Build the first-page results URL for ``query``."""
    return f"{SEARCH_URL}?{urlencode({'q': query})}"


def blocked_reason(url: str, html: str) -> str | None:
    """Return why Bing refused to serve results, or ``None`` if it did not."""
    for marker, reason in _BLOCK_URL_MARKERS.items():
        if marker in url:
            return reason
    for marker, reason in _BLOCK_HTML_MARKERS.items():
        if marker in html:
            return reason
    return None


def _unwrap_redirect(query: str) -> str | None:
    """Decode the destination carried by a ``/ck/a`` tracking link."""
    encoded = (parse_qs(query).get("u") or [""])[0]
    if not encoded.startswith(_REDIRECT_PREFIX):
        return None
    encoded = encoded[len(_REDIRECT_PREFIX) :]
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8")
    except ValueError:  # Bad base64 or not UTF-8.
        return None


def _destination(href: str) -> str | None:
    """Resolve a result link to the URL it leads to, or ``None`` if not a result."""
    try:
        url = urljoin(SEARCH_URL, href.strip())
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if _BING_HOST.match(host) and parts.path == _REDIRECT_PATH:
            url = _unwrap_redirect(parts.query) or ""
            host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None

    # Anything still on Bing is search navigation or a utility link.
    if _BING_HOST.match(host) or unsafe_reason(url):
        return None
    return url


def _snippet(result: Any) -> str | None:
    for selector in SNIPPET_SELECTORS:
        for node in result.select(selector):
            text = " ".join(node.get_text(" ").split())
            if text:
                return text
    return None


def parse_results(html: str, max_results: int) -> list[dict[str, Any]]:
    """Parse organic results from a Bing results page, in ranking order.

    Returns at most ``max_results`` dicts with ``position`` (1-based, counting
    organic results only), ``title``, ``url`` and ``snippet`` (``None`` when
    Bing shows none). Ads, Bing's own links and repeated destination URLs are
    skipped. Returns an empty list if nothing matched.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = next(
        (node for selector in RESULTS_ROOT_SELECTORS if (node := soup.select_one(selector))),
        soup,
    )
    non_organic = {id(node) for node in root.select(NON_ORGANIC_SELECTOR)}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in root.select(RESULT_SELECTOR):
        if len(results) >= max_results:
            break
        if id(item) in non_organic or any(id(a) in non_organic for a in item.parents):
            continue
        link = item.select_one(TITLE_LINK_SELECTOR)
        if link is None:
            continue
        title = " ".join(link.get_text(" ").split())
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
                "snippet": _snippet(item),
            }
        )
    return results
