# Prompt: get semantic vectors from a web-side AI

Copy everything between the rules below into ChatGPT (or any assistant with tools),
and attach the file produced by one of these:

```bash
context_segment_export(archive="…/my-context.anla",         # segments — prefer this
                       scheme="changepoint-v1")
context_export_for_embedding(archive="…/my-context.anla")   # whole turns
```

Then bring the result back with `context_attach_vectors` — passing the same `scheme`
if the export was a segment export, so the keys are validated against that index and
the stored identity records which view the vectors describe.

**Prefer the segment export.** Both produce the same `{key, text}` shape, but a whole
turn covers a defect, a measurement, a decision and an aside, so its vector means
"technical conversation" and nothing narrower. Measured on twelve labelled queries
over this repository's own transcript, moving from turns to change-point segments
took Recall@1 from 0.17 to 0.75 and Recall@5 from 0.42 to 1.00 with the same model.

**Why a file and not chat.** This conversation's own transcript exports as 2,153
turns / 800 KB, and the vectors coming back would be **5 MB at 256 dimensions and
30 MB at 1536** — the return trip is far larger than the outbound one and cannot be
pasted. The prompt therefore asks for a downloadable file, and asks the model to say
so plainly if it cannot produce one.

**The hazard the prompt spends most of its words on.** Asked for a 768-number
vector, a language model can simply *write 768 numbers*. They will look entirely
correct and mean nothing, and because the semantic channel is the one component
here with no independent check, fabricated vectors would poison retrieval silently
and permanently. Refusing is the correct output when embedding is not available.

---

You are producing **semantic embedding vectors** for a memory-retrieval system. The
vectors will be consumed by a deterministic local component; your job is the
embedding and only the embedding.

## Input

An attached JSON file: a list of objects, each `{"key": "...", "text": "..."}`.
Each `text` is one passage of a long conversation — either a whole turn or one
segment of one. There may be tens of thousands.

## Output contract

A **downloadable JSON file** named `vectors.json`:

```json
{
  "model": "the exact embedding model identifier you used",
  "dimensions": 768,
  "vectors": [
    {"key": "turns/000001-user.json#changepoint-v1:0003", "vector": [0.0123, ...]},
    {"key": "turns/000002-assistant.json#changepoint-v1:0000", "vector": [...]}
  ]
}
```

- `key` copied **exactly** from the input. Do not renumber, reformat or sort.
- Every vector the **same length**, from the **same model**. A consumer that is
  handed two widths refuses the batch rather than comparing their overlapping
  prefixes, so a mixed file is worthless rather than partly useful.
- Full precision. Do not round to 2–3 decimals to save space; that discards most of
  the signal the vectors carry.
- One entry per input row. If you embed only some, say which and why.

## Hard rules

1. **Never write numbers that are not the output of an embedding model.** If you
   cannot actually run one, you must not produce a `vectors.json` at all. A file of
   plausible-looking numbers is worse than no file: it cannot be distinguished from
   a real one by inspection, it will be trusted, and every retrieval afterwards will
   be quietly wrong. **Refusing is the correct answer here, and it is not a
   failure.**
2. **One model for the whole batch**, and name it exactly. A vector whose model is
   unknown cannot be compared with anything later.
3. **Do not summarise, translate, clean or truncate the `text`.** Embed what is
   there. The turns are already the compressed form of something larger.
4. **Do not reorder or drop rows silently.** Report any omission with its key.

## How to do it, in order of preference

1. **Call an embedding API from your code tool**, if you have network access and a
   key — for example OpenAI `text-embedding-3-small` (1536 dims, or 256 via the
   `dimensions` parameter). Batch the requests; write the file as you go so a
   failure part-way still leaves usable output.
2. **Run a local sentence-embedding model in your sandbox**, if one is available
   offline (`sentence-transformers` with a cached model such as
   `all-MiniLM-L6-v2`, 384 dims). Check it is genuinely present before promising it.
3. **If neither is possible**, do *not* improvise. Instead write me a short,
   runnable Python script that does this locally — reading the same input file and
   producing exactly the output format above — and tell me what to install and what
   key to set. Then say clearly: *"I cannot embed these here; run this."*

## Before you return the file

State these four things explicitly:

- the model identifier and the dimension;
- how many rows were in, and how many vectors are out;
- **how the vectors were produced** — which API or library call — in one sentence;
- anything you skipped, with its key.

If you cannot state the third one truthfully, do not return a file.

---

## What came back the first time

ChatGPT refused to embed and wrote a script, which is exactly what rules 1 and 3
ask for. It is in this directory as [`make_vectors.py`](make_vectors.py), kept close
to as written because it is good — atomic checkpointed writes, exact key and order
preservation, per-vector width validation, and a batch failure that falls back to
per-row retries so one bad row costs one row.

**One thing was changed, and it would have bitten at your scale.** The script
imported `time` and never used it — the tell that retry was intended and dropped —
and had no handling for a rate limit. With a few thousand rows in batches of 64, a
single 429 failed the batch, then failed each of its 64 rows individually, and
recorded all 64 as permanent omissions. A transient throttle became permanent loss,
in the one channel of this system with no independent check on whether it is
complete. Transient failures now back off and retry; only permanent ones become
omissions.

Exercised against a stub API, because a script nobody has run is a plan:

```
the happy path      10 vectors, width 768, keys and order preserved
a rate limit        waited out, 10/10 — nothing lost to the throttle
a permanent error   exit 2, one row omitted and named, the other nine survived
```

```bash
python -m pip install -U openai
export OPENAI_API_KEY=...
python tools/mcp/make_vectors.py exported.to-embed.json --output vectors.json
```

## Bringing it back

```
context_attach_vectors(archive="…/my-context.anla",
                       vectors="…/vectors.json",
                       scheme="changepoint-v1",           # omit for a turn export
                       model="text-embedding-3-small")
```

The vectors are **auxiliary** — derived, disposable, regenerable — and they live in a
sidecar *beside* the archive rather than inside it, so removing them is `rm` on one
file and the archive's bytes never change. That is `D(P, I) = D(P, ∅)` at its most
literal: delete the whole intelligence plane and every preserved byte extracts
identically, because the decoder was never reading it.

They are stored as `float32` behind a JSON header rather than as a JSON array of
decimals. Measured at 61,458 segments × 768: **192 MB against 978 MB**, and **0.52 s
to load against 38.1 s** — `frombuffer` instead of parsing a gigabyte of text.

Then retrieval uses the semantic channel — `context_address` for segments,
`context_find` for turns — and both report the channel as `PRESENT` with the count
carrying a vector. Until vectors arrive they report `ABSENT` rather than substituting
word overlap under the same name.

**Install NumPy for the search.** It is optional and the preservation plane never
needs it, but the pure-Python cosine is 71 µs a pair: 61,458 vectors is 73 minutes
for one query, which an agent cannot tell from a hang. Without NumPy the search
refuses above 8,000 vectors and says what to install. With it, the same search is
**262 ms**.

**The query needs a vector from the same model.** Embed the question with the model
named above and pass it as `query_vector`; a query embedded by a different model is
a comparison between two vector spaces and will be refused on width, or worse,
accepted at the same width and be meaningless.

## Checking what came back

```bash
python -c "
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
v = d['vectors']
widths = {len(r['vector']) for r in v}
print(f'{len(v)} vectors, widths {widths}, model {d.get(\"model\")}')
import statistics
flat = [x for r in v[:50] for x in r['vector']]
print(f'  spread: min {min(flat):.4f} max {max(flat):.4f} sd {statistics.pstdev(flat):.4f}')
print('  all-identical vectors:', len({tuple(r['vector']) for r in v[:200]}) < 100)
" vectors.json
```

Two things that would indicate fabrication rather than embedding: a suspiciously
round distribution, and near-identical vectors for texts that are not similar. This
is a smell test, not a proof — the real defence is rule 1 above.
