# XML Parsing Core & Format Routing — Breakdown

Feature: `001-xml-response-support` · Phase 2 of 4: XML Parsing Core & Format Routing
Branch: `001-xml-response-support` · Generated against commit `069b461e53a61b73e227c8c43ce78f9347a2d21e`
Previous phase: Phase 1 (Technical Spike) — Reconciled 🟡 YELLOW. Confirmed and independently re-verified: library = `xmltodict` (not the originally-tentative `defusedxml.ElementTree`; `defusedexpat` is dead), namespace stripping = colon-prefix regex via `xmltodict`'s `postprocessor=` hook, list coercion = two-pass `(parent_tag, child_tag)`-scoped algorithm, attribute/text = native `@attr`/`#text` with automatic pure-text-leaf collapse. Promoted to `decisions.md` DEC-8.
Next phase: Phase 3 — Schema Inference & Data Preview Integration (for continuity only; not broken down here)
Source: `plan.md` §8 Phase 2

---

## 1. Phase Context

**Purpose & Outcome**: Replace the hard-coded `response.json()` call at `PaginationEngine`'s single parse chokepoint with a format-aware branch, backed by a new production XML→dict/list converter that ports Phase 1's confirmed `xmltodict`-based convention, and a persisted `Endpoint.response_format` field that drives the branch. Outcome: an XML-configured endpoint's `paginate()` call yields the identical `(records, body)` shape a JSON endpoint yields today, with zero changes to anything downstream of the chokepoint.

**Dependencies**: Needs Phase 1's confirmed conventions (`DEC-8`, `spike-findings.md`) — all inputs to this phase's design are already resolved by trial-and-observation, not assumed. Produces: the format-routing field and the normalized-body output every later phase (3: schema/preview integration, 4: frontend/e2e) consumes.

**Scope calibration note**: Lean. 7 atomic tasks across 3 subphases, 1 `[REVIEW-GATE]`, 0 `[IRREVERSIBLE]` tasks — well under the escalation threshold. The phase's only real algorithmic complexity (list coercion) was already solved and independently re-verified in Phase 1; this phase is a faithful port plus one routine `TextChoices` field addition (the project's 5th — `AuthType`, `PaginationStrategy`, `HTTPMethod`, `TokenType` precede it), not new design work.

**Two things resolved by reading the current code, not left as open questions**:

1. **`detect_data_root()` needs no XML-aware variant** (plan.md §8's flagged "Key Decision"). Read `services/pagination/utils.py:73-115`: it walks `response_body` using only `isinstance(obj, dict)` / `isinstance(value, list)` checks — no JSON-specific parsing, no format awareness anywhere in the function. Once a body is normalized to `dict`/`list` (this phase's job), `detect_data_root()` already works unchanged, exactly as Phase 1 proved for `extract_records_at_path`. No task added for this.
2. **`DEC-8`'s namespace-stripping prose describes the wrong candidate's mechanism.** `DEC-8` says namespace stripping reduces "Clark notation (`{uri}localname`) to `localname` via a single regex" — that's the `defusedxml.ElementTree` candidate's shape. Since `DEC-8` recommends `xmltodict` instead, the actual mechanism this phase must port is `phases/phase-1/spike/trial_xmltodict.py`'s colon-prefix regex (`^[^:]+:`) applied via `xmltodict`'s `postprocessor=` hook (`trial_xmltodict.py:150-166`), which also drops bare `@xmlns`/`@xmlns:*` attribute keys entirely. P2.A-02 cites this file directly, not `DEC-8`'s prose, for the exact mechanism.

---

## 2. Open Decisions

None. `DEC-8` (Origin: Breakdown Engineer · Phase 1 · REVISE, independently re-verified by Reconciler) already resolves the library choice and normalization convention. The one prose imprecision in `DEC-8` (see Phase Context item 2 above) is a citation correction, not an ambiguous or high-consequence call — resolved inline by reading `trial_xmltodict.py` directly, per "Asking vs Assuming."

---

## 3. Subphases & Atomic Tasks

### P2.A — XML Parsing Module

**Objective**: Build the production, XXE-safe XML→dict/list converter as a new sibling service module (alongside `http_client.py`/`ssrf.py`/`encryption.py`), porting Phase 1's confirmed `xmltodict`-based algorithm faithfully — a direct port, not new design.
**Deliverables**: `services/xml_parser.py` with `parse_xml_response()`; `xmltodict` pinned in `requirements.txt`.
**Complexity/risk**: Low design risk (already validated and independently re-verified in Phase 1), but the two-pass list-coercion logic is easy to get subtly wrong if re-derived from scratch instead of ported line-for-line from `trial_xmltodict.py`. Review should check the ported logic against `spike-findings.md` §3's `dc:creator` 1/absent/2 → list/absent/list before/after proof, not just skim for "looks reasonable."

```
Task ID:                  P2.A-01
Title:                    Add xmltodict dependency  [P]
Description:              Add `xmltodict>=1.0.4` to `backend/requirements.txt`, following the
                          file's existing lower-bound-pin convention (e.g. `httpx>=0.27`,
                          `cryptography>=42`) — one new line, alphabetical position not
                          enforced by the existing file (it isn't alphabetized today). Per
                          DEC-8: this is the confirmed candidate, not `defusedxml`
                          (already present transitively, not a new direct dependency) and
                          not `defusedexpat` (dead, must not be added).
Why This Matters:         P2.A-02 cannot import `xmltodict` without this; a missing pin also
                          means CI's dependency install silently uses whatever gets resolved
                          transitively (or fails), not a reproducible pinned version.
Dependencies:              None
Inputs/Preconditions:     backend/requirements.txt (confirmed).
Output/Artifact:          `xmltodict>=1.0.4` line in requirements.txt; verifiable via
                          `pip install -r requirements.txt` succeeding and
                          `python -c "import xmltodict; print(xmltodict.__version__)"`.
Placeholders:             None
Decision Type:            None — DEC-8 already made this call; this task executes it.
Security & Observability: N/A — dependency addition only. `pip-audit` (already in the CI
                          pipeline per project-detail.md §2) covers ongoing CVE monitoring;
                          Phase 1's Reconciler already ran it once against 1.0.4 with no
                          findings.
Testing Notes:            None beyond the install itself succeeding — no code exists yet to
                          test.
```

```
Task ID:                  P2.A-02
Title:                    Create services/xml_parser.py with parse_xml_response()
Description:              New file `backend/api_connector/services/xml_parser.py`, sibling to
                          `services/ssrf.py`/`services/encryption.py`, following their module
                          docstring shape (purpose, security note, any accepted-limitation
                          note — see `services/ssrf.py:1-24` for the exact shape to match).
                          Public function: `parse_xml_response(xml_bytes: bytes) -> dict | list`.
                          Implement by porting `phases/phase-1/spike/trial_xmltodict.py`
                          exactly (not re-deriving):
                            - Namespace stripping: the colon-prefix regex `^[^:]+:` applied via
                              a `postprocessor=` callable (`trial_xmltodict.py:150-166`) — strips
                              `dc:title` → `title`, `@xsi:type` → `@type`, and drops
                              `@xmlns`/`@xmlns:*` keys entirely (not meaningful attributes).
                              This is the mechanism to port — see Phase Context item 2 above on
                              why DEC-8's own "Clark notation" prose describes the other
                              (unchosen) candidate instead.
                            - List coercion: the two-pass algorithm scoped by
                              `(parent_tag, child_tag)` pair (`trial_xmltodict.py:169-219`) —
                              Pass 1 parses once with `force_list=True` to collect, per pair,
                              the max occurrence count under any single parent instance anywhere
                              in the document; Pass 2 parses AGAIN with a `force_list` callable
                              consulting those counts. This means `xmltodict.parse()` runs twice
                              per XML body — an intentional, already-measured cost (Phase 1
                              §8.4), not a bug to optimize away in this task.
                            - Attribute/text convention (`@attr`/`#text`, pure-text-leaf
                              collapse): native to `xmltodict`'s defaults — no extra code needed
                              beyond what namespace-stripping/list-coercion already require.
                          Explicitly pass `disable_entities=True` on BOTH `xmltodict.parse()`
                          calls (Pass 1 and Pass 2), even though it is xmltodict 1.0.4's own
                          default — makes the XXE-safety guarantee visible in this codebase's
                          code, not an implicit library default that could silently change on
                          a future xmltodict upgrade.
Why This Matters:         This is the sole XML-parsing call site the feature adds (SC7) and
                          the one piece of real algorithmic complexity in the whole phase
                          (DEV-1) — a naive flat-count or unconditional-list implementation is
                          proven broken (spike-findings.md §3) and will silently corrupt
                          `data_root_path` resolution for any endpoint with a singular,
                          non-repeating container element.
Dependencies:              P2.A-01
Inputs/Preconditions:     trial_xmltodict.py (confirmed, phases/phase-1/spike/); xmltodict
                          installed (confirmed once P2.A-01 lands).
Output/Artifact:          services/xml_parser.py with parse_xml_response(); verifiable by a
                          unit test asserting byte-for-byte-equivalent (sort_keys JSON
                          comparison) output to Phase 1's own
                          `phases/phase-1/spike/raw_output_xmltodict.txt` when run against
                          `phases/phase-1/spike/sample.xml`.
Placeholders:             None
Decision Type:            [REVERSIBLE] — implements DEC-8's already-decided library
                          (xmltodict) and algorithm; swapping the library later touches only
                          this module's internals, per DEC-8's own reversibility note.
Security & Observability: `disable_entities=True` explicit on both parse calls (see
                          Description). On a rejected/malformed payload, log only the
                          exception's type name and nothing else (e.g.
                          `logger.warning("XML parse rejected: %s", type(exc).__name__)` via
                          `logging.getLogger("api_connector.xml_parser")`) — never the raw XML
                          body or the exception's message text, either of which may echo
                          attacker-supplied content, matching `http_client.py`'s "never log
                          body" contract (`services/http_client.py:27-31`). Do NOT build the
                          optional hardened-expat shim (`_HardenedExpatModule` in
                          `trial_xmltodict.py`) this task — DEC-8 accepts the shared
                          bare-DOCTYPE-no-entity gap as a non-differentiating MVP-scope
                          limitation; note the shim's existence and file location in this
                          module's docstring as a documented future-hardening option (matching
                          `ssrf.py`'s own "accepted limitation" documentation style), don't
                          build it now.
Testing Notes:            Happy path: `sample.xml` (real DNB SRU response) → 3 records
                          resolvable via `extract_records_at_path` with
                          `data_root_path="searchRetrieveResponse.records.record"`; the
                          designed single/absent/multi `dc:creator` case (1/0/2 occurrences)
                          → list-of-1/absent/list-of-2, per spike-findings.md §3's proof. Edge
                          cases (reuse Phase 1's fixtures directly —
                          `phases/phase-1/spike/samples/*.xml` — do not hand-author new XML):
                          mixed content (`sample_mixed_content.xml`) confirms xmltodict's
                          native handling needs no custom `elem.text`/`.tail` concatenation
                          (unlike the ElementTree path Phase 1 also trialed and had to fix);
                          namespace collision (`sample_ns_collision.xml`) confirms the accepted
                          DEC-5 behavior (two differently-namespaced same-local-name elements
                          silently merge into one list) — assert this as documented behavior,
                          not treat it as a bug. Security: the 3 payloads from
                          spike-findings.md §8.2 (classic XXE → rejected; billion-laughs →
                          rejected; bare DOCTYPE with no entity → allowed, the shared accepted
                          gap) run as in-memory strings only, never persisted. Failure mode:
                          non-well-formed XML raises (exact exception type is xmltodict's own —
                          confirm what P2.B-01's catch site needs to handle).
```

### P2.C — Endpoint.response_format Field

**Objective**: Add the persisted, user-editable `TextChoices` field that routes `PaginationEngine`'s format dispatch, defaulted from the connection test's already-detected format at endpoint-creation time.
**Deliverables**: `ResponseFormat` enum; `Endpoint.response_format` field + migration; serializer exposure; creation-time defaulting logic.
**Complexity/risk**: Low — a routine `TextChoices` field addition following an established pattern (4 existing precedents: `AuthType`, `PaginationStrategy`, `HTTPMethod`, `TokenType`). The only non-mechanical piece is P2.C-04's defaulting logic, which touches a view method (`create()`) that currently does not fetch the parent `ConnectionProfile` object at all.

```
Task ID:                  P2.C-01
Title:                    Add ResponseFormat enum + Endpoint.response_format field  [P]
Description:              In `backend/api_connector/models/enums.py`, add
                          `class ResponseFormat(models.TextChoices): JSON = "json", "JSON";
                          XML = "xml", "XML"`, immediately after the existing `HTTPMethod`
                          class (enums.py:41-44) — same two-value-tuple shape every other enum
                          in this file uses. In `backend/api_connector/models/endpoint.py`,
                          import `ResponseFormat` alongside the existing `HTTPMethod` import
                          (line 4) and add
                          `response_format = models.CharField(max_length=10,
                          choices=ResponseFormat.choices, default=ResponseFormat.JSON)`,
                          placed after `endpoint_headers` (line 40) and before `data_root_path`
                          (line 42) — matching `AuthType`'s exact shape on
                          `ConnectionProfile.auth_type` (`models/connection_profile.py:23-27`).
                          This field determines which parser `PaginationEngine.paginate()`
                          dispatches to (DEC-4) — it is a persisted config value, not
                          re-detected per request. Export `ResponseFormat` from
                          `models/__init__.py`'s enums import block (lines 6-13) and its
                          `__all__` list (lines 19-34), alphabetically ordered matching the
                          existing entries.
Why This Matters:         Without this field, PaginationEngine has nothing to branch on —
                          every endpoint stays silently JSON-only regardless of P2.A's new
                          parser existing.
Dependencies:              None  [P]
Inputs/Preconditions:     models/enums.py (confirmed); models/endpoint.py (confirmed);
                          models/__init__.py (confirmed).
Output/Artifact:          Endpoint.response_format field present, defaulting to "json";
                          verifiable via `python manage.py shell -c "from api_connector.models
                          import Endpoint; print(Endpoint._meta.get_field('response_format')
                          .default)"` printing `json`.
Placeholders:             None
Decision Type:            [REVERSIBLE] — follows ADR-003's TextChoices convention exactly
                          (DEC-3); adapts the existing enum/field pattern, no new shape.
Security & Observability: N/A — response_format is non-secret configuration (like `method`,
                          `data_root_path`); no encryption, no special logging treatment.
Testing Notes:            A factory-created Endpoint with no explicit response_format
                          defaults to "json" (extend EndpointFactory in tests/factories.py to
                          confirm — it currently has no response_format override, so it should
                          already inherit the model default with zero factory changes needed;
                          confirm this holds rather than assuming it). No dedicated
                          model-field unit test beyond that — coverage comes via P2.C-03's
                          serializer tests and P2.C-02's migration.
```

```
Task ID:                  P2.C-02
Title:                    Create additive migration for Endpoint.response_format
Description:              Run `python manage.py makemigrations api_connector` after P2.C-01
                          lands, producing
                          `backend/api_connector/migrations/0005_endpoint_response_format.py`
                          with a single `AddField` operation depending on
                          `0004_oauth_ac_state` — matching `0003_oauth_token.py`'s
                          `CharField(choices=..., default=..., max_length=...)` shape exactly
                          (migrations/0003_oauth_token.py:25-34). Must be purely additive — no
                          `RunPython` — matching the existing `0001`-`0004` chain's constraint
                          (requirement.md §8).
Why This Matters:         Without this migration, the model field exists in Python but not in
                          the database — every read/write against response_format fails (or
                          silently diverges) in any environment that hasn't run it.
Dependencies:              P2.C-01
Inputs/Preconditions:     P2.C-01's model field (confirmed once P2.C-01 lands);
                          migrations/0004_oauth_ac_state.py (confirmed, exists).
Output/Artifact:          migrations/0005_endpoint_response_format.py; verifiable via
                          `python manage.py migrate --check` reporting no pending migrations,
                          and `python manage.py sqlmigrate api_connector 0005` showing a
                          single `ADD COLUMN`.
Placeholders:             None
Decision Type:            [REVERSIBLE] — additive schema change, standard Django migration.
Security & Observability: N/A — no data migration, no PII, no credential-adjacent change.
Testing Notes:            Migration applies cleanly against a fresh test DB (implicit in
                          every `@pytest.mark.django_db` run); pre-existing rows default to
                          "json" with no data loss. No dedicated migration test beyond what
                          pytest-django's DB setup already exercises on every test run.
```

```
Task ID:                  P2.C-03
Title:                    Surface response_format in Endpoint serializers
Description:              Add `"response_format"` to `Meta.fields` in
                          `EndpointReadSerializer` (serializers/endpoint.py:48-64),
                          `EndpointCreateSerializer` (:94-104), and `EndpointUpdateSerializer`
                          (:186-196 — plus its `extra_kwargs` loop at :198-210, so it stays
                          optional on PATCH exactly like every other field there). No custom
                          `validate_response_format()` — DRF's `ModelSerializer`
                          auto-generates a `ChoiceField` from the model's
                          `choices=ResponseFormat.choices`, which already rejects any value
                          outside `"json"`/`"xml"` with the standard DRF choice-field error.
Why This Matters:         FR1/FR8 require response_format to be user-viewable and
                          user-editable; without this it exists in the DB but is invisible and
                          immutable through the API Phase 4's endpoint form will call.
Dependencies:              P2.C-01, P2.C-02
Inputs/Preconditions:     serializers/endpoint.py (confirmed); Endpoint.response_format field
                          + migration (confirmed once P2.C-01/02 land).
Output/Artifact:          response_format present in list/retrieve responses and accepted on
                          create/PATCH; verifiable via a round-trip test — create with
                          `{"response_format": "xml"}` persists and reads back "xml"; an
                          invalid value (e.g. "yaml") returns 400.
Placeholders:             None
Decision Type:            [REVERSIBLE] — extends the existing three-serializer pattern
                          (project-detail.md §7 "API & naming conventions"); no new pattern.
Security & Observability: response_format is non-secret; no new validation risk beyond DRF's
                          standard choice-field check.
Testing Notes:            Happy path: explicit response_format="xml" on create persists and
                          round-trips; PATCH updates it. Edge cases: invalid enum value → 400;
                          omitting response_format on create leaves the defaulting decision to
                          P2.C-04 (test that omission specifically, separately from an explicit
                          value). Follow test_endpoint_serializers.py's existing structure.
```

```
Task ID:                  P2.C-04
Title:                    Default response_format from ConnectionProfile.last_test_detected_format at creation
Description:              In `EndpointViewSet.create()` (views/endpoint.py:103-115), fetch the
                          parent profile via
                          `connection_profile = get_object_or_404(ConnectionProfile,
                          pk=profile_pk)` — matching `get_queryset()`'s existing
                          `get_object_or_404` call at line 88 (`ConnectionProfile` is already
                          imported at line 21). Before calling `write_serializer.save(...)`: if
                          `"response_format"` is absent from `request.data`, compute
                          `default_format = connection_profile.last_test_detected_format if
                          connection_profile.last_test_detected_format in
                          ResponseFormat.values else ResponseFormat.JSON` (import
                          `ResponseFormat` from `api_connector.models.enums`, matching
                          `services/auth/registry.py:2`'s exact import-only-the-enum pattern)
                          and pass it as
                          `write_serializer.save(connection_profile_id=profile_pk,
                          response_format=default_format)`; otherwise call
                          `write_serializer.save(connection_profile_id=profile_pk)` unchanged,
                          letting the already-validated user-supplied value win. Domain rule:
                          only `last_test_detected_format` values of exactly `"json"` or
                          `"xml"` become the default — `"csv"`/`"html"`/`"plain_text"`/`None`
                          (never-tested profile) fall back to the model's own `"json"` default,
                          per DEC-4/FR1's "defaulted from the connection test's already-computed
                          format."
Why This Matters:         Without this, SC1 fails outright — a profile that already detected
                          "xml" during connection test would still create JSON-defaulted
                          endpoints, silently reproducing the exact dead-end (requirement.md
                          §1) this feature exists to close.
Dependencies:              P2.C-03
Inputs/Preconditions:     ConnectionProfile.last_test_detected_format (confirmed,
                          models/connection_profile.py:39); ResponseFormat enum (confirmed
                          once P2.C-01 lands).
Output/Artifact:          EndpointViewSet.create() computing and applying the default;
                          verifiable via an API test — create an endpoint on a profile with
                          last_test_detected_format="xml" and no response_format in the
                          request body, assert the created endpoint's response_format == "xml".
Placeholders:             None
Decision Type:            [REVERSIBLE] — adapts the existing "endpoint-level persisted config
                          drives fetch behavior" precedent (DEC-4); the
                          fallback-to-model-default branch for non-json/xml detected formats
                          is the direct reading of FR1, not a new decision requiring sign-off.
Security & Observability: No new outbound calls, no credential access — reads only a
                          non-secret metadata field already documented as safe
                          (models/connection_profile.py:16-18). Log the resolved format
                          alongside the existing "Endpoint created" info log
                          (views/endpoint.py:109-114) — response_format is not sensitive.
Testing Notes:            Happy path: profile with last_test_detected_format="xml", no
                          response_format in request → endpoint defaults to "xml". Edge cases:
                          last_test_detected_format="csv"/"html"/"plain_text" → defaults to
                          "json" (not null, not the unsupported value); never-tested profile
                          (last_test_detected_format=None) → defaults to "json"; explicit
                          response_format supplied → wins regardless of last_test_detected_format
                          (test both agreement and conflict). Follow test_endpoint_api.py's
                          existing ConnectionProfileFactory/EndpointFactory structure.
```

### P2.B — PaginationEngine Format Branch  [REVIEW-GATE]

**Objective**: Wire P2.A and P2.C together at the existing parse chokepoint, replacing the hard-coded `response.json()` call with a format-aware branch, without altering the generator contract.
**Deliverables**: Modified `paginate()` parse block; format-aware `PaginationEngineError` message.
**Complexity/risk**: High blast radius, low design complexity — a ~10-line change to a function every JSON endpoint in production already depends on (ADR-010, IRREVERSIBLE). A mis-scoped edit here regresses the entire existing JSON pipeline, not just XML — this is why plan.md §8 marks this subphase `[REVIEW-GATE]`.

```
Task ID:                  P2.B-01
Title:                    Format-aware parse branch in PaginationEngine.paginate()
Description:              Replace the JSON-only parse block at engine.py:144-151 —
                            ```
                            # Parse JSON
                            try:
                                body = response.json()
                            except (json.JSONDecodeError, Exception) as exc:
                                raise PaginationEngineError(
                                    f"API returned non-JSON response at page "
                                    f"{cumulative_page_count + 1}. Enable data_root_path "
                                    f"validation or check the endpoint URL."
                                ) from exc
                            ```
                          — with a branch on `endpoint.response_format`:
                          `ResponseFormat.JSON` → `response.json()` (unchanged);
                          `ResponseFormat.XML` → `xml_parser.parse_xml_response(response.content)`
                          (new — pass `response.content`, the raw bytes, NOT `response.text`,
                          so the parser honors the XML prolog's own `encoding=` declaration
                          instead of double-decoding through httpx's Content-Type-based charset
                          guess; matches P2.A-02's `parse_xml_response(xml_bytes: bytes)`
                          signature). Keep the existing broad `except (..., Exception)` clause —
                          it already covers xmltodict's parse failures with no new import
                          needed — but make the raised `PaginationEngineError`'s message
                          format-aware: reference `endpoint.response_format` instead of the
                          hard-coded `"non-JSON"` string (FR7). Import `xml_parser` (P2.A-02)
                          and `ResponseFormat` (from `api_connector.models.enums`, matching
                          `services/auth/registry.py:2`'s import-only-the-enum precedent) at
                          the top of engine.py alongside the existing
                          `pagination.utils` import block (lines 32-35). This is the sole
                          change to `paginate()` — the surrounding `yield records, body`
                          generator structure (line 183) and everything after it is untouched,
                          preserving ADR-010's generator contract exactly.
Why This Matters:         This is the single chokepoint (DEC-1) every downstream consumer —
                          extract_records_at_path, all 6 pagination strategies,
                          SchemaInferenceEngine, DataPreviewService — depends on for a
                          normalized dict/list body. A mis-wired branch here either breaks XML
                          endpoints outright or, worse, silently breaks the JSON path that has
                          been in production since Phase 6.
Dependencies:              P2.A-02, P2.C-02
Inputs/Preconditions:     services/xml_parser.py's parse_xml_response() (confirmed once
                          P2.A-02 lands); Endpoint.response_format field (confirmed once
                          P2.C-02 lands).
Output/Artifact:          paginate() yielding an identical (records, body) shape for both
                          formats; verifiable via a PaginationEngine test using an
                          XML-configured Endpoint + httpx_mock returning Phase 1's
                          spike/sample.xml body, asserting extract_records_at_path resolves 3
                          records exactly as the spike proved.
Placeholders:             None
Decision Type:            [REVERSIBLE] — adapts the existing single-branch-point pattern
                          (DEC-1); does not alter the generator/yield contract itself (ADR-010
                          remains untouched — this task must not attempt to change that shape,
                          it is IRREVERSIBLE per the ADR).
Security & Observability: On a parse failure, log only the exception's type name and the page
                          number at WARNING level (matching P2.A-02's xml_parser-level logging
                          convention) — never the response body or the raw exception message,
                          which may echo attacker-supplied XML content, matching
                          http_client.py's "never log body" contract
                          (services/http_client.py:27-31). No new outbound calls or credential
                          access — this task only changes how an already-fetched response is
                          parsed.
Testing Notes:            Happy path: XML-configured endpoint + valid XML body → same
                          records/body shape as an equivalent JSON test. Edge cases:
                          malformed (non-well-formed) XML body → PaginationEngineError with a
                          message naming "xml", not "non-JSON"; ALL existing JSON-endpoint
                          tests (test_pagination_engine.py) must continue passing unmodified —
                          zero regression on the JSON path is the actual bar for this task, not
                          just "XML works." Confirm the row_limit early-exit (lines 157-159)
                          and the generator's for/next early-stop behavior (schema inference's
                          max_pages=3 cap) both still work against an XML-configured endpoint,
                          matching plan.md §11's "generator contract unchanged" final-state
                          item.
```

---

## 4. Phase Acceptance Criteria & Verification

**Completion criteria** (falsifiable, traced to `requirement.md` §5 Success Criteria this phase owns):

- **AC1** (traces SC1): WHEN an `Endpoint` is created without an explicit `response_format` AND the parent `ConnectionProfile.last_test_detected_format` is `"json"` or `"xml"`, THE SYSTEM SHALL persist that detected value as the endpoint's `response_format`. WHEN `last_test_detected_format` is anything else (`None`, `"csv"`, `"html"`, `"plain_text"`), THE SYSTEM SHALL default to `"json"`. WHEN `response_format` is explicitly supplied in the create request, THE SYSTEM SHALL use the supplied value regardless of `last_test_detected_format`.
- **AC2** (traces SC2): WHEN `PaginationEngine.paginate()` is called against an endpoint with `response_format="xml"`, THE SYSTEM SHALL yield the same `(records, body)` shape it yields for JSON, with all element/attribute namespace prefixes stripped from dict keys, such that a `data_root_path` dot-notation string resolves the record list exactly as it would for an equivalent JSON body.
- **AC3** (traces SC2/FR4): WHEN a repeated XML element occurs once under one parent instance but multiple times elsewhere in the same document, THE SYSTEM SHALL normalize both occurrences to a Python `list` at the same dot-path — not a scalar for the single occurrence (the `(parent_tag, child_tag)`-scoped list-coercion rule, DEV-1).
- **AC4** (traces SC7): A repo-wide search confirms `xmltodict`/`xml.*` parsing calls exist only inside `services/xml_parser.py` — no other module parses XML directly. (Manual check per requirement.md NFR1's stated floor — no CI-mechanical grep check is committed this phase, per requirement.md §12.)
- **AC5** (traces FR7): WHEN `response.content` is unparseable for the endpoint's configured `response_format`, THE SYSTEM SHALL raise `PaginationEngineError` with a message naming the actual configured format, not a hard-coded `"non-JSON"` string.
- **AC6** (constraint, ADR-010): The modified `paginate()` remains a generator (uses `yield`, no list-based rewrite) — verified by inspection, and by confirming the existing JSON-path test suite (`test_pagination_engine.py`, `test_pagination_strategies.py`, `test_pagination_framework.py`) continues passing unmodified.

**Manual verification steps** (human smoke test):

1. Re-run Phase 1's spike validation against the now-production code path instead of throwaway trial code: via `python manage.py shell`, call `xml_parser.parse_xml_response()` directly on `phases/phase-1/spike/sample.xml`'s bytes, then feed the result through the real `extract_records_at_path()` with `data_root_path="searchRetrieveResponse.records.record"` — confirm 3 records resolve, matching Phase 1's and its Reconciler's independent results.
2. Create an `Endpoint` via the API on a `ConnectionProfile` whose `last_test_detected_format` is `"xml"` (or use the Django admin / shell to set it), omitting `response_format` — confirm the created endpoint's `response_format` reads back `"xml"`.
3. PATCH that endpoint's `response_format` to `"json"` and back to `"xml"` — confirm both persist.

**Expected automated coverage** (described, not scripted):

- `xml_parser.py`: unit tests for `parse_xml_response()` — namespace stripping (prefixed elements/attributes → stripped keys, `xmlns` declarations dropped), the two-pass list-coercion (single-vs-multi occurrence proof mirroring spike-findings.md §3), the attribute/text convention, and the 3 XXE/security payloads from spike-findings.md §8.2 — reusing Phase 1's real fixtures (`phases/phase-1/spike/sample.xml`, `phases/phase-1/spike/samples/*.xml`) directly rather than hand-authoring new ones.
- `engine.py`: `PaginationEngine` tests extended with an XML-endpoint variant, following `test_pagination_engine.py`'s existing `httpx_mock` pattern — happy path, malformed-XML failure path (format-aware error message), and confirmation that the generator's early-exit contract (`row_limit` truncation, schema-inference-style `max_pages` early stop) behaves identically for an XML-configured endpoint. Zero regression on every existing JSON-path test is the hard bar, not just new XML tests passing.
- `Endpoint` model/serializer/migration: `response_format` persists correctly on create, respects explicit-override-vs-profile-detected-default (all 4 cases: agree, conflict, non-json/xml detected format, never-tested profile), migration applies cleanly with existing rows defaulting to `"json"` — following `test_endpoint_serializers.py`/`test_endpoint_api.py`'s existing structure.

---

## 5. Handoff Note

Build against commit `069b461e53a61b73e227c8c43ce78f9347a2d21e` on branch `001-xml-response-support`. The one `[REVIEW-GATE]` is subphase P2.B (`PaginationEngine` format branch — touches the shared, IRREVERSIBLE generator-based parse chokepoint every JSON endpoint already depends on). No `[IRREVERSIBLE]` tasks this phase. No unresolved Open Decisions block starting implementation. The implementor writes the code and tests and commits **nothing** — the human commits.

**Carried forward for Phase 3** (continuity only — not broken down here):

- `paginate()` currently yields `(records, body)` where `body` is the normalized `dict`/`list`. DEC-6/Phase 3's P3.B needs the **original raw XML text** preserved for the preview panel — not the same value as `body`, and not currently threaded through the yield anywhere. Phase 3's own breakdown will need to determine how `DataPreviewService` recovers the original `response.text`/`response.content` (it's available at the engine level via the `response` object this phase's P2.B-01 already reads, just not currently exposed past `paginate()`'s return). Flagged here for Phase 3 to resolve against the actual code as it exists after this phase lands — not solved in this phase, per JIT.
- `xmltodict`'s ~1.7x performance overhead vs. `ElementTree`, measured only at a synthetic 5000-record/~3.1MB stress size in Phase 1, is not yet confirmed against real SRU page sizes (tens of records). Phase 4's e2e validation against a real API is the natural place to observe this in practice — not a new task in Phase 2 or 3.
- Residual, already-accepted risks (not new to this phase, just still live): cross-namespace same-local-name key collision (DEC-5); the `(parent_tag, child_tag)` heuristic is document-local, not schema-aware, so a field repeating exactly once per record with no other same-page evidence of repetition could resolve as a scalar.
