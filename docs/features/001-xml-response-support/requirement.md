# XML Response Support — Requirement

Feature ref: `001-xml-response-support` · Created: 2026-07-23

---

## 1. Problem Statement

The API Connector assumes every external API response is JSON end-to-end. Endpoints that return XML (e.g. government/public-data SRU APIs) pass connection testing — format detection already correctly labels the response `"xml"` (`backend/api_connector/services/connection_test/service.py:575-621`) — but fail downstream at schema inference and data preview with a non-JSON parse error, because `PaginationEngine.paginate()` hard-codes `response.json()` (`backend/api_connector/services/pagination/engine.py:146`) and raises `PaginationEngineError` on anything else. This produces a misleading dead end: the user is told the connection works, then hits an opaque failure at the very next step.

## 2. Solution Justification

No existing config, tool, or code path already solves this. The detected format (`ConnectionProfile.last_test_detected_format`) is computed and persisted but never consumed by anything in the pagination/schema/preview pipeline — it's a dead end, not a partial solution. Building XML support is the only option; the design question is *how much* of the pipeline needs to change, not *whether* to build it.

Alternatives considered and rejected:
- **Teach every JSON-shape-aware function (`extract_records_at_path`, all 6 pagination strategies, `SchemaInferenceEngine._walk_record`, `DataPreviewService`) to understand XML natively.** Rejected — every one of those functions already operates purely on Python `dict`/`list`, downstream of the single `response.json()` call. Duplicating XML-awareness into each of them multiplies the surface area for no benefit.

## 3. Riskiest Assumption

Normalizing arbitrary XML (including namespaced, SRU/MARCXML-shaped responses) into the same `dict`/`list` convention `response.json()` already produces will let the entire existing downstream pipeline work unmodified. If wrong — e.g. mixed content or irregular namespacing doesn't collapse cleanly into that shape — the single-chokepoint design breaks, and parts of the pipeline need bespoke XML-aware traversal, a materially larger and differently-shaped effort. This is independently testable and is addressed by a Technical Spike (`plan.md` Phase 1) before full implementation proceeds.

## 4. Expected Value

Endpoints that return XML reach full feature parity with JSON endpoints — connection test, data root/record-count path configuration, schema inference, data preview (including the same row/column table, Export CSV/JSON, and pagination UI), and all 6 pagination strategies — removing a currently misleading dead end for a real class of target APIs (public-data/SRU).

## 5. Context & Goals

**Context**: Django/DRF + React monorepo (`docs/project-detail.md`), functionally complete for JSON-only MVP scope (Phase 0-8, security-audited). This is the first feature planned through the formal 5-stage pipeline in this repo (`docs/features/` did not previously exist).

**Primary goal**: an endpoint configured with `response_format = xml` behaves identically, from the user's perspective, to a JSON endpoint at every stage of the pipeline except the "Raw Response" preview panel, which shows the true XML text instead of a JSON reinterpretation.

**Stakeholders/users**: whoever configures connector endpoints against XML-returning APIs (confirmed target: government/public-data SRU APIs).

**Success criteria** (concrete, falsifiable):
- SC1: An XML endpoint's connection test result's detected format (`"xml"`) becomes the endpoint's default `response_format` at creation time, editable by the user.
- SC2: `PaginationEngine.paginate()` successfully yields records for an XML endpoint using the same `data_root_path` dot-notation convention JSON endpoints use, with namespaces stripped from the resolvable paths.
- SC3: All 6 pagination strategies function against an XML endpoint exactly as they do against JSON — including the 3 that read values out of the response body (`Cursor`, `NextURL`, `PageSize`'s `total_pages_path`) via the same dot-notation traversal, with zero code changes to the strategies themselves.
- SC4: Schema inference produces a sane, editable field list for an XML endpoint via the existing `SchemaInferenceEngine`, with zero code changes to `_walk_record`/type inference.
- SC5: Data Preview for an XML endpoint renders the identical table UI (rows, columns, `N/N fields included`, Export CSV/JSON, row-limit control) as a JSON endpoint, built from the same `DataPreviewService` code path.
- SC6: The "Raw Response" panel for an XML endpoint shows the original XML text the API returned, not a JSON-serialized reinterpretation of the parsed body.
- SC7: A single, XXE-safe XML parsing module handles all XML parsing in the codebase — no direct use of an XXE-unsafe parser anywhere (mirrors the ADR-005 single-call-site pattern already enforced for Fernet).
- SC8: End-to-end validation against a real SRU (or comparably namespaced) public XML API completes the full flow (connection test → configure `data_root_path` → schema inference → data preview) without manual workarounds.

## 6. Functional Requirements

- FR1: `Endpoint` gains a `response_format` field (`TextChoices`: `json`, `xml`), defaulted from `ConnectionProfile.last_test_detected_format` at endpoint creation, user-editable via the endpoint form.
- FR2: `PaginationEngine` branches on `endpoint.response_format` at the current `response.json()` call site, dispatching to a JSON parse (unchanged) or an XXE-safe XML→dict/list normalization (new).
- FR3: The XML→dict/list normalization strips XML namespace prefixes from element/attribute names before they reach dot-notation resolution, so `data_root_path`, `key_path`, `cursor_response_path`, `next_url_response_path`, and `total_pages_path` all resolve using the same simple dot-notation JSON endpoints use today.
- FR4: The normalization coerces both a single occurrence and multiple occurrences of a repeated element into a list consistently, so `data_root_path` resolution doesn't silently behave differently based on how many records a given response happens to contain.
- FR5: `extract_records_at_path`, `get_at_path`, `detect_data_root`, `SchemaInferenceEngine._walk_record`, and `DataPreviewService` require no logic changes — they consume the normalized `dict`/`list` exactly as they consume a parsed JSON body today.
- FR6: `DataPreviewService` preserves the original raw XML response text (not a JSON re-serialization) for XML-format endpoints, surfaced via the existing `raw_response_body` field / `RawResponseViewer` component.
- FR7: The `PaginationEngineError` raised on unparseable bodies is format-aware in its message (references the actual configured/detected format, not a hard-coded "non-JSON" assumption).
- FR8: Endpoint form UI surfaces `response_format` (view/edit), matching the existing pattern for other endpoint-level config fields.

## 7. Non-Functional Requirements

- NFR1: **Security — XXE**: XML parsing must use an XXE-safe parser/configuration (e.g. `defusedxml`) as the sole XML-parsing call site in the codebase, mirroring the ADR-005 single-call-site enforcement pattern for Fernet. `[ASSUMPTION]` — no CI-mechanical enforcement (grep-based, like ADR-005's) is assumed required for MVP scope; a code-review convention note is the floor. What changes if wrong: add a CI grep check analogous to `backend-ci.yml`'s ADR-005 check.
- NFR2: **Compatibility**: no change to any existing JSON-endpoint behavior, response shape, or API contract. This is a strictly additive capability.
- NFR3: **Data handling**: XML raw-body sampling/storage follows the same "metadata only in logs, capped sample size" convention already applied to JSON response bodies (`http_client.py`'s "never log body" contract, `ConnectionTestResult.step_results`' 2KB cap, `DataPreviewService`'s 50,000-char `raw_response_body` cap) — no new PII-handling surface introduced.
- NFR4: **Performance**: XML parsing/normalization runs within the same per-page pagination loop as JSON parsing does today; no new network round-trips introduced. `[ASSUMPTION]` — no specific latency target set beyond "doesn't meaningfully change the existing (unvalidated) network-bound NFR targets documented in `docs/benchmark-results.md`." What changes if wrong: benchmark XML-endpoint pagination explicitly.

## 8. Constraints (hard)

- `PaginationEngine.paginate()`'s generator-based contract (ADR-010) is IRREVERSIBLE — the XML format branch must preserve generator/yield semantics; no list-based rewrite.
- `BaseHTTPClient`/`httpx.Client` synchronous architecture (ADR-006) is IRREVERSIBLE — XML parsing happens on the already-fetched `httpx.Response`, no new async code path.
- All enums in this codebase are `TextChoices` (ADR-003) — `response_format` must follow this, not a free-text `CharField` like `last_test_detected_format`.
- Encryption/secrets handling is untouched by this feature — no credential-adjacent code paths are modified.
- Migrations in this app are purely additive, no `RunPython` data migrations (existing convention, `0001`-`0004`) — the new `response_format` migration must follow the same shape.

## 9. Inferred Constraints

- `[INFERRED]` XML request bodies (POST payloads) are out of scope — the request explicitly says "XML API **responses**," and `BaseHTTPClient`'s recently-added POST support (`e4810b4`) sends JSON bodies only. What changes if wrong: adding XML request-body support would need its own requirement pass — outbound serialization is a materially different problem than inbound parsing.
- `[INFERRED]` The XML support only needs to reach parity with what JSON endpoints *actually* do today, not fix pre-existing gaps that also affect JSON (e.g. `record_count_path` is persisted but never consumed by any backend service, for JSON or XML). What changes if wrong: if the human wants `record_count_path` wired up as part of this feature, that's additional scope beyond parity.

## 10. Assumptions

- `[ASSUMPTION]` Format routing is via a persisted `Endpoint.response_format` field (not per-request re-sniffing). Confirmed with the human during convergence. What changes if wrong: re-sniffing removes the new model field/migration but adds per-page format-detection overhead and risks inconsistent behavior mid-pagination.
- `[ASSUMPTION]` XML namespace prefixes are stripped by default in all dot-notation path resolution. Confirmed with the human during convergence. What changes if wrong: paths would need to carry explicit namespace prefixes, a bigger UX departure from the existing JSON dot-path convention.
- `[ASSUMPTION]` The "Raw Response" preview panel shows original XML text for XML endpoints, not a JSON reinterpretation. Confirmed with the human during convergence.
- `[ASSUMPTION]` `defusedxml` (or an equivalent XXE-safe wrapper) is an acceptable new dependency; no XML library exists in `requirements.txt` today, so this is additive, not a replacement of anything. What changes if wrong: a different specific library can be swapped in Phase 2 without affecting the rest of the plan — the choice is validated in Phase 1's spike, not locked here.
- `[ASSUMPTION]` Attribute values and text content in a normalized XML element follow a documented convention (e.g. `@attr` / `#text` keys, to be confirmed in Phase 1's spike against a real sample) rather than being silently dropped. What changes if wrong: if attributes turn out to carry no meaningful data for the target APIs (SRU/MARCXML), the convention can be simplified.

## 11. Precedent & Integration

- **Adapt, not replace, the pagination chokepoint**: `PaginationEngine.paginate()` already centralizes all response-body parsing to one call site (`engine.py:146`) — this feature extends that single site with a format branch rather than introducing parallel JSON/XML code paths through `extract_records_at_path`, the 6 strategies, `SchemaInferenceEngine`, or `DataPreviewService`. See `decisions.md` DEC-1.
- **New XML library is additive**: no existing pattern to disrupt (no XML library present anywhere in the codebase today). XXE-safety is treated as a hard requirement given the project's security-conscious precedent (dedicated SSRF module, `docs/security-audit.md`) even though no XML-specific precedent exists yet. See `decisions.md` DEC-2.
- **`response_format` as `TextChoices`**: follows ADR-003 (all enums are `TextChoices`), not the free-text `CharField` pattern `ConnectionProfile.last_test_detected_format` currently uses. See `decisions.md` DEC-3.
- **Endpoint-level persisted config drives fetch behavior**: matches the existing `data_root_path`/`PaginationConfig` pattern of storing per-endpoint configuration that governs how a response is fetched/parsed, rather than introducing runtime format re-detection. See `decisions.md` DEC-4.

## 12. Out of Scope

- XML request bodies (outbound POST payload serialization) — response parsing only.
- Wiring up runtime consumption of `record_count_path` — it's unconsumed for JSON today; bringing it to life is a pre-existing gap, not XML parity work.
- SOAP/WSDL-specific handling beyond generic XML parsing.
- A CI-mechanical single-call-site enforcement check for the new XML parsing module (analogous to ADR-005's Fernet grep check) — noted as a possible follow-up in NFR1, not committed here.
- Any change to JSON-endpoint behavior, existing pagination strategies' JSON-facing logic, or the existing 6-step connection test diagnostic beyond consuming its already-computed detected format.
