# -*- coding: utf-8 -*-
"""Canonical CBOR — whitepaper open question 2, as code.

The examples come from RFC 8949 appendix A, which is the only way to be confident
an encoder written from prose is actually producing CBOR and not something that
merely round-trips through itself. The rejection tests matter just as much: the
manifest hash is computed over manifest bytes, so a decoder that accepts two
encodings of the same logical value is a decoder through which two archives with
different hashes mean the same thing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla1.cbor import CborError, NotCanonical, decode, encode  # noqa: E402


# --------------------------------------------------------------------------
# RFC 8949 appendix A
# --------------------------------------------------------------------------

RFC_VECTORS = [
    (0, "00"),
    (1, "01"),
    (10, "0a"),
    (23, "17"),
    (24, "1818"),
    (25, "1819"),
    (100, "1864"),
    (1000, "1903e8"),
    (1000000, "1a000f4240"),
    (1000000000000, "1b000000e8d4a51000"),
    (18446744073709551615, "1bffffffffffffffff"),
    (-1, "20"),
    (-10, "29"),
    (-100, "3863"),
    (-1000, "3903e7"),
    (False, "f4"),
    (True, "f5"),
    (b"", "40"),
    (b"\x01\x02\x03\x04", "4401020304"),
    ("", "60"),
    ("a", "6161"),
    ("IETF", "6449455446"),
    ('"\\', "62225c"),
    ("ü", "62c3bc"),
    ("水", "63e6b0b4"),
    ("𐅑", "64f0908591"),
    ([], "80"),
    ([1, 2, 3], "83010203"),
    ([1, [2, 3], [4, 5]], "8301820203820405"),
    (list(range(1, 26)), "98190102030405060708090a0b0c0d0e0f101112131415161718181819"),
    ({}, "a0"),
    ({1: 2, 3: 4}, "a201020304"),
    ({"a": 1, "b": [2, 3]}, "a26161016162820203"),
    (["a", {"b": "c"}], "826161a26162636161"[:6] + "a161626163"),
    ({"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"},
     "a56161614161626142616361436164614461656145"),
]


@pytest.mark.parametrize("value,expected", RFC_VECTORS,
                         ids=[repr(v)[:24] for v, _ in RFC_VECTORS])
def test_rfc_8949_appendix_a_encoding(value, expected):
    assert encode(value).hex() == expected


@pytest.mark.parametrize("value,encoded", RFC_VECTORS,
                         ids=[repr(v)[:24] for v, _ in RFC_VECTORS])
def test_rfc_8949_appendix_a_decoding(value, encoded):
    assert decode(bytes.fromhex(encoded)) == value


# --------------------------------------------------------------------------
# canonical form
# --------------------------------------------------------------------------

def test_integers_use_the_shortest_form():
    assert encode(23) == b"\x17"          # in the initial byte
    assert encode(24) == b"\x18\x18"      # one following byte
    assert encode(255) == b"\x18\xff"
    assert encode(256) == b"\x19\x01\x00"


@pytest.mark.parametrize("encoded,why", [
    ("1817", "23 in one following byte, where the initial byte would do"),
    ("190017", "23 in two bytes"),
    ("1a00000017", "23 in four bytes"),
    ("1b0000000000000017", "23 in eight bytes"),
    ("1900ff", "255 in two bytes"),
    ("3817", "a negative integer in a longer form than needed"),
])
def test_non_shortest_integers_are_refused(encoded, why):
    with pytest.raises(NotCanonical):
        decode(bytes.fromhex(encoded))
    # Not strict: the same bytes decode, because the *value* is unambiguous. The
    # strictness is a policy about encodings, not a limitation of the parser.
    assert decode(bytes.fromhex(encoded), strict=False) is not None


def test_map_keys_are_sorted_by_encoded_bytes_not_by_value():
    # 9 encodes as 0x09 and 10 as 0x0a, so numeric and bytewise order agree here…
    assert encode({10: 0, 9: 0}).hex() == "a2090a0a00"[:2] + "0900" + "0a00"
    # …but 23 encodes as 0x17 and 24 as 0x1818, so a longer encoding sorts later
    # even though 24 > 23 numerically in the same direction. The case that matters
    # is text: "z" (0x617a) sorts after "aa" (0x626161) by value but before it by
    # encoded bytes, because the length is part of the encoding.
    encoded = encode({"z": 1, "aa": 2})
    assert encoded.hex() == "a2617a0162616102"
    assert list(decode(encoded)) == ["z", "aa"]


def test_map_keys_out_of_order_are_refused():
    out_of_order = bytes.fromhex("a2" + "62616102" + "617a01")  # "aa" then "z"
    with pytest.raises(NotCanonical, match="canonical order"):
        decode(out_of_order)
    assert decode(out_of_order, strict=False) == {"aa": 2, "z": 1}


def test_duplicate_map_keys_are_refused_in_both_modes():
    duplicated = bytes.fromhex("a2" + "616101" + "616102")
    with pytest.raises(CborError, match="duplicate map key"):
        decode(duplicated)
    with pytest.raises(CborError, match="duplicate map key"):
        decode(duplicated, strict=False)
    # Note the asymmetry: the *encoder* cannot be handed a duplicate from a Python
    # dict, because two keys that encode identically are the same dict key. Its
    # duplicate check guards a future non-dict caller, is not reachable from here,
    # and is deliberately not asserted as though it were.


def test_indefinite_lengths_are_refused():
    for encoded in ("5f42010243030405ff", "7f61616161ff", "9f018202039f0203ffff",
                    "bf61610161629f0203ffff"):
        with pytest.raises(CborError, match="indefinite"):
            decode(bytes.fromhex(encoded))


def test_trailing_bytes_are_refused():
    with pytest.raises(CborError, match="trailing"):
        decode(b"\x01\x02")


# --------------------------------------------------------------------------
# what the profile excludes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [1.5, 0.0, float("inf"), float("nan")])
def test_floats_are_refused_by_the_encoder(value):
    with pytest.raises(CborError, match="floating point"):
        encode(value)


@pytest.mark.parametrize("encoded", ["f90001", "fa47c35000", "fb7e37e43c8800759c"])
def test_floats_are_refused_by_the_decoder(encoded):
    with pytest.raises(CborError, match="floating point"):
        decode(bytes.fromhex(encoded))


def test_null_and_undefined_are_refused():
    with pytest.raises(CborError, match="null"):
        encode(None)
    with pytest.raises(CborError, match="null"):
        decode(bytes.fromhex("f6"))
    with pytest.raises(CborError, match="undefined"):
        decode(bytes.fromhex("f7"))


def test_tags_are_refused():
    with pytest.raises(CborError, match="tags"):
        decode(bytes.fromhex("c074323031332d30332d32315432303a30343a30305a"))


def test_invalid_utf8_in_a_text_string_is_refused():
    with pytest.raises(CborError, match="UTF-8"):
        decode(bytes.fromhex("62c328"))


def test_truncated_input_is_refused():
    with pytest.raises(CborError, match="truncated"):
        decode(bytes.fromhex("1819"[:2]))
    with pytest.raises(CborError, match="truncated"):
        decode(bytes.fromhex("4401"))


# --------------------------------------------------------------------------
# round trips
# --------------------------------------------------------------------------

MANIFEST_SHAPED = {
    "anla_version": [1, 0],
    "archive_id": bytes(range(16)),
    "snapshot_id": bytes(range(32)),
    "created_unix_ns": 1785063660431000000,
    "hash_algorithms": ["blake3-256"],
    "required_capabilities": ["anla:core:objects:1", "anla:core:chunks:1"],
    "objects_root": bytes(32),
    "chunks": {bytes([i]): {"raw_size": i * 1000, "codec": 0} for i in range(20)},
    "nested": [{"a": [1, {"b": b""}]}, [], {}],
    "true": True,
    "false": False,
    "negative": -1785063660431000000,
}


def test_manifest_shaped_value_round_trips():
    encoded = encode(MANIFEST_SHAPED)
    assert decode(encoded) == MANIFEST_SHAPED


def test_encoding_is_deterministic():
    """The property the manifest hash depends on: same value, same bytes, always —
    including when the dict was built in a different order."""
    shuffled = dict(reversed(list(MANIFEST_SHAPED.items())))
    assert encode(shuffled) == encode(MANIFEST_SHAPED)


def test_re_encoding_a_decoded_value_reproduces_the_bytes():
    """A decoder that accepts only canonical input, paired with an encoder that
    emits only canonical output, means round-tripping is byte-stable — which is
    what lets a reader verify a hash it did not compute itself."""
    encoded = encode(MANIFEST_SHAPED)
    assert encode(decode(encoded)) == encoded


@pytest.mark.parametrize("value", [
    0, 1, 23, 24, 255, 256, 65535, 65536, 2 ** 32 - 1, 2 ** 32, 2 ** 64 - 1,
    -1, -24, -25, -256, -(2 ** 64),
    b"", b"\x00", bytes(1000),
    "", "a", "會話", "🗄️", "café",
    [], [[]], [1, "two", b"\x03", True, False],
    {}, {"": 0}, {0: ""}, {b"k": [1, 2]},
])
def test_round_trip(value):
    assert decode(encode(value)) == value


def test_integers_beyond_64_bits_are_refused():
    with pytest.raises(CborError, match="64 bits"):
        encode(2 ** 64)
    with pytest.raises(CborError, match="64 bits"):
        encode(-(2 ** 64) - 1)


def test_nesting_within_the_bound_is_accepted():
    depth = 60
    value = decode(b"\x81" * depth + b"\x01")
    for _ in range(depth):
        value = value[0]
    assert value == 1


@pytest.mark.parametrize("depth", [65, 400, 20_000])
def test_nesting_past_the_bound_is_refused_not_crashed(depth):
    """A decoder is a parser fed by strangers, and recursion depth is an input.

    Found by probing rather than by reading: at 20,000 levels the first version
    raised RecursionError, which is a crash where a refusal was owed. The
    differential fuzzer classifies exactly that as a finding, which is why it is
    worth checking a new parser against it before the parser has any users.
    """
    encoded = b"\x81" * depth + b"\x01"
    with pytest.raises(CborError, match="nesting deeper"):
        decode(encoded)


def test_the_depth_bound_is_configurable_but_bounded():
    assert decode(b"\x81\x81\x01", max_depth=2) == [[1]]
    with pytest.raises(CborError, match="nesting deeper"):
        decode(b"\x81\x81\x81\x01", max_depth=2)
