# ANLA-MVP v0.1 — Normative Format Specification

**Format identifier:** `ANLA-MVP`
**Format version:** `0.1`
**Status:** Frozen research profile. Implemented twice and cross-verified.
**File extension:** `.anla`
**Media type (provisional):** `application/vnd.evemiss.anla`

---

## 0. What this document is, and what it is not

`ANLA-MVP v0.1` is a small, complete, frozen profile of the Agent-Native Lossless
Archive format. It is not the full format described in
[the ANLA whitepaper](papers/02-anla-whitepaper.zh-Hant.md). The whitepaper
defines a target: BLAKE3, Zstandard, deterministic CBOR manifests, FastCDC,
append-only snapshots, cross-platform metadata namespaces, signatures, parity.
This profile deliberately defines the smallest subset that can be implemented
end to end, in two independent languages, and verified byte for byte — so that
the whitepaper's central claim stops being an assertion and becomes a test.

That claim is:

> An AI may plan how to pack. A public, deterministic, model-independent decoder
> must recover every byte that was declared into the archive.

This document is normative for `ANLA-MVP v0.1` only. Divergences from the
whitepaper's future v1 layout are listed in [§13](#13-known-divergences-from-the-whitepaper).

The key words MUST, MUST NOT, REQUIRED, SHALL, SHOULD, SHOULD NOT and MAY are to
be interpreted as described in RFC 2119.

---

## 1. Design constraints of this profile

1. A conforming decoder MUST NOT require a language model, an embedding model, a
   remote inference service, or any network access to extract an archive.
2. A conforming decoder MUST reproduce declared file contents bit for bit.
3. Every algorithm used is a published standard with widely available
   implementations: SHA-256, CRC-32 (ISO-HDLC), DEFLATE, zlib, JSON.
4. A conforming writer MUST be able to run entirely inside a web browser tab with
   no backend. This constraint is why the profile uses SHA-256 and DEFLATE rather
   than BLAKE3 and Zstandard: both are available as platform primitives
   (`crypto.subtle`, `CompressionStream`) in current browsers.
5. Given identical inputs and identical values for the two inputs that are
   inherently variable (archive UUID and creation timestamp), two conforming
   writers MUST emit byte-identical archives. See [§10](#10-reproducibility).

---

## 2. Overall layout

```text
┌────────────────────────────────┐  offset 0
│ Bootstrap Header — 64 bytes    │
├────────────────────────────────┤  offset 64
│ Record stream                  │
│   CHNK … CHNK  (payload)       │
│   MANF         (manifest)      │
├────────────────────────────────┤
│ Footer — 96 bytes              │
└────────────────────────────────┘  end of file
```

All integers are little-endian and unsigned. There is no alignment padding
anywhere in the format: records are packed end to end, and the footer begins at
`filesize - 96`.

An archive MUST be at least 160 bytes long (header plus footer).

---

## 3. Bootstrap Header (64 bytes)

| Offset | Size | Field | Value |
|---:|---:|---|---|
| 0 | 8 | `magic` | `41 4E 4C 41 0D 0A 1A 0A` (`ANLA\r\n\x1A\n`) |
| 8 | 2 | `version_major` | `0` |
| 10 | 2 | `version_minor` | `1` |
| 12 | 4 | `reserved_a` | `0` |
| 16 | 16 | `archive_uuid` | 16 raw bytes |
| 32 | 28 | `reserved_b` | all zero |
| 60 | 4 | `header_crc32` | CRC-32 of header bytes `[0, 60)` |

The magic ends in `\r\n\x1A\n` for the same reason PNG does: it makes naive text
mode transfer corruption detectable immediately.

A decoder MUST reject the archive if the magic does not match, if
`version_major != 0` or `version_minor != 1`, or if the header CRC does not
match. A decoder MUST NOT reject non-zero `reserved_a` / `reserved_b` — those are
covered by the CRC and are reserved for a future minor version — but a writer
MUST write zeros.

`archive_uuid` is 16 bytes of entropy. It is a UUIDv4 when the platform provides
a CSPRNG. Its textual form (used in the manifest) is the canonical hyphenated
lowercase hex form `8-4-4-4-12`.

---

## 4. Record frame

Every record in the record stream has this 40-byte frame, followed by a JSON
record header, followed by an opaque payload:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | `magic` = `ANLR` |
| 4 | 4 | `type`, four ASCII bytes |
| 8 | 2 | `record_version` = `1` |
| 10 | 2 | `flags` = `0` |
| 12 | 4 | `header_length` — byte length of the JSON record header |
| 16 | 8 | `payload_length` |
| 24 | 8 | `sequence` — 1-based, strictly increasing across the archive |
| 32 | 4 | `header_crc32` — CRC-32 of the JSON record header bytes |
| 36 | 4 | `reserved` = `0` |

```text
record_total_length = 40 + header_length + payload_length
```

The JSON record header MUST be canonical JSON ([§6](#6-canonical-json)). The
payload is bytes; its meaning is defined per record type.

A decoder MUST reject a record whose magic is wrong, whose `header_crc32` does
not match, whose `header_length` exceeds 16 MiB, or whose declared extent
(`offset + record_total_length`) exceeds the archive size. These checks MUST be
performed before any allocation sized from the declared lengths.

Record types in this profile:

| Type | Payload | Required to extract |
|---|---|---|
| `CHNK` | one encoded chunk | yes |
| `MANF` | the snapshot manifest | yes |

`flags` is reserved in this profile and MUST be `0`. Unlike the full format,
`ANLA-MVP v0.1` has no optional record classes: a decoder that encounters an
unknown record type MUST fail rather than skip, because it cannot know whether
the record was required. (The full format solves this with a
`AUXILIARY_DISPOSABLE` flag bit; this profile does not need it, and guessing is
worse than refusing.)

### 4.1 `CHNK`

Record header:

```json
{"chunk_id":"<64 hex>","codec":"store|deflate","payload_sha256":"<64 hex>","raw_size":<int>}
```

Payload: the chunk encoded with `codec` ([§7](#7-codecs)).

### 4.2 `MANF`

Record header:

```json
{"encoding":"canonical-json","payload_sha256":"<64 hex>","preservation_required":true}
```

Payload: the manifest, canonical JSON, UTF-8 ([§8](#8-manifest)).

An archive contains exactly one `MANF` record, and it is the last record in the
stream.

---

## 5. Footer (96 bytes)

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | `magic` = `41 4E 4C 41 46 54 52 00` (`ANLAFTR\0`) |
| 8 | 2 | `version_major` = `0` |
| 10 | 2 | `version_minor` = `1` |
| 12 | 4 | `reserved_a` = `0` |
| 16 | 8 | `manifest_record_offset` |
| 24 | 8 | `manifest_record_length` — full record length, including the frame |
| 32 | 16 | `archive_uuid` — MUST equal the header's |
| 48 | 32 | `manifest_payload_sha256` |
| 80 | 12 | `reserved_b` = all zero |
| 92 | 4 | `footer_crc32` — CRC-32 of footer bytes `[0, 92)` |

The footer is authoritative for locating the manifest. A decoder MUST verify, in
this order: footer magic, footer CRC, `archive_uuid` equality with the header,
that `manifest_record_offset` points at a well-formed `MANF` record whose total
length equals `manifest_record_length`, and that the SHA-256 of the manifest
payload equals `manifest_payload_sha256`. Only then may the manifest be parsed.

---

## 6. Canonical JSON

Record headers and the manifest are encoded with a canonical JSON profile so
that the same logical structure always produces the same bytes — which is what
makes the manifest hash, and therefore reproducibility, meaningful.

Rules:

1. UTF-8, no byte-order mark.
2. No insignificant whitespace anywhere.
3. Object keys sorted ascending by Unicode code point. All keys in this profile
   are ASCII, so a byte-wise sort is equivalent.
4. No duplicate keys.
5. Strings use the shortest JSON escaping: `"`, `\`, and the C0 controls are
   escaped (`\b \t \n \f \r` where defined, `\u00XX` otherwise); every other
   character, including all non-ASCII, is emitted literally as UTF-8. Notably,
   `/` is not escaped and non-ASCII is not `\u`-escaped.
6. Numbers are integers only, in the closed range
   `[-(2^53 - 1), 2^53 - 1]`, written with no leading `+`, no leading zeros, no
   decimal point and no exponent. **Floating point numbers MUST NOT appear
   anywhere in a conforming archive.** Values that can exceed 2^53 — nanosecond
   timestamps — are carried as decimal strings.
7. `true`, `false`, `null` are lowercase literals. `null` is not used by this
   profile.
8. Arrays preserve their defined order; array order is normative wherever this
   spec defines one.

A decoder MUST NOT require that a manifest it reads is canonical — it verifies
integrity through the payload hash, not through re-encoding. A writer MUST emit
canonical JSON.

---

## 7. Codecs

| `codec` | Encoding |
|---|---|
| `store` | identity; payload is the raw chunk |
| `deflate` | zlib format (RFC 1950): a 2-byte zlib header, DEFLATE data (RFC 1951), and an Adler-32 trailer |

`deflate` is the zlib wrapper, **not** raw DEFLATE. This is exactly what the web
platform's `CompressionStream("deflate")` produces and `DecompressionStream("deflate")`
consumes, and what `zlib.compress` / `zlib.decompress` produce and consume in
Python. Raw DEFLATE (`deflate-raw` in the web platform) is not part of this
profile.

For `store`, a decoder MUST verify `payload_length == raw_size`. For any codec, a
decoder MUST verify that the decoded length equals `raw_size` before hashing, and
MUST enforce its own output-size limit while decoding so that a hostile chunk
cannot exhaust memory ([§11](#11-decoder-safety)).

A decoder MUST fail on any other codec string. Compression level is a writer-side
choice with no effect on decoding, and is not recorded per chunk; the requested
level is recorded once in the packing plan for auditing.

---

## 8. Manifest

The manifest is a JSON object with exactly these members:

```json
{
  "format": "ANLA-MVP",
  "format_version": "0.1",
  "archive_uuid": "3bd605e8-451b-43d6-a238-2e6c67f3649b",
  "created_unix_ns": "1752732000000000000",
  "hash_algorithm": "sha256",
  "manifest_encoding": "canonical-json",
  "snapshot_sequence": 1,
  "source_name": "workspace",
  "plan": { "…": "…" },
  "preservation": {
    "lossless": true,
    "decoder_requires_ai": false,
    "object_coverage": "all-selected-objects"
  },
  "objects": [ "…" ],
  "chunks": { "…": "…" },
  "statistics": { "…": "…" },
  "auxiliary": { "decision_log": [], "disposable": true }
}
```

A decoder MUST reject the archive if `format != "ANLA-MVP"`, if
`format_version != "0.1"`, or if `archive_uuid` does not match the textual form
of the header UUID.

`created_unix_ns` is a decimal string: nanoseconds since the Unix epoch, UTC.
`snapshot_sequence` is `1`; this profile has no append-only snapshots.

### 8.1 `objects`

An array. Order is normative: ascending by the UTF-8 bytes of `path`, ties broken
by ascending `type` bytes. Paths are unique across the array.

The record stream is ordered too, and for the same reason — reproducibility.
Files are processed in ascending UTF-8 `path` order, and each file's chunks in
offset order; a `CHNK` record is emitted the first time its content is
encountered and never again. `sequence` numbers therefore run 1..n over the
`CHNK` records in that order, with the `MANF` record last. The
`auxiliary.decision_log` array is in the same order as the `CHNK` records.

A directory object:

```json
{"type":"directory","path":"docs","metadata":{}}
```

A file object:

```json
{"type":"file","path":"docs/readme.txt","size":21,"sha256":"<64 hex>",
 "chunks":[{"id":"<64 hex>","length":4}],"metadata":{"mtime_ns":"1700000000000000000"}}
```

- `path` is a relative POSIX path; see [§9](#9-paths).
- `size` is the file length in bytes.
- `sha256` is the hash of the whole file content, lowercase hex.
- `chunks` is the ordered chunk reference list. Concatenating the referenced raw
  chunks in order MUST reproduce the file exactly, so
  `sum(length) == size` is REQUIRED. An empty file has an empty list.
- `metadata` carries `mtime_ns` (decimal string) when the writer preserved it,
  and is otherwise `{}`. This profile defines no other metadata key. A decoder
  MUST ignore metadata keys it does not know rather than fail: metadata is
  descriptive, and no content depends on it.

Object types other than `directory` and `file` MUST be rejected. Symbolic links,
hard links, sparse ranges, ACLs, extended attributes and alternate data streams
are outside this profile — an archive cannot claim to preserve them, which is
the point of stating so here.

### 8.2 `chunks`

An object mapping `chunk_id` to a descriptor:

```json
"9f64a747…806a": {
  "record_offset": 64, "record_length": 236,
  "payload_offset": 187, "payload_length": 4,
  "raw_size": 4, "codec": "store", "payload_sha256": "<64 hex>"
}
```

`chunk_id` is the SHA-256 of the **raw** (decoded) chunk bytes, lowercase hex.
Content identity is therefore independent of the codec used to store it, which is
what makes deduplication across differently-compressed occurrences possible.

`payload_sha256` is the SHA-256 of the stored (encoded) payload, which lets a
verifier detect medium corruption without paying for decompression.

The offsets are redundant with the record stream on purpose: they give random
access without a scan, and they give the verifier a second, independent
statement to cross-check. A decoder MUST verify that the record at
`record_offset` is a `CHNK` record whose total length equals `record_length` and
whose `chunk_id`, `codec` and `raw_size` match the descriptor. A decoder SHOULD
verify `payload_offset` and `payload_length` against the parsed record rather
than trusting the descriptor.

Keys are serialized in ascending hex order, as canonical JSON requires.

### 8.3 `plan`

The packing plan: the machine-readable statement of what the writer was asked to
do. It is part of the preservation plane because it is audit evidence, not
because extraction needs it.

```json
{"plan_version":"0.1","chunk_size":1048576,"compression":"auto|deflate|store",
 "deflate_level":6,"exclude_globs":[],"preserve_mode":false,"preserve_mtime":true,
 "verification":"full"}
```

`chunking` in this profile is fixed-size only: file bytes are cut at
`chunk_size` boundaries, so chunk `i` covers `[i·chunk_size, min(size, (i+1)·chunk_size))`.
`chunk_size` MUST be ≥ 1. Content-defined chunking is not part of this profile.

`compression: "auto"` means: try `deflate`, keep it only if
`len(compressed) + 8 < len(raw)`, otherwise fall back to `store`. The `+ 8` is
the margin at which compressing stops paying for its own decode cost on small
chunks. `"deflate"` forces the compressed representation even when it is larger;
`"store"` never compresses. The chosen codec is recorded per chunk, so a decoder
never needs to know which mode was used.

`exclude_globs` is the list of exclusion patterns applied *before* the object set
was formed. Its presence is what keeps "we did not pack this" distinguishable
from "we packed this losslessly": excluded paths were never members of the
declared set, and the archive does not claim to contain them.

The pattern dialect is small and fully specified, because two writers that
disagree about which files a pattern covers disagree about what the archive
contains:

| Token | Matches |
|---|---|
| `**` | any sequence of characters, including `/` |
| `*` | any sequence of characters except `/` |
| `?` | exactly one character, except `/` |
| anything else | itself, literally |

A pattern is matched against the whole path, anchored at both ends — there is no
partial match and no implicit prefix. Matching is case-sensitive and applies no
Unicode normalization.

Exclusion is per path, and **a directory is its own path**. `.git/**` removes
everything inside `.git` and leaves `.git` itself, as an empty directory object;
removing the subtree takes both `.git` and `.git/**`. This is stated because it is
otherwise discovered by accident.

### 8.4 `statistics`

Derived counters: `objects`, `files`, `directories`, `unique_chunks`,
`chunk_references`, `logical_bytes`, `stored_payload_bytes`. A verifier MAY
recompute and compare them; they are convenience, not authority.

### 8.5 `auxiliary` — the intelligence plane

```json
{"disposable": true,
 "decision_log": [
   {"chunk_id":"<64 hex>","raw_size":4,"stored_size":4,"codec":"store",
    "reason":"compression-not-beneficial"}
 ]}
```

`reason` is one of `smaller-representation`, `compression-not-beneficial`,
`forced-by-plan`.

This member is the entire intelligence plane of the profile, and it is
**disposable by definition**: replacing `auxiliary` with
`{"decision_log":[],"disposable":true}` changes the manifest bytes, the manifest
hash and the footer, but MUST NOT change what any decoder extracts. Conformance
test `T-AUX-1` ([§12](#12-conformance)) asserts exactly this.

---

## 9. Paths

Paths in the manifest are relative POSIX paths: `/`-separated, no drive letter,
no leading `/`, no `.` or `..` component, no empty component, no NUL. Writers
convert `\` to `/` at pack time.

A writer MUST reject an unsafe path rather than sanitize it silently. A decoder
MUST validate every path again at open time — before any extraction — and MUST
reject the archive if a path is unsafe or duplicated. Validating at write time is
a convenience; validating at read time is the security boundary.

Path bytes are preserved as the writer saw them. This profile does not implement
the whitepaper's `native` / `legacy` name model: it stores one UTF-8 path per
object and makes no claim about recovering a non-UTF-8 original name. An
implementation that needs that guarantee MUST NOT use this profile.

Unicode normalization is not applied. Two paths that differ only by
normalization form (`NFC` vs `NFD`) or only by case are distinct paths here.

Such an archive is perfectly valid, and there are filesystems that cannot restore
it: Windows folds case, and macOS folds `NFC` against `NFD`. A decoder that
extracts to a real filesystem MUST detect that two objects landed on the same
file and MUST fail with a fidelity error naming both archive paths. It MUST NOT
let one overwrite the other, and MUST NOT report success.

Predicting the collision from the path strings is not sufficient — the folding
rules belong to the target filesystem, not to the decoder. The reference
implementations therefore check empirically: each restored file's identity
(`st_dev`, `st_ino`) is recorded, and a target that resolves to an already-written
identity is a collision. This catches case folding, normalization folding, and
whatever else a filesystem does, without the decoder having to model any of it.

---

## 10. Reproducibility

Two inputs to packing are inherently variable: `archive_uuid` and
`created_unix_ns`. Everything else is a function of the input files, their paths,
their preserved mtimes, and the plan.

A conforming writer MUST therefore support **reproducible mode**: the caller
supplies both variable inputs, and the writer emits a byte-exact archive.

```text
pack(files, plan, uuid=U, created_ns=T) → identical bytes, on any conforming writer
```

This is the profile's strongest self-check, and the reason the canonical JSON
rules and the object ordering rule are normative rather than advisory. The
repository's cross-implementation test asserts that the Python writer and the
JavaScript writer, given the same tree and the same `(U, T)`, produce archives
that are equal byte for byte — not merely mutually readable.

Note the one thing reproducibility does *not* cover: `compression: "deflate"` or
`"auto"` embeds the output of a DEFLATE encoder, and different encoders (zlib at
level 6 versus a browser's `CompressionStream`) legitimately produce different
valid compressed bytes for the same input. Byte-exact cross-implementation
equality is therefore asserted for `compression: "store"`, and for `"auto"` /
`"deflate"` archives the assertion is that each implementation reproduces *its
own* output exactly and that both decode the other's output to identical raw
bytes. A future profile that wants byte-exact compressed output across
implementations would have to pin the encoder, not just the format.

---

## 11. Decoder safety

A conforming decoder MUST enforce, before allocating from any declared length:

1. `header_length ≤ 16 MiB`.
2. Every record extent lies inside the archive.
3. Every declared offset and length is checked with arithmetic that cannot
   silently overflow (Python integers are unbounded; JavaScript decoders MUST
   reject any 64-bit field above `Number.MAX_SAFE_INTEGER` rather than round it).
4. A configurable cap on total decoded output and on per-chunk decoded size,
   which MUST be checked while decoding, not after.
5. Path validation per [§9](#9-paths) for every object.
6. No duplicate paths.
7. No unknown record type, no unknown codec, no unknown object type.

A decoder MUST NOT execute anything found in an archive, MUST NOT fetch any
external content — this profile has no external chunk references — and MUST NOT
create special files, apply permissions, or follow links, because this profile
stores none of those.

Failure MUST be explicit. A decoder MUST NOT emit a partial tree while reporting
success. The reference implementations verify the whole archive before writing
any output file.

---

## 12. Conformance

An implementation claiming `ANLA-MVP v0.1` conformance MUST pass the conformance
suite in [`conformance/`](conformance/). The frozen vectors are checked into
`conformance/vectors/`; the suite regenerates the derived ones and compares byte
for byte.

| ID | Assertion |
|---|---|
| `T-HDR-1` | Bad magic, bad version, bad header CRC each rejected |
| `T-FTR-1` | Bad footer magic, bad footer CRC, UUID mismatch each rejected |
| `T-FTR-2` | Footer pointing at a non-`MANF` record rejected |
| `T-MAN-1` | Manifest hash mismatch rejected |
| `T-MAN-2` | Manifest identity mismatch (`format`, `version`, `uuid`) rejected |
| `T-REC-1` | Record header CRC mismatch rejected |
| `T-REC-2` | Unknown record type rejected |
| `T-CHK-1` | Chunk payload hash mismatch rejected |
| `T-CHK-2` | Raw chunk hash mismatch rejected (chunk id is a content claim) |
| `T-CHK-3` | Chunk descriptor / record disagreement rejected |
| `T-CHK-4` | Unknown codec rejected |
| `T-COV-1` | `sum(chunk lengths) != size` rejected |
| `T-PTH-1` | `..`, absolute, drive-letter, UNC, NUL, empty-component paths rejected |
| `T-PTH-2` | Duplicate path rejected |
| `T-EMP-1` | Empty file (no chunk references) round-trips |
| `T-EMP-2` | Empty archive (no objects) round-trips |
| `T-DUP-1` | Identical content in two files stores one chunk, both restore |
| `T-BIG-1` | File larger than `chunk_size` splits and restores |
| `T-UNI-1` | Non-ASCII paths (CJK, emoji, NFC/NFD pair) round-trip byte-exact |
| `T-EXT-1` | Two paths the target filesystem folds together fail as a fidelity error, naming both |
| `T-AUX-1` | Stripping `auxiliary.decision_log` changes no extracted byte |
| `T-REP-1` | Same input + same `(uuid, created_ns)` → byte-identical archive |
| `T-GLB-1` | `*` does not cross `/`, `**` does, and a directory survives its excluded contents |
| `T-XIM-1` | Python writer → JavaScript reader, full verification |
| `T-XIM-2` | JavaScript writer → Python reader, full verification |
| `T-XIM-3` | Python and JavaScript writers agree byte for byte (`store` mode) |
| `T-XIM-4` | Both implementations reject the same corruption with the same error code |
| `T-ORG-1` | The v0.1 archive shipped in the original release still verifies |
| `T-BMB-1` | A chunk declaring an absurd `raw_size` is refused, not allocated |
| `T-BMB-2` | A DEFLATE payload expanding past its declared size is stopped mid-decode |
| `T-FRZ-1` | Every frozen vector still matches what the current writer produces |

`T-ORG-1` exists because a format profile that cannot read the artifact it
shipped with has not frozen anything.

---

## 13. Known divergences from the whitepaper

These are deliberate, and each is a place where the whitepaper's target and this
minimal profile differ. They are listed so that no reader has to discover them by
experiment.

| Whitepaper (target v1) | This profile (MVP v0.1) | Why |
|---|---|---|
| BLAKE3-256 chunk identity | SHA-256 | Available as a browser primitive; BLAKE3 is not |
| Zstandard core codec | DEFLATE (zlib) | Same reason |
| Deterministic CBOR manifest | Canonical JSON | Inspectable with no tooling; the ordering discipline is the part that matters, and it is kept |
| CRC32C in header/record | CRC-32 (ISO-HDLC) | Available in every standard library; CRC32C is not |
| Header offset 12 = `header_size` | `reserved_a`, zero | The header is fixed at 64 bytes in this profile, so the field carries no information |
| Record types `INDX AUXI META SIGN PARI FOOT` | `CHNK`, `MANF` only | Nothing else is implemented, so nothing else is claimed |
| `REQUIRED_FOR_EXTRACTION` / `AUXILIARY_DISPOSABLE` flag bits | `flags` = 0 | No optional record classes exist to skip |
| Footer chain (`previous_footer_offset`), append-only snapshots | single footer, `snapshot_sequence` = 1 | Incremental snapshots are Milestone 3 |
| FastCDC | fixed-size chunking only | Milestone 3 |
| POSIX / Windows / macOS metadata namespaces | `mtime_ns` only | Milestone 2 |
| Encryption, COSE signatures, parity records | none | Later profiles |
| Object identity by `object_id`, parent/child name components | path string per object | Rename tracking needs snapshots, which this profile lacks |

The one divergence that is a *correction* rather than a reduction: the original
v0.1 browser writer sorted the object array with JavaScript's
`String.prototype.localeCompare`, which is locale-dependent and therefore not
reproducible across environments. [§8.1](#81-objects) mandates UTF-8 byte order
instead, and both reference implementations now do that. Archives written by the
original browser build remain readable — object order is not load-bearing for a
reader — but they are not reproducible, and `T-ORG-1` pins that archive as a
read compatibility vector rather than a reproducibility one.

---

## 14. Reference implementations

| | |
|---|---|
| Python | [`python/anla/`](python/anla/) — writer, reader, verifier, extractor, CLI |
| JavaScript | [`web/anla-core.js`](web/anla-core.js) — the same, running in a browser tab or in Node |

Neither implementation imports the other's output format description: both are
written against this document, and the cross-implementation tests
(`T-XIM-1..3`) are what hold them together.

---

## 15. Versioning

`ANLA-MVP v0.1` is frozen. Any change to the bytes an archive contains, or to
what a decoder must accept or reject, requires a new `format_version`. The next
profile will be `ANLA-MVP 0.2` (adding snapshots and FastCDC) or `ANLA 1.0`
(the whitepaper's format, with a different magic and its own spec). Readers
identify the profile from `version_minor` in the header plus `format_version` in
the manifest, and MUST refuse anything they do not implement.

---

*Part of the ANLA project. © 2026 EVEMISS Technology Co., Ltd. Licensed
Apache-2.0. Author: Neo.K.*
