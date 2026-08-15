# ANLA — Agent-Native Lossless Archive

**An AI may plan how to pack. A public, deterministic, model-independent decoder
must recover every byte that was declared into the archive.**

That sentence is the whole project. This repository contains the papers that argue
for it, the frozen specification of the subset that implements it, two reference
implementations that agree byte for byte, the conformance suite that proves it, and
the site that hosts a working version you can run in a browser tab.

- **Install:** `pip install "anla-archive[speed,zstd]"` — the distribution is `anla-archive`; the imports and commands are `anla` and `anla1`
- **Site and live workbench:** https://anla.evemisslab.com
- **Live test:** https://anla.evemisslab.com/demo/ — runs the suite in your browser
- **Specification:** [`SPEC.md`](SPEC.md) — normative for `ANLA-MVP v0.1`
- **1.0 container draft:** [`SPEC-1.0-DRAFT.md`](SPEC-1.0-DRAFT.md) — nothing frozen yet, and it says so
- **Papers:** [`papers/`](papers/) — Traditional Chinese originals, English translations
- **Conformance:** [`conformance/`](conformance/) — fixtures, frozen vectors, drivers
- **Design record:** [`design/decisions-for-1.0.md`](design/decisions-for-1.0.md) — the whitepaper's fifteen open questions, answered or scoped
- **Measured, including where it loses:** https://anla.evemisslab.com/bench/ — six scenarios against ZIP, tar.gz and MVP

```text
Extract(Pack(F, P)) = F
```

---

## What is actually done

`ANLA-MVP v0.1` is a small, frozen, fully implemented profile of the format the
whitepaper describes. It is deliberately the smallest thing that can be finished
and verified end to end, rather than a partial attempt at the whole target.

| | |
|---|---|
| Chunk identity | SHA-256 of the raw chunk |
| Codecs | `store`, `deflate` (zlib, RFC 1950) |
| Chunking | fixed size, or content-defined (`anla-cdc-1`, pinned gear table) |
| Manifest | canonical JSON, hashed into the footer |
| Deduplication | across files, within the archive |
| Verification | header, footer, manifest, every chunk, every file |
| Reproducible | same input + same `(uuid, timestamp)` → identical bytes |
| Metadata | modification time only |
| Snapshots | one |

Not implemented, and therefore not claimed: symbolic and hard links, permissions
and ACLs, extended attributes, alternate data streams, sparse files, Zstandard,
BLAKE3, encryption, signatures, parity, append-only snapshots, partial
materialization. [SPEC.md §13](SPEC.md#13-known-divergences-from-the-whitepaper)
lists every divergence from the whitepaper's target and why each one exists.

> **This is a research profile.** It is tested, but it is young. Do not make an
> ANLA archive the only copy of anything you cannot lose.

---

## Two profiles

`ANLA-MVP v0.1` is finished. `ANLA 1.0` is being specified alongside it, for Python
and Rust, because 1.0 wants BLAKE3 and Zstandard and neither is a browser primitive.
Rather than turn the browser implementation into a WebAssembly download, MVP stays
what it is — the profile a stranger can verify in thirty seconds — and 1.0 becomes
the profile a preservation system can adopt. Different jobs; the reasoning is in the
[design record](design/decisions-for-1.0.md).

The draft is held to the standard MVP was held to: **nothing is frozen until two
independent implementations produce byte-identical archives and a differential fuzzer
finds no divergence between them.** 1.0 now has canonical CBOR, the container (header,
record frame with flags, footer chain, capabilities), the pinned Merkle construction,
the manifest with its five roots, BLAKE3-256, append-only snapshots with
cross-snapshot deduplication, metadata namespaces with an in-archive fidelity
report, symbolic links, Zstandard, and an `anla1` command that packs a real
directory —
a second snapshot of an unchanged tree writes no chunk records at all, and with
`anla-cdc-1` prepending ten bytes to a 300 KB file shares 65 of its 66 chunks with
the snapshot before it. As of 2026-08-14 it also has a **second implementation** —
see below — which satisfies one of the freeze rule's two clauses. The other needs a
Rust *writer*, so nothing is frozen. `SPEC-1.0-DRAFT.md` opens with a table of what
exists, which is the first thing that changes when that changes.

```bash
anla1 pack ./my-project -o project.anla --exclude .git --exclude '.git/**'
anla1 append project.anla ./my-project      # a snapshot, storing only what changed
anla1 snapshots project.anla
anla1 diff project.anla --from 1 --to 2
anla1 extract project.anla --to restored -s 1
```

## ANLA 1.0 has a second implementation, and the freeze rule is met

[`rust/`](rust/) is an independent reader **and writer** — its own canonical CBOR,
container, Merkle construction, manifest verification, SHA-256 and `anla-cdc-1`
chunker, sharing no code with the Python below `blake3` and `zstd`.

The draft set itself a rule in July: *nothing is frozen until two independent
implementations produce byte-identical archives and a differential fuzzer finds no
verdict divergence*. Both halves now hold.

| | |
|---|---|
| Byte-identical output | same tree, same `(uuid, created_ns)`, **identical bytes** — fixed chunking and `anla-cdc-1` at two profiles |
| No verdict divergence | **16,000 mutants across four seeds**, zero divergences, zero code mismatches, zero crashes |
| Same restored content | both readers give the same BLAKE3 for every file of the corpus, on three platforms |

It is still a draft, and [`SPEC-1.0-DRAFT.md`](SPEC-1.0-DRAFT.md) says exactly what
is holding that: two implementations by *one author* are weaker evidence than two by
two, the Rust writer is narrower than the Python one, and the object name model is
still open. The rule has been met; the judgement about whether the design is right
is a different judgement and has not been made.

```bash
cargo install anla1
anla1-rs pack   ./my-project -o project.anla --chunking cdc
anla1-rs verify project.anla
```

`anla1-rs` is the reader and writer used for the cross-implementation comparison; its
`extract` decodes and hashes rather than writing files. To restore a tree, use the
Python CLI's `anla1 extract ARCHIVE --to DIR`.

## A second thing this turned out to be: an agent's own memory

An archive that preserves bytes exactly and expands any part of itself on demand is
also a description of what a model needs from its own context. The same package
therefore carries a context layer, reachable over MCP, and the target is **an AI
natively compressing its own history** — remembering it losslessly, addressing it
semantically, and getting the record itself back rather than a summary of it.

Two front doors on one implementation. **From a terminal**, because a layer that is
about looking at a record and getting an exact piece of it back is a strange thing to
make unavailable to the person who owns the record:

```bash
anla1 context capture  memory.anla            # this machine's newest session
anla1 context project  memory.anla --level L1 # 0.18% of it, every omission expandable
anla1 context expand   memory.anla turns/000978-assistant.json
anla1 context segment  memory.anla --scheme changepoint-v1
anla1 context address  memory.anla "how was the gear table produced"
```

**Or over MCP**, for an agent — stdio for one client, HTTP when Claude Code and Codex
should share one server. `--share DIR` makes it read-only and confined to one
directory, which is what a public URL should be given:

```bash
pip install "anla-archive[speed,zstd]" "mcp>=1.10,<2"
python tools/mcp/anla_mcp.py                          # stdio; 21 tools
python tools/mcp/anla_mcp.py --http                   # http://127.0.0.1:8791/mcp
python tools/mcp/anla_mcp.py --http --share ./shared  # 12 tools, read-only
```

[`tools/mcp/SETUP.md`](tools/mcp/SETUP.md) has the registration for each client.

The loop, and what each step is required to prove:

| tool | the claim it has to hold up |
|---|---|
| `context_capture` | every byte of the transcript, or a refusal — a limit that would drop the front is an error, not a quiet truncation |
| `context_segment` | an index family σ over the turns; **the archive is byte-identical before and after** |
| `context_segment_export` | the views `π_σ(m)` to embed, with the identity that must come back with them |
| `context_attach_vectors` | vectors into the *auxiliary* plane — `D(P, I) = D(P, ∅)` |
| `context_address` | a question in, `(turn, start_byte, end_byte)` out, digest verified against the record |
| `context_relate` | typed relation edges over the index — a kind and its evidence, never a score |
| `context_relations` | what the record says is related to a turn, and why; unranked |

The last row is the whole point. A segment is an **index**, never a stored fragment:
from Neo's 同一性微積分, 切割 = 索引 — a cut adds a perspective and leaves the object
whole. So re-cutting the same memory a different way costs nothing and rewrites
nothing, several schemes coexist over one record, and **a segmenter is allowed to be
wrong**. Measured on this repository's own development transcript, 6,581 turns,
17.5 MB → an 11.5 MB archive:

| | measured |
|---|---|
| Index | 61,458 segments, median 249 bytes, **coverage 1.0000** — no byte of any turn is unreachable through the index, and none is covered twice |
| Preservation | digest **unchanged** through indexing, retrieval and expansion, across two coexisting schemes |
| Expansion | every address resolved to digest-verified exact bytes of the authoritative turn |
| Identity | a 768-wide corpus and a 64-wide query → `INCOMPARABLE: dimensions differs`, not a number |
| Search | 61,458 vectors as `float32` = 192 MB against 978 MB as JSON; loaded in 0.10 s against 24.3 s; ranked in 152 ms; **2.25 s median for a whole addressed query over MCP** |

**Does the segmenting actually help?** Twelve labelled queries, ground truth located
by an anchor string the retriever never sees, questions written to avoid the anchor —
so the label comes from a match the retriever cannot use and the query is exactly the
case lexical search cannot answer. One corpus for all four rows, digest recorded:

| scheme | segments | R@1 | R@5 | MRR | median rank |
|---|---|---|---|---|---|
| `whole-turn-v1` (baseline) | 6,581 | 0.17 | 0.42 | 0.280 | 7.5 |
| `structural-v1` | 18,814 | 0.50 | 0.58 | 0.545 | 2.0 |
| `sized-900-v1` (control) | 23,036 | 0.58 | 0.75 | 0.656 | 1.0 |
| **`changepoint-v1`** | 61,458 | **0.75** | **1.00** | **0.847** | **1.0** |

Two things in that table are worth more than the winning row. The **control beat the
structural scheme** — cutting every ~900 bytes did better than reading the document's
own headings and fences, so that structure was not carrying the information and the
scheme that reads it earned nothing over a ruler. And the **stated p95 gate failed on
every row**, including the winner: it wanted centred random-pair p95 below +0.15
against a baseline of +0.238 measured on a third of this corpus, where the baseline is
now +0.443. `changepoint-v1` halves the crowding to +0.219, which is what the gate was
reaching for, and the gate as written still failed. It is reported failed, in the
JSON and here, because a threshold re-read after the fact to mean whatever the result
supports is not a threshold.

**The same twelve queries, on a model that runs on this machine.** `nomic-embed-text`
through Ollama — 137M parameters, Apache-2.0, 768 dimensions — on identical ground:
same corpus digest, same queries, same schemes, same budget.

| scheme | R@1 hosted → local | MRR hosted → local | p95 hosted → local |
|---|---|---|---|
| `whole-turn-v1` | 0.17 → **0.42** | 0.280 → **0.569** | +0.443 → +0.500 |
| `structural-v1` | 0.50 → **0.58** | 0.545 → **0.704** | +0.356 → +0.351 |
| `sized-900-v1` | 0.58 → 0.50 | 0.656 → 0.631 | +0.361 → **+0.315** |
| **`changepoint-v1`** | 0.75 → 0.75 | 0.847 → **0.861** | +0.219 → **+0.203** |

On the winning scheme they are level at R@1 0.75 and R@5 1.00, with the local model
marginally ahead on MRR and crowding. A 262 MB file that runs offline and pins its
own weights by digest is not a compromise here — a hosted *name* can be re-pointed
without changing, and a local hash cannot.

Two things follow that the hosted run alone could not have shown. **Segmentation's
benefit is a joint property of the unit and the model**: 4.5× on the hosted model
(0.17 → 0.75), 1.8× on the local one (0.42 → 0.75), same destination from very
different starting points — so "0.17 to 0.75" was true and narrower than it sounded.
And **the p95 gate is refuted a second time, independently**: at `whole-turn-v1` the
local model is *more* crowded (+0.500 against +0.443) and retrieves *much* better
(R@1 0.42 against 0.17). The quantity the gate measures moved opposite to the
quantity it existed to predict, which is worse than being set at the wrong level —
a bad level can be re-set; pointing the wrong way cannot be fixed by a better number.

Nothing in this package computes an embedding. The vectors come from whatever model
the agent has — the OpenAI backend in `bench/` is a *test* backend, and the identity
travels with the vectors precisely so that a local or browser model can replace it
without anything silently comparing across the two. That division is UTF-8X's:
「AI 負責策略生成⋯**AI 不參與解碼**」.

```bash
python bench/native_context.py --budget 6000     # the whole loop, over the wire
python bench/segment_retrieval.py <transcript>   # does segmenting actually help?
```

## Two implementations, on purpose

| | |
|---|---|
| [`python/anla/`](python/anla/) | writer, reader, verifier, extractor, ZIP export, `anla` CLI |
| [`web/anla-core.js`](web/anla-core.js) | the same, running in a browser tab or in Node |

Neither is generated from the other, and neither imports the other's description
of the format: both are written against `SPEC.md`. What holds them together is the
conformance suite, which asserts that they produce **identical bytes** for every
reproducible fixture — not merely archives each other can read.

The same `web/anla-core.js` file is copied verbatim into the deployed site, so the
workbench a visitor runs is the implementation the tests ran.

---

## Try it

### In a browser

Open https://anla.evemisslab.com/workbench/ — pick a folder, build a real `.anla`,
open it again, restore it as a ZIP. Your files are read in the tab and never sent
anywhere; the page makes no requests of its own. Append `?selftest=1` and it packs, verifies, re-packs and
compares a fixture against itself in front of you.

There is also a [single-file build](https://anla.evemisslab.com/standalone.html):
save it, open it offline, it still works.

And a [live test page](https://anla.evemisslab.com/demo/) that runs 76 of the
conformance assertions in your own browser — including the byte-for-byte
comparison against hashes the Python writer produced. It fetches nothing: the
fixtures and the frozen vectors are compiled into the page.

### From Python

```bash
pip install -e python
anla pack ./my-project -o project.anla --exclude .git --exclude '.git/**'
anla verify project.anla
anla list project.anla
anla extract project.anla --to restored
anla export project.anla -o project.zip
anla strip project.anla -o shared.anla     # drop the planner's decision log
```

Every subcommand takes `--json`, because the first-class caller of this tool is an
agent rather than a person. Exit codes follow the whitepaper's table: `5` is an
integrity failure, `9` an unsafe path, `8` a resource limit, and so on.

Reproducible output, when you want to compare two writers. **"Same input" means
same names, same content, *same recorded metadata*, and a fixed `(uuid, created_ns)`
— modification times are preserved, so they are part of the hash.** Two checkouts of
one repository do not have the same mtimes, which is enough to make two archives of
"the same tree" differ; pass `--no-mtime` when content and names are what you mean
to compare:

```bash
anla pack ./my-project -o a.anla --uuid 00112233445566778899aabbccddeeff --created-ns 1752732000000000000
```

### From JavaScript

```js
import { pack, openArchive, exportZip } from './web/anla-core.js';

const { bytes } = await pack({
  name: 'my-project',
  directories: ['docs'],
  files: [{ path: 'docs/readme.txt', data: new TextEncoder().encode('hello\n') }],
}, { chunk_size: 1 << 20, compression: 'auto' });

const archive = await openArchive(bytes);   // verifies on open, or throws
archive.read('docs/readme.txt');
```

---

## Tests

```bash
python -m pytest python/tests -q
```

830 tests. The cross-implementation tests need `node` on `PATH` and skip themselves
without it. Everything runs on Linux, macOS and Windows in CI. Another 76
assertions run in a browser on the [live test page](https://anla.evemisslab.com/demo/).

What they cover, beyond the round trips: every rejection a decoder owes you (bad
magic, bad CRC, wrong hash, wrong length, unknown codec, unknown record type,
unsafe path, duplicate path, a compression bomb, an offset past the end of the
file), reproducibility, the disposability of the intelligence plane, and the
filesystem-collision case where an archive is valid but the target filesystem
cannot restore it — where refusing is correct and silently dropping a file is not.

Plus a differential fuzzer, which is the part that finds what the hand-written
tests cannot:

```bash
python tools/fuzz_differential.py -n 20000 --seed 1
```

It mutates the frozen vectors and asks one question of each mutant — do both
implementations reach the same verdict? Agreement needs no oracle; disagreement is
always a defect in an implementation or in the specification. It has produced two
findings, and the second is the argument for the whole exercise: record `sequence`
was specified and checked by neither implementation, which no amount of writing
more tests by hand would have surfaced, because the tests and the implementations
shared the same blind spot.

See [`conformance/README.md`](conformance/README.md) for the assertion table, the
fuzzer, and a suggested order for implementing this format somewhere else.

---

## Layout

```text
SPEC.md                     normative specification for ANLA-MVP v0.1
papers/                     the concept paper and the whitepaper, zh-Hant + en
python/anla/                ANLA-MVP v0.1 reference implementation and CLI
python/anla1/               ANLA 1.0 (draft): CBOR, container, Merkle, manifest,
                            BLAKE3, snapshots, filesystem layer, `anla1` CLI
schemas/anla-1.0.cddl       shape of the 1.0 CBOR structures
python/tests/               the conformance suite (drives both implementations)
web/anla-core.js            JavaScript reference implementation
site/                       the generator for anla.evemisslab.com
conformance/fixtures.json   language-neutral test cases
conformance/vectors/        frozen archives and their hashes
conformance/run_node.mjs    driver for the JavaScript implementation
```

### Which implementation to use

They produce byte-identical archives — CI checks six configurations on three
platforms — so this is purely a speed question, and it has a measured answer
([`/bench/`](https://anla.evemisslab.com/bench/), `throughput` row):

| | pack, `anla-cdc-1` | verify |
|---|---|---|
| `anla1` (Python) | 3.9 MiB/s | 513 MiB/s |
| `anla1-rs` (Rust) | 87.5 MiB/s | — |

Content-defined chunking is the default because fixed chunking destroys
cross-snapshot deduplication, and it is also where the Python writer spends its
time: a per-byte rolling hash in CPython. That loop is written to be *read* — it
is the executable half of §5 — and rewriting it for speed buys 1.3× before it
stops being readable, which is measured in `design/commercial-readiness-plan.md`.

**Use the Python package** to read archives, to check the format against the
specification, to embed in Python, and for trees measured in megabytes.
**Use the Rust binary** for volume.

Building the site:

```bash
python site/build.py
npx wrangler deploy
```

---

## Provenance

The papers were written on 16 July 2026, before any of this code existed. The
original v0.1 deliverable was a single-file browser page; the archive it produced
is checked in as
[`conformance/vectors/browser-interop-v0.1.anla`](conformance/vectors/browser-interop-v0.1.anla)
and both current implementations still restore it exactly. A format profile that
cannot read the artifact it shipped with has not frozen anything.

One thing did change: the original writer ordered the manifest's object array with
JavaScript's `localeCompare`, which is locale-dependent, so its byte layout
depended on the machine that wrote it. The specification now mandates UTF-8 byte
order. Archives from the original build remain readable; they are simply not
reproducible, and the test suite pins that distinction rather than papering over
it.

---

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Author: Neo.K — EVEMISS Technology Co., Ltd. / EveMissLab.
Part of the [EveMissLab](https://evemisslab.com) family of projects.
