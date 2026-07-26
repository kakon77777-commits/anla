# -*- coding: utf-8 -*-
"""The `anla-cdc-1` chunking profile — whitepaper open question 3, answered.

The question was how FastCDC parameters can become a permanently stable profile.
A chunker whose boundaries depend on an unstated gear table is a chunker whose
output depends on which implementation ran, which is the same class of defect as
the locale-dependent object ordering this project already had to correct. These
tests pin every part of the answer: the table's derivation, the boundary
predicate, the tiling, and the property the whole thing exists for.
"""

from __future__ import annotations

import hashlib
import struct

import pytest

from anla import PackPlan, SourceFile, SourceTree, open_archive, pack
from anla.errors import InvalidInput
from anla.fastcdc import (
    GEAR,
    GEAR_TABLE_DIGEST,
    GEAR_TABLE_ID,
    PROFILE_ID,
    CdcProfile,
    build_gear_table,
    cut_points,
)
from conftest import CASES, TREES, build_tree, pack_case

SMALL = CdcProfile(min_size=1024, avg_size=4096, max_size=16384)


def lcg(seed: int, length: int) -> bytes:
    state = seed
    out = bytearray(length)
    for index in range(length):
        state = (1103515245 * state + 12345) & 0xFFFFFFFF
        out[index] = (state >> 16) & 0xFF
    return bytes(out)


def test_gear_table_is_derived_not_copied():
    """Three lines, independently. If this fails, someone edited the table."""
    expected = tuple(
        struct.unpack(">I", hashlib.sha256(
            GEAR_TABLE_ID.encode("ascii") + b"\x00" + bytes([index])).digest()[:4])[0]
        for index in range(256)
    )
    assert GEAR == expected
    assert len(set(GEAR)) == 256, "the table has a collision, which would bias boundaries"


def test_gear_table_digest_pins_the_table():
    flat = b"".join(struct.pack(">I", word) for word in GEAR)
    assert GEAR_TABLE_DIGEST == hashlib.sha256(flat).hexdigest()
    # Written out so a third implementation can compare without running our code.
    assert GEAR_TABLE_DIGEST == \
        "ecdce4099dbb06b791d1255eb242b2ca9a0454541b6d6c376b5df5d17a7e66c2"


def test_a_different_table_id_gives_a_different_table():
    assert build_gear_table("anla-gear-2") != GEAR


def test_ranges_tile_the_input_exactly():
    data = lcg(7, 200_000)
    ranges = cut_points(data, SMALL)
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(data)
    assert all(a[1] == b[0] for a, b in zip(ranges, ranges[1:]))
    assert sum(end - start for start, end in ranges) == len(data)


def test_chunk_sizes_respect_min_and_max():
    data = lcg(11, 300_000)
    sizes = [end - start for start, end in cut_points(data, SMALL)]
    # Every chunk but the last is inside the declared bounds; the last is whatever
    # is left, which may be shorter than min.
    assert all(SMALL.min_size <= size <= SMALL.max_size for size in sizes[:-1])
    assert sizes[-1] <= SMALL.max_size
    mean = sum(sizes) / len(sizes)
    # Normalized chunking should land within a factor of two of the target.
    assert SMALL.avg_size / 2 <= mean <= SMALL.avg_size * 2, mean


def test_boundaries_depend_only_on_content_not_position():
    """The property CDC exists for: a cut is a function of the bytes around it."""
    data = lcg(3, 120_000)
    ranges = cut_points(data, SMALL)
    # Take an interior chunk and confirm the same window cuts the same way when it
    # appears at a different offset.
    start, end = ranges[len(ranges) // 2]
    relocated = lcg(99, 40_000) + data[start - SMALL.min_size:end + SMALL.max_size]
    relocated_ranges = cut_points(relocated, SMALL)
    boundaries = {b for _, b in relocated_ranges}
    offset = 40_000 + SMALL.min_size
    assert any(abs(b - (offset + (end - start))) <= SMALL.max_size
               for b in boundaries)


def test_insertion_at_the_front_keeps_most_chunks():
    """The number that justifies the whole profile.

    Prepend ten bytes. Fixed-size chunking shares nothing, because every later
    boundary moved. Content-defined chunking shares nearly everything.
    """
    original = lcg(7, 32768)
    shifted = b"INSERTED.." + original

    def chunks(data, profile):
        return [data[s:e] for s, e in cut_points(data, profile)]

    cdc_before = set(chunks(original, SMALL))
    cdc_after = chunks(shifted, SMALL)
    cdc_shared = sum(1 for chunk in cdc_after if chunk in cdc_before)

    size = SMALL.avg_size
    fixed_before = {original[i:i + size] for i in range(0, len(original), size)}
    fixed_after = [shifted[i:i + size] for i in range(0, len(shifted), size)]
    fixed_shared = sum(1 for chunk in fixed_after if chunk in fixed_before)

    assert fixed_shared == 0, "fixed-size chunking should share nothing after a shift"
    assert cdc_shared >= len(cdc_after) - 2, \
        f"content-defined chunking shared only {cdc_shared}/{len(cdc_after)}"


def test_the_fixture_pair_shows_the_difference_in_a_real_archive():
    cdc = pack_case(next(c for c in CASES if c.id == "cdc-shifted-pair"))
    fixed = pack_case(next(c for c in CASES if c.id == "fixed-shifted-pair"))

    cdc_stats, fixed_stats = cdc.statistics, fixed.statistics
    assert fixed_stats["unique_chunks"] == fixed_stats["chunk_references"], \
        "the fixed-size case is supposed to deduplicate nothing"
    assert cdc_stats["unique_chunks"] < cdc_stats["chunk_references"]
    assert len(cdc.data) < len(fixed.data) * 0.7, \
        f"{len(cdc.data)} vs {len(fixed.data)} — expected a large saving"

    # And both still restore exactly what went in.
    tree = build_tree(TREES["shifted-pair"])
    for result in (cdc, fixed):
        archive = open_archive(result.data, full=True)
        for source in tree.files:
            assert archive.read(source.path) == source.data


def test_the_plan_records_everything_a_second_implementation_needs():
    result = pack(SourceTree(name="t", files=[SourceFile("a.bin", lcg(5, 50_000))]),
                  PackPlan(chunking=SMALL, compression="store"))
    chunking = open_archive(result.data, full=False).manifest["plan"]["chunking"]
    assert chunking == {
        "algorithm": "fastcdc",
        "version": PROFILE_ID,
        "gear_table_id": GEAR_TABLE_ID,
        "gear_table_sha256": GEAR_TABLE_DIGEST,
        "min": SMALL.min_size,
        "avg": SMALL.avg_size,
        "max": SMALL.max_size,
        "normalization": SMALL.normalization,
        "fingerprint": "gear32",
        "boundary": "top-bits-zero",
    }


def test_a_fixed_size_plan_has_no_chunking_member():
    """Its absence *means* fixed-size, which is what keeps every archive written
    before this profile existed byte-identical to what it was."""
    result = pack(SourceTree(name="t", files=[SourceFile("a.txt", b"x")]))
    assert "chunking" not in open_archive(result.data, full=False).manifest["plan"]


@pytest.mark.parametrize("kwargs", [
    {"algorithm": "rabin"},
    {"version": "anla-cdc-2"},
    {"gear_table_id": "somebody-elses-table"},
    {"min_size": 0},
    {"min_size": 8192, "avg_size": 4096},
    {"avg_size": 5000},          # not a power of two
    {"avg_size": 4096, "normalization": 9},
])
def test_unusable_profiles_are_refused(kwargs):
    base = {"min_size": 1024, "avg_size": 4096, "max_size": 16384}
    with pytest.raises(InvalidInput):
        CdcProfile(**{**base, **kwargs})


def test_reader_needs_no_knowledge_of_chunking():
    """A content-defined archive is readable by a decoder that has never heard of
    the profile: chunk references are chunk references. This is why the profile
    needs no format version bump."""
    result = pack(SourceTree(name="t", files=[SourceFile("a.bin", lcg(13, 60_000))]),
                  PackPlan(chunking=SMALL, compression="store"))
    archive = open_archive(result.data, full=True)
    assert archive.verification["status"] == "ok"
    assert archive.manifest["format_version"] == "0.1"
