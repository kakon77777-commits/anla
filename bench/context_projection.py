# -*- coding: utf-8 -*-
"""The claim, on a real transcript: this is compression, not deletion.

    python bench/context_projection.py [transcripts-dir] [--mib 8]


Three things measured, and the third is the only one that distinguishes this from
summarising:

1. what each projection level costs, against the raw context;
2. what it says it left out — a manifest, not a number;
3. **pick any omitted turn and get it back byte for byte.**
"""
import argparse
import pathlib
import random
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))

from anla.fastcdc import CdcProfile
from anla1.context import (LEVELS, expand, project, projection_manifest,
                           read_jsonl, turn_entries)
from anla1.snapshot import (CODEC_ZSTD, cdc_chunker, list_snapshots,
                            write_snapshot)

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("transcripts", nargs="?",
                    default=str(pathlib.Path.home() / ".claude/projects"))
parser.add_argument("--mib", type=int, default=8)
args = parser.parse_args()
MIB = args.mib

found = sorted(pathlib.Path(args.transcripts).rglob("*.jsonl"),
               key=lambda f: -f.stat().st_size)
if not found:
    raise SystemExit(f"no .jsonl transcripts under {args.transcripts}")
src = found[0]
data = src.read_bytes()[:MIB * 1024 * 1024]
data = data[:data.rfind(b"\n") + 1]

turns = read_jsonl(data)
print(f"context: {len(data):,} bytes, {len(turns):,} turns\n")

work = pathlib.Path(tempfile.mkdtemp()) / "context.anla"
started = time.perf_counter()
size = write_snapshot(
    work, files=turn_entries(turns), created_unix_ns=1, archive_id=bytes(16),
    chunker=cdc_chunker(CdcProfile(min_size=4096, avg_size=16384, max_size=65536)),
    codec=CODEC_ZSTD)
archive = work.read_bytes()
snapshot = list_snapshots(archive)[-1]
print(f"the record   {size:>12,} bytes   {100*size/len(data):5.1f}% of raw   "
      f"{len(snapshot.manifest['objects']):,} objects, "
      f"{len(snapshot.manifest['chunks']):,} unique chunks   "
      f"{time.perf_counter()-started:.1f}s")
print(f"             {len(turns) - len(snapshot.manifest['chunks']):,} turns "
      f"deduplicated against another turn\n")

print(f"{'level':<7}{'shown':>12}{'of raw':>9}{'preserved':>11}{'omitted':>9}"
      f"{'expandable':>12}")
projections = {}
for level in LEVELS:
    p = project(turns, level=level, budget_bytes=32_000)
    projections[level] = p
    print(f"{level:<7}{len(p.text.encode('utf-8')):>12,}"
          f"{100*len(p.text.encode('utf-8'))/len(data):>8.2f}%"
          f"{len(p.preserved):>11,}{len(p.omitted):>9,}{str(p.expandable):>12}")

chosen = projections["L1"]
print(f"\nthe L1 omission manifest names {len(chosen.omitted):,} turns. three of them:")
for entry in chosen.omitted[:3]:
    print(f"  {entry['path']}  {entry['bytes']:>7,}b  {entry['role']:<10}"
          f"{(entry['hint'] or '')[:60]}")

# The test. Not "does it look right" — take omitted turns at random, ask the
# archive for them, and compare with the bytes that went in.
by_path = {t.path: t.raw for t in turns}
sample = random.Random(20260814).sample(chosen.omitted, min(200, len(chosen.omitted)))
paths = [entry["path"] for entry in sample]
started = time.perf_counter()
back = expand(archive, paths, snapshot)
elapsed = time.perf_counter() - started

exact = sum(1 for path in paths if back.get(path) == by_path[path])
print(f"\nexpanded {len(paths)} omitted turns in {elapsed:.2f}s")
print(f"  byte-identical to the original: {exact}/{len(paths)}"
      f"{'' if exact == len(paths) else '   <-- THIS IS THE WHOLE CLAIM AND IT FAILED'}")

manifest = projection_manifest(chosen)
print("\nthe manifest a model would carry alongside its context:")
for key in ("level", "expandable", "bytes_shown", "bytes_total", "share_shown"):
    print(f"  {key:<14}{manifest[key]}")
print(f"  omitted       {len(manifest['omitted']):,} entries, each with a path")
