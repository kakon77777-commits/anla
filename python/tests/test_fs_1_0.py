# -*- coding: utf-8 -*-
"""The filesystem boundary for 1.0 — `python/anla1/fs.py`.

Until this module existed, nothing had put a real filesystem path into a 1.0
archive, so nothing had needed to say what a legal one is. Half of this file is
therefore about names rather than bytes: which ones the format can store, which ones
it must refuse, and the distinction between refusing a name and quietly storing a
different one.

The round trips use a real directory on a real disk on purpose. An in-memory test
cannot tell you that Windows folded a case or that macOS folded a normalization, and
those are the two failures that lose a file while every hash still verifies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import FidelityDegraded, UnsafeObject  # noqa: E402
from anla1.fs import restore_tree, scan_tree  # noqa: E402
from anla1.manifest import check_object_path  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    SourceEntry,
    append_snapshot,
    latest_snapshot,
    list_snapshots,
)

ARCHIVE_ID = bytes(range(16))
CREATED = 1_785_000_000_000_000_000


def make_tree(root: Path) -> dict[str, bytes]:
    """A small tree with the cases that matter: shared content, nesting, empty."""
    files = {
        "readme.txt": b"anla 1.0 on disk\n",
        "docs/guide.md": b"# guide\n",
        "docs/copy.md": b"# guide\n",          # identical: one chunk, two files
        "data/empty": b"",
        "data/blob.bin": bytes(range(256)) * 40,
    }
    for name, payload in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return files


def pack(root: Path, **kwargs) -> bytes:
    tree = scan_tree(root, **kwargs)
    return append_snapshot(b"", files=tree.files, directories=tree.directories,
                           created_unix_ns=CREATED, archive_id=ARCHIVE_ID)


def symlink_or_skip(link: Path, target: Path) -> None:
    """Skip only where symlinks genuinely need a privilege — never on POSIX.

    A blanket `except OSError: skip` would make these tests vanish silently on a
    platform where they should run, and a skipped test is indistinguishable from a
    passing one in a green summary. On POSIX a failure here is a failure.
    """
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        pytest.skip("Windows without developer mode cannot create a symbolic link")


# ---------------------------------------------------------------------------
# round trips
# ---------------------------------------------------------------------------

def test_a_directory_round_trips_through_disk(tmp_path):
    source, destination = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    files = make_tree(source)

    data = pack(source)
    report = restore_tree(data, latest_snapshot(data), destination)

    assert report.files == len(files)
    for name, payload in files.items():
        assert (destination / name).read_bytes() == payload
    # And nothing extra: the restored tree is the packed tree, not a superset.
    restored = {str(p.relative_to(destination)).replace(os.sep, "/")
                for p in destination.rglob("*") if p.is_file()}
    assert restored == set(files)


def test_identical_files_on_disk_share_one_chunk(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    make_tree(source)
    snapshot = latest_snapshot(pack(source))
    guide = [e for e in snapshot.manifest["objects"] if e["path"] == "docs/guide.md"][0]
    copy = [e for e in snapshot.manifest["objects"] if e["path"] == "docs/copy.md"][0]
    assert guide["chunks"] == copy["chunks"]


def test_modification_times_survive(tmp_path):
    source, destination = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    (source / "a.txt").write_bytes(b"timed\n")
    when = 1_600_000_000_000_000_000
    os.utime(source / "a.txt", ns=(when, when))

    data = pack(source)
    restore_tree(data, latest_snapshot(data), destination)
    assert (destination / "a.txt").stat().st_mtime_ns == when


def test_excluded_paths_are_not_packed(tmp_path):
    source = tmp_path / "src"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (source / "keep.txt").write_bytes(b"keep\n")

    snapshot = latest_snapshot(pack(source, exclude=[".git", ".git/**"]))
    assert {e["path"] for e in snapshot.manifest["objects"]} == {"keep.txt"}


def test_a_second_snapshot_of_a_changed_tree_stores_only_the_change(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    make_tree(source)
    one = pack(source)

    (source / "readme.txt").write_bytes(b"anla 1.0 on disk, revised\n")
    tree = scan_tree(source)
    two = append_snapshot(one, files=tree.files, directories=tree.directories,
                          created_unix_ns=CREATED + 1)

    snapshots = list_snapshots(two)
    assert [s.sequence for s in snapshots] == [1, 2]
    # The 10 KB blob is not stored twice; the growth is one small chunk plus metadata.
    assert len(two) - len(one) < 4096


def test_recorded_metadata_is_part_of_what_reproducible_means(tmp_path):
    """Two trees with the same names and content but different mtimes are two
    different archives, and that is correct.

    Recorded metadata is something the archive preserves, so it belongs in the hash.
    The consequence is that "reproducible given the same input" has to include the
    metadata: same names, same content, same recorded metadata, fixed `(uuid,
    created_ns)`. CI learned this the hard way — a cross-platform digest check
    compared six archives of six different inputs, because a checkout stamps mtimes
    with the moment it ran, and reported six different digests from one writer.
    """
    def build(root: Path, when: int, **kwargs) -> bytes:
        root.mkdir()
        (root / "a.txt").write_bytes(b"same content\n")
        os.utime(root / "a.txt", ns=(when, when))
        return pack(root, **kwargs)

    early = build(tmp_path / "early", 1_600_000_000_000_000_000)
    late = build(tmp_path / "late", 1_700_000_000_000_000_000)
    assert early != late, "mtime is recorded, so it must change the archive"

    without_early = build(tmp_path / "e2", 1_600_000_000_000_000_000, preserve_mtime=False)
    without_late = build(tmp_path / "l2", 1_700_000_000_000_000_000, preserve_mtime=False)
    assert without_early == without_late, "with no metadata recorded, only content counts"


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------

def test_a_path_that_would_have_to_be_rewritten_is_refused():
    """Refusing a name is not the same as storing a changed one.

    `safe_path` *returns* a normalized path, and normalization is not identity —
    it turns backslashes into separators. A POSIX file genuinely named `a\\b` would
    be stored as `a/b` and restored as a file inside a directory, so the tree that
    came out would not be the tree that went in while every hash still verified.
    """
    for bad in ("a\\b", "/absolute", "../escape", "a/./b", "a//b", "C:/drive", ""):
        with pytest.raises(UnsafeObject):
            check_object_path(bad)
    for good in ("a", "a/b", "docs/guide.md", "resumé.txt", "深/路徑.txt"):
        assert check_object_path(good) == good


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows cannot create a filename containing a backslash")
def test_a_backslash_in_a_posix_filename_is_refused_by_the_scanner(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a\\b").write_bytes(b"one file, not two\n")
    with pytest.raises(UnsafeObject, match="not stored in normalized form"):
        scan_tree(source)


def test_an_unsafe_path_cannot_be_written_into_an_archive():
    """The writer's own check, so a bad path becomes an error and not an artifact."""
    with pytest.raises(UnsafeObject):
        append_snapshot(b"", files=[SourceEntry.of("../escape", b"x")],
                        created_unix_ns=CREATED, archive_id=ARCHIVE_ID)


# ---------------------------------------------------------------------------
# what the scanner refuses
# ---------------------------------------------------------------------------

def test_a_symlink_is_refused_rather_than_skipped(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "real.txt").write_bytes(b"real\n")
    symlink_or_skip(source / "link.txt", source / "real.txt")
    with pytest.raises(UnsafeObject, match="cannot represent"):
        scan_tree(source)


def test_a_symlink_can_be_left_out_deliberately(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "real.txt").write_bytes(b"real\n")
    symlink_or_skip(source / "link.txt", source / "real.txt")

    tree = scan_tree(source, allow_unsupported=True)
    assert [s["path"] for s in tree.skipped] == ["link.txt"]
    assert [e.path for e in tree.files] == ["real.txt"]


def test_a_symlink_is_never_followed(tmp_path):
    """Following one turns a link into a copy of its target, which changes what the
    archive means without saying so."""
    source, outside = tmp_path / "src", tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"not part of the tree\n")
    symlink_or_skip(source / "elsewhere", outside)

    tree = scan_tree(source, allow_unsupported=True)
    assert not tree.files
    assert [s["path"] for s in tree.skipped] == ["elsewhere"]


def test_a_file_that_changes_while_being_packed_is_refused(tmp_path):
    """Packing a tree that is being written produces an archive of a moment that
    never existed."""
    source = tmp_path / "src"
    source.mkdir()
    target = source / "moving.txt"
    target.write_bytes(b"before\n")

    tree = scan_tree(source)
    target.write_bytes(b"after, and longer\n")     # between the scan and the read
    with pytest.raises(FidelityDegraded, match="changed while it was being packed"):
        append_snapshot(b"", files=tree.files, created_unix_ns=CREATED,
                        archive_id=ARCHIVE_ID)


# ---------------------------------------------------------------------------
# restoring
# ---------------------------------------------------------------------------

def test_restore_refuses_to_overwrite_by_default(tmp_path):
    source, destination = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    (source / "a.txt").write_bytes(b"archived\n")
    data = pack(source)

    destination.mkdir()
    (destination / "a.txt").write_bytes(b"already here\n")
    with pytest.raises(UnsafeObject, match="already exists"):
        restore_tree(data, latest_snapshot(data), destination)
    assert (destination / "a.txt").read_bytes() == b"already here\n"

    restore_tree(data, latest_snapshot(data), destination, overwrite=True)
    assert (destination / "a.txt").read_bytes() == b"archived\n"


def test_nothing_is_written_when_the_archive_does_not_verify(tmp_path):
    """Verification happens before the first file is created, so a bad archive
    leaves the destination untouched instead of half-populated with wrong bytes."""
    from anla.errors import IntegrityFailure

    source, destination = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    make_tree(source)
    data = bytearray(pack(source))

    snapshot = latest_snapshot(bytes(data))
    descriptor = snapshot.manifest["chunks"][sorted(snapshot.manifest["chunks"])[0]]
    data[descriptor["payload_offset"]] ^= 0xFF

    corrupted = bytes(data)
    with pytest.raises(IntegrityFailure):
        restore_tree(corrupted, latest_snapshot(corrupted), destination)
    assert not any(destination.rglob("*")) if destination.exists() else True
