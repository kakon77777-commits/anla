# -*- coding: utf-8 -*-
"""Append-only snapshots — SPEC-1.0-DRAFT.md section 6 and `design/milestone-3-plan.md`.

The container's tests cover the footer chain as bytes. These cover what the chain is
*for*: a second snapshot that stores only what changed, an older snapshot that is
still extractable, and a lineage claim that is checked rather than merely written
down.

The rejection group is the point of the file. Every rule in the plan's table is a
rule some future writer will violate by accident, and each one here is asserted
against an archive built to violate exactly that rule and nothing else — which is
why the helpers below rebuild the newest snapshot properly, hashes and all, instead
of flipping a byte and calling the resulting failure a pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import IntegrityFailure, InvalidInput, ManifestInvalid  # noqa: E402
from anla1 import container as C  # noqa: E402
from anla1.cbor import encode  # noqa: E402
from anla1.manifest import compute_roots  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    SourceEntry,
    append_snapshot,
    cdc_chunker,
    create_archive,
    diff,
    extract_snapshot,
    latest_snapshot,
    list_snapshots,
    snapshot_id_of,
    verify_archive,
)

ARCHIVE_ID = bytes(range(16))
CREATED = 1_785_000_000_000_000_000

V1 = {
    "docs/readme.txt": b"ANLA snapshots, take one\n",
    "docs/copy.txt": b"ANLA snapshots, take one\n",     # same bytes, one chunk
    "data.bin": bytes(range(64)) * 3,
    "empty.txt": b"",
}
V2 = dict(V1, **{"docs/readme.txt": b"ANLA snapshots, take two\n",
                 "notes.md": b"# added in snapshot 2\n"})
del V2["empty.txt"]                                     # and one removed


def build_two() -> bytes:
    one = append_snapshot(b"", files=V1, directories=["docs"],
                          created_unix_ns=CREATED, archive_id=ARCHIVE_ID)
    return append_snapshot(one, files=V2, directories=["docs"],
                           created_unix_ns=CREATED + 1)


def chunk_records(data: bytes) -> int:
    header = C.parse_header(data)
    return sum(1 for record in C.walk_records(data, header) if record.type == "CHNK")


# ---------------------------------------------------------------------------
# the basic shape
# ---------------------------------------------------------------------------

def test_a_single_snapshot_round_trips():
    data = append_snapshot(b"", files=V1, directories=["docs"],
                           created_unix_ns=CREATED, archive_id=ARCHIVE_ID)
    snapshot = latest_snapshot(data)
    assert snapshot.sequence == 1
    assert extract_snapshot(data, snapshot) == V1
    assert verify_archive(data).unique_chunks == 2   # readme/copy share; data.bin


def test_the_first_snapshot_declares_no_parent():
    data = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                           archive_id=ARCHIVE_ID)
    assert "parent_snapshot" not in latest_snapshot(data).manifest


def test_an_empty_archive_is_a_header_and_nothing_else():
    data = create_archive(ARCHIVE_ID)
    assert len(data) == C.HEADER_SIZE
    assert C.parse_header(data).archive_uuid == ARCHIVE_ID
    with pytest.raises(ManifestInvalid, match="no complete footer"):
        latest_snapshot(data)


def test_lineage_is_recorded_and_checked():
    data = build_two()
    one, two = list_snapshots(data)
    assert (one.sequence, two.sequence) == (1, 2)
    assert two.parent_snapshot == one.snapshot_id
    # `snapshot_id` is the hash of the stored manifest bytes, and re-encoding the
    # decoded manifest must reproduce them — otherwise every parent link would be a
    # hash of something no longer in the file.
    assert snapshot_id_of(one.manifest) == one.snapshot_id


# ---------------------------------------------------------------------------
# what the append actually saves
# ---------------------------------------------------------------------------

def test_an_unchanged_tree_stores_no_chunks_at_all():
    """The second snapshot of an identical tree is a manifest and a footer."""
    one = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                          archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files=V1, created_unix_ns=CREATED + 1)
    assert chunk_records(one) == chunk_records(two)
    report = verify_archive(two)
    assert report.unique_chunks == 2
    assert len(report.snapshots) == 2


def test_a_changed_file_appends_only_its_own_chunk():
    one = append_snapshot(b"", files=V1, directories=["docs"],
                          created_unix_ns=CREATED, archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files=V2, directories=["docs"],
                          created_unix_ns=CREATED + 1)
    # readme changed and notes.md is new; data.bin and copy.txt are untouched.
    assert chunk_records(two) - chunk_records(one) == 2


def test_old_bytes_are_never_rewritten():
    """Everything the first snapshot wrote survives byte for byte.

    Except the header's `latest_footer_hint`, which is advisory by specification and
    which no reader is allowed to use to decide what is latest — so moving it cannot
    change how anything reads.
    """
    one = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                          archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files=V2, created_unix_ns=CREATED + 1)
    assert two[:len(one)] != one                          # the hint moved
    assert two[C.HEADER_SIZE:len(one)] == one[C.HEADER_SIZE:]
    assert two[:32] == one[:32]                           # magic, version, sizes


def test_a_snapshot_manifest_is_self_contained():
    """Snapshot 2 lists descriptors for chunks written during snapshot 1.

    This is decision 1: extracting any snapshot reads exactly one manifest. A delta
    manifest would make `preservation_root` cover a tree its own document does not
    contain.
    """
    data = build_two()
    one, two = list_snapshots(data)
    reused = set(one.manifest["chunks"]) & set(two.manifest["chunks"])
    assert reused, "the second snapshot shares nothing, so nothing is being tested"
    for chunk_id in reused:
        descriptor = two.manifest["chunks"][chunk_id]
        assert descriptor == one.manifest["chunks"][chunk_id]
        assert descriptor["record_offset"] < one.footer.manifest_offset


def test_the_append_is_deterministic():
    assert build_two() == build_two()


def test_content_defined_chunking_shares_across_snapshots():
    """The workload `anla-cdc-1` exists for, now across snapshots rather than files.

    With sizes scaled down so the test stays fast. The profile identity is untouched
    — same algorithm, same version, same gear table — because the sizes are declared
    per archive and the boundary rule is what has to be pinned.

    The content is an LCG rather than something arithmetic, and that is load-bearing:
    on periodic input the gear fingerprint cycles through too few values to satisfy
    the boundary condition, every cut lands on `max_size`, and content-defined
    chunking degenerates to fixed-size — at which point a shifted copy shares nothing
    and this test passes vacuously while asserting the opposite. The first version of
    it did exactly that.
    """
    from anla.fastcdc import CdcProfile

    state, body = 12345, bytearray()
    for _ in range(300_000):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        body.append((state >> 16) & 0xFF)
    body = bytes(body)
    chunker = cdc_chunker(CdcProfile(min_size=1024, avg_size=4096, max_size=16384))
    one = append_snapshot(b"", files={"big.bin": body}, created_unix_ns=CREATED,
                          chunker=chunker, archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files={"big.bin": b"prepended!" + body},
                          created_unix_ns=CREATED + 1, chunker=chunker)
    a, b = list_snapshots(two)
    shared = set(a.manifest["chunks"]) & set(b.manifest["chunks"])
    assert len(shared) >= 0.8 * len(a.manifest["chunks"])
    assert extract_snapshot(two, b)["big.bin"] == b"prepended!" + body
    # And the point of sharing them: the second copy costs far less than the first.
    assert len(two) - len(one) < 0.35 * len(one)


# ---------------------------------------------------------------------------
# reading any snapshot, not only the newest
# ---------------------------------------------------------------------------

def test_every_snapshot_is_extractable_not_only_the_latest():
    data = build_two()
    one, two = list_snapshots(data)
    assert extract_snapshot(data, one) == V1
    assert extract_snapshot(data, two) == V2


def test_three_snapshots_each_restore_their_own_tree():
    trees = [V1, V2, dict(V2, **{"data.bin": b"replaced\n"})]
    data = b""
    for index, tree in enumerate(trees):
        data = append_snapshot(data, files=tree, created_unix_ns=CREATED + index,
                               archive_id=ARCHIVE_ID if index == 0 else None)
    snapshots = list_snapshots(data)
    assert [s.sequence for s in snapshots] == [1, 2, 3]
    for snapshot, tree in zip(snapshots, trees):
        assert extract_snapshot(data, snapshot) == tree


def test_diff_reports_what_changed():
    data = build_two()
    one, two = list_snapshots(data)
    changes = diff(one, two)
    assert changes.added == ["notes.md"]
    assert changes.removed == ["empty.txt"]
    assert changes.modified == ["docs/readme.txt"]
    assert "data.bin" in changes.unchanged
    assert changes.shared_chunks and changes.changed


def test_diff_of_a_snapshot_with_itself_is_empty():
    data = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                           archive_id=ARCHIVE_ID)
    only = latest_snapshot(data)
    assert not diff(only, only).changed


# ---------------------------------------------------------------------------
# an interrupted append
# ---------------------------------------------------------------------------

def test_an_interrupted_append_reads_as_the_previous_snapshot():
    """Truncate at *every* alignment boundary in the appended region.

    This is the property the footer chain exists for, and it has only ever been
    tested at a handful of offsets. A partial append must read as the older
    snapshot — not as a newer one, and not as damage.
    """
    one = append_snapshot(b"", files=V1, directories=["docs"],
                          created_unix_ns=CREATED, archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files=V2, directories=["docs"],
                          created_unix_ns=CREATED + 1)
    checked = 0
    for cut in range(len(one), len(two), C.RECORD_ALIGNMENT):
        torn = two[:cut]
        snapshot = latest_snapshot(torn)
        assert snapshot.sequence == 1, f"a torn append read as snapshot 2 at {cut}"
        assert extract_snapshot(torn, snapshot) == V1
        checked += 1
    assert checked > 8, "the appended region was too small to be a real test"


def test_a_torn_append_can_be_appended_to_again():
    """Recovery, not just survival: the archive is still writable afterwards.

    An append resumes at the end of the newest complete snapshot, not at the end of
    the file, so the abandoned bytes are reclaimed. Writing after them instead would
    put every following record at an offset that is not a multiple of eight — and
    `find_latest_footer` scans in alignment-sized steps, so the new footer would be
    *invisible* and the archive would keep reading as the older snapshot. That is
    what this test found; it is not a hypothetical.
    """
    one = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                          archive_id=ARCHIVE_ID)
    two = append_snapshot(one, files=V2, created_unix_ns=CREATED + 1)
    for divisor in (2, 3, 5):
        torn = two[:len(one) + (len(two) - len(one)) // divisor]
        repaired = append_snapshot(torn, files=V2, created_unix_ns=CREATED + 2)
        snapshots = list_snapshots(repaired)
        assert [s.sequence for s in snapshots] == [1, 2]
        assert extract_snapshot(repaired, snapshots[1]) == V2
        verify_archive(repaired)
        assert len(repaired) == len(two), "the failed append was not reclaimed"


def test_every_record_begins_on_an_alignment_boundary():
    """The invariant `find_latest_footer`'s backward scan silently depends on.

    Records are padded to eight bytes, which keeps them aligned only if every writer
    also *starts* at an aligned offset. A writer that does not makes the newest
    footer unfindable while leaving every hash in the archive correct, so this is
    asserted about the whole file rather than trusted to follow from the padding.
    """
    data = build_two()
    header = C.parse_header(data)
    assert header.first_record_offset % C.RECORD_ALIGNMENT == 0
    for record in C.walk_records(data, header):
        assert record.offset % C.RECORD_ALIGNMENT == 0
    assert len(data) % C.RECORD_ALIGNMENT == 0


# ---------------------------------------------------------------------------
# rejections — the plan's table, one test each
# ---------------------------------------------------------------------------

def replace_latest(data: bytes, manifest: dict, *,
                   footer_sequence: int | None = None) -> bytes:
    """Rebuild the newest snapshot's `MANF` and `FOOT` around a modified manifest.

    Properly: the payload hash is recomputed and the footer re-derived, so the
    archive that comes out is wrong in exactly one way and internally consistent in
    every other. A test that instead corrupted a byte would pass on the hash check
    and prove nothing about the rule it claims to test.
    """
    latest = latest_snapshot(data)
    algorithm = latest.hash_algorithm
    head = data[:latest.footer.manifest_offset]
    sequence = C.parse_record(data, latest.footer.manifest_offset).sequence

    payload = encode(manifest)
    record = C.build_record(
        "MANF", {"hash_algorithm": algorithm,
                 "payload_hash": C.hash_bytes(payload, algorithm)},
        payload, sequence)
    out = head + record
    footer_offset = len(out)
    out += C.build_footer_record(
        sequence=sequence + 1,
        snapshot_sequence=(footer_sequence if footer_sequence is not None
                           else manifest["snapshot_sequence"]),
        manifest_offset=len(head), manifest_length=len(record),
        preservation_root=manifest["preservation_root"],
        auxiliary_root=manifest["auxiliary_root"],
        previous_footer_offset=latest.footer.previous_footer_offset,
        hash_algorithm=algorithm)
    return C.with_footer_hint(out, footer_offset)


def reroot(manifest: dict, algorithm: str) -> dict:
    """Recompute the roots, for mutations that change what the manifest lists."""
    def hasher(payload: bytes) -> bytes:
        return C.hash_bytes(payload, algorithm)

    roots = compute_roots(manifest["objects"], manifest["chunks"],
                          manifest["metadata"], manifest["auxiliary"], hasher)
    for name in ("objects_root", "chunks_root", "metadata_root", "preservation_root",
                 "auxiliary_root"):
        manifest[name] = getattr(roots, name)
    return manifest


def test_a_parent_that_does_not_match_the_chain_is_refused():
    """The rule that makes `parent_snapshot` more than a comment.

    Note what is *not* needed to build this archive: no root changes, because
    `parent_snapshot` is not covered by `preservation_root` — the gap Milestone 0
    measured. Everything hashes. Only the chain says otherwise.
    """
    data = build_two()
    manifest = dict(latest_snapshot(data).manifest)
    manifest["parent_snapshot"] = bytes(32)
    forged = replace_latest(data, manifest)
    with pytest.raises(IntegrityFailure, match="parent_snapshot does not match"):
        list_snapshots(forged)


def test_a_snapshot_after_the_first_with_no_parent_is_refused():
    data = build_two()
    manifest = {k: v for k, v in latest_snapshot(data).manifest.items()
                if k != "parent_snapshot"}
    with pytest.raises(ManifestInvalid, match="declares no parent"):
        list_snapshots(replace_latest(data, manifest))


def test_a_non_contiguous_snapshot_sequence_is_refused():
    data = build_two()
    manifest = dict(latest_snapshot(data).manifest)
    manifest["snapshot_sequence"] = 7
    with pytest.raises(ManifestInvalid, match="not contiguous"):
        list_snapshots(replace_latest(data, manifest))


def test_a_first_snapshot_that_is_not_sequence_one_is_refused():
    data = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                           archive_id=ARCHIVE_ID)
    manifest = dict(latest_snapshot(data).manifest)
    manifest["snapshot_sequence"] = 2
    with pytest.raises(ManifestInvalid, match="is not sequence 1"):
        list_snapshots(replace_latest(data, manifest))


def test_a_forward_chunk_reference_is_refused():
    """A chunk record at or past the manifest that references it cannot exist in an
    append-only file, which is what makes this arithmetic rather than a guess."""
    data = build_two()
    latest = latest_snapshot(data)
    manifest = dict(latest.manifest)
    chunks = dict(manifest["chunks"])
    victim = sorted(chunks)[0]
    descriptor = dict(chunks[victim])
    descriptor["record_offset"] = latest.footer.manifest_offset + 8
    chunks[victim] = descriptor
    manifest["chunks"] = chunks
    forged = replace_latest(data, reroot(manifest, latest.hash_algorithm))
    with pytest.raises(ManifestInvalid, match="not before the manifest"):
        list_snapshots(forged)


def test_one_chunk_id_with_two_different_descriptors_is_refused():
    data = build_two()
    latest = latest_snapshot(data)
    older = list_snapshots(data)[0]
    shared = sorted(set(older.manifest["chunks"]) & set(latest.manifest["chunks"]))[0]

    manifest = dict(latest.manifest)
    chunks = dict(manifest["chunks"])
    descriptor = dict(chunks[shared])
    descriptor["raw_size"] += 1              # same id, a different story about it
    chunks[shared] = descriptor
    manifest["chunks"] = chunks
    forged = replace_latest(data, reroot(manifest, latest.hash_algorithm))
    with pytest.raises(IntegrityFailure, match="two different descriptors"):
        list_snapshots(forged)


def test_a_second_hash_algorithm_in_one_archive_is_refused():
    """Chunk ids *are* hashes, so two algorithms means two namespaces of chunk id
    sharing one lookup — identical bytes stored twice and deduplication quietly off.
    Hash agility is per archive, not per snapshot."""
    one = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                          archive_id=ARCHIVE_ID, hash_algorithm="sha256")
    assert latest_snapshot(one).hash_algorithm == "sha256"
    with pytest.raises(InvalidInput, match="one hash algorithm"):
        append_snapshot(one, files=V2, created_unix_ns=CREATED + 1,
                        hash_algorithm="blake3-256")


def test_appending_to_the_wrong_archive_is_refused():
    one = append_snapshot(b"", files=V1, created_unix_ns=CREATED,
                          archive_id=ARCHIVE_ID)
    with pytest.raises(InvalidInput, match="does not match the archive"):
        append_snapshot(one, files=V2, created_unix_ns=CREATED + 1,
                        archive_id=bytes(16))


def test_a_new_archive_needs_an_id():
    with pytest.raises(InvalidInput, match="needs an archive_id"):
        append_snapshot(b"", files=V1, created_unix_ns=CREATED)


def test_a_corrupted_chunk_is_found_by_verify_even_if_no_snapshot_reads_it():
    """Verification walks every chunk of every snapshot, not only the newest tree."""
    data = bytearray(build_two())
    one = list_snapshots(bytes(data))[0]
    # A chunk that snapshot 2 dropped, so extracting the latest snapshot would not
    # touch it. An archive is not verified by verifying its most recent state.
    dropped = [cid for cid, _ in one.manifest["chunks"].items()]
    descriptor = one.manifest["chunks"][dropped[0]]
    data[descriptor["payload_offset"]] ^= 0xFF
    with pytest.raises(IntegrityFailure, match="does not match its id"):
        verify_archive(bytes(data))


def test_verify_reports_the_saving():
    data = build_two()
    report = verify_archive(data)
    assert len(report.snapshots) == 2
    assert report.archive_bytes == len(data)
    # Two snapshots of an overlapping tree occupy less than the sum of their trees.
    assert report.chunk_bytes < report.logical_bytes


def test_an_archive_uses_one_chunking_rule():
    """The same defect as the hash algorithm, one layer down.

    Two snapshots cut by different boundaries produce different chunk ids for
    identical bytes, so deduplication silently does nothing while every check still
    passes. Found by running `test_demo/` on real papers and noticing that a
    one-paragraph edit cost a whole file.
    """
    from anla.fastcdc import CdcProfile

    small = cdc_chunker(CdcProfile(min_size=1024, avg_size=4096, max_size=16384))
    files = [SourceEntry.of("a.txt", b"x" * 50_000)]
    one = append_snapshot(b"", files=files, created_unix_ns=CREATED, chunker=small,
                          archive_id=ARCHIVE_ID)

    # Recorded, so a later writer can be held to it rather than guessing.
    plan = latest_snapshot(one).manifest["packing_plan"]
    assert plan["version"] == "anla-cdc-1" and plan["avg"] == 4096

    append_snapshot(one, files=files, created_unix_ns=CREATED + 1, chunker=small)
    with pytest.raises(InvalidInput, match="one chunking rule"):
        append_snapshot(one, files=files, created_unix_ns=CREATED + 1,
                        chunker=cdc_chunker())


def test_a_chunk_size_below_the_file_is_what_makes_deduplication_work():
    """Why the rule above matters, stated as a measurement.

    The pinned default has a 64 KiB floor, so a 36 KiB document is one chunk and an
    edit anywhere in it rewrites all of it. This is the property `--chunk-avg`
    exists for, pinned here so nobody 'simplifies' the flag away.
    """
    from anla.fastcdc import CdcProfile

    # LCG, not arithmetic. The first version of this test used `(i * 7919) % 251`
    # and failed, because on periodic input the gear fingerprint never satisfies the
    # boundary condition, every cut lands on `max_size`, and a smaller average makes
    # things *worse* rather than better. The warning about that is forty lines up in
    # this same file, which is the whole reason it is worth writing twice.
    state, buffer = 987654321, bytearray()
    for _ in range(36_000):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        buffer.append((state >> 16) & 0xFF)
    body = bytes(buffer)
    revised = body[:12_000] + b"a new paragraph\n" + body[12_000:]

    def cost(chunker) -> int:
        one = append_snapshot(b"", files=[SourceEntry.of("p.md", body)],
                              created_unix_ns=CREATED, chunker=chunker,
                              archive_id=ARCHIVE_ID)
        two = append_snapshot(one, files=[SourceEntry.of("p.md", revised)],
                              created_unix_ns=CREATED + 1, chunker=chunker)
        return len(two) - len(one)

    default_cost = cost(cdc_chunker())
    tuned_cost = cost(cdc_chunker(CdcProfile(min_size=1024, avg_size=4096,
                                             max_size=16384)))
    assert default_cost > len(body), "the default should store the whole file again"
    assert tuned_cost < default_cost / 2, (tuned_cost, default_cost)
