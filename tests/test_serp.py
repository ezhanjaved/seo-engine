"""Tests for the SERP skill. The browser is faked; nothing here hits the network.

The HTML below is a simplified stand-in for a results page and for ranking
pages. It is not a copy of Google's current markup and the tests do not
depend on it.
"""

from __future__ import annotations

import base64
import json
import sys
from contextlib import contextmanager

import pytest

from skills.serp import bing, collector, google
from skills.serp.__main__ import main
from skills.serp.extractor import CONTENT_FIELDS, MAX_HEADINGS, extract_page
from skills.serp.urls import unsafe_reason


def organic(url, title, snippet=None):
    snippet_html = f'<div class="VwiC3b">{snippet}</div>' if snippet else ""
    return f'<div class="g"><a href="{url}"><h3>{title}</h3></a>{snippet_html}</div>'


SERP_HTML = f"""
<html><head><title>best local seo tools - Google Search</title></head><body>
<div id="top-nav">
  <a href="/search?q=best+local+seo+tools&tbm=isch">Images</a>
  <a href="https://maps.google.com/maps?q=best+local+seo+tools">Maps</a>
  <a href="https://accounts.google.com/ServiceLogin">Sign in</a>
</div>
<div id="search">
  <div id="tads">
    <div data-text-ad="1"><a href="https://ads.example.com/buy"><h3>Sponsored tool</h3></a></div>
  </div>
  <div id="rso">
    {organic("https://alpha.example.com/tools", "Alpha: 10 Best Local SEO Tools", "Alpha   snippet\n text.")}
    {organic("/url?q=https://beta.example.com/guide%3Fa%3D1&sa=U&ved=abc", "Beta Guide", "Beta snippet.")}
    <div class="related-question-pair">
      <a href="https://paa.example.com/answer"><h3>What is local SEO?</h3></a>
    </div>
    {organic("https://alpha.example.com/tools#pricing", "Alpha duplicate", "Dup snippet.")}
    {organic("https://www.google.com/search?q=more+tools", "More results from Google")}
    {organic("https://webcache.googleusercontent.com/search?q=cache:x", "Cached")}
    {organic("javascript:alert(1)", "Script link")}
    {organic("file:///etc/passwd", "File link")}
    {organic("http://127.0.0.1:8080/admin", "Loopback link")}
    <div class="g"><a href="https://notitle.example.com/"><h3> </h3></a></div>
    <div class="g"><a href="https://nolink.example.com/">Plain link without a title heading</a></div>
    {organic("https://gamma.example.com/", "Gamma Home")}
    {organic("https://delta.example.com/post", "Delta Post", "Delta snippet.")}
  </div>
  <div id="botstuff"><a href="https://related.example.com/"><h3>Related search</h3></a></div>
</div>
<a href="https://policies.google.com/privacy">Privacy</a>
</body></html>
"""

EXPECTED_URLS = [
    "https://alpha.example.com/tools",
    "https://beta.example.com/guide?a=1",
    "https://gamma.example.com/",
    "https://delta.example.com/post",
]

BODY_TEXT = "Local SEO tools help a business appear in nearby searches. " * 6

ARTICLE_HTML = f"""
<html><head>
  <title>  Alpha:   Best Tools </title>
  <meta name="Description" content="  A guide to   local SEO tools. ">
  <meta property="og:description" content="Social description">
  <link rel="stylesheet" href="/site.css">
  <link rel="canonical" href="/tools?ref=canonical">
  <style>.x {{ color: red }}</style>
</head><body>
  <header><div class="logo">ACME BRAND</div><nav><a href="/">MENU HOME</a></nav></header>
  <main>
    <article>
      <h1>Best <em>Local</em> SEO Tools</h1>
      <p>{BODY_TEXT}</p>
      <h2>Why   it matters</h2>
      <p>Visible   paragraph
         two.</p>
      <h3>Rank tracking</h3>
      <h2></h2>
      <script>var tracking = "SCRIPT TEXT";</script>
      <noscript>NOSCRIPT TEXT</noscript>
      <form><label>SUBSCRIBE FORM</label><input name="email"></form>
      <aside>SIDEBAR PROMO</aside>
      <div role="dialog">COOKIE BANNER</div>
      <button>CLICK ME</button>
      <h4>Deep heading</h4>
    </article>
  </main>
  <footer><h2>FOOTER HEADING</h2>FOOTER LINKS</footer>
</body></html>
"""


def page_html(name):
    return (
        f"<html><head><title>{name} title</title></head><body><main><h1>{name} h1</h1>"
        f"<p>{name} {BODY_TEXT}</p></main></body></html>"
    )


# --- Fake browser ------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, content_type):
        self.status = status
        self.headers = {"content-type": content_type}


class FakePage:
    def __init__(self, context):
        self.context = context
        self.url = "about:blank"
        self.closed = False
        self._html = ""

    def goto(self, url, **kwargs):
        self.context.visited.append(url)
        entry = self.context.site[url]
        if isinstance(entry, Exception):
            raise entry
        self.url = entry.get("final_url", url)
        self._html = entry.get("html", "")
        return FakeResponse(entry.get("status", 200), entry.get("content_type", "text/html; charset=utf-8"))

    def wait_for_selector(self, selector, **kwargs):
        pass

    def wait_for_load_state(self, state, **kwargs):
        pass

    def content(self):
        return self._html

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, site):
        self.site = site
        self.visited = []
        self.pages = []

    def new_page(self):
        page = FakePage(self)
        self.pages.append(page)
        return page


QUERY = "best local seo tools"
SERP_URL = google.search_url(QUERY)


@pytest.fixture
def browser(monkeypatch):
    """Replace the Playwright boundary with a fake serving a small fixed 'web'.

    Returns the fake context; edit ``browser.site`` to change what a URL serves.
    """
    context = FakeContext(
        {
            SERP_URL: {"html": SERP_HTML},
            EXPECTED_URLS[0]: {"html": ARTICLE_HTML},
            EXPECTED_URLS[1]: {"html": page_html("Beta"), "final_url": "https://beta.example.com/guide/"},
            EXPECTED_URLS[2]: {"html": page_html("Gamma")},
            EXPECTED_URLS[3]: {"html": page_html("Delta")},
        }
    )

    @contextmanager
    def fake_browser_context(headless):
        context.headless = headless
        yield context

    monkeypatch.setattr(collector, "_browser_context", fake_browser_context)
    return context


# --- URL safety --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "http://sub.example.co.uk/path?q=1#frag",
        "https://example.com:8443/a",
        "https://8.8.8.8/",
    ],
)
def test_public_http_urls_are_safe(url):
    assert unsafe_reason(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "example.com/path",
        "/relative/path",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "ftp://example.com/file",
        "chrome://settings",
        "https://",
        "https:///path",
        "https://user:pass@example.com/",
        "https://example.com:notaport/",
        "https://exa mple.com/",
        "https://example.com/\npath",
        "http://localhost:3000/",
        "http://app.localhost/",
        "http://printer.local/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://2130706433/",
        "http://0x7f.0.0.1/",
        "http://intranet/",
        "https://example.com/" + "a" * 2000,
    ],
)
def test_unsafe_or_malformed_urls_are_rejected(url):
    assert unsafe_reason(url) is not None


# --- SERP parsing ------------------------------------------------------------


def test_organic_results_are_parsed_in_order():
    results = google.parse_results(SERP_HTML, 10)

    assert [r["url"] for r in results] == EXPECTED_URLS
    assert [r["position"] for r in results] == [1, 2, 3, 4]
    assert [r["title"] for r in results] == [
        "Alpha: 10 Best Local SEO Tools",
        "Beta Guide",
        "Gamma Home",
        "Delta Post",
    ]


def test_snippets_are_normalized_and_null_when_absent():
    results = google.parse_results(SERP_HTML, 10)

    assert [r["snippet"] for r in results] == [
        "Alpha snippet text.",
        "Beta snippet.",
        None,
        "Delta snippet.",
    ]


def test_redirect_wrapped_links_are_unwrapped():
    assert google.parse_results(SERP_HTML, 10)[1]["url"] == "https://beta.example.com/guide?a=1"


@pytest.mark.parametrize(
    "excluded",
    [
        "ads.example.com",  # ad block
        "paa.example.com",  # People Also Ask
        "related.example.com",  # related searches
        "google.com",  # search navigation / internal
        "googleusercontent.com",  # cache
        "javascript:",
        "file:",
        "127.0.0.1",
        "notitle.example.com",
        "nolink.example.com",
    ],
)
def test_non_organic_and_unsafe_links_are_excluded(excluded):
    assert not any(excluded in r["url"] for r in google.parse_results(SERP_HTML, 10))


def test_duplicate_destinations_are_collapsed():
    urls = [r["url"] for r in google.parse_results(SERP_HTML, 10)]

    assert len([u for u in urls if u.startswith("https://alpha.example.com/tools")]) == 1


@pytest.mark.parametrize("limit, expected", [(1, 1), (2, 2), (4, 4), (10, 4)])
def test_max_results_caps_without_inventing_results(limit, expected):
    results = google.parse_results(SERP_HTML, limit)

    assert [r["url"] for r in results] == EXPECTED_URLS[:expected]


def test_results_are_found_without_a_known_results_container():
    html = f"<html><body>{organic('https://solo.example.com/', 'Solo', 'Solo snippet.')}</body></html>"

    assert google.parse_results(html, 10) == [
        {"position": 1, "title": "Solo", "url": "https://solo.example.com/", "snippet": "Solo snippet."}
    ]


def test_unrecognized_markup_gives_no_results():
    assert google.parse_results("<html><body><p>Nothing here</p></body></html>", 10) == []


def test_search_url_encodes_the_query():
    assert google.search_url("café & bar") == "https://www.google.com/search?q=caf%C3%A9+%26+bar"


@pytest.mark.parametrize(
    "url, html",
    [
        ("https://www.google.com/sorry/index?continue=x", "<html></html>"),
        ("https://consent.google.com/m?continue=x", "<html></html>"),
        (SERP_URL, '<html><form id="captcha-form"></form></html>'),
        (SERP_URL, "<html>Our systems have detected unusual traffic from your computer network.</html>"),
    ],
)
def test_block_pages_are_detected(url, html):
    assert google.blocked_reason(url, html)


def test_normal_results_page_is_not_a_block():
    assert google.blocked_reason(SERP_URL, SERP_HTML) is None


# --- Ranking-page extraction -------------------------------------------------


@pytest.fixture
def article():
    return extract_page(ARTICLE_HTML, "https://alpha.example.com/tools")


def test_extraction_returns_exactly_the_documented_fields(article):
    assert tuple(article) == CONTENT_FIELDS


def test_title_is_extracted(article):
    assert article["title"] == "Alpha: Best Tools"


def test_meta_description_is_extracted(article):
    assert article["meta_description"] == "A guide to local SEO tools."


def test_canonical_is_extracted_and_resolved(article):
    assert article["canonical"] == "https://alpha.example.com/tools?ref=canonical"


def test_h1_is_extracted(article):
    assert article["h1"] == "Best Local SEO Tools"
    assert article["h1_count"] == 1


def test_headings_keep_level_and_order_and_skip_noise(article):
    assert article["headings"] == [
        {"level": 2, "text": "Why it matters"},
        {"level": 3, "text": "Rank tracking"},
        {"level": 4, "text": "Deep heading"},
    ]
    assert article["headings_truncated"] is False


def test_main_text_comes_from_main_and_drops_non_content(article):
    text = article["main_text"]

    assert article["main_text_source"] == "main"
    assert text.startswith("Best Local SEO Tools Local SEO tools help")
    assert "Visible paragraph two." in text
    for noise in (
        "SCRIPT TEXT",
        "NOSCRIPT TEXT",
        "SUBSCRIBE FORM",
        "SIDEBAR PROMO",
        "COOKIE BANNER",
        "CLICK ME",
        "FOOTER",
        "MENU HOME",
        "ACME BRAND",
        "color: red",
    ):
        assert noise not in text


def test_main_text_whitespace_is_normalized(article):
    assert "  " not in article["main_text"]
    assert "\n" not in article["main_text"]
    assert article["main_text"] == article["main_text"].strip()


def test_word_count_matches_main_text(article):
    assert article["main_text_truncated"] is False
    assert article["word_count"] == len(article["main_text"].split())


def test_word_count_is_exact():
    html = "<html><body><p>one two  three\nfour</p><script>five six</script></body></html>"

    page = extract_page(html, "https://example.com/")

    assert page["main_text"] == "one two three four"
    assert page["word_count"] == 4


def test_long_text_is_truncated_on_a_word_boundary_and_flagged():
    html = f"<html><body><main><p>{'alpha beta gamma ' * 200}</p></main></body></html>"

    page = extract_page(html, "https://example.com/", max_text_chars=103)

    assert page["main_text_truncated"] is True
    assert len(page["main_text"]) <= 103
    assert page["main_text"].endswith(("alpha", "beta", "gamma"))
    assert page["word_count"] == 600  # Counts the full text, not the truncated text.


def test_text_at_the_limit_is_not_flagged_as_truncated():
    page = extract_page("<html><body><p>12345 789</p></body></html>", "https://example.com/", 9)

    assert page["main_text"] == "12345 789"
    assert page["main_text_truncated"] is False


def test_single_article_is_used_when_there_is_no_main():
    html = f"<html><body><div>SITE CHROME</div><article><p>{BODY_TEXT}</p></article></body></html>"

    page = extract_page(html, "https://example.com/")

    assert page["main_text_source"] == "article"
    assert "SITE CHROME" not in page["main_text"]


def test_body_is_the_fallback_and_drops_site_header():
    html = (
        "<html><body><header><h1>Site Title</h1>HEADER CHROME</header>"
        f"<div><p>{BODY_TEXT}</p></div><article>One</article><article>Two</article></body></html>"
    )

    page = extract_page(html, "https://example.com/")

    assert page["main_text_source"] == "body"
    assert page["h1"] == "Site Title"  # Read before the header is dropped.
    assert "HEADER CHROME" not in page["main_text"]
    assert page["main_text"].endswith("One Two")


def test_empty_main_shell_falls_back_to_body():
    html = f"<html><body><main><p>Loading</p></main><div><p>{BODY_TEXT}</p></div></body></html>"

    page = extract_page(html, "https://example.com/")

    assert page["main_text_source"] == "body"
    assert "Local SEO tools help" in page["main_text"]


def test_missing_fields_are_null_or_empty_not_invented():
    page = extract_page("<html><body><p>Just text.</p></body></html>", "https://example.com/")

    assert page["title"] is None
    assert page["meta_description"] is None
    assert page["canonical"] is None
    assert page["h1"] is None
    assert page["h1_count"] == 0
    assert page["headings"] == []
    assert page["main_text"] == "Just text."


def test_empty_document_is_handled():
    page = extract_page("", "https://example.com/")

    assert page["main_text"] == ""
    assert page["word_count"] == 0


def test_multiple_h1s_report_first_and_count():
    page = extract_page("<body><h1>First</h1><h1>Second</h1></body>", "https://example.com/")

    assert page["h1"] == "First"
    assert page["h1_count"] == 2


def test_heading_list_is_capped_and_flagged():
    html = "<body>" + "".join(f"<h2>H{i}</h2>" for i in range(MAX_HEADINGS + 5)) + "</body>"

    page = extract_page(html, "https://example.com/")

    assert len(page["headings"]) == MAX_HEADINGS
    assert page["headings_truncated"] is True


def test_extraction_is_deterministic():
    assert extract_page(ARTICLE_HTML, "https://a.example.com/") == extract_page(
        ARTICLE_HTML, "https://a.example.com/"
    )


# --- Collection --------------------------------------------------------------


def run(**overrides):
    kwargs = {"query": QUERY}
    kwargs.update(overrides)
    return collector.collect(**kwargs)


def test_collect_returns_documented_shape(browser):
    result = run()

    assert list(result) == ["request", "serp", "summary"]
    assert result["request"] == {
        "query": QUERY,
        "engine": "google",
        "max_results": 10,
        "max_text_chars": 10000,
    }
    assert list(result["serp"]) == ["url", "fetched_at", "results_found", "results"]
    assert result["serp"]["url"] == SERP_URL
    assert result["serp"]["results_found"] == 4
    assert result["summary"] == {
        "results_requested": 10,
        "results_extracted": 4,
        "pages_successful": 4,
        "pages_failed": 0,
    }
    for item in result["serp"]["results"]:
        assert list(item) == ["position", "title", "url", "snippet", "page"]
        assert list(item["page"]) == [
            "final_url",
            "status",
            *CONTENT_FIELDS,
            "extraction_status",
            "error",
        ]
    json.dumps(result)  # Must be JSON-serializable.


def test_collect_keeps_serp_data_alongside_page_data(browser):
    first, second = run()["serp"]["results"][:2]

    assert first["position"] == 1
    assert first["title"] == "Alpha: 10 Best Local SEO Tools"
    assert first["snippet"] == "Alpha snippet text."
    assert first["page"]["title"] == "Alpha: Best Tools"
    assert first["page"]["status"] == 200
    assert first["page"]["extraction_status"] == "success"
    assert first["page"]["error"] is None
    assert second["url"] == "https://beta.example.com/guide?a=1"
    assert second["page"]["final_url"] == "https://beta.example.com/guide/"


def test_collect_visits_results_in_ranking_order_and_closes_pages(browser):
    run()

    assert browser.visited == [SERP_URL, *EXPECTED_URLS]
    assert all(page.closed for page in browser.pages)


def test_collect_respects_max_results(browser):
    result = run(max_results=2)

    assert [r["url"] for r in result["serp"]["results"]] == EXPECTED_URLS[:2]
    assert browser.visited == [SERP_URL, *EXPECTED_URLS[:2]]
    assert result["summary"]["results_requested"] == 2
    assert result["summary"]["results_extracted"] == 2


def test_collect_passes_text_limit_to_extraction(browser):
    page = run(max_text_chars=100)["serp"]["results"][0]["page"]

    assert len(page["main_text"]) <= 100
    assert page["main_text_truncated"] is True


def test_collect_is_headless_by_default(browser):
    run()

    assert browser.headless is True


@pytest.mark.parametrize(
    "entry, error",
    [
        (TimeoutError("Page.goto: Timeout 20000ms exceeded.\nCall log:\n  - navigating"), "TimeoutError: Page.goto: Timeout 20000ms exceeded."),
        (RuntimeError("net::ERR_NAME_NOT_RESOLVED"), "RuntimeError: net::ERR_NAME_NOT_RESOLVED"),
        (RuntimeError("Download is starting"), "RuntimeError: Download is starting"),
    ],
)
def test_one_failing_page_is_recorded_and_the_rest_continue(browser, entry, error):
    browser.site[EXPECTED_URLS[1]] = entry

    result = run()

    failed = result["serp"]["results"][1]
    assert failed["title"] == "Beta Guide"  # SERP evidence survives the page failure.
    assert failed["page"]["extraction_status"] == "failed"
    assert failed["page"]["error"] == error
    assert all(failed["page"][field] is None for field in ("final_url", "status", *CONTENT_FIELDS))
    assert [r["page"]["extraction_status"] for r in result["serp"]["results"]] == [
        "success",
        "failed",
        "success",
        "success",
    ]
    assert result["summary"]["pages_successful"] == 3
    assert result["summary"]["pages_failed"] == 1
    assert all(page.closed for page in browser.pages)


def test_http_error_page_is_failed_but_keeps_status(browser):
    browser.site[EXPECTED_URLS[2]] = {"status": 403, "html": "<h1>Access denied</h1>"}

    page = run()["serp"]["results"][2]["page"]

    assert page["extraction_status"] == "failed"
    assert page["error"] == "HTTP 403"
    assert page["status"] == 403
    assert page["final_url"] == EXPECTED_URLS[2]
    assert page["h1"] is None  # The error page's content is not reported as evidence.


def test_non_html_response_is_not_extracted(browser):
    browser.site[EXPECTED_URLS[3]] = {"content_type": "application/pdf", "html": "%PDF-1.7"}

    page = run()["serp"]["results"][3]["page"]

    assert page["extraction_status"] == "failed"
    assert page["error"] == "non-HTML content type: application/pdf"
    assert page["main_text"] is None


def test_unsafe_url_is_never_visited(browser):
    page = collector._collect_page(browser, "file:///etc/passwd", 1000, 1000)

    assert page["extraction_status"] == "failed"
    assert page["error"] == "unsafe URL: unsupported scheme 'file'"
    assert browser.visited == []


class FakeRoute:
    def __init__(self, url, resource_type="document"):
        self.request = type("Request", (), {"url": url, "resource_type": resource_type})()
        self.action = None

    def abort(self):
        self.action = "abort"

    def continue_(self):
        self.action = "continue"


@pytest.mark.parametrize(
    "url, resource_type, action",
    [
        ("https://example.com/", "document", "continue"),
        ("https://example.com/app.js", "script", "continue"),
        ("https://example.com/hero.png", "image", "abort"),
        ("https://example.com/video.mp4", "media", "abort"),
        ("http://127.0.0.1:9000/", "document", "abort"),
        ("http://169.254.169.254/latest/", "xhr", "abort"),
    ],
)
def test_request_routing_blocks_heavy_and_local_requests(url, resource_type, action):
    route = FakeRoute(url, resource_type)

    collector._route_request(route)

    assert route.action == action


# --- SERP-level failures -----------------------------------------------------


def test_serp_navigation_failure_is_an_acquisition_error(browser):
    browser.site[SERP_URL] = TimeoutError("Page.goto: Timeout 20000ms exceeded.")

    with pytest.raises(collector.SerpAcquisitionError, match="could not load the google results page"):
        run()
    assert all(page.closed for page in browser.pages)


def test_captcha_is_reported_not_bypassed(browser):
    browser.site[SERP_URL] = {
        "status": 429,
        "final_url": "https://www.google.com/sorry/index?continue=x",
        "html": '<form id="captcha-form"></form>',
    }

    with pytest.raises(collector.SerpBlockedError, match="CAPTCHA"):
        run()
    assert browser.visited == [SERP_URL]  # Nothing else was attempted.


def test_serp_http_error_is_an_acquisition_error(browser):
    browser.site[SERP_URL] = {"status": 503, "html": "<h1>Service unavailable</h1>"}

    with pytest.raises(collector.SerpAcquisitionError, match="HTTP 503"):
        run()


def test_unparseable_serp_is_a_parse_error(browser):
    browser.site[SERP_URL] = {"html": "<html><body><p>Redesigned page</p></body></html>"}

    with pytest.raises(collector.SerpParseError, match="no organic results could be parsed"):
        run()


def test_missing_playwright_is_a_browser_startup_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    with pytest.raises(collector.BrowserStartupError, match="Playwright is not installed"):
        run()


# --- Input validation --------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * 501])
def test_invalid_query_is_rejected(browser, bad):
    with pytest.raises(ValueError, match="query"):
        run(query=bad)
    assert browser.visited == []


def test_query_whitespace_is_normalized(browser):
    assert run(query="  best  local seo   tools ")["request"]["query"] == QUERY


@pytest.mark.parametrize("bad", ["yahoo", "", "Google", "BING", None])
def test_unsupported_engine_is_rejected(browser, bad):
    with pytest.raises(ValueError, match="Unsupported engine"):
        run(engine=bad)
    assert browser.visited == []


@pytest.mark.parametrize("bad", [0, -1, 21, "10", 2.5, True])
def test_invalid_max_results_is_rejected(browser, bad):
    with pytest.raises(ValueError, match="max_results"):
        run(max_results=bad)
    assert browser.visited == []


@pytest.mark.parametrize("bad", [0, 99, 200001, "1000"])
def test_invalid_max_text_chars_is_rejected(browser, bad):
    with pytest.raises(ValueError, match="max_text_chars"):
        run(max_text_chars=bad)


@pytest.mark.parametrize("bad", [0, 121, "20"])
def test_invalid_timeout_is_rejected(browser, bad):
    with pytest.raises(ValueError, match="timeout"):
        run(timeout=bad)


# --- CLI ---------------------------------------------------------------------

CLI_ARGS = ["--query", QUERY]


def test_cli_writes_json_to_stdout(browser, capsys):
    exit_code = main(CLI_ARGS + ["--engine", "google", "--max-results", "3"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["request"]["max_results"] == 3
    assert [r["url"] for r in result["serp"]["results"]] == EXPECTED_URLS[:3]
    assert result["summary"]["pages_successful"] == 3


def test_cli_defaults(browser, capsys):
    main(CLI_ARGS)

    assert json.loads(capsys.readouterr().out)["request"] == {
        "query": QUERY,
        "engine": "google",
        "max_results": 10,
        "max_text_chars": 10000,
    }


def test_cli_headed_flag_disables_headless(browser, capsys):
    main(CLI_ARGS + ["--headed"])

    assert browser.headless is False


def test_cli_output_is_ascii_and_round_trips_non_ascii(browser, capsys):
    browser.site[EXPECTED_URLS[0]] = {"html": "<title>واٹر پروفنگ</title><body><p>café</p></body>"}

    main(CLI_ARGS)

    out = capsys.readouterr().out
    assert out.isascii()
    assert json.loads(out)["serp"]["results"][0]["page"]["title"] == "واٹر پروفنگ"


def test_cli_partial_failure_still_succeeds(browser, capsys):
    browser.site[EXPECTED_URLS[0]] = RuntimeError("net::ERR_CONNECTION_REFUSED")

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["summary"]["pages_failed"] == 1


@pytest.mark.parametrize(
    "args, message",
    [
        (["--query", "   "], "query must be a non-empty string"),
        (CLI_ARGS + ["--engine", "yahoo"], "Unsupported engine 'yahoo'"),
        (CLI_ARGS + ["--max-results", "0"], "max_results must be between 1 and 20"),
        (CLI_ARGS + ["--max-text-chars", "5"], "max_text_chars must be between"),
        (CLI_ARGS + ["--timeout", "0"], "timeout must be between"),
    ],
)
def test_cli_invalid_input_exits_2_with_clean_stdout(browser, capsys, args, message):
    exit_code = main(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert message in captured.err
    assert browser.visited == []


@pytest.mark.parametrize("args", [[], ["--query"], CLI_ARGS + ["--max-results", "ten"], CLI_ARGS + ["--bogus"]])
def test_cli_usage_error_exits_2(browser, capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        main(args)

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


def test_cli_browser_startup_failure_exits_3(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.startswith("error: BrowserStartupError: Playwright is not installed")


def test_cli_blocked_serp_exits_4_with_clean_stdout(browser, capsys):
    browser.site[SERP_URL] = {"final_url": "https://www.google.com/sorry/index", "status": 429}

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert captured.err.startswith("error: SerpBlockedError: Google served its automated-traffic")
    assert "Traceback" not in captured.err
    assert captured.err.count("\n") == 1


def test_cli_unparseable_serp_exits_4(browser, capsys):
    browser.site[SERP_URL] = {"html": "<html></html>"}

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert captured.err.startswith("error: SerpParseError:")


def test_cli_unexpected_failure_exits_1_without_traceback(browser, monkeypatch, capsys):
    monkeypatch.setattr(google, "parse_results", lambda *args: 1 / 0)

    exit_code = main(CLI_ARGS)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "error: ZeroDivisionError: division by zero\n"


# --- Bing --------------------------------------------------------------------
#
# As with the Google fixture, this HTML is a simplified stand-in, not a copy of
# Bing's current markup. These tests are not live verification.


def bing_tracked(url, prefix="a1"):
    """A Bing click-tracking link (/ck/a) wrapping ``url``."""
    encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&amp;&amp;p=abc123&amp;u={prefix}{encoded}&amp;ntb=1"


def bing_result(url, title, snippet_html=""):
    return f'<li class="b_algo"><h2><a href="{url}">{title}</a></h2>{snippet_html}</li>'


BING_HTML = f"""
<html><head><title>best local seo tools - Search</title></head><body>
<nav class="b_scopebar">
  <a href="/images/search?q=best+local+seo+tools">Images</a>
  <a href="/videos/search?q=best+local+seo+tools">Videos</a>
</nav>
<ol id="b_results">
  <li class="b_ad b_adTop"><ul>
    {bing_result("https://ads.example.com/buy", "Sponsored tool", '<div class="b_caption"><p>Ad text.</p></div>')}
  </ul></li>
  {bing_result("https://alpha.example.com/tools", "Alpha: 10 <strong>Best</strong> Local SEO Tools",
               '<div class="b_caption"><p>Alpha   snippet' + chr(10) + ' text.</p></div>')}
  {bing_result(bing_tracked("https://beta.example.com/guide?a=1"), "Beta Guide",
               '<p class="b_lineclamp2">Beta snippet.</p>')}
  <li class="b_ans"><ul>
    {bing_result("https://paa.example.com/answer", "People also ask: what is local SEO?")}
  </ul></li>
  {bing_result("https://alpha.example.com/tools#pricing", "Alpha duplicate", '<div class="b_caption"><p>Dup.</p></div>')}
  {bing_result("https://www.bing.com/search?q=more+tools", "More results from Bing")}
  {bing_result("/videos/search?q=local+seo", "Videos of local seo")}
  {bing_result(bing_tracked("https://www.bing.com/maps?q=seo"), "Tracked link back to Bing")}
  {bing_result(bing_tracked("https://undecodable.example.com/", prefix="zz"), "Unknown wrapper prefix")}
  {bing_result("https://www.bing.com/ck/a?p=abc&amp;u=a1%%%notbase64", "Corrupt wrapper")}
  {bing_result("https://www.bing.com/ck/a?p=abc", "Wrapper without destination")}
  {bing_result("javascript:void(0)", "Script link")}
  {bing_result("file:///etc/passwd", "File link")}
  {bing_result("http://127.0.0.1:8080/admin", "Loopback link")}
  {bing_result("https://notitle.example.com/", "  ")}
  <li class="b_algo"><div class="b_caption"><p>Result without a title link.</p></div></li>
  <li class="b_algo"><h2>Title without a link</h2></li>
  <li class="b_algo">
    <h2><a href="https://gamma.example.com/">Gamma Home</a></h2>
    <div class="b_deep"><h3><a href="https://gamma.example.com/pricing">Pricing</a></h3></div>
  </li>
  {bing_result("https://delta.example.com/post", "Delta Post", '<div class="b_caption"><p></p><p>Delta snippet.</p></div>')}
  <li class="b_pag"><a href="/search?q=best+local+seo+tools&amp;first=11">2</a></li>
</ol>
<aside id="b_context"><ul>
  {bing_result("https://sidebar.example.com/", "Sidebar entity")}
</ul></aside>
</body></html>
"""

BING_SERP_URL = bing.search_url(QUERY)


@pytest.fixture
def bing_browser(browser):
    """The fake browser, additionally serving the Bing results page."""
    browser.site[BING_SERP_URL] = {"html": BING_HTML}
    return browser


def test_bing_search_url_encodes_the_query():
    assert BING_SERP_URL == "https://www.bing.com/search?q=best+local+seo+tools"
    assert bing.search_url("café & bar") == "https://www.bing.com/search?q=caf%C3%A9+%26+bar"


def test_bing_organic_results_are_parsed_in_order():
    results = bing.parse_results(BING_HTML, 10)

    assert [r["url"] for r in results] == EXPECTED_URLS
    assert [r["position"] for r in results] == [1, 2, 3, 4]
    assert [r["title"] for r in results] == [
        "Alpha: 10 Best Local SEO Tools",
        "Beta Guide",
        "Gamma Home",
        "Delta Post",
    ]


def test_bing_snippets_are_normalized_and_null_when_absent():
    results = bing.parse_results(BING_HTML, 10)

    assert [r["snippet"] for r in results] == [
        "Alpha snippet text.",
        "Beta snippet.",
        None,
        "Delta snippet.",
    ]


def test_bing_tracking_links_are_decoded_to_their_destination():
    assert bing.parse_results(BING_HTML, 10)[1]["url"] == "https://beta.example.com/guide?a=1"


@pytest.mark.parametrize(
    "excluded",
    [
        "ads.example.com",  # ad block
        "paa.example.com",  # answer box
        "sidebar.example.com",  # outside the results column
        "bing.com",  # navigation, utility and undecodable tracking links
        "undecodable.example.com",
        "javascript:",
        "file:",
        "127.0.0.1",
        "notitle.example.com",
        "gamma.example.com/pricing",  # deep link under a result, not a result
    ],
)
def test_bing_non_organic_internal_and_malformed_results_are_excluded(excluded):
    assert not any(excluded in r["url"] for r in bing.parse_results(BING_HTML, 10))


def test_bing_duplicate_destinations_are_collapsed():
    urls = [r["url"] for r in bing.parse_results(BING_HTML, 10)]

    assert len([u for u in urls if u.startswith("https://alpha.example.com/tools")]) == 1


@pytest.mark.parametrize("limit, expected", [(1, 1), (2, 2), (4, 4), (10, 4)])
def test_bing_max_results_caps_without_inventing_results(limit, expected):
    results = bing.parse_results(BING_HTML, limit)

    assert [r["url"] for r in results] == EXPECTED_URLS[:expected]


def test_bing_results_are_found_without_the_results_container():
    html = f"<html><body><ul>{bing_result('https://solo.example.com/', 'Solo')}</ul></body></html>"

    assert bing.parse_results(html, 10) == [
        {"position": 1, "title": "Solo", "url": "https://solo.example.com/", "snippet": None}
    ]


@pytest.mark.parametrize("html", ["", "<html><body><p>Nothing here</p></body></html>", SERP_HTML])
def test_bing_unrecognized_markup_gives_no_results(html):
    assert bing.parse_results(html, 10) == []


def test_google_parser_does_not_read_bing_markup():
    assert google.parse_results(BING_HTML, 10) == []


@pytest.mark.parametrize(
    "url, html",
    [
        ("https://www.bing.com/turing/captcha/challenge?q=x", "<html></html>"),
        (BING_SERP_URL, '<html><div id="b_captcha"></div></html>'),
        (BING_SERP_URL, "<html><h1>One last step</h1>Please solve the challenge below to continue.</html>"),
        (BING_SERP_URL, '<html><script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script></html>'),
    ],
)
def test_bing_block_pages_are_detected(url, html):
    assert bing.blocked_reason(url, html)


def test_bing_normal_results_page_is_not_a_block():
    assert bing.blocked_reason(BING_SERP_URL, BING_HTML) is None


@pytest.mark.parametrize("name", ["google", "bing"])
def test_every_engine_provides_the_engine_interface(name):
    engine = collector.ENGINES[name]

    assert isinstance(engine.READY_SELECTOR, str)
    assert all(callable(getattr(engine, f)) for f in ("search_url", "blocked_reason", "parse_results"))


def test_bing_collect_returns_documented_shape(bing_browser):
    result = run(engine="bing")

    assert result["request"]["engine"] == "bing"
    assert result["serp"]["url"] == BING_SERP_URL
    assert [r["url"] for r in result["serp"]["results"]] == EXPECTED_URLS
    assert result["summary"] == {
        "results_requested": 10,
        "results_extracted": 4,
        "pages_successful": 4,
        "pages_failed": 0,
    }
    for item in result["serp"]["results"]:
        assert list(item) == ["position", "title", "url", "snippet", "page"]
        assert list(item["page"]) == ["final_url", "status", *CONTENT_FIELDS, "extraction_status", "error"]


def test_bing_collect_only_talks_to_bing_and_the_ranking_pages(bing_browser):
    run(engine="bing", max_results=2)

    assert bing_browser.visited == [BING_SERP_URL, *EXPECTED_URLS[:2]]
    assert all(page.closed for page in bing_browser.pages)


def test_bing_results_go_through_the_generic_page_extractor(bing_browser, monkeypatch):
    calls = []

    def spy(html, base_url, max_text_chars):
        calls.append(base_url)
        return extract_page(html, base_url, max_text_chars)

    monkeypatch.setattr(collector, "extract_page", spy)

    bing_pages = [r["page"] for r in run(engine="bing")["serp"]["results"]]
    google_pages = [r["page"] for r in run(engine="google")["serp"]["results"]]

    assert calls[:4] == [EXPECTED_URLS[0], "https://beta.example.com/guide/", *EXPECTED_URLS[2:]]
    assert len(calls) == 8
    assert bing_pages[0]["title"] == "Alpha: Best Tools"
    assert bing_pages[0]["h1"] == "Best Local SEO Tools"
    assert bing_pages == google_pages  # Same pages, same evidence, either engine.
    assert not hasattr(bing, "extract_page")


def test_bing_page_failure_is_recorded_and_the_rest_continue(bing_browser):
    bing_browser.site[EXPECTED_URLS[2]] = RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    result = run(engine="bing")

    assert [r["page"]["extraction_status"] for r in result["serp"]["results"]] == [
        "success",
        "success",
        "failed",
        "success",
    ]
    assert result["summary"]["pages_failed"] == 1


def test_bing_captcha_is_reported_not_bypassed(bing_browser):
    bing_browser.site[BING_SERP_URL] = {
        "final_url": "https://www.bing.com/turing/captcha/challenge",
        "html": "<html>Please solve the challenge below to continue</html>",
    }

    with pytest.raises(collector.SerpBlockedError, match="Bing served its CAPTCHA challenge page"):
        run(engine="bing")
    assert bing_browser.visited == [BING_SERP_URL]  # Nothing else was attempted.


def test_bing_unparseable_serp_is_a_parse_error(bing_browser):
    bing_browser.site[BING_SERP_URL] = {"html": "<html><body><p>Redesigned page</p></body></html>"}

    with pytest.raises(collector.SerpParseError, match="from the bing results page"):
        run(engine="bing")


def test_bing_serp_navigation_failure_is_an_acquisition_error(bing_browser):
    bing_browser.site[BING_SERP_URL] = TimeoutError("Page.goto: Timeout 20000ms exceeded.")

    with pytest.raises(collector.SerpAcquisitionError, match="could not load the bing results page"):
        run(engine="bing")


@pytest.mark.parametrize("engine, serp_url", [("google", SERP_URL), ("bing", BING_SERP_URL)])
def test_cli_accepts_each_supported_engine(bing_browser, capsys, engine, serp_url):
    exit_code = main(CLI_ARGS + ["--engine", engine, "--max-results", "3", "--headed"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["request"]["engine"] == engine
    assert result["serp"]["url"] == serp_url
    assert [r["url"] for r in result["serp"]["results"]] == EXPECTED_URLS[:3]
    assert bing_browser.visited[0] == serp_url


def test_cli_default_engine_is_still_google(bing_browser, capsys):
    main(CLI_ARGS)

    assert json.loads(capsys.readouterr().out)["request"]["engine"] == "google"
    assert bing_browser.visited[0] == SERP_URL


def test_cli_blocked_bing_exits_4_with_clean_stdout(bing_browser, capsys):
    bing_browser.site[BING_SERP_URL] = {"final_url": "https://www.bing.com/turing/captcha/challenge"}

    exit_code = main(CLI_ARGS + ["--engine", "bing"])

    captured = capsys.readouterr()
    assert exit_code == 4
    assert captured.out == ""
    assert captured.err.startswith("error: SerpBlockedError: Bing served its CAPTCHA challenge page")
    assert captured.err.count("\n") == 1


def test_cli_unsupported_engine_lists_supported_engines(bing_browser, capsys):
    exit_code = main(CLI_ARGS + ["--engine", "duckduckgo"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "error: Unsupported engine 'duckduckgo'. Supported: ['bing', 'google']\n"
    assert bing_browser.visited == []
