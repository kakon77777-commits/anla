# -*- coding: utf-8 -*-
"""The 1.0 manifest and its roots — SPEC-1.0-DRAFT.md §5.

The test that matters is `test_emptying_the_intelligence_plane_cannot_move_the_
preservation_root`. It is the whitepaper's central claim, `D(P, I) = D(P, ∅)`,
reduced to one equality — which is the entire reason the roots are arranged the way
they are. MVP could only demonstrate the same property by rebuilding the manifest
and comparing what came out.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import IntegrityFailure, InvalidInput, ManifestInvalid  # noqa: E402
from anla1.cbor import decode, encode  # noqa: E402
from anla1.manifest import (  # noqa: E402
    ChunkEntry,
    ObjectEntry,
    build_manifest,
    compute_roots,
    object_id_for,
    verify_manifest,
    without_auxiliary,
)
from anla1.merkle import merkle_root  # noqa: E402


def H(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


ARCHIVE_ID = bytes(range(16))


def sample_objects() -> list[ObjectEntry]:
    return [
        ObjectEntry(kind="directory", path="docs"),
        ObjectEntry(kind="regular-file", path="docs/readme.txt", size=12,
                    content_hash=H(b"hello world\n"), chunks=(H(b"hello world\n"),),
                    metadata={"mtime_ns": 1_700_000_000_000_000_000}),
        ObjectEntry(kind="regular-file", path="data.bin", size=4,
                    content_hash=H(b"\x01\x02\x03\x04"), chunks=(H(b"\x01\x02\x03\x04"),)),
    ]


def sample_chunks() -> list[ChunkEntry]:
    return [
        ChunkEntry(chunk_id=H(b"hello world\n"), record_offset=64, record_length=96,
                   payload_offset=104, payload_length=12, raw_size=12, codec_id=0,
                   payload_hash=H(b"hello world\n")),
        ChunkEntry(chunk_id=H(b"\x01\x02\x03\x04"), record_offset=160, record_length=88,
                   payload_offset=200, payload_length=4, raw_size=4, codec_id=0,
                   payload_hash=H(b"\x01\x02\x03\x04")),
    ]


def sample_manifest(**overrides):
    kwargs = dict(
        archive_id=ARCHIVE_ID, snapshot_sequence=1, created_unix_ns=1_785_000_000_000_000_000,
        objects=sample_objects(), chunks=sample_chunks(), hasher=H,
        hash_algorithm="sha256",
        required_capabilities=["anla:core:objects:1", "anla:core:chunks:1"],
        auxiliary=[{"decision": "store", "chunk": 0, "reason": "already-compressed"},
                   {"decision": "store", "chunk": 1, "reason": "too-small"}],
    )
    kwargs.update(overrides)
    return build_manifest(**kwargs)


# ---------------------------------------------------------------------------
# the property the arrangement exists for
# ---------------------------------------------------------------------------

def test_emptying_the_intelligence_plane_cannot_move_the_preservation_root():
    """`D(P, I) = D(P, ∅)`, as one equality instead of an argument."""
    manifest = sample_manifest()
    assert manifest["auxiliary"], "the fixture must have an intelligence plane"

    stripped = without_auxiliary(manifest, H)
    assert stripped["auxiliary"] == []
    assert stripped["auxiliary_root"] != manifest["auxiliary_root"]
    assert stripped["auxiliary_root"] == merkle_root([], H)

    # The whole claim, checked in one line.
    assert stripped["preservation_root"] == manifest["preservation_root"]
    # And the three roots it is built from are untouched too.
    for name in ("objects_root", "chunks_root", "metadata_root"):
        assert stripped[name] == manifest[name]

    # A stripped manifest is still a valid manifest, not a manifest with a hole.
    verify_manifest(stripped, H)


def test_the_preservation_root_does_not_take_auxiliary_as_an_input():
    """Stated structurally, so the property above cannot pass by coincidence."""
    a = sample_manifest(auxiliary=[])
    b = sample_manifest(auxiliary=[{"anything": "at all"}])
    assert a["auxiliary_root"] != b["auxiliary_root"]
    assert a["preservation_root"] == b["preservation_root"]


def test_changing_an_object_does_move_the_preservation_root():
    """The other half: if the preservation root ignored real changes too, the test
    above would be worthless."""
    base = sample_manifest()
    changed = sample_manifest(objects=sample_objects()[:2])
    assert changed["objects_root"] != base["objects_root"]
    assert changed["preservation_root"] != base["preservation_root"]


def test_changing_a_chunk_descriptor_moves_the_preservation_root():
    base = sample_manifest()
    chunks = sample_chunks()
    moved = [ChunkEntry(**{**chunks[0].__dict__, "record_offset": 4096}), chunks[1]]
    changed = sample_manifest(chunks=moved)
    assert changed["chunks_root"] != base["chunks_root"]
    assert changed["preservation_root"] != base["preservation_root"]


# ---------------------------------------------------------------------------
# object identity
# ---------------------------------------------------------------------------

def test_object_id_covers_content_not_just_the_path():
    a = ObjectEntry(kind="regular-file", path="a.txt", size=1, content_hash=H(b"a"))
    b = ObjectEntry(kind="regular-file", path="a.txt", size=1, content_hash=H(b"b"))
    assert object_id_for(a, H) != object_id_for(b, H)


def test_object_id_is_stable_for_the_same_object():
    entry = sample_objects()[1]
    assert object_id_for(entry, H) == object_id_for(entry, H)


def test_metadata_participates_in_object_identity():
    without = ObjectEntry(kind="regular-file", path="a.txt", size=1, content_hash=H(b"a"))
    with_meta = ObjectEntry(kind="regular-file", path="a.txt", size=1,
                            content_hash=H(b"a"), metadata={"mtime_ns": 1})
    assert object_id_for(without, H) != object_id_for(with_meta, H)


def test_an_object_id_that_does_not_match_its_object_is_refused():
    manifest = sample_manifest()
    manifest["objects"][0]["path"] = "somewhere-else"
    with pytest.raises(IntegrityFailure, match="object_id does not match"):
        verify_manifest(manifest, H)


def test_duplicate_paths_are_refused_at_build_time():
    duplicated = sample_objects() + [ObjectEntry(kind="directory", path="docs")]
    with pytest.raises(InvalidInput, match="duplicate object path"):
        sample_manifest(objects=duplicated)


def test_duplicate_chunk_ids_are_refused_at_build_time():
    chunks = sample_chunks()
    with pytest.raises(InvalidInput, match="duplicate chunk id"):
        sample_manifest(chunks=chunks + [chunks[0]])


# ---------------------------------------------------------------------------
# roots against the manifest's own contents
# ---------------------------------------------------------------------------

def test_a_freshly_built_manifest_verifies():
    roots = verify_manifest(sample_manifest(), H)
    assert len(roots.preservation_root) == 32


@pytest.mark.parametrize("root_name", [
    "objects_root", "chunks_root", "metadata_root", "preservation_root",
    "auxiliary_root",
])
def test_a_tampered_root_is_refused(root_name):
    manifest = sample_manifest()
    manifest[root_name] = bytes(32)
    with pytest.raises(IntegrityFailure, match=root_name):
        verify_manifest(manifest, H)


def test_adding_an_object_without_updating_the_root_is_refused():
    """The check that makes a declared root worth declaring: without it, a root
    would only prove the manifest had not been edited, not that it describes what
    it claims to."""
    manifest = sample_manifest()
    extra = ObjectEntry(kind="regular-file", path="smuggled.txt", size=0)
    manifest["objects"].append(extra.as_manifest_entry(H))
    with pytest.raises(IntegrityFailure, match="objects_root"):
        verify_manifest(manifest, H)


@pytest.mark.parametrize("member", [
    "anla_version", "archive_id", "objects", "chunks", "preservation_root",
    "auxiliary_root", "hash_algorithms",
])
def test_a_missing_required_member_is_refused(member):
    manifest = sample_manifest()
    del manifest[member]
    with pytest.raises(ManifestInvalid, match="missing required member"):
        verify_manifest(manifest, H)


def test_an_unsupported_manifest_version_is_refused():
    manifest = sample_manifest()
    manifest["anla_version"] = [2, 0]
    with pytest.raises(ManifestInvalid, match="unsupported manifest version"):
        verify_manifest(manifest, H)


# ---------------------------------------------------------------------------
# determinism and encoding
# ---------------------------------------------------------------------------

def test_the_manifest_round_trips_through_canonical_cbor():
    manifest = sample_manifest()
    assert decode(encode(manifest)) == manifest


def test_the_encoding_is_byte_stable():
    """Two manifests built from the same inputs encode identically, which is what
    the footer's hash over them is worth."""
    assert encode(sample_manifest()) == encode(sample_manifest())


def test_object_order_in_the_manifest_does_not_depend_on_input_order():
    forward = sample_manifest(objects=sample_objects())
    backward = sample_manifest(objects=list(reversed(sample_objects())))
    assert encode(forward) == encode(backward)


def test_chunk_order_does_not_depend_on_input_order():
    forward = sample_manifest(chunks=sample_chunks())
    backward = sample_manifest(chunks=list(reversed(sample_chunks())))
    assert forward["chunks_root"] == backward["chunks_root"]


def test_absent_optional_members_are_omitted_not_null():
    manifest = sample_manifest()
    assert "parent_snapshot" not in manifest
    assert "packing_plan" not in manifest
    # And with them present, the digest is over the plan's canonical encoding.
    plan = {"compression": "zstd", "level": 9}
    with_plan = sample_manifest(parent_snapshot=bytes(32), packing_plan=plan)
    assert with_plan["parent_snapshot"] == bytes(32)
    assert with_plan["packing_plan_digest"] == H(encode(plan))


def test_an_empty_archive_still_has_every_root():
    manifest = sample_manifest(objects=[], chunks=[], auxiliary=[])
    roots = verify_manifest(manifest, H)
    empty = merkle_root([], H)
    assert roots.objects_root == roots.chunks_root == roots.metadata_root == empty
    assert roots.auxiliary_root == empty
    # preservation_root is still a hash over three roots, not the empty root.
    assert roots.preservation_root != empty


def test_roots_are_computed_from_contents_not_carried_over():
    """compute_roots is a pure function of what it is given, so a caller cannot
    accidentally inherit a root from a previous snapshot."""
    manifest = sample_manifest()
    recomputed = compute_roots(manifest["objects"], manifest["chunks"],
                               manifest["metadata"], manifest["auxiliary"], H)
    assert recomputed.preservation_root == manifest["preservation_root"]
