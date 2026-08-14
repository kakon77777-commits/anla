# -*- coding: utf-8 -*-
"""Put real files in this folder. This runs ANLA over them and tells you the truth.

    python test_demo/run.py             # pack, verify, extract, compare, report
    python test_demo/run.py --keep      # leave the artifacts in test_demo/_out/
    python test_demo/run.py --json

The corpus is whatever is in this directory. Drop papers in, drop source code in,
drop a PDF in — nothing here knows or cares what a file is, which is the point:
`Extract(Pack(F, P)) = F` is supposed to hold for bytes, and a harness that had to
be taught about a new file type would be a harness that could be *surprised* by one.

**Every comparison is against the file on disk, re-read.** Not against what the
scanner captured on the way in. That distinction is the whole reason this exists:
comparing an archive to the copy of the input the archiver is holding is a check
that cannot fail for the reason anyone cares about, and this repository has already
found that shape five times.

Reported per file extension, so when a new kind of file arrives it appears as its
own row rather than dissolving into a total. A round trip that works for Markdown
and not for PDF should look like a round trip that works for Markdown and not for
PDF.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python"))

from anla1.fs import restore_tree, scan_tree          # noqa: E402
from anla1.snapshot import (                           # noqa: E402
    append_snapshot,
    cdc_chunker,
    diff,
    extract_snapshot,
    list_snapshots,
    verify_archive,
)

#: The runner's own output. Everything else in this folder is corpus, including
#: this file — a Python source file is exactly the kind of thing that is going in
#: here next, so there is no reason to hide it from the archive.
EXCLUDE = ("_out", "_out/**", "__pycache__", "__pycache__/**", "*.pyc")

FIXED_UUID = bytes(range(16))
FIXED_TIME = 1_785_000_000_000_000_000


@dataclass
class Report:
    corpus: str
    files: int = 0
    logical_bytes: int = 0
    archive_bytes: int = 0
    unique_chunks: int = 0
    compared: int = 0
    mismatches: list[dict] = field(default_factory=list)
    by_extension: dict = field(default_factory=dict)
    revision: dict = field(default_factory=dict)
    profiles: list = field(default_factory=list)
    restored_to_disk: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.mismatches and self.compared == self.files and self.files > 0


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return "(no extension)"
    # `.zh-Hant.md` is a Markdown file, not a `.zh-Hant` file.
    return "." + name.rsplit(".", 1)[-1].lower()


def check_corpus(corpus: Path, *, keep: Path | None = None) -> Report:
    """Pack the corpus, verify it, extract it, and compare against the disk."""
    report = Report(corpus=str(corpus))
    tree = scan_tree(corpus, exclude=EXCLUDE)
    if not tree.files:
        raise SystemExit(f"{corpus} holds no files to test")

    data = append_snapshot(
        b"", files=tree.files, directories=tree.directories,
        objects=tree.objects, fidelity=tree.skipped,
        created_unix_ns=FIXED_TIME, chunker=cdc_chunker(),
        archive_id=FIXED_UUID)

    verified = verify_archive(data)
    report.files = len(tree.files)
    report.archive_bytes = len(data)
    report.unique_chunks = verified.unique_chunks
    report.logical_bytes = verified.logical_bytes

    # The comparison. Read from disk again, in binary, and compare bytes. Never
    # text: these papers are UTF-8 with CJK in them, and a text-mode read on this
    # host would decode as cp950 and turn a byte-exact round trip into a claim
    # about two mojibake strings agreeing with each other.
    restored = extract_snapshot(data, list_snapshots(data)[0])
    sizes: dict[str, list] = defaultdict(lambda: [0, 0, 0])   # files, bytes, matched
    for entry in tree.files:
        original = (corpus / entry.path).read_bytes()
        came_back = restored.get(entry.path)
        bucket = sizes[_extension(entry.path)]
        bucket[0] += 1
        bucket[1] += len(original)
        report.compared += 1
        if came_back == original:
            bucket[2] += 1
            continue
        report.mismatches.append({
            "path": entry.path,
            "reason": "absent from the archive" if came_back is None else
                      f"{len(original)} bytes in, {len(came_back)} bytes out"
                      if len(came_back) != len(original) else
                      "same length, different bytes",
        })

    report.by_extension = {
        ext: {"files": n, "bytes": total, "round_tripped": matched}
        for ext, (n, total, matched) in sorted(sizes.items())
    }

    report.revision = _revision_cycle(corpus, data, tree)
    report.profiles = _profile_sweep(corpus, tree)
    if keep is not None:
        report.restored_to_disk = _write_artifacts(keep, data, corpus)
    return report


def _revision_cycle(corpus: Path, data: bytes, tree) -> dict:
    """What a second draft costs.

    The workload these files are actually going to see. A paper is not written once;
    it is written forty times, and the question ANLA has to answer well is what the
    forty-first draft costs when thirty-nine of them are already in the archive.

    The edit is applied in memory, never to the corpus on disk: a test that rewrote
    the files it was given would be a test nobody could run twice.
    """
    from anla1.snapshot import SourceEntry

    biggest = max(tree.files, key=lambda e: len(e.read()))
    edited = []
    for entry in tree.files:
        if entry.path != biggest.path:
            edited.append(entry)
            continue
        body = entry.read()
        # A realistic revision: a paragraph inserted a third of the way in, which
        # shifts every byte after it. Appending at the end would be the easy case
        # and would not exercise content-defined chunking at all.
        cut = len(body) // 3
        revised = body[:cut] + "\n\n（改稿：這一段是第二版加進去的。）\n\n".encode() + body[cut:]
        edited.append(SourceEntry(path=entry.path, read=lambda r=revised: r))

    second = append_snapshot(data, files=edited, directories=tree.directories,
                             objects=tree.objects, created_unix_ns=FIXED_TIME + 1,
                             chunker=cdc_chunker())
    verify_archive(second)
    older, newer = list_snapshots(second)
    changes = diff(older, newer)

    # And the first draft must still come back untouched.
    first_again = extract_snapshot(second, older)
    unchanged = all(first_again[e.path] == (corpus / e.path).read_bytes()
                    for e in tree.files)
    return {
        "edited": biggest.path,
        "grew_by": len(second) - len(data),
        "edited_file_bytes": len(biggest.read()),
        "new_chunks": len(changes.new_chunks),
        "shared_chunks": len(changes.shared_chunks),
        "first_draft_still_exact": unchanged,
    }


def _profile_sweep(corpus: Path, tree) -> list[dict]:
    """What a second draft costs at several chunk sizes, on *this* corpus.

    The pinned default averages 256 KiB with a 64 KiB floor. That is right for disk
    images and wrong for prose: a 30 KiB paper is entirely below the floor, so it is
    one chunk, so content-defined chunking does nothing at all and editing one
    paragraph rewrites the whole file. The first run of this harness on real papers
    is what surfaced that — a 36 KiB whitepaper cost 39 KiB to revise.

    `anla-cdc-1` is not what changes here. It pins the gear table and the boundary
    rule, which is the part two implementations have to agree on; the sizes are
    declared per archive and are supposed to fit the corpus.
    """
    from anla.fastcdc import DEFAULT_PROFILE, CdcProfile
    from anla1.snapshot import SourceEntry

    biggest = max(tree.files, key=lambda e: len(e.read()))
    body = biggest.read()
    cut = len(body) // 3
    revised = body[:cut] + "\n\n（改稿）\n\n".encode() + body[cut:]

    rows = []
    for profile in (DEFAULT_PROFILE, CdcProfile(min_size=16384, avg_size=65536,
                                                max_size=262144),
                    CdcProfile(min_size=4096, avg_size=16384, max_size=65536),
                    CdcProfile(min_size=1024, avg_size=4096, max_size=16384),
                    CdcProfile(min_size=256, avg_size=1024, max_size=4096)):
        chunker = cdc_chunker(profile)
        first = append_snapshot(b"", files=tree.files, directories=tree.directories,
                                created_unix_ns=FIXED_TIME, chunker=chunker,
                                archive_id=FIXED_UUID)
        edited = [SourceEntry(path=e.path, read=(lambda r=revised: r))
                  if e.path == biggest.path else e for e in tree.files]
        second = append_snapshot(first, files=edited, directories=tree.directories,
                                 created_unix_ns=FIXED_TIME + 1, chunker=chunker)
        rows.append({"avg_size": profile.avg_size, "min_size": profile.min_size,
                     "first_snapshot_bytes": len(first),
                     "second_draft_bytes": len(second) - len(first),
                     "chunks": len(list_snapshots(first)[0].manifest["chunks"])})
    return rows


def _write_artifacts(out: Path, data: bytes, corpus: Path) -> dict:
    """Leave the archive and a restored tree on disk, for poking at."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    archive = out / "corpus.anla"
    archive.write_bytes(data)
    restored = out / "restored"
    restore_tree(data, list_snapshots(data)[0], restored)
    # Compare the *files on disk* now, not the in-memory extraction: this is the
    # path a person actually uses, and it is the one where a filesystem gets to
    # fold a name or mangle a line ending.
    differing = [str(p.relative_to(restored)).replace("\\", "/")
                 for p in restored.rglob("*") if p.is_file()
                 and p.read_bytes() != (corpus / p.relative_to(restored)).read_bytes()]
    return {"archive": str(archive), "restored": str(restored),
            "files_differing_on_disk": differing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(HERE))
    parser.add_argument("--keep", action="store_true",
                        help="leave the archive and a restored copy in _out/")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    corpus = Path(args.corpus).resolve()
    report = check_corpus(corpus, keep=(HERE / "_out") if args.keep else None)

    if args.json:
        payload = {k: v for k, v in vars(report).items()}
        payload["ok"] = report.ok
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"corpus: {corpus}")
        print(f"  {report.files} files, {report.logical_bytes:,} bytes "
              f"-> {report.archive_bytes:,} bytes in {report.unique_chunks} chunks")
        for ext, row in report.by_extension.items():
            mark = "ok" if row["round_tripped"] == row["files"] else "MISMATCH"
            print(f"    {ext:<16} {row['files']:>4} files  {row['bytes']:>10,} bytes"
                  f"  {mark}")
        revision = report.revision
        print(f"  second draft of {revision['edited']} "
              f"({revision['edited_file_bytes']:,} bytes): "
              f"+{revision['grew_by']:,} bytes, "
              f"{revision['new_chunks']} new chunks, "
              f"{revision['shared_chunks']} reused")
        print(f"  first draft still byte-exact: {revision['first_draft_still_exact']}")
        if report.profiles:
            best = min(report.profiles, key=lambda r: r["second_draft_bytes"])
            print("  cost of that second draft, by chunk size:")
            for row in report.profiles:
                note = "  <- the pinned default" if row["avg_size"] == 262144 else (
                    "  <- best here" if row is best else "")
                print(f"    avg {row['avg_size']:>7,}  min {row['min_size']:>6,}  "
                      f"{row['chunks']:>4} chunks  "
                      f"+{row['second_draft_bytes']:>8,} bytes{note}")
        if report.restored_to_disk:
            print(f"  artifacts: {report.restored_to_disk['restored']}")
            print(f"  differing on disk: "
                  f"{report.restored_to_disk['files_differing_on_disk'] or 'none'}")
        for bad in report.mismatches:
            print(f"  MISMATCH {bad['path']}: {bad['reason']}")
        print(f"  {'every file came back byte for byte' if report.ok else 'FAILED'}")

    return 0 if report.ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
