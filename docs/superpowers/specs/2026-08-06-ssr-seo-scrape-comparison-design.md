# SSR vs. Client-Rendered Site — SEO Crawlability Comparison — Design

## Purpose

GoHighLevel's AI Studio site builder renders pages client-side (JavaScript
builds the DOM in the browser); the older HL Site Builder renders pages
server-side (full HTML in the initial response). There's ongoing debate about
whether AI Studio sites carry an SEO indexing penalty as a result.

This project builds a one-off (but rerunnable) comparison to answer, with
evidence rather than assumption: **what specifically is missing from an AI
Studio page for a non-rendering crawler, what already survives regardless of
rendering, and whether the gap is mitigable without switching platforms.**
It is diagnostic, not a verdict-first exercise — the report should reflect
whatever the data shows.

This is a standalone side investigation, unrelated to the BatchData/GHL
integration this repo otherwise contains. It lives in its own subfolder with
its own dependencies so it doesn't touch `requirements.txt` or `main.py`.

## Sites Under Test

Two real, published (non-preview, non-staging) sites for the same business,
built on the two different platforms, so the comparison isolates the
rendering-method variable:

| Page    | AI Studio (client-rendered)                  | HL Site Builder (server-rendered)         |
|---------|-----------------------------------------------|--------------------------------------------|
| Home    | `https://studio.lionsoftsolutions.com/`       | `https://lionsoftsolutions.com/home`        |
| About   | `https://studio.lionsoftsolutions.com/about`  | `https://lionsoftsolutions.com/about-us`    |
| Contact | `https://studio.lionsoftsolutions.com/contact`| `https://lionsoftsolutions.com/contact-us`  |

Six URLs total. A third candidate site
(`https://preview-1775243201872018439.vibepreview.com/`) was ruled out during
brainstorming: it's an unpublished preview/staging domain, sits behind a
Cloudflare block that rejects plain HTTP requests from any user-agent
(confirmed via `curl`), and preview domains aren't indexed by search engines
regardless of rendering — so testing it wouldn't isolate the SSR variable and
wasn't representative of a real published site. Bypassing that Cloudflare
block is explicitly out of scope; it's a different problem (bot-blocking)
than the one this test investigates (rendering/SSR).

## What Gets Extracted, Per URL, Two Ways

**1. Raw HTTP fetch** (`requests`, no JS execution) — simulates what a
non-rendering crawler sees: many social-media unfurlers, some LLM/AI
crawlers, naive scrapers, and (per Google's own documentation) the first pass
of Googlebot's two-wave indexing before a page is queued for rendering.

**2. Playwright render** (headless Chromium, wait for network-idle) —
simulates what a rendering-capable crawler sees, i.e. modern Googlebot after
its render pass, or a human visitor.

For each method, extract the same fields so they're directly diffable:

- `<title>`
- meta description
- canonical tag
- OG / Twitter card tags
- heading structure (H1/H2 tags and their text)
- visible body text (word count + a text sample)
- internal links discovered
- JSON-LD / structured data blocks, if any
- HTTP status code and any sign of blocking (redirect to a challenge page,
  4xx/5xx, empty body)

Comparing structured SEO elements individually (not just total text length)
matters because some of these — title, meta description, OG tags — are
typically injected into raw HTML by frameworks like React even before
hydration, and would already be crawlable without rendering. The report
needs to show which specific elements survive raw and which don't, since
that's what determines whether the gap is fixable via lighter-weight means
(e.g. static meta-tag injection) versus requiring a full rendering/SSR
solution.

## Script

New folder: `ssr-seo-comparison/` at the repo root, with its own venv and
`requirements.txt` (`requests`, `beautifulsoup4`, `playwright`). Not added to
the main app's `requirements.txt` — this tooling has nothing to do with the
Flask app and shouldn't become a permanent dependency of it.

One Python script (`compare.py`) that:

1. Loops over the 6 URLs.
2. For each, does a raw `requests.get()` fetch and extracts the fields above
   via BeautifulSoup.
3. For each, does a Playwright headless-Chromium navigation (wait for
   network-idle), then extracts the same fields via the rendered DOM.
4. Writes a raw JSON dump of all extracted data (so the run can be
   inspected/debugged or fed into a different report format later without
   re-scraping).
5. Writes `report.md` — the deliverable.

Rerunnable: running the script again just overwrites the JSON dump and
report with fresh data. No state carried between runs.

## Report (`report.md`) Structure

1. **Summary table** — one row per page-pair (home/about/contact), showing
   at a glance which SEO elements were present raw vs. only after render, for
   each platform.
2. **Per-page detail** — for each of the 3 page-pairs, the raw vs. rendered
   extraction side by side for both platforms, including text samples.
3. **Findings** — plain-language section covering:
   - What is actually lost without rendering, specifically (not just "less
     text" — which structured elements are missing or present).
   - What already survives raw HTML regardless of rendering (so it's not
     part of the problem).
   - Known mitigation options for a CSR site (dynamic rendering / prerendering
     for bots, hybrid server-injected meta tags, migrating to an SSR
     framework) and, based on what this test found, whether a lighter-weight
     mitigation would plausibly close the gap or whether the gap is
     structural to the platform.
   - An explicit statement that this test does not determine whether
     Googlebot specifically waits long enough to render AI Studio pages in
     practice (that requires Search Console data over time, which is outside
     the scope of a one-off scrape) — the report characterizes what's
     technically present/absent, not confirmed indexing outcomes.

## Out of Scope

- Bypassing Cloudflare or any other bot-detection on any tested site.
- Visual/styling comparison — text and SEO-signal content only.
- Testing the vibepreview.com preview domain.
- Any change to the main Flask app or its dependencies.
- Confirming actual Google Search Console indexing status (would require
  ongoing data the two sites may not have accumulated).
