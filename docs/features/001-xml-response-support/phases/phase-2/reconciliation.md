══════════════════════════════════════════════════════════════
Phase 2 Reconciliation · XML Parsing Core & Format Routing
Baseline: 069b461e53a61b73e227c8c43ce78f9347a2d21e on branch 001-xml-response-support
Verdict: 🟢 GREEN
══════════════════════════════════════════════════════════════

Note on delta state: the phase's changes are no longer an uncommitted working-tree
delta — `git status` shows a clean tree, and `git log 069b461..HEAD --oneline` shows
exactly one commit, `5d241ed "feat: implement XML response support in PaginationEngine"`,
covering the entire phase in one commit rather than `implementation.md`'s suggested
6-commit plan. This is a human commit-granularity choice, not an Implementor deviation —
verification below proceeded against `git diff 069b461e53a61b73e227c8c43ce78f9347a2d21e
5d241ed` (equivalent to the working-tree delta the pipeline normally reviews pre-commit).

1. PHASE REALITY REPORT

   Artifact Status:

     backend/requirements.txt (P2.A-01)
       Status:  FOUND
       Details: `xmltodict>=1.0.4` added, matching the file's existing lower-bound-pin
                convention. Confirmed installed at exactly 1.0.4 (`pip show xmltodict`).

     backend/api_connector/services/xml_parser.py (P2.A-02)
       Status:  FOUND
       Details: `parse_xml_response(xml_bytes: bytes) -> dict | list`, ports
                trial_xmltodict.py's postprocessor-based namespace-stripping and
                two-pass (parent_tag, child_tag)-scoped list-coercion exactly.
                `disable_entities=True` explicit on both `xmltodict.parse()` calls.
                On failure, logs only `type(exc).__name__` — matches http_client.py's
                "never log body" contract. Docstring matches ssrf.py's shape (purpose,
                security note, documented accepted-limitation + hardened-expat-shim
                pointer, not built).

     backend/api_connector/models/enums.py — ResponseFormat (P2.C-01)
       Status:  FOUND
       Details: `class ResponseFormat(TextChoices): JSON="json"/XML="xml"`, placed
                immediately after `HTTPMethod`, exact shape match to the file's other
                enums.

     backend/api_connector/models/endpoint.py — response_format field (P2.C-01)
       Status:  FOUND
       Details: `CharField(max_length=10, choices=ResponseFormat.choices,
                default=ResponseFormat.JSON)`, placed between `endpoint_headers` and
                `data_root_path` exactly as specified.

     backend/api_connector/models/__init__.py — ResponseFormat export (P2.C-01)
       Status:  FOUND
       Details: Exported in both the import block and `__all__`, alphabetically
                ordered, matching the existing entries.

     backend/api_connector/migrations/0005_endpoint_response_format.py (P2.C-02)
       Status:  FOUND
       Details: Single `AddField`, depends on `0004_oauth_ac_state`, no `RunPython` —
                purely additive, matching the 0001-0004 chain's constraint.

     backend/api_connector/serializers/endpoint.py — response_format exposure (P2.C-03)
       Status:  FOUND
       Details: `"response_format"` present in `Meta.fields` on
                `EndpointReadSerializer`, `EndpointCreateSerializer`, and
                `EndpointUpdateSerializer` (plus its `extra_kwargs` optional-on-PATCH
                loop). No custom validator — DRF's auto `ChoiceField` handles rejection.

     backend/api_connector/views/endpoint.py — creation-time defaulting (P2.C-04)
       Status:  FOUND
       Details: `EndpointViewSet.create()` now fetches
                `connection_profile = get_object_or_404(ConnectionProfile, pk=profile_pk)`
                before saving; computes `default_format` from
                `connection_profile.last_test_detected_format` (only exact `"json"`/
                `"xml"` count, everything else — including `None` — falls back to
                `ResponseFormat.JSON`) when `"response_format"` is absent from
                `request.data`; the resolved format is included in the "Endpoint
                created" info log. Matches the breakdown's exact spec.

     backend/api_connector/services/pagination/engine.py — format branch (P2.B-01, REVIEW-GATE)
       Status:  FOUND
       Details: The JSON-only parse block at the baseline's lines 144-151 is replaced
                by a branch on `endpoint.response_format` (`ResponseFormat.XML` →
                `xml_parser.parse_xml_response(response.content)` — raw bytes, not
                `.text`, so the XML prolog's own `encoding=` is honored; else →
                `response.json()`, unchanged). `PaginationEngineError`'s message is now
                format-aware. A new `logger.warning` on parse failure logs
                `endpoint.response_format` (a constrained enum, not free text), the
                page number, and `type(exc).__name__` only. `xml_parser`/`ResponseFormat`
                imported at the top alongside the existing `pagination.utils` block. The
                `yield records, body` generator structure (ADR-010) is byte-for-byte
                unchanged — confirmed both by inspection and by the pre-existing
                JSON-path suite passing unmodified (see Tests below).

   Tests:   Ran the real suite myself, not from implementation.md's pasted output.

     `pytest --tb=short` (full suite): **466 passed** in 3.75s — matches
     implementation.md's claim exactly.

     `pytest tests/test_pagination_engine.py -v`: **27 passed** — all pre-existing
     JSON-path classes (`TestPaginationEngineOffsetLimit`, `TestDetectDataRoot`,
     `TestExtractRecordsAtPath`, `TestBuildRequestUrl`) pass unmodified; new
     `TestPaginationEngineXml` (4 tests: happy-path shape parity, malformed-XML
     format-aware error asserting `"xml" in message` and `"non-JSON" not in message`,
     `row_limit=15` stopping after 2 of a possible-3-page XML sequence, `max_pages=3`
     stopping after exactly 3 requests) — read each test body; assertions genuinely
     exercise what they claim, not tautologies.

     `pytest tests/test_pagination_engine.py tests/test_pagination_strategies.py
     tests/test_pagination_framework.py -q`: **84 passed** — zero regression on the
     existing JSON pipeline, the actual bar for this phase (breakdown §4).

     `pytest tests/test_endpoint_serializers.py tests/test_endpoint_api.py -q`:
     **39 passed** (21 + 18) — matches implementation.md's split exactly, including
     `TestEndpointCreateResponseFormatDefaulting`'s all 4 domain cases (agree,
     conflict, 3× unsupported-detected-format fallback, never-tested profile) — read
     the test bodies directly, not just the pass count.

     `pytest tests/test_xml_parser.py -v` (folded into the full run): 9/9, including
     the byte-for-byte spike-comparison test, the dc:creator 1/absent/2 proof, mixed
     content, namespace collision, all 3 security payloads, and the non-well-formed-XML
     failure-mode test. No `[EXTERNAL]`-tagged path this phase (confirmed — no
     Placeholders entries in breakdown.md), so no cross-check needed there.

     Manual verification step 1 (breakdown §4), re-run independently via
     `manage.py shell`:
     ```
     resolved records: 3
     first title: TEST_3 : Untertitel_Test / Maxwell Mustermann
     ```
     Matches implementation.md's own re-run and Phase 1's confirmed result exactly.

   Convention & Dependency Check:
     `ruff check .` → all checks passed. `ruff format --check .` → **"107 files
     already formatted"**, exit 0 — i.e. the *current* tree has zero formatting debt
     anywhere, including `engine.py` and `http_client.py`. This is inconsistent with
     implementation.md's narrative that format --check "flags 2 files ... reformatting
     the whole file was deliberately reverted" — see Unplanned Changes below; the net
     effect is benign (whitespace-only) but the claim itself doesn't hold against the
     committed state. ADR-005 grep (Fernet-import enforcement): zero hits outside
     `encryption.py`, confirmed. AC4 grep
     (`import xmltodict|import xml\.|from xml\.`): exactly one hit,
     `services/xml_parser.py:45` — confirmed independently. `makemigrations
     --check --dry-run`: "No changes detected." `migrate --check`: exit 0. Dependency:
     `xmltodict` confirmed installed at 1.0.4 (satisfies the `>=1.0.4` pin);
     `pip-audit --requirement requirements.txt` → "No known vulnerabilities found" —
     this environment has live PyPI/advisory-DB access, so this is a direct check, not
     deferred to CI. `defusedexpat` (DEC-8's named-dead package) is not present,
     confirmed by absence from requirements.txt and the diff.

   Unplanned Changes:
     Whitespace-only `ruff format` reformatting touched three files no task in
     breakdown.md named: `backend/api_connector/services/http_client.py` (one
     multi-line-wrapped `httpx.Client(...)` call, confirmed by reading the diff — zero
     logic change), and two Phase-1 spike reference files (`phases/phase-1/spike/trial.py`,
     `phases/phase-1/spike/trial_xmltodict.py`, both line-wrapping only). None of the
     three appear anywhere in implementation.md's §2 "What Changed" file list.
     Materially, this is inert — confirmed by diffing each file line-by-line, no
     behavior change, and it falls squarely under this pipeline's own "not significant"
     category (formatting/comments only). It's flagged here specifically because
     implementation.md's §7 Tests section makes an explicit, checkable claim —
     "`http_client.py` (pre-existing, untouched by this phase)" — that the actual diff
     contradicts (the file *was* touched, just cosmetically). This is exactly the class
     of self-reported-but-unverified claim this pipeline exists to catch; see Section 5.
     No drive-by logic changes, no silent library swaps, no unflagged security-sensitive
     code, and the phase's one `[REVIEW-GATE]` (P2.B) has a recorded halt-and-resolution
     in `decisions.md`'s "Implementor tactical decisions — Phase 2" entry — not silently
     powered through.

   Significant Deviations:
     None significant. Every planned artifact matches breakdown.md's spec (the "header
     -comment drift only" implementation.md notes for cited line numbers was confirmed
     immaterial by reading each file directly). The one confirmed discrepancy (the
     http_client.py formatting claim, above) does not meet the significance bar — no
     contract, path, signature, schema, or downstream-consumed behavior changed; it is
     recorded as an Unplanned Change and a self-report-reliability note, not a DEV-N.

2. MEMORY BANK UPDATES (project-detail.md)
   Updated surgically, from verified reality only:
   - §2 Tech Stack: added `xmltodict>=1.0.4` to the backend dependency list, noting the
     sole call site and the confirmed installed version/pip-audit result.
   - §4 Architecture: added `xml_parser.py` to the `services/` top-level module list
     (confirmed sole XML-parse call site via the AC4 grep); added a note under
     `services/pagination/` describing the new format branch and the
     `PaginationEngineError` message-text change.
   - §6 Data Model: added `Endpoint.response_format` to "Key non-obvious fields" (field
     shape, defaulting rule, editability) and `0005_endpoint_response_format.py` to the
     Migrations list.
   - §12 Metadata Footer: added a dated Changelog entry recording this update and its
     scope (narrow, phase-driven — not a full re-sweep; explicitly notes §1/§3/§5/§7-11
     were not re-verified).
   No other section touched — §1 Snapshot, §3 Runtime, §5 Core Flows, §7 Precedent
   Registry, §8 Constraints, §9 Footguns, §10 Glossary, §11 Open Questions are all
   outside this phase's confirmed scope and were left as-is, per Rule 3.

   Also updated `docs/_meta/active-context.md`: Phase 2 status → "Reconciled — 🟢
   GREEN"; Next Action reflects that the phase is already committed (`5d241ed`) rather
   than instructing the human to commit an already-committed delta, and points to
   Breakdown Engineer for Phase 3.

3. CARRY-FORWARD TO NEXT PHASE (Phase 3 — Schema Inference & Data Preview Integration)

   - `paginate()` now yields `(records, body)` where, for an XML-configured endpoint,
     `body` is the namespace-stripped, list-coerced dict/list — never the original XML
     text. Phase 3's P3.B (raw-response preservation) needs the **original raw XML
     text**, not `body` — this is not currently threaded through `paginate()`'s yield
     anywhere; it is only available at the engine level via the `response` object
     `_request_with_retry()` returns, which `paginate()` itself already holds locally
     but does not expose past the yield. Phase 3's breakdown must determine how
     `DataPreviewService` recovers `response.text`/`response.content` for this case —
     this was flagged as a known gap in Phase 2's own Handoff Note and remains
     unresolved by this phase (correctly — it's Phase 3's job, not Phase 2's).
   - `PaginationEngineError`'s message text changed (was always
     `"API returned non-JSON response..."`; now format-aware,
     `"...could not be parsed as {format}..."`). No current test in the backend suite
     asserts the old exact wording (confirmed by reading
     `test_non_json_response_raises_engine_error`, which only asserts
     `pytest.raises(PaginationEngineError)`), so this is a non-issue for Phase 3, but
     Phase 4's frontend/e2e work should be aware if any UI error-matching logic
     depends on the old string (none found in this backend-only phase).
   - `detect_data_root()` needs no XML-aware variant (confirmed again by this phase,
     not just assumed from Phase 1) — it operates purely on `isinstance(dict)`/
     `isinstance(list)` checks once the body is normalized. Phase 3 can rely on this
     without re-verifying.
   - Residual, already-accepted risks unchanged from DEC-5/DEC-8 (cross-namespace
     same-local-name key collision; the `(parent_tag, child_tag)` heuristic is
     document-local, not schema-aware) — not new to this phase, not re-litigated here,
     but still live for Phase 3/4 to keep in mind if a real API surfaces either.
   - `xmltodict`'s ~1.7x overhead vs. `ElementTree`, measured only at a synthetic
     5000-record stress size in Phase 1, is still not confirmed against real SRU page
     sizes — Phase 4's e2e validation remains the natural place to observe this, not a
     new task in Phase 3.

4. ESCALATION
   N/A — verdict is GREEN, nothing to escalate.

5. WHAT I COULD NOT VERIFY
   - **implementation.md's self-report reliability**: confirmed one concrete instance
     where its claim ("http_client.py ... untouched by this phase") does not match the
     actual diff (the file was cosmetically reformatted). The discrepancy itself is
     immaterial in effect, but I cannot rule out that other narrative claims in that
     document rest on similarly unverified assumptions beyond what I independently
     re-checked here (tests, greps, migration state, the manual shell verification, and
     every cited artifact). Treat implementation.md's prose as a guide to *where* to
     look, not as proof on its own — consistent with this pipeline's Rule 1.
   - **Same-model blind spot**: if this Reconciler pass and the Implementor session
     that built Phase 2 ran on the same underlying model, both may share blind spots
     around the same categories of subtle bug (e.g. an off-by-one in the list-coercion
     max-count logic, or a namespace-stripping edge case neither would think to test).
     The byte-for-byte comparison against Phase 1's independently-produced spike output
     (`test_sample_matches_spike_confirmed_output`) is the strongest available mitigation
     here, but it is not a substitute for a differently-modeled or human review of
     `xml_parser.py`'s two-pass algorithm specifically, per the breakdown's own risk
     note.
   - **Runtime/production behavior against a real external API**: everything here was
     verified against Phase 1's fixture-based samples and `httpx_mock`. No live network
     call to a real SRU/MARCXML API was made this phase (by design — that's Phase 4's
     job) — real-world response quirks (encoding edge cases, unusual attribute usage)
     remain unvalidated until then.
   - **Security design intent** (as opposed to implementation-level bugs): the
     Security Self-Check in implementation.md was spot-checked against the actual code
     (log calls, `disable_entities=True` placement, `get_object_or_404` scoping) and
     held up under that check, but a full security-design review (whether XXE-safety-
     by-parser-default is the right posture at all, vs. e.g. also disabling DTDs
     outright) is outside what file-reading and test-running can confirm — deferred to
     a human security review or the project's existing security-audit cadence, same as
     Phase 1's Reconciler noted.
   - Everything else in this report reflects direct verification (file reads, live test
     runs, live greps, a live migration check, a live `pip-audit` run) in this
     environment.
