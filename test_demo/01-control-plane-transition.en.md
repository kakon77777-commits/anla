---
title: "From Path Containers to Intelligent Packaging: The Control-Plane Transition Thesis for AI-Native Lossless Archive Formats"
subtitle: "An engineering observation on archive formats, model independence, and autonomous packaging"
author: "Neo.K"
organization: "EVEMISSLAB / EVEMISS Technology Co., Ltd."
date: "2026-07-16"
version: "v0.1"
status: "Observation paper / public concept draft"
language: "en"
translation_of: "01-control-plane-transition.zh-Hant.md"
disclosure: "This paper does not use any of the author's unpublished private theoretical documents as a basis for its argument."
---

# From Path Containers to Intelligent Packaging

## The Control-Plane Transition Thesis for AI-Native Lossless Archive Formats

**Author:** Neo.K
**Date:** 16 July 2026
**Document type:** Observation paper / public concept draft
**Translation:** English rendition of the Traditional Chinese original, which remains the canonical text.

---

## Abstract

ZIP, TAR and 7z were designed as file containers operated by humans: a person
selects files, sets compression options, builds an archive, and another person or
application unpacks it. Modern tools have added automatic detection, content
preview and better Unicode support, but the control plane of the format has
stayed roughly where it began — a human issues a compression command and the tool
executes a fixed strategy.

When AI agents begin managing code projects, research data, game assets, model
files and cross-platform workspaces, the compression system acquires a new kind of
operator. An agent does not merely call "compress" and "decompress". It analyses
file types, measures compressibility, chooses lossless codecs, plans chunking,
builds indexes, updates incrementally, materializes subsets, verifies integrity,
and records every packing decision it made.

This paper proposes the **control-plane transition thesis**:

> The next significant evolution of archive formats may not come first from a
> higher single-codec compression ratio, but from the packaging control plane
> moving from manual human configuration to autonomous operation that an AI can
> plan, audit and replay.

AI-native, however, must not come to mean generative reconstruction, and a model
must never be permitted to substitute a summary, a prompt, a semantic
approximation, or a judgement that content "could be regenerated" for the
original data. The paper therefore draws a strict boundary:

> An AI may decide *how* to preserve. It may not decide whether the original bits
> are worth preserving. Whatever is declared into an archive must be recoverable,
> exactly, by a decoder that is deterministic and independent of any model.

AI-native lossless packaging is defined here as the separation of a
**preservation plane** from an **intelligence plane**. The preservation plane
carries original content, paths, metadata, integrity and recovery. The
intelligence plane carries planning, indexing, querying and automation. The
intelligence plane may be deleted or rebuilt at any time, and the preservation
plane must still decode completely. This gives a format both agent operability
and long-term digital preservation, without making a file's lifetime depend on a
particular model, vendor or inference result.

**Keywords:** AI-native format, lossless compression, archive format, coding
agent, content addressing, deterministic decoding, model independence,
compression control plane

---

# 1. The problem is not that ZIP is old; it is that the operator has changed

## 1.1 The historical success of traditional formats

ZIP's longevity does not come from its algorithm. Its larger advantages are:

- broad operating-system support;
- support in most programming languages and standard libraries;
- support in email, browsers, cloud drives and messaging tools;
- a stable mental model among users;
- document and application formats that reuse the ZIP container;
- decades of accumulated toolchain compatibility.

ZIP's market position can therefore be written, roughly, as:

$$
V_{\mathrm{ZIP}}
=
V_{\mathrm{codec}}
+
V_{\mathrm{compatibility}}
+
V_{\mathrm{installed\ base}}
+
V_{\mathrm{social\ expectation}}
$$

A format that is more modern in compression ratio, encryption or Unicode design
still finds the last three terms very hard to displace at once.

The ZIP specification later added a UTF-8 flag and a Unicode Path Extra Field to
address the absence of self-describing filename encoding. Yet a great many
historical archives still carry only local code-page bytes, leaving the receiving
end dependent on external context or manual choice to decode a name correctly.
Once a format establishes long-term path dependence, context it failed to record
early can remain a burden on tools for decades.

---

## 1.2 Traditional tools still put a human at the centre

The typical flow is:

```text
human selects files
→ human picks ZIP or 7z
→ human sets a compression level
→ tool applies a fixed strategy
→ human names and moves the archive
```

This flow presumes an operator who has:

- visual understanding of the directory;
- subjective preferences about ratio versus speed;
- manual judgement about paths and encodings;
- prior knowledge of which files matter;
- responsibility for the extraction location and overwrite risk.

Even where compression software offers an automatic mode, the decisions are
usually local and unauditable. A tool may pick a method by file extension, but it
does not emit a complete machine-readable plan explaining:

- why the data was chunked this way;
- why a particular codec was chosen;
- which blocks were deduplicated;
- which metadata was preserved;
- which platform attributes cannot be restored;
- whether the archive supports partial materialization;
- whether an update requires repacking everything.

For a human compressing a folder occasionally, these gaps are acceptable. For an
agent maintaining large workspaces autonomously, they become systemic limits.

---

# 2. AI-native is not "a compression tool with a chat box"

## 2.1 Wrapping an interface is not a native format

If an AI merely calls, from a GUI or a shell:

```bash
7z a project.7z project/
```

then an AI is using a traditional tool. Nothing about the format's capability
model has changed.

Genuinely AI-native packaging lets an agent work directly with:

- analysis of a file set;
- lossless codec selection per data type;
- fixed or content-defined chunking;
- deduplication across files and across versions;
- mixed fast and high-compression modes;
- random access into large files;
- aggregation of small files;
- incremental versions;
- remote partial download;
- path context and platform metadata;
- integrity, signatures and damage recovery;
- structured decision records.

The core of AI-native is therefore not a natural-language interface, but a
control surface the format itself exposes: composable, queryable, verifiable.

---

## 2.2 From "a command" to "a packing plan"

Traditional compression input is usually just:

$$
(\text{source},\text{format},\text{level})
$$

The input to an AI-native system looks more like:

$$
P
=
(C, K, D, M, I, S, V)
$$

where:

- $C$ is codec configuration;
- $K$ is chunking configuration;
- $D$ is deduplication configuration;
- $M$ is metadata preservation policy;
- $I$ is index configuration;
- $S$ is security and resource limits;
- $V$ is versioning and update strategy.

The AI's role is to produce a packing plan from a file set $F$ and a user policy
$\Pi$:

$$
P = \operatorname{Plan}_{AI}(F,\Pi)
$$

But a plan must not be the same thing as a result. It is handed to a
deterministic writer for validation:

$$
A = W(F,P)
$$

where $W$ must reject:

- input objects the plan does not cover;
- lossy codecs;
- unrecognized decoders;
- chunks lacking integrity information;
- metadata loss that violates policy;
- undeclared path normalization;
- parameters beyond the safety limits.

---

# 3. The lossless floor

## 3.1 The content-fidelity invariant

Let $F=\{f_1,f_2,\ldots,f_n\}$ be the set of files declared into an archive, $A$
the archive, and $D$ the standard decoder. The most basic requirement is:

$$
D(A)=F
$$

and for each file's content:

$$
H(f_i)=H(\widehat{f_i}),\qquad \forall i
$$

where $H$ is the cryptographic hash the specification names and $\widehat{f_i}$ is
the extracted content.

This is a bit-level requirement, not a similarity requirement. None of the
following may substitute for that equality:

- the text means the same thing;
- the image looks similar;
- the video scores well enough on a quality metric;
- the program still compiles;
- a model can regenerate it;
- the dependency can be downloaded again;
- an agent judged the file unimportant.

---

## 3.2 Archive scope and data omission must stay separate

An AI may advise a user to exclude caches, build products or re-downloadable
dependencies — but exclusion must happen *before* the archive set is formed.

Let the original workspace be $U$ and the user-approved archive set be:

$$
F = \operatorname{Select}(U,\Pi)
$$

The lossless promise holds only for $F$:

$$
D(W(F,P))=F
$$

If a file is not in $F$, the manifest must record explicitly that it was not
packed. The user must never be left believing the whole workspace was preserved.

These two things then stop being confused with each other:

- the decision about archive scope;
- lossless compression within that scope.

---

## 3.3 Metadata needs graded fidelity too

"The file contents are identical" does not mean "the workspace is identical".
Some systems also depend on:

paths and case; permissions; ACLs; symbolic links; hard links; sparse ranges;
extended attributes; alternate data streams; resource forks; creation and
modification times; reparse points.

So three levels should be distinguished:

### Content-level lossless

$$
F_{\mathrm{content}}
\equiv
\widehat{F}_{\mathrm{content}}
$$

### Namespace-level lossless

$$
F_{\mathrm{namespace}}
\equiv
\widehat{F}_{\mathrm{namespace}}
$$

### Platform-metadata-level lossless

$$
F_{\mathrm{metadata}}
\equiv
\widehat{F}_{\mathrm{metadata}}
$$

When extracting across platforms, the target filesystem may be unable to apply
all metadata as stored. The decoder must then retain the original metadata and
emit an explicit report — it must not discard silently and still claim full
restoration.

---

# 4. The preservation plane and the intelligence plane

## 4.1 The preservation plane

The preservation plane holds everything needed to extract the original data:

```text
Preservation Plane
├─ format version and capability declarations
├─ object list
├─ original file content
├─ chunk map
├─ codecs and parameters
├─ paths and platform metadata
├─ content hashes
├─ snapshot root
├─ signatures
└─ recovery information
```

It has four properties:

1. it is publicly implementable;
2. it does not depend on model inference;
3. its decoding result is determined;
4. it remains verifiable long term.

---

## 4.2 The intelligence plane

The intelligence plane holds derived data an agent needs in order to work:

```text
Intelligence Plane
├─ compression decision records
├─ file type and language annotations
├─ search indexes
├─ similarity indexes
├─ task-specific views
├─ agent operation logs
├─ access-heat hints
└─ rebuildable semantic indexes
```

A different model can rebuild the intelligence plane, so it must never be a
precondition for recovering original content.

Formally, with:

$$
A = (P,I)
$$

where $P$ is the preservation plane and $I$ the intelligence plane, the following
must hold:

$$
D(P,I)=D(P,\varnothing)=F
$$

This is the **disposability of the intelligence layer**.

---

## 4.3 The model-independence criterion

If a format can only be decompressed correctly by the model that created it, it
is not a dependable file format. It is a model-bound generation protocol.

An AI-native format should satisfy:

$$
D_{m_1}(A)=D_{m_2}(A)=D_{\mathrm{nonAI}}(A)=F
$$

where $m_1$ and $m_2$ are different models and $D_{\mathrm{nonAI}}$ is the
specification's decoder with no model in it at all.

A model may change packing efficiency. It may not change extraction truth.

---

# 5. The control-plane transition thesis

## 5.1 The thesis

> **Control-plane transition thesis.** As AI agents come to manage large,
> heterogeneous file populations continuously, the primary locus of innovation in
> compression systems will shift from the compression ratio of a single codec
> toward a packaging control plane that an agent can plan, verify, update and
> partially materialize.

This does not dismiss codec research. A codec still determines the space and time
efficiency of particular data. But across a multi-type workspace, the overall
result also depends on:

$$
E_{\mathrm{archive}}
=
f(
E_{\mathrm{codec}},
E_{\mathrm{chunk}},
E_{\mathrm{dedup}},
E_{\mathrm{index}},
E_{\mathrm{update}},
E_{\mathrm{access}}
)
$$

with terms for single-block compression efficiency, chunking efficiency,
deduplication efficiency, retrieval efficiency, incremental-update efficiency and
partial-access efficiency respectively.

An AI's advantage is that it can coordinate these dimensions dynamically, against
the whole workspace and its task history.

---

## 5.2 What an agent can do that a fixed default cannot

Within a single archive, for instance:

- source code suits smaller chunks, which improves incremental deduplication;
- large already-compressed video should be stored, not recompressed;
- repeated model weights suit larger chunks with cross-version deduplication;
- thousands of small text files can be aggregated first, then dictionary-compressed;
- frequently read indexes can sit at the front or in a separate fast region;
- cold data can take a slow-encoding, fast-decoding, high-ratio setting;
- a remote workspace can carry a partial-materialization index;
- Windows, Linux and macOS metadata can be preserved in separate namespaces.

Traditional tools can reach some of this through a great many manual options. An
agent can turn those choices into a replayable plan and adjust it against real
measurements.

---

# 6. Why existing formats supply only part of the answer

## 6.1 ZIP

ZIP offers broad compatibility, per-file packaging and several extension fields.
Its historical baggage includes filename encodings that may not be
self-describing, a central directory and local headers that create awkward
consistency problems, incremental and cross-version deduplication that are not
part of its core model, and agent decisions and indexes that are not first-class
structures.

ZIP is well suited as an export and interchange format. It need not be the
internal ceiling of an AI-native system.

---

## 6.2 7z

7z has a more modern Unicode and compression design, and supports capabilities
such as solid compression — but it remains primarily a high-efficiency
compression container rather than an agent's versioned workspace protocol.

---

## 6.3 CAR and content-addressed packaging

IPLD CAR streams content-addressed blocks, and demonstrates that an archive can
be organized around content hashes and an object graph rather than only around a
path tree. CAR does not, however, define complete cross-platform file metadata,
compression-strategy governance, or an AI decision plane.

---

## 6.4 OCI Image

The OCI Image Specification uses manifests, descriptors and content-addressed
blobs, with an index able to point at per-platform versions. It demonstrates the
interoperability strength of separating manifest from payload, content addressing,
and platform views. Its target, though, is container images rather than
general-purpose preservation of arbitrary workspaces.

---

## 6.5 BagIt

BagIt requires a payload manifest that lists every file with its checksum, which
suits reliable transfer and digital preservation. Its important lesson is that a
completeness inventory belongs in the core of a packaging specification, not as an
afterthought. BagIt does not target efficient chunking, deduplication, random
access or agent-driven updates.

---

# 7. Conditions that would refute the thesis

The control-plane transition thesis is not necessarily correct. The following
would weaken it.

## 7.1 Insufficient return from AI planning

If experiments show that an AI's mixed chunking and codec plans yield no stable
gain over a fixed Zstandard or 7z setting while adding significant complexity,
then AI planning should not be a format's central selling point.

---

## 7.2 Decision cost above the saving

Let planning cost be $C_p$ and the saved storage, transfer and decompression cost
be $B_s$. If, over the long run:

$$
C_p > B_s
$$

then autonomous planning has no engineering value.

---

## 7.3 Complexity that destroys interoperability

If a new format's optional capabilities multiply until implementations cannot
interoperate, decoders become prone to security defects, a minimal reader cannot
be built, or archives require a large runtime, then it may repeat the failure of
other over-complex formats.

---

## 7.4 Humans and ordinary programs cannot use it

AI-native must not mean human-excluding. A format operable only by agents, with no
stable CLI, library or filesystem mount, will struggle to form a real ecosystem.

---

# 8. Research and experiment design

## 8.1 Test data sets

At minimum: large numbers of small source files; large binary models; already
compressed images and video; Office and PDF documents; game assets and
legacy-encoded filenames; multi-version repositories; Windows, Linux and macOS
metadata; large sparse files; repeated backup data.

---

## 8.2 Comparison baselines

ZIP Deflate; 7z LZMA2; TAR plus Zstandard; fixed-size chunking plus Zstandard;
FastCDC plus Zstandard; an AI-planned mixed strategy.

---

## 8.3 Metrics

### Storage

$$
R_c
=
\frac{\text{archive bytes}}{\text{original bytes}}
$$

### Packing speed

$$
T_p
=
\frac{\text{input bytes}}{\text{pack time}}
$$

### Extraction speed

$$
T_u
=
\frac{\text{output bytes}}{\text{unpack time}}
$$

### Incremental efficiency

$$
R_{\Delta}
=
\frac{\text{new archive bytes}}{\text{changed source bytes}}
$$

### Partial-materialization efficiency

$$
L_m
=
\text{time to materialize the requested object set}
$$

### Fidelity

$$
Q_f
=
\begin{cases}
1, & \text{every required content and metadata item verifies}\\
0, & \text{any required item disagrees}
\end{cases}
$$

In a lossless format, fidelity is not a continuous score. It is a specification-level
pass or fail.

---

# 9. Governance principles

## 9.1 The AI may only propose a plan

The final writer must verify that codecs are lossless; that every input byte has a
corresponding chunk; that all chunks decode; that the manifest is complete; that
path and metadata policy is satisfied; and, on completion, perform a sampled or
full round trip.

---

## 9.2 Unknown capabilities must be refused or degraded

A decoder must not guess at an unknown codec or unknown metadata semantics.

On encountering an unknown required capability:

```text
MUST fail
```

On encountering an unknown optional intelligence index:

```text
MAY skip
```

This lets the format grow without endangering the preservation core.

---

## 9.3 Intelligence indexes must not contaminate preservation truth

AI annotations can be wrong: a misjudged language, a mis-inferred MIME type, an
incorrect file relationship, a mistaken importance class. They must therefore
record their producer, model or tool version, time, confidence, whether a human
confirmed them, and whether they can be rebuilt.

A wrong index can be deleted. The original files must be unaffected.

---

# 10. Conclusion

An AI-native compression format is not a model pressing the compress button for a
human, and it is not a generative model substituting approximate content for
original data.

It represents two changes happening at once.

First, the control plane of compression and packaging becomes something an agent
can plan autonomously. An AI can decide lossless codecs, chunking, deduplication,
indexing and update strategy from file types, version relationships, access
patterns and resource conditions.

Second, data preservation must become stricter than before. Because the
decision-maker is no longer always human, the format needs invariants, manifests,
hashes, capability declarations and a deterministic decoder to bound the AI's
freedom.

The paper's central definition is:

> **AI-native lossless packaging is a format that permits an AI to plan, build,
> index, update and query autonomously, while a public, deterministic,
> model-independent decoder guarantees that all declared original content and
> protected metadata can be recovered exactly.**

The real innovation is therefore not in letting an AI decide what data may be
lost. It is in:

> **giving an AI packaging intelligence while making the format itself refuse
> information loss.**

---

# References

1. PKWARE, *APPNOTE.TXT — ZIP File Format Specification*.
   https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT

2. IETF, *RFC 8878: Zstandard Compression and the application/zstd Media Type*.
   https://www.rfc-editor.org/rfc/rfc8878

3. W. Xia et al., *FastCDC: A Fast and Efficient Content-Defined Chunking Approach
   for Data Deduplication*, USENIX ATC 2016.
   https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia

4. IETF, *RFC 8949: Concise Binary Object Representation (CBOR)*.
   https://www.rfc-editor.org/rfc/rfc8949

5. BLAKE3 Team, *BLAKE3 Specification and Reference Implementations*.
   https://github.com/BLAKE3-team/BLAKE3

6. IPLD, *Content Addressable aRchives Specification*.
   https://ipld.io/specs/transport/car/

7. Open Container Initiative, *OCI Image Specification*.
   https://github.com/opencontainers/image-spec

8. IETF, *RFC 8493: The BagIt File Packaging Format*.
   https://www.rfc-editor.org/rfc/rfc8493

9. IETF, *RFC 9052: CBOR Object Signing and Encryption*.
   https://www.rfc-editor.org/rfc/rfc9052
