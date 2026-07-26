---
title: "AI-Native Lossless Archive Format — Technical Whitepaper"
subtitle: "Agent-Native Lossless Archive Format (ANLA) v0.1"
author: "Neo.K"
organization: "EVEMISSLAB / EVEMISS Technology Co., Ltd."
date: "2026-07-16"
version: "v0.1"
status: "Technical whitepaper / pre-specification draft"
language: "en"
translation_of: "02-anla-whitepaper.zh-Hant.md"
scope: "This version defines only lossless preservation, deterministic decoding and the agent control surface. It admits nothing generative and no semantic approximation."
---

# AI-Native Lossless Archive Format — Technical Whitepaper

## Agent-Native Lossless Archive Format (ANLA) v0.1

**Author:** Neo.K
**Date:** 16 July 2026
**Status:** Pre-specification draft
**Provisional extension:** `.anla`
**Provisional media type:** `application/vnd.evemiss.anla`
**Translation:** English rendition of the Traditional Chinese original, which remains the canonical text.

> **Reading note.** This whitepaper describes the *target* format. The subset that
> is actually implemented, frozen and cross-verified today is `ANLA-MVP v0.1`, whose
> normative definition is [SPEC.md](../SPEC.md). Section 13 of that document lists
> every place the two differ, and why.

---

# Executive summary

ANLA is a general-purpose lossless archive format for AI agents, human users and
ordinary programs alike. It is not a new single compression algorithm. It is a
packaging protocol built on multiple codecs, content addressing, a verifiable
manifest, a cross-platform object model, incremental snapshots and a structured
control surface.

The first principle of ANLA v0.1 is:

> **An AI may choose how to compress. It may not substitute, summarize, infer or
> regenerate any original data that has been declared into the archive — in any
> form.**

The format must satisfy:

$$
\operatorname{Extract}(\operatorname{Pack}(F,P))=F
$$

where $F$ is the set of objects approved into the archive, $P$ is a lossless
packing plan produced by an AI or a conventional planner, `Pack` is a deterministic
writing process bound by the specification, and `Extract` is a standard decoding
process that requires no AI.

ANLA divides the system into two planes:

1. **Preservation plane:** original payload, chunks, object topology, paths,
   metadata, hashes, snapshots, signatures and recovery data.
2. **Intelligence plane:** AI decision records, content indexes, language
   annotations, search data, access hints and agent operation history.

The intelligence plane is optional and rebuildable. With every intelligence record
deleted, the preservation plane must still decode completely.

This whitepaper defines: the core invariants; the file and metadata object model;
the binary container layout; manifests and snapshots; chunks and codecs; path and
legacy-encoding preservation; random access and streaming; incremental versions;
the agent planning interface; CLI, JSON and MCP surfaces; security, encryption,
signatures and recovery; conformance profiles; and a Rust reference implementation
route.

---

# Part I — Goals and boundaries

## Chapter 1. Design goals

### 1.1 Core goals

ANLA v0.1 must:

1. provide bit-level lossless recovery of the file contents it packages;
2. preserve sufficient path and platform metadata;
3. support independent decoders on x86, x64 and ARM across operating systems;
4. allow different files or chunks to use different lossless codecs;
5. support fixed-size and content-defined chunking;
6. support deduplication across files and across snapshots;
7. support streaming writes;
8. support random access once packing is complete;
9. support append-only incremental updates;
10. allow an agent to plan and operate in a structured way;
11. ensure extraction depends on no agent and no model;
12. provide integrity, signatures and safety limits;
13. allow export to ZIP, TAR or a plain directory;
14. allow future extension, with unknown required capabilities failing safely.

---

### 1.2 Explicit non-goals

ANLA v0.1 does not include: generative reconstruction of images, text, audio or
video; prompts substituting for original files; summaries substituting for
original content; semantically lossy compression; automatic deletion of
"re-downloadable" dependencies; automatic omission of build products; model-weight
compression research; invention of a new low-level entropy coder; arbitrary
execution of code inside an archive; anti-cheat, DRM or access-control
circumvention; a mandatory vector database or knowledge graph; any dependency on
unpublished or private theory.

---

### 1.3 An operational definition of AI-native

ANLA's AI-native character consists of these capabilities:

**Self-describing.** Codecs, versions, chunk maps, path representations and
required capabilities are all declared explicitly by the format.

**Plannable.** An agent can emit a complete packing plan rather than only passing
"maximum compression".

**Auditable.** Each planning round can retain its input evidence, the reasons for
each choice, tool versions and benchmark results.

**Replayable.** The same plan can be executed again by a deterministic writer.

**Queryable.** An agent can enumerate objects, chunks, snapshots, differences and
metadata.

**Partially materializable.** Only the objects a task needs are extracted, without
scanning the entire payload.

**Model-independent.** Replacing or removing the model does not affect extraction
of existing archives.

---

## Chapter 2. Core invariants

### 2.1 Content integrity

For every ordinary file $f_i$:

$$
H(B_i)=H(\widehat{B_i})
$$

where $B_i$ is the original content bytes, $\widehat{B_i}$ the extracted bytes, and
$H$ the hash function the manifest names.

---

### 2.2 Complete chunk coverage

Let a file $f$ have content $B$ and chunk-slice sequence:

$$
S_f=(s_1,s_2,\ldots,s_k)
$$

Then:

$$
B=s_1\Vert s_2\Vert\cdots\Vert s_k
$$

and: slices must not leave gaps; slices must not overlap unless the specification
explicitly declares repeated references to the same chunk; the sum of slice
uncompressed lengths must equal the file size; every referenced chunk must exist or
be resolvable through an external descriptor in the same snapshot.

---

### 2.3 Deterministic decoding

For the same archive bytes and the same capability set, a decoder must produce the
same output:

$$
D_1(A)=D_2(A)
$$

provided $D_1$ and $D_2$ conform to the same profile.

---

### 2.4 The intelligence plane is disposable

With an archive:

$$
A=(P,I)
$$

it must hold that:

$$
D(P,I)=D(P,\varnothing)
$$

---

### 2.5 A model may not be the decoder

The dependency set of a standard decoder must not include: a particular LLM; a
remote inference API; an embedding model; a generative model; natural-language
judgement; or a vendor's proprietary service.

---

### 2.6 Explicit failure

On an unknown required capability, a decoder must refuse rather than guess:

```text
required capability unknown → fail
optional auxiliary record unknown → skip
```

---

# Part II — The logical object model

## Chapter 3. Archive structure

The ANLA logical model is:

$$
\mathcal{A}
=
(S,O,C,M,X,R,Q)
$$

with $S$ the set of snapshots, $O$ filesystem objects, $C$ chunks, $M$ manifests
and descriptors, $X$ optional indexes and intelligence extensions, $R$ recovery and
signature data, and $Q$ policy and capability declarations.

---

## Chapter 4. Filesystem objects

### 4.1 Object kinds

v0.1 defines:

```text
regular-file
directory
symbolic-link
hard-link-reference
sparse-file
windows-reparse-point
platform-special
```

`platform-special` preserves objects a decoder should not create automatically —
device nodes, named pipes, sockets, unknown reparse points. By default a decoder
preserves only their metadata and does not instantiate them, unless the user
explicitly authorizes it and the platform supports it.

---

### 4.2 Object identity

Every object has a stable `object_id`. A path is not the unique identifier.

```json
{
  "object_id": "b3:...",
  "kind": "regular-file",
  "parent_id": "b3:...",
  "name": { "...": "..." }
}
```

This avoids: the same path pointing at different objects in different snapshots; a
rename being misread as a delete plus an add; hard-link relationships that cannot
be expressed; and path-normalization collisions.

---

## Chapter 5. The path model

### 5.1 A path is not a single UTF-8 string

To avoid reproducing ZIP's historical problem, ANLA splits a path into
parent/child relationships and name components.

Each name component may carry:

```json
{
  "portable_utf8": "會話01.txt",
  "unicode_normalization": "unmodified",
  "native": {
    "platform": "windows-nt",
    "representation": "utf16le-code-units",
    "data_base64": "..."
  },
  "legacy": {
    "encoding": "cp932",
    "raw_bytes_base64": "...",
    "confidence": "confirmed"
  }
}
```

---

### 5.2 `portable_utf8`

`portable_utf8` is for display, cross-platform export, querying and ordinary CLI
use. It must be valid UTF-8, and it is not the sole evidence of the original name.

---

### 5.3 Native names

`native` preserves the source platform's actual name representation: UTF-16LE code
units on Windows NT; the raw byte sequence on POSIX; UTF-8 or the filesystem's
native representation, plus necessary extensions, on macOS.

Restoring on the same platform, a decoder prefers the native representation; across
platforms it follows the mapping policy.

---

### 5.4 Legacy archive import

Importing from an old ZIP or another archive, ANLA can preserve the original
filename bytes, the assumed code page, the decoded Unicode, how the determination
was made, and whether a human confirmed it. These become preservation metadata, so
that nothing has to be guessed again later.

---

### 5.5 Path safety

An extractor must reject or remap: `..` traversal; absolute paths; Windows drive
prefixes; UNC paths; NUL; names reserved on the target platform; collisions after
normalization; case-insensitive collisions; symlink escapes.

Every remapping must appear in an extraction report.

---

## Chapter 6. Metadata namespaces

### 6.1 Common metadata

```json
{
  "size": 12345,
  "modified_time": "...",
  "created_time": "...",
  "accessed_time": "...",
  "read_only": false,
  "executable_hint": true
}
```

Times use a UTC value, the original precision, the original time zone or
"unknown", and an explicit calendar and epoch.

---

### 6.2 POSIX namespace

May preserve: mode; UID/GID; user and group name; extended attributes; ACLs;
device major/minor; link count.

---

### 6.3 Windows namespace

May preserve: file attributes; security descriptor; alternate data streams; reparse
data; creation time; object ID; sparse ranges; compression attribute.

---

### 6.4 macOS namespace

May preserve: extended attributes; ACLs; resource fork; Finder info; quarantine
attribute; clone and sparse hints.

---

### 6.5 Extraction capability report

A decoder must report:

```json
{
  "object_id": "b3:...",
  "content": "restored",
  "path": "mapped",
  "metadata": {
    "posix.mode": "restored",
    "windows.acl": "preserved-in-sidecar",
    "macos.resource_fork": "unsupported"
  }
}
```

Metadata must never be lost silently because the target platform cannot apply it.

---

# Part III — The binary container

## Chapter 7. Overall layout

ANLA v0.1 uses:

```text
┌──────────────────────┐
│ Bootstrap Header      │
├──────────────────────┤
│ Record Stream         │
│  MANF / CHNK / INDX   │
│  META / SIGN / PARI   │
├──────────────────────┤
│ Latest Footer         │
└──────────────────────┘
```

This supports streaming reads from the front, fast access to the latest snapshot
from the tail, appending new snapshots, and scanning the record stream when the
footer is damaged.

---

## Chapter 8. Bootstrap header

### 8.1 Magic

Provisionally 8 bytes:

```text
41 4E 4C 41 0D 0A 1A 0A
A  N  L  A \r \n SUB \n
```

---

### 8.2 Header fields

Fixed 64 bytes:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | Magic |
| 8 | 2 | Major version, little-endian |
| 10 | 2 | Minor version |
| 12 | 4 | Header size |
| 16 | 8 | Global flags |
| 24 | 8 | First record offset |
| 32 | 8 | Latest footer offset hint |
| 40 | 16 | Archive UUID |
| 56 | 4 | Header CRC32C |
| 60 | 4 | Reserved |

The latest-footer offset is a hint only. The authoritative footer must still be
confirmed by scanning from the tail and verifying its hash.

---

## Chapter 9. Record frame

Each record:

| Field | Size |
|---|---:|
| Record magic | 4 |
| Record type | 4 |
| Record version | 2 |
| Record flags | 2 |
| Header length | 4 |
| Payload length | 8 |
| Record sequence | 8 |
| Header CRC32C | 4 |
| Reserved | 4 |
| Extended header | variable |
| Payload | variable |
| Padding | 0–7 |

Record magic, provisionally:

```text
ANLR
```

---

### 9.1 Record types

| Type | Meaning |
|---|---|
| `CHNK` | a compressed or uncompressed chunk |
| `MANF` | a snapshot manifest |
| `INDX` | a random-access index |
| `AUXI` | optional intelligence data |
| `META` | large or platform metadata |
| `SIGN` | signatures |
| `PARI` | recovery / parity |
| `FOOT` | snapshot footer |

---

### 9.2 The required flag

Record flags include:

```text
bit 0: REQUIRED_FOR_EXTRACTION
bit 1: REQUIRED_FOR_VERIFICATION
bit 2: ENCRYPTED
bit 3: COMPRESSED_METADATA
bit 4: AUXILIARY_DISPOSABLE
```

For an unknown record: if `REQUIRED_FOR_EXTRACTION=1`, a decoder must fail; if
`AUXILIARY_DISPOSABLE=1`, a decoder may skip it.

---

## Chapter 10. Footer

A footer always contains: footer version; snapshot sequence; manifest offset and
length; primary index offset and length; previous footer offset; preservation root
digest; auxiliary root digest; footer digest; footer CRC32C.

Each update appends a footer. Old footers are never overwritten.

---

# Part IV — Manifests and snapshots

## Chapter 11. Manifest encoding

### 11.1 Deterministic CBOR

ANLA v0.1 recommends RFC 8949 deterministic CBOR, because it is binary-friendly,
supports maps, arrays and byte strings, suits signing, can be schema-defined with
CDDL, and yields a stable byte representation for the same logical data.

A manifest does not use floating-point numbers for required structural fields.

---

### 11.2 Root manifest

Conceptually:

```json
{
  "anla_version": [0, 1],
  "archive_id": "...",
  "snapshot_id": "b3:...",
  "parent_snapshot": "b3:...",
  "created_at": "...",
  "hash_algorithms": ["blake3-256"],
  "required_capabilities": [
    "core.objects.v1",
    "core.chunks.v1",
    "codec.zstd.v1"
  ],
  "objects_root": "b3:...",
  "chunks_root": "b3:...",
  "metadata_root": "b3:...",
  "preservation_root": "b3:...",
  "auxiliary_root": "b3:...",
  "packing_plan_digest": "b3:..."
}
```

---

## Chapter 12. Snapshots

### 12.1 Append-only

Every update creates a new snapshot:

$$
S_{t+1}=(S_t,\Delta O,\Delta C,\Delta M)
$$

Old snapshots stay readable.

---

### 12.2 Snapshot ID

A snapshot ID is the content hash of the canonicalized manifest:

$$
\operatorname{snapshot\_id}
=
H(\operatorname{CanonicalEncode}(M))
$$

Signature fields must not create a circular dependency; a signature lives in a
separate `SIGN` record that references the snapshot ID.

---

### 12.3 Snapshot completeness

A snapshot must list root directory objects, all reachable objects, all chunk
references, external chunk descriptors, required metadata and required
capabilities. It must not depend on undeclared global state.

---

# Part V — Chunks and compression

## Chapter 13. Chunk identity

### 13.1 Digest

v0.1 default:

```text
BLAKE3-256
```

A chunk ID is computed over the uncompressed content:

$$
\operatorname{chunk\_id}=H(B_{\mathrm{raw}})
$$

so the same content has the same identity even when stored under a different
codec.

---

### 13.2 Compressed representation ID

Additionally:

$$
\operatorname{repr\_id}=H(C(B_{\mathrm{raw}},p))
$$

used to verify the stored compressed payload.

---

## Chapter 14. Chunking

### 14.1 Supported modes

```text
fixed-size
fastcdc
whole-object
small-object-pack
external-chunk-map
```

---

### 14.2 Fixed-size

Suits known random access, large immutable binaries, simple implementations, and
GPU or parallel processing. Parameters must be preserved:

```json
{
  "algorithm": "fixed",
  "size": 4194304
}
```

---

### 14.3 Content-defined chunking

Suits multi-version data, frequent insertion and deletion, backups, source code and
documents. v0.1 may adopt a FastCDC profile, with all parameters preserved:

```json
{
  "algorithm": "fastcdc",
  "version": "anla-profile-1",
  "min": 65536,
  "avg": 262144,
  "max": 1048576,
  "normalization": 2,
  "gear_table_id": "anla-standard-1"
}
```

Writing only `fastcdc` is insufficient: different implementations would then
produce different chunk boundaries.

---

### 14.4 Small-file aggregation

Many small files may be aggregated into a pack chunk, but the manifest must retain
each file's byte offset, length, content hash, metadata and object ID. Aggregation
must not break single-file verification or partial extraction.

---

## Chapter 15. Codecs

### 15.1 Codec registry

v0.1 core profile:

| Codec ID | Codec |
|---:|---|
| 0 | Store |
| 1 | Zstandard |
| 2 | Deflate |
| 3 | LZMA2 |
| 4 | Brotli |
| 5 | LZ4 Frame |

Minimum requirement for a core decoder:

```text
Store + Zstandard
```

Other codecs may be declared through capabilities.

---

### 15.2 Codec descriptor

```json
{
  "codec_id": 1,
  "codec_name": "zstd",
  "format_profile": "rfc8878",
  "level": 9,
  "dictionary": null,
  "window_log": null,
  "uncompressed_size": 1048576
}
```

Codec parameters must be sufficient for an independent decoder to reproduce
decoding.

---

### 15.3 Codec selection

An AI planner may choose a codec from MIME type, magic bytes, an entropy sample,
trial compression results, a decompression-latency target, a memory ceiling, access
frequency and the target platform.

The writer must then confirm that the codec is declared in the required
capabilities, is lossless, has round-tripped successfully, and does not exceed the
resource policy.

---

### 15.4 Already-compressed formats

JPEG, MP4, ZIP, 7z and PDF are not necessarily worth recompressing. A planner may
choose `Store` while still chunking, hashing, deduplicating, indexing and
encrypting.

---

## Chapter 16. Dictionaries

A compression dictionary is itself a preservation-plane object, with a dictionary
ID, its original bytes, a hash, a codec namespace, an optional description of its
training source, and its required capability. A decoder must not depend on an
undeclared dictionary from outside the archive.

---

# Part VI — Content addressing and deduplication

## Chapter 17. Deduplication scope

Supported:

```text
within-object
within-snapshot
within-archive
across-archive-store
remote-content-store
```

---

### 17.1 Deduplication inside an archive

If two slices reference the same `chunk_id`, only one payload representation needs
to be stored.

---

### 17.2 External chunks

An external content store may be referenced:

```json
{
  "chunk_id": "b3:...",
  "locations": [
    {
      "scheme": "https",
      "uri": "...",
      "expected_size": 1234
    }
  ],
  "embedded_fallback": false
}
```

Without an embedded fallback, the archive must not be labelled `self-contained`.

---

### 17.3 Deduplication and privacy

Cross-user deduplication can leak the existence of content. ANLA defines:

- `private`: no deduplication across trust domains;
- `archive-local`: within a single archive only;
- `trusted-store`: within one trust domain;
- `convergent`: a high-risk experimental mode, which v0.1 forbids by default.

---

# Part VII — Random access and streaming

## Chapter 18. Streaming creation

A writer may: write the bootstrap header; write chunks in order; write the
manifest; write the index; write the footer.

Before the footer arrives, a receiver may verify record headers, buffer chunks and
build a temporary index — but must not declare the snapshot complete.

---

## Chapter 19. Random access

A primary index maps at least:

```text
chunk_id → record_offset, payload_offset, compressed_length
object_id → manifest_entry
snapshot_id → footer_offset
```

An index can be rebuilt, so its corruption must not destroy the payload.

---

## Chapter 20. Partial materialization

An agent may request:

```json
{
  "snapshot": "b3:...",
  "objects": ["b3:...", "b3:..."],
  "destination": "...",
  "metadata_policy": "best-effort-report"
}
```

The resolver computes the minimal chunk set:

$$
C_Q
=
\bigcup_{o\in Q}\operatorname{Chunks}(o)
$$

and reads only $C_Q$.

---

# Part VIII — The intelligence plane

## Chapter 21. The packing plan

### 21.1 Plan schema

```json
{
  "plan_version": "0.1",
  "source_snapshot": "...",
  "selection": {
    "included_roots": ["..."],
    "excluded": []
  },
  "chunking_rules": [
    {
      "match": {"mime": "text/*"},
      "strategy": "fastcdc-text"
    }
  ],
  "codec_rules": [
    {
      "match": {"already_compressed": true},
      "codec": "store"
    }
  ],
  "metadata_policy": "full-supported",
  "verification": "full-round-trip",
  "resource_limits": {
    "memory_bytes": 4294967296,
    "threads": 8
  }
}
```

---

### 21.2 Plan and writer are separate

```text
AI Planner
   ↓ JSON Plan
Policy Validator
   ↓ Approved Plan
Deterministic Writer
   ↓
ANLA Archive
```

A planner does not write arbitrary binary format directly.

---

### 21.3 Decision log

Optionally preserved:

```json
{
  "decision_id": "...",
  "target": "object-id",
  "choice": "zstd-level-9",
  "alternatives": [
    {"codec": "store", "size": 1000000},
    {"codec": "zstd-3", "size": 410000},
    {"codec": "zstd-9", "size": 360000}
  ],
  "reason_codes": [
    "cold-data",
    "high-text-redundancy",
    "decompression-budget-satisfied"
  ],
  "planner": {
    "type": "model",
    "name": "...",
    "version": "..."
  }
}
```

A decision log is an `AUXI` record and does not affect extraction.

---

## Chapter 22. Optional indexes

Optional: full text; MIME; language; symbol and AST; image perceptual hash; audio
fingerprint; vector embedding; relationship graph; access heat.

Each index must declare its schema, generator, version, source snapshot, whether it
can be rebuilt, whether it contains private information, and whether it is
encrypted.

---

## Chapter 23. Decisions an AI must not make

Without explicit user or policy approval, a planner must not: exclude files;
rewrite original files; turn lossless into lossy; preserve only a recipe; download
external content in place of local content; overwrite an existing snapshot; remove
encryption; upload a private index; execute code inside the archive; or change
permission semantics.

---

# Part IX — Security

## Chapter 24. The extraction threat model

An ANLA decoder must prevent: path traversal; absolute-path overwrite; symlink and
hard-link escape; Unicode normalization collisions; case collisions; compression
bombs; chunk bombs; deep recursion; billion-laughs-style manifest attacks;
oversized declared lengths; integer overflow; codec memory exhaustion; malicious
sparse files; special-file creation; unauthorized ACL application; external-chunk
SSRF; signature bypass; and parser differential attacks.

---

## Chapter 25. Resource limits

An extraction request must support:

```json
{
  "max_output_bytes": 100000000000,
  "max_objects": 1000000,
  "max_path_depth": 256,
  "max_name_bytes": 4096,
  "max_chunk_uncompressed": 67108864,
  "max_ratio_per_chunk": 1000,
  "max_total_ratio": 100,
  "max_memory_bytes": 4294967296,
  "max_external_fetches": 0
}
```

Exceeding a limit must stop and report, never automatically relax the limit.

---

## Chapter 26. Safe extraction modes

### Inspect only

Creates no files.

### Quarantine extract

Applies no executable permissions; creates no symlinks; creates no special files;
applies no ACLs; rewrites dangerous names; produces a report.

### Exact restore

Used only with a trusted archive, a compatible platform and explicit user
authorization.

---

# Part X — Encryption and signatures

## Chapter 27. Order of compression and encryption

Required:

```text
Raw Chunk
→ Compress
→ Encrypt
```

You cannot encrypt first and expect general compression to work.

---

## Chapter 28. Chunk encryption

v0.1 recommends an AEAD profile; the full algorithm is defined by a separate
security profile.

Each encrypted chunk must carry an algorithm ID, a nonce, a key slot ID, associated
data, a ciphertext length and an authentication tag.

The associated data must bind at least the archive ID, the snapshot ID or security
context, the chunk ID, and the codec descriptor.

---

## Chapter 29. Metadata encryption

Available in grades:

```text
payload-only
payload-and-paths
full-manifest
opaque-archive
```

If the manifest is encrypted, the bootstrap must still retain a minimum capability
declaration, so a decoder knows which decryption module it needs.

---

## Chapter 30. Signatures

COSE_Sign1, or an equivalent public profile, may sign:

$$
\operatorname{Sign}(
\operatorname{archive\_id}
\Vert
\operatorname{snapshot\_id}
\Vert
\operatorname{preservation\_root}
)
$$

A signature does not replace chunk hashes.

---

# Part XI — Damage recovery

## Chapter 31. Detection and recovery are separate

A hash can detect damage:

$$
H(B)\neq H(\widehat{B})
$$

but cannot repair it.

---

## Chapter 32. Minimum recovery capability

v0.1 must ensure: footers can be repeated; manifests may optionally be repeated;
records carry a synchronization magic; indexes can be rebuilt; chunks can be
verified independently; damage to one chunk does not prevent extraction of others;
and a scanner can list recoverable objects.

---

## Chapter 33. Parity extension

A `PARI` record may use Reed–Solomon or another erasure code in a later profile.

A v0.1 core decoder may skip parity, but must not mistake the presence of parity
for payload.

---

# Part XII — Versioning and extension

## Chapter 34. Version policy

### Major

Breaks core parsing or semantics.

### Minor

Adds optional capabilities without breaking an existing core decoder.

---

## Chapter 35. Capability URIs

```text
anla:core:objects:1
anla:core:chunks:1
anla:codec:zstd:rfc8878
anla:index:fulltext:1
anla:security:cose-sign1:1
```

Required and optional capabilities must be listed separately.

---

## Chapter 36. Registry

Before formal standardization, a public Git repository maintains record types,
codec IDs, metadata namespaces, capabilities, error codes and test vectors. No
single private service may be the sole registration authority.

---

# Part XIII — CLI and agent API

## Chapter 37. CLI

```bash
anla plan <source> --policy policy.json --json
anla pack <source> --plan plan.json --output project.anla
anla inspect project.anla --json
anla list project.anla --snapshot latest --json
anla verify project.anla --mode full --json
anla extract project.anla --to output --safe
anla extract project.anla --object <id> --to output
anla update project.anla <source> --append
anla snapshots project.anla --json
anla diff project.anla <snapshot-a> <snapshot-b>
anla recover project.anla --scan
anla export project.anla --format zip --output project.zip
```

---

## Chapter 38. Exit codes

```text
0  success
1  generic failure
2  invalid input
3  unsupported required capability
4  manifest invalid
5  integrity failure
6  signature failure
7  decryption failure
8  resource limit exceeded
9  unsafe path or object
10 incomplete external content
11 extraction fidelity degraded
12 recovery partially successful
```

---

## Chapter 39. Structured errors

```json
{
  "error": {
    "code": "ANLA_UNSUPPORTED_REQUIRED_CAPABILITY",
    "message": "The archive requires codec.example.v2.",
    "retryable": false,
    "archive_safe": true,
    "details": {
      "capability": "anla:codec:example:2"
    }
  }
}
```

---

## Chapter 40. MCP and agent tools

```text
archive_plan
archive_pack
archive_inspect
archive_list_objects
archive_verify
archive_extract_objects
archive_append_snapshot
archive_diff_snapshots
archive_get_extraction_report
archive_export_view
```

Not provided:

```text
archive_run_embedded_program
archive_load_arbitrary_decoder
```

---

# Part XIV — Reference implementation

## Chapter 41. Technology stack

### Core

Rust stable; `serde`; a deterministic CBOR library; `blake3`; `zstd`; `crc32c`;
`fastcdc` or a locally pinned specification implementation.

### Optional C ABI

A minimal decoder API, to ease integration from other languages.

### Planner

A separate process, connected over JSON or a named pipe, which never enters the
core parser.

---

## Chapter 42. Repository

```text
anla/
├─ README.md
├─ LICENSE
├─ SECURITY.md
├─ SPEC.md
├─ schemas/
│  ├─ manifest.cddl
│  ├─ plan.schema.json
│  └─ extraction-report.schema.json
├─ crates/
│  ├─ anla-core/
│  ├─ anla-format/
│  ├─ anla-codec/
│  ├─ anla-chunk/
│  ├─ anla-fsmodel/
│  ├─ anla-security/
│  ├─ anla-cli/
│  └─ anla-planner-sdk/
├─ tools/
│  ├─ anla-inspect/
│  ├─ anla-recover/
│  └─ anla-fuzz/
├─ fixtures/
│  ├─ paths/
│  ├─ metadata/
│  ├─ corrupt/
│  ├─ bombs/
│  └─ cross-platform/
└─ conformance/
```

---

## Chapter 43. Parser principles

Bounds-check before allocating; do not trust declared lengths; parse iteratively and
bound recursion; use checked arithmetic; refuse unknown required records; run codec
decompression inside resource limits; fuzz every record and manifest; build
differential tests to keep multiple implementations consistent.

---

# Part XV — Conformance

## Chapter 44. Profiles

### ANLA-Core-Reader

Reads header, records and footer; parses a deterministic CBOR manifest; Store;
Zstandard; ordinary files and directories; BLAKE3 verification; safe paths;
extraction report.

### ANLA-Core-Writer

Includes core reader, and additionally: creates a single snapshot; fixed chunks;
whole object; Store and Zstandard; a complete manifest; a footer.

### ANLA-Advanced-Writer

FastCDC; deduplication; multiple snapshots; small-file aggregation; indexes; agent
plans.

### ANLA-Preservation

POSIX, Windows and macOS metadata; links and sparse files; a full fidelity report;
recovery.

---

## Chapter 45. Test vectors

Must include: an empty archive; an empty file; a single small file; a large
multi-chunk file; repeated chunks; UTF-8 multilingual paths; non-UTF-8 POSIX path
bytes; Windows UTF-16 special names; an NFC/NFD conflict; a case conflict; a
symlink; a hard link; a sparse file; an alternate data stream; a damaged chunk; a
damaged footer; an unknown optional record; an unknown required record; a
compression bomb; an appended snapshot; an encrypted archive; a bad signature;
legacy ZIP import metadata.

---

# Part XVI — Benchmarks

## Chapter 46. Baselines

ZIP Deflate; 7z LZMA2; TAR plus Zstandard; fixed 1 MiB plus Zstandard; FastCDC plus
Zstandard; the ANLA planner.

---

## Chapter 47. Data sets

Linux kernel source; a multi-version Git working tree; Node, Rust and Python
projects; model weights; images, audio and video; Office and PDF; game assets;
backup snapshots; multilingual and legacy-encoded filenames; a Windows metadata
fixture.

---

## Chapter 48. Metrics

### Compression ratio

$$
R_c
=
\frac{B_{\mathrm{archive}}}{B_{\mathrm{source}}}
$$

### Pack throughput

$$
T_p
=
\frac{B_{\mathrm{source}}}{t_{\mathrm{pack}}}
$$

### Extract throughput

$$
T_e
=
\frac{B_{\mathrm{restored}}}{t_{\mathrm{extract}}}
$$

### Dedup ratio

$$
R_d
=
1-
\frac{B_{\mathrm{unique\ chunks}}}{B_{\mathrm{chunk\ references}}}
$$

### Incremental amplification

$$
A_{\Delta}
=
\frac{B_{\mathrm{new\ records}}}{B_{\mathrm{changed\ source}}}
$$

### Planner return

$$
G_p
=
B_{\mathrm{fixed\ baseline}}
-
B_{\mathrm{planned}}
-
C_{\mathrm{planning}}
$$

Planning CPU, energy and latency must be discounted before any gain is claimed.

---

# Part XVII — Development roadmap

## Chapter 49. Milestone 0 — freeze the specification

Magic; header; record frame; footer; CDDL; BLAKE3; Store and Zstandard; safety
limits; test vectors.

---

## Chapter 50. Milestone 1 — core reader and writer

Single snapshot; ordinary files and directories; fixed chunks; verify; extract;
cross-platform CI.

---

## Chapter 51. Milestone 2 — the full filesystem model

Symlinks; hard links; sparse files; POSIX metadata; Windows metadata; macOS
metadata; fidelity report.

---

## Chapter 52. Milestone 3 — incremental and deduplication

FastCDC; cross-file deduplication; appended snapshots; diff; recovery scan.

---

## Chapter 53. Milestone 4 — the agent planner

Plan schema; a rule-based planner; a benchmark planner; an AI planner adapter; a
decision log; a policy validator.

Build the rule-based planner first, as a reproducible baseline, then evaluate
whether a model genuinely improves the result.

---

## Chapter 54. Milestone 5 — UI and mounting

A human GUI; an agent observatory; a read-only mount; partial materialization;
ZIP and TAR export.

---

# Part XVIII — Open questions

1. Should BLAKE3 be the only core hash, or should SHA-256 be required alongside it?
2. Should the deterministic CBOR profile follow RFC 8949 core requirements, or pin
   a stricter CDE?
3. How should FastCDC parameters be turned into a permanently stable profile?
4. What is the minimal cross-platform model for Windows NT names against POSIX byte
   names?
5. Should a metadata sidecar have its own standard?
6. Should a snapshot manifest use a single Merkle root or several?
7. How can an encrypted archive reconcile partial access with metadata privacy?
8. Should parity enter the core preservation profile?
9. How can a multi-volume archive keep snapshot atomicity?
10. How can a remote chunk store avoid SSRF, content substitution and availability
    dependence?
11. How can an agent planner prove nothing was left unpacked?
12. How can coverage of a packing plan be verified formally?
13. How can an AI planner be prevented from trading extraction latency for ratio?
14. How should cross-implementation parser differential testing be built?
15. Should `.anla` remain a single file, or also define a directory layout?

---

# Conclusion

ANLA v0.1 does not attempt to rebuild information theory, and it does not treat a
generative model as a decoder.

It establishes only a strict, implementable foundation:

- original content must be preserved completely;
- paths and platform metadata must be represented explicitly;
- codecs must be self-describing;
- chunks must be independently verifiable;
- snapshots must be appendable and revertible;
- an agent may plan, but may not bypass the writer's lossless validation;
- intelligence indexes may disappear and the archive remains readable;
- extraction requires no AI;
- unknown required capabilities must fail safely;
- every lossy extension is outside v0.1.

In one sentence:

> **ANLA is a lossless, content-addressed, versioned archive format that an AI can
> plan autonomously, that a deterministic writer builds, and that a
> model-independent decoder restores exactly.**

---

# Referenced specifications and engineering material

1. PKWARE, *APPNOTE.TXT — ZIP File Format Specification*.
   https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT

2. IETF, *RFC 8878: Zstandard Compression and the application/zstd Media Type*.
   https://www.rfc-editor.org/rfc/rfc8878

3. IETF, *RFC 8949: Concise Binary Object Representation (CBOR)*.
   https://www.rfc-editor.org/rfc/rfc8949

4. IETF, *RFC 9052: CBOR Object Signing and Encryption (COSE)*.
   https://www.rfc-editor.org/rfc/rfc9052

5. IETF, *RFC 8493: The BagIt File Packaging Format*.
   https://www.rfc-editor.org/rfc/rfc8493

6. BLAKE3 Team, *BLAKE3*.
   https://github.com/BLAKE3-team/BLAKE3

7. W. Xia et al., *FastCDC*, USENIX ATC 2016.
   https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia

8. IPLD, *Content Addressable aRchives*.
   https://ipld.io/specs/transport/car/

9. Open Container Initiative, *Image Specification*.
   https://github.com/opencontainers/image-spec

10. Unicode Consortium, *Unicode Standard Annex #15: Unicode Normalization Forms*.
    https://unicode.org/reports/tr15/
