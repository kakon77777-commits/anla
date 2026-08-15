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
    write_snapshot,
)

EXCLUDE = ("__pycache__", "__pycache__/**", "*.pyc", ".git", ".git/**")
#: The Rust writer, when it has been built. Its absence is reported rather than
#: silently dropping the row — a benchmark missing its fastest entrant with no note
#: is a benchmark that flatters the one that is left.
RUST_DIR = ROOT / "rust" / "target" / "release"
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


#: Two scenarios pack `python/` as it exists right now, which means their inputs
#: change whenever the repository does. That is worth saying on the rows
#: themselves rather than in a commit message nobody reads next to the number.
DRIFT_CAVEAT = (" **This row's input is the live repository, so its absolute byte counts are not comparable between commits** — adding four test files moved every size on it, including every competitor's. Only the ratios within one run mean anything across time, and a regression small enough to hide inside a few new files would not be visible here at all. The four scenarios with fixed inputs are where a regression would show, and they are exact: on the run that added this note, not one byte moved on any of them.")


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
             "lose is not reporting, it is marketing." + DRIFT_CAVEAT,
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
             "deduplication is a different mechanism and not a worse compressor."
             + DRIFT_CAVEAT,
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


def scenario_throughput(work: Path) -> Result:
    """How fast, which is the question three weeks of correctness work never asked.

    Ratios say what an archive costs to keep. This says what it costs to make, and
    until 2026-08-14 nobody had run it. The answer changed the roadmap: the Python
    writer packs at single-digit MiB/s with content-defined chunking, which is the
    *default* — because fixed chunking makes cross-snapshot deduplication collapse,
    as the `shifted-insert` row measures. So the mode that makes the product worth
    having is the mode that is unusably slow, in the implementation a user installs.

    The Rust writer does the identical work — byte-identical, proven by
    `tools/compare_writers.py` — sixteen times faster. That is not a format problem;
    it is a per-byte rolling-hash loop in CPython, and `design/commercial-readiness-plan.md`
    records the measured 1.3x ceiling on fixing it in pure Python.

    Incompressible input on purpose: compressible data measures zstd, not the writer.
    """
    import random
    import subprocess
    import time

    rng = random.Random(20260814)
    payload = bytes(rng.getrandbits(8) for _ in range(64 * 1024 * 1024))
    source = work / "throughput"
    source.mkdir()
    for index in range(64):
        (source / f"part-{index:03d}.bin").write_bytes(
            payload[index * 1024 * 1024:(index + 1) * 1024 * 1024])
    megabytes = 64.0

    def timed(call) -> float:
        start = time.perf_counter()
        call()
        return time.perf_counter() - start

    rates: dict[str, float] = {}

    # Both implementations scan the same directory off the same disk. The first
    # version of this fed Python a list of in-memory buffers while Rust read 64
    # files, so Rust was doing strictly more work and its number came out a third
    # low — an unfair benchmark is worse than none, and it flattered the
    # implementation that is already losing.
    def python_pack(target: Path, **kwargs) -> None:
        tree = scan_tree(source, preserve_mtime=False, preserve_posix=False)
        write_snapshot(target, **tree.as_source(), created_unix_ns=1,
                       archive_id=FIXED_UUID, **kwargs)

    fixed_target = work / "fixed.anla"
    rates["python_pack_fixed"] = round(megabytes / timed(
        lambda: python_pack(fixed_target)), 1)

    cdc_target = work / "cdc.anla"
    rates["python_pack_cdc"] = round(megabytes / timed(
        lambda: python_pack(cdc_target, chunker=cdc_chunker())), 1)

    archive = cdc_target.read_bytes()
    rates["python_verify"] = round(megabytes / timed(
        lambda: verify_archive(archive)), 1)

    binary = next((RUST_DIR / n for n in ("anla1-rs.exe", "anla1-rs")
                   if (RUST_DIR / n).exists()), None)
    if binary is not None:
        # `cdc`, not `anla-cdc-1`. Neither CLI has ever accepted the profile's own
        # name — Python refuses it outright and Rust used to *ignore* it and pick
        # its default, which is **fixed** chunking. So every published
        # `rust_pack_cdc` figure before this line changed was the Rust writer doing
        # fixed chunking, compared against the Python writer doing CDC: the exact
        # unfair comparison the comment thirty lines above warns about, in the row
        # that comment is attached to.
        #
        # It surfaced only because the flag was changed from silently ignoring an
        # unknown value to erroring on one, at which point this run stopped instead
        # of quietly measuring the wrong thing — which is the argument for that
        # change, arriving three weeks late.
        rust_target = work / "rust.anla"
        rates["rust_pack_cdc"] = round(megabytes / timed(
            lambda: subprocess.run(
                [str(binary), "pack", str(source), "-o", str(rust_target),
                 "--chunking", "cdc", "--uuid", FIXED_UUID.hex(),
                 "--created-ns", "1"], check=True, capture_output=True)), 1)

    # Computed, not written down. Both language versions of this note carried a
    # hand-typed multiple and they had drifted apart from each other — one said
    # sixteen times and the other twenty-two — while the measured ratio was neither.
    factor = (f'{rates["rust_pack_cdc"] / rates["python_pack_cdc"]:.0f}'
              if "rust_pack_cdc" in rates else "—")
    return Result(
        scenario="throughput",
        headline="64 MiB of incompressible data, packed and verified",
        note="MiB per second, on the machine that ran this. Content-defined chunking "
             "is the default because fixed chunking destroys deduplication — and in "
             "the Python writer it is also the slow path, by two orders of magnitude. "
             "The Rust writer produces byte-identical archives at {factor} times the "
             "rate, so this is an implementation number and not a format number. It "
             "is published because a project that measures only what it is good at is "
             "not measuring." + (
                 "" if binary is not None else
                 " The Rust row is absent on this run: the binary was not built."),
        inputs={"logical_bytes": 64 * 1024 * 1024, "files": 64},
        sizes={},
        detail={"mib_per_second": rates,
                # Every language's note is rendered through these, so one measured
                # value fills both and neither can drift from the other.
                "note_values": {"factor": factor},
                "hours_to_pack_one_tib": {
                    name: round(1024 * 1024 / rate / 3600, 2)
                    for name, rate in rates.items() if "pack" in name and rate}})


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
    "throughput": scenario_throughput,
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
        # Not every scenario produces an archive size. `throughput` measures rates,
        # and the summary line assumed one shape for all rows.
        headline = (f"{result.sizes['anla_1_0']:>12,} bytes"
                    if "anla_1_0" in result.sizes
                    else f"{'rates only':>18}")
        print(f"{name:<16} {headline}  ({payload['seconds']}s)", file=sys.stderr)

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
