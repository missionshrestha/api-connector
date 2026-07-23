# backend/api_connector/services/xml_parser.py
"""
XML response normalization.

Converts an XML API response into the same dict/list shape response.json()
produces for a JSON endpoint, so PaginationEngine's single parse chokepoint
(DEC-1) can hand XML bodies to every existing downstream consumer
(extract_records_at_path, pagination strategies, SchemaInferenceEngine,
DataPreviewService) unmodified. Ports the convention confirmed by Phase 1's
spike (spike-findings.md) and promoted in decisions.md DEC-8:
  - Namespace stripping: every element/attribute tag is reduced from its
    namespaced form to its local name via a colon-prefix regex (DEC-5);
    bare `xmlns`/`xmlns:*` declarations are dropped entirely, not surfaced
    as attributes.
  - List coercion: a two-pass algorithm scoped by (parent_tag, child_tag)
    pair — a naive flat-count or unconditional-list rule is proven broken
    (spike-findings.md §3) and must not be used.
  - Attribute/text convention: `@attr`/`#text` keys, with a pure-text-leaf
    collapse — native to xmltodict, no extra code required.

Security (OWASP A(XXE) / CWE-611):
  disable_entities=True is passed explicitly on every xmltodict.parse() call,
  even though it is xmltodict 1.0.4's own default — this makes the
  XXE-safety guarantee visible in this codebase's code rather than an
  implicit library default that could silently change on a future upgrade.
  On a rejected/malformed payload, only the exception's type name is
  logged — never the raw XML body or the exception's message text, either
  of which may echo attacker-supplied content (matches http_client.py's
  "never log body" contract).

Accepted limitation (matches DEC-8's carried-forward residual risk): a bare
DOCTYPE with no entity declaration is allowed through at these defaults —
a gap shared with every candidate trialed in Phase 1, not unique to this
implementation. A ~20-line hardened-expat shim closing this gap
(`_HardenedExpatModule`, reusing defusedxml.common's exception classes) is
documented and available at
`docs/features/001-xml-response-support/phases/phase-1/spike/trial_xmltodict.py`
as a future-hardening option; DEC-8 accepts the gap as non-differentiating
MVP scope, so it is not built here.
"""

import logging
import re

import xmltodict

logger = logging.getLogger("api_connector.xml_parser")

_PREFIX_RE = re.compile(r"^[^:]+:")


def _strip_prefix(name: str) -> str:
    return _PREFIX_RE.sub("", name)


def _postprocessor(path, key, value):
    """Strip namespace prefixes (DEC-5) and drop xmlns declarations
    entirely — xmltodict (unlike ElementTree) surfaces xmlns:* as regular
    '@'-prefixed attributes when process_namespaces=False, which would
    otherwise pollute the 'meaningful attributes only' convention."""
    if key == "@xmlns" or key.startswith("@xmlns:"):
        return None  # drop: not a meaningful attribute, just a declaration
    if key.startswith("@"):
        return "@" + _strip_prefix(key[1:]), value
    return _strip_prefix(key), value


def _collect_max_counts(xml_bytes: bytes) -> dict:
    """Pass 1: parse with force_list=True (every child wrapped, uniformly)
    and walk the resulting structure to find, for every (parent_tag,
    child_tag) pair (already prefix-stripped via postprocessor), the max
    occurrence count under any single parent instance anywhere in the doc."""
    forced = xmltodict.parse(
        xml_bytes,
        dict_constructor=dict,
        force_list=True,
        postprocessor=_postprocessor,
        disable_entities=True,
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
        # A document has exactly one root, never coerced to a list —
        # unwrap force_list's 1-item wrapping of the root itself.
        root_node = root_val[0] if isinstance(root_val, list) else root_val
        walk(root_node, root_key)
    return max_counts


def _make_force_list_fn(max_counts: dict):
    def force_list_fn(path, key, value):
        stripped_key = _strip_prefix(key)
        parent_tag = _strip_prefix(path[-1][0]) if path else None
        return max_counts.get((parent_tag, stripped_key), 0) > 1

    return force_list_fn


def parse_xml_response(xml_bytes: bytes) -> dict | list:
    """
    Parse an XML API response into the normalized dict/list shape every
    downstream consumer of PaginationEngine's chokepoint expects.

    Runs xmltodict.parse() twice — Pass 1 collects per-(parent_tag,
    child_tag) max occurrence counts, Pass 2 uses those counts to decide
    which children become lists (see module docstring). This is an
    intentional, already-measured cost (spike-findings.md §8.4), not a bug
    to optimize away.

    Raises whatever xmltodict.parse() raises on non-well-formed or
    rejected XML (e.g. ValueError, xml.parsers.expat.ExpatError) — callers
    catch broadly, matching the existing JSON parse chokepoint's contract.
    """
    try:
        max_counts = _collect_max_counts(xml_bytes)
        force_list_fn = _make_force_list_fn(max_counts)
        return xmltodict.parse(
            xml_bytes,
            dict_constructor=dict,
            postprocessor=_postprocessor,
            force_list=force_list_fn,
            disable_entities=True,
        )
    except Exception as exc:
        logger.warning("XML parse rejected: %s", type(exc).__name__)
        raise
