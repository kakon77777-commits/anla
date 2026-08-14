# -*- coding: utf-8 -*-
"""The two-field name model — whitepaper Q4, `design/q4-name-model.md`.

`path` is the portable name: always present, always UTF-8, always §5.2.1-safe.
`name` is the native bytes, present **only when they differ**. The absence rule is
the load-bearing one: it means `object_id` is unchanged for every object whose name
was already UTF-8, so answering question 4 invalidates no archive that never had
the question.
"""

from __future__ import annotations

import os

import pytest

from anla.errors import ManifestInvalid, UnsafeObject
from anla1.blake3 import blake3_256 as H
from anla1.fs import restore_tree
from anla1.manifest import (
    NATIVE_NAME_CAPABILITY, ObjectEntry, check_native_name, derive_path,
    native_name_for, object_id_for,
)
from anla1.snapshot import (
    SourceEntry, append_snapshot, extract_snapshot, list_snapshots, verify_archive,
)

#: Left column is what a filesystem hands you, right is what a person reads.
DERIVATIONS = [
    (b"hello.txt", "hello.txt"),
    ("café.txt".encode("utf-8"), "café.txt"),
    ("中文.txt".encode("utf-8"), "中文.txt"),
    (b"caf\xe9.txt", "caf%E9.txt"),          # latin-1, the classic
    (b"\xff\xfe.bin", "%FF%FE.bin"),         # not text in any encoding
    (b"a\x80b\x81c", "a%80b%81c"),           # continuation bytes with no lead
    (b"dir/caf\xe9.txt", "dir/caf%E9.txt"),  # the separator survives escaping
]


def pack(**kwargs):
    return append_snapshot(b"", created_unix_ns=1, archive_id=bytes(16), **kwargs)


@pytest.mark.parametrize("native,expected", DERIVATIONS)
def test_the_derivation_is_what_the_spec_says(native, expected):
    assert derive_path(native) == expected


@pytest.mark.parametrize("native,expected", DERIVATIONS)
def test_the_pair_reconstructs_the_original_bytes_exactly(native, expected):
    """The property the whole model exists for.

    Whichever field carries it, the bytes come back. This is the test that would
    fail if the `%XX` escaping and the `surrogateescape` decoding ever drifted apart
    — they are inverses by construction rather than by a table kept in step, and
    this says so for bytes no table would have thought to include.
    """
    path, name = native_name_for(native)
    assert path == expected
    recovered = name if name is not None else path.encode("utf-8")
    assert recovered == native


@pytest.mark.parametrize("native,expected", DERIVATIONS)
def test_name_is_present_exactly_when_it_is_not_redundant(native, expected):
    path, name = native_name_for(native)
    redundant = path.encode("utf-8") == native
    assert (name is None) is redundant, "a name that carries nothing must be omitted"


def test_object_id_is_unchanged_for_every_name_that_is_already_utf_8():
    """The reason `name` is absent when redundant, stated as an equality.

    Answering question 4 must not invalidate archives that never had the question.
    Emitting `name` unconditionally would have changed every object id ever written,
    to fix a case most archives do not contain.
    """
    for native, _ in DERIVATIONS:
        path, name = native_name_for(native)
        if name is not None:
            continue
        before = object_id_for(ObjectEntry(kind="regular-file", path=path), H)
        after = object_id_for(ObjectEntry(kind="regular-file", path=path, name=name), H)
        assert before == after, path


def test_a_native_name_changes_the_object_id_when_it_is_present():
    """The negative control for the test above.

    If `name` did not participate in identity, an archive could carry two different
    native names under one id and a reader could not tell which it verified.
    """
    plain = object_id_for(ObjectEntry(kind="regular-file", path="caf%E9.txt"), H)
    with_name = object_id_for(
        ObjectEntry(kind="regular-file", path="caf%E9.txt", name=b"caf\xe9.txt"), H)
    assert plain != with_name


# ---------------------------------------------------------------------------
# what is refused
# ---------------------------------------------------------------------------

def test_a_redundant_name_is_refused_rather_than_stored():
    """Two encodings of one archive is one encoding too many.

    A `name` equal to `path` encoded carries nothing, and allowing it would let two
    writers produce different bytes for the same tree — which is the property
    `tools/compare_writers.py` exists to check.
    """
    with pytest.raises(ManifestInvalid, match="carries nothing"):
        check_native_name(b"hello.txt", path="hello.txt")


def test_a_name_whose_derivation_is_not_the_path_is_refused():
    """The safety argument, and the reason the two fields are tied together.

    Without this, an archive could carry a harmless `path` and a traversing `name`:
    a reader that prefers `name` writes outside the destination, a reader that falls
    back writes inside it, and every hash verifies for both. Two conforming readers
    disagreeing about *where a file goes* is worse than either behaviour alone.
    """
    with pytest.raises(ManifestInvalid, match="not this name's derivation"):
        check_native_name(b"../escape.txt", path="harmless.txt")


def test_tying_them_together_is_what_makes_the_path_check_cover_the_name():
    """Stated as a test because it is an argument, and arguments rot.

    The derivation escapes undecodable bytes and never removes a `/` or a `.`, so a
    traversing name derives a traversing path — and that path is refused by the
    check §5.2.1 already required. The name needs no separate traversal rule, which
    is only true while the relation above holds.
    """
    for hostile in (b"../x.txt", b"/etc/passwd", b"a/../../b"):
        derived = derive_path(hostile)
        with pytest.raises(UnsafeObject):
            pack(files=[], objects=[ObjectEntry(kind="directory", path=derived,
                                                name=hostile)])


@pytest.mark.parametrize("bad,error", [
    ("a string, not bytes", ManifestInvalid),
    (b"", UnsafeObject),
    (42, ManifestInvalid),
])
def test_a_name_that_is_not_bytes_or_is_empty_is_refused(bad, error):
    with pytest.raises(error):
        check_native_name(bad, path="whatever.txt")


# ---------------------------------------------------------------------------
# through a whole archive
# ---------------------------------------------------------------------------

def test_the_capability_is_declared_only_when_an_archive_uses_it():
    """Optional, and absent when unused.

    Declaring it on every archive would tell a reader it needs something it does
    not, and the capability's whole purpose is to let a reader that lacks the
    feature decide for itself.
    """
    plain = list_snapshots(pack(files=[SourceEntry.of("a.txt", b"x")]))[-1]
    assert NATIVE_NAME_CAPABILITY not in plain.manifest["optional_capabilities"]

    native = list_snapshots(pack(
        files=[SourceEntry.of("caf%E9.txt", b"x")],
        native_names={"caf%E9.txt": b"caf\xe9.txt"}))[-1]
    assert NATIVE_NAME_CAPABILITY in native.manifest["optional_capabilities"]
    assert NATIVE_NAME_CAPABILITY not in native.manifest["required_capabilities"], \
        "a reader that ignores it can still restore every byte"


def test_an_archive_carrying_a_native_name_verifies_and_extracts():
    archive = pack(files=[SourceEntry.of("caf%E9.txt", b"contents")],
                   native_names={"caf%E9.txt": b"caf\xe9.txt"})
    verify_archive(archive)
    snapshot = list_snapshots(archive)[-1]
    assert extract_snapshot(archive, snapshot) == {"caf%E9.txt": b"contents"}
    entry, = [e for e in snapshot.manifest["objects"] if e["kind"] == "regular-file"]
    assert entry["name"] == b"caf\xe9.txt"


def test_restore_either_applies_the_native_name_or_reports_that_it_did_not(tmp_path):
    """The invariant that holds on every platform — and the only honest assertion.

    What actually happens here depends on the filesystem: on POSIX `os.fsdecode`
    recovers the byte through a surrogate and the file lands under its true name; on
    Windows the same call raises, because a name there is UTF-16 and `0xE9` is not
    valid UTF-8, so the file lands under `caf%E9.txt`. Asserting either outcome
    would make this test pass on one platform and fail on the other for reasons that
    are not defects.

    What must hold everywhere is that the reader did not go quiet: **the name was
    applied, or the report says it was not.** Neither is the failure — a reader that
    silently writes the escaped label has told its caller the archive contained
    something it did not.
    """
    archive = pack(files=[SourceEntry.of("caf%E9.txt", b"contents")],
                   native_names={"caf%E9.txt": b"caf\xe9.txt"})
    snapshot = list_snapshots(archive)[-1]
    report = restore_tree(archive, snapshot, tmp_path / "out")

    on_disk = {os.fsencode(p.name) for p in (tmp_path / "out").iterdir()}
    applied = b"caf\xe9.txt" in on_disk
    reported = any(r["path"] == "caf%E9.txt" for r in report.names_not_applied)

    assert applied != reported, (
        f"exactly one must be true — applied={applied} reported={reported}, "
        f"on disk: {on_disk}")
    if not applied:
        assert on_disk == {b"caf%E9.txt"}, "the fallback writes the portable label"


def can_create_a_non_utf_8_filename(where) -> bool:
    """Ask the filesystem, rather than guessing from `sys.platform`.

    This began as `skipif(sys.platform == "win32")` and was wrong on macOS, where
    `os.fsdecode` succeeds through a surrogate and then APFS refuses the write with
    `errno 92`. Two platforms refuse such a name for two different reasons at two
    different layers, and a third accepts it — which is more variety than a platform
    name can express. The probe costs one file.
    """
    try:
        probe = where / os.fsdecode(b"probe-\xe9")
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def test_a_tree_containing_a_non_utf_8_filename_packs_and_round_trips(tmp_path):
    """The case that used to kill the pack with a traceback, end to end."""
    from anla1.fs import scan_tree

    source = tmp_path / "src"
    source.mkdir()
    if not can_create_a_non_utf_8_filename(source):
        pytest.skip("this filesystem will not hold a name that is not valid UTF-8")
    (source / os.fsdecode(b"caf\xe9.txt")).write_bytes(b"contents")
    (source / "plain.txt").write_bytes(b"other")

    tree = scan_tree(source)
    assert tree.native_names == {"caf%E9.txt": b"caf\xe9.txt"}, \
        "only the name that needed it is carried"

    archive = append_snapshot(b"", **tree.as_source(), created_unix_ns=1,
                              archive_id=bytes(16))
    snapshot = list_snapshots(archive)[-1]
    report = restore_tree(archive, snapshot, tmp_path / "out")
    assert not report.names_not_applied, "this platform can represent the name"
    assert (tmp_path / "out" / os.fsdecode(b"caf\xe9.txt")).read_bytes() == b"contents"
