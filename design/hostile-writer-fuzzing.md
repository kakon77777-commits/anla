# The integrity layer was shielding the parser from the fuzzer

Status: **fixed, and the fix found three real defects.** A note about the
instrument rather than the format, kept because the mistake is not specific to
ANLA and I would otherwise make it again.

## What was wrong with the fuzzer

`tools/fuzz_1_0.py` builds an archive, mutates its bytes, and compares what the
Python and Rust readers say about the result. Its mutation strategies were bit
flips, truncation, extension, hostile integers in aligned words, and block
splices. Sixteen thousand mutants, no divergences, and the freeze rule counted
that as one of its two clauses satisfied.

Every one of those strategies is stopped by a hash.

An ANLA record carries a `payload_hash` over its payload, and the reader checks it
before it parses anything. So a mutation that lands inside a manifest produces
exactly one outcome: both readers answer `integrity-failure`, they agree, the
mutant is scored a success, and

> the CBOR decoder, the canonical-form rules, the path rules, the required-member
> rules and the root arithmetic **are never executed**.

Those are most of the reader. The fuzzer was not testing them and its clean report
did not mean they agreed — it meant they had never been asked. This is
[`feedback-gate-evidence-must-be-measured`](../../..) in a new costume: the check
was real, its inputs could not reach the thing it was checking.

The number that should have raised the question was already in the output.
Mutants "accepted by both" hovered around 2–5% and refusals were overwhelmingly
`integrity-failure`. A refusal distribution that flat is a description of the
first gate, not of the reader.

## What replaced it

`rehashed_manifest`: mutate the manifest payload, then **repair the hash over the
mutated bytes** — recompute `payload_hash`, rebuild the record, rebuild the footer.

The threat model this represents is the one that matters. Not a corrupt disk,
which the hash layer handles and which no format can do more about, but **a writer
that is lying**: an archive assembled deliberately, with every hash correct, over
content designed to make a reader do something it should not. That archive passes
every integrity check ever written, and the only thing between it and the caller is
the rules.

It is also the only mutation class that can reach them.

## What it found immediately

Three defects, all in Python, all the same shape.

| what the archive did | Python before | Rust | who was right |
|---|---|---|---|
| `path` holding bytes that are not UTF-8 | `UnicodeDecodeError`, exit 1 | `manifest-invalid`, exit 4 | Rust |
| object entry with no `path` member | `unsafe-object`, exit 9 | `manifest-invalid`, exit 4 | Rust |
| manifest with no `hash_algorithms` member | `KeyError`, exit 1 | `manifest-invalid`, exit 4 | Rust |

Two crashed. The third was worse than a crash: Python reported a **security event**
— "unsafe path" — about a path that did not exist. A caller acts differently on the
two answers. One sends them to an audit log looking for an attacker; the other
sends them to fetch another copy of a damaged file. Saying the wrong one is not a
cosmetic difference.

### They were one mistake, written three times

Each was **a required member read somewhere other than the place that checks
required members are present**:

- `parse_record` and `parse_footer_record` wrapped `CborError` by hand;
  `parse_manifest` was the third such site and nobody wrapped it.
- `verify_manifest` checks `object_id` presence with `not in` and then reads `path`
  with `.get()`, handing `None` to a validator that judges *legality*.
- `read_snapshot` reads `manifest["hash_algorithms"]` to cross-check it against the
  record header — seven lines *before* `verify_manifest`, the only function that had
  ever checked a member was there.

So the fixes are not three patches. They are three relocations, each moving a check
into the operation that cannot proceed without it:

- `cbor.decode_untrusted` — the one way archive bytes become objects, and therefore
  the one place a decode failure is classified. No hand-written wrapper survives.
- `manifest.sorted_by_path` — the one way objects are ordered, and therefore the one
  place a path is proven encodable. It was previously five copies of
  `sort(key=lambda e: e.path.encode("utf-8"))`, all five of which assumed.
- `manifest.parse_manifest` — presence moved out of the validator and into the
  *constructor*, so no downstream code can be handed an incomplete manifest and
  forget to ask.

The distinction the second fix restores is worth naming, because it is the one the
`path` bug destroyed: **absence is `manifest-invalid`, illegality is
`unsafe-object`.** A member that is not there cannot be unsafe.

## What this says about the freeze rule

The rule was: freeze nothing until two implementations produce byte-identical
archives *and* a differential fuzzer finds no verdict divergence. Both clauses were
satisfied. Both were still satisfied the moment before this mutator existed, and
three divergences were sitting in the reader the whole time.

The rule is not wrong. What it needed was the observation that **a fuzzer is bounded
by the states its mutations can construct**, and that a layered format's early
layers are very good at making later ones unreachable. The same reasoning applies to
anything else guarded behind a checksum, a signature, or a schema validator: the
guard that protects the code also hides it.

The falsifiability question to ask of any fuzzer, then, is not "did it find
anything" but: *which code can a mutation actually reach?* Answering it here took
one measurement — instrument the reader, count which functions ever run — and the
answer would have been embarrassing at any point in the previous sixteen thousand
mutants.

## Where this lives now

- `tools/fuzz_1_0.py` — `rehashed_manifest`, 20 shares of the strategy pool.
- `python/tests/test_hostile_writer_1_0.py` — the same construction as a fixture, so
  the three defects have named tests rather than a seed that happened to find them.
  Its `forge()` rebuilds the footer rather than requiring a same-length edit, after
  the first version could only express same-size lies and failed on a length
  mismatch while appearing to test path safety.
