# ANLA over MCP

```bash
python tools/mcp/anla_mcp.py
```

Registered for this repository in [`.mcp.json`](../../.mcp.json), so an agent working
here has it without any setup. Needs `mcp>=1.10,<2` (2.0 moved `mcp.server.fastmcp`; the server says so rather than failing with a bare import error), `blake3` and `zstandard`; stdio only,
because it touches the filesystem and nothing here should be reachable over a network.

## Why this is not a CLI wrapper

The whitepaper's claim is that **a model may plan how to pack, and a deterministic
decoder with no model in it must return every declared byte.** The second half has
been built and proven for weeks. The first half did not exist: there was no planner,
and an agent's only way in was a command line designed for people.

The loop these tools make possible is the first half:

```
anla_survey   →  measured facts, and a recommended plan
   agent      →  chooses a plan, for reasons it can state
anla_pack     →  the plan is recorded IN the archive as `packing_plan`
anla_append   →  inherits that plan, so a later snapshot cannot cut differently
```

That last step is the point. A packing plan in a log is a memory; a packing plan in
the manifest is an artifact — an append that would cut at different boundaries is
*refused*, rather than quietly producing different chunk ids for identical bytes and
deduplicating against nothing while every check still passes.

## The tools

| tool | what it does |
|---|---|
| `anla_survey` | Packs a sample at four chunk sizes and reports what each cost. Returns a recommended plan and the measurement behind it. |
| `anla_pack` | New archive. Records the plan. `engine="rust"` is ~20× faster and byte-identical. |
| `anla_append` | Another snapshot, inheriting the archive's recorded chunking. |
| `anla_verify` | Every snapshot and chunk; optionally asks the independent Rust reader the same question. |
| `anla_extract` | Restore, and with `compare_with` check every restored byte against the source. |
| `anla_snapshots` / `anla_list` / `anla_diff` | The chain, one snapshot's objects, and what changed. |
| `anla_manifest` | The five roots, capabilities, the plan, and the fidelity report. |
| `anla_compare_writers` | Pack one tree with both implementations and diff the bytes. |

## Context — an agent compressing its own

`design/context-compression.md` has the argument; MNVP 原則四 has the sentence:
**永久刪除與可展開壓縮是不同操作** — permanent deletion and expandable compression
are different operations, and summarising a context is the first.

| tool | what it does |
|---|---|
| `context_capture` | Store a transcript losslessly, one object per turn. Name none and it takes this machine's newest session — which, for an agent inside one, is its own. |
| `context_project` | Read it at L0/L1/L2/L3, with a manifest naming every omission and the path that restores it. |
| `context_expand` | Hand omitted turns back byte for byte, out of the archive, with no model involved. |
| `context_find` | Locate turns worth expanding. A placeholder for DRVS, built in its discipline: every hit says *what* matched, results land in tiers rather than carrying a score, and a query that matches nothing says so. |
| `context_status` | Turns, snapshots, unique chunks, what it cost. |

On a real 6.3 MB session of 2,071 turns: the record is 63.5% of the context with 260
turns deduplicated away, an L1 projection is **0.25%** of it, and expanded turns come
back byte-identical.

**The cost worth knowing before you use it:** capturing the same context twice added
970,584 bytes of which **100% was manifest and none was new content** — 352 bytes to
re-describe each turn, every checkpoint, growing with the conversation. That is
Decision 1's price at turn granularity, `FLAG_COMPRESSED_METADATA` is the reserved
answer, and until then checkpoint on meaningful boundaries rather than on a timer.

## Semantic addressing — from a question to the exact bytes

A whole turn is the wrong unit to embed: it covers a defect, a measurement, a
decision and an aside, so its vector means "technical conversation" and nothing
narrower. Measured, that showed up as the best real match scoring *below* the 95th
percentile of random pairs. The unit had to get smaller — but not by storing pieces.

From Neo's 同一性微積分, **切割 = 索引**: a cut adds a perspective and leaves the
object whole. So a segment is `(turn, start_byte, end_byte)` in the auxiliary plane,
several index families coexist over one record, and re-cutting rewrites nothing.

| tool | what it does |
|---|---|
| `context_segment` | Build an index family σ. Reports coverage and the archive's digest before and after — indexing that changed a byte would be a defect, so it is checked rather than asserted. |
| `context_segment_export` | The views `π_σ(m)` to embed, with the identity that must come back with them. A `limit` samples across the whole record by default and names which part it covered. |
| `context_attach_vectors` | Vectors into the auxiliary plane, keyed by segment. `float32` behind a JSON header: 61,458 × 768 measures **978 MB as JSON and 192 MB here**, and loads in 0.52 s instead of 38.1 s. |
| `context_address` | A question in, `(turn, start_byte, end_byte)` out, digest verified against the record. |

Three refusals are the load-bearing part:

* a query vector whose model, revision, dimensions, projection version or scheme
  disagrees with the corpus returns **`INCOMPARABLE`**, not a number. Width is not
  identity, and cosine will give a confident answer to two vector spaces;
* a search projected past a stated time budget **says so** rather than running.
  61,458 vectors at 768 dimensions is **152 ms** with NumPy and about **11 s**
  without, and the refusal quotes its own projection so a caller can disagree with
  the estimate instead of with a magic number;
* a search over a partially embedded index reports `semantic_corpus_share`, because
  the nearest hit inside a tenth of the record looks exactly like a complete search.

`bench/segment_retrieval.py` measures whether any of this helps, against twelve
labelled queries whose ground truth comes from an anchor string the retriever never
sees. `bench/native_context.py` runs the whole loop over the wire on this
repository's own transcript.

## Two rules these tools follow

**Every number was measured by the call that returned it.** No estimates and no
"typically". `anla_survey` really packs samples, because the pinned 256 KiB default
is wrong for prose by a factor of three and no amount of reasoning about file sizes
would have found that — it was found by measuring. On this repository's own
`test_demo/`, survey recommends a 16 KiB average: the second snapshot then costs
23,120 bytes where the default costs 54,936.

**A tool reports what it could not do.** The fidelity report, unapplied metadata
namespaces and unapplied native names come back rather than being dropped, because
*stored but not applied* and *not stored* are different facts, and conflating them
throws away whether the data still exists.

## Verifying it works

`tools/mcp/test_mcp.py` speaks JSON-RPC to the server over stdio, as a client does,
rather than importing the module and calling the functions. That distinction earned
itself immediately: the error-handling decorator was written without
`functools.wraps`, so FastMCP — which derives each tool's input schema from the
function signature — gave **all ten tools** a schema of `required: ["args",
"kwargs"]`. Every direct call worked perfectly. No client could have called a single
one.
