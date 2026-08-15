# -*- coding: utf-8 -*-
"""Does segmentation make semantic addressing work? Measured, with ground truth.

    python bench/segment_retrieval.py <transcript.jsonl> [--budget 6000]

The gate, fixed before any of this was built:

    centred random-pair p95          must fall below +0.15   (turn-level: +0.238)
    best match for a real question   must land clearly above random p95

and, because those two say only that the geometry is workable rather than that
retrieval works, a labelled query set measuring **Recall@1, Recall@5, MRR**.

**How the labels are made honest.** Each question is about a fact that is in this
conversation, and its ground truth is located by exact search for a distinctive
anchor string — `anla-gear-1`, `functools.wraps`, `0.317`. The *question* is then
written to avoid the anchor entirely. So the label comes from a string match the
retriever never sees, and the query is exactly the case lexical matching cannot
answer. A question that shared words with its answer would measure nothing.

If segmentation does not move these numbers it did not work, and no reweighting of
Ψ will be offered in place of moving them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))

from anla1.context import read_jsonl  # noqa: E402
from anla1.segment import SCHEMES, build_index, project_segment  # noqa: E402

#: (question, anchor). The anchor locates the truth; the question avoids it.
QUERIES = [
    ("how was the rolling-hash constant table produced instead of copied",
     "anla-gear-1"),
    ("what was the writer's throughput with content-defined boundaries",
     "3.9 MiB/s"),
    ("why did every tool end up advertising the wrong parameters",
     "functools.wraps"),
    ("what did Windows refuse to do to a file that was mapped into memory",
     "will not truncate a memory-mapped"),
    ("the broken archive that both readers said was fine",
     "archive_id"),
    ("what does an unchanged checkpoint cost per turn",
     "352 bytes"),
    ("how similar were two unrelated pieces of this conversation",
     "0.317"),
    ("why are odd nodes promoted rather than duplicated in the tree",
     "2012-2459"),
    ("the distinction between throwing something away and folding it up",
     "永久刪除與可展開壓縮"),
    ("the test for whether a cut belongs to this framework at all",
     "同一性判據"),
    ("what happened when the fuzzer's mutations never got past the hash",
     "shielding the parser"),
    ("why did the benchmark's own numbers stop being comparable between runs",
     "live repository"),
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def centred(vectors: dict[str, list[float]]):
    keys = list(vectors)
    width = len(vectors[keys[0]])
    mean = [sum(vectors[k][i] for k in keys) / len(keys) for i in range(width)]
    return {k: [x - m for x, m in zip(v, mean)] for k, v in vectors.items()}, mean


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", type=pathlib.Path)
    parser.add_argument("--budget", type=int, default=6000,
                        help="segments embedded per scheme")
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--backend", default="openai", choices=("openai", "ollama"),
                        help="openai needs a key; ollama runs on this machine")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--schemes", default="",
                        help="comma-separated subset, for re-running one row")
    parser.add_argument("--merge", action="store_true",
                        help="keep rows already in --out that this run did not produce")
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("bench/segment_retrieval.json"))
    args = parser.parse_args()

    # Two backends on identical ground: same corpus digest, same twelve labelled
    # queries, same schemes. That is the only way the comparison means anything —
    # and it is the comparison that decides whether the local model is a real
    # replacement or a convenient one.
    local = None
    if args.backend == "ollama":
        from anla1.backends import backend_for
        local = backend_for("ollama", host=args.host)
        identity = local.identity(args.model)
        args.model, args.dimensions = identity.model, identity.dimensions
        print(f"backend: {identity.model} @ {identity.dimensions}d, "
              f"revision {identity.revision[:16]}")
    elif not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set (or pass --backend ollama)")
    from openai import OpenAI
    # A 429 killed this run after three of four schemes, twenty minutes and about
    # 15,000 embeddings in — and the harness had no retry, which is the same defect
    # already found and fixed in tools/mcp/make_vectors.py and never carried across
    # to here. The timeout is short for the same reason it is short there: a client
    # retrying at the 600-second default sits at zero CPU for half an hour and looks
    # exactly like a hang.
    client = None if local is not None else OpenAI(timeout=60.0, max_retries=8)

    data = args.transcript.read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    turns = read_jsonl(data)
    raws = {t.path: t.raw for t in turns}
    # Pin what was measured. The transcript this runs on is the session that is
    # writing it, so it grows between runs and two rows produced days apart are
    # rows about different corpora. `--merge` makes that easy to do by accident,
    # so the digest is recorded and a merge across digests is refused below.
    digest = hashlib.blake2b(data, digest_size=16).hexdigest()
    print(f"{len(turns):,} turns, corpus digest {digest[:16]}\n")

    def embed(texts: list[str]) -> list[list[float]]:
        if local is not None:
            model = args.model.split(":", 1)[1]
            out = []
            for i in range(0, len(texts), 64):
                out.extend(local.embed([t[:6000] or " " for t in texts[i:i + 64]],
                                       model))
                print(f"    embedded {min(i + 64, len(texts))}/{len(texts)}",
                      file=sys.stderr)
            return out
        out = []
        for i in range(0, len(texts), 128):
            batch = [t[:6000] or " " for t in texts[i:i + 128]]
            # The SDK retries a 429 on its own; this is the outer wait for the case
            # where a whole run is over the per-minute token budget and no amount of
            # sub-second backoff helps. A partial table is worse than a slow one:
            # the whole output is a comparison between rows.
            for attempt in range(6):
                try:
                    reply = client.embeddings.create(
                        model=args.model, dimensions=args.dimensions, input=batch)
                    break
                except Exception as failure:                        # noqa: BLE001
                    transient = any(mark in str(failure).lower() for mark in
                                    ("rate limit", "429", "timeout", "502", "503",
                                     "504", "overloaded"))
                    if not transient or attempt == 5:
                        raise
                    wait = 5 * 2 ** attempt
                    print(f"    {type(failure).__name__}, waiting {wait}s "
                          f"(attempt {attempt + 1}/6)", file=sys.stderr)
                    time.sleep(wait)
            out.extend(item.embedding for item in
                       sorted(reply.data, key=lambda x: x.index))
            print(f"    embedded {min(i + 128, len(texts))}/{len(texts)}",
                  file=sys.stderr)
        return out

    question_vectors = dict(zip([q for q, _ in QUERIES],
                                embed([q for q, _ in QUERIES])))

    wanted = [s.strip() for s in args.schemes.split(",") if s.strip()] or list(SCHEMES)
    unknown = [s for s in wanted if s not in SCHEMES]
    if unknown:
        raise SystemExit(f"unknown scheme(s) {unknown}; have {sorted(SCHEMES)}")

    results = {}
    if args.merge and args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))
        if previous.get("corpus_digest") != digest:
            raise SystemExit(
                f"{args.out} holds rows measured on corpus "
                f"{(previous.get('corpus_digest') or 'unrecorded')[:16]} "
                f"({previous.get('turns')} turns) and this is {digest[:16]} "
                f"({len(turns)} turns). Merging would put two different corpora in "
                f"one table and the comparison between rows — which is the entire "
                f"output — would be meaningless. Re-run every scheme against one "
                f"transcript, or write to a different --out. A file with no recorded "
                f"digest is refused for the same reason: it cannot be shown to be "
                f"this corpus.")
        results.update(previous["schemes"])

    def save():
        """Written after every scheme, not at the end.

        A 429 on the fourth scheme discarded three schemes' worth of measurements
        and twenty minutes of embedding, because the only write was after the loop.
        Each row is complete when it is written, so a partial file is a partial
        table rather than a wrong one — and it says which schemes are in it.
        """
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"model": args.model, "dimensions": args.dimensions,
             "turns": len(turns), "corpus_digest": digest, "corpus_bytes": len(data),
             "queries": len(QUERIES), "schemes_requested": wanted,
             "complete": set(wanted) <= set(results), "schemes": results},
            ensure_ascii=False, indent=1), encoding="utf-8")

    for scheme in wanted:
        index = build_index([(t.path, t.raw) for t in turns], scheme)
        views = {}
        for seg in index.segments:
            try:
                text = project_segment(seg, raws[seg.source_turn])
            except Exception:
                continue
            if len(text) >= 40:
                views[seg.segment_id] = (seg, text)

        # Ground truth: which segments actually contain each anchor.
        truth = {}
        for question, anchor in QUERIES:
            truth[question] = {sid for sid, (_, text) in views.items()
                               if anchor.lower() in text.lower()}

        # Every truth-bearing segment is embedded, plus a random sample up to the
        # budget — so recall is measured against a large corpus without paying to
        # embed all of it, and never by quietly shrinking the haystack.
        keep = {sid for found in truth.values() for sid in found}
        rest = [sid for sid in views if sid not in keep]
        random.Random(20260814).shuffle(rest)
        chosen = list(keep) + rest[:max(0, args.budget - len(keep))]

        print(f"{scheme}: {len(index.segments):,} segments, embedding "
              f"{len(chosen):,} ({len(keep)} carry an answer)")
        vectors = dict(zip(chosen, embed([views[s][1] for s in chosen])))
        vectors, _ = centred(vectors)

        keys = list(vectors)
        rng = random.Random(7)
        pairs = [(rng.choice(keys), rng.choice(keys)) for _ in range(4000)]
        randoms = [cosine(vectors[a], vectors[b]) for a, b in pairs if a != b]
        p95 = sorted(randoms)[int(0.95 * len(randoms))]

        ranks, answerable = [], 0
        for question, _ in QUERIES:
            if not truth[question]:
                continue
            answerable += 1
            qv = question_vectors[question]
            ranked = sorted(keys, key=lambda s: -cosine(qv, vectors[s]))
            hit = next((i + 1 for i, s in enumerate(ranked) if s in truth[question]),
                       None)
            ranks.append(hit)

        found = [r for r in ranks if r]
        results[scheme] = {
            "segments": len(index.segments),
            "embedded": len(chosen),
            "answerable_queries": answerable,
            "random_p95_centred": round(p95, 4),
            "recall_at_1": round(sum(1 for r in found if r == 1) / answerable, 3),
            "recall_at_5": round(sum(1 for r in found if r <= 5) / answerable, 3),
            "mrr": round(sum(1 / r for r in found) / answerable, 3),
            "median_rank": statistics.median(found) if found else None,
            "gate_p95": p95 < 0.15,
        }
        row = results[scheme]
        save()
        print(f"    p95 {row['random_p95_centred']:+.3f}  R@1 {row['recall_at_1']:.2f}  "
              f"R@5 {row['recall_at_5']:.2f}  MRR {row['mrr']:.3f}  "
              f"median rank {row['median_rank']}\n")

    save()
    print(f"{'scheme':<18}{'p95':>8}{'R@1':>7}{'R@5':>7}{'MRR':>7}{'gate':>7}")
    for scheme, row in results.items():
        print(f"{scheme:<18}{row['random_p95_centred']:>+8.3f}{row['recall_at_1']:>7.2f}"
              f"{row['recall_at_5']:>7.2f}{row['mrr']:>7.3f}"
              f"{'pass' if row['gate_p95'] else 'FAIL':>7}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
