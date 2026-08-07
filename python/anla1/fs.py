# -*- coding: utf-8 -*-
"""The filesystem boundary for ANLA 1.0 — everything that knows about an OS.

`snapshot.py` deals in paths and bytes and has no idea where either came from.
This module is the only place that calls `os.walk`, `stat`, or `write_bytes`, which
is deliberate: the portable half of the format stays testable without a disk, and
the half that cannot be portable is small enough to read in one sitting.

Three things here are not conveniences.

**An unsupported entry is refused, not skipped.** A symbolic link, a device node or
a socket is something 1.0 cannot yet represent, and an archive that silently omitted
one would still be claiming `Extract(Pack(F, P)) = F`. Skipping is available, and it
costs an explicit flag *and* a non-zero exit code (`FidelityDegraded`, 11), so that
no script can treat a partial archive as a complete one by accident. The in-archive
fidelity report that would make this a recorded fact rather than an operator's
memory arrives with Milestone 2.

**A file that changes while it is being packed is an error.** Packing a tree that is
being written produces an archive of a moment that never existed. Each file is
re-`stat`ed after it is read and a changed size or mtime stops the pack.

**A name that cannot be stored unchanged is refused, not rewritten.** `safe_path`
returns a *normalized* path, and normalization is not identity: a POSIX file
genuinely named ``a\\b`` comes back as ``a/b``, which would restore as a file inside
a directory. So the scan compares before and after and refuses a difference. The
same rule catches the collision where two on-disk names map to one archive path.

On the way out the check is by device and inode instead, because the destination
filesystem folds names the source did not — Windows folds case, macOS folds NFC
against NFD — and one file quietly overwriting another is exactly the loss this
format exists to prevent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from anla.errors import FidelityDegraded, InvalidInput, UnsafeObject
from anla.globs import matches_any

from .manifest import check_object_path
from .snapshot import Snapshot, SourceEntry, extract_snapshot

__all__ = ["SourceTree", "RestoreReport", "scan_tree", "restore_tree"]


@dataclass
class SourceTree:
    root: str
    files: list[SourceEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    #: `{"path": ..., "kind": ..., "reason": ...}` for everything left out.
    skipped: list[dict] = field(default_factory=list)
    total_bytes: int = 0


def _archive_path(entry: Path, root: Path) -> str:
    """The portable name for an on-disk path, or a refusal.

    `check_object_path` is the manifest's own rule, used here so that the writer and
    the reader cannot disagree about what a legal path is — and it refuses a name it
    would have to change rather than storing the changed version.
    """
    return check_object_path(PurePosixPath(entry.relative_to(root).as_posix()).as_posix())


def _describe(entry: Path) -> str:
    if entry.is_symlink():
        return "symbolic link"
    if entry.is_dir():
        return "directory"
    if entry.is_file():
        return "regular file"
    return "special file"


def _opener(entry: Path, expected: os.stat_result):
    """Read the file, then check it did not move under us while we did."""
    def read() -> bytes:
        data = entry.read_bytes()
        after = entry.stat()
        if after.st_size != expected.st_size or after.st_mtime_ns != expected.st_mtime_ns:
            raise FidelityDegraded(
                "a file changed while it was being packed",
                path=str(entry),
                was={"size": expected.st_size, "mtime_ns": expected.st_mtime_ns},
                now={"size": after.st_size, "mtime_ns": after.st_mtime_ns})
        if len(data) != expected.st_size:
            raise FidelityDegraded("a file changed while it was being packed",
                                   path=str(entry), stat_size=expected.st_size,
                                   read_size=len(data))
        return data
    return read


def scan_tree(root: str | os.PathLike[str], *,
              exclude: Iterable[str] = (),
              allow_unsupported: bool = False,
              preserve_mtime: bool = True) -> SourceTree:
    """A directory on disk, as input for `append_snapshot`.

    Symbolic links are never followed. Following one turns a link into a second copy
    of its target, which changes what the archive means without saying so.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise InvalidInput("source must be an existing directory", source=str(root_path))
    patterns = tuple(exclude)
    tree = SourceTree(root=str(root_path))
    seen: dict[str, str] = {}

    def claim(archive_path: str, disk_path: Path) -> None:
        previous = seen.get(archive_path)
        if previous is not None:
            raise UnsafeObject(
                "two source names become the same archive path",
                path=archive_path, sources=[previous, str(disk_path)])
        seen[archive_path] = str(disk_path)

    def refuse_or_skip(entry: Path, archive_path: str) -> None:
        kind = _describe(entry)
        if not allow_unsupported:
            raise UnsafeObject(
                "1.0 cannot represent this entry, and omitting it silently would "
                "make the archive claim more than it contains",
                path=archive_path, kind=kind,
                hint="pass --skip-unsupported to leave it out deliberately")
        tree.skipped.append({"path": archive_path, "kind": kind,
                             "reason": "not representable in ANLA 1.0"})

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        dirnames.sort()
        filenames.sort()
        here = Path(dirpath)
        for name in list(dirnames):
            entry = here / name
            archive_path = _archive_path(entry, root_path)
            if matches_any(archive_path, patterns):
                dirnames.remove(name)
                continue
            if entry.is_symlink():
                refuse_or_skip(entry, archive_path)
                dirnames.remove(name)
                continue
            claim(archive_path, entry)
            tree.directories.append(archive_path)
        for name in filenames:
            entry = here / name
            archive_path = _archive_path(entry, root_path)
            if matches_any(archive_path, patterns):
                continue
            if entry.is_symlink() or not entry.is_file():
                refuse_or_skip(entry, archive_path)
                continue
            claim(archive_path, entry)
            stat = entry.stat()
            tree.files.append(SourceEntry(
                path=archive_path, read=_opener(entry, stat),
                mtime_ns=stat.st_mtime_ns,
                metadata={"mtime_ns": stat.st_mtime_ns} if preserve_mtime else {}))
            tree.total_bytes += stat.st_size

    tree.files.sort(key=lambda e: e.path.encode("utf-8"))
    tree.directories.sort(key=lambda p: p.encode("utf-8"))
    tree.skipped.sort(key=lambda s: s["path"])
    return tree


# ---------------------------------------------------------------------------
# restoring
# ---------------------------------------------------------------------------

@dataclass
class RestoreReport:
    destination: str
    files: int = 0
    directories: int = 0
    bytes_written: int = 0


def restore_tree(data: bytes, snapshot: Snapshot,
                 destination: str | os.PathLike[str], *,
                 overwrite: bool = False,
                 restore_mtime: bool = True) -> RestoreReport:
    """Write one snapshot to disk, after it has verified in full.

    `extract_snapshot` verifies every chunk and every file hash before this function
    creates anything, so a failure leaves the destination untouched rather than
    half-populated with bytes that turned out to be wrong.
    """
    restored = extract_snapshot(data, snapshot)
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = RestoreReport(destination=str(root))

    # Identity of everything written this run. A filesystem that cannot tell two
    # archive paths apart — Windows folds case, macOS folds NFC against NFD — would
    # otherwise let one file silently become the other.
    written: dict[tuple[int, int], str] = {}

    def target_for(path: str) -> Path:
        resolved = (root / check_object_path(path)).resolve()
        if resolved != root and root not in resolved.parents:
            raise UnsafeObject("object path escapes the destination", path=path)
        return resolved

    for entry in snapshot.manifest["objects"]:
        if entry["kind"] != "directory":
            continue
        target_for(entry["path"]).mkdir(parents=True, exist_ok=True)
        report.directories += 1

    for entry in sorted(snapshot.manifest["objects"], key=lambda e: e["path"]):
        if entry["kind"] != "regular-file":
            continue
        path = entry["path"]
        target = target_for(path)
        if target.exists():
            stat = target.stat()
            collided = written.get((stat.st_dev, stat.st_ino))
            if collided is not None:
                raise FidelityDegraded(
                    "two distinct archive paths collide on the target filesystem",
                    paths=[collided, path], target=str(target),
                    reason="the destination cannot represent both names distinctly")
            if not overwrite:
                raise UnsafeObject("destination file already exists", path=path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = restored[path]
        target.write_bytes(content)
        stat = target.stat()
        written[(stat.st_dev, stat.st_ino)] = path
        if restore_mtime and "mtime_ns" in entry.get("metadata", {}):
            mtime = entry["metadata"]["mtime_ns"]
            os.utime(target, ns=(mtime, mtime))
        report.files += 1
        report.bytes_written += len(content)
    return report
