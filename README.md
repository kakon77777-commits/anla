# ANLA — Agent-Native Lossless Archive

**An AI may plan how to pack. A public, deterministic, model-independent decoder
must recover every byte that was declared into the archive.**

That sentence is the whole project. This repository contains the papers that argue
for it, the frozen specification of the subset that implements it, two reference
implementations that agree byte for byte, the conformance suite that proves it, and
the site that hosts a working version you can run in a browser tab.

- **Site and live workbench:** https://anla.evemisslab.com
- **Specification:** [`SPEC.md`](SPEC.md) — normative for `ANLA-MVP v0.1`
- **Papers:** [`papers/`](papers/) — Traditional Chinese originals, English translations
- **Conformance:** [`conformance/`](conformance/) — fixtures, frozen vectors, drivers

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
| Chunking | fixed size |
| Manifest | canonical JSON, hashed into the footer |
| Deduplication | across files, within the archive |
| Verification | header, footer, manifest, every chunk, every file |
| Reproducible | same input + same `(uuid, timestamp)` → identical bytes |
| Metadata | modification time only |
| Snapshots | one |

Not implemented, and therefore not claimed: symbolic and hard links, permissions
and ACLs, extended attributes, alternate data streams, sparse files, FastCDC,
Zstandard, BLAKE3, encryption, signatures, parity, append-only snapshots, partial
materialization. [SPEC.md §13](SPEC.md#13-known-divergences-from-the-whitepaper)
lists every divergence from the whitepaper's target and why each one exists.

> **This is a research profile.** It is tested, but it is young. Do not make an
> ANLA archive the only copy of anything you cannot lose.

---

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

### From Python

```bash
pip install -e python
anla pack ./my-project -o project.anla --exclude .git --exclude '.git/**'
anla verify project.anla
anla list project.anla
anla extract project.anla --to restored
anla export project.anla -o project.zip
```

Every subcommand takes `--json`, because the first-class caller of this tool is an
agent rather than a person. Exit codes follow the whitepaper's table: `5` is an
integrity failure, `9` an unsafe path, `8` a resource limit, and so on.

Reproducible output, when you want to compare two writers:

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

165 tests. The cross-implementation tests need `node` on `PATH` and skip themselves
without it. Everything runs on Linux, macOS and Windows in CI.

What they cover, beyond the round trips: every rejection a decoder owes you (bad
magic, bad CRC, wrong hash, wrong length, unknown codec, unknown record type,
unsafe path, duplicate path, a compression bomb, an offset past the end of the
file), reproducibility, the disposability of the intelligence plane, and the
filesystem-collision case where an archive is valid but the target filesystem
cannot restore it — where refusing is correct and silently dropping a file is not.

See [`conformance/README.md`](conformance/README.md) for the assertion table and a
suggested order for implementing this format somewhere else.

---

## Layout

```text
SPEC.md                     normative specification for ANLA-MVP v0.1
papers/                     the concept paper and the whitepaper, zh-Hant + en
python/anla/                Python reference implementation and CLI
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
