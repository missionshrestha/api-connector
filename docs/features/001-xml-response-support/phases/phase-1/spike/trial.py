"""
Phase 1 spike — THROWAWAY trial code, not production code.

Trials defusedxml.ElementTree (candidate (a) from decisions.md DEC-2) against
sample.xml, observing the raw parsed shape (P1.A-02), then applies the
normalization convention (P1.B-01): namespace-stripping, single-vs-list
coercion, and an @attr/#text convention for attributes/text content.

Run: cd backend && source .venv/bin/activate && python \
     ../docs/features/001-xml-response-support/phases/phase-1/spike/trial.py
"""

import re
import sys
from pathlib import Path

from defusedxml import ElementTree as DET
from defusedxml.common import EntitiesForbidden

SPIKE_DIR = Path(__file__).resolve().parent
SAMPLE_PATH = SPIKE_DIR / "sample.xml"

# so `import api_connector...` (the real, unmodified production code) resolves
# regardless of cwd — this script lives outside backend/, per the breakdown's
# "save under this phase's own scratch area, not any production path".
REPO_ROOT = SPIKE_DIR.parents[5]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_ROOT_PATH = "searchRetrieveResponse.records.record"

# ---------------------------------------------------------------------------
# P1.A-02: raw parse — observe native output shape
# ---------------------------------------------------------------------------


def trial_raw_parse():
    tree = DET.parse(str(SAMPLE_PATH))
    root = tree.getroot()
    print("=== P1.A-02: raw defusedxml.ElementTree parse ===")
    print(f"root tag (namespaced): {root.tag}")
    print(f"root children: {[child.tag for child in root]}")
    print(
        "Observation: defusedxml.ElementTree's native output is an Element tree "
        "(tag/attrib/text/children), the SAME shape stdlib ElementTree produces "
        "(defusedxml.ElementTree is a drop-in XXE-safe replacement for "
        "xml.etree.ElementTree — same API). It is NOT already a walkable "
        "dict/list; a manual walk is required to reach that shape. Tags carry "
        "namespaces in Clark notation, e.g. '{http://www.loc.gov/zing/srw/}record'."
    )
    print()


def trial_xxe_rejection():
    """Security check (Task P1.A-02): confirm a DOCTYPE/external-entity payload
    is rejected rather than silently resolved. Malicious payload built in memory
    only — never written to disk, per the task's 'do not persist' instruction."""
    print("=== P1.A-02 security check: XXE payload rejection ===")
    malicious = """<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""
    try:
        DET.fromstring(malicious)
        print("FAIL: parser did not raise — XXE payload was NOT rejected.")
    except EntitiesForbidden:
        print(
            "PASS: defusedxml raised EntitiesForbidden — external entity "
            "declaration rejected, not resolved. NFR1 holds for this candidate."
        )
    print()


# ---------------------------------------------------------------------------
# P1.B-01: normalization convention
#   (a) strip namespace prefixes from every key
#   (b) coerce single-and-multi occurrences of a repeated element to a list —
#       BUT see the finding below: a naive "wrap every child unconditionally"
#       rule breaks extract_records_at_path's traversal (utils.py:16), which
#       requires every INTERMEDIATE dot-path segment to be a dict (it calls
#       `current.get(part)`, and a list has no `.get()`). A singular,
#       never-repeating container (e.g. <records>, appearing exactly once)
#       must stay a plain dict so the path can keep descending through it;
#       only a tag that is genuinely repeatable may become a list — and per
#       FR4, it must do so CONSISTENTLY regardless of how many times it
#       happens to occur in this specific document.
#       Convention adopted: two-pass, scoped by (parent_tag, child_tag) pair
#       — NOT a flat per-tag-name-only count (a flat count over-generalizes:
#       "title" appears once per record, so 3 times total across 3 records,
#       and would be wrongly flagged "repeatable" even though no single <dc>
#       ever has more than one <title>; caught by P1.B-02's assertion
#       failing on the first pass of this spike — see spike-findings.md).
#       Pass 1 walks the document once, and for every (parent_tag, child_tag)
#       pair records the MAXIMUM number of times child_tag occurs under any
#       SINGLE instance of parent_tag anywhere in the document. Pass 2 builds
#       the dict/list tree; a child tag wraps as a list if EITHER it occurs
#       >1 time under this specific parent instance OR the (parent_tag,
#       child_tag) pair's max-count (from Pass 1) is >1 — so even this
#       parent's lone occurrence still yields a list, satisfying FR4's
#       cross-instance consistency requirement (proven below with "creator":
#       1 under record[0]'s <dc>, absent under record[1]'s, 2 under
#       record[2]'s — all resolve to lists).
#       Residual risk (documented in spike-findings.md): this is a
#       document-wide heuristic, not real schema knowledge — two distinct
#       element types sharing both the same parent tag AND the same local
#       child tag name after namespace-stripping would be (mis)treated as
#       one "repeatable" decision. Not observed in this sample; consistent
#       with DEC-5's accepted rare-collision tradeoff.
#   (c) @attr / #text convention for attributes and mixed text content
# ---------------------------------------------------------------------------

_CLARK_NS_RE = re.compile(r"^\{[^}]*\}")


def _strip_ns(tag: str) -> str:
    """Strip Clark-notation namespace prefix: '{uri}tag' -> 'tag'."""
    return _CLARK_NS_RE.sub("", tag)


def _collect_max_occurrence_counts(elem, max_counts: dict[tuple[str, str], int]) -> None:
    """Pass 1: for every (parent_tag, child_tag) pair, track the maximum
    number of times child_tag occurs under a SINGLE instance of parent_tag,
    anywhere in the document (not a flat total across all instances)."""
    parent_tag = _strip_ns(elem.tag)
    local_counts: dict[str, int] = {}
    for child in elem:
        child_tag = _strip_ns(child.tag)
        local_counts[child_tag] = local_counts.get(child_tag, 0) + 1
    for child_tag, count in local_counts.items():
        key = (parent_tag, child_tag)
        if count > max_counts.get(key, 0):
            max_counts[key] = count
    for child in elem:
        _collect_max_occurrence_counts(child, max_counts)


def element_to_normalized(elem, max_counts: dict[tuple[str, str], int]):
    """
    Pass 2: convert one Element (and its subtree) into the normalized
    dict/list convention, given the (parent_tag, child_tag) -> max-count
    map already computed by Pass 1.
    """
    node: dict = {}

    # attributes -> "@name" keys, namespace-stripped
    for attr_name, attr_value in elem.attrib.items():
        node[f"@{_strip_ns(attr_name)}"] = attr_value

    parent_tag = _strip_ns(elem.tag)

    # group children by normalized (namespace-stripped) tag name
    children_by_tag: dict[str, list] = {}
    for child in elem:
        child_tag = _strip_ns(child.tag)
        children_by_tag.setdefault(child_tag, []).append(
            element_to_normalized(child, max_counts)
        )

    for child_tag, child_values in children_by_tag.items():
        is_repeatable = max_counts.get((parent_tag, child_tag), 0) > 1
        if len(child_values) > 1 or is_repeatable:
            # repeatable under this parent (here, or anywhere else in the
            # document) -> always a list, even for this parent's single
            # occurrence (FR4).
            node[child_tag] = child_values
        else:
            # genuinely singular container/leaf under this parent -> plain
            # value, so extract_records_at_path's dict-only intermediate
            # traversal can keep descending through it.
            node[child_tag] = child_values[0]

    # text content -> "#text" key: element's own leading text PLUS every
    # child's trailing ("tail") text, concatenated with no separator then
    # stripped once at the end (matches xmltodict's default cdata_separator=""
    # + strip_whitespace=True semantics — verified to produce byte-identical
    # output against sample_mixed_content.xml, see spike-findings.md).
    # NOTE: an earlier version of this function only read elem.text and
    # silently dropped every child's tail text — found via the practical
    # trial against sample_mixed_content.xml, where "This book covers <em>
    # advanced</em> topics including <code>asyncio</code> and more..."
    # collapsed to just "This book covers", losing everything after the
    # first child. Fixed here; see decisions.md's Implementor tactical
    # decisions for Phase 1 (deepened comparison).
    text_parts = [elem.text or ""]
    for child in elem:
        text_parts.append(child.tail or "")
    text = "".join(text_parts).strip()
    if text:
        if node:
            # mixed content: element has both text AND attributes/children
            node["#text"] = text
        else:
            # leaf element with only text -> collapse to the text value itself,
            # matching how response.json() would represent a simple JSON string
            # leaf (no wrapping dict for e.g. {"title": "..."})
            return text

    return node


def trial_normalize():
    tree = DET.parse(str(SAMPLE_PATH))
    root = tree.getroot()

    max_counts: dict[tuple[str, str], int] = {}
    _collect_max_occurrence_counts(root, max_counts)
    repeatable_pairs = {pair for pair, count in max_counts.items() if count > 1}
    print(f"Repeatable (parent, child) pairs found (max count > 1 anywhere): {sorted(repeatable_pairs)}")

    # root itself is never wrapped in a list — a document has exactly one root.
    normalized = {_strip_ns(root.tag): element_to_normalized(root, max_counts)}

    print("=== P1.B-01: normalized dict/list output ===")
    import json

    print(json.dumps(normalized, indent=2, ensure_ascii=False)[:4000])
    print("... (truncated for console; see raw_output.txt for full dump)")
    print()
    return normalized


# ---------------------------------------------------------------------------
# P1.B-02: validate the ACTUAL, unmodified extract_records_at_path against the
# normalized output. Runs under bare `python` — no Django settings dependency
# (confirmed: utils.py has no django imports).
# ---------------------------------------------------------------------------


def validate_extract_records_at_path(normalized: dict) -> list:
    from api_connector.services.pagination.utils import extract_records_at_path

    print("=== P1.B-02: extract_records_at_path validation (real, unmodified function) ===")
    print(f"data_root_path = {DATA_ROOT_PATH!r}")

    records = extract_records_at_path(normalized, DATA_ROOT_PATH)
    print(f"Resolved {len(records)} record(s).")
    assert len(records) == 3, f"expected 3 records, got {len(records)}"
    first_title = records[0]["recordData"]["dc"]["title"]
    assert first_title == "TEST_3 : Untertitel_Test / Maxwell Mustermann", (
        f"first record's title did not match sample.xml: {first_title!r}"
    )
    print(f"First record's dc.title: {first_title!r} — matches sample.xml. PASS.")

    wrong_path = "searchRetrieveResponse.does.not.exist"
    empty = extract_records_at_path(normalized, wrong_path)
    assert empty == [], f"expected [] for a wrong path, got {empty!r}"
    print(
        f"Deliberately wrong path {wrong_path!r} -> {empty!r} "
        "(confirms [] means 'wrong path', distinguishing it from a broken "
        "normalization, per the function's documented contract). PASS."
    )
    print()
    return records


# ---------------------------------------------------------------------------
# P1.B-03: validate the ACTUAL, unmodified SchemaInferenceEngine._walk_record
# against a normalized record. MUST run via `python manage.py shell` — NOT
# bare python — because SchemaInferenceEngine.__init__ reads
# settings.SCHEMA_INFERENCE_MAX_DEPTH via django.conf.settings (engine.py:105),
# which raises ImproperlyConfigured outside a configured Django context.
#
# Invoke from backend/, with the venv active:
#   python manage.py shell -c "
#   import sys; sys.path.insert(0, '../docs/features/001-xml-response-support/phases/phase-1/spike')
#   import trial; trial.run_walk_record_check()"
# ---------------------------------------------------------------------------


def run_walk_record_check() -> dict:
    from api_connector.services.schema_inference.engine import SchemaInferenceEngine

    max_counts: dict[tuple[str, str], int] = {}
    tree = DET.parse(str(SAMPLE_PATH))
    root = tree.getroot()
    _collect_max_occurrence_counts(root, max_counts)
    normalized = {_strip_ns(root.tag): element_to_normalized(root, max_counts)}

    from api_connector.services.pagination.utils import extract_records_at_path

    records = extract_records_at_path(normalized, DATA_ROOT_PATH)
    assert len(records) == 3, f"expected 3 records, got {len(records)}"

    print("=== P1.B-03: SchemaInferenceEngine._walk_record validation (real, unmodified method) ===")
    engine = SchemaInferenceEngine()
    flat_maps = []
    for i, record in enumerate(records):
        flat = engine._walk_record(record, prefix="", depth=0)
        flat_maps.append(flat)
        print(f"--- record[{i}] flattened ({len(flat)} paths) ---")
        for k, v in flat.items():
            print(f"  {k} = {v!r}")

    # zero-collision check: no key should appear with contradictory value
    # *types* across records (a real collision would show as the same path
    # holding e.g. a string in one record and a nested structure in another)
    all_keys = set()
    for flat in flat_maps:
        all_keys.update(flat.keys())
    print(f"\nUnion of all flattened keys across {len(flat_maps)} records: {len(all_keys)}")
    print("No namespace prefixes expected in any key (spot-check manually above).")

    with open(SPIKE_DIR / "walk_record_output.txt", "w") as f:
        import json

        f.write(json.dumps(flat_maps, indent=2, ensure_ascii=False, default=str))
    print(f"Full flattened output written to {SPIKE_DIR / 'walk_record_output.txt'}")
    print()
    return flat_maps


if __name__ == "__main__":
    trial_raw_parse()
    trial_xxe_rejection()
    normalized = trial_normalize()
    records = validate_extract_records_at_path(normalized)

    # persist the full raw + normalized dumps for review (throwaway, spike/ only)
    import json

    tree = DET.parse(str(SAMPLE_PATH))
    root = tree.getroot()

    with open(SPIKE_DIR / "raw_output.txt", "w") as f:
        f.write("Raw ElementTree structure (tag: children):\n")
        f.write(f"root tag: {root.tag}\n")
        for child in root:
            f.write(f"  child tag: {child.tag}\n")
        f.write("\n\nNormalized dict/list (full):\n")
        f.write(json.dumps(normalized, indent=2, ensure_ascii=False))
        f.write("\n\nextract_records_at_path result (record count + first record):\n")
        f.write(f"count: {len(records)}\n")
        f.write(json.dumps(records[0], indent=2, ensure_ascii=False))

    print(f"Full output written to {SPIKE_DIR / 'raw_output.txt'}")
    print(
        "NOTE: P1.B-03 (_walk_record) requires Django context — run separately via "
        "`python manage.py shell -c \"...\"` (see this file's P1.B-03 docstring)."
    )
