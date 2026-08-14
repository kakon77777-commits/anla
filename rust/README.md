# `anla1-rs` — the second implementation

```bash
cargo build --release
./target/release/anla1-rs verify   ../some.anla
./target/release/anla1-rs snapshots ../some.anla
./target/release/anla1-rs list      ../some.anla
./target/release/anla1-rs extract   ../some.anla    # path + BLAKE3 per file
./target/release/anla1-rs selftest
```

This exists for one reason. The freeze rule at the top of
[`SPEC-1.0-DRAFT.md`](../SPEC-1.0-DRAFT.md) says:

> No part of this document is frozen until two independent implementations produce
> byte-identical archives from the same input, and a differential fuzzer finds no
> verdict divergence between them.

Since July there has been one. This is the other half.

## What it does and does not do

It **reads**. It does not write. A reader is the half that matters more for a
preservation format — anyone may write an archive, everyone has to be able to read
one — and it is the half a differential fuzzer can use, because verdict agreement
needs no oracle.

Byte-identity of *writers* is therefore still unproven, and the specification says
which part of that is even provable: compressed output is a function of the
compressor, so byte-identity is a claim about `store` while `objects_root` and the
chunk-id set are what must match under any codec (§8).

## What is written here rather than imported

Two crates only: `blake3` and `zstd`, the primitives the format names. Everything
the specification actually *defines* is written out:

| | why |
|---|---|
| Canonical CBOR, encoder and strict decoder | A crate would enforce that crate's idea of CBOR. The point of a second implementation is to disagree where §5.1 is ambiguous. |
| The container: header, record frame, footer chain | The byte tables in §3 and §4 are the thing being tested. |
| The Merkle construction | Domain separation, odd nodes promoted not duplicated, a defined empty root. Three choices, each load-bearing (§5.3). |
| SHA-256 | Present only so archives written before BLAKE3 still read. One more crate carried forever, for that, is a bad trade. |

## An honest limitation

**Two implementations by one author are weaker evidence than two by two authors.**
I have read the Python. A shared *misreading* of the specification reproduces here
rather than being caught, and no amount of care changes that.

What it still catches is real: everywhere the document is ambiguous enough that two
writings of it diverge, and everywhere one implementation does something the
document never said. The fuzzer is what turns that from a hope into a search —
[`tools/fuzz_1_0.py`](../tools/fuzz_1_0.py) mutates a valid archive and asks both
readers the same question.

## What it found on its first run

**Record sequences (§4.3) were not checked here at all**, and the fuzzer found it in
under three hundred mutants: Python refused, this reader accepted.

That rule has now been missed three times by three separate attempts to implement a
document that states it plainly — both MVP implementations, and this one. The reason
is structural rather than careless. Everything else a reader does is seek-based:
find the footer, jump to the manifest, jump to each chunk. §4.3 is the only rule
that requires walking every record from the start, so it is the only one that costs
something no other check has already paid for. **An expensive rule with no other
caller is the rule an implementer skips.**

Two more came out of the same run, both about *which* refusal a reader gives when an
archive is broken in more than one way:

* **Structure before content.** "The bytes of this chunk are wrong" is not a
  statement anyone can act on about a file whose record framing has not been
  validated. The Python verifier now checks §4.3 before it checks chunk hashes.
* **A declared limit that is exceeded is a resource limit, not a malformed
  manifest.** The two readers classified a 16 MiB record header differently, and the
  caller's next move differs: one says "find another copy", the other says "this was
  written by something broken".

Fixing that second one immediately produced a third finding, which is the one worth
remembering. Python's backwards footer scan caught three exception *types*, which
was accidentally complete until the reclassification — after which that refusal
started escaping the loop and aborting the search. **Catching by exception type
couples control flow to classification, so changing what an error is called silently
changes behaviour somewhere that never mentioned it.**
