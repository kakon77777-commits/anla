# ANLA — Agent-Native Lossless Archive

**An AI may plan how to pack. A public, deterministic, model-independent decoder
must recover every byte that was declared into the archive.**

That sentence is the whole project. This repository contains the papers that argue
for it, the frozen specification of the subset that implements it, two reference
implementations that agree byte for byte, the conformance suite that proves it, and
the site that hosts a working version you can run in a browser tab.

- **Site and live workbench:** https://anla.evemisslab.com
- **Live test:** https://anla.evemisslab.com/demo/ — runs the suite in your browser
- **Specification:** [`SPEC.md`](SPEC.md) — normative for `ANLA-MVP v0.1`
- **1.0 container draft:** [`SPEC-1.0-DRAFT.md`](SPEC-1.0-DRAFT.md) — nothing frozen yet, and it says so
- **Papers:** [`papers/`](papers/) — Traditional Chinese originals, English translations
- **Conformance:** [`conformance/`](conformance/) — fixtures, frozen vectors, drivers
- **Design record:** [`design/decisions-for-1.0.md`](design/decisions-for-1.0.md) — the whitepaper's fifteen open questions, answered or scoped

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
cross-snapshot deduplication, and an `anla1` command that packs a real directory —
a second snapshot of an unchanged tree writes no chunk records at all, and with
`anla-cdc-1` prepending ten bytes to a 300 KB file shares 65 of its 66 chunks with
the snapshot before it. What it does not have is a second implementation, so nothing
is frozen. `SPEC-1.0-DRAFT.md` opens with a table of what exists, which is the first
thing that changes when that changes.

```bash
anla1 pack ./my-project -o project.anla --exclude .git --exclude '.git/**'
anla1 append project.anla ./my-project      # a snapshot, storing only what changed
anla1 snapshots project.anla
anla1 diff project.anla --from 1 --to 2
anla1 extract project.anla --to restored -s 1
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

602 tests. The cross-implementation tests need `node` on `PATH` and skip themselves
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
