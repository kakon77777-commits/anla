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


def python_pack(corpus: Path, out: Path, codec: str, average: int) -> None:
    from anla1.cli import main

    argv = ["pack", str(corpus), "-o", str(out), "--no-metadata", "--force",
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


def rust_pack(corpus: Path, out: Path, codec: str, average: int) -> None:
    argv = [str(RUST), "pack", str(corpus), "-o", str(out),
            "--codec", codec, "--chunk-avg", str(average),
            "--uuid", UUID, "--created-ns", CREATED]
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


def main(argv: list[str]) -> int:
    corpus = Path(argv[0]) if argv else ROOT / "test_demo"
    if not RUST.exists():
        print(f"{RUST} is not built — run `cargo build --release` in rust/",
              file=sys.stderr)
        return 2

    failures = 0
    with tempfile.TemporaryDirectory(prefix="anla-writers-") as tmp:
        work = Path(tmp)
        for codec, average, must_match in (("store", 4096, True),
                                           ("store", 262144, True),
                                           ("zstd", 4096, False)):
            py, rs = work / "py.anla", work / "rs.anla"
            python_pack(corpus, py, codec, average)
            rust_pack(corpus, rs, codec, average)
            same = py.read_bytes() == rs.read_bytes()
            label = f"{codec}/avg={average}"

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

    if failures:
        print(f"{failures} comparison(s) failed", file=sys.stderr)
        return 1
    print("two writers, no shared code: store is byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
