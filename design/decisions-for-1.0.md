# Decisions for ANLA 1.0

**Status:** working design record, not normative.
**Normative today:** [`SPEC.md`](../SPEC.md) — `ANLA-MVP v0.1`.
**Target:** the format in [the whitepaper](../papers/02-anla-whitepaper.en.md).

The whitepaper ends with fifteen open questions. Several of them are not
philosophy: a normative 1.0 cannot be written while they are open, because each one
determines bytes. This document records which are now answered, what the answer is,
and — for the ones still open — what would settle them.

The pattern to hold onto is the one the project already learned the hard way. The
first release's writer ordered manifest objects with `localeCompare`, so the bytes
depended on which machine wrote them. Nobody noticed until two implementations were
compared byte for byte. **Every open question below is a place where the same defect
can hide**, and the ones that hide it best are the ones that look like details.

---

## Answered

### Q3 — How can FastCDC parameters form a permanently stable profile?

**Answered, with running code.** See
[SPEC.md §8.3.1](../SPEC.md#831-content-defined-chunking--the-anla-cdc-1-profile).

Writing `"fastcdc"` plus three sizes into a manifest is not a specification. Two
implementations would still disagree about the gear table and the mask, and
therefore about where chunks begin — and because the chunk id is the content id,
disagreeing about boundaries means disagreeing about every hash in the archive.

`anla-cdc-1` pins the fingerprint (32-bit gear, chosen so a JavaScript
implementation can be exact without bignum arithmetic), the boundary predicate
(top *k* bits zero — the top, because that is where gear hashing accumulates
history), the normalization rule, and the search window. The part worth carrying
into 1.0 unchanged is the gear table:

```text
gear[i] = big-endian uint32 of SHA-256("anla-gear-1" || 0x00 || i)
```

**Derived, not published as 256 constants.** A table that must be transcribed
between codebases is a table that will one day be transcribed wrongly, and the
error would be invisible until someone compared archives. A derived table can be
regenerated in three lines and checked against one digest.

Both reference implementations now cut identically — the `cdc-shifted-pair`
fixture is byte-exact across them — and the profile needed no format version bump,
which is itself a finding: see Q15.

*Cost of getting this wrong:* every chunk id in every archive.

### Q14 — Cross-implementation parser differential testing

**Answered, and it immediately earned its keep.**
[`tools/fuzz_differential.py`](../tools/fuzz_differential.py) mutates the frozen
vectors and compares both implementations' verdicts. It asks only whether they
*agree* — which needs no oracle — and treats disagreement as a defect in an
implementation or in the specification for leaving the case open.

Twenty thousand mutants produced two findings, and the second is why this belongs
before 1.0 rather than after:

1. A 64-bit field above `Number.MAX_SAFE_INTEGER` was classified as a resource
   limit by one implementation and a malformed manifest by the other.
2. **Record `sequence` was specified and unchecked by both.** "1-based, strictly
   increasing" is unenforceable by a reader that does not walk the whole stream —
   and the access pattern this format is designed for does not walk it. Python
   accepted `sequence = 2^63`; JavaScript refused it only because it could not
   represent the number. Neither was checking the rule.

The lesson for 1.0: the whitepaper's target format has *far* more stated
invariants than this profile — flag bits, capability URIs, footer chains, metadata
namespaces, signature bindings. Every one of them is a candidate for the same
failure, where the prose says something and no code evaluates it. The fuzzer should
grow alongside the format rather than be bolted on when it is called frozen.

### Q1 — BLAKE3 only, or SHA-256 as well?

**Decision: `hash_algorithms` stays a list, BLAKE3-256 is the required core, and
SHA-256 is a declarable capability rather than a second mandatory hash.**

Requiring both doubles the hashing cost of every write to buy a hedge nobody has
asked for. Allowing either without a required core means two conformant archives
that no single reader can open, which is worse than a slower one. The manifest
already declares `hash_algorithms`, so a future migration has somewhere to live.

The one thing 1.0 must not do is what MVP does — assume the algorithm from the
profile version. `hash_algorithms` must be read, not inferred.

### Q2 — Which deterministic CBOR profile?

**Decision: RFC 8949 §4.2.1 core deterministic encoding, plus three restrictions
of our own**, all of which exist because MVP's canonical JSON needed the same ones:

1. No floating point anywhere in the preservation plane. MVP learned this as
   "nanosecond timestamps are decimal strings"; in CBOR they can be integers, but
   the prohibition stays, because a float is a value whose bytes depend on how it
   was computed.
2. Integers in their shortest form, which core deterministic encoding already
   requires — restated because it is the rule an implementation is most likely to
   get away with breaking locally.
3. No indefinite-length items in the preservation plane. Streaming writers want
   them; a signature over a manifest cannot afford them.

CDE (the stricter draft) is not adopted, because pinning to a moving draft is how
a format acquires a dependency it cannot version.

### Q15 — Should `.anla` stay a single file, or also define a directory layout?

**Decision: single file remains normative. A directory layout is a separate,
optional profile, and it is not 1.0's problem.**

The reason is what shipping content-defined chunking just demonstrated: a change
that touches only the writer needs no format version. A directory layout changes
what a *reader* must do, so it is a different format wearing the same name. The
single-file container is also what makes the whole thing testable as a byte string,
and every guarantee in this project is currently expressed as "these bytes".

---

## Decided in principle, needs the spec pass to be real

### Q6 — One Merkle root, or several?

**Leaning: several, exactly as the whitepaper's manifest already sketches** —
`objects_root`, `chunks_root`, `metadata_root`, then `preservation_root` over
those, with `auxiliary_root` deliberately outside it.

The reason is the invariant this project cares most about. `D(P, I) = D(P, ∅)` is
only cheap to verify if the intelligence plane hangs off its own root: you can then
show that dropping it cannot change the preservation root, instead of re-hashing
everything to discover that it did not. MVP already proved the operation is wanted
(`anla strip`), and it had to rebuild the whole manifest to do it.

Open: whether `metadata_root` is per-namespace. Probably yes, so that a platform
whose metadata a reader cannot apply is a subtree it can report on rather than a
verification failure.

### Q4 — Minimal cross-platform model for Windows NT names against POSIX bytes

**Leaning: keep the whitepaper's three-part name (`portable_utf8`, `native`,
`legacy`) and make exactly one part normative for identity.**

The MVP finding that matters here: two paths differing only by case, or only by
Unicode normalization form, are distinct in the archive and *not* distinct on some
filesystems. Both implementations now fail extraction with a fidelity error naming
both paths, and that behaviour was discovered by running the suite on a real
Windows host, not by reasoning.

So 1.0 must decide which part of a name is compared for uniqueness inside the
archive, and state plainly that no name model can prevent a target filesystem from
folding two of them together — only detect it.

### Q8 — Does parity enter the core preservation profile?

**Leaning: no.** Parity is a separate `PARI` capability, and the core stays a
format that can *detect* damage and localize it. A core that promises repair has to
promise a repair rate, and a repair rate depends on the failure model of the
medium, which the format does not know.

What the core does owe: damage to one chunk must not cost you the others. That is
already true in MVP and should stay a conformance requirement rather than becoming
a parity feature.

---

## Still open, and what would settle each

| # | Question | What would settle it |
|---|---|---|
| Q5 | Should a metadata sidecar be its own standard? | An implementation of Milestone 2 on all three platforms. Until something has actually tried to restore Windows ACLs onto ext4 and write the report, the sidecar's shape is speculation. |
| Q7 | Encrypted archives: partial access versus metadata privacy | Deciding who the adversary is. "Hide the paths" and "materialize one object without downloading the rest" are close to contradictory, and the resolution is a policy grade, not a clever construction. |
| Q9 | Multi-volume snapshot atomicity | Trying to write one. MVP's footer is one 96-byte record at a known offset; the moment there are two volumes there is no such place, and the footer chain has to become a first-class object. |
| Q10 | Remote chunk stores: SSRF, substitution, availability | This one is nearly answered by refusal: content addressing already defeats substitution, and `max_external_fetches: 0` is the sane default. What is open is whether an archive with external chunks may ever call itself `self-contained` — it may not — and how loudly a reader must say so. |
| Q11 | How does a planner prove nothing was left unpacked? | A coverage proof over the *selection*, not the archive. MVP does the easy half: every declared object is fully covered by chunks, and every exclusion is recorded in the plan. The hard half is proving the selection was what the user approved, which is an interface problem wearing a format costume. |
| Q12 | Formal coverage verification of a packing plan | Q11 with a stronger word for "prove". Worth attempting only after Q11's evidence trail exists. |
| Q13 | Stopping a planner trading extraction latency for ratio | A decode-latency budget in the plan, enforced by the writer during its round trip, and refusal if the measured budget is exceeded. This is implementable now and is the most under-rated item on the list: it is the one place where "an AI may plan" could quietly make archives worse. |


---

## The decision the whitepaper does not contain

`SPEC.md` §1 constraint 4 says a conforming writer must run in a browser tab with
no backend, and that constraint is *why* MVP uses SHA-256 and DEFLATE: both are
platform primitives. 1.0 wants BLAKE3 and Zstandard, and neither is.

That is the real fork, and it is not a codec question:

**Option A — keep the browser constraint for 1.0.** BLAKE3 and Zstandard arrive as
vendored WebAssembly. The live workbench and the offline single-file page keep
working, and the project keeps its most persuasive property: you can verify the
claims in a tab with no install. The cost is that "no dependencies, no build step"
stops being true of the JavaScript implementation, and a WASM blob is exactly the
kind of artifact whose provenance is hard to state.

**Option B — drop it for 1.0.** 1.0 is specified for Python and Rust, per the
whitepaper's chapter 41. The browser keeps the MVP profile, which stays frozen,
supported and honest about what it is. Two profiles, two audiences, one
specification family — and `ANLA-MVP` was always described as a profile, not a
lesser version.

**Recommendation: B, and say so in the specification rather than letting it be
discovered.** The browser profile earned its place — it is what makes the format
checkable by a stranger in thirty seconds — and turning it into a WASM download in
order to match a codec choice trades away the property that is actually rare.
1.0's job is to be the format that a preservation system can adopt; MVP's job is to
be the format anyone can verify. Those are different jobs.

If B is taken, one thing must be built early, not late: a `store`-only,
BLAKE3-hashed 1.0 archive that the JavaScript implementation can *read* even if it
cannot write. A format whose newest profile is invisible to its own demo page is a
format that will drift.

---

## Order of work, if 1.0 goes ahead

The whitepaper's milestones are already in the right order; what this document adds
is where the risk actually sits.

1. **Milestone 0 — freeze the container.** New magic, header, record frame with the
   `REQUIRED_FOR_EXTRACTION` / `AUXILIARY_DISPOSABLE` flag bits, footer chain, CDDL
   schemas, capability URIs. Two implementations reading each other's bytes before
   any codec work. This is where Q2 and Q6 stop being leanings.
2. **Milestone 3 before Milestone 2.** Append-only snapshots and cross-snapshot
   deduplication, reusing `anla-cdc-1` unchanged. Snapshots are the structural
   change; metadata namespaces are breadth. Doing breadth first means doing it
   twice.
3. **Milestone 2 — metadata namespaces**, one platform at a time, with the fidelity
   report as the deliverable rather than an afterthought. This is where Q4 and Q5
   get answered by contact with reality.
4. **Milestone 4 — the planner**, rule-based first, as the whitepaper insists. Add
   Q13's decode-latency budget here, in the validator, before any model is allowed
   to propose anything.
5. **Crypto last.** Signatures and encryption after the container is frozen, because
   both sign or wrap bytes that must have stopped moving.

The step before step 1 was a fuzzer (Q14). It exists now, and it found a stated
invariant that neither implementation checked — inside a profile small enough to
hold in one's head. The target format is much larger. Two implementations that
agree on every fixture agree only about the inputs someone thought of.
