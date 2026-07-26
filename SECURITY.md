# Security

## Reporting

Open a security advisory on the repository, or write to the maintainer through the
contact on https://evemisslab.com. Please do not open a public issue for anything
that lets a crafted archive escape a decoder.

Include the archive, or a script that generates it. A reproducer for a parser bug
is usually a few hundred bytes.

---

## What a decoder here has to survive

An `.anla` file is untrusted input. Every field in it is an assertion by whoever
wrote it, and a decoder that believes those assertions is the vulnerability. The
reference implementations therefore treat the following as in scope, with a test
for each ([`conformance/README.md`](conformance/README.md)):

- **Path traversal and absolute paths.** `..`, `/etc/passwd`, `C:\`, UNC paths,
  NUL bytes, empty components. Refused at open time, before any extraction, and
  the extraction target is confined to the destination directory.
- **Filesystem collisions.** Two paths a filesystem folds together (case on
  Windows, NFC against NFD on macOS) fail with a fidelity error naming both. One
  file silently overwriting another is treated as a security-relevant defect, not
  a cosmetic one.
- **Compression bombs.** A chunk that decodes to more than it declares is stopped
  mid-decode, not after the allocation. Declared sizes are checked against a limit
  before anything is allocated.
- **Oversized and lying lengths.** Record header length is capped at 16 MiB; every
  declared extent must lie inside the archive; the JavaScript decoder refuses a
  64-bit field above `Number.MAX_SAFE_INTEGER` rather than rounding it into a
  plausible-looking offset.
- **Unknown capabilities.** An unknown codec, record type or object kind fails.
  This profile has no optional record classes, so skipping would mean guessing
  whether the record mattered.
- **Resource exhaustion.** Configurable caps on total output bytes, object count,
  path depth, name length and per-chunk decoded size. Exceeding a limit is an
  error; it is never a reason to relax the limit.

Out of scope, because the format does not have them: executing anything found in
an archive, fetching external content (this profile has no external chunk
references), creating device nodes or special files, following or creating links,
applying permissions or ACLs.

---

## What the format does not protect against

Stated plainly, because a preservation format that overstates its guarantees is
worse than one that understates them:

- **`ANLA-MVP v0.1` has no signatures and no encryption.** A hash proves an archive
  is internally consistent. It does not prove who wrote it. Anyone who can rewrite
  the payload can rewrite the hashes and the footer to match. If you need
  authenticity, sign the archive out of band; if you need confidentiality, encrypt
  it out of band.
- **A hash detects damage; it cannot repair it.** There is no parity in this
  profile. One corrupted chunk means the files that reference it cannot be
  restored — the others still can, and the scanner will tell you which.
- **Deduplication is archive-local.** No cross-archive or convergent
  deduplication exists here, so the existence-leak that a shared content store
  can create does not arise. If a later profile adds one, that is a privacy
  decision, not only a performance one.
- **The intelligence plane may be wrong.** A decision log or an index is a record
  of what a planner believed. It is not evidence about content, it carries no
  authority, and a decoder must never let it change what gets extracted.

---

## Reporting a specification defect

If a frozen conformance vector and `SPEC.md` disagree, that is a specification
defect and worth reporting as one. Third-party implementations will test against
the vectors, so a document that contradicts them is the thing that is wrong.
