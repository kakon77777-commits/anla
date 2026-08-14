# -*- coding: utf-8 -*-
"""Archives that are internally consistent and still illegal.

Every other test that feeds a reader bad bytes corrupts them, and corruption is
caught by the payload hash. That is correct behaviour and it is also a blindfold:
the CBOR decoder, the canonical-form rules, the path rules and the root arithmetic
all sit *behind* a hash check, so a mutation-based test never executes them. The
differential fuzzer ran sixteen thousand mutants without reaching any of them.

The threat model that matters is not a corrupt disk. It is **a writer that is
lying** — an archive assembled by someone who computed every hash correctly over
content designed to do harm. These tests build exactly that, and they found two
real divergences between the two implementations the day they were written:

* a manifest whose `path` was not valid UTF-8 — Python raised an unhandled
  `UnicodeDecodeError` and exited 1, Rust answered `manifest-invalid` and exited 4;
* a manifest with no `path` member at all — Python called it an *unsafe path*,
  which is a security claim about a path that does not exist. Rust called it a
  missing member, and Rust was right.

Both are fixed. These keep them fixed.
"""

from __future__ import annotations

import pytest

from anla.errors import ManifestInvalid, UnsafeObject
from anla1 import container as C
from anla1.blake3 import blake3_256 as H
from anla1.cbor import decode, encode
from anla1.snapshot import SourceEntry, append_snapshot, verify_archive


def forge(edit) -> bytes:
    """Build an archive, rewrite its manifest, and repair every hash over it.

    `edit` receives the decoded manifest and mutates it in place. What comes back
    is an archive no integrity check can fault: the record's payload hash, its
    header CRC and the footer's own hash all describe the manifest that is actually
    there. Only the *rules* can refuse it, which is the point.
    """
    archive = append_snapshot(b"", files=[SourceEntry.of("hello.txt", b"x" * 40)],
                              created_unix_ns=1, archive_id=bytes(16))
    footer = C.find_latest_footer(archive)
    record = C.parse_record(archive, footer.manifest_offset)
    manifest = decode(archive[record.payload_offset:
                              record.payload_offset + record.payload_length])
    edit(manifest)
    payload = encode(manifest)
    header = dict(record.header)
    header["payload_hash"] = H(payload)
    rebuilt = C.build_record(record.type, header, payload, record.sequence, record.flags)

    # The footer is rebuilt rather than reused, because an edit that changes the
    # manifest's length moves it. The first version of this asserted the length was
    # unchanged instead, which quietly restricted every test to edits of exactly the
    # same size — and the one edit that could not be (deleting a member) failed on a
    # length mismatch while appearing to test path safety. A test fixture that can
    # only express same-size lies is not a hostile writer.
    tail = C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=footer.snapshot_sequence,
        manifest_offset=record.offset, manifest_length=len(rebuilt),
        preservation_root=footer.preservation_root,
        previous_footer_offset=footer.previous_footer_offset,
        auxiliary_root=footer.auxiliary_root, hash_algorithm=footer.hash_algorithm)
    data = bytes(archive[:record.offset]) + rebuilt + tail
    return C.with_footer_hint(data, record.offset + len(rebuilt))


def set_path(value):
    def edit(manifest):
        manifest["objects"][0]["path"] = value
    return edit


def test_the_forgery_really_is_internally_consistent():
    """The premise. Without it every test below could be passing on a broken hash.

    An unmodified round trip through `forge` must verify, which says the repair is
    complete — and then the *same* machinery with an illegal path must be refused
    for the path and nothing else.
    """
    untouched = forge(lambda manifest: None)
    verify_archive(untouched)  # raises if any hash, CRC or offset was left wrong


@pytest.mark.parametrize("path,why", [
    ("../aa.txt", "traversal"),
    ("/etc/pwd1", "absolute"),
    ("a\\bbb.txt", "a backslash a POSIX name may legitimately contain"),
    ("a/../b.tx", "traversal in the middle"),
    ("", "present but empty — a string, so a legality question, not a missing member"),
    ("a" + chr(0) + "b.txt", "an embedded NUL"),
])
def test_an_illegal_path_with_a_correct_hash_is_still_refused(path, why):
    """The security boundary, exercised the only way that reaches it."""
    with pytest.raises(UnsafeObject):
        verify_archive(forge(set_path(path)))


def test_a_missing_path_is_a_broken_manifest_not_an_unsafe_one():
    """Absence and illegality are different answers.

    `entry.get("path")` returns `None` when the member is gone, and handing that to
    the path validator reported a *security event* for a path that was never there.
    The two lead a caller to different places — one to an audit log, one to another
    copy of the archive — so the reader has to distinguish them.
    """
    def drop(manifest):
        del manifest["objects"][0]["path"]

    with pytest.raises(ManifestInvalid, match="has no path"):
        verify_archive(forge(drop))


@pytest.mark.parametrize("member", [
    "hash_algorithms", "preservation_root", "objects", "chunks", "archive_id",
    "anla_version", "optional_capabilities", "auxiliary_root",
])
def test_a_manifest_missing_any_required_member_is_refused_the_same_way(member):
    """Not one member — every one of them, because the bug was never about a member.

    `read_snapshot` cross-checks `manifest["hash_algorithms"]` against the record
    header *before* `verify_manifest` has confirmed anything is present, so a
    manifest without it raised `KeyError` and left the CLI as a traceback. Testing
    only that member would have fixed one subscript; the presence check now lives in
    `parse_manifest`, so no code downstream can be handed an incomplete manifest at
    all, and this parametrisation is what says so for every member rather than the
    one the fuzzer happened to delete.
    """
    def drop(manifest):
        del manifest[member]

    with pytest.raises(ManifestInvalid, match="missing required member"):
        verify_archive(forge(drop))


def test_a_path_that_is_not_utf_8_is_refused_by_the_decoder():
    """CBOR text must be valid UTF-8, and the decoder is what says so.

    This cannot be built through `encode`, which refuses to produce it — the bytes
    have to be corrupted after encoding and the hash repaired over the result,
    which is the same hostile-writer shape one level lower down.
    """
    archive = append_snapshot(b"", files=[SourceEntry.of("hello.txt", b"x" * 40)],
                              created_unix_ns=1, archive_id=bytes(16))
    record = C.parse_record(archive, C.find_latest_footer(archive).manifest_offset)
    payload = bytearray(archive[record.payload_offset:
                                record.payload_offset + record.payload_length])
    payload[payload.find(b"hello.txt") + 1] = 0xFF
    header = dict(record.header)
    header["payload_hash"] = H(bytes(payload))
    rebuilt = C.build_record(record.type, header, bytes(payload), record.sequence,
                             record.flags)
    data = bytearray(archive)
    span = ((record.unpadded_length + 7) // 8) * 8
    data[record.offset:record.offset + span] = rebuilt

    with pytest.raises(ManifestInvalid, match="not valid UTF-8"):
        verify_archive(bytes(data))
