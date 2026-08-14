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

**Where that stands, precisely: both clauses are now satisfied.**

There is a second implementation — [`rust/`](rust/), sharing no code with the Python
below `blake3` and `zstd`, with its own canonical CBOR, container, Merkle
construction, manifest verification, SHA-256, `anla-cdc-1` chunker, reader and
writer.

* **Byte-identity.** The same directory packed by both writers, under the same fixed
  `(uuid, created_ns)` with no recorded metadata, produces **identical bytes** — with
  fixed chunking and with `anla-cdc-1` at two profiles. Canonical CBOR, object
  ordering, chunk boundaries, record framing and every Merkle root have to agree
  exactly for that to happen, because any one of them disagreeing moves an offset.
  Checked by [`tools/compare_writers.py`](tools/compare_writers.py) in CI.
* **No verdict divergence.** 16,000 mutants across four seeds, after the four
  disagreements the fuzzer found on its first runs and which are recorded in §4.3
  and below.

**And what that clause did not cover, which is the more useful thing to record.**
Every mutation strategy the fuzzer had was defeated by a hash before it could be
interesting: a record's `payload_hash` is checked before its payload is parsed, so a
mutated manifest produced `integrity-failure` from both readers, they agreed, and
the CBOR decoder, the canonical-form rules, the path rules, the required-member
rules and the root arithmetic **were never executed**. Sixteen thousand mutants had
reached none of them. The clause was satisfied and most of the reader was untested.

The strategy that reaches them mutates a manifest and then *repairs the hash over
what it mutated* — not a corrupt disk, but a writer that is lying, with every
integrity field correct over content built to make a reader misbehave. It found
three divergences on its first five hundred mutants, all of them Python crashing or
misclassifying where Rust answered correctly. They are fixed, they have named tests
in `python/tests/test_hostile_writer_1_0.py`, and the reasoning is in
[`design/hostile-writer-fuzzing.md`](design/hostile-writer-fuzzing.md).

The general form is worth stating in a specification rather than a commit message:
**a fuzzer is bounded by the states its mutations can construct, and in a layered
format the early layers are very effective at making the later ones unreachable.**
Anything guarded behind a checksum, a signature or a schema validator has the same
blind spot. The question to ask of a fuzzer is not what it found, but which code a
mutation can reach at all.

The clause is stated over `store`, and §8 says why: compressed output is a function
of the compressor, so two writers on different libzstd builds may legitimately
differ. What must match under any codec is `objects_root` and the chunk-id set, and
that is what the comparison checks there instead.

**An archive names itself in two places, and they MUST agree.** `archive_id` in
every snapshot's manifest MUST equal `archive_uuid` in the bootstrap header. Nothing
checked this until the two writers were compared: a Rust append used an unset option
for the manifest while inheriting the header's real value, and **both readers
verified the result**. Two implementations agreeing that a broken archive is fine is
exactly what a *byte* comparison catches and a *verdict* comparison cannot — which
is the argument for having both, stated as an incident rather than as a principle.

Same shape as the hash algorithm being named in a record header and in the manifest
(§7): a field stated twice needs a rule saying they match, or it is two fields that
happen to be spelled the same.

**So what is still holding the word DRAFT in the title?** Not the freeze rule.
Three things, and they are worth naming rather than leaving as a feeling:

1. **Two implementations by one author are weaker evidence than two by two.** A
   shared *misreading* of a sentence below reproduces in both rather than being
   caught. The exercise finds every place the document was ambiguous enough that two
   writings of it diverged — five, so far — and nothing at all about the places it
   is confidently, consistently wrong.
2. **The Rust writer is narrower than the Python one**: no `--skip-unsupported` and
   so no fidelity report. It now covers files, directories, symbolic links, recorded
   metadata and appending, and byte-identity is demonstrated over all of those —
   including a two-snapshot archive — but not over the parts still missing.
3. **§10 still lists open questions**, including the object name model (whitepaper
   Q4), which will change `object_id` when it is answered.

Freezing means promising not to change these bytes. The rule this draft set itself
has been met; the judgement about whether the design is *right* has not been made,
and it is a different judgement.

### What exists so far

| Piece | State |
|---|---|
| Canonical CBOR encoder and strict decoder | **implemented** — [`python/anla1/cbor.py`](python/anla1/cbor.py), 129 tests |
| Content-defined chunking (`anla-cdc-1`) | **implemented and cross-verified**, reused unchanged from MVP |
| Container: header, record frame, flags, footer chain, capabilities | **implemented** — [`python/anla1/container.py`](python/anla1/container.py), 41 tests |
| Merkle construction and the five roots (§5.3) | **implemented** — [`python/anla1/merkle.py`](python/anla1/merkle.py), 65 tests |
| Manifest: objects, chunk map, roots, verification (§5) | **implemented** — [`python/anla1/manifest.py`](python/anla1/manifest.py), 32 tests |
| A complete archive, written and read back | **implemented** — 15 end-to-end tests |
| Append-only snapshots and cross-snapshot deduplication (§6) | **implemented** — [`python/anla1/snapshot.py`](python/anla1/snapshot.py), 28 tests |
| Filesystem layer: scan a directory, restore a snapshot (§5.2.1) | **implemented** — [`python/anla1/fs.py`](python/anla1/fs.py), 14 tests |
| The `anla1` command line, with `--json` and the whitepaper's exit codes | **implemented** — [`python/anla1/cli.py`](python/anla1/cli.py), 12 tests |
| A streaming writer | **implemented** — `write_snapshot` puts records on disk as they are produced and memory-maps the existing archive, so the bound falls from *archive + largest file* to *largest file*. An append writes after the newest complete footer and patches the 64-byte header rather than rebuilding the file. Byte-identical to the in-memory path, which is the only property such a refactor is allowed to have. |
| CDDL schemas | [`schemas/anla-1.0.cddl`](schemas/anla-1.0.cddl), shape only |
| Object name model (whitepaper Q4) | one `path`, deliberately not settled |
| BLAKE3-256 | **implemented** — [`python/anla1/blake3.py`](python/anla1/blake3.py), a dependency-free reference plus the Rust fast path, 55 tests |
| Chunking profile recorded and checked across snapshots | **implemented** |
| Zstandard (§8) | **implemented** — [`python/anla1/codecs.py`](python/anla1/codecs.py), 12 tests |
| Metadata namespaces and the fidelity report (§5.2.2) | **implemented** — 27 tests |
| Symbolic links | **implemented** — stored verbatim, restored under policy |
| **A second implementation — reader *and* writer** | **implemented** — [`rust/`](rust/); `store` output is byte-identical to the Python writer's, checked in CI on three platforms |
| Differential fuzzing for 1.0 (Python against Rust) | **implemented** — [`tools/fuzz_1_0.py`](tools/fuzz_1_0.py) |
| Signatures, encryption, parity | later milestones |

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

**And then it happened a third time.** The Rust reader, written from this section
with that paragraph in front of it, did not implement the check either — and the
1.0 differential fuzzer found it in under three hundred mutants. Three independent
attempts, one plainly stated rule, three misses.

So the reason is structural, not careless, and it belongs here rather than in a
commit message. **Every other rule a reader enforces is seek-based**: find the
footer, jump to the manifest, jump to each chunk. This is the only one that requires
walking every record from the start, so it is the only one that costs a pass nothing
else has already paid for. An expensive rule with no other caller is the rule an
implementer skips.

A conforming reader MUST make that pass. If that cost is unacceptable to some future
profile, the answer is to change the rule, not to leave it stated and unenforced.

### 4.4 Alignment is a rule about starts, not only about padding

Every record MUST begin at an offset that is a multiple of eight.

This does not follow from "records are padded to eight bytes". Padding keeps a
sequence of records aligned only while every writer also *starts* at an aligned
offset, and the case where one does not is not hypothetical: a torn append leaves a
file at an arbitrary length, and a writer that resumes at the end of that file puts
every subsequent record at a misaligned offset.

The consequence is worse than untidy. `find_latest_footer` scans backwards in
alignment-sized steps (§6), so a misaligned footer is never probed — the archive
reads as the previous snapshot, with every hash in it correct, and no error anywhere.
It is the same failure class as trusting `latest_footer_hint`, reached by a
different route, and it was found by appending to a deliberately torn archive rather
than by reading this document.

A writer therefore MUST resume an append at the end of the newest complete snapshot
rather than at the end of the file. See §6.

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

### 5.2.1 Object paths and kinds

An object's `path` MUST be relative, MUST NOT be empty, MUST NOT contain a NUL, a
drive letter, or a `.` or `..` component, and MUST use `/` as its only separator.
The rule is MVP's ([SPEC.md §9](SPEC.md#9-path-safety)), reused unchanged.

**A path that would have to be rewritten to satisfy that rule is refused, not
rewritten.** The distinction is the whole content of this subsection. MVP's
`safe_path` *returns* a normalized path, and normalization is not identity: it turns
a backslash into a separator, so a POSIX file genuinely named `a\b` would be stored
as `a/b` and restored as a file `b` inside a directory `a`. The tree that came out
would differ from the tree that went in with every hash verifying. A conforming
reader MUST refuse such a path, and a writer MUST refuse such a name rather than
storing the rewritten form.

A `path` MUST also be **encodable as UTF-8**, and a writer MUST check this rather
than discover it. The requirement looks redundant — `path` is CBOR text, so of
course it is UTF-8 — but a POSIX filename is an arbitrary byte string, and a runtime
that surfaces an undecodable byte as a lone surrogate hands the writer a `str` that
cannot be encoded back. The rule above governs a path's *structure*; this one
governs whether it can exist at all, and the two are separate checks. Objects are
ordered by their UTF-8 path bytes, so a name with no UTF-8 bytes has no position in
the order and cannot be written even in principle.

Errors here divide, and a conforming reader MUST NOT merge them: a `path` member
that is **absent or not a text string** makes the manifest invalid, while a `path`
that is present and breaks a rule above makes the object unsafe. The first says
these bytes are damaged; the second says this archive is trying to escape. A caller
acts on them differently.

This is where whitepaper question 4 bites, and it is not answered here. Until the
name model carries native and legacy forms alongside the portable one, a name that
cannot survive the round trip is refused, because refusing is the only answer that
does not quietly change what the archive contains. `design/q4-name-model.md` sets
out the model that will answer it; the checks in this subsection are the part of it
that is already true and already enforced.

`kind` MUST be `regular-file`, `directory` or `symbolic-link`. Devices, sockets and
FIFOs are not representable in 1.0 and MUST NOT be approximated by something that is
— a socket stored as an empty file is a different tree.

A `symbolic-link` carries `target`, a **byte string, stored exactly as the operating
system returned it**. It is not a path in this archive's namespace: it is an opaque
string the *target* filesystem interprets, and it may be absolute, may leave the
tree, may point at nothing. A writer MUST NOT normalize, resolve or validate it —
doing so stores a different link, which is the rule above with worse consequences,
because this one gets followed.

Whether such a link may be **created** is a separate question, and belongs to the
restorer. A target that is absolute or escapes the destination MUST be refused on
restore unless the operator asks for it, because creating it is what turns an
extracted archive into a route to the rest of the filesystem.

### 5.2.2 Metadata namespaces, and the fidelity report

Object metadata is a map of namespace to entries: `{"common": {"mtime_ns": …},
"posix": {"mode": …}}`. Flat keys are refused — `mode` means something different
on every platform, and a bare key leaves a reader nowhere to record that it could
not use it.

**Metadata namespaces are `optional_capabilities`, never `required`.** An earlier
draft of §5.3 left open whether `metadata_root` should be split per namespace, so
that "metadata a reader cannot apply is a subtree it reports on rather than a
verification failure". That premise does not hold and the question is now closed:
verification is hashing, not interpretation. Object metadata is inside `object_id`,
so a reader that has never heard of `posix` computes the same id over the same
canonical CBOR, verifies, and extracts every byte — it simply cannot apply what it
verified. An unknown namespace could never have caused a verification failure, so a
root per namespace buys nothing. What can wrongly refuse such an archive is a
*capability*, and that is where the granularity belongs.

The archive-level `metadata` array carries namespaced blocks that are not per
object. The first is `fidelity`:

```text
{"namespace": "fidelity",
 "entries": [{"path": "dev/log", "reason": "kind-not-representable",
              "kind": "socket"}]}
```

Every entry MUST carry a `path` and a `reason` from a closed set
(`kind-not-representable`, `read-failed`, `excluded-by-policy`). Free text would
make the report unsummarisable, and a record of *absence* that nobody reads is one
that may as well not be there.

**The report is in the preservation plane, and MUST NOT be placed in `auxiliary`.**
`auxiliary` is disposable by definition; a record of what the archive does not hold
must not be droppable, because dropping it turns a declared-incomplete archive into
an apparently complete one — worse than either. It is therefore covered by
`metadata_root`, and removing it changes the snapshot's identity.

A reader MUST surface the report without being asked. Three states exist and a tool
that conflates them is not reporting: **stored and applied**, **stored but not
applied** (this reader or filesystem cannot use it — recoverable elsewhere), and
**not stored** (gone). Only the last belongs in the archive, because only the writer
can know it.

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

```text
objects_root ┐
chunks_root  ├─► preservation_root
metadata_root┘
auxiliary_root      (outside, on purpose)
```

#### The Merkle construction

Pinned, for the same reason the gear table is: two implementations that build the
tree differently compute different roots for identical content, and the
disagreement is invisible until somebody compares two archives.

```text
leaf(data)         = H(0x00 || data)
node(left, right)  = H(0x01 || left || right)
empty tree         = H(0x02)
preservation_root  = H(0x03 || objects_root || chunks_root || metadata_root)
object_id          = H(0x10 || canonical CBOR of the object without its id)
```

Levels are built pairwise from the left. **An odd node is promoted unchanged, never
duplicated.** Three choices there are load-bearing:

- **Domain separation.** Without the `0x00` / `0x01` prefixes, a tree over two
  leaves and a tree over one leaf whose data happens to be `left || right` produce
  the same root, so a proof for one is a proof for the other. One byte per hash
  closes the classic Merkle second-preimage attack.
- **Promotion, not duplication.** Duplicating the odd node — Bitcoin's original
  choice — makes `[a, b, c]` and `[a, b, c, c]` produce the same root
  (CVE-2012-2459). The conformance suite asserts that collision is *absent* rather
  than trusting that it is.
- **A defined empty root.** Empty is a legitimate state — no metadata namespaces, no
  intelligence plane — and a construction with no answer for it invites every
  implementation to invent one.

Leaf order is part of the definition: objects by `object_id`, chunks by `chunk_id`,
metadata by its encoded entry. Sorted by encoded bytes, as everywhere else here,
because that is the order two implementations can agree on without agreeing on a
collation.

A root nobody can produce a proof against is only a checksum, so an inclusion proof
is part of the construction rather than a later addition — partial materialization
has to be able to show that what it extracted belongs to the snapshot it claims.

#### What `preservation_root` does not cover, and what that means for signatures

It covers objects, chunks and metadata. It does **not** cover the manifest's policy
fields: `required_capabilities`, `hash_algorithms`, `created_unix_ns`, the packing
plan. Editing those leaves `preservation_root` identical — verified, not assumed.

They are not unprotected: the `MANF` record header hashes the manifest payload, so
any edit changes that hash. But it does mean a **signature over `preservation_root`
alone would not bind the policy fields**, and an archive could then be re-labelled
with different capability requirements while its signature still verified.

So a signature MUST bind `snapshot_id` — the hash of the canonical manifest
encoding — and not merely the preservation root. The whitepaper's chapter 30 already
signs `archive_id ‖ snapshot_id ‖ preservation_root`; this paragraph exists so that
the `snapshot_id` term is understood as load-bearing rather than as belt and braces,
because it is exactly the term a later simplification would drop.

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

### 6.1 A manifest describes its whole snapshot

A snapshot's `MANF` MUST list every object in that snapshot's tree and a descriptor
for every chunk it references — including chunks whose `CHNK` records were written
for an earlier snapshot. A manifest is never a delta.

So extracting any snapshot reads exactly one manifest, and `preservation_root`
covers a tree the document containing it actually describes. The alternative was
considered and rejected: a delta manifest makes snapshot *N* unreadable without all
*N* of its ancestors, and makes a root cover something absent from its own document,
which is not a root.

The delta therefore lives in the payload records — `ΔC` above — which is where the
bytes are.

The cost is that a manifest grows with the tree rather than with the change. Two
things absorb it: `FLAG_COMPRESSED_METADATA` (§4.2), which exists for exactly this
and is set by nothing else so far, and the fact that consecutive manifests are
nearly identical, which is the case compression is good at.

### 6.2 A chunk is stored once per archive

If a chunk id is already present anywhere in the archive, a new snapshot MUST
reference the existing record rather than writing the bytes again.

This requires a chunk id to descriptor lookup across prior snapshots. Walking those
manifests is sufficient and requires nothing new. An `INDX` record MAY carry a
cumulative index, and if present it is a **cache**: a reader MUST produce identical
results with it ignored, and MUST resolve any disagreement in favour of the
manifests. An index permitted to win is a second format.

**One archive uses one chunking rule, and one hash algorithm, for its chunk ids.**
The chunking profile is recorded in `packing_plan` and an append that would use a
different one is refused. Two snapshots cut at different boundaries produce
different chunk ids for identical bytes, so deduplication silently does nothing
while every check still passes — the same shape as the hash rule below, and found
the same way: by measuring a real corpus and noticing the numbers were wrong.

 Chunk ids are hashes, so
two algorithms in one archive means two namespaces of chunk id sharing one lookup —
identical bytes stored twice and deduplication silently doing nothing. Hash agility
(§7) is per archive, not per snapshot. This is the one place where agility has a
boundary, and it is a consequence of content addressing rather than a limitation of
the container.

### 6.3 Lineage is checked

- `parent_snapshot` MUST be absent when `snapshot_sequence` is 1, and present
  otherwise.
- `parent_snapshot` MUST equal the `snapshot_id` of the snapshot that the footer
  chain points back to.
- `snapshot_sequence` MUST be exactly one greater than its parent's.
- The oldest snapshot in a chain MUST have `snapshot_sequence` 1. (Single-volume
  only; question 9 above is what would relax this.)

Note what an archive violating the second rule does *not* need in order to look
correct: nothing else changes. `parent_snapshot` is not covered by
`preservation_root` — the gap §5.3 records — so an archive can name any ancestor at
all, or a different one, with every root and every payload hash still verifying.
Checked here, or it is decoration.

### 6.4 No forward references

A chunk descriptor MUST NOT point at a record that begins at, or extends past, the
offset of the `MANF` that references it.

In an append-only file every byte a snapshot depends on was written before it, which
turns this from a plausibility judgement into arithmetic a reader can evaluate while
holding one manifest and one footer.

### 6.5 One chunk id, one descriptor

If two snapshots reference the same chunk id, their descriptors MUST be identical in
every field. The same content id with different stored bytes, or a different place
to find them, means one of the two snapshots is wrong about what it stored, and a
content-addressed format cannot be indifferent to which.

### 6.6 Appending

A writer MUST resume at the end of the newest complete snapshot — the end of its
`FOOT` record — and not at the end of the file.

Everything beyond that footer belongs to no snapshot: it can only be an append that
did not finish, since a chunk record can be referenced only by a manifest written
after it. Discarding it reclaims the space, and, by §4.4, is what keeps the next
record aligned. A writer that appends after the abandoned bytes produces an archive
whose newest footer cannot be found.

Old bytes are otherwise never modified. The one exception is `latest_footer_hint` in
the bootstrap header, which is advisory and which no reader may use to decide what is
latest (§3), so moving it cannot change how anything reads.

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

### 7.1 What landing BLAKE3 demonstrated

Adding it changed one table — the algorithm registry — and moved no container
field. Archives written with `sha256` before it existed still read, and the reader
picks its hash function by looking up the name it just read out of the record it is
verifying. That is what hash agility was for, and it is now exercised rather than
declared: the end-to-end suite builds and reads the same archive under both
algorithms, and refuses an archive whose `MANF` record header and `hash_algorithms`
disagree about which one was used.

`hash_bytes` deliberately has **no default algorithm**. Every caller has just read a
name from the archive, and a default would be an invitation to skip that read —
which is precisely the mistake `ANLA-MVP` made by inferring the hash from the
profile version.

### 7.2 Two implementations of the hash itself

`blake3` (the Rust extension) is used when installed, and
[`python/anla1/blake3.py`](python/anla1/blake3.py) is a dependency-free reference
that the suite asserts agrees with it byte for byte — at every chunk boundary
(1024, 1025, 2048, 3072, 4096, 8192, 16385), at random lengths, incrementally, and
for extended output.

The reference exists because **a specification whose hash is only available as a
compiled wheel has a hole in it**: someone checking this document cannot read what
it says the hash is. Which implementation runs is then a performance question and
never a correctness one — and if that ever stops being true, a test says so before
an archive does.

---

## 8. Codecs

A numeric registry, so a codec identifier costs two bytes rather than a string per
chunk:

| id | codec | state |
|---:|---|---|
| 0 | `store` | core |
| 1 | `zstd` | core |
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

**A codec cannot reach `objects_root`, and can reach `preservation_root`.** Chunk ids
are hashes of the *raw* chunk, so the tree's identity does not depend on how it was
stored; chunk *descriptors* carry `codec_id`, `payload_length`, `payload_hash` and an
offset, so `chunks_root` — and through it `preservation_root` — does.

That has a consequence for the freeze rule at the top of this document, and it is
better stated than discovered. Compressed output is a function of the compressor:
two conforming writers on different libzstd builds may produce different bytes for
the same input and both be right. So:

- **byte-identical archives** is a claim about `store`, and is what the
  cross-implementation check must use;
- for a compressed archive, what two implementations MUST agree on is
  `objects_root` and the set of chunk ids — the tree, not the layout.

`packing_plan.codec` records the level and the libzstd version that produced the
bytes, because a plan that omits them cannot explain why two writers disagreed.

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
   any codec work. *Done in one implementation, which is not the same as frozen.*
2. **Milestone 3 before Milestone 2.** Append-only snapshots and cross-snapshot
   deduplication, reusing `anla-cdc-1` unchanged. Snapshots are the structural
   change; metadata namespaces are breadth, and doing breadth first means doing it
   twice. *Done in one implementation — §6.1 to §6.6 are what implementing it
   settled, and §4.4 is what it found.*
3. **Milestone 2 — metadata namespaces**, one platform at a time, with the fidelity
   report as the deliverable rather than an afterthought.
4. **Milestone 4 — the planner**, rule-based first, with Q13's latency budget
   enforced by the validator before any model is allowed to propose anything.
5. **Crypto last.** Signatures and encryption sign or wrap bytes that must have
   stopped moving.

---

*Draft. © 2026 EVEMISS Technology Co., Ltd. Apache-2.0. Author: Neo.K.*
