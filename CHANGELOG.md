# Changelog

Notable changes to the ANLA project. The format profile version
(`ANLA-MVP 0.1`) is independent of the release date below: any change to the bytes
an archive contains, or to what a decoder must accept or reject, requires a new
`format_version`.

---

## 2026-07-27 (evening) — the 1.0 container, implemented

Milestone 0 continues. [`python/anla1/container.py`](python/anla1/container.py) is
the byte level of [`SPEC-1.0-DRAFT.md`](SPEC-1.0-DRAFT.md): header, record frame with
flags and 8-byte padding, the footer chain, and capability checking. 41 tests.

### Added

- **Record flags, with refusal as the default.** A reader meeting an unknown record
  type consults `AUXILIARY_DISPOSABLE`; with neither that nor
  `REQUIRED_FOR_EXTRACTION` set it refuses, because a writer that wanted the record
  skippable had a bit to say so. A record claiming to be both is an error in each
  direction.
- **The footer chain.** One `FOOT` per snapshot, chained by
  `previous_footer_offset`, never rewritten. A cycle is refused rather than followed;
  a chain that does not descend, or whose snapshot sequence does not decrease, is
  refused too.
- **Capability checking** — unknown *required* capabilities refuse, unknown
  *optional* ones are ignored silently and recorded as ignored, so a caller can see
  what was skipped without being handed a warning it might treat as an error.

### Changed in the specification, because implementing it said so

- **`latest_footer_hint` MUST NOT be used to determine which snapshot is latest.**
  The draft previously said a reader must verify the hint and fall back to scanning.
  That is not strong enough: a hint pointing at an *older but perfectly valid* footer
  passes verification, and a reader that accepts it reports an older snapshot as
  current with every hash checking out. The latest footer is now found by scanning
  backwards, always. Tests: a lying hint, four kinds of nonsense hint, an interrupted
  append, and a corrupt trailing footer all resolve to the correct snapshot.

- **The footer names its own hash algorithm.** A consequence of hash agility that
  only appears once the reader exists — the footer is read *before* the manifest that
  declares `hash_algorithms`, so it cannot inherit the choice from it. An unknown
  algorithm there is refused, not guessed.

- **The magic-number paragraph was wrong.** It claimed the 1.0 and MVP magics differ
  by one byte. They differ by four: both open with `ANLA`, the fifth byte is the
  generation digit, and inserting it shifts the CR/LF/SUB trailer along. The test
  comparing them is what caught it, which is the argument for writing tests against
  the specification rather than against the code.

## 2026-07-27 (later) — Option B taken; the 1.0 container draft begins

Neo chose **Option B**: `ANLA 1.0` is specified for Python and Rust, and `ANLA-MVP`
stays frozen as the profile anyone can verify in a browser tab. Recorded with its
consequences in [`design/decisions-for-1.0.md`](design/decisions-for-1.0.md).

### Added

- **[`SPEC-1.0-DRAFT.md`](SPEC-1.0-DRAFT.md)** — the container: new magic, header
  with a real `header_size`, record frame with the `REQUIRED_FOR_EXTRACTION` /
  `AUXILIARY_DISPOSABLE` flag bits and 8-byte padding, the footer chain, canonical
  CBOR manifests, several Merkle roots, hash agility, a numeric codec registry, and
  capability URIs.

  It opens with a table of what is implemented versus what is only specified, and it
  is held to the standard MVP was held to: **nothing is frozen until two independent
  implementations produce byte-identical archives and the differential fuzzer finds
  no divergence.** Two decisions are singled out as the reason a new magic number is
  needed rather than a minor version: record flags change what a decoder does with
  what it does not recognise, and the footer chain changes how it finds the manifest
  at all.

- **[`python/anla1/cbor.py`](python/anla1/cbor.py)** — canonical CBOR, no
  dependencies, in both directions. The encoder emits one byte sequence per value;
  **the strict decoder refuses non-canonical input** rather than normalizing it,
  because the manifest hash is computed over manifest bytes and a decoder that
  accepts two encodings of one logical manifest is a decoder through which two
  archives with different hashes mean the same thing.

  129 tests, including every encoding vector in RFC 8949 appendix A — the only way
  to be confident an encoder written from prose emits CBOR rather than something
  that merely round-trips through itself.

### Fixed

- **The new decoder crashed on deep nesting before it had any users.** Twenty
  thousand nested arrays raised `RecursionError`, which is a crash where a refusal
  was owed. Now bounded at 64 levels — deeper than any manifest, shallower than any
  attack. Found by probing the parser with the question the differential fuzzer asks
  ("does it refuse, or does it fall over?") rather than by reading it, which is the
  habit worth keeping as 1.0 grows.

## 2026-07-27 — differential fuzzing, and a stated invariant nobody checked

The whitepaper's open question 14 asked for cross-implementation parser
differential testing. It is answered, and it earned its keep on the first run.

### Added

- **[`tools/fuzz_differential.py`](tools/fuzz_differential.py)** — mutates the
  frozen vectors and compares both implementations' verdicts. Bit flips,
  truncation, hostile length and offset fields with the covering CRC repaired, and
  manifest-level defects re-sealed so every hash is correct — the last category
  being where the findings live, since a byte flip usually dies at a hash and
  proves only that hashing works.

  It asks whether the two implementations *agree*, which needs no oracle.
  Disagreement is always a defect in an implementation, or in the specification for
  leaving the case open. A divergence or an uncaught exception fails the run; a
  code mismatch is reported and kept as a file, because it may be a specification
  gap and triage belongs to a person.

- **`T-SEQ-1..4`** — regression tests for the sequence rule, and **`T-FUZZ-1`**, a
  bounded fuzz run on fixed seeds in the suite. CI runs 3000 mutants on a seed
  derived from the run number, so the space keeps being searched rather than the
  same mutants re-checked forever, and keeps any findings as an artifact.

  The suite also asserts the fuzzer *can* fail: it rigs a verdict and confirms the
  comparison notices. A fuzzer that cannot fail is a progress bar.

### Fixed

- **Record `sequence` was specified and unchecked by both implementations.** The
  spec said "1-based, strictly increasing across the archive" and no code evaluated
  it. Python, with unbounded integers, accepted `sequence = 2^63`; JavaScript
  refused it only because it could not represent the value. The phrasing was the
  root cause: "strictly increasing" is unenforceable by a reader that does not walk
  the whole stream, and the access pattern this format is designed for — footer to
  manifest, then jump to each chunk descriptor — does not walk it.

  [SPEC.md §4.3](SPEC.md#43-record-sequence) now states it as arithmetic a reader
  can actually evaluate: every sequence at least 1, each `CHNK` in
  `1..len(chunks)` and distinct, the `MANF` exactly `len(chunks) + 1`. Both
  implementations enforce all three.

- **A 64-bit field above `Number.MAX_SAFE_INTEGER` is now a malformed manifest, not
  a resource limit.** No runtime can hold 2^53 bytes, so such a field necessarily
  points outside the archive: it is nonsense, not merely large — and a decoder with
  unbounded integers reaches the same conclusion by comparing the extent against
  the archive size. [SPEC.md §11](SPEC.md#11-decoder-safety) says which
  classification is correct, because the fuzzer found both implementations refusing
  the same byte for different stated reasons.

### Verified

- 20,000 mutants across five seeds: no divergences, no code mismatches, no uncaught
  exceptions. 201 tests in the suite.

## 2026-07-26 (evening) — content-defined chunking, and open question 3 answered

Groundwork for 1.0, done in the cheap profile where getting it wrong is survivable.

### Added

- **The `anla-cdc-1` chunking profile** —
  [SPEC.md §8.3.1](SPEC.md#831-content-defined-chunking--the-anla-cdc-1-profile),
  [`python/anla/fastcdc.py`](python/anla/fastcdc.py), and the same in
  [`web/anla-core.js`](web/anla-core.js). The whitepaper's open question 3 asked how
  FastCDC parameters could become a permanently stable profile; writing `"fastcdc"`
  and three sizes is not an answer, because two implementations would still disagree
  about the gear table and the mask, and therefore about every chunk id in the
  archive.

  Everything is pinned: a 32-bit gear fingerprint (chosen so JavaScript can be exact
  without bignum arithmetic), a single boundary predicate on the *top* k bits,
  FastCDC's normalization rule, and the search window. The gear table is **derived**
  — `gear[i] = SHA-256("anla-gear-1" ‖ 0x00 ‖ i)[0:4]` — rather than published as 256
  constants, because a table that must be transcribed will one day be transcribed
  wrongly, invisibly. `gear_table_sha256` pins the result and travels in every plan.

  Both implementations cut identically: the `cdc-shifted-pair` fixture is byte-exact
  across them. What it buys, measured on that fixture: prepend ten bytes to a file
  and content-defined chunking keeps 54 of 55 chunks while fixed-size keeps none, so
  the same tree packs **45% smaller**.

- **No format version bump, deliberately.** A reader needs to know nothing about
  chunking — chunk references are chunk references — so this is a writer capability
  and `chunking` is descriptive, like the rest of `plan`. Its absence *means*
  fixed-size, which is why every previously frozen vector is still byte-identical.

- **[`design/decisions-for-1.0.md`](design/decisions-for-1.0.md)** — the whitepaper's
  fifteen open questions, sorted into answered, decided-in-principle, and still-open
  with what would settle each. Includes the decision the whitepaper does not
  contain: 1.0 wants BLAKE3 and Zstandard, neither of which is a browser primitive,
  so either the browser constraint survives as vendored WebAssembly or 1.0 is
  specified for Python and Rust while `ANLA-MVP` stays the profile anyone can verify
  in a tab. The recommendation, with reasons, is the latter.

- **Live test rows for all of it** — the demo page grew a chunking suite: the gear
  table checked against its own derivation, the tiling and size bounds, the
  insertion-survival comparison, and the byte-exactness of both chunking modes.
  76 assertions now, still starting on load.

- **Two fixture content forms**, `lcg` and `concat`, so a fixture can carry 32 KiB
  of pseudo-random bytes as two numbers instead of a wall of base64. The generator
  is pinned in `fixtures.json`; JavaScript must use `Math.imul`, since a plain
  32-bit multiply exceeds 2^53 and would diverge silently — which is the one thing
  a shared fixture cannot tolerate.

### Changed

- The two large new vectors are not inlined into the live test page. Their hashes
  still are, so the byte-exactness suite still checks them by packing the same cases
  in the browser; the page says which ones it did not carry, because a silently
  truncated test set reads as full coverage when it is not.

## 2026-07-26 (later) — a live test page, and one conformance gap closed

### Added

- **[`/demo/`](https://anla.evemisslab.com/demo/) — the conformance suite, running
  in the reader's browser.** 67 assertions across four suites: cross-implementation
  byte equality, frozen vectors, round trips with the preservation invariants, and
  the rejections. Bilingual, starts on load, and fetches nothing — `fixtures.json`
  and the frozen vectors are compiled into the page, because `connect-src` is
  `'none'` and a page that fetched its own fixtures would need that promise
  loosened to test itself.

  The load-bearing suite is the first one: it compares what the browser packs
  against the hashes in `conformance/vectors/SHA256SUMS`, which the *Python* writer
  produced. A green row there means the reader's browser just reproduced, byte for
  byte, an archive a different implementation in a different language wrote.

- **`Archive.rewrite_without_auxiliary()` / `rewriteWithoutAuxiliary()`, and
  `anla strip`.** Emptying the intelligence plane is now an operation, not only an
  assertion: the manifest record and footer are re-emitted, every chunk record
  keeps its bytes and its offset, and the result verifies and extracts identically.
  A planner's decision log records what a model was told and what it chose, which
  is not always something to hand over with the data. Specified in
  [SPEC.md §8.5](SPEC.md#85-auxiliary--the-intelligence-plane).

### Fixed

- **The JavaScript decoder buffered a DEFLATE stream before checking its size.**
  SPEC.md §11 requires the output cap to be enforced *while* decoding; the previous
  code inflated fully and compared lengths afterwards, which passes the same
  assertions while allocating the whole bomb first. It now reads the stream
  incrementally and cancels once the declared size is exceeded. `T-BMB-2` now runs
  against both implementations instead of only Python.

- **`T-AUX-1` was close to vacuous.** It compared a manifest against a copy of
  itself, which passes regardless of what the code under test does. It now compares
  a *rewritten archive's* extraction against the original's, on both sides, and
  `T-AUX-2` pins that stripping twice equals stripping once.

---

## 2026-07-26 — `ANLA-MVP v0.1` frozen, twice implemented

The first release where the format is specified rather than merely implemented.

### Added

- **[`SPEC.md`](SPEC.md)** — normative specification of `ANLA-MVP v0.1`: bootstrap
  header, record frame, footer, canonical JSON profile, codecs, manifest, path
  rules, reproducibility, decoder safety requirements, the conformance table, and a
  full list of divergences from the whitepaper's target format.
- **Python reference implementation** ([`python/anla/`](python/anla/)) — writer,
  reader, verifier, extractor with an extraction report, ZIP export, and an `anla`
  CLI whose every subcommand can emit JSON and whose exit codes follow the
  whitepaper's table.
- **JavaScript reference implementation** ([`web/anla-core.js`](web/anla-core.js))
  — the same format, no dependencies, running unchanged in a browser tab and in
  Node. Includes a software SHA-256 fallback so the page works in contexts where
  `crypto.subtle` is unavailable.
- **Conformance suite** ([`conformance/`](conformance/)) — a language-neutral
  `fixtures.json`, nine frozen byte-exact vectors with `SHA256SUMS`, a Node driver,
  and 165 tests that drive both implementations from one `pytest` run.
- **Reproducible mode** — supplying the archive UUID and creation timestamp makes
  the output byte-exact, which is what lets two implementations be compared rather
  than merely cross-read.
- **Filesystem-collision detection** — two archive paths a target filesystem folds
  together now fail with a fidelity error naming both, in both implementations,
  instead of one file silently overwriting the other.
- **English translations of both papers** ([`papers/`](papers/)); the Traditional
  Chinese originals remain canonical.
- **[`anla.evemisslab.com`](https://anla.evemisslab.com)** — bilingual site with the
  live workbench, the specification, the conformance report and both papers, plus a
  single-file offline build of the workbench.
- `SECURITY.md`, stating both what the decoder defends against and what the format
  does not protect against.

### Changed

- **Object ordering is now UTF-8 byte order, not locale collation.** The original
  v0.1 browser writer sorted the manifest's object array with
  `String.prototype.localeCompare`, so the archive's byte layout depended on the
  machine that produced it. This was the one correction rather than reduction in
  this release; it is what makes reproducibility possible at all.
- **The exclusion glob dialect is specified** — `**` crosses `/`, `*` does not, `?`
  matches one non-`/` character, patterns are anchored at both ends, and a
  directory is its own path. Both implementations share the dialect;
  `fnmatch`-style matching (where `*` crosses `/`) is deliberately not used.
- **`?` in an exclusion glob no longer matches `/`.** The original implementation
  translated it to `.`, which crossed path separators.
- Chunk descriptor offsets are now cross-checked against the parsed record rather
  than trusted, so a manifest that disagrees with its own record stream is refused.

### Verified

- Python and JavaScript writers produce **byte-identical archives** for all nine
  reproducible fixtures. The same digest appears from Python, from Node, and from a
  real browser running the deployed page's self-test.
- The archive shipped with the original v0.1 browser release
  (`conformance/vectors/browser-interop-v0.1.anla`) still verifies and restores
  exactly, in both implementations.

### Known limitations

Unchanged from the original release, and enumerated in
[SPEC.md §13](SPEC.md#13-known-divergences-from-the-whitepaper): no links,
permissions, ACLs, extended attributes, alternate data streams or sparse files; no
FastCDC, Zstandard or BLAKE3; no encryption, signatures or parity; one snapshot per
archive; no partial materialization.

---

## 2026-07-17 — original v0.1 deliverable

- Single-file standalone browser page: a product landing page and a working
  ANLA-MVP writer and reader using Web Crypto and the platform's compression
  streams.
- Verified against a Python MVP in both directions at the time; that Python code is
  superseded by [`python/anla/`](python/anla/).

## 2026-07-16 — the papers

- *From Path Containers to Intelligent Packaging: The Control-Plane Transition
  Thesis for AI-Native Lossless Archive Formats* — concept paper, including the
  conditions that would refute the thesis.
- *ANLA v0.1 Technical Whitepaper* — the target format: object model, binary
  container, manifests and snapshots, chunking and codecs, the agent planning
  interface, security, conformance profiles, milestones and eighteen open
  questions.
