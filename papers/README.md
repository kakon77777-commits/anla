# Papers

Both documents were written on 16 July 2026, before any of the implementation
existed. The Traditional Chinese versions are canonical; the English versions are
faithful renditions, not independent works.

| Document | zh-Hant (canonical) | English |
|---|---|---|
| Concept paper — the control-plane transition thesis | [`01-control-plane-transition.zh-Hant.md`](01-control-plane-transition.zh-Hant.md) | [`01-control-plane-transition.en.md`](01-control-plane-transition.en.md) |
| Technical whitepaper — ANLA v0.1 | [`02-anla-whitepaper.zh-Hant.md`](02-anla-whitepaper.zh-Hant.md) | [`02-anla-whitepaper.en.md`](02-anla-whitepaper.en.md) |

Both are rendered on the site:
[English](https://anla.evemisslab.com/papers/) ·
[中文](https://anla.evemisslab.com/zh/papers/)

---

## How these relate to the code

The whitepaper describes a **target**: BLAKE3, Zstandard, deterministic CBOR
manifests, FastCDC, append-only snapshots, cross-platform metadata namespaces,
encryption, signatures, parity.

[`SPEC.md`](../SPEC.md) describes what is **done**: `ANLA-MVP v0.1`, the smallest
subset that can be implemented twice, frozen, and verified byte for byte. Section
13 of that document lists every divergence and the reason for it.

Reading the whitepaper as a description of the current implementation will
mislead you. Reading `SPEC.md` as the whole ambition will undersell it. They are
both accurate about different things, and the split is deliberate: a paper that
claims what its code does not do is the failure mode this project exists to argue
against.

---

## The shared principle

> An AI may plan how to pack. It may not substitute, summarize, infer or regenerate
> any original data that has been declared into the archive — in any form. A
> standard decoder must recover all of it, exactly, without any model.

The concept paper argues why this boundary is the interesting one. The whitepaper
turns it into invariants a writer can be held to. `SPEC.md` turns those invariants
into byte offsets and a test suite.
