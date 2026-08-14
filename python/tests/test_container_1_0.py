# -*- coding: utf-8 -*-
"""The ANLA 1.0 container — SPEC-1.0-DRAFT.md sections 3, 4, 6 and 9.

Three behaviours here are the reason 1.0 needs its own magic number rather than a
minor version, and each gets its own group below: record flags decide what a reader
does with what it does not recognise, footers chain backwards so an interrupted
append is survivable, and the header's footer hint is never permitted to decide
which snapshot is current.

The last of those is the one worth reading. A reader that trusts the hint reports an
older snapshot as current, with every hash checking out — which is the class of
failure this project keeps finding and the reason the tests are written before the
writer that would depend on them.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import (  # noqa: E402
    IntegrityFailure,
    InvalidInput,
    ManifestInvalid,
    UnsupportedCapability,
)
from anla1 import container as C  # noqa: E402
from anla1.cbor import encode  # noqa: E402

UUID = bytes(range(16))


def one_snapshot(*, snapshots: int = 1, hint: int | None = None,
                 hash_algorithm: str = C.CORE_HASH) -> bytes:
    """A container with *snapshots* appended snapshots and nothing else in it.

    No manifests, no chunks — the container is being tested, not the format built
    on it, and a fake manifest offset is enough to check the chain.
    """
    data = C.build_header(UUID)
    sequence = 1
    previous: int | None = None
    for snapshot in range(1, snapshots + 1):
        payload = encode({"pretend": "manifest", "snapshot": snapshot})
        manifest_offset = len(data)
        manifest = C.build_record(
            "MANF", {"hash_algorithm": hash_algorithm,
                     "payload_hash": C.hash_bytes(payload, hash_algorithm)},
            payload, sequence)
        data += manifest
        sequence += 1
        footer_offset = len(data)
        data += C.build_footer_record(
            sequence=sequence, snapshot_sequence=snapshot,
            manifest_offset=manifest_offset, manifest_length=len(manifest),
            preservation_root=bytes([snapshot]) * 32,
            previous_footer_offset=previous, hash_algorithm=hash_algorithm)
        sequence += 1
        previous = footer_offset
    return C.with_footer_hint(data, hint if hint is not None else previous or 0)


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------

def test_header_round_trip():
    header = C.parse_header(C.build_header(UUID, latest_footer_hint=4096))
    assert header.version_major == 1 and header.version_minor == 0
    assert header.header_size == C.HEADER_SIZE
    assert header.first_record_offset == C.HEADER_SIZE
    assert header.latest_footer_hint == 4096
    assert header.archive_uuid == UUID


def test_the_magic_carries_a_generation_digit_after_a_shared_tag():
    """Both profiles are ANLA, so both open with `ANLA`; the fifth byte says which
    generation, and the rest is the CR-LF-SUB text-mode canary PNG uses.

    An earlier draft of the specification claimed the two magics were one byte
    apart. This assertion is what said otherwise — inserting the digit shifts the
    trailer along, so four bytes differ.
    """
    from anla.format import ARCHIVE_MAGIC as MVP_MAGIC
    assert C.ARCHIVE_MAGIC != MVP_MAGIC
    assert len(C.ARCHIVE_MAGIC) == len(MVP_MAGIC) == 8
    assert C.ARCHIVE_MAGIC[:4] == MVP_MAGIC[:4] == b"ANLA"
    assert C.ARCHIVE_MAGIC[4:5] == b"1"
    # The canary survives in both: a text-mode transfer mangles CR, LF and SUB.
    # Written as byte values rather than escapes, because a control character in
    # a source literal is invisible to a reviewer.
    canary = bytes([0x0D, 0x0A, 0x1A])
    for magic in (C.ARCHIVE_MAGIC, MVP_MAGIC):
        assert canary in bytes(magic)


def test_an_mvp_archive_is_refused_by_the_1_0_parser_and_vice_versa():
    from anla.format import build_header as mvp_header, parse_header as mvp_parse
    with pytest.raises(ManifestInvalid, match="ANLA 1.0 magic"):
        C.parse_header(mvp_header(UUID) + bytes(96))
    with pytest.raises(ManifestInvalid, match="bootstrap magic"):
        mvp_parse(C.build_header(UUID) + bytes(96))


def test_header_crc_is_checked():
    data = bytearray(C.build_header(UUID))
    data[45] ^= 0xFF  # inside the UUID, which the CRC covers
    with pytest.raises(IntegrityFailure, match="header CRC"):
        C.parse_header(bytes(data))


def test_unknown_global_flags_are_refused():
    """Reserved means reserved. A reader that ignores an unknown global flag is a
    reader that will one day ignore the one that mattered."""
    data = bytearray(C.build_header(UUID))
    struct.pack_into("<Q", data, 16, 1)
    struct.pack_into("<I", data, 56, C.crc32(bytes(data[:56])))
    with pytest.raises(UnsupportedCapability, match="global flags"):
        C.parse_header(bytes(data))


def test_header_size_is_used_not_assumed():
    """A future minor version may extend the header; a reader that assumes 64 would
    then read the extension as a record."""
    data = bytearray(C.build_header(UUID)) + bytes(64)
    struct.pack_into("<I", data, 12, 128)          # header_size
    struct.pack_into("<Q", data, 24, 128)          # first_record_offset
    struct.pack_into("<I", data, 56, C.crc32(bytes(data[:56])))
    header = C.parse_header(bytes(data))
    assert header.header_size == 128 and header.first_record_offset == 128


def test_a_first_record_inside_the_header_is_refused():
    data = bytearray(C.build_header(UUID))
    struct.pack_into("<Q", data, 24, 32)
    struct.pack_into("<I", data, 56, C.crc32(bytes(data[:56])))
    with pytest.raises(ManifestInvalid, match="overlaps the header"):
        C.parse_header(bytes(data))


# ---------------------------------------------------------------------------
# record frame
# ---------------------------------------------------------------------------

def test_records_are_padded_to_eight_bytes():
    for payload_size in range(0, 24):
        record = C.build_record("CHNK", {"n": payload_size}, bytes(payload_size), 1)
        assert len(record) % 8 == 0
        parsed = C.parse_record(record, 0)
        assert parsed.total_length == len(record)
        assert parsed.payload_length == payload_size


def test_padding_must_be_zero():
    record = bytearray(C.build_record("CHNK", {"a": 1}, b"x", 1))
    assert C.padding_for(C.RECORD_FRAME_SIZE + 4 + 1) > 0
    record[-1] = 0xFF
    with pytest.raises(ManifestInvalid, match="padding is not zero"):
        C.parse_record(bytes(record), 0)


def test_record_header_is_canonical_cbor():
    record = C.build_record("CHNK", {"b": 2, "a": 1}, b"", 1)
    parsed = C.parse_record(record, 0)
    assert parsed.header == {"a": 1, "b": 2}
    # And the encoding is the canonical one, so the CRC is over stable bytes.
    assert record[C.RECORD_FRAME_SIZE:C.RECORD_FRAME_SIZE + parsed.header_length] \
        == encode({"a": 1, "b": 2})


def test_a_non_canonical_record_header_is_refused():
    record = bytearray(C.build_record("CHNK", {"a": 1}, b"", 1))
    start = C.RECORD_FRAME_SIZE
    # Re-encode {"a": 1} with the integer in a longer form: a1 61 61 18 01
    non_canonical = bytes.fromhex("a161611801")
    body = bytes(record[:start]) + non_canonical
    frame = bytearray(body[:C.RECORD_FRAME_SIZE])
    struct.pack_into("<I", frame, 12, len(non_canonical))
    struct.pack_into("<I", frame, 32, C.crc32(non_canonical))
    rebuilt = bytes(frame) + non_canonical
    rebuilt += bytes(C.padding_for(len(rebuilt)))
    # The wording is `<what>: <cbor complaint>`, uniform across the three places an
    # archive's CBOR is decoded and matching what the Rust reader prints. Two of
    # those three used to wrap `CborError` by hand and the third was forgotten,
    # which is how a malformed manifest escaped the Python CLI as a traceback; one
    # helper does it now and there is no hand-written block left to forget.
    with pytest.raises(ManifestInvalid, match="record header: "):
        C.parse_record(rebuilt, 0)


def test_unaligned_record_offsets_are_refused():
    data = bytes(4) + C.build_record("CHNK", {}, b"", 1)
    with pytest.raises(ManifestInvalid, match="8-byte aligned"):
        C.parse_record(data, 4)


def test_sequence_below_one_is_refused_by_both_directions():
    with pytest.raises(InvalidInput, match="at least 1"):
        C.build_record("CHNK", {}, b"", 0)
    record = bytearray(C.build_record("CHNK", {}, b"", 1))
    struct.pack_into("<Q", record, 24, 0)
    with pytest.raises(ManifestInvalid, match="at least 1"):
        C.parse_record(bytes(record), 0)


# ---------------------------------------------------------------------------
# flags — SPEC-1.0-DRAFT.md 4.2
# ---------------------------------------------------------------------------

def test_a_known_record_type_is_known_whatever_its_flags():
    for flags in (C.FLAG_REQUIRED_FOR_EXTRACTION, C.FLAG_AUXILIARY_DISPOSABLE):
        record = C.parse_record(C.build_record("CHNK", {}, b"", 1, flags), 0)
        assert C.record_disposition(record) == "known"


def test_an_unknown_type_marked_disposable_may_be_skipped():
    record = C.parse_record(
        C.build_record("XZZZ", {}, b"payload", 1, C.FLAG_AUXILIARY_DISPOSABLE), 0)
    assert C.record_disposition(record) == "skip"


def test_an_unknown_type_marked_required_must_fail():
    record = C.parse_record(
        C.build_record("XZZZ", {}, b"", 1, C.FLAG_REQUIRED_FOR_EXTRACTION), 0)
    assert C.record_disposition(record) == "fail"


def test_an_unknown_type_with_no_flags_must_fail():
    """The default is refusal. A writer that wanted it skippable had a bit to say
    so, and guessing is how a preservation format loses data quietly."""
    record = C.parse_record(C.build_record("XZZZ", {}, b"", 1, 0), 0)
    assert C.record_disposition(record) == "fail"


def test_required_and_disposable_together_is_an_error():
    both = C.FLAG_REQUIRED_FOR_EXTRACTION | C.FLAG_AUXILIARY_DISPOSABLE
    with pytest.raises(InvalidInput, match="both required and disposable"):
        C.build_record("AUXI", {}, b"", 1, both)
    record = bytearray(C.build_record("AUXI", {}, b"", 1, 0))
    struct.pack_into("<H", record, 10, both)
    with pytest.raises(ManifestInvalid, match="both required and disposable"):
        C.parse_record(bytes(record), 0)


def test_undefined_flag_bits_are_refused():
    record = bytearray(C.build_record("CHNK", {}, b"", 1, 0))
    struct.pack_into("<H", record, 10, 1 << 9)
    with pytest.raises(UnsupportedCapability, match="undefined record flags"):
        C.parse_record(bytes(record), 0)


# ---------------------------------------------------------------------------
# footer chain — SPEC-1.0-DRAFT.md 6
# ---------------------------------------------------------------------------

def test_a_single_snapshot_is_found():
    footer = C.find_latest_footer(one_snapshot())
    assert footer.snapshot_sequence == 1
    assert footer.previous_footer_offset is None
    assert footer.preservation_root == bytes([1]) * 32


def test_snapshots_chain_backwards_newest_first():
    footers = C.walk_footers(one_snapshot(snapshots=4))
    assert [f.snapshot_sequence for f in footers] == [4, 3, 2, 1]
    assert footers[-1].previous_footer_offset is None
    # Offsets strictly descend, which is what makes the walk terminate.
    offsets = [f.offset for f in footers]
    assert offsets == sorted(offsets, reverse=True)


def test_the_footer_hint_is_never_believed():
    """A hint pointing at an older footer must not make it the latest snapshot.

    This is the failure the draft singles out: an interrupted append leaves a stale
    hint, and a reader that trusts it reports the wrong snapshot while every hash
    checks out.
    """
    data = one_snapshot(snapshots=3)
    latest = C.find_latest_footer(data)
    older = C.walk_footers(data)[2]
    assert older.snapshot_sequence == 1

    lied_to = C.with_footer_hint(data, older.offset)
    assert C.parse_header(lied_to).latest_footer_hint == older.offset
    assert C.find_latest_footer(lied_to).snapshot_sequence == latest.snapshot_sequence


@pytest.mark.parametrize("hint", [0, 1, 7, 999_999, 2 ** 40])
def test_a_nonsense_hint_changes_nothing(hint):
    data = C.with_footer_hint(one_snapshot(snapshots=2), hint)
    assert C.find_latest_footer(data).snapshot_sequence == 2


def test_an_interrupted_append_leaves_the_previous_snapshot_readable():
    """The property the chain exists for. Truncate mid-footer and the archive is
    the earlier snapshot, not damage."""
    complete = one_snapshot(snapshots=2)
    three = one_snapshot(snapshots=3)
    # Cut inside the third snapshot's footer record.
    torn = three[:len(complete) + (len(three) - len(complete)) // 2]
    footer = C.find_latest_footer(torn)
    assert footer.snapshot_sequence == 2
    assert [f.snapshot_sequence for f in C.walk_footers(torn)] == [2, 1]


def test_a_corrupt_trailing_footer_is_skipped_not_fatal():
    data = bytearray(one_snapshot(snapshots=2))
    latest = C.find_latest_footer(bytes(data))
    # Corrupt the newest footer's payload so its hash fails.
    data[latest.record.payload_offset] ^= 0xFF
    footer = C.find_latest_footer(bytes(data))
    assert footer.snapshot_sequence == 1


def test_a_cycle_in_the_chain_is_refused():
    data = bytearray(one_snapshot(snapshots=2))
    latest = C.find_latest_footer(bytes(data))
    # Point the newest footer at itself, and repair every hash so only the cycle
    # check can catch it.
    body = {"snapshot_sequence": 2, "manifest_offset": C.HEADER_SIZE,
            "manifest_length": 8, "preservation_root": bytes(32),
            "previous_footer_offset": latest.offset}
    payload = encode(body)
    rebuilt = C.build_record(
        "FOOT", {"hash_algorithm": C.CORE_HASH,
                 "payload_hash": C.hash_bytes(payload, C.CORE_HASH)},
        payload, latest.record.sequence)
    forged = bytes(data[:latest.offset]) + rebuilt
    with pytest.raises(ManifestInvalid, match="cycle"):
        C.walk_footers(forged)


def test_a_chain_that_does_not_descend_is_refused():
    data = one_snapshot(snapshots=2)
    latest = C.find_latest_footer(data)
    body = {"snapshot_sequence": 2, "manifest_offset": C.HEADER_SIZE,
            "manifest_length": 8, "preservation_root": bytes(32),
            "previous_footer_offset": latest.offset + 8}
    payload = encode(body)
    rebuilt = C.build_record(
        "FOOT", {"hash_algorithm": C.CORE_HASH,
                 "payload_hash": C.hash_bytes(payload, C.CORE_HASH)},
        payload, latest.record.sequence)
    with pytest.raises(ManifestInvalid, match="does not descend"):
        C.walk_footers(data[:latest.offset] + rebuilt)


def test_a_footer_payload_hash_mismatch_is_an_integrity_failure():
    data = bytearray(one_snapshot())
    footer = C.find_latest_footer(bytes(data))
    data[footer.record.payload_offset] ^= 0x01
    with pytest.raises(IntegrityFailure, match="footer payload hash"):
        C.parse_footer_record(bytes(data), footer.offset)


@pytest.mark.parametrize("algorithm", ["blake3-256", "sha256"])
def test_the_footer_names_whichever_hash_wrote_it(algorithm):
    """Hash agility has a consequence that only appears in the reader: a footer is
    read *before* the manifest that declares `hash_algorithms`, so it cannot
    inherit the choice from it. It therefore has to say."""
    footer = C.find_latest_footer(one_snapshot(hash_algorithm=algorithm))
    assert footer.hash_algorithm == algorithm
    assert footer.record.header["hash_algorithm"] == algorithm


def test_the_default_hash_is_the_core_hash():
    assert C.CORE_HASH == "blake3-256"
    assert C.find_latest_footer(one_snapshot()).hash_algorithm == C.CORE_HASH


def test_an_archive_written_with_sha256_still_reads_after_blake3_arrived():
    """The payoff for putting agility in the container rather than in a revision:
    adding BLAKE3 changed one table and moved no field, so archives written before
    it existed are unaffected."""
    data = one_snapshot(snapshots=2, hash_algorithm="sha256")
    assert [f.snapshot_sequence for f in C.walk_footers(data)] == [2, 1]
    assert all(f.hash_algorithm == "sha256" for f in C.walk_footers(data))


def test_an_unknown_footer_hash_algorithm_is_refused_not_guessed():
    """`blake3-256` used to be this test's example of an unknown algorithm. It is
    known now, which is what shipping a hash looks like from a test's point of
    view — so the example moved rather than the assertion."""
    payload = encode({"snapshot_sequence": 1, "manifest_offset": 64,
                      "manifest_length": 8, "preservation_root": bytes(32)})
    record = C.build_record("FOOT", {"hash_algorithm": "sha3-512",
                                     "payload_hash": bytes(64)}, payload, 1)
    data = C.build_header(UUID) + record
    with pytest.raises(UnsupportedCapability, match="hash algorithm"):
        C.parse_footer_record(data, C.HEADER_SIZE)


def test_an_archive_with_no_footer_is_refused():
    with pytest.raises(ManifestInvalid, match="no complete footer"):
        C.find_latest_footer(C.build_header(UUID) + bytes(64))


def test_absent_footer_fields_are_omitted_not_null():
    """`null` is not in the CBOR profile, so absence is the absence of a key."""
    footer = C.find_latest_footer(one_snapshot())
    payload_map = footer.record.header
    assert "payload_hash" in payload_map
    assert footer.auxiliary_root is None and footer.index_offset is None


# ---------------------------------------------------------------------------
# capabilities — SPEC-1.0-DRAFT.md 9
# ---------------------------------------------------------------------------

def test_known_required_capabilities_are_accepted():
    report = C.check_capabilities({
        "required_capabilities": ["anla:core:objects:1", "anla:core:chunks:1"],
        "optional_capabilities": [],
    })
    assert report.required == ["anla:core:objects:1", "anla:core:chunks:1"]
    assert report.ignored_optional == []


def test_an_unknown_required_capability_is_refused():
    with pytest.raises(UnsupportedCapability, match="capabilities this reader lacks"):
        C.check_capabilities({"required_capabilities": ["anla:codec:zstd:rfc8878"]})


def test_an_unknown_optional_capability_is_ignored_but_recorded():
    report = C.check_capabilities({
        "required_capabilities": ["anla:core:objects:1"],
        "optional_capabilities": ["anla:index:fulltext:1", "anla:core:chunks:1"],
    })
    assert report.ignored_optional == ["anla:index:fulltext:1"]


def test_capability_lists_must_be_lists_of_strings():
    for bad in ({"required_capabilities": "anla:core:objects:1"},
                {"required_capabilities": [1]},
                {"optional_capabilities": {"a": 1}}):
        with pytest.raises(ManifestInvalid, match="list of strings"):
            C.check_capabilities(bad)


# ---------------------------------------------------------------------------
# whole-container walk
# ---------------------------------------------------------------------------

def test_every_record_in_a_two_snapshot_archive_walks_cleanly():
    data = one_snapshot(snapshots=2)
    records = list(C.walk_records(data))
    assert [r.type for r in records] == ["MANF", "FOOT", "MANF", "FOOT"]
    assert [r.sequence for r in records] == [1, 2, 3, 4]
    # Contiguous and aligned: each record starts where the last one ended.
    at = C.HEADER_SIZE
    for record in records:
        assert record.offset == at
        at = record.end
    assert at == len(data)
