# Prompt: get semantic vectors from a web-side AI

Copy everything between the rules below into ChatGPT (or any assistant with tools),
and attach the file `*.to-embed.json` produced by:

```bash
context_export_for_embedding(archive="…/my-context.anla")
```

Then bring the result back with `context_attach_vectors`.

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
Each `text` is one turn of a long conversation. There may be a few thousand.

## Output contract

A **downloadable JSON file** named `vectors.json`:

```json
{
  "model": "the exact embedding model identifier you used",
  "dimensions": 768,
  "vectors": [
    {"key": "turns/000001-user.json", "vector": [0.0123, -0.0456, ...]},
    {"key": "turns/000002-assistant.json", "vector": [...]}
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

## Bringing it back

```
context_attach_vectors(archive="…/my-context.anla",
                       vectors="…/vectors.json",
                       model="text-embedding-3-small")
```

The vectors land in the archive's **auxiliary** plane — derived, disposable,
regenerable — so `strip` can remove them and the preserved record does not change by
a byte.

Then retrieval uses the semantic channel, and `context_find` reports it as
`PRESENT` with the count of turns carrying one. Until vectors arrive it reports
`ABSENT` rather than substituting word overlap under the same name.

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
