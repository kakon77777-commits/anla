# -*- coding: utf-8 -*-
"""A context does not arrive whole. It grows, and it is saved again and again.

    python bench/context_growth.py [transcripts-dir] [--mib 32]


Compressing one finished transcript is the wrong question — ANLA loses that one to
plain zstd by more than two to one, because zstd sees repetition across the entire
stream while ANLA compresses each chunk alone so any chunk can be read without the
others. That is a real cost and it buys random access.

The question that matters is what it costs to *keep* a context as it grows: ten
checkpoints of a conversation, each one mostly the previous one. Against the
alternative anyone would actually reach for — recompressing the whole thing each
time — and against keeping only the newest, which is what a summariser does and is
not the same product.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))
import zstandard  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUST = next(p for p in (ROOT / "rust/target/release").glob("anla1-rs*") if p.suffix in ("", ".exe"))
import argparse
import tempfile

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("transcripts", nargs="?",
                    default=str(pathlib.Path.home() / ".claude/projects"),
                    help="a directory of .jsonl session transcripts")
parser.add_argument("--mib", type=int, default=32)
parser.add_argument("-o", "--work", default="")
args = parser.parse_args()

_scratch = None if args.work else tempfile.TemporaryDirectory()
WORK = pathlib.Path(args.work or _scratch.name)
SOURCE = pathlib.Path(args.transcripts)

found = sorted(SOURCE.rglob("*.jsonl"), key=lambda f: -f.stat().st_size)
if not found:
    raise SystemExit(f"no .jsonl transcripts under {SOURCE}")
biggest = found[0]
print(f"corpus: {biggest.name} ({biggest.stat().st_size:,} bytes on disk)")
whole = biggest.read_bytes()[:args.mib * 1024 * 1024]
whole = whole[:whole.rfind(b"\n") + 1]
lines = whole.splitlines(keepends=True)

STEPS = 10
tree = WORK / "tree"
tree.mkdir(parents=True, exist_ok=True)
archive = WORK / "growing.anla"
archive.unlink(missing_ok=True)

compressor = zstandard.ZstdCompressor(level=10)
anla_total = zstd_each = zstd_newest = 0
print(f"{'checkpoint':<12}{'context':>13}{'ANLA adds':>12}{'zstd whole':>12}"
      f"{'ANLA total':>13}{'zstd total':>13}")

for step in range(1, STEPS + 1):
    cut = len(lines) * step // STEPS
    payload = b"".join(lines[:cut])
    (tree / "session.jsonl").write_bytes(payload)

    before = archive.stat().st_size if archive.exists() else 0
    command = [str(RUST), "append" if before else "pack"]
    command += ([str(archive), "-o", str(tree)] if before
                else [str(tree), "-o", str(archive)])
    command += ["--chunking", "cdc", "--chunk-avg", "16384", "--codec", "zstd"]
    done = subprocess.run(command, capture_output=True, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit((done.stdout or done.stderr)[:400])
    after = archive.stat().st_size

    # What it costs to keep every checkpoint the other way: recompress the whole
    # context each time and keep all ten files.
    whole_now = len(compressor.compress(payload))
    zstd_each += whole_now
    zstd_newest = whole_now
    anla_total = after

    print(f"{step:<12}{len(payload):>13,}{after - before:>12,}{whole_now:>12,}"
          f"{anla_total:>13,}{zstd_each:>13,}")

print()
print(f"keeping all {STEPS} checkpoints:")
print(f"  ANLA archive                 {anla_total:>13,}")
print(f"  one zstd file per checkpoint {zstd_each:>13,}   "
      f"{zstd_each / anla_total:.1f}x ANLA")
print(f"  only the newest zstd file    {zstd_newest:>13,}   "
      f"— but the earlier nine are gone, which is a different product")
