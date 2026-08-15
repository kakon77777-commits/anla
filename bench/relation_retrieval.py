# -*- coding: utf-8 -*-
"""Do the relation edges earn anything? Two measurements, one of them well-powered.

    python bench/relation_retrieval.py <transcript.jsonl> [--backend ollama]

`design/phase-and-relations.md` §6 step 2 says to measure whether edges help against
the no-edges baseline, and that if they do not, that is the answer. This is that
measurement. It is written to be able to return *no*.

**Part A — are the edges semantic at all?** For every stored edge, the cosine between
its two turns, against two controls: random pairs (the floor) and merely *adjacent*
turns (what conversation order already gives away for free). Roughly nine thousand
edges, so this part has real statistical power, and it can produce three different
negatives — edges no better than random means they carry no semantic signal; edges no
better than adjacency means they add nothing to what ordering already knows; edges
far above both means they are *redundant* with the embedding and a retriever using
both learns nothing new.

**Part B — do they help retrieval?** The labelled set, re-scored with a graph bonus.
Its power is poor and the honest thing is to say so before running rather than after
seeing the number:

* Twelve queries. One query is 0.083 of R@1, so nothing below that is visible and
  nothing at that scale is distinguishable from noise.
* `changepoint-v1` already scores **R@5 = 1.00** locally. There is no headroom there
  at all; a graph bonus can only push a correct answer *out* of the top five.
* The whole realistic upside is the three queries whose answer currently sits at rank
  2–5, and moving all three would be the largest result this instrument can report.

So Part B is a sweep, not a selection. Picking the best cell of a grid on twelve
queries and reporting it as the effect would be fitting to the test set; the grid is
printed whole so its shape can be read, and `beta = 0` is in it as a control that must
reproduce the published baseline exactly. If it does not, the harness is wrong and
every other cell is wrong with it.

Using the graph to re-score is not the scalarization Paper 02 §9 forbids. §9 forbids
the *structure* carrying a number; a task choosing how to weigh a typed relation, made
afterwards and for one task, is precisely what it says a scalarization legitimately is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python"))

from anla1.context import read_jsonl                                    # noqa: E402
from anla1.relations import derive_edges                 # noqa: E402
from anla1.segment import (PROJECTION_VERSION, SEGMENT_SCHEMA_VERSION,  # noqa: E402
                           Segment, build_index, digest_of, project_segment)
from segment_retrieval import QUERIES, centred, cosine                  # noqa: E402

#: Fixed before the run. A sweep whose range was chosen after seeing the answer is
#: not a sweep.
BETAS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.40)
SEEDS = (1, 3, 5)


def whole_turn(path: str, raw: bytes) -> str:
    return project_segment(Segment(
        segment_id=f"{path}#whole", source_turn=path, source_digest=digest_of(raw),
        scheme_id="whole-turn-v1", scheme_version=SEGMENT_SCHEMA_VERSION,
        ranges=((0, len(raw)),), kind="turn", ordinal=0,
        projection_version=PROJECTION_VERSION), raw)


def summarise(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {"n": len(values), "mean": round(statistics.fmean(values), 4),
            "median": round(statistics.median(values), 4),
            "p05": round(ordered[int(0.05 * len(ordered))], 4),
            "p95": round(ordered[int(0.95 * len(ordered))], 4)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", type=pathlib.Path)
    parser.add_argument("--backend", default="ollama", choices=("ollama", "openai"))
    parser.add_argument("--model", default="nomic-embed-text")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--dimensions", type=int, default=768)
    parser.add_argument("--scheme", default="changepoint-v1")
    parser.add_argument("--budget", type=int, default=5000,
                        help="segments embedded for part B; matches the baseline run")
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("bench/relation_retrieval.json"))
    parser.add_argument("--cache", action="store_true",
                        help="reuse embeddings keyed by text digest and model identity")
    args = parser.parse_args()

    identity = None
    if args.backend == "ollama":
        from anla1.backends import backend_for
        engine = backend_for("ollama", host=args.host)
        identity = engine.identity(args.model)
        model = identity.model.split(":", 1)[1]
        print(f"backend: {identity.model} @ {identity.dimensions}d, "
              f"revision {identity.revision[:16]}")

        def embed(texts: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for i in range(0, len(texts), 64):
                out.extend(engine.embed([t[:6000] or " " for t in texts[i:i + 64]],
                                        model))
                print(f"    embedded {min(i + 64, len(texts))}/{len(texts)}",
                      file=sys.stderr)
            return out
    else:
        from openai import OpenAI
        client = OpenAI(timeout=60.0, max_retries=8)

        def embed(texts: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for i in range(0, len(texts), 128):
                reply = client.embeddings.create(
                    model=args.model, dimensions=args.dimensions,
                    input=[t[:6000] or " " for t in texts[i:i + 128]])
                out.extend(item.embedding
                           for item in sorted(reply.data, key=lambda x: x.index))
                print(f"    embedded {min(i + 128, len(texts))}/{len(texts)}",
                      file=sys.stderr)
            return out

    data = args.transcript.read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    turns = read_jsonl(data)
    raws = {t.path: t.raw for t in turns}
    digest = hashlib.blake2b(data, digest_size=16).hexdigest()
    print(f"{len(turns):,} turns, corpus digest {digest[:16]}")

    # Twelve thousand embeddings is twenty minutes, and the question being asked here
    # changed three times while the answer sat in the same vectors. Cached under the
    # *text's* digest and the model identity, not the corpus digest — so a changed
    # projection, a re-pulled model or a different transcript all miss, and a cache
    # cannot quietly answer a question about text it never saw.
    cache_key = f"{identity.model if identity else args.model}|" \
                f"{identity.revision if identity else ''}|{PROJECTION_VERSION}"
    cache_path = args.out.with_suffix(".vectors.json")
    cache: dict[str, list[float]] = {}
    if args.cache and cache_path.exists():
        held = json.loads(cache_path.read_text(encoding="utf-8"))
        if held.get("key") == cache_key:
            cache = held["vectors"]
            print(f"  cache: {len(cache):,} vectors from {cache_path.name}")
        else:
            print(f"  cache: ignored, it was written by {held.get('key')!r}")

    raw_embed = embed

    def embed(texts: list[str]) -> list[list[float]]:            # noqa: F811
        if not args.cache:
            return raw_embed(texts)
        keys = [hashlib.blake2b(t.encode("utf-8"), digest_size=16).hexdigest()
                for t in texts]
        absent = [i for i, k in enumerate(keys) if k not in cache]
        if absent:
            print(f"    {len(absent):,} of {len(texts):,} not cached")
            for i, vector in zip(absent, raw_embed([texts[i] for i in absent])):
                cache[keys[i]] = vector
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"key": cache_key, "vectors": cache}),
                                  encoding="utf-8")
        return [cache[k] for k in keys]

    edges = derive_edges(turns)
    by_kind: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        by_kind.setdefault(edge["kind"], []).append((edge["from"], edge["to"]))
    print(f"{len(edges):,} edges: "
          + ", ".join(f"{k} {len(v):,}" for k, v in sorted(by_kind.items())))

    # ---------------------------------------------------------------- part A
    print("\npart A — are the edges semantic at all?")
    ordered_paths = [t.path for t in turns]
    texts = [whole_turn(p, raws[p]) for p in ordered_paths]
    keep = [i for i, t in enumerate(texts) if len(t) >= 40]
    print(f"  embedding {len(keep):,} turns at whole-turn granularity")
    vectors = dict(zip([ordered_paths[i] for i in keep],
                       embed([texts[i] for i in keep])))
    vectors, _ = centred(vectors)

    def score_pairs(pairs) -> list[float]:
        return [cosine(vectors[a], vectors[b]) for a, b in pairs
                if a in vectors and b in vectors and a != b]

    rng = random.Random(20260815)
    present = [p for p in ordered_paths if p in vectors]
    part_a = {
        "random": summarise(score_pairs(
            [(rng.choice(present), rng.choice(present)) for _ in range(8000)])),
        # the free baseline: what conversation order gives away without a graph
        "adjacent": summarise(score_pairs(list(zip(present, present[1:])))),
    }
    # Each kind whole, then split by whether it links turns ordering already puts
    # side by side. Without the split the two populations are averaged together and
    # a kind that is 90% adjacency reports a mean that is mostly adjacency's — which
    # is how `replies-to` first looked like a weak relation rather than a mostly
    # redundant one. The gap is what separates a graph from a sequence.
    order = {path: i for i, path in enumerate(ordered_paths)}
    for kind in sorted(by_kind):
        pairs = by_kind[kind]
        near = [p for p in pairs if abs(order[p[0]] - order[p[1]]) == 1]
        far = [p for p in pairs if abs(order[p[0]] - order[p[1]]) > 1]
        part_a[kind] = summarise(score_pairs(pairs))
        part_a[kind]["adjacent_share"] = round(len(near) / len(pairs), 3) if pairs else None
        part_a[f"{kind} (gap>1)"] = summarise(score_pairs(far))
        part_a[f"{kind} (gap>1)"]["max_gap"] = (
            max(abs(order[a] - order[b]) for a, b in far) if far else 0)

    width = max(len(k) for k in part_a)
    print(f"  {'relation':<{width}} {'n':>7} {'mean':>8} {'median':>8} "
          f"{'p05':>8} {'p95':>8} {'adj':>6}")
    for name, row in part_a.items():
        if not row["n"]:
            continue
        share = row.get("adjacent_share")
        print(f"  {name:<{width}} {row['n']:>7,} {row['mean']:>+8.4f} "
              f"{row['median']:>+8.4f} {row['p05']:>+8.4f} {row['p95']:>+8.4f} "
              + (f"{share:>6.1%}" if share is not None else " " * 6))

    # ---------------------------------------------------------------- part B
    print(f"\npart B — does the graph help retrieval? ({args.scheme})")
    index = build_index([(t.path, t.raw) for t in turns], args.scheme)
    views = {}
    for seg in index.segments:
        try:
            text = project_segment(seg, raws[seg.source_turn])
        except Exception:                                              # noqa: BLE001
            continue
        if len(text) >= 40:
            views[seg.segment_id] = (seg, text)

    truth = {question: {sid for sid, (_, text) in views.items()
                        if anchor.lower() in text.lower()}
             for question, anchor in QUERIES}
    # Same sample as the baseline row: same seed, same budget, same order, so the
    # two runs differ in the graph bonus and in nothing else.
    held = {sid for found in truth.values() for sid in found}
    rest = [sid for sid in views if sid not in held]
    random.Random(20260814).shuffle(rest)
    chosen = list(held) + rest[:max(0, args.budget - len(held))]
    print(f"  embedding {len(chosen):,} segments ({len(held)} carry an answer)")

    seg_vectors = dict(zip(chosen, embed([views[s][1] for s in chosen])))
    seg_vectors, _ = centred(seg_vectors)
    question_vectors = dict(zip([q for q, _ in QUERIES],
                                embed([q for q, _ in QUERIES])))

    turn_of = {sid: views[sid][0].source_turn for sid in seg_vectors}
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], set()).add(edge["to"])
        adjacency.setdefault(edge["to"], set()).add(edge["from"])

    keys = list(seg_vectors)
    answerable = [q for q, _ in QUERIES if truth[q]]
    base_rank: dict[str, list[str]] = {}
    for question in answerable:
        qv = question_vectors[question]
        base_rank[question] = sorted(
            keys, key=lambda s: -cosine(qv, seg_vectors[s]))

    grid = {}
    for k in SEEDS:
        for beta in BETAS:
            ranks = []
            for question in answerable:
                qv = question_vectors[question]
                plain = {s: cosine(qv, seg_vectors[s]) for s in keys}
                near = set()
                for seed in base_rank[question][:k]:
                    near |= adjacency.get(turn_of[seed], set())
                ranked = sorted(keys, key=lambda s: -(
                    plain[s] + (beta if turn_of[s] in near else 0.0)))
                ranks.append(next((i + 1 for i, s in enumerate(ranked)
                                   if s in truth[question]), None))
            found = [r for r in ranks if r]
            n = len(answerable)
            grid[f"k={k},beta={beta}"] = {
                "seeds": k, "beta": beta,
                "recall_at_1": round(sum(1 for r in found if r == 1) / n, 3),
                "recall_at_5": round(sum(1 for r in found if r <= 5) / n, 3),
                "mrr": round(sum(1 / r for r in found) / n, 3),
                "queries_at_rank_1": sum(1 for r in found if r == 1),
                "median_rank": statistics.median(found) if found else None,
                # Per query, because the aggregate on twelve queries cannot show
                # whether a cell moved one query or shuffled three. Those are
                # different findings and R@1 reports them the same.
                "ranks": dict(zip(answerable, ranks)),
            }

    print(f"  {'seeds':>6} {'beta':>6} {'R@1':>7} {'R@5':>7} {'MRR':>7} "
          f"{'at rank 1':>11}")
    for row in grid.values():
        print(f"  {row['seeds']:>6} {row['beta']:>6.2f} {row['recall_at_1']:>7.3f} "
              f"{row['recall_at_5']:>7.3f} {row['mrr']:>7.3f} "
              f"{row['queries_at_rank_1']:>7}/{len(answerable)}")

    control = grid[f"k={SEEDS[0]},beta=0.0"]
    best = max(grid.values(), key=lambda r: r["mrr"])
    delta = best["mrr"] - control["mrr"]
    resolution = round(1 / len(answerable), 3)

    moved = {q: (control["ranks"][q], best["ranks"][q]) for q in answerable
             if control["ranks"][q] != best["ranks"][q]}
    hurt = [name for name, row in grid.items()
            if row["recall_at_5"] < control["recall_at_5"]]


    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "model": identity.model if identity else args.model,
        "revision": identity.revision if identity else None,
        "dimensions": identity.dimensions if identity else args.dimensions,
        "corpus_digest": digest, "turns": len(turns), "edges": len(edges),
        "edges_by_kind": {k: len(v) for k, v in sorted(by_kind.items())},
        "scheme": args.scheme, "queries": len(answerable),
        "resolution_of_one_query": resolution,
        "part_a_pair_similarity": part_a,
        "part_b_grid": grid,
        "part_b_control_beta_zero": control,
        "part_b_best_cell": best,
        "part_b_queries_that_moved": {q: {"control": a, "best": b}
                                      for q, (a, b) in moved.items()},
        "part_b_cells_where_recall_at_5_got_worse": hurt,
        "part_b_best_minus_control_mrr": round(delta, 3),
        "part_b_within_noise": abs(delta) < resolution,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n  control (beta=0)  MRR {control['mrr']:.3f}, "
          f"{control['queries_at_rank_1']}/{len(answerable)} at rank 1")
    print(f"  best cell         MRR {best['mrr']:.3f} at k={best['seeds']}, "
          f"beta={best['beta']}")
    print(f"  difference        {delta:+.3f}, and one query is {resolution:.3f} — "
          + ("inside the noise floor" if abs(delta) < resolution
             else "larger than one query"))
    print(f"  queries that moved: {len(moved)} of {len(answerable)}")
    for question, (was, now) in moved.items():
        print(f"    rank {was} -> {now}   {question[:64]}")
    if hurt:
        print(f"  cells where R@5 got worse: {', '.join(hurt)} — the bonus can push "
              f"a correct answer out of the top five, so this is two-sided")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
