# Relation edges, measured: two of the three are adjacency with a label

`design/phase-and-relations.md` §6 set the order — build typed edges, then *measure
whether they help*, and "if they do not, that is the answer." They were built, and
measured, and the answer is mostly no. This is that result.

Everything below is on one pinned corpus: **6,581 turns, digest `38c5455779cbe268`**,
the same one the segmentation benchmark used, embedded with
`nomic-embed-text` at 768d, revision `0a109f422b47e3a3`. Reproduce with:

```bash
python bench/relation_retrieval.py <transcript.jsonl> --backend ollama --cache
```

---

## What was built

`python/anla1/relations.py` derives **9,050 edges**, populating the `edges` field that
`SegmentIndex` had reserved and left empty since it was written. Three kinds, and only
what the record states outright:

| kind | n | derived from |
|---|---:|---|
| `replies-to` | 5,244 | the record's `parentUuid` |
| `tool-result-of` | 1,737 | `tool_use.id` matching `tool_result.tool_use_id` |
| `mentions-path` | 2,069 | the same literal path string in both turns |

Each edge carries a *kind* and the evidence that produced it, never a score — Paper 02
§9 puts scalarization after the structure as a task choice, and a weight stored on the
edge would collapse the thing the graph exists to keep apart. `verify_edges` re-derives
the whole set and compares, so a stored graph that has drifted from its record fails
rather than being believed.

Three kinds the design named are **not stored because the segment tuple already implies
them** — `same-turn`, `next-in-turn`, `next-turn`. Three more are **not derivable at
all** — `supersedes`, `supports`, `contradicts` are judgements about content, not facts
the record states, and they stay listed with that reason rather than quietly dropped.

Reachable as `anla1 context relate`, and over MCP as `context_relate` (writing,
withdrawn under `--share`) and `context_relations` (read-only, derives in memory when no
sidecar holds edges, and says so).

---

## Part A: are the edges semantic at all?

Cosine between the two turns of every edge, against two controls — random pairs, and
merely **adjacent** turns, which is what conversation order gives away for free. Roughly
nine thousand edges, so this part has power.

| relation | n | mean cosine | vs adjacency |
|---|---:|---:|---:|
| random | 7,999 | +0.0074 | 0.04× |
| **adjacent** | 6,580 | **+0.1850** | 1.00× |
| `mentions-path` | 2,069 | +0.4723 | 2.55× |
| `replies-to` | 5,244 | +0.1974 | 1.07× |
| `tool-result-of` | 1,737 | +0.2785 | 1.51× |

Read alone, that table says every kind beats random and the graph is worth having. It is
misleading, and the thing it hides is topological rather than semantic:

**90.6% of `replies-to` edges connect turns that are already adjacent.** So do 90.6% of
`tool-result-of`. Of all 9,050 edges, only **2,035 link a pair that ordering does not
already put side by side** — 78% of the graph reproduces adjacency, which is precisely
the relation this module declines to store on the grounds that it is implied.

Splitting each kind by whether it spans a gap makes the result unambiguous:

| relation | n | mean cosine | vs adjacency |
|---|---:|---:|---:|
| `mentions-path` (gap > 1) | 1,576 | **+0.4473** | **2.42×** |
| `tool-result-of` (gap > 1) | 164 | +0.1324 | 0.72× |
| `replies-to` (gap > 1) | 495 | +0.0887 | **0.48×** |

**`replies-to` is adjacency with a label.** Its apparent strength was borrowed: the tenth
of it that is not adjacency scores *below* plain ordering, at roughly half. Same shape
for `tool-result-of`. Only `mentions-path` survives the split — it is 76% long-range,
reaches up to **5,103 turns**, and its long-range portion is still 2.42× adjacency.

So the semantic content of this graph is concentrated in about 1,576 edges, and the other
7,474 are either ordering restated or weaker than ordering.

**This does not make `replies-to` useless — it makes it structural rather than
semantic.** The conversation DAG answers *what replied to what*, and its 495 branch edges
are exactly where the record stops being a list. Cosine is the wrong instrument for that
job, and the finding is that it must not be used as a semantic signal, not that it must
be deleted. Likewise `tool-result-of`: knowing *which* adjacent pair is a call and its
result is information no ordering carries, even when the topology is identical.

---

## Part B: does the graph help retrieval?

The twelve labelled queries, re-scored with a graph bonus: seeds = top-*k* by cosine,
then a fixed additive β for any candidate whose turn is one hop from a seed.

The instrument's limits were stated before the run rather than after seeing the number.
Twelve queries means one query is 0.083 of R@1 and nothing finer is visible;
`changepoint-v1` already scores **R@5 = 1.00**, so there is no headroom there and a bonus
can only push a correct answer out. The whole realistic upside was the three queries
sitting at rank 2–5.

| seeds | β | R@1 | R@5 | MRR |
|---:|---:|---:|---:|---:|
| 1 | 0.00 | 0.750 | 1.000 | 0.861 |
| 1 | 0.05 | 0.833 | 1.000 | 0.903 |
| 1 | 0.40 | 0.833 | **0.917** | 0.885 |
| 3 | 0.00 | 0.750 | 1.000 | 0.861 |
| 3 | 0.20 | 0.833 | 1.000 | **0.917** |
| 5 | 0.05 | 0.750 | 1.000 | 0.847 |
| 5 | 0.20 | 0.833 | 1.000 | 0.903 |

The β = 0 control reproduces the published baseline exactly — R@1 0.750, R@5 1.000, MRR
0.861 — which is what says the harness is wired correctly rather than producing a clean
negative out of a bug.

Best cell is MRR 0.917 at k=3, β=0.20: **+0.056, and one query is 0.083.** The
improvement is smaller than the instrument can resolve.

The per-query ranks say more than the aggregate, and they contradict the obvious reading
of it. Three of twelve queries moved, not one:

| | control | best cell |
|---|---:|---:|
| how the rolling-hash constant table was produced | 3 | **1** |
| the distinction between deleting and folding up | 2 | **1** |
| the fuzzer's mutations never getting past the hash | 1 | **2** |

Two improved, one got worse, net +1 at R@1. And at k=1, β=0.40 the bonus pushed a correct
answer out of the top five, dropping R@5 to 0.917 — so the mechanism is genuinely
two-sided and the grid can show it.

**The honest summary: the graph moves a quarter of the queries and helps on balance, by
less than this instrument can resolve.** Twelve queries cannot distinguish that from
noise. A larger labelled set could; nothing else here can.

---

## What this changes

1. **`mentions-path` is the retrieval-relevant kind.** If the retrieval layer ever uses
   the graph, it should use this one — the others contribute topology the index already
   has, and a similarity below what ordering gives.
2. **`replies-to` and `tool-result-of` are navigation, not similarity.** They should be
   offered for walking the record and excluded from any semantic expansion.
3. **The p95 gate is still failed**, and this run does not touch that. `changepoint-v1`
   sits at +0.203 against a gate of +0.15, and the graph does not change the geometry.
4. **Nothing here is a phase.** These are the context/index base $I_{\mathrm{sem}}$; there
   is no transport, no composition law, and the phase channel remains `ABSENT` — which is
   a measurement, not a placeholder. §6 step 3 is unchanged: transport only if a
   composition law is written down first.

---

## Defects this found

Four in the path extractor alone, none of which raised anything, because a missing edge
looks exactly like two turns with nothing in common:

* Allowing spaces inside a path component made the pattern greedy across prose:
  `src/a.py and src/b.py` matched **once**, as a single 33-character "path", so neither
  real file produced an edge. Spaces are needed — this repository lives under
  `D:/Ai/work together/ANLA` — and what separates a directory name from prose between two
  paths turns out to be the dot: `work together` has none, `a.py and` does.
* `_normalise` replaced separators per character, so a JSON-escaped `D:\\Ai\\x.py` became
  `d://ai//x.py` and did not match the same file written with forward slashes.
* Stripping punctuation symmetrically turned `.github/workflows/ci.yml` into a different
  file from itself.
* An early variant truncated `..._v0.1.md` to `..._v0.1`.

And one in the verifier: `verify_edges` originally compared `(kind, from, to)` as a
**set**, and reported `identical: True` on a list holding 1,680 more edges than it
expected. A set cannot see multiplicity, so the one defect the comparison was most likely
to meet was the one it could not detect. It now compares whole edges, counts duplicate
keys separately, and refuses to call an empty graph identical to an empty expectation.

Also corrected: the site had `MCP · 20 tools` typed into a card and "Twenty tools" /
「二十個工具」 typed into both language bodies, against 23 actually registered. All three
are now counted from the server's source at build time, and the build stops rather than
rendering a number it could not derive.
