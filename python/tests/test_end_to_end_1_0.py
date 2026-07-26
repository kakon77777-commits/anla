# -*- coding: utf-8 -*-
"""A complete 1.0 archive, assembled and read back — the Milestone 0 coherence check.

The container has tests and the manifest has tests. This file asks the question
neither of them can: do the pieces fit? It writes a real archive out of the
primitives — header, `CHNK` records, `MANF`, `FOOT` — then reads it the way a
decoder would, from the tail inwards, and reassembles a file's bytes.

There is no writer API yet; that is Milestone 1. Assembling by hand here is
deliberate, because a smoke test that goes through the same convenience layer the
implementation uses can pass while the format itself does not hold together.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import IntegrityFailure  # noqa: E402
from anla1 import container as C  # noqa: E402
from anla1.cbor import encode  # noqa: E402
from anla1.manifest import (  # noqa: E402
    ChunkEntry,
    ObjectEntry,
    build_manifest,
    parse_manifest,
    verify_manifest,
    without_auxiliary,
)

ARCHIVE_ID = bytes(range(16))
HASH = "sha256"


def H(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


FILES = {
    "docs/readme.txt": b"ANLA 1.0 end to end\n",
    "data.bin": bytes(range(64)) * 3,
    "docs/copy.txt": b"ANLA 1.0 end to end\n",   # same content: one chunk, two files
    "empty.txt": b"",
}


def build_archive(*, auxiliary: list[dict] | None = None,
                  previous: bytes | None = None) -> bytes:
    """Header, one CHNK per unique chunk, one MANF, one FOOT."""
    data = C.build_header(ARCHIVE_ID)
    sequence = 1
    chunk_entries: list[ChunkEntry] = []
    seen: dict[bytes, ChunkEntry] = {}

    for path in sorted(FILES):
        payload = FILES[path]
        if not payload:
            continue                       # an empty file references no chunk
        chunk_id = H(payload)
        if chunk_id in seen:
            continue                       # deduplicated: written once
        offset = len(data)
        record = C.build_record(
            "CHNK",
            {"chunk_id": chunk_id, "codec_id": 0, "raw_size": len(payload),
             "payload_hash": H(payload)},
            payload, sequence)
        data += record
        parsed = C.parse_record(record, 0)
        entry = ChunkEntry(chunk_id=chunk_id, record_offset=offset,
                           record_length=len(record),
                           payload_offset=offset + parsed.payload_offset,
                           payload_length=len(payload), raw_size=len(payload),
                           codec_id=0, payload_hash=H(payload))
        seen[chunk_id] = entry
        chunk_entries.append(entry)
        sequence += 1

    objects = [ObjectEntry(kind="directory", path="docs")]
    for path in sorted(FILES):
        payload = FILES[path]
        objects.append(ObjectEntry(
            kind="regular-file", path=path, size=len(payload),
            content_hash=H(payload),
            chunks=(H(payload),) if payload else (),
            metadata={"mtime_ns": 1_700_000_000_000_000_000}))

    manifest = build_manifest(
        archive_id=ARCHIVE_ID, snapshot_sequence=1,
        created_unix_ns=1_785_000_000_000_000_000,
        objects=objects, chunks=chunk_entries, hasher=H, hash_algorithm=HASH,
        required_capabilities=["anla:core:objects:1", "anla:core:chunks:1",
                               "anla:core:snapshots:1", "anla:hash:sha256:1",
                               "anla:codec:store:1"],
        auxiliary=auxiliary or [],
        parent_snapshot=previous)

    payload = encode(manifest)
    manifest_offset = len(data)
    manifest_record = C.build_record(
        "MANF", {"hash_algorithm": HASH, "payload_hash": H(payload)}, payload, sequence)
    data += manifest_record
    sequence += 1

    footer_offset = len(data)
    data += C.build_footer_record(
        sequence=sequence, snapshot_sequence=1,
        manifest_offset=manifest_offset, manifest_length=len(manifest_record),
        preservation_root=manifest["preservation_root"],
        auxiliary_root=manifest["auxiliary_root"], hash_algorithm=HASH)
    return C.with_footer_hint(data, footer_offset)


def read_archive(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """Read it the way a decoder would: tail first, then verify, then extract."""
    header = C.parse_header(data)
    assert header.archive_uuid == ARCHIVE_ID

    footer = C.find_latest_footer(data)
    manifest_record = C.parse_record(data, footer.manifest_offset)
    assert manifest_record.type == "MANF"
    payload = data[manifest_record.payload_offset:
                   manifest_record.payload_offset + manifest_record.payload_length]
    if C.hash_bytes(payload, manifest_record.header["hash_algorithm"]) \
            != manifest_record.header["payload_hash"]:
        raise IntegrityFailure("manifest payload hash mismatch")

    manifest = parse_manifest(payload)
    verify_manifest(manifest, H)
    C.check_capabilities(manifest)

    # The footer's root must be the manifest's, or the footer is describing a
    # different snapshot than the one it points at.
    if footer.preservation_root != manifest["preservation_root"]:
        raise IntegrityFailure("footer and manifest disagree about preservation_root")

    restored: dict[str, bytes] = {}
    for entry in manifest["objects"]:
        if entry["kind"] != "regular-file":
            continue
        parts = []
        for chunk_id in entry["chunks"]:
            descriptor = manifest["chunks"][chunk_id]
            record = C.parse_record(data, descriptor["record_offset"])
            assert record.type == "CHNK"
            raw = data[descriptor["payload_offset"]:
                       descriptor["payload_offset"] + descriptor["payload_length"]]
            if H(raw) != chunk_id:
                raise IntegrityFailure("raw chunk hash does not match its content id")
            parts.append(raw)
        content = b"".join(parts)
        if H(content) != entry["content_hash"]:
            raise IntegrityFailure("file content hash mismatch", path=entry["path"])
        restored[entry["path"]] = content
    return manifest, restored


# ---------------------------------------------------------------------------

def test_a_complete_archive_round_trips():
    manifest, restored = read_archive(build_archive())
    assert restored == FILES


def test_identical_content_is_stored_once():
    manifest, _ = read_archive(build_archive())
    files = [o for o in manifest["objects"] if o["kind"] == "regular-file"]
    assert len(files) == 4
    # readme.txt and copy.txt share content, empty.txt has none: three files with
    # bytes, two distinct chunks.
    assert len(manifest["chunks"]) == 2


def test_an_empty_file_references_no_chunk():
    manifest, restored = read_archive(build_archive())
    empty = next(o for o in manifest["objects"] if o["path"] == "empty.txt")
    assert empty["chunks"] == [] and empty["size"] == 0
    assert restored["empty.txt"] == b""


def test_the_archive_is_byte_stable():
    """Same inputs, same bytes — the property everything else is measured against,
    and the one 1.0 must inherit from MVP."""
    assert build_archive() == build_archive()


def test_the_footer_and_manifest_must_agree_about_the_root():
    data = bytearray(build_archive())
    footer = C.find_latest_footer(bytes(data))
    # Rewrite the footer with a different preservation root, hashes repaired, so
    # only the cross-check can catch it.
    body = {"snapshot_sequence": 1, "manifest_offset": footer.manifest_offset,
            "manifest_length": footer.manifest_length,
            "preservation_root": bytes(32)}
    payload = encode(body)
    rebuilt = C.build_record(
        "FOOT", {"hash_algorithm": HASH, "payload_hash": H(payload)},
        payload, footer.record.sequence)
    forged = bytes(data[:footer.offset]) + rebuilt
    with pytest.raises(IntegrityFailure, match="disagree about preservation_root"):
        read_archive(forged)


def test_a_corrupted_chunk_payload_is_caught():
    data = bytearray(build_archive())
    manifest, _ = read_archive(bytes(data))
    descriptor = next(iter(manifest["chunks"].values()))
    data[descriptor["payload_offset"]] ^= 0xFF
    with pytest.raises(IntegrityFailure, match="raw chunk hash"):
        read_archive(bytes(data))


def test_an_unknown_required_capability_stops_the_read():
    """A reader must refuse an archive that needs something it does not have, even
    when every hash in it is perfect."""
    manifest_extra = build_archive()
    data = bytearray(manifest_extra)
    footer = C.find_latest_footer(bytes(data))
    record = C.parse_record(bytes(data), footer.manifest_offset)
    payload = bytes(data[record.payload_offset:
                         record.payload_offset + record.payload_length])
    manifest = parse_manifest(payload)
    manifest["required_capabilities"] = sorted(
        manifest["required_capabilities"] + ["anla:codec:zstd:rfc8878"])
    # Recompute nothing else: capabilities are not covered by preservation_root,
    # which is itself worth knowing — they are policy, not content.
    new_payload = encode(manifest)
    rebuilt = C.build_record("MANF", {"hash_algorithm": HASH,
                                      "payload_hash": H(new_payload)},
                             new_payload, record.sequence)
    forged = bytes(data[:footer.manifest_offset]) + rebuilt
    forged += C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=1,
        manifest_offset=footer.manifest_offset, manifest_length=len(rebuilt),
        preservation_root=manifest["preservation_root"],
        auxiliary_root=manifest["auxiliary_root"], hash_algorithm=HASH)
    from anla.errors import UnsupportedCapability
    with pytest.raises(UnsupportedCapability, match="capabilities this reader lacks"):
        read_archive(forged)


def test_stripping_the_intelligence_plane_leaves_every_file_identical():
    """The whole point, end to end rather than at the manifest level: rewrite the
    archive with the auxiliary plane emptied and extract the same bytes."""
    decisions = [{"chunk": 0, "codec": "store", "reason": "incompressible"},
                 {"chunk": 1, "codec": "store", "reason": "small"}]
    data = build_archive(auxiliary=decisions)
    manifest, before = read_archive(data)
    assert manifest["auxiliary"] == decisions

    stripped_manifest = without_auxiliary(manifest, H)
    payload = encode(stripped_manifest)
    footer = C.find_latest_footer(data)
    record = C.parse_record(data, footer.manifest_offset)
    rebuilt = C.build_record("MANF", {"hash_algorithm": HASH,
                                      "payload_hash": H(payload)},
                             payload, record.sequence)
    rewritten = data[:footer.manifest_offset] + rebuilt
    rewritten += C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=1,
        manifest_offset=footer.manifest_offset, manifest_length=len(rebuilt),
        preservation_root=stripped_manifest["preservation_root"],
        auxiliary_root=stripped_manifest["auxiliary_root"], hash_algorithm=HASH)

    after_manifest, after = read_archive(rewritten)
    assert after == before
    assert after_manifest["auxiliary"] == []
    assert after_manifest["preservation_root"] == manifest["preservation_root"]
    assert len(rewritten) < len(data)


def test_every_record_in_the_archive_is_a_type_the_reader_knows():
    records = list(C.walk_records(build_archive()))
    assert [C.record_disposition(r) for r in records] == ["known"] * len(records)
    assert [r.type for r in records][-2:] == ["MANF", "FOOT"]
    assert [r.sequence for r in records] == list(range(1, len(records) + 1))
