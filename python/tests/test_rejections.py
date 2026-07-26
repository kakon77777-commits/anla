# -*- coding: utf-8 -*-
"""What a conforming decoder must refuse.

Half of a preservation format is what it accepts. The other half — the half that
decides whether "verified" means anything — is what it refuses. Each test here
forges an archive that is well formed at the frame level and wrong at exactly one
semantic level, and asserts the reader catches it.

The forge helper builds archives from parts using only the layout primitives, so
these tests do not inherit the writer's assumptions.
"""

from __future__ import annotations

import struct
import zlib

import pytest

from anla import Limits, PackPlan, SourceFile, SourceTree, open_archive, pack
from anla.canonical import canonical_bytes
from anla.errors import (
    IntegrityFailure,
    ManifestInvalid,
    ResourceLimitExceeded,
    UnsafeObject,
    UnsupportedCapability,
)
from anla.format import (
    FOOTER_SIZE,
    HEADER_SIZE,
    build_footer,
    build_header,
    build_record,
    crc32,
    parse_record,
    sha256_digest,
    sha256_hex,
    uuid_text,
)

UUID = bytes(range(16))


def forge(chunks, objects, *, manifest_patch=None, chunk_header_patch=None,
          uuid=UUID, created_ns=0, footer_manifest_offset=None):
    """Assemble an archive from explicit parts.

    *chunks* is a list of ``(chunk_id, codec, payload, raw_size)``; nothing is
    derived, so a test can state a wrong chunk id on purpose.
    """
    pieces = [build_header(uuid)]
    offset = HEADER_SIZE
    sequence = 1
    chunk_map = {}
    for chunk_id, codec, payload, raw_size in chunks:
        header = {"chunk_id": chunk_id, "raw_size": raw_size, "codec": codec,
                  "payload_sha256": sha256_hex(payload)}
        if chunk_header_patch:
            header = chunk_header_patch(dict(header))
        record = build_record("CHNK", header, payload, sequence)
        sequence += 1
        pieces.append(record)
        chunk_map[chunk_id] = {
            "record_offset": offset,
            "record_length": len(record),
            "payload_offset": offset + (len(record) - len(payload)),
            "payload_length": len(payload),
            "raw_size": raw_size,
            "codec": codec,
            "payload_sha256": sha256_hex(payload),
        }
        offset += len(record)

    manifest = {
        "format": "ANLA-MVP",
        "format_version": "0.1",
        "archive_uuid": uuid_text(uuid),
        "created_unix_ns": str(created_ns),
        "hash_algorithm": "sha256",
        "manifest_encoding": "canonical-json",
        "snapshot_sequence": 1,
        "source_name": "forged",
        "plan": PackPlan().as_manifest_member(),
        "preservation": {"lossless": True, "decoder_requires_ai": False,
                         "object_coverage": "all-selected-objects"},
        "objects": objects,
        "chunks": chunk_map,
        "statistics": {"objects": len(objects),
                       "files": sum(1 for o in objects if o.get("type") == "file"),
                       "directories": sum(1 for o in objects if o.get("type") == "directory"),
                       "unique_chunks": len(chunk_map), "chunk_references": 0,
                       "logical_bytes": 0, "stored_payload_bytes": 0},
        "auxiliary": {"decision_log": [], "disposable": True},
    }
    if manifest_patch:
        manifest = manifest_patch(manifest)

    payload = canonical_bytes(manifest)
    record = build_record("MANF", {"encoding": "canonical-json",
                                   "payload_sha256": sha256_hex(payload),
                                   "preservation_required": True}, payload, sequence)
    manifest_offset = offset
    pieces.append(record)
    pieces.append(build_footer(
        manifest_offset if footer_manifest_offset is None else footer_manifest_offset,
        len(record), uuid, sha256_digest(payload)))
    return b"".join(pieces)


def one_file_archive(content=b"hello world"):
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": chunk_id, "length": len(content)}], "metadata": {}}]
    return [(chunk_id, "store", content, len(content))], objects


def valid_archive():
    chunks, objects = one_file_archive()
    return forge(chunks, objects)


def test_the_forge_produces_something_valid():
    archive = open_archive(valid_archive())
    assert archive.read("a.txt") == b"hello world"


# ---------------------------------------------------------------------------
# T-HDR-1
# ---------------------------------------------------------------------------

def test_bad_bootstrap_magic():
    data = bytearray(valid_archive())
    data[3] = 0x42
    with pytest.raises(ManifestInvalid, match="bootstrap magic"):
        open_archive(bytes(data))


def test_unsupported_version():
    data = bytearray(valid_archive())
    struct.pack_into("<H", data, 10, 2)  # minor version 2
    struct.pack_into("<I", data, 60, crc32(bytes(data[:60])))  # keep the CRC honest
    with pytest.raises(ManifestInvalid, match="unsupported ANLA version"):
        open_archive(bytes(data))


def test_header_crc_mismatch():
    data = bytearray(valid_archive())
    data[20] ^= 0xFF  # inside the UUID, covered by the header CRC
    with pytest.raises(IntegrityFailure, match="header CRC"):
        open_archive(bytes(data))


def test_archive_shorter_than_header_plus_footer():
    with pytest.raises(ManifestInvalid, match="smaller than a header"):
        open_archive(b"ANLA" * 8)


# ---------------------------------------------------------------------------
# T-FTR-1, T-FTR-2
# ---------------------------------------------------------------------------

def test_bad_footer_magic():
    data = bytearray(valid_archive())
    data[len(data) - FOOTER_SIZE] = 0x00
    with pytest.raises(ManifestInvalid, match="footer magic"):
        open_archive(bytes(data))


def test_footer_crc_mismatch():
    data = bytearray(valid_archive())
    data[len(data) - FOOTER_SIZE + 20] ^= 0xFF
    with pytest.raises(IntegrityFailure, match="footer CRC"):
        open_archive(bytes(data))


def test_footer_uuid_mismatch():
    data = bytearray(valid_archive())
    base = len(data) - FOOTER_SIZE
    data[base + 32] ^= 0xFF
    struct.pack_into("<I", data, base + 92, crc32(bytes(data[base:base + 92])))
    with pytest.raises(IntegrityFailure, match="archive UUID"):
        open_archive(bytes(data))


def test_footer_pointing_at_a_chunk_record():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects, footer_manifest_offset=HEADER_SIZE)
    with pytest.raises(ManifestInvalid, match="MANF"):
        open_archive(data)


# ---------------------------------------------------------------------------
# T-MAN-1, T-MAN-2
# ---------------------------------------------------------------------------

def test_manifest_hash_mismatch():
    data = bytearray(valid_archive())
    # Flip a byte inside the manifest payload. The record header CRC covers the
    # record header, not the payload, so only the footer hash can catch this.
    index = data.rindex(b'"source_name":"forged"') + 16
    data[index] ^= 0x20
    with pytest.raises(IntegrityFailure, match="manifest SHA-256"):
        open_archive(bytes(data))


def test_manifest_declaring_another_format():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects,
                 manifest_patch=lambda m: {**m, "format_version": "0.2"})
    with pytest.raises(UnsupportedCapability, match="different format profile"):
        open_archive(data)


def test_manifest_uuid_not_matching_the_header():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects,
                 manifest_patch=lambda m: {**m, "archive_uuid": uuid_text(bytes(16))})
    with pytest.raises(IntegrityFailure, match="manifest UUID"):
        open_archive(data)


def test_manifest_missing_a_required_member():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects,
                 manifest_patch=lambda m: {k: v for k, v in m.items() if k != "preservation"})
    with pytest.raises(ManifestInvalid, match="missing required member"):
        open_archive(data)


# ---------------------------------------------------------------------------
# T-REC-1, T-REC-2
# ---------------------------------------------------------------------------

def test_record_header_crc_mismatch():
    data = bytearray(valid_archive())
    index = data.index(b'"chunk_id"')
    data[index + 2] ^= 0x20
    with pytest.raises(IntegrityFailure, match="record header CRC"):
        open_archive(bytes(data))


def test_unknown_record_type_where_a_chunk_was_promised():
    data = bytearray(valid_archive())
    data[HEADER_SIZE + 4:HEADER_SIZE + 8] = b"WHAT"
    with pytest.raises(ManifestInvalid, match="non-CHNK record"):
        open_archive(bytes(data))


def test_record_declaring_a_payload_past_the_end_of_the_archive():
    data = bytearray(valid_archive())
    struct.pack_into("<Q", data, HEADER_SIZE + 16, 1 << 40)
    with pytest.raises(ManifestInvalid, match="outside the archive"):
        open_archive(bytes(data))


def test_offset_beyond_the_safe_integer_range_is_refused_not_rounded():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects, footer_manifest_offset=(1 << 60))
    with pytest.raises((ManifestInvalid, ResourceLimitExceeded)):
        open_archive(data)


# ---------------------------------------------------------------------------
# T-SEQ-1..4 — found by differential fuzzing, not by reading
# ---------------------------------------------------------------------------

def _reseal(data: bytes, patch) -> bytes:
    """Rewrite a record frame field and re-emit nothing else.

    The sequence lives in the frame, which no CRC covers, so a mutant needs no
    repair to reach the semantic checks — which is exactly why the field went
    unvalidated for so long.
    """
    out = bytearray(data)
    patch(out)
    return bytes(out)


def test_record_sequence_of_zero_is_rejected():
    """T-SEQ-1."""
    data = _reseal(valid_archive(),
                   lambda out: struct.pack_into("<Q", out, HEADER_SIZE + 24, 0))
    with pytest.raises(ManifestInvalid, match="sequence must be at least 1"):
        open_archive(data)


def test_absurd_record_sequence_is_rejected():
    """T-SEQ-2. A JavaScript reader cannot represent this value at all; a Python
    reader can, and used to accept it. Differential fuzzing is what noticed."""
    data = _reseal(valid_archive(),
                   lambda out: struct.pack_into("<Q", out, HEADER_SIZE + 24, 2 ** 63))
    with pytest.raises(ManifestInvalid, match="sequence is out of range"):
        open_archive(data)


def test_manifest_sequence_must_be_chunks_plus_one():
    """T-SEQ-3: SPEC.md section 4.3 states the count as arithmetic, so it can be
    checked by a reader that jumps straight to the manifest."""
    data = bytearray(valid_archive())
    from anla.format import parse_footer, parse_header
    header = parse_header(bytes(data))
    footer = parse_footer(bytes(data), header)
    struct.pack_into("<Q", data, footer.manifest_record_offset + 24, 9)
    with pytest.raises(ManifestInvalid, match=r"len\(chunks\) \+ 1"):
        open_archive(bytes(data))


def test_two_chunk_records_may_not_share_a_sequence():
    """T-SEQ-4."""
    content_a, content_b = b"first chunk", b"second chunk"
    id_a, id_b = sha256_hex(content_a), sha256_hex(content_b)
    objects = [
        {"type": "file", "path": "a.txt", "size": len(content_a), "sha256": id_a,
         "chunks": [{"id": id_a, "length": len(content_a)}], "metadata": {}},
        {"type": "file", "path": "b.txt", "size": len(content_b), "sha256": id_b,
         "chunks": [{"id": id_b, "length": len(content_b)}], "metadata": {}},
    ]
    chunks = [(id_a, "store", content_a, len(content_a)),
              (id_b, "store", content_b, len(content_b))]
    data = bytearray(forge(chunks, objects))
    # Give the second chunk record the first one's sequence.
    second = parse_record(bytes(data), HEADER_SIZE)
    struct.pack_into("<Q", data, HEADER_SIZE + second.total_length + 24, 1)
    with pytest.raises(ManifestInvalid, match="share a sequence"):
        open_archive(bytes(data))


def test_the_frozen_vectors_all_satisfy_the_sequence_rule():
    """A rule that the format's own artifacts violate is a wrong rule."""
    from conftest import VECTORS
    for vector in sorted(VECTORS.glob("*.anla")):
        archive = open_archive(vector, full=False)
        assert archive.verification["status"] == "ok", vector.name


# ---------------------------------------------------------------------------
# T-CHK-1..4
# ---------------------------------------------------------------------------

def test_stored_chunk_payload_hash_mismatch():
    data = bytearray(valid_archive())
    index = data.index(b"hello world")
    data[index] = ord("H")
    with pytest.raises(IntegrityFailure, match="payload hash mismatch"):
        open_archive(bytes(data))


def test_raw_chunk_hash_must_match_the_content_id():
    """T-CHK-2: the chunk id is a claim about content, not a label."""
    content = b"hello world"
    wrong_id = sha256_hex(b"something else entirely")
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": wrong_id, "length": len(content)}], "metadata": {}}]
    data = forge([(wrong_id, "store", content, len(content))], objects)
    with pytest.raises(IntegrityFailure, match="raw chunk hash"):
        open_archive(data)


def test_chunk_descriptor_disagreeing_with_its_record():
    chunks, objects = one_file_archive()

    def patch(manifest):
        chunk_id = next(iter(manifest["chunks"]))
        manifest["chunks"][chunk_id]["record_length"] += 1
        return manifest

    with pytest.raises(IntegrityFailure, match="record length disagrees"):
        open_archive(forge(chunks, objects, manifest_patch=patch))


def test_chunk_record_header_disagreeing_with_the_descriptor():
    chunks, objects = one_file_archive()
    data = forge(chunks, objects,
                 chunk_header_patch=lambda h: {**h, "raw_size": h["raw_size"] + 1})
    with pytest.raises(IntegrityFailure, match="disagrees with the descriptor"):
        open_archive(data)


def test_unknown_codec():
    content = b"hello world"
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": chunk_id, "length": len(content)}], "metadata": {}}]
    data = forge([(chunk_id, "brotli", content, len(content))], objects)
    with pytest.raises(UnsupportedCapability, match="unsupported codec"):
        open_archive(data)


def test_chunk_id_that_is_not_lowercase_hex():
    content = b"hello world"
    bad_id = sha256_hex(content).upper()
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": bad_id, "length": len(content)}], "metadata": {}}]
    with pytest.raises(ManifestInvalid, match="lowercase 64-hex"):
        open_archive(forge([(bad_id, "store", content, len(content))], objects))


# ---------------------------------------------------------------------------
# T-COV-1
# ---------------------------------------------------------------------------

def test_chunk_coverage_must_add_up_to_the_declared_size():
    content = b"hello world"
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content) + 5,
                "sha256": sha256_hex(content),
                "chunks": [{"id": chunk_id, "length": len(content)}], "metadata": {}}]
    with pytest.raises(IntegrityFailure, match="coverage does not add up"):
        open_archive(forge([(chunk_id, "store", content, len(content))], objects))


def test_file_content_hash_mismatch():
    content = b"hello world"
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(b"a different file"),
                "chunks": [{"id": chunk_id, "length": len(content)}], "metadata": {}}]
    with pytest.raises(IntegrityFailure, match="file content hash"):
        open_archive(forge([(chunk_id, "store", content, len(content))], objects))


def test_chunk_reference_to_an_unknown_chunk():
    content = b"hello world"
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": "0" * 64, "length": len(content)}], "metadata": {}}]
    with pytest.raises(ManifestInvalid, match="unknown chunk"):
        open_archive(forge([(chunk_id, "store", content, len(content))], objects))


# ---------------------------------------------------------------------------
# T-PTH-1, T-PTH-2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "../escape.txt",
    "a/../../escape.txt",
    "/absolute.txt",
    "C:/windows.txt",
    "\\\\server\\share\\file.txt",
    "a//b.txt",
    "./relative.txt",
    "trailing/",
    "with\0nul.txt",
    "",
])
def test_unsafe_paths_are_rejected(path):
    content = b"x"
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": path, "size": 1, "sha256": sha256_hex(content),
                "chunks": [{"id": chunk_id, "length": 1}], "metadata": {}}]
    with pytest.raises(UnsafeObject):
        open_archive(forge([(chunk_id, "store", content, 1)], objects))


def test_duplicate_paths_are_rejected():
    content = b"x"
    chunk_id = sha256_hex(content)
    entry = {"type": "file", "path": "a.txt", "size": 1, "sha256": sha256_hex(content),
             "chunks": [{"id": chunk_id, "length": 1}], "metadata": {}}
    with pytest.raises(UnsafeObject, match="duplicate object path"):
        open_archive(forge([(chunk_id, "store", content, 1)], [entry, dict(entry)]))


def test_unsupported_object_type_is_rejected():
    objects = [{"type": "symbolic-link", "path": "link", "metadata": {}}]
    with pytest.raises(UnsupportedCapability, match="unsupported object type"):
        open_archive(forge([], objects))


def test_extraction_cannot_escape_the_destination(tmp_path):
    """The writer refuses unsafe paths, so this is the reader's own boundary."""
    from anla.format import safe_path
    with pytest.raises(UnsafeObject):
        safe_path("../outside.txt")


# ---------------------------------------------------------------------------
# T-BMB-1
# ---------------------------------------------------------------------------

def test_chunk_declaring_more_than_the_limit_is_refused_before_allocation():
    content = b"x" * 1024
    chunk_id = sha256_hex(content)
    objects = [{"type": "file", "path": "a.txt", "size": len(content),
                "sha256": sha256_hex(content),
                "chunks": [{"id": chunk_id, "length": len(content)}], "metadata": {}}]

    def patch(manifest):
        manifest["chunks"][chunk_id]["raw_size"] = 1 << 40
        return manifest

    data = forge([(chunk_id, "store", content, len(content))], objects,
                 manifest_patch=patch)
    with pytest.raises(ResourceLimitExceeded, match="per-chunk size limit"):
        open_archive(data, limits=Limits(max_chunk_uncompressed=1 << 20))


def test_compression_bomb_stops_while_decoding():
    """A deflate payload that expands far past its declared raw_size must be
    refused mid-stream, not after a gigabyte has been allocated."""
    bomb = zlib.compress(b"\0" * (8 * 1024 * 1024))
    declared = 1024
    fake_id = sha256_hex(b"\0" * declared)
    objects = [{"type": "file", "path": "bomb.bin", "size": declared,
                "sha256": fake_id,
                "chunks": [{"id": fake_id, "length": declared}], "metadata": {}}]
    data = forge([(fake_id, "deflate", bomb, declared)], objects)
    with pytest.raises(ResourceLimitExceeded, match="more bytes than it declares"):
        open_archive(data)


def test_too_many_objects_is_refused():
    tree = SourceTree(name="many", files=[
        SourceFile(f"f{i}.txt", str(i).encode()) for i in range(20)
    ])
    data = pack(tree).data
    with pytest.raises(ResourceLimitExceeded, match="more objects"):
        open_archive(data, limits=Limits(max_objects=5))


def test_output_byte_limit_is_refused():
    tree = SourceTree(name="big", files=[SourceFile("a.bin", b"x" * 4096)])
    data = pack(tree, PackPlan(chunk_size=1024, compression="store")).data
    with pytest.raises(ResourceLimitExceeded):
        open_archive(data, limits=Limits(max_output_bytes=2048))


def test_writer_refuses_an_unsafe_path_rather_than_sanitizing_it():
    tree = SourceTree(name="bad", files=[SourceFile("../escape.txt", b"x")])
    with pytest.raises(UnsafeObject):
        pack(tree)


def test_writer_refuses_a_plan_it_cannot_honour():
    from anla.errors import InvalidInput
    with pytest.raises(InvalidInput, match="preserve_mode"):
        pack(SourceTree(name="x"), PackPlan(preserve_mode=True))
    with pytest.raises(InvalidInput, match="chunk_size"):
        pack(SourceTree(name="x"), PackPlan(chunk_size=0))
