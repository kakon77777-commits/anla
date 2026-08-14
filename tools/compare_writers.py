# -*- coding: utf-8 -*-
"""Two writers, one tree. The clause the freeze rule is actually stated over.

    python tools/compare_writers.py <corpus-directory>

Packs the same directory with the Python writer and the Rust writer, under the same
fixed `(uuid, created_ns)` and no recorded metadata, and compares the bytes.

**`store` must be byte-identical, and a difference fails.** That is the clause:
canonical CBOR, object ordering, chunk boundaries, record framing and Merkle roots
all have to agree exactly, and any one of them disagreeing moves an offset.

**`zstd` is reported and does not fail**, and the reason is a prediction the
specification makes in §8: compressed output is a function of the compressor, so two
writers linking different libzstd builds may produce different bytes for the same
input and both be right. What must still match under any codec is `objects_root` and
the chunk-id set — the *tree*, not the layout — so that is checked instead.

If zstd does match, the two builds happen to share a libzstd. That is worth printing
and worth not relying on.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from anla1.snapshot import latest_snapshot  # noqa: E402

RUST = ROOT / "rust" / "target" / "release" / (
    "anla1-rs.exe" if sys.platform == "win32" else "anla1-rs")

UUID = "00112233445566778899aabbccddeeff"
CREATED = "1785000000000000000"
EXCLUDE = ("_out", "__pycache__")


def python_pack(corpus: Path, out: Path, codec: str, average: int, metadata: bool = False) -> None:
    from anla1.cli import main

    argv = ["pack", str(corpus), "-o", str(out), "--force"] + ([] if metadata else ["--no-metadata"]) + [
            "--codec", codec, "--chunk-avg", str(average),
            "--uuid", UUID, "--created-ns", CREATED, "--json"]
    for name in EXCLUDE:
        argv += ["--exclude", name, "--exclude", f"{name}/**"]
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        code = main(argv)
    if code != 0:
        raise SystemExit(f"the python writer exited {code}")


def rust_pack(corpus: Path, out: Path, codec: str, average: int, metadata: bool = False) -> None:
    argv = [str(RUST), "pack", str(corpus), "-o", str(out),
            "--codec", codec, "--chunk-avg", str(average),
            "--uuid", UUID, "--created-ns", CREATED] + ([] if metadata else ["--no-metadata"])
    for name in EXCLUDE:
        argv += ["--exclude", name]
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"the rust writer exited {result.returncode}: {result.stderr}")


def tree_identity(path: Path) -> tuple[str, list[str]]:
    """`objects_root` and the chunk-id set: what must match under *any* codec."""
    snapshot = latest_snapshot(path.read_bytes())
    return (snapshot.manifest["objects_root"].hex(),
            sorted(chunk.hex() for chunk in snapshot.manifest["chunks"]))


def compare_append(corpus: Path, work: Path) -> int:
    """Create, then append, with both writers.

    A second snapshot exercises everything one snapshot cannot: the footer chain,
    the parent link, resuming at the end of the newest complete snapshot rather than
    the end of the file, and a manifest that lists descriptors for chunks an earlier
    snapshot wrote.

    It is also what found the `archive_id` bug: the Rust append used its unset
    `--uuid` for the manifest while inheriting the header's, and *both readers
    verified it*, because nothing cross-checked the two places an archive names
    itself. Both now do.
    """
    import shutil

    v1, v2 = work / "v1", work / "v2"
    for target in (v1, v2):
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
    for source in sorted(corpus.glob("*.md")):
        shutil.copyfile(source, v1 / source.name)
        shutil.copyfile(source, v2 / source.name)
    biggest = max(v2.glob("*.md"), key=lambda p: p.stat().st_size)
    biggest.write_bytes(biggest.read_bytes() + b"\n\n(a second draft)\n")
    (v2 / "added.md").write_bytes(b"new in the second snapshot\n")

    py, rs = work / "py-append.anla", work / "rs-append.anla"
    python_pack(v1, py, "store", 4096)
    rust_pack(v1, rs, "store", 4096)

    from anla1.cli import main as anla1_main
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        code = anla1_main(["append", str(py), str(v2), "--no-metadata", "--codec",
                           "store", "--chunk-avg", "4096",
                           "--created-ns", str(int(CREATED) + 1), "--json"])
    if code != 0:
        print(f"  append               the python writer exited {code}", file=sys.stderr)
        return 1
    result = subprocess.run(
        [str(RUST), "append", str(rs), "-o", str(v2), "--no-metadata", "--codec",
         "store", "--chunk-avg", "4096", "--created-ns", str(int(CREATED) + 1)],
        capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  append               the rust writer exited {result.returncode}: "
              f"{result.stderr}", file=sys.stderr)
        return 1

    if py.read_bytes() == rs.read_bytes():
        print(f"  append (2 snapshots) byte-identical, {py.stat().st_size:,} bytes")
        return 0
    print(f"  append (2 snapshots) DIFFER — {py.stat().st_size:,} vs "
          f"{rs.stat().st_size:,} bytes", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    corpus = Path(argv[0]) if argv else ROOT / "test_demo"
    if not RUST.exists():
        print(f"{RUST} is not built — run `cargo build --release` in rust/",
              file=sys.stderr)
        return 2

    failures = 0
    with tempfile.TemporaryDirectory(prefix="anla-writers-") as tmp:
        work = Path(tmp)
        for codec, average, metadata, must_match in (("store", 4096, False, True),
                                                     ("store", 262144, False, True),
                                                     ("store", 4096, True, True),
                                                     ("zstd", 4096, True, False)):
            py, rs = work / "py.anla", work / "rs.anla"
            python_pack(corpus, py, codec, average, metadata)
            rust_pack(corpus, rs, codec, average, metadata)
            same = py.read_bytes() == rs.read_bytes()
            label = f"{codec}/avg={average}" + ("/metadata" if metadata else "")

            if same:
                print(f"  {label:<20} byte-identical, {py.stat().st_size:,} bytes")
                continue
            if must_match:
                print(f"  {label:<20} DIFFER — {py.stat().st_size:,} vs "
                      f"{rs.stat().st_size:,} bytes", file=sys.stderr)
                failures += 1
                continue

            # The predicted case. The bytes may differ; the tree may not.
            py_tree, rs_tree = tree_identity(py), tree_identity(rs)
            if py_tree != rs_tree:
                print(f"  {label:<20} DIFFER, and so does the tree — that is not "
                      f"the compressor, that is a defect", file=sys.stderr)
                failures += 1
            else:
                print(f"  {label:<20} bytes differ (different libzstd builds), "
                      f"objects_root and every chunk id identical — §8 as written")

        failures += compare_append(corpus, work)

    if failures:
        print(f"{failures} comparison(s) failed", file=sys.stderr)
        return 1
    print("two writers, no shared code: store is byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
