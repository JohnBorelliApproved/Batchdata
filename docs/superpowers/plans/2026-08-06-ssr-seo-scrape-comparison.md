# SSR vs. Client-Rendered SEO Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rerunnable Python tool that scrapes 3 matched page-pairs (home/about/contact) across a GHL AI Studio (client-rendered) site and an HL Site Builder (server-rendered) site, both raw and Playwright-rendered, and produces `report.md` documenting exactly what SEO-relevant content survives without JS rendering, what's lost, and mitigation options.

**Architecture:** A small, flat set of pure-function modules (`extract.py`, `fetch_raw.py`, `fetch_rendered.py`, `report.py`) wired together by one orchestrator (`compare.py`). Extraction and report generation are pure functions tested with static/local fixtures — no real network calls in the test suite. The two network-fetching functions are tested against a local `http.server` fixture that serves JS-delayed content, so tests prove the raw-vs-rendered mechanism itself without depending on the real target sites being up.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `playwright` (sync API, headless Chromium), `pytest`. Isolated venv, no changes to the main Flask app's dependencies.

## Global Constraints

- Lives entirely under `ssr-seo-comparison/` at the repo root, with its own `venv/` and `requirements.txt`. Do not add anything to the main app's `requirements.txt` or touch `main.py`.
- Only the 6 real, published URLs from the spec are used — no preview/staging domains, no vibepreview.com.
- No bypassing Cloudflare or any bot-detection on any tested site.
- Text/SEO-signal content only — no visual/styling comparison.
- Final report is Markdown, written to `ssr-seo-comparison/output/report.md`.
- The report must reflect what the data actually shows (diagnostic framing) — findings and mitigation text describe options and tradeoffs, not a predetermined verdict.
- `ssr-seo-comparison/venv/` and `ssr-seo-comparison/output/` are generated/local — gitignored, not committed.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `ssr-seo-comparison/requirements.txt`
- Create: `ssr-seo-comparison/.gitignore`
- Create: `ssr-seo-comparison/tests/__init__.py` (empty, makes tests a package for consistent imports)

**Interfaces:**
- Produces: an activated venv at `ssr-seo-comparison/venv/` with `requests`, `beautifulsoup4`, `playwright`, and `pytest` installed, plus Playwright's Chromium browser binary installed. All later tasks assume this environment exists and is activated when running `pytest` or `python compare.py`.

- [ ] **Step 1: Create the project folder and venv**

```bash
mkdir -p ssr-seo-comparison/tests
cd ssr-seo-comparison
python3 -m venv venv
source venv/bin/activate
```

- [ ] **Step 2: Write `requirements.txt`**

```
requests
beautifulsoup4
playwright
pytest
```

- [ ] **Step 3: Install dependencies and Playwright's browser binary**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected: all four packages install cleanly, and `playwright install chromium` downloads the Chromium binary Playwright drives (this is separate from `pip install` and required before any Playwright script will run).

- [ ] **Step 4: Write `.gitignore`**

```
venv/
output/
__pycache__/
*.pyc
```

- [ ] **Step 5: Create empty `tests/__init__.py`**

```bash
touch tests/__init__.py
```

- [ ] **Step 6: Verify the environment**

Run: `python -c "import requests, bs4, playwright, pytest; print('ok')"`
Expected: prints `ok` with no import errors.

- [ ] **Step 7: Commit**

```bash
cd ..
git add ssr-seo-comparison/requirements.txt ssr-seo-comparison/.gitignore ssr-seo-comparison/tests/__init__.py
git commit -m "Scaffold ssr-seo-comparison project

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(`venv/` is excluded by `.gitignore`, so it won't be staged.)

---

### Task 2: SEO Field Extraction (`extract.py`)

**Files:**
- Create: `ssr-seo-comparison/extract.py`
- Test: `ssr-seo-comparison/tests/test_extract.py`

**Interfaces:**
- Produces: `extract_seo_fields(html: str, url: str) -> dict` with keys:
  `url` (str), `title` (str|None), `meta_description` (str|None), `canonical` (str|None),
  `og_tags` (dict[str,str]), `twitter_tags` (dict[str,str]),
  `headings` (dict with keys `"h1"` and `"h2"`, each a list[str]),
  `body_text` (str, whitespace-collapsed, scripts/styles stripped),
  `word_count` (int), `internal_links` (sorted list[str], same-domain only),
  `json_ld` (list[str], raw text of each `<script type="application/ld+json">` block).
  This function does not know about HTTP status codes — callers add `status_code` to the returned dict themselves.
- Consumes: nothing from other tasks (pure function, only needs `beautifulsoup4`).

- [ ] **Step 1: Write the failing test**

```python
# ssr-seo-comparison/tests/test_extract.py
from extract import extract_seo_fields

SAMPLE_HTML = """
<html>
  <head>
    <title>Test Page Title</title>
    <meta name="description" content="A test description.">
    <link rel="canonical" href="https://example.com/canonical-page">
    <meta property="og:title" content="OG Title">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary">
    <script type="application/ld+json">{"@type": "Organization"}</script>
  </head>
  <body>
    <h1>Main Heading</h1>
    <h2>Sub Heading One</h2>
    <h2>Sub Heading Two</h2>
    <p>Some visible body copy here.</p>
    <a href="https://example.com/about">About</a>
    <a href="https://external-site.com/other">External</a>
    <script>console.log("should be stripped");</script>
    <style>.hidden { display: none; }</style>
  </body>
</html>
"""


def test_extracts_title():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["title"] == "Test Page Title"


def test_extracts_meta_description():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["meta_description"] == "A test description."


def test_extracts_canonical():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["canonical"] == "https://example.com/canonical-page"


def test_extracts_og_and_twitter_tags():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["og_tags"] == {"og:title": "OG Title", "og:type": "website"}
    assert result["twitter_tags"] == {"twitter:card": "summary"}


def test_extracts_headings():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["headings"]["h1"] == ["Main Heading"]
    assert result["headings"]["h2"] == ["Sub Heading One", "Sub Heading Two"]


def test_body_text_excludes_scripts_and_styles():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert "should be stripped" not in result["body_text"]
    assert "display: none" not in result["body_text"]
    assert "Some visible body copy here." in result["body_text"]


def test_word_count_matches_body_text():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["word_count"] == len(result["body_text"].split())
    assert result["word_count"] > 0


def test_internal_links_only_same_domain():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["internal_links"] == ["https://example.com/about"]


def test_extracts_json_ld():
    result = extract_seo_fields(SAMPLE_HTML, "https://example.com/")
    assert result["json_ld"] == ['{"@type": "Organization"}']


def test_missing_fields_are_none_or_empty():
    result = extract_seo_fields("<html><head></head><body></body></html>", "https://example.com/")
    assert result["title"] is None
    assert result["meta_description"] is None
    assert result["canonical"] is None
    assert result["og_tags"] == {}
    assert result["headings"]["h1"] == []
    assert result["body_text"] == ""
    assert result["word_count"] == 0
    assert result["internal_links"] == []
    assert result["json_ld"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ssr-seo-comparison && source venv/bin/activate && pytest tests/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'extract'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

```python
# ssr-seo-comparison/extract.py
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def extract_seo_fields(html, url):
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (
        meta_description_tag.get("content", "").strip()
        if meta_description_tag
        else None
    )

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = canonical_tag.get("href") if canonical_tag else None

    og_tags = {}
    for tag in soup.find_all("meta", attrs={"property": True}):
        prop = tag.get("property", "")
        if prop.startswith("og:"):
            og_tags[prop] = tag.get("content", "")

    twitter_tags = {}
    for tag in soup.find_all("meta", attrs={"name": True}):
        name = tag.get("name", "")
        if name.startswith("twitter:"):
            twitter_tags[name] = tag.get("content", "")

    headings = {
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1")],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")],
    }

    body = soup.find("body")
    if body:
        for tag in body.find_all(["script", "style"]):
            tag.decompose()
        body_text = " ".join(body.get_text(separator=" ").split())
    else:
        body_text = ""

    domain = urlparse(url).netloc
    internal_links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if urlparse(href).netloc == domain:
            internal_links.add(href)

    json_ld = [
        script.get_text(strip=True)
        for script in soup.find_all("script", attrs={"type": "application/ld+json"})
    ]

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "canonical": canonical,
        "og_tags": og_tags,
        "twitter_tags": twitter_tags,
        "headings": headings,
        "body_text": body_text,
        "word_count": len(body_text.split()) if body_text else 0,
        "internal_links": sorted(internal_links),
        "json_ld": json_ld,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extract.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add ssr-seo-comparison/extract.py ssr-seo-comparison/tests/test_extract.py
git commit -m "Add SEO field extraction for ssr-seo-comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Raw HTTP Fetch (`fetch_raw.py`)

**Files:**
- Create: `ssr-seo-comparison/fetch_raw.py`
- Test: `ssr-seo-comparison/tests/test_fetch_raw.py`

**Interfaces:**
- Produces: `fetch_raw(url: str, timeout: int = 15) -> tuple[str, int]` returning `(html_text, status_code)`. No JS execution — this is the plain HTTP response body.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing test**

This test spins up a real local HTTP server (stdlib `http.server`) serving a page whose body is only fully populated by a `<script>` after page load — proving `fetch_raw` captures the pre-JS state, with no mocking and no dependency on the real target sites.

```python
# ssr-seo-comparison/tests/test_fetch_raw.py
import functools
import http.server
import threading

import pytest

from fetch_raw import fetch_raw

JS_DELAYED_HTML = """<html>
<head><title>Local Test Page</title></head>
<body>
<div id="root">Loading...</div>
<script>
document.getElementById('root').innerText = 'Rendered Content Here';
</script>
</body>
</html>"""


@pytest.fixture
def local_server(tmp_path):
    (tmp_path / "index.html").write_text(JS_DELAYED_HTML)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
    )
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/index.html"
    server.shutdown()
    thread.join()


def test_fetch_raw_returns_status_200(local_server):
    _, status_code = fetch_raw(local_server)
    assert status_code == 200


def test_fetch_raw_does_not_execute_js(local_server):
    html, _ = fetch_raw(local_server)
    assert "Loading..." in html
    assert "Rendered Content Here" not in html
```

Note: this test uses a real `<script>` that runs synchronously in a browser DOM, but since `fetch_raw` never executes JavaScript at all, the assertion holds regardless of timing — there's no race condition here.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch_raw.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fetch_raw'`.

- [ ] **Step 3: Write the implementation**

```python
# ssr-seo-comparison/fetch_raw.py
import requests

USER_AGENT = "Mozilla/5.0 (compatible; SSRComparisonBot/1.0; +https://lionsoftsolutions.com)"


def fetch_raw(url, timeout=15):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    return response.text, response.status_code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_raw.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add ssr-seo-comparison/fetch_raw.py ssr-seo-comparison/tests/test_fetch_raw.py
git commit -m "Add raw HTTP fetch for ssr-seo-comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Playwright Rendered Fetch (`fetch_rendered.py`)

**Files:**
- Create: `ssr-seo-comparison/fetch_rendered.py`
- Test: `ssr-seo-comparison/tests/test_fetch_rendered.py`

**Interfaces:**
- Produces: `fetch_rendered(url: str, wait_ms: int = 2000, timeout: int = 30000) -> tuple[str, int | None]` returning `(rendered_html, status_code)`. Loads the page in headless Chromium, waits for network-idle, then waits an additional `wait_ms` for any post-load JS (e.g. `setTimeout`-based rendering), and returns `page.content()` — the fully rendered DOM as HTML.
- Consumes: nothing from other tasks (uses the Playwright Chromium binary installed in Task 1).

- [ ] **Step 1: Write the failing test**

Reuses the same local-server pattern as Task 3, but this time asserts the *opposite*: rendering does pick up the JS-injected content. This is the same server fixture duplicated here (not imported from `test_fetch_raw.py`) so this test file has no cross-file dependency.

```python
# ssr-seo-comparison/tests/test_fetch_rendered.py
import functools
import http.server
import threading

import pytest

from fetch_rendered import fetch_rendered

JS_DELAYED_HTML = """<html>
<head><title>Local Test Page</title></head>
<body>
<div id="root">Loading...</div>
<script>
setTimeout(function() {
  document.getElementById('root').innerText = 'Rendered Content Here';
}, 300);
</script>
</body>
</html>"""


@pytest.fixture
def local_server(tmp_path):
    (tmp_path / "index.html").write_text(JS_DELAYED_HTML)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)
    )
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/index.html"
    server.shutdown()
    thread.join()


def test_fetch_rendered_returns_status_200(local_server):
    _, status_code = fetch_rendered(local_server, wait_ms=1000)
    assert status_code == 200


def test_fetch_rendered_executes_delayed_js(local_server):
    html, _ = fetch_rendered(local_server, wait_ms=1000)
    assert "Rendered Content Here" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch_rendered.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fetch_rendered'`.

- [ ] **Step 3: Write the implementation**

```python
# ssr-seo-comparison/fetch_rendered.py
from playwright.sync_api import sync_playwright


def fetch_rendered(url, wait_ms=2000, timeout=30000):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            response = page.goto(url, wait_until="networkidle", timeout=timeout)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            status_code = response.status if response else None
            return html, status_code
        finally:
            browser.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_rendered.py -v`
Expected: both tests PASS. (This test is slower than the others — it launches a real browser — expect a few seconds per test.)

- [ ] **Step 5: Commit**

```bash
cd ..
git add ssr-seo-comparison/fetch_rendered.py ssr-seo-comparison/tests/test_fetch_rendered.py
git commit -m "Add Playwright rendered fetch for ssr-seo-comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Report Generation (`report.py`)

**Files:**
- Create: `ssr-seo-comparison/report.py`
- Test: `ssr-seo-comparison/tests/test_report.py`

**Interfaces:**
- Produces: `generate_report(pages: list[dict]) -> str` returning the full Markdown report as a string. `pages` is a list of dicts shaped as:
  ```python
  {
      "page": "home",
      "platforms": {
          "ai_studio": {"url": "...", "raw": {...extract_seo_fields dict + status_code...}, "rendered": {...}},
          "site_builder": {"url": "...", "raw": {...}, "rendered": {...}},
      },
  }
  ```
  where each `raw`/`rendered` dict is exactly what `extract_seo_fields` returns (Task 2) plus a `status_code` key added by the caller.
- Consumes: the `extract_seo_fields` return shape from Task 2 (as a plain dict — no import needed, `report.py` only consumes the data shape, not the function).

- [ ] **Step 1: Write the failing test**

```python
# ssr-seo-comparison/tests/test_report.py
from report import generate_report


def make_extract_result(title=None, meta_description=None, body_text="", h1=None, links=None):
    return {
        "url": "https://example.com/",
        "status_code": 200,
        "title": title,
        "meta_description": meta_description,
        "canonical": None,
        "og_tags": {},
        "twitter_tags": {},
        "headings": {"h1": h1 or [], "h2": []},
        "body_text": body_text,
        "word_count": len(body_text.split()) if body_text else 0,
        "internal_links": links or [],
        "json_ld": [],
    }


def make_pages():
    ai_raw = make_extract_result(title="AI Studio Home")
    ai_rendered = make_extract_result(
        title="AI Studio Home",
        meta_description="AI Studio meta",
        body_text="Full rendered body copy for AI Studio home page.",
        h1=["Welcome"],
        links=["https://studio.example.com/about"],
    )
    sb_raw = make_extract_result(
        title="Site Builder Home",
        meta_description="Site Builder meta",
        body_text="Full raw body copy for Site Builder home page.",
        h1=["Welcome"],
        links=["https://example.com/about"],
    )
    sb_rendered = sb_raw

    return [
        {
            "page": "home",
            "platforms": {
                "ai_studio": {
                    "url": "https://studio.example.com/",
                    "raw": ai_raw,
                    "rendered": ai_rendered,
                },
                "site_builder": {
                    "url": "https://example.com/home",
                    "raw": sb_raw,
                    "rendered": sb_rendered,
                },
            },
        }
    ]


def test_report_includes_page_names():
    report = generate_report(make_pages())
    assert "home" in report.lower()


def test_report_summary_section_present():
    report = generate_report(make_pages())
    assert "## Summary" in report


def test_report_flags_body_text_missing_raw_for_ai_studio():
    report = generate_report(make_pages())
    assert "Visible body text" in report


def test_report_findings_section_present():
    report = generate_report(make_pages())
    assert "## Findings" in report
    assert "Mitigation options" in report


def test_report_includes_text_samples():
    report = generate_report(make_pages())
    assert "Full rendered body copy for AI Studio home page." in report
    assert "Full raw body copy for Site Builder home page." in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Write the implementation**

```python
# ssr-seo-comparison/report.py
FIELD_LABELS = {
    "title": "Title tag",
    "meta_description": "Meta description",
    "headings": "Headings (H1/H2)",
    "body_text": "Visible body text",
    "internal_links": "Internal links",
    "json_ld": "Structured data (JSON-LD)",
}

PLATFORM_LABELS = {
    "ai_studio": "AI Studio",
    "site_builder": "Site Builder",
}

MITIGATION_TEXT = """If body text, headings, or internal links are missing from the raw HTML response,
a non-rendering crawler indexes the page as effectively empty apart from whatever
survives in `<head>` (title, meta description, OG tags). Three mitigation paths
exist, in increasing order of effort:

1. **Server-injected meta tags only** -- if title/meta description/OG tags already
   survive raw (as they typically do with a React app's default `index.html`), the
   page can still generate reasonable search snippets and social previews even if
   body content isn't indexed. This doesn't fix content indexing, only the
   snippet/preview layer.
2. **Dynamic rendering / prerendering** -- detect crawler user-agents server-side
   and serve a prerendered (fully rendered) HTML snapshot to them while serving the
   normal client-rendered app to real users. This closes the gap without changing
   the app itself, at the cost of running and maintaining a prerendering service
   (e.g. Prerender.io, Rendertron) in front of the site.
3. **Migrate to an SSR/SSG framework** (Next.js, Remix, Astro, etc.) -- the app
   itself emits full HTML on first response. This is the most complete fix but
   requires a platform change AI Studio doesn't currently support; not actionable
   without GoHighLevel building SSR into AI Studio itself.

Whether option 1 alone is sufficient depends on how much of a given page's value is
in body content that needs indexing (blog posts, service descriptions) versus a
simple contact/landing page where title and meta description carry most of the SEO
weight. The per-page results above indicate which case applies to each page tested.

This test does not confirm what Googlebot does with these pages in practice.
Google's indexing pipeline queues JS pages for a second rendering pass; the AI
Studio pages would need to survive Google's render-budget and time-to-render
window, which a one-off local scrape cannot measure. Google Search Console's URL
Inspection tool is the way to confirm actual indexing outcomes over time.
"""


def _field_present(data, field):
    value = data.get(field)
    if field == "headings":
        return bool(value.get("h1") or value.get("h2"))
    if isinstance(value, (str,)):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(value)


def _mark(present):
    return "present" if present else "MISSING"


def _summary_rows(pages):
    rows = []
    for page in pages:
        for platform_key, platform_label in PLATFORM_LABELS.items():
            platform_data = page["platforms"][platform_key]
            raw = platform_data["raw"]
            rendered = platform_data["rendered"]
            row = f"| {page['page']} | {platform_label} "
            for field in FIELD_LABELS:
                row += f"| {_mark(_field_present(raw, field))} | {_mark(_field_present(rendered, field))} "
            row += "|"
            rows.append(row)
    return rows


def _summary_table(pages):
    header_fields = " | ".join(
        f"{label} (raw) | {label} (rendered)" for label in FIELD_LABELS.values()
    )
    header = f"| Page | Platform | {header_fields} |"
    separator = "|" + "---|" * (2 + 2 * len(FIELD_LABELS))
    return "\n".join([header, separator] + _summary_rows(pages))


def _text_sample(text, length=300):
    text = text.strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def _page_detail(page):
    lines = [f"### {page['page'].capitalize()}", ""]
    for platform_key, platform_label in PLATFORM_LABELS.items():
        platform_data = page["platforms"][platform_key]
        lines.append(f"**{platform_label}** ({platform_data['url']})")
        lines.append("")
        for stage_key, stage_label in (("raw", "Raw HTML"), ("rendered", "Rendered")):
            data = platform_data[stage_key]
            lines.append(f"- {stage_label} status: {data.get('status_code')}")
            lines.append(f"- {stage_label} title: {data.get('title') or '(none)'}")
            lines.append(
                f"- {stage_label} meta description: {data.get('meta_description') or '(none)'}"
            )
            lines.append(
                f"- {stage_label} H1: {', '.join(data['headings']['h1']) or '(none)'}"
            )
            lines.append(f"- {stage_label} word count: {data.get('word_count', 0)}")
            lines.append(
                f"- {stage_label} body text sample: {_text_sample(data.get('body_text', '')) or '(empty)'}"
            )
            lines.append("")
    return "\n".join(lines)


def _aggregate_field_presence(pages, platform_key, stage_key):
    presence = {}
    for field in FIELD_LABELS:
        presence[field] = all(
            _field_present(page["platforms"][platform_key][stage_key], field)
            for page in pages
        )
    return presence


def _findings(pages):
    ai_raw_presence = _aggregate_field_presence(pages, "ai_studio", "raw")
    ai_rendered_presence = _aggregate_field_presence(pages, "ai_studio", "rendered")

    lost = []
    survived = []
    for field, label in FIELD_LABELS.items():
        if ai_raw_presence[field] and ai_rendered_presence[field]:
            survived.append(label)
        elif not ai_raw_presence[field] and ai_rendered_presence[field]:
            lost.append(label)

    lines = ["## Findings", ""]
    lines.append("### What's lost without rendering (AI Studio)")
    if lost:
        lines.extend(f"- {item}" for item in lost)
    else:
        lines.append("- Nothing tested was consistently missing raw across all pages.")
    lines.append("")
    lines.append("### What survives raw regardless of rendering (AI Studio)")
    if survived:
        lines.extend(f"- {item}" for item in survived)
    else:
        lines.append("- Nothing tested was consistently present raw across all pages.")
    lines.append("")
    lines.append("### Mitigation options")
    lines.append(MITIGATION_TEXT)
    return "\n".join(lines)


def generate_report(pages):
    sections = [
        "# SSR vs. Client-Rendered SEO Comparison Report",
        "",
        "## Summary",
        "",
        _summary_table(pages),
        "",
        "## Per-Page Detail",
        "",
    ]
    for page in pages:
        sections.append(_page_detail(page))
    sections.append(_findings(pages))
    return "\n".join(sections)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add ssr-seo-comparison/report.py ssr-seo-comparison/tests/test_report.py
git commit -m "Add markdown report generator for ssr-seo-comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Orchestrator (`urls.py` + `compare.py`)

**Files:**
- Create: `ssr-seo-comparison/urls.py`
- Create: `ssr-seo-comparison/compare.py`
- Test: `ssr-seo-comparison/tests/test_compare.py`

**Interfaces:**
- Produces: `run_comparison(page_pairs=PAGE_PAIRS) -> dict` returning `{"pages": [...]}` in the exact shape `generate_report` (Task 5) consumes. `main()` writes `output/data.json` and `output/report.md`.
- Consumes: `extract_seo_fields` (Task 2), `fetch_raw` (Task 3), `fetch_rendered` (Task 4), `generate_report` (Task 5).

- [ ] **Step 1: Write `urls.py`**

```python
# ssr-seo-comparison/urls.py
PAGE_PAIRS = [
    {
        "page": "home",
        "ai_studio_url": "https://studio.lionsoftsolutions.com/",
        "site_builder_url": "https://lionsoftsolutions.com/home",
    },
    {
        "page": "about",
        "ai_studio_url": "https://studio.lionsoftsolutions.com/about",
        "site_builder_url": "https://lionsoftsolutions.com/about-us",
    },
    {
        "page": "contact",
        "ai_studio_url": "https://studio.lionsoftsolutions.com/contact",
        "site_builder_url": "https://lionsoftsolutions.com/contact-us",
    },
]
```

- [ ] **Step 2: Write the failing test for `compare.py`**

```python
# ssr-seo-comparison/tests/test_compare.py
import compare

FAKE_RAW_HTML = "<html><head><title>Raw Title</title></head><body>Raw body</body></html>"
FAKE_RENDERED_HTML = (
    "<html><head><title>Rendered Title</title></head><body>Rendered body</body></html>"
)


def test_run_comparison_builds_expected_structure(monkeypatch):
    monkeypatch.setattr(compare, "fetch_raw", lambda url: (FAKE_RAW_HTML, 200))
    monkeypatch.setattr(compare, "fetch_rendered", lambda url: (FAKE_RENDERED_HTML, 200))

    page_pairs = [
        {
            "page": "home",
            "ai_studio_url": "https://studio.example.com/",
            "site_builder_url": "https://example.com/home",
        }
    ]

    result = compare.run_comparison(page_pairs)

    assert list(result.keys()) == ["pages"]
    assert len(result["pages"]) == 1

    home = result["pages"][0]
    assert home["page"] == "home"
    assert set(home["platforms"].keys()) == {"ai_studio", "site_builder"}

    ai_studio = home["platforms"]["ai_studio"]
    assert ai_studio["url"] == "https://studio.example.com/"
    assert ai_studio["raw"]["title"] == "Raw Title"
    assert ai_studio["raw"]["status_code"] == 200
    assert ai_studio["rendered"]["title"] == "Rendered Title"
    assert ai_studio["rendered"]["status_code"] == 200

    site_builder = home["platforms"]["site_builder"]
    assert site_builder["url"] == "https://example.com/home"
    assert site_builder["raw"]["title"] == "Raw Title"


def test_run_comparison_multiple_pages(monkeypatch):
    monkeypatch.setattr(compare, "fetch_raw", lambda url: (FAKE_RAW_HTML, 200))
    monkeypatch.setattr(compare, "fetch_rendered", lambda url: (FAKE_RENDERED_HTML, 200))

    page_pairs = [
        {"page": "home", "ai_studio_url": "https://a.example/", "site_builder_url": "https://b.example/"},
        {"page": "about", "ai_studio_url": "https://a.example/about", "site_builder_url": "https://b.example/about"},
    ]

    result = compare.run_comparison(page_pairs)

    assert [p["page"] for p in result["pages"]] == ["home", "about"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_compare.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'compare'`.

- [ ] **Step 4: Write the implementation**

```python
# ssr-seo-comparison/compare.py
import json
import os

from extract import extract_seo_fields
from fetch_raw import fetch_raw
from fetch_rendered import fetch_rendered
from report import generate_report
from urls import PAGE_PAIRS

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def collect_platform_data(url):
    raw_html, raw_status = fetch_raw(url)
    raw_data = extract_seo_fields(raw_html, url)
    raw_data["status_code"] = raw_status

    rendered_html, rendered_status = fetch_rendered(url)
    rendered_data = extract_seo_fields(rendered_html, url)
    rendered_data["status_code"] = rendered_status

    return {"url": url, "raw": raw_data, "rendered": rendered_data}


def run_comparison(page_pairs=PAGE_PAIRS):
    pages = []
    for pair in page_pairs:
        pages.append(
            {
                "page": pair["page"],
                "platforms": {
                    "ai_studio": collect_platform_data(pair["ai_studio_url"]),
                    "site_builder": collect_platform_data(pair["site_builder_url"]),
                },
            }
        )
    return {"pages": pages}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = run_comparison()

    data_path = os.path.join(OUTPUT_DIR, "data.json")
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2)

    report_path = os.path.join(OUTPUT_DIR, "report.md")
    with open(report_path, "w") as f:
        f.write(generate_report(data["pages"]))

    print(f"Wrote {data_path}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_compare.py -v`
Expected: both tests PASS. (These use `monkeypatch` on the names imported into `compare`'s namespace, so no real network or browser calls happen in this test.)

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests across all 5 test files PASS.

- [ ] **Step 7: Commit**

```bash
cd ..
git add ssr-seo-comparison/urls.py ssr-seo-comparison/compare.py ssr-seo-comparison/tests/test_compare.py
git commit -m "Add orchestrator script for ssr-seo-comparison

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: End-to-End Run Against Real Sites

**Files:**
- None created — this task runs the pipeline built in Tasks 1-6 against the real URLs in `urls.py` and verifies the output.

**Interfaces:**
- Consumes: `compare.main()` (Task 6).
- Produces: `ssr-seo-comparison/output/data.json` and `ssr-seo-comparison/output/report.md` (gitignored, not committed — these are regenerable run artifacts, not source).

- [ ] **Step 1: Run the full comparison**

```bash
cd ssr-seo-comparison
source venv/bin/activate
python compare.py
```

Expected: prints `Wrote .../output/data.json` and `Wrote .../output/report.md` with no unhandled exceptions. This makes 12 network requests total (6 URLs × raw + rendered) and will take on the order of a minute or two due to Playwright browser launches.

- [ ] **Step 2: Sanity-check the AI Studio home page result**

Run: `python -c "import json; d = json.load(open('output/data.json')); home = d['pages'][0]['platforms']['ai_studio']; print('raw word_count:', home['raw']['word_count']); print('rendered word_count:', home['rendered']['word_count'])"`

Expected: raw `word_count` is very small (single digits — just the title text, consistent with the ~46-character raw HTML body observed during brainstorming), rendered `word_count` is much larger (hundreds of words, consistent with the ~6,187-character rendered content observed during brainstorming). If raw and rendered word counts come back roughly equal, something is wrong (either the site changed, or Playwright isn't actually waiting for render) — stop and debug before proceeding, per the systematic-debugging skill, rather than treating the report as trustworthy.

- [ ] **Step 3: Sanity-check the Site Builder home page result**

Run: `python -c "import json; d = json.load(open('output/data.json')); home = d['pages'][0]['platforms']['site_builder']; print('raw word_count:', home['raw']['word_count']); print('rendered word_count:', home['rendered']['word_count'])"`

Expected: raw and rendered word counts are close to each other (within normal variance — Site Builder is server-rendered, so raw HTML should already contain full content, consistent with the ~6,255-character raw HTML observed during brainstorming).

- [ ] **Step 4: Read the generated report**

Open `ssr-seo-comparison/output/report.md` and confirm:
- The Summary table has 6 rows (3 pages × 2 platforms) and reads as a coherent table.
- Each Per-Page Detail section has real title/meta description/body text values for both platforms (not `(none)`/`(empty)` for the Site Builder or the rendered AI Studio rows — `(none)`/`(empty)` should only show up for AI Studio raw fields where content is genuinely absent).
- The Findings section's "lost"/"survived" lists match what Steps 2-3 showed numerically.
- No exceptions or error text leaked into the report content (e.g. from a failed fetch on one of the 6 URLs — if a page failed, its status_code will reveal it before the report reaches the reader).

If any URL fails to fetch (e.g. a transient network error, or one of the 6 URLs no longer resolves), re-run `python compare.py` — the script has no persisted state, so a re-run is always safe and cheap other than time.

- [ ] **Step 5: Confirm report and data are gitignored, not staged**

Run: `git status`
Expected: `ssr-seo-comparison/output/` does not appear (already excluded via `.gitignore` from Task 1). No commit needed for this task — it produces run artifacts, not source code.
