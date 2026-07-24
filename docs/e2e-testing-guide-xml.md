# API Connector — XML Response Support: End-to-End Testing Guide

Companion to [`e2e-testing-guide.md`](./e2e-testing-guide.md), scoped to `001-xml-response-support`. Where that guide walks every auth type against JSON APIs, this one walks the same **Profile Setup → Connection Test → Endpoint Creation → Pagination → Schema** structure against **6 real, live, independently-operated XML APIs** — chosen to cover every pagination strategy that makes sense against real XML sources, and several genuinely different XML shapes (namespaced library metadata, Atom/GeoRSS, RSS 2.0 with CDATA, and AWS's S3 listing format).

---

## How to Read This Guide

Each section is independently reproducible. All were executed on **2026-07-24** against the app's REST API directly (not a browser — no browser-automation tooling was available in the session that ran this; this exercises the exact same backend code paths — `ConnectionTestService`, `PaginationEngine`, `SchemaInferenceEngine`, `DataPreviewService` — a UI click would). Frontend-only claims (the `response_format` Select, `RawResponseViewer`'s XML highlighting) are covered separately in §9 and in `frontend/src/features/data-preview/components/__tests__/RawResponseViewer.dom.test.tsx`.

Three sections below **found something genuinely new** — not bugs in `001-xml-response-support` itself, but real characteristics of live APIs and one pre-existing, XML-and-JSON-agnostic app constraint that only real (not mocked) XML sources could surface. Each is called out inline with a `>` blockquote, and consolidated in §8.

**Before you start:** App running (`docs/project-detail.md` §3), network access to the hosts below, no credentials needed anywhere in this guide (all 6 targets are public, unauthenticated APIs).

**Record counts, IDs, and article titles will differ when you reproduce this** — every target here is a live, independently-operated data source that changes over time. That doesn't invalidate anything below; only the specific numbers will move.

---

## Table of Contents

1. [XML-Specific Conventions (Reference)](#1-xml-specific-conventions-reference)
2. [Cursor (Integer Position) — Deutsche Nationalbibliothek SRU](#2-cursor-integer-position--deutsche-nationalbibliothek-sru)
3. [Page / Size — World Bank API](#3-page--size--world-bank-api)
4. [Offset / Limit — NCBI E-utilities (PubMed)](#4-offset--limit--ncbi-e-utilities-pubmed)
5. [No Pagination (Atom / GeoRSS) — USGS Earthquakes](#5-no-pagination-atom--georss--usgs-earthquakes)
6. [No Pagination (RSS + CDATA) — BBC News](#6-no-pagination-rss--cdata--bbc-news)
7. [Cursor (Opaque Token) — NOAA GOES-16 S3 Bucket](#7-cursor-opaque-token--noaa-goes-16-s3-bucket)
8. [Known Limitations & Residual Risks](#8-known-limitations--residual-risks)
9. [XSS-Safety of the Raw XML Response Viewer](#9-xss-safety-of-the-raw-xml-response-viewer)
10. [Quick Reference](#10-quick-reference)

---

## 1. XML-Specific Conventions (Reference)

Fields behave exactly as documented in `e2e-testing-guide.md` §1, with these XML-only additions:

| Field | Description | Notes |
|---|---|---|
| **Response Format** | New `Endpoint`-level Select: `JSON` / `XML` | Defaults from the profile's last `Test Connection`'s detected format (only an exact `"xml"` match defaults to XML — see the recurring pattern in §8); always user-editable. |
| **Data Root Path / Record Count Path** | Same dot-notation UX as JSON | **Namespaces are stripped automatically** — `<dc:title>` under `<zs:records>` resolves as `records.title` dot-path, never `zs:records.dc:title`. **XML attributes become `@name` keys** (e.g. `<record id="42">` → `@id`), and text content alongside attributes/children becomes `#text`. A pure-text leaf with no attributes collapses straight to a string (no `#text` wrapper) — see any `dc:title`-style field below. |
| **Raw Response panel** | Shows the *original XML text*, not a JSON reinterpretation | Toggle it on any endpoint below and you'll see real `<?xml ...?>`-prefixed text, syntax-highlighted for XML (tag/attribute coloring), not JSON coloring. |

---

## 2. Cursor (Integer Position) — Deutsche Nationalbibliothek SRU

**API:** `https://services.dnb.de/sru/dnb` — Germany's National Library, SRU (Search/Retrieve via URL) protocol, Dublin Core (`oai_dc`) records. No signup, no key.

### 2.1 Create the Profile — and a real configuration gotcha

The natural first attempt — pasting DNB's documented endpoint straight into **Base URL** — works for testing the connection, but **not** for the endpoint underneath it:

1. **+ New Profile**
   - **Base URL:** `https://services.dnb.de/sru/dnb`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: true`, all 6 steps pass, **`Detected Format: xml`** (a bare GET returns DNB's SRU "explain" self-description document — still real XML).

> **Gotcha, discovered live:** DNB's SRU endpoint rejects *any* character appended after `/sru/dnb` — including a bare trailing slash — with a `HTTP 200` response that is nonetheless a `<diagnostics>`/error document, not real data. Since `Endpoint.path` always appends to `base_url` (`base_url.rstrip("/") + path`) and must be non-empty, an `Endpoint` created directly under *this* profile (any `path`, even `"/"`) fails Schema Inference with a **misleading `422 API_CONN_051`**: *"No records found... Verify the data_root_path is correct"* — the real cause is the base URL/path split, not `data_root_path` (which is correct). Reproduced both via raw HTTP and through the app itself. See §8 for the general lesson (this isn't DNB-specific) and the exact fix used next.

### 2.2 The working Profile + Endpoint split

1. **+ New Profile**
   - **Base URL:** `https://services.dnb.de` *(host only — no path)*
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: false` (bare host root is a `404`) — **expected**, see §8's recurring pattern. `Detected Format` is never set (the diagnostic sequence stops at the first failing step).
3. **+ New Endpoint**
   - **Name:** `SRU searchRetrieve (oai_dc)`
   - **Path:** `/sru/dnb` *(the fixed path lives here instead)*
   - **Method:** `GET`
   - **Query Parameters:** `version=1.1`, `operation=searchRetrieve`, `query=WOE=test`, `recordSchema=oai_dc`, `maximumRecords=3`
   - **Response Format:** `XML` — **manually set**, since this profile's own `last_test_detected_format` is `null` (step 2 never reached format detection), so the create-mode default falls back to `JSON` per the documented fallback rule. This exercises the manual-override half of the Select's behavior, not just auto-detection.
   - **Data Root Path:** `searchRetrieveResponse.records.record`
   - **Record Count Path:** `searchRetrieveResponse.numberOfRecords`

### 2.3 Pagination — Cursor

| Field | Value |
|---|---|
| Strategy | `Cursor` |
| `cursor_request_param` | `startRecord` |
| `cursor_response_path` | `searchRetrieveResponse.nextRecordPosition` |
| `max_pages` | `5` |
| `max_records` | `15` |

SRU's own protocol *is* a cursor advance (`startRecord` in, `nextRecordPosition` out) — confirmed directly: page 1 (no `startRecord`) returns `nextRecordPosition=4`; `startRecord=4` returns `nextRecordPosition=7`.

### 2.4 Schema Inference & Data Preview

**Schema Inference** produced **16 fields**, zero namespace-prefix leakage (`recordData.dc.creator`, never a raw `dc:creator` or Clark-notation URI), correct list-coercion for repeatable elements (`dc.creator`: `array_of_primitives`; `dc.identifier`: `array_of_objects`, each `{"@type": ..., "#text": ...}`) — and **9 records sampled**, i.e. 3 real pages × 3 records/page (visible from `dc.creator`'s `null_percentage = 0.222` = 2/9), confirming the cursor genuinely advanced across multiple live pages during inference, not just one.

**Data Preview** (`row_limit=5`): 5 rows, `has_more: true`, `raw_response_body` starting with `<?xml version="1.0" encoding="UTF-8"?>` — the real XML text, not a JSON reinterpretation.

**`CursorStrategy` never touches the known, pre-existing `_next_url` bug** (`PaginationEngine._request_with_retry` drops query strings on that sentinel path, `engine.py:123-126`, unrelated to this feature) — confirmed by code inspection (`CursorStrategy.next_params()` never returns the `_next_url` sentinel) and by observing every page's query params intact throughout this run.

---

## 3. Page / Size — World Bank API

**API:** `https://api.worldbank.org/v2` — World Bank's open data catalog. No signup, no key. `format=xml` opts into XML (JSON is the undocumented default).

### 3.1 Create the Profile

1. **+ New Profile**
   - **Base URL:** `https://api.worldbank.org`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: false` (bare host root `404`s) — same recurring pattern as DNB's host-root profile (§8); the actual endpoint below works fine regardless.

### 3.2 Create Endpoint: Countries

1. **+ New Endpoint**
   - **Name:** `Countries`
   - **Path:** `/v2/country`
   - **Query Parameters:** `format=xml`
   - **Response Format:** `XML` (manual — same reason as DNB's split profile)
   - **Data Root Path:** `countries.country`

> **Limitation, discovered live:** World Bank expresses pagination metadata (`page`, `pages`, `per_page`, `total`) as **XML attributes on the response root** — `<wb:countries page="1" pages="59" ... total="295">`. After namespace-stripping, those become `@page`/`@pages`/`@total` — but this app's dot-notation path fields (`data_root_path`, `record_count_path`, `total_pages_path`, `cursor_response_path`, `next_url_response_path`) are validated by `^[\w]+(\.[\w]+)*$`, which **rejects any `@` character**. Setting `record_count_path` to `countries.@total` was tried and rejected: `400 — "record_count_path must use dot-notation... No double dots, leading/trailing dots, or special characters."` This is a real, currently-live gap: **root-level pagination/count metadata expressed as an XML attribute is structurally unreachable** through these fields — it's not about *this* endpoint's data (attribute-based *record* fields, like `@id` on each `<country>`, work completely normally, see §3.4). See §8.

### 3.3 Pagination — Page / Size (worked around the limitation above)

| Field | Value |
|---|---|
| Strategy | `Page / Size` |
| `page_param` | `page` |
| `page_size_param` | `per_page` |
| `page_size` | `5` |
| `total_pages_path` | *(left blank — see above)* |
| `max_pages` | `3` |

Without `total_pages_path`, `PageSizeStrategy` falls back to comparing each page's record count against `page_size` to detect the last page (`strategies.py:116-127`) — a real, working fallback, not a crash. Confirmed via `Data Preview` with `row_limit=12`: **12 records fetched**, requiring 3 real pages at `page_size=5` — the strategy genuinely advanced multiple pages despite the missing total.

### 3.4 Schema Inference & Data Preview

**Schema Inference**: 18 fields, including several attribute-based ones *within* each record — `@id`, `adminregion.@id`, `adminregion.@iso2code`, `adminregion.#text`, `incomeLevel.@id`, etc. — proving attribute fields inside records are fully reachable and correctly typed; only *root-level* pagination-metadata attributes hit the limitation above.

**Data Preview**: `raw_response_body` begins with a literal UTF-8 BOM (`﻿`) before `<?xml ...?>` — World Bank's server sends one; the app preserves it byte-for-byte in the Raw Response panel (faithful to "what the API actually returned," per DEC-6), and it doesn't interfere with `highlightXml`'s tag-matching (the BOM is inert text before the first real tag).

---

## 4. Offset / Limit — NCBI E-utilities (PubMed)

**API:** `https://eutils.ncbi.nlm.nih.gov` — NCBI's Entrez programming utilities, `esearch` endpoint (returns matching PubMed IDs). No signup for light use.

### 4.1 Create the Profile

1. **+ New Profile**
   - **Base URL:** `https://eutils.ncbi.nlm.nih.gov`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: true`, but **`Detected Format: html`**, not `xml` — the bare host root `301`-redirects to an HTML landing page. Same recurring base_url-vs-endpoint mismatch as §2/§3, just manifesting as a *wrong* detected format instead of an outright failure (see §8).

### 4.2 Create Endpoint: esearch (PubMed IDs)

1. **+ New Endpoint**
   - **Name:** `esearch (PubMed IDs)`
   - **Path:** `/entrez/eutils/esearch.fcgi`
   - **Query Parameters:** `db=pubmed`, `term=cancer`, `retmode=xml`
   - **Response Format:** `XML` (manual — root detected `html`)
   - **Data Root Path:** `eSearchResult.IdList.Id`
   - **Record Count Path:** `eSearchResult.Count`

NCBI's response includes a real `<!DOCTYPE eSearchResult PUBLIC "..." "https://eutils.ncbi.nlm.nih.gov/eutils/dtd/...">` referencing an external DTD — a genuine, real-world confirmation of SC7's XXE-safety claim: `xml_parser.py`'s `disable_entities=True` accepts this bare DOCTYPE (no entity declared, matching the accepted-limitation note in its own docstring) without attempting to fetch the external subset, and the parse succeeds normally.

### 4.3 Pagination — Offset / Limit

| Field | Value |
|---|---|
| Strategy | `Offset / Limit` |
| `offset_param` | `retstart` |
| `limit_param` | `retmax` |
| `page_size` | `5` |

`retstart`/`retmax` is a standard, stateless offset/limit pair — confirmed independently (raw HTTP) that varying `retstart` returns a different ID window each time.

### 4.4 Schema Inference — a genuinely different result

> **Gotcha, discovered live:** `Schema Inference` returned **`[]` — zero fields — with a normal `HTTP 200`**, not an error. Attempting `Data Preview` afterward fails with `422`: *"No fields are marked for inclusion. Go to the Schema Explorer and include at least one field."* This is **not** the same failure as §2.1's gotcha (which was "no records found") — records *were* found here (`eSearchResult.IdList.Id` resolves to a real list of `<Id>42493811</Id>`-style elements); they're just **bare scalar strings, not objects**, and `SchemaInferenceEngine._walk_record` has nothing to flatten from a scalar — it produces no dot-paths at all. **This is format-agnostic** — a JSON endpoint with `data_root_path` pointing at `["1", "2", "3"]` would hit the identical gap, since `_walk_record` operates on the same normalized structure regardless of source format. Not a bug in `001-xml-response-support`; a pre-existing edge case this run happened to surface. See §8.

---

## 5. No Pagination (Atom / GeoRSS) — USGS Earthquakes

**API:** `https://earthquake.usgs.gov` — USGS's live earthquake feed, Atom format with GeoRSS geo-extensions. No signup.

### 5.1 Create the Profile

1. **+ New Profile**
   - **Base URL:** `https://earthquake.usgs.gov`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: true`, but **`Detected Format: html`** — the bare root is USGS's website homepage, not the feed. Same pattern as §4; the feed endpoint itself is unaffected.

### 5.2 Create Endpoint: Significant Earthquakes (past month)

1. **+ New Endpoint**
   - **Name:** `Significant Earthquakes (past month)`
   - **Path:** `/earthquakes/feed/v1.0/summary/significant_month.atom`
   - **Query Parameters:** *(none — the path alone selects this feed)*
   - **Response Format:** `XML` (manual)
   - **Data Root Path:** `feed.entry`
   - **Pagination:** `No Pagination` — this feed is a fixed, unpaginated list by design.

### 5.3 Schema Inference & Data Preview

**Schema Inference**: 13 fields — `title`, `id`, `link.@href`/`link.@rel`/`link.@type` (Atom's `<link>` is attribute-only, no text — correctly surfaced as `@`-keys with no spurious `#text`), `category.@label`/`category.@term` (`category` itself resolves `array_of_objects` since some entries have multiple), `summary.#text`/`summary.@type` (mixed: has both an attribute *and* text, correctly getting the `#text` key this time — contrast with `link`, which has no text and thus no `#text` key at all).

**Data Preview** (`row_limit=3`): 3 rows, `raw_response_body` starting with `<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom" xmlns:georss="...`.

---

## 6. No Pagination (RSS + CDATA) — BBC News

**API:** `https://feeds.bbci.co.uk/news/world/rss.xml` — BBC's public world-news RSS 2.0 feed. No signup.

### 6.1 Create the Profile

1. **+ New Profile**
   - **Base URL:** `https://feeds.bbci.co.uk`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: false` (bare host root `404`s) — same pattern as §2/§3.

### 6.2 Create Endpoint: World News

1. **+ New Endpoint**
   - **Name:** `World News`
   - **Path:** `/news/world/rss.xml`
   - **Response Format:** `XML` (manual)
   - **Data Root Path:** `rss.channel.item`
   - **Pagination:** `No Pagination` — RSS is a fixed-length list by convention.

### 6.3 Schema Inference & Data Preview — CDATA confirmed against a real feed

BBC wraps `<title>`/`<description>` in `<![CDATA[...]]>` (protecting embedded HTML/ampersands from needing entity-escaping). **Schema Inference** produced 9 fields, and critically: `title` and `description` resolved to **clean, unwrapped plain strings** (e.g. `"US imposes tariffs on dozens of trade partners, citing forced labour concerns"`) — no literal `<![CDATA[` or `]]>` leaking into the value. `xmltodict` (the library `001-xml-response-support` chose, DEC-8) handles CDATA natively; Phase 1's spike only proved this against a synthetic sample (`sample_mixed_content.xml`) — this is the first confirmation against a real, live CDATA-bearing feed.

Also present: `guid.@isPermaLink`/`guid.#text` (mixed attribute+text, same shape as USGS's `summary` field), `thumbnail.@height`/`@width`/`@url` (a `media:thumbnail` element, namespace-stripped to `thumbnail`).

**Data Preview** (`row_limit=3`): 3 rows; `rows[0].title` matches the live top headline at capture time.

---

## 7. Cursor (Opaque Token) — NOAA GOES-16 S3 Bucket

**API:** `https://noaa-goes16.s3.amazonaws.com` — a public, unauthenticated AWS S3 bucket (NOAA's GOES-16 satellite imagery archive), listed via S3's REST `?list-type=2` API. This is deliberately a *very* different domain from §2-6: not a "designed API" at all, just S3's standard bucket-listing XML, which happens to also be a public, real, namespaced (`http://s3.amazonaws.com/doc/2006-03-01/`) XML source.

### 7.1 Create the Profile

1. **+ New Profile**
   - **Base URL:** `https://noaa-goes16.s3.amazonaws.com`
   - **Auth Type:** `No Auth`
2. **Test Connection** → `overall_passed: true`, **`Detected Format: xml`** — unlike every other profile in this guide, **the bare root itself is valid XML here** (S3 returns a full, unfiltered bucket listing at `/` with no query params) — the recurring host-root-mismatch pattern (§8) isn't universal; it depends on whether the host's root happens to serve the same kind of content as the actual endpoint.

### 7.2 Create Endpoint: List Objects (v2)

1. **+ New Endpoint**
   - **Name:** `List Objects (v2)`
   - **Path:** `/`
   - **Query Parameters:** `list-type=2`, `max-keys=5`
   - **Response Format:** `XML` (auto-detected correctly this time, per §7.1)
   - **Data Root Path:** `ListBucketResult.Contents`
   - **Record Count Path:** `ListBucketResult.KeyCount`

### 7.3 Pagination — Cursor (opaque token, not an integer)

| Field | Value |
|---|---|
| Strategy | `Cursor` |
| `cursor_request_param` | `continuation-token` |
| `cursor_response_path` | `ListBucketResult.NextContinuationToken` |
| `max_pages` | `3` |

Unlike §2's DNB (`startRecord` is a plain integer position), S3's cursor is a long, opaque, base64-ish token string — the same "opaque cursor" shape `e2e-testing-guide.md` §10.4 demonstrates for Airtable, now confirmed to work identically for a real XML source. `CursorStrategy`'s contract (`cursor is None or cursor == ""` means stop) doesn't care what shape the cursor value takes.

### 7.4 Schema Inference & Data Preview

**Schema Inference**: 7 fields (`Key`, `LastModified` → correctly inferred `datetime`, `ETag`, `Size`, `StorageClass`, `ChecksumAlgorithm`, `ChecksumType`) — a uniform, fully-structured record shape (every object has every field; `null_percentage: 0.0` across the board).

**Data Preview** (`row_limit=12`): **12 objects fetched** at `max-keys=5`/page — confirms the opaque continuation token genuinely advanced across 3 real pages, not just decoded a single response.

---

## 8. Known Limitations & Residual Risks

**A recurring pattern across 4 of 6 profiles above (§2, §3, §4, §6 — not §7's S3):** testing a profile's bare `Base URL` alone often does **not** reflect the actual data endpoint's format or even its reachability, whenever the API's meaningful content lives at a specific sub-path rather than the host root. This isn't a bug — `Test Connection` is documented to test exactly `base_url`, nothing more — but it means **`Detected Format`/`overall_passed` from a profile's own connection test is not a reliable signal for endpoints created under it**, for a meaningful fraction of real-world APIs. Users configuring a similar API should expect to set `Response Format` manually rather than assume the Select's default is meaningful. This affects JSON-configured profiles identically (format-agnostic) — this guide just happened to be the first to exercise it against enough different real hosts to notice the pattern clearly.

- **The base-URL/path split gotcha (§2.1)** is general, not DNB-specific: any single-fixed-endpoint API (common among SRU/Z39.50-adjacent library systems, and likely other legacy/government services) will hit the same misleading `422 API_CONN_051` if a user follows the natural instinct to paste the whole documented endpoint URL into **Base URL**. Not fixed in code this phase (Rule 2/6 — out of scope, and it's a pre-existing `Endpoint.path` constraint, unrelated to XML specifically). Worth a follow-up: either detect an error/diagnostics-shaped zero-record response distinctly from a genuinely empty one, or accept this guide as the mitigation.
- **The `@attr` root-level pagination-metadata limitation (§3.2)** is a real, currently-live gap: `data_root_path`/`record_count_path`/`total_pages_path`/`cursor_response_path`/`next_url_response_path` are all validated by a dot-notation pattern (`^[\w]+(\.[\w]+)*$`) that structurally cannot express an `@`-prefixed attribute key — even though the XML normalization layer itself (`xml_parser.py`) produces exactly that convention for attributes. Any real API expressing count/cursor/next-page metadata as a root-level XML attribute (not uncommon — World Bank does it) cannot have that specific value wired up, though the endpoint still works via the fallback behavior demonstrated in §3.3. Worth a follow-up: either relax the dot-notation pattern to allow a leading `@` per segment, or document this as an accepted limitation.
- **The scalar-record schema-inference gap (§4.4)**: `data_root_path` resolving to a list of scalars (not objects) silently produces zero inferred fields, which then blocks `Data Preview` entirely (`422`, "no fields marked for inclusion") with no error message pointing back at the real cause. Format-agnostic, pre-existing, not fixed this phase.
- **DEV-1** (`PaginationEngine._request_with_retry` drops the query string on the `_next_url` sentinel path, `engine.py:123-126`) remains open and format-agnostic. None of the 6 APIs in this guide exercise `NextURL`/`LinkHeader` strategies (deliberately, per OD-1's reasoning — see `phases/phase-4/breakdown.md` §2) — `e2e-testing-guide.md` §10.5/§10.6 already cover those strategies against JSON APIs unaffected by this bug's XML-specific relevance.
- **The pre-existing `highlightJson` bug** (found incidentally during `RawResponseViewer`'s XML work — its number-coloring regex corrupts its own injected `class="..."` markup) is unrelated to XML and not exercised by this guide, but affects every JSON-configured endpoint's Raw Response panel too. See `phases/phase-4/implementation.md` §4/§9.
- **Also confirmed, not written up as a full section**: `http://lx2.loc.gov:210/lcdb` (Library of Congress SRU, MODS schema, `zs:`-prefixed namespace style rather than DNB's default namespace) — cursor pagination independently confirmed advancing (`nextRecordPosition` 4 → 7) via the same `startRecord` mechanism as §2, over plain HTTP on a non-standard port. Not run through the app's full pipeline this session (time-scoped); the underlying mechanism is identical to §2's proven case.
- **Cross-namespace same-local-name key collision** (DEC-5's accepted risk) was not observed in any of the 6 live sources above — still a real, accepted residual risk for sources unlike these (demonstrated only via Phase 1's synthetic `sample_ns_collision.xml`).

---

## 9. XSS-Safety of the Raw XML Response Viewer

Not re-verified against any of the 6 live sources above (none contain adversarial content — they're all real library/government/news data, nothing to observe). Covered instead by 2 targeted, automated regression tests against a synthetic payload matching `RawResponseViewer`'s own documented threat model (`</span><script>...`), once as XML element text and once as an XML attribute value:

```
frontend/src/features/data-preview/components/__tests__/RawResponseViewer.dom.test.tsx
  ✓ escapes an XSS payload in XML element text content instead of executing it
  ✓ escapes an XSS payload in an XML attribute value instead of executing it
```

Both assert no live `<script>` DOM element is ever produced. `highlightXml` was additionally re-run directly against §2's real, unmodified DNB response body (not just synthetic fixtures) — correct tag/attribute coloring, no live `<script>` producible. See `phases/phase-4/implementation.md` §7 for full output.

---

## 10. Quick Reference

| # | API | Auth | Pagination | XML shape | Notable finding |
|---|---|---|---|---|---|
| §2 | Deutsche Nationalbibliothek SRU | No Auth | Cursor (integer position) | Namespaced Dublin Core, default namespace | Base-URL/path split gotcha (§8) |
| §3 | World Bank | No Auth | Page / Size | `wb:`-namespaced, root-level attributes | `@attr` path limitation (§8) |
| §4 | NCBI E-utilities | No Auth | Offset / Limit | Simple, external DTD reference | Scalar-record schema gap (§8); real XXE-safety confirmation |
| §5 | USGS Earthquakes | No Auth | No Pagination | Atom + GeoRSS | Attribute-only elements (no `#text`) |
| §6 | BBC News RSS | No Auth | No Pagination | RSS 2.0 + CDATA | Real CDATA unwrapping confirmed |
| §7 | NOAA GOES-16 (S3) | No Auth | Cursor (opaque token) | AWS S3 listing format | Non-"designed API" XML source; base_url alone *does* auto-detect correctly here |

Every pagination strategy meaningful for a real XML source is covered except `Next URL`/`Link Header` (deliberately deferred — see §8's DEV-1 note; already covered for JSON in `e2e-testing-guide.md` §10.5/§10.6).
