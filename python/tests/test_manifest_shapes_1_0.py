# -*- coding: utf-8 -*-
"""A member's type is part of the manifest, and used to be nobody's job.

`tools/compare_manifest_rules.py` enumerates every single-member edit of a manifest
— delete it, rename it, give it each wrong shape — repairs every hash and root so
only the *rules* can refuse the result, and asks both implementations. Its first run
found **65 disagreements in 179 cases**, 33 of them this reader crashing with
`KeyError` or `TypeError` where Rust answered `manifest-invalid`.

Every one was the same thing: a member *used* by code that had established only that
it existed. `manifest["chunks"][id]["raw_size"]` was arithmetic on whatever was
there. So the fix is two tables — `MEMBER_SHAPES` and `CHUNK_SHAPES` — checked in
the place presence is already checked, and the tests below are the shapes that
matter most rather than a copy of the enumeration, which lives in the tool.

Widening the tool afterwards found four more, and the widening is the lesson: it had
no row for a *negative* integer, and CBOR's unsigned and negative integers are
different major types while Python's `int` is one type. `raw_size: -5` was accepted
here and refused by Rust, and only the random fuzzer had ever hit it.
"""

from __future__ import annotations

import pytest

from anla.errors import IntegrityFailure, ManifestInvalid
from anla1.blake3 import blake3_256 as H
from anla1.cbor import decode, encode
from anla1 import container as C
from anla1.manifest import compute_roots, parse_manifest
from anla1.snapshot import SourceEntry, append_snapshot, verify_archive


def archive() -> bytes:
    return append_snapshot(b"", files=[SourceEntry.of("a.txt", b"x" * 400)],
                           created_unix_ns=1, archive_id=bytes(16))


def edited(edit) -> bytes:
    """An archive whose manifest `edit` has changed, with every hash and root
    repaired — so nothing but a *rule* can refuse what comes back.

    Note what this cannot test: an edit to a *root* member, which the repair below
    overwrites. `tools/compare_manifest_rules.py` had the same hole and now takes a
    `protect` argument; here the root members are simply left to that tool, because
    a fixture that quietly undoes the edit under test is worse than one that does
    not offer the case.
    """
    data = archive()
    footer = C.find_latest_footer(data)
    record = C.parse_record(data, footer.manifest_offset)
    manifest = decode(data[record.payload_offset:
                           record.payload_offset + record.payload_length])
    edit(manifest)
    try:
        roots = compute_roots(manifest.get("objects", []), manifest.get("chunks", {}),
                              manifest.get("metadata", []),
                              manifest.get("auxiliary", []), H)
        for name in ("objects_root", "chunks_root", "metadata_root",
                     "preservation_root", "auxiliary_root"):
            if name in manifest:
                manifest[name] = getattr(roots, name)
    except Exception:
        roots = None
    payload = encode(manifest)
    header = dict(record.header)
    header["payload_hash"] = H(payload)
    rebuilt = C.build_record(record.type, header, payload, record.sequence,
                             record.flags)
    tail = C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=footer.snapshot_sequence,
        manifest_offset=record.offset, manifest_length=len(rebuilt),
        preservation_root=(roots.preservation_root if roots
                           else footer.preservation_root),
        previous_footer_offset=footer.previous_footer_offset,
        auxiliary_root=(roots.auxiliary_root if roots else footer.auxiliary_root),
        hash_algorithm=footer.hash_algorithm)
    return C.with_footer_hint(bytes(data[:record.offset]) + rebuilt + tail,
                              record.offset + len(rebuilt))


def test_the_fixture_produces_a_valid_archive_when_it_changes_nothing():
    """The premise. Every refusal below has to come from the edit and not the
    rebuilding, and this is the only thing that says so."""
    verify_archive(edited(lambda manifest: None))


@pytest.mark.parametrize("member,wrong", [
    ("objects", {}), ("chunks", []), ("metadata", "text"), ("auxiliary", 5),
    ("archive_id", "not bytes"), ("snapshot_sequence", "one"),
    ("created_unix_ns", []), ("hash_algorithms", "blake3-256"),
    ("optional_capabilities", {}),
])
def test_a_member_of_the_wrong_shape_is_refused(member, wrong):
    """`metadata` and `auxiliary` were accepted as *anything* before this: neither
    was in the one type check the manifest had, which covered `objects` and
    `chunks` and stopped there."""
    with pytest.raises(ManifestInvalid, match="must be"):
        verify_archive(edited(lambda m, k=member, v=wrong: m.__setitem__(k, v)))


@pytest.mark.parametrize("member", ["parent_snapshot", "packing_plan",
                                    "packing_plan_digest"])
def test_an_optional_member_of_the_wrong_shape_is_refused_too(member):
    """Absent is legal; present and malformed is not.

    Leaving these out of the table kept an `AttributeError` reachable after every
    required member had been fixed — the enumeration went 65 → 16, and four of the
    sixteen were exactly this.
    """
    with pytest.raises(ManifestInvalid, match="must be"):
        verify_archive(edited(lambda m, k=member: m.__setitem__(k, "wrong")))


@pytest.mark.parametrize("member", ["record_offset", "record_length",
                                    "payload_offset", "payload_length",
                                    "raw_size", "codec_id", "payload_hash"])
def test_every_chunk_descriptor_member_is_checked(member):
    """Nothing checked any of these. They were read straight out of the map by
    arithmetic and slicing, which is why a text `raw_size` was a `TypeError`."""
    def edit(manifest):
        for descriptor in manifest["chunks"].values():
            descriptor[member] = "wrong"

    with pytest.raises(ManifestInvalid, match="must be"):
        verify_archive(edited(edit))

    def drop(manifest):
        for descriptor in manifest["chunks"].values():
            descriptor.pop(member)

    with pytest.raises(ManifestInvalid, match="missing required member"):
        verify_archive(edited(drop))


@pytest.mark.parametrize("value", [-5, True])
def test_a_size_that_is_not_an_unsigned_integer_is_refused(value):
    """CBOR's unsigned and negative integers are different major types; Python's
    `int` is one type and covers `bool` as well. `isinstance(value, int)` therefore
    accepted `raw_size: -5` where Rust's `as_u64()` refused it, and the difference
    surfaced as this reader blaming a *root mismatch* for a malformed manifest."""
    def edit(manifest):
        for descriptor in manifest["chunks"].values():
            descriptor["raw_size"] = value

    with pytest.raises(ManifestInvalid):
        verify_archive(edited(edit))


def test_an_object_may_not_name_a_chunk_the_manifest_does_not_describe():
    """`verify` exists to predict whether `extract` will work, and it did not.

    With the chunk map emptied, verification passed — the roots all agreed, because
    they were recomputed over the emptied map — and extraction then died on a
    `KeyError` looking the descriptor up. An archive reported sound that cannot be
    unpacked is the worst answer this software can give.
    """
    with pytest.raises(ManifestInvalid, match="does not describe"):
        verify_archive(edited(lambda m: m.__setitem__("chunks", {})))


def test_a_descriptor_pointing_past_the_end_is_malformed_not_corrupt():
    """Python slicing past the end returns what is there and no complaint.

    So a descriptor claiming a payload beyond the archive produced a *shorter*
    string whose hash then failed, and the reader reported an integrity failure —
    "these bytes are damaged, find another copy" — for a manifest describing
    something that was never there. The two send a caller to different places.
    """
    def edit(manifest):
        for descriptor in manifest["chunks"].values():
            descriptor["payload_offset"] = 999_999

    with pytest.raises(ManifestInvalid, match="past the end"):
        verify_archive(edited(edit))


def test_a_genuinely_damaged_payload_is_still_an_integrity_failure():
    """The negative control for the test above.

    Reclassifying the out-of-range case would be worthless if it also reclassified
    real corruption. A descriptor that points *inside* the archive at the wrong
    bytes must still say the bytes are wrong.
    """
    data = bytearray(archive())
    footer = C.find_latest_footer(bytes(data))
    manifest = parse_manifest(bytes(data)[
        (r := C.parse_record(bytes(data), footer.manifest_offset)).payload_offset:
        r.payload_offset + r.payload_length])
    descriptor = next(iter(manifest["chunks"].values()))
    at = descriptor["payload_offset"]
    data[at] ^= 0xFF
    with pytest.raises(IntegrityFailure):
        verify_archive(bytes(data))
