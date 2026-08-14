# -*- coding: utf-8 -*-
"""Zstandard, and what having a compressor costs the freeze rule.

The interesting tests here are not "does it get smaller". They are the three places
where adding a codec could have quietly broken something that was previously true:

`test_a_codec_reaches_the_layout_and_not_the_tree` is the one that decides how the
freeze rule has to be phrased. It was written asserting that `preservation_root` was
invariant under compression, and it failed: descriptors carry `codec_id`,
`payload_length` and offsets, so `chunks_root` moves and `preservation_root` moves
with it. What is invariant is `objects_root` and the chunk ids. The test now asserts
both halves — what a codec may not touch, and what it may — because a test that only
checked the half I expected would have let the wrong claim into the specification.

`test_a_frame_that_decodes_to_something_else_is_caught` exists because the two hash
checks in the reader do different jobs, and without a compressed codec the second
one was unreachable. A test that cannot distinguish a live check from dead code is
not testing the check.

`test_a_declared_size_larger_than_the_descriptor_is_refused_before_allocating` is
the bomb. `zstandard`'s `max_output_size` is *ignored* for a frame that declares its
content size, which is every frame this writer produces — so the obvious protection
does nothing at all, and the real one is a header read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import (  # noqa: E402
    IntegrityFailure,
    ResourceLimitExceeded,
    UnsupportedCapability,
)
from anla1 import container as C  # noqa: E402
from anla1.cbor import encode  # noqa: E402
from anla1.codecs import (  # noqa: E402
    CODEC_STORE,
    CODEC_ZSTD,
    compress_chunk,
    decompress_chunk,
    deterministic_across_builds,
    have_zstd,
    plan_for,
)
from anla1.manifest import compute_roots  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    SourceEntry,
    append_snapshot,
    extract_snapshot,
    latest_snapshot,
    verify_archive,
)

pytestmark = pytest.mark.skipif(not have_zstd(),
                                reason="the zstandard library is not installed")

ARCHIVE_ID = bytes(range(16))
CREATED = 1_785_000_000_000_000_000
H = lambda data: C.hash_bytes(data, C.CORE_HASH)  # noqa: E731

PROSE = ("ANLA is an archive format for agents. " * 900).encode()


def lcg(length: int, seed: int = 20260807) -> bytes:
    """Bytes zstd cannot compress.

    Chained, not `(i * k + c) % 256`, which is periodic with a period of 32 and
    compresses 72x. That is the third time in one day this project has mistaken an
    arithmetic sequence for entropy, so it is a named function now.
    """
    state, out = seed, bytearray()
    for _ in range(length):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        out.append((state >> 16) & 0xFF)
    return bytes(out)


NOISE = lcg(20_000)


def pack(files: dict[str, bytes], **kwargs) -> bytes:
    return append_snapshot(
        b"", files=[SourceEntry.of(p, d) for p, d in files.items()],
        created_unix_ns=CREATED, archive_id=ARCHIVE_ID, **kwargs)


# ---------------------------------------------------------------------------
# it works, and it is smaller
# ---------------------------------------------------------------------------

def test_prose_compresses_and_round_trips():
    stored = pack({"paper.md": PROSE}, codec=CODEC_ZSTD)
    plain = pack({"paper.md": PROSE})
    assert len(stored) < len(plain) / 4
    snapshot = latest_snapshot(stored)
    verify_archive(stored)
    assert extract_snapshot(stored, snapshot) == {"paper.md": PROSE}


def test_a_chunk_that_grew_is_stored_instead():
    """Random bytes come back from zstd slightly longer than they went in."""
    used, packed = compress_chunk(NOISE, CODEC_ZSTD)
    assert used == CODEC_STORE and packed == NOISE

    data = pack({"noise.bin": NOISE}, codec=CODEC_ZSTD)
    descriptor = next(iter(latest_snapshot(data).manifest["chunks"].values()))
    assert descriptor["codec_id"] == CODEC_STORE
    assert extract_snapshot(data, latest_snapshot(data)) == {"noise.bin": NOISE}


def test_an_archive_that_used_no_zstd_does_not_require_it():
    """Declared from what was used, not from what was asked for."""
    data = pack({"noise.bin": NOISE}, codec=CODEC_ZSTD)
    required = latest_snapshot(data).manifest["required_capabilities"]
    assert "anla:codec:zstd:1" not in required

    data = pack({"paper.md": PROSE}, codec=CODEC_ZSTD)
    assert "anla:codec:zstd:1" in \
        latest_snapshot(data).manifest["required_capabilities"]


def test_a_reader_without_zstd_refuses_rather_than_guesses():
    data = pack({"paper.md": PROSE}, codec=CODEC_ZSTD)
    without = frozenset(c for c in C.KNOWN_CAPABILITIES if "zstd" not in c)
    with pytest.raises(UnsupportedCapability, match="capabilities this reader lacks"):
        C.check_capabilities(latest_snapshot(data).manifest, without)


def test_the_plan_records_what_produced_the_bytes():
    """Level and library, because compressed bytes are a function of the compressor
    and a plan that omits it cannot explain why two writers disagreed."""
    data = pack({"paper.md": PROSE}, codec=CODEC_ZSTD, level=7)
    plan = latest_snapshot(data).manifest["packing_plan"]["codec"]
    assert plan["name"] == "zstd" and plan["level"] == 7
    assert plan["library"].startswith("libzstd ")


# ---------------------------------------------------------------------------
# what compression must NOT change
# ---------------------------------------------------------------------------

def test_a_codec_reaches_the_layout_and_not_the_tree():
    """Both halves, because I only expected one of them.

    Invariant: `objects_root` and every chunk id, which are computed from raw
    content. Not invariant: `chunks_root` and `preservation_root`, which cover
    descriptors — `codec_id`, `payload_length`, `payload_hash`, offsets — and those
    are exactly what a codec exists to change.

    This test was written asserting that `preservation_root` was invariant. It
    failed, which is the only reason the wrong claim did not reach the
    specification. So `preservation_root` is the identity of the snapshot *as
    stored*, `objects_root` is the identity of the tree, and the freeze rule's
    byte-identity clause is a claim about `store`.
    """
    files = {"paper.md": PROSE, "noise.bin": NOISE}
    plain = latest_snapshot(pack(files)).manifest
    low = latest_snapshot(pack(files, codec=CODEC_ZSTD, level=3)).manifest
    high = latest_snapshot(pack(files, codec=CODEC_ZSTD, level=19)).manifest

    assert encode(low) != encode(high), "the levels must actually differ, or this " \
                                        "test is comparing a thing with itself"
    for root in ("objects_root", "metadata_root"):
        assert plain[root] == low[root] == high[root], root
    assert set(plain["chunks"]) == set(low["chunks"]) == set(high["chunks"])

    for root in ("chunks_root", "preservation_root"):
        assert plain[root] != low[root], f"{root} must move when the layout moves"


def test_only_store_is_promised_to_be_reproducible_across_builds():
    assert deterministic_across_builds(CODEC_STORE)
    assert not deterministic_across_builds(CODEC_ZSTD)


def test_deduplication_still_works_through_the_codec():
    """Two files with identical content share one chunk however it was stored."""
    data = pack({"a.md": PROSE, "b.md": PROSE}, codec=CODEC_ZSTD)
    assert verify_archive(data).unique_chunks == 1


# ---------------------------------------------------------------------------
# what a decoder owes
# ---------------------------------------------------------------------------

def test_a_declared_size_larger_than_the_descriptor_is_refused():
    """The bomb, and the reason the check is a header read.

    `max_output_size` is ignored for a frame that declares its content size, so the
    protection that looks obvious is not protection. This refuses on the mismatch
    between the frame's own declaration and the descriptor, before anything is
    allocated.
    """
    import zstandard

    bomb = zstandard.ZstdCompressor(level=3).compress(b"\0" * 50_000_000)
    assert len(bomb) < 5000, "a 50 MB frame of zeroes should be tiny"
    with pytest.raises(ResourceLimitExceeded, match="disagree about the decoded size"):
        decompress_chunk(bomb, CODEC_ZSTD, raw_size=1000)


def test_a_frame_declaring_no_size_is_refused():
    import io

    import zstandard

    buffer = io.BytesIO()
    with zstandard.ZstdCompressor(level=3).stream_writer(buffer, closefd=False) as w:
        w.write(b"x" * 10_000)
    frame = buffer.getvalue()
    with pytest.raises(ResourceLimitExceeded, match="declares no content size"):
        decompress_chunk(frame, CODEC_ZSTD, raw_size=10_000)


def test_a_frame_that_decodes_to_something_else_is_caught():
    """The check behind the payload hash, which store alone could never exercise.

    The forged chunk is a *valid* zstd frame, of the correct decoded length, with a
    correct `payload_hash` for its own bytes and a correctly rebuilt manifest. Every
    check but one passes. The one that fails is `chunk_id`, which is the hash of what
    came out — and until there was a codec, nothing could make those two disagree.
    """
    import zstandard

    body = ("the original paragraph. " * 500).encode()
    data = bytearray(pack({"paper.md": body}, codec=CODEC_ZSTD))
    snapshot = latest_snapshot(bytes(data))
    chunk_id, descriptor = next(iter(snapshot.manifest["chunks"].items()))
    assert descriptor["codec_id"] == CODEC_ZSTD, "this test needs a compressed chunk"

    forged = zstandard.ZstdCompressor(level=10).compress(b"!" * len(body))
    assert len(forged) <= descriptor["payload_length"], "forgery must fit in place"
    forged += b"\0" * (descriptor["payload_length"] - len(forged))

    start = descriptor["payload_offset"]
    data[start:start + descriptor["payload_length"]] = forged

    # Rebuild the descriptor and the manifest so that *only* the content is wrong.
    manifest = dict(snapshot.manifest)
    chunks = dict(manifest["chunks"])
    chunks[chunk_id] = dict(descriptor, payload_hash=H(forged))
    manifest["chunks"] = chunks
    roots = compute_roots(manifest["objects"], manifest["chunks"],
                          manifest["metadata"], manifest["auxiliary"], H)
    for name in ("objects_root", "chunks_root", "metadata_root", "preservation_root",
                 "auxiliary_root"):
        manifest[name] = getattr(roots, name)

    payload = encode(manifest)
    manifest_sequence = C.parse_record(bytes(data),
                                       snapshot.footer.manifest_offset).sequence
    record = C.build_record("MANF", {"hash_algorithm": C.CORE_HASH,
                                     "payload_hash": H(payload)}, payload,
                            manifest_sequence)
    head = bytes(data[:snapshot.footer.manifest_offset])
    out = head + record
    footer_offset = len(out)
    # The footer's sequence has to be the real next one. An arbitrary number is a
    # *second* defect, and now that verification checks structure before content it
    # is the one that gets reported — so the test would pass while proving something
    # else entirely. Found by the ordering change, which is the ordering change
    # earning its place.
    out += C.build_footer_record(
        sequence=manifest_sequence + 1, snapshot_sequence=1,
        manifest_offset=len(head),
        manifest_length=len(record), preservation_root=manifest["preservation_root"],
        auxiliary_root=manifest["auxiliary_root"], hash_algorithm=C.CORE_HASH)
    forged_archive = C.with_footer_hint(out, footer_offset)

    with pytest.raises(IntegrityFailure, match="does not match its id"):
        verify_archive(forged_archive)


def test_an_unknown_codec_id_is_refused():
    with pytest.raises(UnsupportedCapability, match="unknown codec id"):
        decompress_chunk(b"whatever", 99, raw_size=8)
    with pytest.raises(UnsupportedCapability, match="unknown codec id"):
        plan_for(99)
