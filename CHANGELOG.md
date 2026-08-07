# Changelog

Notable changes to the ANLA project. The format profile version
(`ANLA-MVP 0.1`) is independent of the release date below: any change to the bytes
an archive contains, or to what a decoder must accept or reject, requires a new
`format_version`.

---

## 2026-08-07 — Zstandard, and what a compressor costs the freeze rule

### Added

- **[`python/anla1/codecs.py`](python/anla1/codecs.py)** — the codec registry, with
  `zstd` implemented. 12 tests. `anla1 pack --codec zstd` is the default;
  `--level N` and `--codec store` are there when you want them.

  Measured on this project's own papers: **163,200 → 92,360 bytes**. On eight
  successive commits of `python/`: **369 KiB against 783 KiB for a single `tar.gz`
  of all eight** — it was 1.01× that `tar.gz` with the codec off, so deduplication
  is what wins and compression compounds it.

- **`tools/check_zstd.py`**, run by CI. `test_codecs_1_0.py` skips itself without
  the library, and a skipped module looks exactly like a passing one — the same hole
  `check_blake3.py` closes. It also re-asserts that a zstd frame declares its
  content size, because that header is what the bomb check reads.

### Fixed

- **Bomb protection is a header read, not an output limit.** `zstandard`'s
  `max_output_size` is *ignored* for a frame that declares its content size — which
  is every frame this writer produces — so the obvious protection does nothing
  against the case that matters. The declared size is read out of the frame header
  and compared with the descriptor's `raw_size` before anything is allocated, and a
  frame that declares no size is refused rather than decoded blind.

- **A chunk that grew is stored.** Random bytes come back from zstd ten bytes
  longer. The writer keeps whichever is smaller, records which it chose, and an
  archive where nothing compressed does not require `anla:codec:zstd:1` of its
  readers.

- **Stored bytes and raw bytes are now hashed separately.** `payload_hash` catches
  damage to what is on disk; `chunk_id` catches a codec that decoded to something
  else entirely. The second was unreachable while `store` was the only codec, and
  it has a test that forges a *valid* zstd frame of the correct length with a
  correct payload hash and a correctly rebuilt manifest — every check passes but
  that one.

### Changed

- **A codec reaches `preservation_root`, and the specification now says so.** §8 had
  no position on this and the first draft of the test asserted the opposite. Chunk
  ids are hashes of the *raw* chunk, so `objects_root` and every chunk id are
  invariant under compression — but descriptors carry `codec_id`, `payload_length`,
  `payload_hash` and offsets, so `chunks_root` moves and `preservation_root` moves
  with it.

  So `preservation_root` is the identity of the snapshot *as stored*, `objects_root`
  is the identity of the tree, and the freeze rule's **byte-identity clause is a
  claim about `store`**. For a compressed archive what two implementations must
  agree on is `objects_root` and the chunk-id set. `packing_plan.codec` records the
  level and the libzstd version that produced the bytes, because a plan that omits
  them cannot explain why two writers disagreed.

- The benchmark's first row used to be the argument for Zstandard. It now answers
  itself — 1.2× a `tar.gz`, down from 3.4× — and **still loses**, for a structural
  reason: `tar.gz` compresses across file boundaries and ANLA compresses each chunk
  alone so that any chunk can be read without the others. The store-only line is
  kept beside the compressed one in every row where it used to lose.

---

## 2026-08-07 — Milestone 2: an archive that records what it does not contain

### Added

- **Metadata namespaces.** Object metadata is now `{"common": {"mtime_ns": …},
  "posix": {"mode": …}}` rather than flat keys. `mode` means something different on
  every platform, and a bare key left a reader nowhere to record that it could not
  use one.

- **The fidelity report**, in the archive and in the preservation plane. Before
  this, the only record that a pack had left something out was the exit code of the
  pack that made it — an operator told once, on the day. `anla1 verify` now exits
  **11** for as long as the report is there, and `list` shows the absent entries
  alongside the present ones.

  Not in `auxiliary`: `auxiliary` is disposable by definition and `strip` empties
  it, so a record of what the archive does *not* hold would be droppable — turning
  a declared-incomplete archive into an apparently complete one, which is worse
  than either. A test asserts `strip` cannot launder it away.

- **Symbolic links.** `anla1 pack` refused any tree containing one, which meant it
  could not pack most real projects. A link's target is stored **verbatim, as
  bytes** — not normalized, not resolved, not validated — because a target is not a
  name in the archive's namespace but an opaque string the target filesystem
  interprets. Rewriting it would store a different link.

  Creating one is a separate decision: a target that is absolute or leaves the
  destination is refused on restore unless `--allow-external-links` says otherwise.
  The archive stays an accurate record either way.

- **A `metadata-cost` benchmark scenario**, because a milestone with no measurement
  is not finished. Per object: **36 bytes** for times, **15** more for POSIX mode,
  **105** for a symbolic link. It moves no compression number at all — that is the
  honest result, and it is published rather than omitted.

### Changed

- **An open question in the specification is closed, and the premise was wrong.**
  §5.3 had guessed `metadata_root` should be split per namespace so that metadata a
  reader cannot apply would be "a subtree it reports on rather than a verification
  failure". Verification is hashing, not interpretation: object metadata is inside
  `object_id`, so a reader that has never heard of `posix` computes the same id over
  the same canonical CBOR and verifies perfectly. It just cannot apply what it
  verified. An unknown namespace could never have caused a verification failure, so
  a root per namespace buys nothing.

  What *can* wrongly refuse such an archive is a capability. So metadata namespaces
  are **`optional_capabilities`, never required**, and `check_capabilities` reports
  them as ignored — which it has always returned and nothing had used.

- **Three states, not two.** "Stored and applied", "stored but not applied", and
  "not stored" are different facts, and only the last means data is gone. `extract`
  reports what this machine could not apply separately from what the archive says it
  never held.

- `--skip-unsupported` now covers only devices, sockets and FIFOs, and what it skips
  is written into the archive rather than only into the exit code.

---

## 2026-08-07 — The `anla1` command, and what a real path turned out to cost

### Added

- **[`python/anla1/fs.py`](python/anla1/fs.py)** — the filesystem boundary: scan a
  directory into a snapshot, restore a snapshot onto a disk. 14 tests. Everything
  that calls `os.walk`, `stat` or `write_bytes` lives here and nowhere else, so the
  portable half of the format stays testable without a disk.

- **[`python/anla1/cli.py`](python/anla1/cli.py)** — the `anla1` command: `pack`,
  `append`, `snapshots`, `list`, `verify`, `extract`, `diff`. 12 tests. Every
  subcommand takes `--json`; exit codes are the whitepaper's, shared with `anla`.

  A separate binary rather than a flag on `anla`, for the same reason 1.0 has its
  own magic number: one command switching profiles on a flag invites an archive
  written under one profile and read under the other.

- **`--uuid` and `--created-ns` on `pack`**, and a CI step that packs the same tree
  twice and compares. Reproducibility is not a debugging convenience here — it is
  the only way the freeze rule can ever be checked, since it is stated as *two
  implementations producing byte-identical archives*.

- **The writer reads one file at a time** (`SourceEntry`), so a tree no longer has
  to fit in memory before packing starts. The archive itself is still assembled in
  memory, which the specification's table now says out loud.

### Fixed

- **1.0 had no rule for what a legal object path is.** Not a decision that went the
  wrong way — an omission: until this release nothing had put a filesystem path into
  a 1.0 archive, so nothing had needed one. `check_object_path` is now called by the
  writer and by `verify_manifest`, from one definition.

- **A path that would have to be rewritten is refused rather than rewritten**
  (`SPEC-1.0-DRAFT.md` §5.2.1). MVP's `safe_path` *returns* a normalized path, and
  normalization is not identity: it turns a backslash into a separator. A POSIX file
  genuinely named `a\b` would have been stored as `a/b` and restored as a file
  inside a directory — a different tree, with every hash verifying. Found by reading
  what the function returns rather than what its name suggests.

### Changed

- **An entry 1.0 cannot represent is refused, not skipped.** A symbolic link, device
  or socket stops the pack. `--skip-unsupported` leaves it out deliberately and
  exits **11** (fidelity degraded) even though it produced an archive, so a script
  cannot mistake a partial archive for a complete one. The in-archive fidelity
  report that would make this a recorded fact rather than a remembered one is
  Milestone 2.

- **A file that changes while it is being packed is an error.** Packing a tree that
  is being written produces an archive of a moment that never existed; each file is
  re-`stat`ed after it is read.

---

## 2026-07-27 — Milestone 3: append-only snapshots, and an invisible footer

### Added

- **[`python/anla1/snapshot.py`](python/anla1/snapshot.py)** — appending a snapshot
  to an existing 1.0 archive, reusing every chunk already in it. 28 tests.
  `append_snapshot`, `list_snapshots`, `extract_snapshot`, `verify_archive`, `diff`.

  A second snapshot of an unchanged tree writes no chunk records at all — a manifest
  and a footer. With `anla-cdc-1`, prepending ten bytes to a 300 KB file shares 65 of
  66 chunks with the previous snapshot.

- **[`design/milestone-3-plan.md`](design/milestone-3-plan.md)**, written before the
  code, and **`SPEC-1.0-DRAFT.md` §6.1–§6.6**, written from what the code settled: a
  manifest describes its whole snapshot and never a delta; a chunk is stored once per
  archive; lineage is checked against the chain; no forward references; one chunk id
  has one descriptor.

### Fixed

- **A writer must resume an append at the end of the newest complete snapshot, not
  at the end of the file** (`SPEC-1.0-DRAFT.md` §4.4 and §6.6). A torn write leaves
  the file at an arbitrary length; appending onto that end puts every following
  record at an offset that is not a multiple of eight. `find_latest_footer` scans
  backwards in alignment-sized steps, so the new footer is **never probed** — the
  archive keeps reading as the older snapshot, with every hash in it correct and
  nothing reporting an error.

  "Records are padded to eight bytes" is not the same statement as "records begin at
  multiples of eight". The first is about what a writer emits; the second is what a
  reader depends on. This is the third rule in this format that looked like a
  consequence of another rule and was not — after `latest_footer_hint` and record
  `sequence`.

### Changed

- **One archive uses one hash algorithm for its chunk ids** (§6.2). Chunk ids are
  hashes, so two algorithms in one archive means two namespaces of chunk id sharing
  one lookup: identical bytes stored twice, deduplication silently doing nothing,
  and every check still passing. Hash agility is per archive, not per snapshot — the
  first boundary the agility added in Milestone 0 has run into.

---

## 2026-07-27 — BLAKE3, and the first real exercise of hash agility

### Added

- **[`python/anla1/blake3.py`](python/anla1/blake3.py)** — BLAKE3-256, the core hash
  of 1.0, as a dependency-free reference implementation, with the Rust `blake3`
  extension used automatically when installed.

  The reference exists because a specification whose hash is only available as a
  compiled wheel has a hole in it: someone checking the document cannot read what it
  says the hash is. Which implementation runs is a performance question and never a
  correctness one — 55 tests assert the two agree byte for byte at every chunk
  boundary (1024, 1025, 2048, 3072, 4096, 8192, 16385), at random lengths,
  incrementally at ten different split sizes, and for extended output.

- **Hash agility, exercised rather than declared.** The end-to-end suite now builds
  and reads the same archive under both `blake3-256` and `sha256`, with the reader
  choosing its hash function from the name it reads out of the record it is about to
  verify. Adding BLAKE3 changed one table and moved no container field; archives
  written with `sha256` before it existed still read.

### Changed

- `blake3-256` is the default for new footers and manifests, and `CORE_HASH` names
  it separately from the algorithm table, so "what this implementation supports" and
  "what the format requires" cannot drift into each other.
- `hash_bytes` has **no default algorithm**. Every caller has just read a name out
  of the archive, and a default would be an invitation to skip that read — which is
  exactly the mistake MVP made by inferring the hash from the profile version.
- A reader now checks that the `MANF` record header and the manifest's own
  `hash_algorithms` name the *same* algorithm. Two places state it; if they were
  allowed to disagree, a reader could verify with one and interpret with the other.

### Noticed while doing it

Two container tests failed on the change, and both were right to. One asserted a
footer's algorithm was `sha256` — it is `blake3-256` now, so the test became
parametric over both, which is the stronger statement anyway. The other used
`blake3-256` as its example of an *unknown* algorithm, and that example had just
become known. It moved to `sha3-512`. That is what shipping a hash looks like from a
test's point of view, and it is worth recording that the suite noticed rather than
the reader.

## 2026-07-28 — Milestone 0 closes: the manifest, its roots, and a whole archive

The 1.0 container can now be written and read end to end, by one implementation.
That is not "1.0 works" — the freeze rule needs two — but it is the point at which
the container stops being a document.

### Added

- **[`python/anla1/merkle.py`](python/anla1/merkle.py)** — the Merkle construction,
  pinned. Three choices in it are load-bearing and each closes a hole a plausible
  alternative leaves open:
  - **domain separation** (`H(0x00 || leaf)`, `H(0x01 || left || right)`), closing
    the classic second-preimage attack where a two-leaf tree and a one-leaf tree
    share a root;
  - **odd nodes promoted, never duplicated** — duplicating makes `[a,b,c]` and
    `[a,b,c,c]` collide, which is CVE-2012-2459, and the suite asserts the collision
    is absent rather than trusting it;
  - **a defined empty root**, because empty is a legitimate state and a
    construction with no answer for it invites each implementation to invent one.

  Inclusion proofs are part of it, not an addition: a root nobody can prove against
  is only a checksum, and partial materialization has to show that what it extracted
  belongs to the snapshot it claims. 65 tests, including every leaf of every tree
  size up to 40.

- **[`python/anla1/manifest.py`](python/anla1/manifest.py)** — objects, chunk map,
  the five roots, and verification that recomputes every root from the manifest's
  own contents. A declared root that disagrees with what it sits beside is refused;
  without that check a root would only prove the manifest had not been edited, not
  that it describes what it claims to. 32 tests.

- **Nine end-to-end tests** that assemble a real archive from the primitives and
  read it back the way a decoder would — tail first, verify, then extract.
  Deliberately not going through a convenience layer: a smoke test that uses the
  same helper the implementation uses can pass while the format does not hold
  together.

- **[`schemas/anla-1.0.cddl`](schemas/anla-1.0.cddl)** — shape only, and it says so
  at the top. It cannot express canonical encoding, the Merkle construction, or that
  a declared root must equal the recomputed one, so a validator that accepts a
  document against it has checked considerably less than a reader does.

### Found while implementing

- **`preservation_root` does not cover the manifest's policy fields** —
  `required_capabilities`, `hash_algorithms`, `created_unix_ns`, the packing plan.
  Editing them leaves the root identical; verified, not assumed. They are still
  protected by the `MANF` record's payload hash, but it means **a signature over
  `preservation_root` alone would not bind them**, and an archive could be
  re-labelled with different capability requirements while its signature still
  verified.

  So a signature MUST bind `snapshot_id`, the hash of the canonical manifest
  encoding. The whitepaper already signs `archive_id ‖ snapshot_id ‖
  preservation_root`; [SPEC-1.0-DRAFT.md §5.3](SPEC-1.0-DRAFT.md) now records *why*
  the `snapshot_id` term is load-bearing, because it is exactly the term a later
  simplification would drop as redundant.

### Fixed

- A duplicated paragraph in the draft, left by the previous commit's line splice.
- An obscure index calculation in `merkle_path` rewritten to be readable. It passed
  its tests either way; in a file that defines part of the format, "the tests pass"
  is not sufficient, because the tests are the only other reader.

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
