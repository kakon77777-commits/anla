# -*- coding: utf-8 -*-
"""Canonical JSON — SPEC.md section 6."""

from __future__ import annotations

import pytest

from anla.canonical import CanonicalJSONError, canonical, canonical_bytes


def test_keys_are_sorted_by_code_point():
    assert canonical({"b": 1, "a": 2, "A": 3}) == '{"A":3,"a":2,"b":1}'


def test_no_insignificant_whitespace():
    assert canonical({"a": [1, 2, {"b": "c"}]}) == '{"a":[1,2,{"b":"c"}]}'


def test_non_ascii_is_literal_utf8():
    assert canonical_bytes({"path": "會話01.txt"}) == '{"path":"會話01.txt"}'.encode("utf-8")


def test_solidus_is_not_escaped():
    assert canonical("docs/readme.txt") == '"docs/readme.txt"'


@pytest.mark.parametrize("value,expected", [
    ("\n", '"\\n"'),
    ("\t", '"\\t"'),
    ("\r", '"\\r"'),
    ("\b", '"\\b"'),
    ("\f", '"\\f"'),
    ("\x00", '"\\u0000"'),
    ("\x1f", '"\\u001f"'),
    ('"', '"\\""'),
    ("\\", '"\\\\"'),
    ("\x7f", '"\x7f"'),
])
def test_string_escaping_is_the_shortest_form(value, expected):
    assert canonical(value) == expected


def test_booleans_are_lowercase_literals():
    assert canonical({"a": True, "b": False}) == '{"a":true,"b":false}'


def test_null_is_rejected():
    with pytest.raises(CanonicalJSONError):
        canonical(None)


def test_floats_are_rejected():
    with pytest.raises(CanonicalJSONError):
        canonical({"size": 1.0})


def test_integers_beyond_2_53_are_rejected():
    with pytest.raises(CanonicalJSONError):
        canonical(2 ** 53)
    assert canonical(2 ** 53 - 1) == "9007199254740991"


def test_nanosecond_timestamps_are_carried_as_strings():
    # 2^53 nanoseconds is only about 104 days, so a real timestamp cannot be a
    # number here. This is why the manifest uses decimal strings.
    assert canonical({"created_unix_ns": "1752732000000000000"}) \
        == '{"created_unix_ns":"1752732000000000000"}'


def test_lone_surrogate_is_rejected():
    with pytest.raises(CanonicalJSONError):
        canonical("bad\ud800name")


def test_array_order_is_preserved():
    assert canonical([3, 1, 2]) == "[3,1,2]"


def test_matches_the_original_browser_release_bytes():
    """The manifest of the archive shipped in the original v0.1 release must
    re-encode to exactly the bytes it was stored as. If canonicalization drifted,
    every manifest hash ever written would stop verifying."""
    import json
    from pathlib import Path

    from anla import open_archive

    vector = Path(__file__).resolve().parents[2] / "conformance" / "vectors" \
        / "browser-interop-v0.1.anla"
    archive = open_archive(vector, full=False)
    record_offset = archive.footer.manifest_record_offset
    from anla.format import parse_record
    record = parse_record(archive.data, record_offset)
    stored = archive.data[record.payload_offset:record.payload_offset + record.payload_length]
    assert canonical_bytes(json.loads(stored.decode("utf-8"))) == stored
