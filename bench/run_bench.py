# -*- coding: utf-8 -*-
"""Measure what ANLA actually does to real bytes, and publish the numbers.

    python bench/run_bench.py            # run everything, write bench/results.json
    python bench/run_bench.py --json     # the same, to stdout
    python bench/run_bench.py -s git-history

**ANLA 1.0 does not compress.** Its only codec is `store`, so a single-snapshot 1.0
archive is always *larger* than the tree it holds — the manifest and the record
frames are pure overhead. Every number here is deduplication, and the point of
running this rather than asserting it is that deduplication has a shape: it does
almost nothing on one snapshot of unique files and almost everything on the eighth
snapshot of a source tree.

So each scenario is measured against the alternatives a person would actually use —
a ZIP per version, one `tar.gz`, and ANLA-MVP, which *does* compress — and the rows
where ANLA loses are kept in. A benchmark you can only lose by not running is not a
benchmark, and the honest reading of this table is the reason Zstandard is on the
list rather than a nice-to-have.

Everything is measured. Nothing in the output is a literal typed by a person, and
`bench/results.json` records the commit it was produced at so the published page can
say how old its numbers are.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from anla1.fs import scan_tree                       # noqa: E402
from anla1.codecs import CODEC_STORE, CODEC_ZSTD, have_zstd   # noqa: E402
from anla1.snapshot import (                          # noqa: E402
    append_snapshot,
    cdc_chunker,
    extract_snapshot,
    list_snapshots,
    single_chunk,
    verify_archive,
)

EXCLUDE = ("__pycache__", "__pycache__/**", "*.pyc", ".git", ".git/**")
FIXED_UUID = bytes(range(16))
FIXED_TIME = 1_785_000_000_000_000_000


# ---------------------------------------------------------------------------
# measurement helpers — each one returns bytes, none of them estimate
# ---------------------------------------------------------------------------

def tree_bytes(root: Path) -> tuple[int, int]:
    """(total file bytes, file count) for what ANLA would actually store."""
    total = count = 0
    for entry in scan_tree(root, exclude=EXCLUDE).files:
        total += len(entry.read())
        count += 1
    return total, count


def zip_bytes(roots: list[Path]) -> int:
    """One ZIP per tree, deflate level 9, summed.

    The baseline for "I kept a compressed copy of each version", which is what
    people do when they do not have snapshots.
    """
    total = 0
    for root in roots:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for entry in scan_tree(root, exclude=EXCLUDE).files:
                zf.writestr(entry.path, entry.read())
        total += buffer.tell()
    return total


def targz_bytes(roots: list[Path]) -> int:
    """One `tar.gz` over every version at once.

    Kinder to ANLA's competition than it looks: gzip's window is 32 KB, so it finds
    repetition *within* that window and essentially none between two copies of a
    source tree that are megabytes apart in the stream. That limit is the reason
    deduplication is a different mechanism rather than a worse compressor.
    """
    raw = io.BytesIO()
    with tarfile.TarFile(fileobj=raw, mode="w") as tf:
        for index, root in enumerate(roots):
            for entry in scan_tree(root, exclude=EXCLUDE).files:
                payload = entry.read()
                info = tarfile.TarInfo(f"v{index}/{entry.path}")
                info.size = len(payload)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(payload))
    return len(gzip.compress(raw.getvalue(), 9, mtime=0))


def mvp_bytes(root: Path) -> int | None:
    """ANLA-MVP over the same tree — the profile that *does* compress (deflate).

    Present so the table shows where 1.0 would land once it has a codec, rather than
    leaving that as a promise.
    """
    try:
        from anla.writer import PackPlan, collect_tree, pack
    except ImportError:
        return None
    plan = PackPlan(compression="auto", exclude_globs=EXCLUDE)
    tree = collect_tree(root, plan)
    return len(pack(tree, plan, archive_uuid=FIXED_UUID, created_ns=FIXED_TIME).data)


def composition(data: bytes) -> list[dict]:
    """Per snapshot: how many bytes went to content, and how many to describing it.

    Measured by walking the records rather than inferred from the totals, because
    the interesting question about decision 1 — a manifest describes its whole
    snapshot, never a delta — is exactly what that costs on the eighth snapshot, and
    a number derived from sizes could not separate the two.
    """
    from anla1 import container as C
    from anla1.snapshot import list_snapshots

    header = C.parse_header(data)
    rows, start = [], header.first_record_offset
    for snapshot in list_snapshots(data):
        end = snapshot.footer.record.end
        chunk_bytes = metadata_bytes = 0
        for record in C.walk_records(data[:end], header):
            if record.offset < start:
                continue
            if record.type == "CHNK":
                chunk_bytes += record.total_length
            else:
                metadata_bytes += record.total_length
        rows.append({"snapshot": snapshot.sequence, "new_chunk_bytes": chunk_bytes,
                     "metadata_bytes": metadata_bytes})
        start = end
    return rows


def round_trip(data: bytes, expected: list[dict[str, bytes]]) -> int:
    """Extract every snapshot and compare it with the tree that produced it.

    `verify_archive` proves an archive is *internally consistent*: every hash agrees
    with every other hash. It cannot prove the bytes are the ones that went in — a
    writer that consistently stored the wrong content would satisfy it completely,
    because it would also have consistently hashed the wrong content.

    So this is the check the measurements were resting on and did not have. It is
    the same shape as every other lesson in this repository: a check that compares a
    thing to itself cannot fail for the reason you care about.

    Returns the number of files compared, so a silent zero is visible.
    """
    compared = 0
    snapshots = list_snapshots(data)
    if len(snapshots) != len(expected):
        raise AssertionError(f"{len(snapshots)} snapshots for {len(expected)} trees")
    for snapshot, wanted in zip(snapshots, expected):
        restored = extract_snapshot(data, snapshot)
        if restored != wanted:
            missing = sorted(set(wanted) - set(restored))
            extra = sorted(set(restored) - set(wanted))
            differs = sorted(k for k in set(wanted) & set(restored)
                             if wanted[k] != restored[k])
            raise AssertionError(
                f"snapshot {snapshot.sequence} did not round trip: "
                f"missing={missing[:3]} extra={extra[:3]} differs={differs[:3]}")
        compared += len(wanted)
    if not compared:
        raise AssertionError("nothing was compared, so nothing was checked")
    return compared


def anla1_snapshots(roots: list[Path], *, chunking: str = "cdc",
                    codec: int = 0) -> tuple[int, list[int], dict]:
    """Append one snapshot per tree. Returns (final size, size after each, report)."""
    chunker = cdc_chunker() if chunking == "cdc" else single_chunk
    data, sizes, trees = b"", [], []
    for index, root in enumerate(roots):
        # No recorded metadata at all, so the table does not move when it is
        # regenerated on a different machine: POSIX records a file mode and Windows
        # has none to record, which is correct and would otherwise show up here as a
        # change nobody made.
        scanned = scan_tree(root, exclude=EXCLUDE, preserve_mtime=False,
                            preserve_posix=False)
        trees.append({entry.path: entry.read() for entry in scanned.files})
        data = append_snapshot(
            data, files=scanned.files, directories=scanned.directories,
            created_unix_ns=FIXED_TIME + index, chunker=chunker, codec=codec,
            archive_id=FIXED_UUID if index == 0 else None)
        sizes.append(len(data))
    report = verify_archive(data)          # never report a size we did not verify
    compared = round_trip(data, trees)     # ...and never one we did not restore
    return len(data), sizes, {
        "snapshots": len(report.snapshots),
        "unique_chunks": report.unique_chunks,
        "chunk_bytes": report.chunk_bytes,
        "logical_bytes": report.logical_bytes,
        "files_round_tripped": compared,
        "composition": composition(data),
    }


# ---------------------------------------------------------------------------

@dataclass
class Result:
    scenario: str
    headline: str
    note: str
    inputs: dict = field(default_factory=dict)
    sizes: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    @property
    def ratios(self) -> dict:
        anla = self.sizes.get("anla_1_0")
        base = self.inputs.get("logical_bytes")
        out = {}
        if anla and base:
            out["anla_1_0_vs_input"] = round(anla / base, 4)
        for name, size in self.sizes.items():
            if name != "anla_1_0" and size and anla:
                out[f"anla_1_0_vs_{name}"] = round(anla / size, 4)
        return out


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------

def scenario_source_tree(work: Path) -> Result:
    """One snapshot of a real source tree — where ANLA 1.0 loses, on purpose."""
    target = ROOT / "python"
    logical, files = tree_bytes(target)
    size, _, report = anla1_snapshots([target], codec=CODEC_ZSTD if have_zstd()
                                      else CODEC_STORE)
    stored_only, _, _ = anla1_snapshots([target], codec=CODEC_STORE)
    return Result(
        scenario="source-tree",
        headline="One snapshot of this repository's python/ directory",
        note="This row used to be the argument for Zstandard, stated as a "
             "measurement: with only `store` a single snapshot was larger than the "
             "tree and both compressors beat it comfortably. The codec landed, so "
             "the row now answers its own question — and the `store` line is kept "
             "beside it, because a benchmark that quietly drops the case it used to "
             "lose is not reporting, it is marketing.",
        inputs={"logical_bytes": logical, "files": files},
        sizes={"anla_1_0": size,
               "anla_1_0_store_only": stored_only,
               "zip_deflate9": zip_bytes([target]),
               "targz": targz_bytes([target]),
               "anla_mvp_deflate": mvp_bytes(target)},
        detail=report)


def scenario_git_history(work: Path, versions: int = 8) -> Result:
    """Successive commits of a real source tree, one snapshot each.

    The scenario ANLA exists for, and the only one where a person has to choose
    between keeping every version and keeping only the newest.
    """
    revisions = subprocess.run(
        ["git", "log", "--format=%h", "-n", str(versions), "--", "python"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    revisions.reverse()                                   # oldest first
    roots = []
    for revision in revisions:
        destination = work / f"v-{revision}"
        destination.mkdir(parents=True)
        archive = subprocess.run(
            ["git", "archive", "--format=tar", revision, "--", "python"],
            cwd=ROOT, capture_output=True, check=True).stdout
        with tarfile.TarFile(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(destination)
        roots.append(destination / "python")

    logical = sum(tree_bytes(root)[0] for root in roots)
    size, growth, report = anla1_snapshots(roots, codec=CODEC_ZSTD if have_zstd()
                                           else CODEC_STORE)
    stored_only, _, _ = anla1_snapshots(roots, codec=CODEC_STORE)
    first = growth[0]
    return Result(
        scenario="git-history",
        headline=f"{len(roots)} successive commits of python/, one snapshot each",
        note="Every version is recoverable, byte for byte. The comparison is against "
             "keeping each version as its own ZIP, which is what people do without "
             "snapshots, and against one tar.gz of all of them — gzip's 32 KB window "
             "cannot see from one copy of the tree to the next, which is why "
             "deduplication is a different mechanism and not a worse compressor.",
        inputs={"logical_bytes": logical, "versions": len(roots),
                "revisions": revisions},
        sizes={"anla_1_0": size,
               "anla_1_0_store_only": stored_only,
               "zip_deflate9_per_version": zip_bytes(roots),
               "targz_all_versions": targz_bytes(roots)},
        detail={**report,
                "after_each_snapshot": growth,
                "first_snapshot_bytes": first,
                "later_snapshots_bytes": size - first,
                "mean_later_snapshot_bytes": (
                    round((size - first) / max(1, len(roots) - 1)))})


def scenario_duplicate_tree(work: Path, copies: int = 5) -> Result:
    """The deduplication ceiling: the same tree, over and over."""
    source = ROOT / "papers"
    roots = []
    for index in range(copies):
        destination = work / f"copy-{index}"
        shutil.copytree(source, destination)
        roots.append(destination)
    logical = sum(tree_bytes(root)[0] for root in roots)
    size, growth, report = anla1_snapshots(roots)
    return Result(
        scenario="duplicate-tree",
        headline=f"The same directory snapshotted {copies} times, unchanged",
        note="The ceiling. Snapshots 2 to 5 add a manifest and a footer and nothing "
             "else, so their cost is the price of decision 1 in the snapshot design: "
             "a manifest describes its whole snapshot rather than a delta.",
        inputs={"logical_bytes": logical, "copies": copies},
        sizes={"anla_1_0": size, "zip_deflate9_per_copy": zip_bytes(roots)},
        detail={**report, "after_each_snapshot": growth,
                "cost_per_repeat_snapshot": (
                    round((size - growth[0]) / max(1, copies - 1)))})


def scenario_incompressible(work: Path) -> Result:
    """The honest floor: random bytes, then the same random bytes again."""
    import random

    rng = random.Random(20260807)
    payload = bytes(rng.getrandbits(8) for _ in range(2_000_000))
    first, second = work / "rand-1", work / "rand-2"
    for root in (first, second):
        root.mkdir()
        (root / "blob.bin").write_bytes(payload)

    logical, _ = tree_bytes(first)
    size, growth, report = anla1_snapshots([first, second])
    return Result(
        scenario="incompressible",
        headline="2 MB of random bytes, then the identical file again",
        note="Nothing compresses this, and nothing should. The first snapshot costs "
             "slightly more than the file; the second costs almost nothing, because "
             "deduplication does not care whether the bytes are compressible.",
        inputs={"logical_bytes": logical * 2, "files": 2},
        sizes={"anla_1_0": size, "zip_deflate9_per_copy": zip_bytes([first, second]),
               "targz_both": targz_bytes([first, second])},
        detail={**report, "after_each_snapshot": growth,
                "second_snapshot_bytes": size - growth[0]})


def scenario_shifted_insert(work: Path) -> Result:
    """Content-defined chunking against fixed chunking, on a shifted file."""
    import random

    rng = random.Random(20260807)
    payload = bytes(rng.getrandbits(8) for _ in range(3_000_000))
    before, after = work / "shift-1", work / "shift-2"
    for root, data in ((before, payload), (after, b"x" * 64 + payload)):
        root.mkdir()
        (root / "big.bin").write_bytes(data)

    cdc_size, cdc_growth, cdc_report = anla1_snapshots([before, after], chunking="cdc")
    fixed_size, fixed_growth, _ = anla1_snapshots([before, after], chunking="none")
    return Result(
        scenario="shifted-insert",
        headline="3 MB file, then the same file with 64 bytes inserted at the front",
        note="The case fixed-size chunking cannot survive: every boundary moves, so "
             "not one chunk matches and the whole file is stored twice. "
             "Content-defined boundaries follow the content, so only the chunks that "
             "actually changed are new.",
        inputs={"logical_bytes": 3_000_000 * 2 + 64, "files": 2},
        sizes={"anla_1_0": cdc_size, "anla_1_0_fixed_chunking": fixed_size},
        detail={**cdc_report,
                "cdc_second_snapshot_bytes": cdc_size - cdc_growth[0],
                "fixed_second_snapshot_bytes": fixed_size - fixed_growth[0]})


def scenario_metadata_cost(work: Path) -> Result:
    """What Milestone 2 costs: namespaced metadata and symbolic links.

    Built from objects rather than from a directory, deliberately. The filesystem
    version cannot run on a Windows host without developer mode, and a scenario that
    quietly measured something different depending on the machine would make the
    published table depend on who generated it. This measures the format, which is
    the same everywhere.
    """
    from anla1.manifest import ObjectEntry
    from anla1.snapshot import SourceEntry

    count = 500
    files = [SourceEntry.of(f"src/file{i:03d}.txt", f"contents of {i}\n".encode())
             for i in range(count)]
    timed = [SourceEntry(path=f.path, read=f.read,
                         metadata={"common": {"mtime_ns": 1_700_000_000_000_000_000 + i}})
             for i, f in enumerate(files)]
    full = [SourceEntry(path=f.path, read=f.read, metadata={
        "common": {"mtime_ns": 1_700_000_000_000_000_000 + i},
        "posix": {"mode": 0o644}}) for i, f in enumerate(files)]
    links = [ObjectEntry(kind="symbolic-link", path=f"link/l{i:03d}",
                         target=f"../src/file{i:03d}.txt".encode())
             for i in range(count)]

    def size(entries, objects=()) -> int:
        return len(append_snapshot(
            b"", files=entries, directories=["src", "link"], objects=list(objects),
            created_unix_ns=FIXED_TIME, archive_id=FIXED_UUID))

    bare, with_times, with_posix = size(files), size(timed), size(full)
    with_links = size(full, links)
    # This scenario builds its objects rather than scanning them, so it does its own
    # round trip. Links carry no content and must not appear in the extraction.
    built = append_snapshot(b"", files=full, directories=["src", "link"],
                            objects=links, created_unix_ns=FIXED_TIME,
                            archive_id=FIXED_UUID)
    round_trip(built, [{f.path: f.read() for f in files}])
    logical = sum(len(f.read()) for f in files)
    return Result(
        scenario="metadata-cost",
        headline=f"{count} files: what namespaced metadata and {count} symlinks add",
        note="Milestone 2 moves no compression number, because it is not about "
             "compression — it is what lets the tool pack trees it used to refuse "
             "outright. This is its actual bill, per object, in the manifest. A "
             "symbolic link costs a manifest entry and no chunk at all: it has no "
             "content, only a target.",
        inputs={"logical_bytes": logical, "files": count, "links": count},
        sizes={"anla_1_0": with_links,
               "no_metadata": bare,
               "times_only": with_times,
               "times_and_mode": with_posix},
        detail={"files_round_tripped": count,
                "bytes_per_object_for_times": round((with_times - bare) / count, 1),
                "bytes_per_object_for_mode": round((with_posix - with_times) / count, 1),
                "bytes_per_symlink": round((with_links - with_posix) / count, 1)})


SCENARIOS = {
    "source-tree": scenario_source_tree,
    "metadata-cost": scenario_metadata_cost,
    "git-history": scenario_git_history,
    "duplicate-tree": scenario_duplicate_tree,
    "incompressible": scenario_incompressible,
    "shifted-insert": scenario_shifted_insert,
}


# ---------------------------------------------------------------------------

def revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-s", "--scenario", action="append", choices=sorted(SCENARIOS))
    parser.add_argument("--json", action="store_true", help="write to stdout as well")
    parser.add_argument("-o", "--output",
                        help="where to write; defaults to bench/results.json for a "
                             "full run, and is required for a partial one")
    args = parser.parse_args(argv)

    chosen = args.scenario or list(SCENARIOS)
    if args.scenario and not args.output:
        # A subset must not land in the published file. Writing one scenario over
        # `results.json` produces a table that looks complete and is not, and the
        # site build cannot tell the difference — it renders whatever it is given.
        parser.error("running a subset needs an explicit -o; bench/results.json is "
                     "the published table and must come from a full run")
    output = Path(args.output or Path(__file__).parent / "results.json")
    results = []
    for name in chosen:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix=f"anla-bench-{name}-") as tmp:
            result = SCENARIOS[name](Path(tmp))
        payload = asdict(result)
        payload["ratios"] = result.ratios
        payload["seconds"] = round(time.perf_counter() - started, 2)
        results.append(payload)
        print(f"{name:<16} {result.sizes['anla_1_0']:>12,} bytes  "
              f"({payload['seconds']}s)", file=sys.stderr)

    document = {
        "generated_at_unix_ns": time.time_ns(),
        "revision": revision(),
        "profile": "ANLA 1.0 (draft)",
        # The single most important field on the published page. Every ratio below
        # is deduplication; none of it is compression, because 1.0 has no codec that
        # compresses. Stated as data so the page cannot forget to say it.
        "codecs": ["store", "zstd"] if have_zstd() else ["store"],
        "chunking": "anla-cdc-1",
        "hash": "blake3-256",
        "platform": {"system": os.name, "python": sys.version.split()[0]},
        "results": results,
    }
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    print(f"wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
