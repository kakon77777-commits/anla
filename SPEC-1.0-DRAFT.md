# ANLA 1.0 — Container Specification (DRAFT)

**Status: DRAFT. Nothing here is frozen.**
**Frozen and normative today:** [`SPEC.md`](SPEC.md) — `ANLA-MVP v0.1`.
**Design record:** [`design/decisions-for-1.0.md`](design/decisions-for-1.0.md).

---

## 0. What this is, and the rule it is held to

`ANLA-MVP v0.1` is the profile that is finished: small, frozen, implemented twice,
verified byte for byte, and runnable in a browser tab. This document is the start of
the other one — the format the [whitepaper](papers/02-anla-whitepaper.en.md)
describes, specified for Python and Rust.

That split was a decision, taken on 2026-07-26 and recorded with its reasoning in
the design record. 1.0 wants BLAKE3 and Zstandard; neither is a browser primitive.
Rather than turn the browser implementation into a WebAssembly download, `ANLA-MVP`
stays what it is — the profile a stranger can verify in thirty seconds — and 1.0
becomes the profile a preservation system can adopt. Different jobs.

**The rule this draft is held to**, and the reason the word DRAFT is in the title:

> No part of this document is frozen until two independent implementations produce
> byte-identical archives from the same input, and a differential fuzzer finds no
> verdict divergence between them.

That is the standard `ANLA-MVP` was held to. Applying it *before* the word "1.0"
appears in public is the whole point of writing this file separately, rather than
editing `SPEC.md` and hoping.

### What exists so far

| Piece | State |
|---|---|
| Canonical CBOR encoder and strict decoder | **implemented** — [`python/anla1/cbor.py`](python/anla1/cbor.py), 129 tests |
| Content-defined chunking (`anla-cdc-1`) | **implemented and cross-verified**, reused unchanged from MVP |
| Container: header, record frame, flags, footer chain, capabilities | **implemented** — [`python/anla1/container.py`](python/anla1/container.py), 41 tests |
| Manifest contents (§5.2), objects, chunk map | specified in sketch, not implemented |
| BLAKE3-256 | decided (§7), not implemented |
| Zstandard | decided (§8), not implemented |
| Metadata namespaces, snapshots beyond one, signatures, encryption, parity | later milestones |

Anything not in the "implemented" rows is a claim about intent, not about code. This
table is the first thing to update when that changes, and it is deliberately at the
top.

---

## 1. What changes from MVP, and why each change is worth a new container

MVP is not a subset of 1.0 by accident — it is a subset chosen so that the parts it
left out are exactly the parts that need a different container.

| | MVP v0.1 | 1.0 |
|---|---|---|
| Manifest encoding | canonical JSON | canonical CBOR (§5) |
| Hash | SHA-256, inferred from the profile | declared in `hash_algorithms`, BLAKE3-256 core (§7) |
| Codecs | `store`, `deflate` | codec registry with ids, Zstandard core (§8) |
| Record flags | must be zero | `REQUIRED_FOR_EXTRACTION` / `AUXILIARY_DISPOSABLE` (§4.2) |
| Unknown records | always fail | fail or skip, by flag (§4.2) |
| Snapshots | exactly one | append-only chain (§6) |
| Integrity roots | one manifest hash in the footer | several Merkle roots (§5.3) |
| Capabilities | implied by the version | declared as URIs, required and optional separated (§9) |

Two of those are the reason a new magic number is needed rather than a minor
version bump. **Record flags** change what a decoder must do with something it does
not recognise, and **the footer chain** changes how a decoder finds the manifest at
all. A reader that does not know about either cannot safely guess.

Everything else on that list could in principle have been a capability declaration
inside MVP. They are here instead because a format with a hundred optional
capabilities and one magic number is a format nobody can implement a *minimal*
reader for — which is refutation condition 7.3 in the concept paper.

---

## 2. Overall layout

```text
┌──────────────────────────────────┐  offset 0
│ Bootstrap Header — 64 bytes      │
├──────────────────────────────────┤  offset 64
│ Record stream                    │
│   CHNK  chunk payloads           │
│   META  large or platform metadata│
│   AUXI  intelligence plane        │
│   INDX  random-access index      │
│   MANF  snapshot manifest        │
│   SIGN  signatures               │
│   PARI  parity                   │
│   FOOT  snapshot footer          │
│   … repeated per snapshot        │
└──────────────────────────────────┘  end of file
```

Unlike MVP, the footer is **not** at a fixed offset from the end, because there is
one footer per snapshot and they accumulate. A reader locates the latest footer by
scanning backwards for the footer magic and verifying it. The header's hint is
**not** used to decide which footer is latest — see §6, where implementing the
reader sharpened that rule.

All integers are little-endian and unsigned. Records are packed end to end with
padding to an 8-byte boundary (§4) — a change from MVP, where there was none,
adopted so that a memory-mapped reader can align payload access.

---

## 3. Bootstrap header (64 bytes)

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 8 | `magic` | `41 4E 4C 41 31 0D 0A 1A` (`ANLA1\r\n\x1A`) |
| 8 | 2 | `version_major` | `1` |
| 10 | 2 | `version_minor` | `0` |
| 12 | 4 | `header_size` | `64` |
| 16 | 8 | `global_flags` | all bits reserved, MUST be `0` |
| 24 | 8 | `first_record_offset` | `64` |
| 32 | 8 | `latest_footer_hint` | a guess, not authority |
| 40 | 16 | `archive_uuid` | |
| 56 | 4 | `header_crc32` | CRC-32 of `[0, 56)` |
| 60 | 4 | `reserved` | MUST be `0` |

Both magics open with the same four bytes, `ANLA`, because both are this format.
The fifth byte is the **generation digit** — `31`, ASCII `"1"`, here — and the
rest is the CR / LF / SUB sequence PNG uses, so that a naive text-mode transfer
corrupts the magic detectably instead of corrupting the payload silently.

```text
MVP  41 4E 4C 41 0D 0A 1A 0A     A N L A   CR LF SUB LF
1.0  41 4E 4C 41 31 0D 0A 1A     A N L A 1 CR LF SUB
```

So four bytes differ, not one: inserting the digit shifts the trailer along. What
matters is that a reader can tell which profile it is holding from the first eight
bytes, that neither can be mistaken for a damaged copy of the other, and that a
third generation has an obvious place to put its digit.

(An earlier draft of this paragraph claimed the two magics were one byte apart.
They are not, and the test that compares them is what said so — which is the
argument for writing tests against the specification rather than against the
code.)

So four bytes differ, not one — inserting the digit shifts the trailer along. What
matters is that a reader can decide which profile it is holding from the first eight
bytes, that neither can be mistaken for a damaged copy of the other, and that a
third generation has an obvious place to put its digit.

(An earlier draft of this section claimed the two magics were one byte apart. They
are not, and the test that compares them said so — which is the whole argument for
writing the tests against the specification rather than against the code.)

`header_size` is a real field here, unlike MVP's `reserved_a`. A reader MUST use it
to find the first record rather than assuming 64, so that a future minor version can
extend the header without moving the record stream.

**`latest_footer_hint` MUST NOT be used to determine which snapshot is latest.**

The earlier wording here said a decoder must verify the hint and fall back to
scanning. Implementing the reader showed that is not strong enough: a hint pointing
at an *older but perfectly valid* footer passes verification, and a decoder that
accepts it reports an older snapshot as current with every hash checking out. So the
rule is now the stronger one — the latest footer is found by scanning backwards from
the end, always, and the hint is at most a cross-check that may be ignored.

A writer MAY maintain the hint, which means rewriting the 64-byte header on each
append. That the field can therefore be stale, or torn if the process dies
mid-write, is precisely why no reader is permitted to depend on it.

---

## 4. Record frame

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | `magic` = `ANLR` |
| 4 | 4 | `type`, four ASCII bytes |
| 8 | 2 | `record_version` |
| 10 | 2 | `flags` (§4.2) |
| 12 | 4 | `header_length` — canonical CBOR record header |
| 16 | 8 | `payload_length` |
| 24 | 8 | `sequence` (§4.3) |
| 32 | 4 | `header_crc32` |
| 36 | 4 | `reserved` = `0` |

```text
record_total_length = 40 + header_length + payload_length + padding
padding = (-(40 + header_length + payload_length)) mod 8
```

Padding bytes MUST be zero and MUST NOT be included in any hash.

### 4.1 Record types

| Type | Payload | Default requirement |
|---|---|---|
| `CHNK` | one encoded chunk | required |
| `MANF` | a snapshot manifest, canonical CBOR | required |
| `FOOT` | a snapshot footer | required |
| `INDX` | random-access index | optional, rebuildable |
| `META` | large or platform metadata | required if referenced |
| `AUXI` | intelligence plane | optional, disposable |
| `SIGN` | signatures | optional |
| `PARI` | parity | optional |

### 4.2 Flags, and the rule that makes extension safe

```text
bit 0  REQUIRED_FOR_EXTRACTION
bit 1  REQUIRED_FOR_VERIFICATION
bit 2  ENCRYPTED
bit 3  COMPRESSED_METADATA
bit 4  AUXILIARY_DISPOSABLE
bits 5–15  reserved, MUST be 0
```

On encountering a record type it does not know:

```text
REQUIRED_FOR_EXTRACTION = 1  →  MUST fail
AUXILIARY_DISPOSABLE = 1     →  MAY skip
neither set                  →  MUST fail
```

The last line is the one that matters, and it is where MVP's behaviour is preserved
rather than relaxed: **the default is refusal.** A record that says nothing about
itself is treated as required, because a writer that wanted it skippable had a bit to
say so, and guessing on the reader's side is how a preservation format quietly loses
data.

Both bits set is an error. A decoder MUST NOT accept a record that claims to be
both required and disposable.

### 4.3 Record sequence

As in [MVP §4.3](SPEC.md#43-record-sequence), stated as arithmetic a reader can
evaluate rather than as "strictly increasing", which a reader that jumps straight to
the manifest cannot check:

- every record has `sequence >= 1`;
- within one snapshot, sequences are contiguous and unique;
- a snapshot's `FOOT` record has the highest sequence in that snapshot;
- across snapshots, sequences continue upward and never restart.

The reason this is spelled out again, in a draft, before any code exists: in MVP the
loose phrasing survived a specification, two implementations and a test suite
without anyone noticing that nothing evaluated it. It was found by differential
fuzzing. The lesson is not "check sequences" — it is that **every invariant in this
document needs a sentence saying how a reader checks it**, and any that cannot be
written that way should be deleted rather than left as decoration.

---

## 5. Manifest

Canonical CBOR, per [`python/anla1/cbor.py`](python/anla1/cbor.py) and the profile
below. This is whitepaper open question 2, decided.

### 5.1 The encoding profile

RFC 8949 §4.2.1 core deterministic encoding, and three restrictions of our own:

1. **No floating point anywhere.** A value whose bytes depend on how it was computed
   has no place in a preservation plane. MVP expressed the same rule as "nanosecond
   timestamps are decimal strings"; in CBOR they are integers, and the prohibition
   stays.
2. **Integers in their shortest form** — already required by core deterministic
   encoding, restated because it is the rule an implementation is most likely to get
   away with breaking locally.
3. **No indefinite lengths, no tags, no `null`, no `undefined`.** Absence is
   expressed by omitting a key. A streaming writer would like indefinite lengths; a
   signature over a manifest cannot afford them.

CDE — the stricter draft — is deliberately not adopted: pinning to a moving draft is
how a format acquires a dependency it cannot version.

**A decoder MUST reject non-canonical input**, not normalize it. The manifest hash
is computed over manifest bytes, so a decoder that accepts two encodings of the same
logical manifest is a decoder through which two archives with different hashes mean
the same thing. That is also where parser-differential attacks live.

Map keys are sorted by their **encoded bytes**, bytewise — not by the decoded value.
The distinction is not academic: `"z"` precedes `"aa"` by encoded bytes and follows
it by code point, because the length is part of the encoding.

### 5.2 Shape

Sketched, not settled — the field names come from the whitepaper's chapter 11.2 and
survive contact with implementation or they change:

```text
anla_version          [1, 0]
archive_id            16 bytes
snapshot_id           hash of the canonical manifest encoding
parent_snapshot       omitted for the first snapshot
created_unix_ns       integer
hash_algorithms       ["blake3-256"]  — read, never inferred (§7)
required_capabilities [ URIs ]        — §9
optional_capabilities [ URIs ]
objects_root          hash
chunks_root           hash
metadata_root         hash
preservation_root     hash over the three above
auxiliary_root        hash, outside preservation_root
packing_plan_digest   hash
```

### 5.3 Several roots, on purpose

Whitepaper open question 6 asked one root or many. Many, and the reason is the
invariant this project cares most about:

```text
D(P, I) = D(P, ∅)
```

If the intelligence plane hangs off its own root, dropping it *demonstrably* cannot
change `preservation_root` — one comparison, no re-hashing. MVP proved the operation
is wanted (`anla strip` exists because a decision log records what a model was told
and chose, which is not always something to hand over with the data), and MVP had to
rebuild the entire manifest to do it.

Still open: whether `metadata_root` is per-namespace. Probably, so that metadata a
reader cannot apply is a subtree it reports on rather than a verification failure.

---

## 6. Snapshots and the footer chain

Each snapshot appends: its new `CHNK` records, its `MANF`, then a `FOOT`.

```text
S(t+1) = (S(t), ΔO, ΔC, ΔM)
```

A footer record's payload carries: snapshot sequence; manifest offset and length;
primary index offset and length; **previous footer offset**; `preservation_root`;
and `auxiliary_root`. Absent values are omitted, never encoded as `null` — the CBOR
profile has no null, and absence is the absence of a key.

Payload integrity lives in the record header (`payload_hash`), not in a field inside
the payload, which would be self-referential.

**The footer names its own hash algorithm** in that record header. This is a
consequence of hash agility that only becomes visible once the reader exists: the
footer is read *before* the manifest that declares `hash_algorithms`, so it cannot
inherit the choice from it. An unknown algorithm there is refused rather than
guessed at.

Old footers are never rewritten. That is what makes an append crash-safe: an
interrupted write leaves a trailing partial footer, the previous one is still intact
and verifiable, and the archive reads as the older snapshot rather than as damaged.

A reader MUST be able to enumerate snapshots by walking `previous_footer_offset`
backwards, and MUST detect a cycle rather than following one.

**Open (whitepaper question 9):** multi-volume atomicity. MVP's footer is one
96-byte record at a known offset; with two volumes there is no such place, and the
chain has to become a first-class object rather than a convenience. Not decided, and
not blocking single-volume 1.0.

---

## 7. Hashes

`hash_algorithms` is a list, **read and never inferred** — the one thing 1.0 must not
copy from MVP, where the algorithm follows from the profile version.

- `blake3-256` is the required core.
- `sha256` is a declarable capability, not a second mandatory hash. Requiring both
  doubles the cost of every write to buy a hedge nobody asked for; allowing either
  with no required core produces two conformant archives that no single reader can
  open, which is worse.

Hash outputs are CBOR byte strings, not hex text. MVP used hex because its manifest
was JSON and JSON has no byte string; CBOR does, and 32 bytes beats 64 characters in
a structure that appears once per chunk.

**Not implemented.** Until BLAKE3 lands, the reference implementation writes and
reads `sha256` only, and says so in `hash_algorithms` — which is exactly the
mechanism working as intended, and is why hash agility is in the container rather
than in a later revision.

---

## 8. Codecs

A numeric registry, so a codec identifier costs two bytes rather than a string per
chunk:

| id | codec | state |
|---:|---|---|
| 0 | `store` | core |
| 1 | `zstd` | core, not implemented |
| 2 | `deflate` | capability |
| 3 | `lzma2` | capability |
| 4 | `brotli` | capability |
| 5 | `lz4-frame` | capability |

Chunk descriptors carry enough parameters for an independent decoder to reproduce
decoding — for Zstandard that is the frame profile, the level actually used, the
window log and any dictionary reference. A codec whose parameters are not fully
recorded is a codec that cannot be decoded by anyone else, which is refutation
condition 7.3 again.

Compression happens before encryption, never the reverse.

---

## 9. Capabilities

```text
anla:core:objects:1
anla:core:chunks:1
anla:core:snapshots:1
anla:hash:blake3-256:1
anla:codec:zstd:rfc8878
anla:chunking:anla-cdc-1
anla:index:fulltext:1
anla:security:cose-sign1:1
```

Required and optional are separate lists. An unknown **required** capability MUST
cause refusal; an unknown **optional** one MUST be ignored without comment.

The registry lives in this repository as text, not in a service. A registry behind
someone's API is a format with a single point of failure the specification never
mentions.

---

## 10. What this draft does not decide

Carried from [`design/decisions-for-1.0.md`](design/decisions-for-1.0.md), where each
has a note on what would settle it: metadata sidecar standardisation (Q5); encrypted
archives balancing partial access against metadata privacy (Q7); multi-volume
snapshot atomicity (Q9); how a planner proves nothing was left unpacked (Q11) and
whether that can be formalised (Q12); and a decode-latency budget so a planner cannot
trade extraction speed for ratio unnoticed (Q13) — which is implementable now and is
the most under-rated item on the list.

Parity stays out of the core (Q8). A core that promises repair has to promise a
repair rate, and a repair rate depends on the failure model of the medium, which a
format does not know. What the core does owe is that damage to one chunk costs you
only that chunk — true in MVP, and a conformance requirement here.

---

## 11. Order of work

1. **Milestone 0 — freeze the container.** Header, record frame with flags, footer
   chain, capability URIs, the CBOR manifest, CDDL schemas. Two implementations
   reading each other's bytes, and the differential fuzzer pointed at them, before
   any codec work. *Canonical CBOR is done; the rest of this list is not.*
2. **Milestone 3 before Milestone 2.** Append-only snapshots and cross-snapshot
   deduplication, reusing `anla-cdc-1` unchanged. Snapshots are the structural
   change; metadata namespaces are breadth, and doing breadth first means doing it
   twice.
3. **Milestone 2 — metadata namespaces**, one platform at a time, with the fidelity
   report as the deliverable rather than an afterthought.
4. **Milestone 4 — the planner**, rule-based first, with Q13's latency budget
   enforced by the validator before any model is allowed to propose anything.
5. **Crypto last.** Signatures and encryption sign or wrap bytes that must have
   stopped moving.

---

*Draft. © 2026 EVEMISS Technology Co., Ltd. Apache-2.0. Author: Neo.K.*
