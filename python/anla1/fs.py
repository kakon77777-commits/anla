# -*- coding: utf-8 -*-
"""The filesystem boundary for ANLA 1.0 — everything that knows about an OS.

`snapshot.py` deals in paths and bytes and has no idea where either came from.
This module is the only place that calls `os.walk`, `stat`, or `write_bytes`, which
is deliberate: the portable half of the format stays testable without a disk, and
the half that cannot be portable is small enough to read in one sitting.

Four things here are not conveniences.

**An unsupported entry is refused, not skipped.** A device node, a socket or a FIFO
is something 1.0 cannot represent, and an archive that silently omitted one would
still be claiming `Extract(Pack(F, P)) = F`. Skipping costs an explicit flag, a
non-zero exit code (`FidelityDegraded`, 11), *and* an entry in the archive's own
fidelity report — so the omission outlives the terminal it was announced in.

**A symbolic link is stored, with its target exactly as the OS gave it.** Whether
one may be *created* is a restore-time decision, taken where creating it is what
makes it dangerous.

**Metadata is namespaced, and only recorded where it is true.** `posix.mode` is
written on POSIX and nowhere else: a synthetic mode on Windows would store a fact
that never held, and a reader cannot tell an invented value from an observed one.
That is also why the same tree packs to different bytes on different platforms, and
why `preserve_posix=False` exists for the case where content and names are what you
mean to compare.

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

from .manifest import ObjectEntry, check_object_path, sorted_by_path
from .snapshot import Snapshot, SourceEntry, extract_snapshot

__all__ = ["SourceTree", "RestoreReport", "scan_tree", "restore_tree"]


@dataclass
class SourceTree:
    root: str
    files: list[SourceEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    #: Symbolic links and any other object that carries no chunks.
    objects: list[ObjectEntry] = field(default_factory=list)
    #: The fidelity report: `{"path": ..., "reason": ..., "kind": ...}` for every
    #: entry the writer could not keep. Goes *into the archive*, not just into a
    #: terminal — an operator told once, on the day, is not a record.
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


def _metadata(stat: os.stat_result, preserve_mtime: bool,
              preserve_posix: bool = True) -> dict[str, dict]:
    """Namespaced metadata for one object.

    `common` holds what every platform agrees about. `posix` holds the permission
    bits and is only recorded where they mean something — writing a synthetic `mode`
    on Windows would store a fact that was never true, and a reader has no way to
    tell an invented value from an observed one.
    """
    metadata: dict[str, dict] = {}
    if preserve_mtime:
        metadata["common"] = {"mtime_ns": stat.st_mtime_ns}
    if preserve_posix and os.name == "posix":
        metadata["posix"] = {"mode": stat.st_mode & 0o7777}
    return metadata


def _link_entry(entry: Path, archive_path: str, preserve_mtime: bool) -> ObjectEntry:
    """A symbolic link, stored with its target exactly as the OS gave it.

    Bytes, not a path: a link target is not a name in the archive's namespace, it is
    an opaque string the *target* filesystem interprets. It may be absolute, may
    escape the tree, may point at nothing. Normalizing it would store a different
    link — the same mistake as rewriting `a\\b` into `a/b`, with worse consequences,
    because this one is followed.

    Nothing is resolved and nothing is validated here. Whether such a link may be
    *created* is a question for restore, where creating it is what makes it matter.
    """
    raw = os.readlink(entry)
    target = raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else raw
    stat = entry.lstat()
    return ObjectEntry(kind="symbolic-link", path=archive_path, target=target,
                       metadata={"common": {"mtime_ns": stat.st_mtime_ns}}
                       if preserve_mtime else {})


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
              preserve_mtime: bool = True,
              preserve_posix: bool = True) -> SourceTree:
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
        # `reason` comes from a closed set so the report can be summarised; `kind`
        # carries the detail. Free text in both would make a hundred entries
        # unreadable, which for a record of absence means unread.
        tree.skipped.append({"path": archive_path, "kind": kind,
                             "reason": "kind-not-representable"})

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
                # A link to a directory is a link, not a directory. Walking into it
                # would put the target's contents in the archive under this name.
                claim(archive_path, entry)
                tree.objects.append(_link_entry(entry, archive_path, preserve_mtime))
                dirnames.remove(name)
                continue
            claim(archive_path, entry)
            tree.directories.append(archive_path)
        for name in filenames:
            entry = here / name
            archive_path = _archive_path(entry, root_path)
            if matches_any(archive_path, patterns):
                continue
            if entry.is_symlink():
                claim(archive_path, entry)
                tree.objects.append(_link_entry(entry, archive_path, preserve_mtime))
                continue
            if not entry.is_file():
                refuse_or_skip(entry, archive_path)
                continue
            claim(archive_path, entry)
            stat = entry.stat()
            tree.files.append(SourceEntry(
                path=archive_path, read=_opener(entry, stat),
                mtime_ns=stat.st_mtime_ns,
                metadata=_metadata(stat, preserve_mtime, preserve_posix)))
            tree.total_bytes += stat.st_size

    tree.files = sorted_by_path(tree.files)
    tree.directories = sorted_by_path(tree.directories, lambda p: p)
    tree.objects = sorted_by_path(tree.objects)
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
    links: int = 0
    bytes_written: int = 0
    #: Namespaces present in the archive that this run could not apply — a
    #: *different* fact from the archive's own fidelity report, and one only the
    #: reader can know. "Not stored" is a loss; "stored, not applied" is a limit of
    #: this machine, and conflating them throws away whether the data still exists.
    metadata_not_applied: dict[str, int] = field(default_factory=dict)


def _note_unapplied(entry: dict, report: RestoreReport, *, applied: set[str]) -> None:
    """Count namespaces this run carried but could not use.

    Not an error and not a warning: the data is in the archive, intact and verified,
    and some other machine can apply it. Recorded so the caller can tell that from
    the case where the writer never stored it at all.
    """
    for namespace in entry.get("metadata", {}):
        if namespace not in applied:
            report.metadata_not_applied[namespace] = \
                report.metadata_not_applied.get(namespace, 0) + 1


def _restore_link(entry: dict, target: Path, root: Path, *,
                  overwrite: bool, allow_external: bool) -> None:
    """Create one symbolic link, or refuse to.

    The archive stores what the link said. Creating it is a separate decision, and
    the dangerous one: a target that is absolute or climbs out of the destination
    turns an extracted archive into a way to reach the rest of the filesystem. So it
    is refused here rather than sanitised at pack time — sanitising would have made
    the archive an inaccurate record of the tree, and the record is the point.
    """
    raw = entry["target"]
    text = raw.decode("utf-8", "surrogateescape")
    landing = (target.parent / text)
    escapes = PurePosixPath(text).is_absolute() or (len(text) > 1 and text[1] == ":")
    if not escapes:
        try:
            escapes = root != landing.resolve() and root not in landing.resolve().parents
        except OSError:                       # a target that cannot even be resolved
            escapes = True
    if escapes and not allow_external:
        raise UnsafeObject(
            "the link points outside the destination", path=entry["path"],
            target=text,
            hint="pass --allow-external-links if that is what you meant to restore")
    if target.is_symlink() or target.exists():
        if not overwrite:
            raise UnsafeObject("destination already exists", path=entry["path"])
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(text)
    except (OSError, NotImplementedError) as exc:
        raise FidelityDegraded(
            "this system will not create symbolic links, so the link was not "
            "restored — it is still in the archive",
            path=entry["path"], target=text, detail=str(exc)) from exc


def restore_tree(data: bytes, snapshot: Snapshot,
                 destination: str | os.PathLike[str], *,
                 overwrite: bool = False,
                 restore_mtime: bool = True,
                 allow_external_links: bool = False) -> RestoreReport:
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
        if entry["kind"] == "symbolic-link":
            _restore_link(entry, target_for(entry["path"]), root,
                          overwrite=overwrite,
                          allow_external=allow_external_links)
            report.links += 1
            _note_unapplied(entry, report, applied={"common"})
            continue
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
        applied = set()
        metadata = entry.get("metadata", {})
        posix = metadata.get("posix", {})
        if os.name == "posix" and "mode" in posix:
            os.chmod(target, posix["mode"])
            applied.add("posix")
        common = metadata.get("common", {})
        if restore_mtime and "mtime_ns" in common:
            os.utime(target, ns=(common["mtime_ns"], common["mtime_ns"]))
            applied.add("common")
        elif not restore_mtime:
            applied.add("common")          # declined, not unable
        _note_unapplied(entry, report, applied=applied)
        report.files += 1
        report.bytes_written += len(content)
    return report
