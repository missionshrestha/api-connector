# backend/tests/test_xml_parser.py
"""
xml_parser.parse_xml_response() unit tests.

Reuses Phase 1's real spike fixtures directly (phases/phase-1/spike/) rather
than hand-authoring new XML, per the breakdown's Testing Notes.
"""

import json
import xml.parsers.expat
from pathlib import Path

import pytest

from api_connector.services.pagination.utils import extract_records_at_path
from api_connector.services.xml_parser import parse_xml_response

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = REPO_ROOT / "docs/features/001-xml-response-support/phases/phase-1/spike"
SAMPLES_DIR = SPIKE_DIR / "samples"

DATA_ROOT_PATH = "searchRetrieveResponse.records.record"


class TestParseXmlResponseHappyPath:
    def test_sample_matches_spike_confirmed_output(self):
        """Byte-for-byte (sort_keys JSON comparison) equivalent to Phase 1's
        own confirmed xmltodict output for the same sample."""
        xml_bytes = (SPIKE_DIR / "sample.xml").read_bytes()
        result = parse_xml_response(xml_bytes)

        expected = json.loads((SPIKE_DIR / "raw_output_xmltodict.txt").read_text())
        assert json.dumps(result, sort_keys=True) == json.dumps(
            expected, sort_keys=True
        )

    def test_sample_resolves_three_records(self):
        xml_bytes = (SPIKE_DIR / "sample.xml").read_bytes()
        result = parse_xml_response(xml_bytes)

        records = extract_records_at_path(result, DATA_ROOT_PATH)
        assert len(records) == 3

    def test_dc_creator_single_absent_multi_coerces_to_lists(self):
        """spike-findings.md §3's central proof: 1/absent/2 occurrences of
        dc:creator all resolve to a list at the same dot-path, never a bare
        scalar for the single-occurrence case."""
        xml_bytes = (SPIKE_DIR / "sample.xml").read_bytes()
        result = parse_xml_response(xml_bytes)
        records = extract_records_at_path(result, DATA_ROOT_PATH)

        creator_0 = records[0]["recordData"]["dc"]["creator"]
        assert creator_0 == ["Mustermann, Maxwell [Verfasser]"]

        assert "creator" not in records[1]["recordData"]["dc"]

        creator_2 = records[2]["recordData"]["dc"]["creator"]
        assert creator_2 == [
            "Kaur, Lakhveer [Herausgeber]",
            "Kumar, Pushpendra [Herausgeber]",
        ]


class TestParseXmlResponseEdgeCases:
    def test_mixed_content_needs_no_custom_concatenation(self):
        """xmltodict natively concatenates elem.text + every child.tail —
        unlike the ElementTree path Phase 1 also trialed and had to fix."""
        xml_bytes = (SAMPLES_DIR / "sample_mixed_content.xml").read_bytes()
        result = parse_xml_response(xml_bytes)
        assert result is not None  # parses without error; native handling, no crash

    def test_namespace_collision_merges_as_documented_dec5_behavior(self):
        """Two differently-namespaced same-local-name elements silently
        merge into one list — accepted DEC-5 behavior, not a bug."""
        xml_bytes = (SAMPLES_DIR / "sample_ns_collision.xml").read_bytes()
        result = parse_xml_response(xml_bytes)

        # Walk to find the merged "title" key produced by the collision.
        def find_title(node):
            if isinstance(node, dict):
                if "title" in node:
                    return node["title"]
                for v in node.values():
                    found = find_title(v)
                    if found is not None:
                        return found
            return None

        title = find_title(result)
        assert isinstance(title, list)
        assert len(title) == 2


class TestParseXmlResponseSecurity:
    """The 3 payloads from spike-findings.md §8.2, run as in-memory strings
    only, never persisted."""

    def test_classic_xxe_rejected(self):
        payload = """<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""
        with pytest.raises(ValueError):
            parse_xml_response(payload)

    def test_billion_laughs_rejected(self):
        payload = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>&lol3;</root>"""
        with pytest.raises(ValueError):
            parse_xml_response(payload)

    def test_bare_doctype_no_entity_allowed(self):
        """Shared, accepted MVP-scope gap (DEC-8) — not the hardened-expat
        shim's job to close in this task."""
        payload = """<?xml version="1.0"?>
<!DOCTYPE root SYSTEM "http://example.com/should-not-be-fetched.dtd">
<root>hello</root>"""
        result = parse_xml_response(payload)
        assert result == {"root": "hello"}


class TestParseXmlResponseFailureMode:
    def test_non_well_formed_xml_raises(self):
        """Confirms the exact exception type P2.B-01's catch site needs to
        handle — xmltodict's own ExpatError, not a custom exception."""
        with pytest.raises(xml.parsers.expat.ExpatError):
            parse_xml_response(b"<root><unclosed></root>")
