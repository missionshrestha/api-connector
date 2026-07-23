HEADER
  Feature 001-xml-response-support · Phase 2 — XML Parsing Core & Format Routing
  Baseline commit: 069b461e53a61b73e227c8c43ce78f9347a2d21e on branch 001-xml-response-support
  State: UNCOMMITTED working tree (review with: git diff 069b461e53a61b73e227c8c43ce78f9347a2d21e)
  Status: READY FOR REVIEW

1. Summary
   - Replaced `PaginationEngine`'s hard-coded `response.json()` parse with a format-aware
     branch driven by a new persisted `Endpoint.response_format` field, backed by a new
     production XML→dict/list converter (`services/xml_parser.py`) that ports Phase 1's
     confirmed `xmltodict`-based convention line-for-line. An XML-configured endpoint's
     `paginate()` call now yields the identical `(records, body)` shape a JSON endpoint
     yields — zero changes to anything downstream of the chokepoint (DEC-1). All 7 tasks
     across the 3 subphases (P2.A, P2.C, P2.B) are implemented and verified; the phase's one
     `[REVIEW-GATE]` (P2.B, the shared chokepoint) was halted on per Rule 4/Step 2 and
     resumed after explicit human confirmation to proceed (see `decisions.md`'s Phase 2
     tactical-decisions entry). Full backend suite: 466 passed, zero regression on the
     existing JSON pipeline.
   - Pre-flight cleanliness check: at start, `git status` showed `docs/_meta/active-context.md`
     (modified) and `phases/phase-2/breakdown.md` (new) already staged — these are Stage 3
     (Breakdown Engineer)'s own committed-to-index output for this phase, not unrelated or
     unknown work, so building on top of them (without staging anything myself) was judged
     reasonable rather than a halt-worthy "unknown uncommitted state."

2. What Changed — file by file
   - `backend/requirements.txt`: added `xmltodict>=1.0.4` (P2.A-01).
   - `backend/api_connector/services/xml_parser.py` (new, P2.A-02): `parse_xml_response(xml_bytes:
     bytes) -> dict | list`. Ports `phases/phase-1/spike/trial_xmltodict.py` exactly:
     colon-prefix namespace stripping via a `postprocessor=` callable (drops bare
     `@xmlns`/`@xmlns:*` keys), the two-pass `(parent_tag, child_tag)`-scoped list-coercion
     algorithm, `disable_entities=True` explicit on both `xmltodict.parse()` calls. On
     parse failure, logs only `type(exc).__name__` via
     `logging.getLogger("api_connector.xml_parser")` — never the body or exception message.
     Docstring documents the module purpose/security posture matching `ssrf.py`'s shape,
     and notes the accepted bare-DOCTYPE-no-entity gap plus the hardened-expat shim's
     location as a documented future-hardening option (not built, per DEC-8).
   - `backend/tests/test_xml_parser.py` (new): 9 tests.
   - `backend/api_connector/models/enums.py`: added `ResponseFormat(TextChoices)` —
     `JSON`/`XML` — immediately after `HTTPMethod` (P2.C-01).
   - `backend/api_connector/models/endpoint.py`: imported `ResponseFormat`; added
     `response_format = CharField(max_length=10, choices=ResponseFormat.choices,
     default=ResponseFormat.JSON)` between `endpoint_headers` and `data_root_path`.
   - `backend/api_connector/models/__init__.py`: exported `ResponseFormat`, alphabetically
     ordered in both the import block and `__all__`.
   - `backend/api_connector/migrations/0005_endpoint_response_format.py` (new, P2.C-02):
     single `AddField`, depends on `0004_oauth_ac_state`, purely additive.
   - `backend/api_connector/serializers/endpoint.py` (P2.C-03): added `"response_format"`
     to `Meta.fields` in `EndpointReadSerializer`, `EndpointCreateSerializer`, and
     `EndpointUpdateSerializer` (plus its `extra_kwargs` loop). No custom validator — DRF
     auto-generates the `ChoiceField` from the model's `choices=`.
   - `backend/tests/test_endpoint_serializers.py`: +5 tests (explicit-XML valid,
     invalid-value rejected, omission valid, create+read round-trip, PATCH round-trip).
   - `backend/api_connector/views/endpoint.py` (P2.C-04): `EndpointViewSet.create()` now
     fetches `connection_profile = get_object_or_404(ConnectionProfile, pk=profile_pk)`
     before saving; if `"response_format"` is absent from `request.data`, computes
     `default_format` from `connection_profile.last_test_detected_format` (only `"json"`/
     `"xml"` values count — anything else, including `None`, falls back to
     `ResponseFormat.JSON`) and passes it to `write_serializer.save(...)`; otherwise saves
     unchanged, letting the validated user-supplied value win. The "Endpoint created" info
     log now includes the resolved `response_format`.
   - `backend/tests/test_endpoint_api.py`: +6 tests covering all 4 domain cases (agree,
     conflict, unsupported-detected-format fallback ×3 parametrized, never-tested profile).
   - `backend/api_connector/services/pagination/engine.py` (P2.B-01, the review-gated
     change): replaced the JSON-only parse block (lines 144-151 at baseline) with a branch
     on `endpoint.response_format` — `ResponseFormat.XML` calls
     `xml_parser.parse_xml_response(response.content)` (raw bytes, so the parser honors the
     XML prolog's own `encoding=` declaration); `ResponseFormat.JSON`/default calls
     `response.json()`, unchanged. The raised `PaginationEngineError`'s message is now
     format-aware (names `endpoint.response_format` instead of the hard-coded
     `"non-JSON"` string). Added a `logger.warning` on parse failure logging only
     `endpoint.response_format` (a controlled enum value, not user input), the page
     number, and `type(exc).__name__` — never the response body or exception message.
     Imported `xml_parser` and `ResponseFormat` at the top, alongside the existing
     `pagination.utils` import block. The generator/`yield records, body` structure
     (ADR-010) is untouched — confirmed by inspection and by the unmodified existing
     JSON-path suite passing unchanged.
   - `backend/tests/test_pagination_engine.py`: +4 tests in a new
     `TestPaginationEngineXml` class — happy path (same shape as JSON), malformed-XML
     format-aware error, `row_limit` early-exit, and `max_pages=3` early-stop, all against
     an XML-configured endpoint.

3. How It Works
   - **P2.A**: `parse_xml_response()` runs `xmltodict.parse()` twice. Pass 1 parses with
     `force_list=True` and walks the result to record, per `(parent_tag, child_tag)` pair,
     the maximum occurrence count under any single parent instance anywhere in the
     document. Pass 2 re-parses using a `force_list` callable that consults those counts —
     a child is coerced to a list if its pair's max count exceeds 1, so a parent's lone
     occurrence of an otherwise-repeatable tag still yields a list (the spike's central
     finding). Both passes share the same `postprocessor` that strips namespace prefixes
     and drops `xmlns` declarations.
   - **P2.C**: `POST .../endpoints/` — if the client supplies `response_format`, it's
     validated and used as-is. If omitted, the view reads the parent
     `ConnectionProfile.last_test_detected_format`; only `"json"`/`"xml"` are honored as
     defaults, everything else (a never-tested profile, or a detected `"csv"`/`"html"`/
     `"plain_text"`) falls back to the model's own `"json"` default.
   - **P2.B**: `PaginationEngine.paginate()`'s single parse step now branches on
     `endpoint.response_format` before extracting records — everything before (request
     construction, retry logic) and after (record extraction, row_limit truncation, the
     generator's yield/next-page loop) is byte-for-byte unchanged from the JSON path,
     which is exactly DEC-1's single-chokepoint design paying off.

4. Decisions Made
   - See `decisions.md`'s new "Implementor tactical decisions — Phase 2" entry: the
     `[REVIEW-GATE]` P2.B halt and its resolution (human confirmed "proceed now", the
     breakdown's specification as written). No other adapt-vs-replace calls were needed —
     P2.A was a faithful port, P2.C a routine `TextChoices` field addition following 4
     existing precedents.

5. Deviations from the Breakdown
   - None. The breakdown's cited line numbers (`enums.py:41-44`, `endpoint.py:40`/`42`,
     `views/endpoint.py:103-115`, `engine.py:144-151`, `serializers/endpoint.py`'s Meta
     ranges) all matched the actual current code within a line or two (header-comment
     drift only) — confirmed during pre-flight, no plan-vs-reality conflict.
   - `breakdown.md` was NOT edited (preserved as approved spec).

6. Contract Changes — for the Reconciler
   - `Endpoint.response_format` (new field, migration `0005_endpoint_response_format`):
     `CharField`, choices `"json"`/`"xml"`, default `"json"`. Exposed on all three Endpoint
     serializers (read, create, update/PATCH).
   - `EndpointViewSet.create()` now unconditionally fetches the parent `ConnectionProfile`
     via `get_object_or_404` (previously only used as a queryset filter in `get_queryset()`,
     never fetched as an object inside `create()` itself).
   - New module `api_connector/services/xml_parser.py`, sibling to `ssrf.py`/
     `encryption.py`. Public API: `parse_xml_response(xml_bytes: bytes) -> dict | list`.
   - `PaginationEngine.paginate()`'s `PaginationEngineError` message text changed (was
     always `"API returned non-JSON response..."`, now format-aware,
     `"...could not be parsed as {format}..."`) — any caller/test asserting the exact old
     JSON-only message string would need updating; the existing test asserting only
     `pytest.raises(PaginationEngineError)` (no message match) was unaffected.
   - Generator contract (ADR-010) unchanged — confirmed by inspection (`yield records,
     body` untouched) and by the full existing JSON-path suite passing unmodified.

7. Tests & Verification (real output)

   Full backend suite:
   ```
   $ pytest --tb=short
   ============================= test session starts ==============================
   ...
   collected 466 items
   ...
   ============================= 466 passed in 3.70s ===============================
   ```

   `xml_parser.py` unit tests (`pytest tests/test_xml_parser.py -v`): 9/9 passed —
   byte-for-byte (sort_keys JSON) match to Phase 1's own confirmed `raw_output_xmltodict.txt`
   for `sample.xml`; the designed `dc:creator` 1/absent/2 → list-of-1/absent/list-of-2 case;
   mixed content (native handling, no crash); namespace collision (documented DEC-5 merge
   behavior, asserted as 2-item list); classic XXE rejected (`ValueError`); billion-laughs
   rejected (`ValueError`); bare DOCTYPE-no-entity allowed (matches the shared, accepted
   gap); non-well-formed XML raises `xml.parsers.expat.ExpatError` (confirms the exact
   type P2.B-01's catch site needs to handle).

   `PaginationEngine` tests (`pytest tests/test_pagination_engine.py -v`): 27/27 passed —
   all pre-existing JSON-path tests (`TestPaginationEngineOffsetLimit`, `TestDetectDataRoot`,
   `TestExtractRecordsAtPath`, `TestBuildRequestUrl`) pass unmodified; new
   `TestPaginationEngineXml` (4 tests): happy path yields identical `(records, body)` shape
   to the JSON equivalent; malformed XML raises `PaginationEngineError` whose message
   contains `"xml"` and not `"non-JSON"`; `row_limit=15` stops after exactly 2 of a
   possible-3-page sequence (mirrors the JSON `row_limit` test); `SafetyConfig(max_pages=3)`
   stops after exactly 3 requests against an XML-configured endpoint (mirrors schema
   inference's `max_pages=3` cap).

   Wider JSON-path regression check
   (`pytest tests/test_pagination_engine.py tests/test_pagination_strategies.py
   tests/test_pagination_framework.py -v`): 84/84 passed.

   Endpoint serializer/API tests: `test_endpoint_serializers.py` 21/21 passed;
   `test_endpoint_api.py` 18/18 passed (includes all 4 `response_format`-defaulting domain
   cases: agree, conflict, unsupported-detected-format ×3, never-tested profile).

   Migration: `makemigrations --check --dry-run` → "No changes detected" (exit 0);
   `sqlmigrate api_connector 0005` → single `ALTER TABLE ... ADD COLUMN "response_format"
   varchar(10) DEFAULT 'json' NOT NULL` (+ drop-default); `migrate api_connector 0005` →
   applied OK against the real dev DB; `migrate --check` → exit 0 (no pending) after
   applying.

   Manual verification step 1 (breakdown §4), re-run against the production code path via
   `manage.py shell`:
   ```
   >>> normalized = xml_parser.parse_xml_response(sample.xml bytes)
   >>> records = extract_records_at_path(normalized, "searchRetrieveResponse.records.record")
   resolved records: 3
   first title: TEST_3 : Untertitel_Test / Maxwell Mustermann
   ```
   Matches Phase 1's and its Reconciler's independently-verified results. Manual steps 2/3
   (create-via-API defaulting, PATCH round-trip) are covered by the automated
   `test_endpoint_api.py`/`test_endpoint_serializers.py` round-trip tests above — not
   separately re-run by hand, since those tests exercise the identical code path.

   Lint/CI parity: `ruff check .` → all checks passed. `ruff format --check .` → flags 2
   files: `http_client.py` (pre-existing, untouched by this phase) and
   `pagination/engine.py` — confirmed pre-existing by running `ruff format --check`
   against the baseline commit's copy of `engine.py` directly (also fails) — this phase's
   ~10-line change did not introduce new formatting debt, and reformatting the whole file
   was deliberately reverted to keep the diff to just the task's change (Rule 2). ADR-005
   grep enforcement: no matches outside `encryption.py` (pass).

   `pip-audit --requirement requirements.txt` → "No known vulnerabilities found" (includes
   the new `xmltodict>=1.0.4` pin; this environment has live PyPI access, so this is a
   direct check, not deferred to CI).

   Security Self-Check: see §"Security Self-Check" below.

8. Phase Acceptance Criteria
   - **AC1** (response_format defaulting, traces SC1): MET. `test_endpoint_api.py`'s
     `TestEndpointCreateResponseFormatDefaulting` covers all stated cases (detected
     json/xml → used; csv/html/plain_text/None → falls back to json; explicit value wins
     regardless of detected format, both agreement and conflict).
   - **AC2** (XML→(records, body) parity, traces SC2): MET.
     `TestPaginationEngineXml::test_happy_path_same_shape_as_json` yields the same
     `(records, body)` shape as the JSON equivalent; namespace prefixes stripped (verified
     transitively via `xml_parser.py`'s own namespace-stripping tests, which the pagination
     path consumes unmodified).
   - **AC3** (single/multi list coercion, traces SC2/FR4): MET.
     `test_dc_creator_single_absent_multi_coerces_to_lists` proves the 1/absent/2 → all-list
     result at the identical dot-path.
   - **AC4** (xmltodict/xml.* calls confined to xml_parser.py, traces SC7): MET.
     `grep -rn "import xmltodict\|import xml\.\|from xml\." api_connector/ --include="*.py"`
     returns exactly one hit: `services/xml_parser.py:45`. Manual check, per requirement.md
     NFR1's stated floor — no CI-mechanical grep check was added this phase (matches
     requirement.md §12).
   - **AC5** (format-aware PaginationEngineError message, traces FR7): MET.
     `test_malformed_xml_raises_format_aware_error` asserts the message contains `"xml"`
     and not `"non-JSON"`.
   - **AC6** (generator contract unchanged, ADR-010): MET. Verified by inspection
     (`yield records, body` at the same call site, structurally unchanged) and by the full
     pre-existing JSON-path suite (`test_pagination_engine.py`,
     `test_pagination_strategies.py`, `test_pagination_framework.py` — 84 tests) passing
     unmodified.

9. Needs Your Eyes
   - **P2.B was the phase's designated review gate** — it's the highest-blast-radius
     change in this phase (the shared, IRREVERSIBLE-per-ADR-010 chokepoint every JSON
     endpoint already depends on), even though the task's own Decision Type is
     `[REVERSIBLE]` (it only adds a branch; it does not touch the generator/yield shape).
     Please give `engine.py`'s diff the closest read in this phase — it's the smallest
     diff by line count but the one place a mistake would regress production JSON traffic,
     not just XML.
   - **List-coercion port fidelity**: per the breakdown's own risk note, please spot-check
     `xml_parser.py`'s two-pass algorithm against `spike-findings.md` §3's `dc:creator`
     1/absent/2 proof directly (not just "looks reasonable") — the byte-for-byte test
     against Phase 1's own confirmed output (`test_sample_matches_spike_confirmed_output`)
     is the strongest evidence here, but a human read of the port is still worth it given
     this was flagged as the phase's one real algorithmic-complexity risk.
   - **`PaginationEngineError` message text changed** (§6 Contract Changes) — if any
     downstream code (frontend error-message matching, e2e test in a later phase) depends
     on the exact old `"non-JSON"` wording, it will need updating. No such dependency was
     found in this backend-only phase's own test suite, but Phase 4 (frontend/e2e) should
     be aware.
   - **Nothing `[EXTERNAL]`-tagged this phase** — no placeholder paths pending external
     resources.
   - Residual, already-accepted risks carried forward unchanged from DEC-5/DEC-8 (namespace
     collision, the document-local list-coercion heuristic) — not new to this phase, not
     re-litigated here.

10. Suggested Commit Plan

    Precedent check: `git log --oneline -20` shows this project's convention is plain,
    imperative-mood subjects without a `type(scope):` prefix (e.g. "feat: add API
    Connector feature concept document...", "feat: support POST requests in
    BaseHTTPClient...") — a loose Conventional-Commits *flavor* (uses `feat:`/`docs:`
    prefixes) but not the strict `type(scope):` form. Matching that convention below.

    1. `feat: add production XML parsing module`
       Files: `backend/requirements.txt`, `backend/api_connector/services/xml_parser.py`,
       `backend/tests/test_xml_parser.py`

       Ports Phase 1's spike-confirmed xmltodict convention (namespace stripping,
       two-pass list coercion, @attr/#text) into production code, verified byte-for-byte
       against the spike's own confirmed output. A naive flat-count or unconditional-list
       implementation was proven broken in Phase 1 (spike-findings.md §3); this ports the
       (parent_tag, child_tag)-scoped algorithm instead. disable_entities=True made
       explicit on both parse calls rather than relying on xmltodict's own default, so the
       XXE-safety guarantee is visible in this codebase's code.

       Assisted-by: Implementor:claude-sonnet-5 [pytest] [ruff] [pip-audit]

    2. `feat: add Endpoint.response_format field`
       Files: `backend/api_connector/models/enums.py`,
       `backend/api_connector/models/endpoint.py`,
       `backend/api_connector/models/__init__.py`

       Persisted TextChoices field (ADR-003 convention) to drive PaginationEngine's
       upcoming format dispatch. Chosen over re-detecting format per request (DEC-4) to
       match the existing precedent that endpoint-level config, not per-call sniffing,
       drives fetch behavior.

       Assisted-by: Implementor:claude-sonnet-5 [pytest]

    3. `chore: add migration for Endpoint.response_format`
       Files: `backend/api_connector/migrations/0005_endpoint_response_format.py`

       Purely additive AddField, matching the existing 0001-0004 chain's no-RunPython
       constraint (requirement.md §8). Separated from the model-definition commit above
       so a reviewer can see the Python change and the generated migration independently.

       Assisted-by: Implementor:claude-sonnet-5 [manage.py makemigrations]

    4. `feat: surface response_format on Endpoint serializers`
       Files: `backend/api_connector/serializers/endpoint.py`,
       `backend/tests/test_endpoint_serializers.py`

       Makes response_format user-viewable/editable through the API (FR1/FR8) — without
       this it existed in the DB but was invisible through Phase 4's future endpoint form.
       No custom validator needed; DRF's ModelSerializer already rejects out-of-choice
       values via the model's own choices=.

       Assisted-by: Implementor:claude-sonnet-5 [pytest]

    5. `feat: default response_format from connection-test detection on create`
       Files: `backend/api_connector/views/endpoint.py`,
       `backend/tests/test_endpoint_api.py`

       Closes the gap requirement.md §1 exists to fix: a profile that already detected
       "xml" during connection test would otherwise still create JSON-defaulted endpoints.
       Restricted the default to exactly "json"/"xml" detected values (not "csv"/
       "html"/"plain_text") per FR1's literal reading — those fall back to the model's own
       "json" default rather than propagating an unsupported format.

       Assisted-by: Implementor:claude-sonnet-5 [pytest]

    6. `feat: branch PaginationEngine's parse step on response_format`
       Files: `backend/api_connector/services/pagination/engine.py`,
       `backend/tests/test_pagination_engine.py`

       Wires P2.A and P2.C together at the single existing parse chokepoint (DEC-1),
       replacing the hard-coded response.json() call. Passes response.content (raw bytes),
       not response.text, so the XML parser honors the prolog's own encoding= declaration
       instead of double-decoding through httpx's Content-Type-based charset guess. This
       is the phase's REVIEW-GATE subphase — reviewed and confirmed by the human
       before implementation; the generator/yield contract (ADR-010) is deliberately
       untouched, verified by the full pre-existing JSON-path suite passing unmodified.

       Assisted-by: Implementor:claude-sonnet-5 [pytest] [ruff]

    Note: `docs/_meta/active-context.md` and `docs/features/001-xml-response-support/
    decisions.md` were also updated (phase status tracking, and the Phase 2 tactical
    decisions / review-gate resolution record) — fold these into whichever commit(s) you
    prefer, or keep as a separate `docs:` commit; they're pipeline bookkeeping, not part
    of the reviewable code delta above.

## Security Self-Check

- **Injection**: no SQL/shell/`eval`/`exec` anywhere in this phase's code. `xmltodict.parse()`
  is not code execution — it's a data parser with `disable_entities=True` explicit.
- **XSS**: N/A — backend API only, no HTML rendering in this phase's code.
- **Log Injection**: checked every new/changed log call.
  `xml_parser.py`'s `logger.warning("XML parse rejected: %s", type(exc).__name__)` — only
  the exception *type name* (a fixed set of Python identifiers), never the body or
  exception message. `engine.py`'s new `logger.warning(...)` logs
  `endpoint.response_format` (a `TextChoices` value, constrained to `"json"`/`"xml"` by
  the model/serializer, not free text), the page number (int), and `type(exc).__name__` —
  no unsanitized user input. `views/endpoint.py`'s extended "Endpoint created" log adds
  only `endpoint.response_format` (same constrained enum value).
- **Authorization / IDOR**: `EndpointViewSet.create()`'s new `get_object_or_404(
  ConnectionProfile, pk=profile_pk)` call uses the same `profile_pk` URL-scoping the
  existing `get_queryset()` already relies on as its access-control boundary — no new
  resource type or lookup pattern introduced. `response_format` itself carries no
  authorization implication (it's endpoint config, not a credential or scope).
- **Secrets**: no secrets touched, logged, or written to `implementation.md`.
- **Sensitive-data exposure**: the new format-aware `PaginationEngineError` message
  includes only `endpoint.response_format` (`"json"`/`"xml"`) and the page number — never
  response body content or the raw exception message, matching the existing JSON path's
  posture and `http_client.py`'s "never log body" contract.
- **Crypto**: not touched this phase.
- **SSRF**: not touched this phase — no new outbound-request code path; `xml_parser.py`
  operates only on bytes already fetched by the existing, unmodified `BaseHTTPClient`/
  `_request_with_retry` path.
- **Input validation**: `response_format` is validated by DRF's auto-generated
  `ChoiceField` (from the model's `choices=ResponseFormat.choices`) on both create and
  PATCH — confirmed via `test_invalid_response_format_rejected` (a `"yaml"` value returns
  400). XML body content itself is parsed defensively (`disable_entities=True`) rather
  than "validated" in the input-sanitization sense, since it's the actual API response
  payload, not user-supplied form input.
- **Dependencies**: `xmltodict>=1.0.4` — confirmed installed at exactly `1.0.4` (satisfies
  the pin), confirmed importable, and `pip-audit --requirement requirements.txt` reports
  "No known vulnerabilities found" against the full pinned set including this new
  dependency. This environment has live PyPI/vulnerability-DB access, so this is a direct
  check, not the deferred-to-CI fallback. `defusedexpat` (the breakdown's originally-named,
  now-confirmed-dead companion package) was deliberately NOT added, per DEC-8.

Flagged for deeper human/CI review: the P2.B `engine.py` change specifically (§9), given
its blast radius on the existing JSON pipeline even though it's a small, well-specified
diff; and the list-coercion port fidelity in `xml_parser.py` (§9), given it's the phase's
one real algorithmic-complexity risk per the breakdown's own framing. Everything else in
this Security Self-Check reflects what was directly verified in this environment, not
self-reported without evidence.
