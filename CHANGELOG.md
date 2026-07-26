# Changelog

Notable changes to the ANLA project. The format profile version
(`ANLA-MVP 0.1`) is independent of the release date below: any change to the bytes
an archive contains, or to what a decoder must accept or reject, requires a new
`format_version`.

---

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
