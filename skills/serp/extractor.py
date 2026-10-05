"""Ranking-page content extraction.

Works on any HTML document and knows nothing about search engines. It is
deterministic: the same HTML always yields the same output, and nothing is
summarised, classified or inferred.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DEFAULT_MAX_TEXT_CHARS = 10_000  # Per page; roughly 2,500 tokens of English text.
MAX_HEADINGS = 100  # Per page, H2-H6.
# A <main>/<article> with less text than this is treated as an empty shell.
MIN_CONTAINER_CHARS = 200

# Content keys of an extracted page. All are None when a page was not extracted.
CONTENT_FIELDS = (
    "title",
    "meta_description",
    "canonical",
    "h1",
    "h1_count",
    "headings",
    "headings_truncated",
    "main_text",
    "main_text_source",
    "main_text_truncated",
    "word_count",
)

# Removed everywhere before any text is read.
_NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "nav",
    "footer",
    "aside",
    "form",
    "button",
    "select",
    "dialog",
)
_NOISE_ROLES = (
    "navigation",
    "banner",
    "contentinfo",
    "complementary",
    "search",
    "dialog",
    "alertdialog",
    "menu",
    "menubar",
)
_HEADING = re.compile(r"^h[1-6]$")
_DESCRIPTION = re.compile(r"^description$", re.IGNORECASE)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Cut ``text`` to at most ``limit`` characters, on a word boundary."""
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    if not text[limit].isspace() and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(), True


def _canonical(soup: BeautifulSoup, base_url: str) -> str | None:
    for link in soup.find_all("link", href=True):
        if "canonical" in [rel.lower() for rel in link.get("rel") or []]:
            href = link["href"].strip()
            return urljoin(base_url, href) if href else None
    return None


def _main_container(soup: BeautifulSoup) -> tuple[Any, str]:
    """Pick the element most likely to hold the page's main content."""
    body = soup.body or soup
    mains = soup.find_all("main") + [
        tag for tag in soup.find_all(attrs={"role": "main"}) if tag.name != "main"
    ]
    # Nested <article>s (e.g. comments) belong to their outermost article.
    articles = [tag for tag in soup.find_all("article") if not tag.find_parent("article")]

    if mains:
        candidate, source = max(mains, key=lambda tag: len(_clean(tag.get_text(" ")))), "main"
    elif len(articles) == 1:
        candidate, source = articles[0], "article"
    else:
        return body, "body"  # No container, or a listing of several articles.

    if len(_clean(candidate.get_text(" "))) < MIN_CONTAINER_CHARS:
        return body, "body"
    return candidate, source


def extract_page(
    html: str, base_url: str, max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
) -> dict[str, Any]:
    """Extract SEO/content evidence from one HTML document.

    Args:
        html: The page's HTML (ideally the rendered DOM).
        base_url: The page's own URL, used to resolve a relative canonical.
        max_text_chars: Upper bound on ``main_text`` length.

    Returns:
        A dict with exactly the keys in ``CONTENT_FIELDS``. A value the page
        does not provide is ``None`` (``headings`` is ``[]``); nothing is
        invented. ``word_count`` counts the full main text, before truncation.
    """
    soup = BeautifulSoup(html, "html.parser")

    title_tag = next((t for t in soup.find_all("title") if not t.find_parent("svg")), None)
    description_tag = soup.find("meta", attrs={"name": _DESCRIPTION})
    title = _clean(title_tag.get_text() if title_tag else None)
    description = _clean(description_tag.get("content") if description_tag else None)
    canonical = _canonical(soup, base_url)

    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": _NOISE_ROLES}):
        if not tag.decomposed:
            tag.decompose()

    # Headings are read before the site <header> is dropped: it often holds the H1.
    h1s: list[str] = []
    headings: list[dict[str, Any]] = []
    for tag in soup.find_all(_HEADING):
        text = _clean(tag.get_text(" "))
        if not text:
            continue
        if tag.name == "h1":
            h1s.append(text)
        else:
            headings.append({"level": int(tag.name[1]), "text": text})

    container, source = _main_container(soup)
    if source == "body":
        for tag in container.find_all("header"):
            if not tag.decomposed and not tag.find_parent(["main", "article"]):
                tag.decompose()
    full_text = _clean(container.get_text(" "))
    main_text, text_truncated = _truncate(full_text, max_text_chars)

    return {
        "title": title or None,
        "meta_description": description or None,
        "canonical": canonical,
        "h1": h1s[0] if h1s else None,
        "h1_count": len(h1s),
        "headings": headings[:MAX_HEADINGS],
        "headings_truncated": len(headings) > MAX_HEADINGS,
        "main_text": main_text,
        "main_text_source": source,
        "main_text_truncated": text_truncated,
        "word_count": len(full_text.split()),
    }
