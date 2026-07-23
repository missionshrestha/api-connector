"""
Phase 1 spike — THROWAWAY trial code, not production code.

Trials xmltodict (candidate (b) from decisions.md DEC-2) as a second,
directly-comparable candidate to trial.py's defusedxml.ElementTree, per the
user's request to trial BOTH options before choosing. Applies the SAME
normalization convention (namespace/prefix stripping, (parent_tag, child_tag)
-scoped list coercion, @attr/#text) via xmltodict's own native mechanisms
(force_list callable, postprocessor) rather than a hand-rolled tree walk.

Security note up front (see spike-findings.md §"Library comparison" for the
full writeup): the breakdown named `defusedexpat` as the companion package for
this candidate (decisions.md DEC-2 / breakdown.md P1.A-02's option (b)).
Research confirmed `defusedexpat` is DEAD — last released 2013, only
supports Python 3.3/3.4, incompatible with this project's Python 3.11+/3.12
stack. Two things make this less of a problem than it first appears:
(1) modern xmltodict (1.0.4, installed here) has a BUILT-IN `disable_entities`
    parameter, defaulted to `True`, which blocks entity declarations outright
    — verified empirically below (see trial_xxe_rejection_xmltodict).
(2) a small hand-written shim (_HardenedExpatModule below) replicates
    defusedxml.ElementTree's own hardening technique (setting
    StartDoctypeDeclHandler/EntityDeclHandler/ExternalEntityRefHandler
    directly on the raw expat parser, reusing defusedxml.common's own
    exception classes) for teams wanting `forbid_dtd=True` too, which neither
    candidate's default enables.

Run: cd backend && source .venv/bin/activate && python \
     ../docs/features/001-xml-response-support/phases/phase-1/spike/trial_xmltodict.py
"""

import re
import sys
import time
from pathlib import Path

import xmltodict
import xml.parsers.expat as _real_expat
from defusedxml.common import DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden

SPIKE_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = SPIKE_DIR / "samples"
SAMPLE_PATH = SPIKE_DIR / "sample.xml"

REPO_ROOT = SPIKE_DIR.parents[5]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_ROOT_PATH = "searchRetrieveResponse.records.record"

# ---------------------------------------------------------------------------
# Security: default xmltodict (disable_entities=True) vs. a hardened-expat
# shim replicating defusedxml.ElementTree's technique, since `defusedexpat`
# (the breakdown's named companion package for this candidate) is dead.
# ---------------------------------------------------------------------------


class _HardenedExpatModule:
    """pyexpat-module-compatible shim for xmltodict's `expat=` parameter.
    Applies the SAME handler-hardening defusedxml.ElementTree.DefusedXMLParser
    applies internally (see defusedxml/common.py, defusedxml/ElementTree.py),
    directly to a raw xml.parsers.expat parser, reusing defusedxml's own
    exception classes. Stricter than xmltodict's own default: also forbids
    the DTD declaration outright (forbid_dtd), not just entity declarations.
    """

    ExpatError = _real_expat.ExpatError
    error = _real_expat.error

    @staticmethod
    def ParserCreate(*args, **kwargs):
        parser = _real_expat.ParserCreate(*args, **kwargs)

        def _forbid_dtd(name, sysid, pubid, has_internal_subset):
            raise DTDForbidden(name, sysid, pubid)

        def _forbid_entity(name, is_parameter_entity, value, base, sysid, pubid, notation_name):
            raise EntitiesForbidden(name, value, base, sysid, pubid, notation_name)

        def _forbid_external(context, base, sysid, pubid):
            raise ExternalReferenceForbidden(context, base, sysid, pubid)

        parser.StartDoctypeDeclHandler = _forbid_dtd
        parser.EntityDeclHandler = _forbid_entity
        parser.ExternalEntityRefHandler = _forbid_external
        return parser


def trial_xxe_rejection_xmltodict():
    print("=== xmltodict security check: XXE / entity / DTD payload rejection ===")

    classic_xxe = """<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""

    billion_laughs = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>&lol3;</root>"""

    benign_external_dtd_only = """<?xml version="1.0"?>
<!DOCTYPE root SYSTEM "http://example.com/should-not-be-fetched.dtd">
<root>hello</root>"""

    print("--- (1) classic entity-based XXE, default settings (disable_entities=True) ---")
    try:
        result = xmltodict.parse(classic_xxe, dict_constructor=dict)
        print(f"FAIL: parsed without error -> {result!r}")
    except ValueError as e:
        print(f"PASS: rejected -> {type(e).__name__}: {e}")

    print("--- (2) billion-laughs entity bomb, default settings ---")
    try:
        result = xmltodict.parse(billion_laughs, dict_constructor=dict)
        print(f"FAIL: parsed without error -> {result!r}")
    except ValueError as e:
        print(f"PASS: rejected (entity declarations disabled before expansion could occur) -> {type(e).__name__}: {e}")

    print("--- (3) DOCTYPE with ONLY an external subset reference, no entity, default settings ---")
    print("    (tests whether a bare DOCTYPE — no malicious entity — is silently allowed)")
    try:
        result = xmltodict.parse(benign_external_dtd_only, dict_constructor=dict)
        print(f"ALLOWED at default settings -> {result!r} (no entity was declared, so disable_entities' EntityDeclHandler never fires; the external subset itself is not fetched because ExternalEntityRefHandler is unset, matching Python's non-resolution-by-default posture since 3.7.1)")
    except ValueError as e:
        print(f"Rejected -> {type(e).__name__}: {e}")

    print("\n--- same 3 payloads against the hardened-expat shim (forbid_dtd=True) ---")
    for label, payload in [
        ("classic XXE", classic_xxe),
        ("billion laughs", billion_laughs),
        ("benign external-subset-only DOCTYPE", benign_external_dtd_only),
    ]:
        try:
            xmltodict.parse(payload, dict_constructor=dict, expat=_HardenedExpatModule)
            print(f"FAIL ({label}): parsed without error under hardened shim")
        except (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden) as e:
            print(f"PASS ({label}): hardened shim rejected -> {type(e).__name__}")
    print()


# ---------------------------------------------------------------------------
# Normalization convention, built on xmltodict's own mechanisms
# ---------------------------------------------------------------------------

_PREFIX_RE = re.compile(r"^[^:]+:")


def _strip_prefix(name: str) -> str:
    return _PREFIX_RE.sub("", name)


def _postprocessor(path, key, value):
    """Strip namespace prefixes (per DEC-5) and drop xmlns declarations
    entirely — xmltodict (unlike ElementTree) surfaces xmlns:* as regular
    '@'-prefixed attributes when process_namespaces=False, which would
    otherwise pollute the 'meaningful attributes only' convention."""
    if key == "@xmlns" or key.startswith("@xmlns:"):
        return None  # drop: not a meaningful attribute, just a declaration
    if key.startswith("@"):
        return "@" + _strip_prefix(key[1:]), value
    return _strip_prefix(key), value


def _collect_max_counts_xmltodict(xml_bytes) -> dict:
    """Pass 1: parse with force_list=True (every child wrapped, uniformly)
    and walk the resulting structure to find, for every (parent_tag,
    child_tag) pair (already prefix-stripped via postprocessor), the max
    occurrence count under any single parent instance anywhere in the doc."""
    forced = xmltodict.parse(
        xml_bytes, dict_constructor=dict, force_list=True, postprocessor=_postprocessor
    )
    max_counts: dict[tuple[str, str], int] = {}

    def walk(node, parent_tag: str) -> None:
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if k.startswith("@") or k == "#text":
                continue
            items = v if isinstance(v, list) else [v]
            key_pair = (parent_tag, k)
            if len(items) > max_counts.get(key_pair, 0):
                max_counts[key_pair] = len(items)
            for item in items:
                walk(item, k)

    for root_key, root_val in forced.items():
        # root itself is force_list-wrapped too (a 1-item list); unwrap it —
        # a document has exactly one root, never coerced to a list (matches
        # trial.py's ElementTree convention).
        root_node = root_val[0] if isinstance(root_val, list) else root_val
        walk(root_node, root_key)
    return max_counts


def _make_force_list_fn(max_counts: dict):
    def force_list_fn(path, key, value):
        stripped_key = _strip_prefix(key)
        parent_tag = _strip_prefix(path[-1][0]) if path else None
        return max_counts.get((parent_tag, stripped_key), 0) > 1

    return force_list_fn


def normalize_with_xmltodict(xml_bytes) -> dict:
    max_counts = _collect_max_counts_xmltodict(xml_bytes)
    force_list_fn = _make_force_list_fn(max_counts)
    normalized = xmltodict.parse(
        xml_bytes,
        dict_constructor=dict,
        postprocessor=_postprocessor,
        force_list=force_list_fn,
    )
    return normalized, max_counts


# ---------------------------------------------------------------------------
# P1.B-02 equivalent: validate against the real extract_records_at_path
# ---------------------------------------------------------------------------


def validate_extract_records_at_path_xmltodict(normalized: dict) -> list:
    from api_connector.services.pagination.utils import extract_records_at_path

    print("=== xmltodict: extract_records_at_path validation (real, unmodified function) ===")
    records = extract_records_at_path(normalized, DATA_ROOT_PATH)
    print(f"Resolved {len(records)} record(s).")
    if records:
        first_title = records[0]["recordData"]["dc"]["title"]
        print(f"First record's dc.title: {first_title!r}")
    print()
    return records


# ---------------------------------------------------------------------------
# P1.B-03 equivalent: validate against the real _walk_record (Django context)
# ---------------------------------------------------------------------------


def run_walk_record_check_xmltodict() -> list:
    from api_connector.services.schema_inference.engine import SchemaInferenceEngine
    from api_connector.services.pagination.utils import extract_records_at_path

    with open(SAMPLE_PATH, "rb") as f:
        xml_bytes = f.read()
    normalized, _ = normalize_with_xmltodict(xml_bytes)
    records = extract_records_at_path(normalized, DATA_ROOT_PATH)
    assert len(records) == 3, f"expected 3 records, got {len(records)}"

    print("=== xmltodict: SchemaInferenceEngine._walk_record validation ===")
    engine = SchemaInferenceEngine()
    flat_maps = []
    for i, record in enumerate(records):
        flat = engine._walk_record(record, prefix="", depth=0)
        flat_maps.append(flat)
        print(f"--- record[{i}] flattened ({len(flat)} paths) ---")
        for k, v in flat.items():
            print(f"  {k} = {v!r}")
    print()

    with open(SPIKE_DIR / "walk_record_output_xmltodict.txt", "w") as f:
        import json

        f.write(json.dumps(flat_maps, indent=2, ensure_ascii=False, default=str))
    print(f"Full flattened output written to {SPIKE_DIR / 'walk_record_output_xmltodict.txt'}")
    return flat_maps


# ---------------------------------------------------------------------------
# Practical comparison: additional complex samples + performance timing
# ---------------------------------------------------------------------------


def compare_on_sample(path: Path, label: str):
    print(f"\n{'=' * 70}\nSample: {label} ({path.name})\n{'=' * 70}")
    xml_bytes = path.read_bytes()

    import trial as et_trial  # the defusedxml.ElementTree-based module

    # --- ElementTree candidate ---
    t0 = time.perf_counter()
    from defusedxml import ElementTree as DET

    tree = DET.fromstring(xml_bytes)
    max_counts_et: dict = {}
    et_trial._collect_max_occurrence_counts(tree, max_counts_et)
    normalized_et = {
        et_trial._strip_ns(tree.tag): et_trial.element_to_normalized(tree, max_counts_et)
    }
    et_elapsed = time.perf_counter() - t0

    # --- xmltodict candidate ---
    t0 = time.perf_counter()
    normalized_xd, max_counts_xd = normalize_with_xmltodict(xml_bytes)
    xd_elapsed = time.perf_counter() - t0

    print(f"defusedxml.ElementTree: {et_elapsed * 1000:.2f} ms")
    print(f"xmltodict:              {xd_elapsed * 1000:.2f} ms")

    import json

    print("\n--- ElementTree normalized (first 1500 chars) ---")
    print(json.dumps(normalized_et, indent=2, ensure_ascii=False)[:1500])
    print("\n--- xmltodict normalized (first 1500 chars) ---")
    print(json.dumps(normalized_xd, indent=2, ensure_ascii=False)[:1500])

    return normalized_et, normalized_xd


if __name__ == "__main__":
    trial_xxe_rejection_xmltodict()

    with open(SAMPLE_PATH, "rb") as f:
        xml_bytes = f.read()
    normalized, max_counts = normalize_with_xmltodict(xml_bytes)

    import json

    print("=== xmltodict normalized output (main DNB sample, first 3000 chars) ===")
    print(json.dumps(normalized, indent=2, ensure_ascii=False)[:3000])
    print("...\n")

    validate_extract_records_at_path_xmltodict(normalized)

    with open(SPIKE_DIR / "raw_output_xmltodict.txt", "w") as f:
        f.write(json.dumps(normalized, indent=2, ensure_ascii=False))
    print(f"Full xmltodict output written to {SPIKE_DIR / 'raw_output_xmltodict.txt'}")

    # practical comparison across the additional complex samples
    for sample_file, label in [
        ("sample_loc_marc.xml", "LOC MARCXML (real, 2nd source, prefixed zs: namespace)"),
        ("sample_mixed_content.xml", "Synthetic mixed content (text + child elements interleaved)"),
        ("sample_ns_collision.xml", "Synthetic namespace collision (dc:title vs mods:title)"),
    ]:
        compare_on_sample(SAMPLES_DIR / sample_file, label)

    print("\n" + "=" * 70)
    print("PERFORMANCE: sample_large.xml (5000 synthetic records, ~3.1MB)")
    print("=" * 70)
    compare_on_sample(SAMPLES_DIR / "sample_large.xml", "Large synthetic (performance)")
