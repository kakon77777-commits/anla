# -*- coding: utf-8 -*-
"""The ``anla1`` command line interface — ANLA 1.0 (draft).

Separate binary from ``anla`` rather than a flag on it, for the same reason 1.0 has
its own magic number: they are different formats, and a single command that switches
between them on a flag invites an archive written under one profile and read under
the other.

Every subcommand takes ``--json``, because the first-class caller of this tool is an
agent rather than a person, and exit codes come from :mod:`anla.errors` — the
whitepaper's table, shared with MVP, so a failure is classifiable without reading
prose. Two of them are worth knowing here: **9** is an unsafe or unrepresentable
object and **11** is fidelity degraded, which is what a deliberately incomplete pack
returns even though it produced an archive.

``pack`` and ``append`` accept ``--uuid`` and ``--created-ns`` so that two writers
can be handed the same inputs and compared byte for byte. That is not a debugging
convenience: it is the only way the freeze rule can ever be satisfied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anla.errors import AnlaError, InvalidInput

from . import __draft__, __profile__
from .container import CORE_HASH, HASHES
from .fs import restore_tree, scan_tree
from .manifest import fidelity_of
from .snapshot import (
    append_snapshot,
    cdc_chunker,
    diff,
    list_snapshots,
    single_chunk,
    verify_archive,
)

PROGRAM = "anla1"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _emit(payload: dict, as_json: bool, lines: list[str]) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for line in lines:
            print(line)


def _uuid_arg(value: str | None) -> bytes | None:
    if value is None:
        return None
    try:
        raw = bytes.fromhex(value.replace("-", "").strip())
    except ValueError as exc:
        raise InvalidInput("--uuid must be 16 bytes of hex", value=value) from exc
    if len(raw) != 16:
        raise InvalidInput("--uuid must be 16 bytes of hex", value=value)
    return raw


def _new_uuid() -> bytes:
    import uuid

    return uuid.uuid4().bytes


def _created_ns(value: int | None) -> int:
    if value is not None:
        return value
    import time

    return time.time_ns()


def _chunker(name: str):
    return cdc_chunker() if name == "cdc" else single_chunk


def _read(path: str) -> bytes:
    return Path(path).read_bytes()


def _pick(archive: bytes, sequence: int | None):
    """One snapshot by number, or the newest.

    Always via `list_snapshots`, never `find_latest_footer` alone, so that every
    lineage rule in §6.3 has been evaluated before anything is reported — a command
    that answered from the newest footer would report a chain it never checked.
    """
    snapshots = list_snapshots(archive)
    if sequence is None:
        return snapshots[-1], snapshots
    for snapshot in snapshots:
        if snapshot.sequence == sequence:
            return snapshot, snapshots
    raise InvalidInput("no such snapshot", requested=sequence,
                       available=[s.sequence for s in snapshots])


def _write_out(path: str, data: bytes, force: bool) -> None:
    target = Path(path)
    if target.exists() and not force:
        raise InvalidInput("output already exists; pass --force to replace it",
                           path=str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _skip_payload(tree) -> tuple[list[dict], int]:
    return tree.skipped, 11 if tree.skipped else 0


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_pack(args: argparse.Namespace) -> int:
    tree = scan_tree(args.source, exclude=args.exclude or (),
                     allow_unsupported=args.skip_unsupported,
                     preserve_mtime=not args.no_mtime)
    data = append_snapshot(
        b"", files=tree.files, directories=tree.directories,
        objects=tree.objects, fidelity=tree.skipped,
        created_unix_ns=_created_ns(args.created_ns),
        chunker=_chunker(args.chunking),
        hash_algorithm=args.hash,
        archive_id=_uuid_arg(args.uuid) or _new_uuid())
    _write_out(args.output, data, args.force)
    report = verify_archive(data)
    skipped, code = _skip_payload(tree)
    files = sum(1 for e in report.snapshots[-1].manifest["objects"]
                if e["kind"] == "regular-file")
    _emit({"archive": args.output, "bytes": len(data), "snapshot": 1,
           "files": files,
           "links": sum(1 for e in report.snapshots[-1].manifest["objects"]
                        if e["kind"] == "symbolic-link"),
           "chunks": report.unique_chunks, "hash": args.hash,
           "chunking": args.chunking, "skipped": skipped},
          args.json,
          [f"packed {args.source} -> {args.output}",
           f"  {len(data)} bytes, {report.unique_chunks} chunks, snapshot 1"]
          + [f"  skipped {s['path']} ({s['kind']})" for s in skipped])
    return code


def cmd_append(args: argparse.Namespace) -> int:
    existing = _read(args.archive)
    before = len(existing)
    tree = scan_tree(args.source, exclude=args.exclude or (),
                     allow_unsupported=args.skip_unsupported,
                     preserve_mtime=not args.no_mtime)
    data = append_snapshot(
        existing, files=tree.files, directories=tree.directories,
        objects=tree.objects, fidelity=tree.skipped,
        created_unix_ns=_created_ns(args.created_ns),
        chunker=_chunker(args.chunking))
    report = verify_archive(data)
    Path(args.archive).write_bytes(data)
    latest, previous = report.snapshots[-1], report.snapshots[-2]
    changes = diff(previous, latest)
    skipped, code = _skip_payload(tree)
    _emit({"archive": args.archive, "snapshot": latest.sequence,
           "bytes": len(data), "grew_by": len(data) - before,
           "added": changes.added, "removed": changes.removed,
           "modified": changes.modified,
           "new_chunks": len(changes.new_chunks),
           "shared_chunks": len(changes.shared_chunks),
           "skipped": skipped},
          args.json,
          [f"appended snapshot {latest.sequence} to {args.archive}",
           f"  +{len(data) - before} bytes, {len(changes.new_chunks)} new chunks, "
           f"{len(changes.shared_chunks)} reused",
           f"  {len(changes.added)} added, {len(changes.modified)} modified, "
           f"{len(changes.removed)} removed"]
          + [f"  skipped {s['path']} ({s['kind']})" for s in skipped])
    return code


def cmd_snapshots(args: argparse.Namespace) -> int:
    snapshots = list_snapshots(_read(args.archive))
    rows = [{"sequence": s.sequence, "snapshot_id": s.snapshot_id.hex(),
             "parent": s.parent_snapshot.hex() if s.parent_snapshot else None,
             "created_unix_ns": s.manifest["created_unix_ns"],
             "objects": len(s.manifest["objects"]),
             "chunks": len(s.manifest["chunks"]),
             "hash": s.hash_algorithm}
            for s in snapshots]
    _emit({"archive": args.archive, "snapshots": rows}, args.json,
          [f"{r['sequence']:>3}  {r['snapshot_id'][:16]}  "
           f"{r['objects']:>5} objects  {r['chunks']:>5} chunks" for r in rows])
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    snapshot, _ = _pick(_read(args.archive), args.snapshot)
    rows = [{"path": e["path"], "kind": e["kind"], "size": e.get("size", 0),
             "target": (e["target"].decode("utf-8", "surrogateescape")
                        if e["kind"] == "symbolic-link" else None)}
            for e in sorted(snapshot.manifest["objects"], key=lambda e: e["path"])]
    missing = fidelity_of(snapshot.manifest)

    def line(row: dict) -> str:
        if row["kind"] == "regular-file":
            return f"{row['size']:>10}  {row['path']}"
        if row["kind"] == "symbolic-link":
            return f"{'link':>10}  {row['path']} -> {row['target']}"
        return f"{'dir':>10}  {row['path']}/"

    _emit({"archive": args.archive, "snapshot": snapshot.sequence, "objects": rows,
           "fidelity": missing}, args.json,
          [line(row) for row in rows]
          + [f"{'absent':>10}  {e['path']} ({e['reason']})" for e in missing])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data = _read(args.archive)
    report = verify_archive(data)
    # Surfaced without being asked for, and it changes the exit code. An archive can
    # be perfectly valid *and* declare that it is missing things; a verify that
    # returned 0 for both would make the fidelity report a footnote, and the reason
    # it sits in the preservation plane is that it must not be one.
    missing = fidelity_of(report.snapshots[-1].manifest)
    lines = [f"{args.archive}: " + ("ok" if not missing else "ok, but incomplete"),
             f"  {len(report.snapshots)} snapshots, {report.unique_chunks} unique chunks",
             f"  {report.chunk_bytes} stored for {report.logical_bytes} logical bytes"]
    if missing:
        lines.append(f"  the archive records {len(missing)} entries it does not hold:")
        lines += [f"    {e['path']} ({e['reason']}: {e.get('kind', '?')})"
                  for e in missing]
    _emit({"archive": args.archive, "ok": True,
           "snapshots": len(report.snapshots),
           "unique_chunks": report.unique_chunks,
           "chunk_bytes": report.chunk_bytes,
           "logical_bytes": report.logical_bytes,
           "archive_bytes": report.archive_bytes,
           "complete": not missing,
           "fidelity": missing}, args.json, lines)
    return 11 if missing else 0


def cmd_extract(args: argparse.Namespace) -> int:
    data = _read(args.archive)
    snapshot, _ = _pick(data, args.snapshot)
    result = restore_tree(data, snapshot, args.to, overwrite=args.overwrite,
                          restore_mtime=not args.no_mtime,
                          allow_external_links=args.allow_external_links)
    # `metadata_not_applied` is this machine's limit, not the archive's. Reported
    # separately from `fidelity` because "the archive never held it" and "this run
    # could not use it" are different facts, and only one of them means data is gone.
    _emit({"archive": args.archive, "snapshot": snapshot.sequence,
           "destination": result.destination, "files": result.files,
           "directories": result.directories, "links": result.links,
           "bytes": result.bytes_written,
           "metadata_not_applied": result.metadata_not_applied},
          args.json,
          [f"restored snapshot {snapshot.sequence} to {result.destination}",
           f"  {result.files} files, {result.directories} directories, "
           f"{result.links} links, {result.bytes_written} bytes"]
          + [f"  metadata this system could not apply: {ns} ({n} objects)"
             f" - it is still in the archive"
             for ns, n in sorted(result.metadata_not_applied.items())])
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    snapshots = list_snapshots(_read(args.archive))
    by_sequence = {s.sequence: s for s in snapshots}
    newer = args.to or snapshots[-1].sequence
    older = args.from_ if args.from_ is not None else newer - 1
    for wanted in (older, newer):
        if wanted not in by_sequence:
            raise InvalidInput("no such snapshot", requested=wanted,
                               available=sorted(by_sequence))
    changes = diff(by_sequence[older], by_sequence[newer])
    _emit({"archive": args.archive, "from": older, "to": newer,
           "added": changes.added, "removed": changes.removed,
           "modified": changes.modified, "unchanged": len(changes.unchanged),
           "new_chunks": len(changes.new_chunks),
           "shared_chunks": len(changes.shared_chunks)}, args.json,
          [f"snapshot {older} -> {newer}"]
          + [f"  + {p}" for p in changes.added]
          + [f"  - {p}" for p in changes.removed]
          + [f"  ~ {p}" for p in changes.modified])
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=f"{__profile__} — draft of {__draft__}. Nothing here is frozen.")
    parser.add_argument("--version", action="version",
                        version=f"{PROGRAM} {__profile__} (draft {__draft__})")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="emit JSON")

    def writing(p: argparse.ArgumentParser) -> None:
        p.add_argument("--exclude", action="append", metavar="GLOB",
                       help="skip paths matching this glob (repeatable)")
        p.add_argument("--skip-unsupported", action="store_true",
                       help="leave out entries 1.0 cannot represent (devices, "
                            "sockets, FIFOs) instead of refusing. The omission is "
                            "recorded in the archive's fidelity report, and the "
                            "exit code stays 11 for as long as it is there")
        p.add_argument("--no-mtime", action="store_true",
                       help="do not record modification times")
        p.add_argument("--chunking", choices=("none", "cdc"), default="cdc",
                       help="cdc = anla-cdc-1 content-defined chunking (default)")
        p.add_argument("--created-ns", type=int,
                       help="fix the creation timestamp, for reproducible output")

    p_pack = sub.add_parser("pack", help="create an archive from a directory")
    p_pack.add_argument("source")
    p_pack.add_argument("-o", "--output", required=True)
    p_pack.add_argument("--uuid", help="fix the archive id, for reproducible output")
    p_pack.add_argument("--hash", choices=sorted(HASHES), default=CORE_HASH)
    p_pack.add_argument("--force", action="store_true",
                        help="replace an existing output file")
    writing(p_pack)
    common(p_pack)
    p_pack.set_defaults(func=cmd_pack)

    p_append = sub.add_parser("append", help="append a snapshot of a directory")
    p_append.add_argument("archive")
    p_append.add_argument("source")
    writing(p_append)
    common(p_append)
    p_append.set_defaults(func=cmd_append)

    p_snapshots = sub.add_parser("snapshots", help="list the snapshots in an archive")
    p_snapshots.add_argument("archive")
    common(p_snapshots)
    p_snapshots.set_defaults(func=cmd_snapshots)

    p_list = sub.add_parser("list", help="list the objects in one snapshot")
    p_list.add_argument("archive")
    p_list.add_argument("-s", "--snapshot", type=int)
    common(p_list)
    p_list.set_defaults(func=cmd_list)

    p_verify = sub.add_parser("verify", help="verify every snapshot and every chunk")
    p_verify.add_argument("archive")
    common(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_extract = sub.add_parser("extract", help="restore one snapshot to a directory")
    p_extract.add_argument("archive")
    p_extract.add_argument("--to", required=True)
    p_extract.add_argument("-s", "--snapshot", type=int)
    p_extract.add_argument("--overwrite", action="store_true")
    p_extract.add_argument("--allow-external-links", action="store_true",
                           help="create symbolic links whose target is absolute or "
                                "points outside the destination")
    p_extract.add_argument("--no-mtime", action="store_true",
                           help="do not restore modification times")
    common(p_extract)
    p_extract.set_defaults(func=cmd_extract)

    p_diff = sub.add_parser("diff", help="compare two snapshots")
    p_diff.add_argument("archive")
    p_diff.add_argument("--from", dest="from_", type=int)
    p_diff.add_argument("--to", type=int)
    common(p_diff)
    p_diff.set_defaults(func=cmd_diff)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AnlaError as exc:
        json.dump(exc.as_dict(), sys.stderr, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stderr.write("\n")
        return exc.exit_code
    except FileNotFoundError as exc:
        sys.stderr.write(f"{PROGRAM}: no such file: {exc.filename}\n")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
