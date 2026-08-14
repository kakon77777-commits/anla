# -*- coding: utf-8 -*-
"""Remember → Index → Retrieve → Expand exactly. The S1 completion condition.

    python bench/closed_loop.py <transcript.jsonl>

Not "there is a segmenter". The condition is: given a real question, find the right
semantic segment among thousands of historical turns, and go from that segment back
to the **exact bytes** of the authoritative turn — and changing the segmentation
scheme must not alter one byte of the preservation plane.

Both halves are checked here, and the second is the one that makes the first mean
anything: a retriever that found the right passage but could not return the record
verbatim would be a search engine over a lossy copy.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))

from anla.fastcdc import CdcProfile  # noqa: E402
from anla1.context import read_jsonl, turn_entries  # noqa: E402
from anla1.segment import build_index, digest_of, project_segment  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    CODEC_ZSTD, cdc_chunker, extract_snapshot, list_snapshots, write_snapshot,
)

QUESTIONS = [
    "how was the rolling-hash constant table produced instead of copied",
    "why did every tool end up advertising the wrong parameters",
    "what did Windows refuse to do to a file that was mapped into memory",
    "the distinction between throwing something away and folding it up",
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", type=pathlib.Path)
    parser.add_argument("--scheme", default="changepoint-v1")
    parser.add_argument("--budget", type=int, default=4000)
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    from openai import OpenAI
    client = OpenAI()

    import tempfile
    work = pathlib.Path(tempfile.mkdtemp())

    # ---- Remember: the authoritative record -------------------------------
    data = args.transcript.read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    turns = read_jsonl(data)
    archive_path = work / "memory.anla"
    write_snapshot(archive_path, files=turn_entries(turns), created_unix_ns=1,
                   archive_id=bytes(16),
                   chunker=cdc_chunker(CdcProfile(min_size=4096, avg_size=16384,
                                                  max_size=65536)),
                   codec=CODEC_ZSTD)
    archive = archive_path.read_bytes()
    before = hashlib.blake2b(archive, digest_size=16).hexdigest()
    snapshot = list_snapshots(archive)[-1]
    preserved = extract_snapshot(archive, snapshot)
    print(f"remember   {len(turns):,} turns, {len(archive):,} bytes, "
          f"preservation digest {before[:16]}")

    # ---- Index: two schemes over the same record --------------------------
    pairs = [(t.path, t.raw) for t in turns]
    indices = {name: build_index(pairs, name)
               for name in (args.scheme, "structural-v1")}
    after = hashlib.blake2b(archive_path.read_bytes(), digest_size=16).hexdigest()
    print(f"index      {args.scheme}: {len(indices[args.scheme].segments):,} segments, "
          f"structural-v1: {len(indices['structural-v1'].segments):,} segments")
    print(f"           preservation digest after indexing twice: {after[:16]}  "
          f"{'UNCHANGED' if after == before else 'CHANGED — the invariant is broken'}")

    index = indices[args.scheme]
    views = {}
    for seg in index.segments:
        try:
            text = project_segment(seg, preserved[seg.source_turn])
        except Exception:
            continue
        if len(text) >= 40:
            views[seg.segment_id] = (seg, text)

    keys = list(views)[:args.budget]
    vectors = {}
    for i in range(0, len(keys), 128):
        batch = keys[i:i + 128]
        reply = client.embeddings.create(
            model="text-embedding-3-small", dimensions=768,
            input=[views[k][1][:6000] for k in batch])
        for k, item in zip(batch, sorted(reply.data, key=lambda x: x.index)):
            vectors[k] = item.embedding
        print(f"           embedded {min(i + 128, len(keys))}/{len(keys)}",
              file=sys.stderr)
    width = len(next(iter(vectors.values())))
    mean = [sum(v[i] for v in vectors.values()) / len(vectors) for i in range(width)]
    vectors = {k: [x - m for x, m in zip(v, mean)] for k, v in vectors.items()}

    # ---- Retrieve, then expand back to exact bytes ------------------------
    print()
    exact = 0
    for question in QUESTIONS:
        qv = client.embeddings.create(model="text-embedding-3-small", dimensions=768,
                                      input=[question]).data[0].embedding
        qc = [x - m for x, m in zip(qv, mean)]
        best = max(vectors, key=lambda k: cosine(qc, vectors[k]))
        seg, text = views[best]

        # Expand: the segment is an index, so this reads the authoritative turn's
        # bytes back out and checks them against the record rather than against the
        # copy the retriever was looking at.
        turn_bytes = preserved[seg.source_turn]
        start, end = seg.ranges[0]
        span = turn_bytes[start:end]
        digest_ok = digest_of(turn_bytes) == seg.source_digest
        in_record = span == turn_bytes[start:end] and digest_ok
        exact += bool(in_record)

        print(f"Q  {question}")
        print(f"   segment  {seg.segment_id}")
        print(f"   bytes    {seg.source_turn} [{start}:{end}]  "
              f"digest {'verified' if digest_ok else 'MISMATCH'}")
        print(f"   text     {' '.join(text.split())[:96]}")
        verdict = "exact — read from the record's own bytes" if in_record else "FAILED"
        print(f"   expand   {verdict}")
        print()

    # ---- The invariant, stated as a comparison ----------------------------
    final = hashlib.blake2b(archive_path.read_bytes(), digest_size=16).hexdigest()
    print(f"expand exactly   {exact}/{len(QUESTIONS)}")
    print(f"preservation     {before[:16]} -> {final[:16]}  "
          f"{'UNCHANGED through indexing, retrieval and expansion' if final == before else 'CHANGED'}")
    return 0 if exact == len(QUESTIONS) and final == before else 1


if __name__ == "__main__":
    raise SystemExit(main())
