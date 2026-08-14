# From "the freeze rule is met" to "someone can use this"

Written 2026-08-14, after Q4 closed the last open question that changes bytes.

The project has spent three weeks answering *is this correct?* and has a good answer.
It has never asked *would anyone use it?*, and the two questions have almost nothing
in common. This document is the second one, measured rather than assumed, because the
first thing measuring found was a hundredfold performance gap nobody had looked for.

---

## 1. Where we actually are

**`ANLA-MVP v0.1` — frozen and finished.** Two implementations (Python, JavaScript),
byte-identical output, 10 frozen conformance vectors, a browser workbench that
verifies itself in a tab. This is done and should not be touched.

**`ANLA 1.0` — DRAFT, and complete as a format.** Container, canonical CBOR manifest,
five Merkle roots, append-only snapshots with cross-snapshot deduplication,
content-defined chunking (`anla-cdc-1`), BLAKE3-256, Zstandard, metadata namespaces,
the fidelity report, symbolic links, native names (§5.2.1.1, closed today). Two
implementations sharing no code below `blake3` and `zstd`, producing **byte-identical
archives** across six configurations on three platforms.

**The evidence behind it is unusually good**, and that is the project's real asset:

| instrument | what it covers |
|---|---|
| 738 Python + 14 Rust tests | the rules, individually |
| byte comparison, 6 configurations × 3 platforms | that two writers agree exactly |
| differential fuzzing, hash-repairing mutator | that two readers agree on hostile input |
| 258-case enumeration of every manifest edit | that they agree *completely* on one axis |
| verify-predicts-extract, on all 258 | that a green verify means something |
| `test_demo/` corpus, 20 files, 12 types | that real files round-trip byte for byte |
| `bench/` against ZIP, tar.gz, ANLA-MVP | what it costs, including the rows it loses |

Nothing below changes that. The gap is not correctness.

---

## 2. What "commercially usable" means

Someone trusts it with data they cannot afford to lose, and gets it back. That is
five separate conditions, and the project currently meets one:

| | condition | today |
|---|---|---|
| 1 | **Fast enough** that using it is not a decision | **no** — measured below |
| 2 | **Installable** without cloning a repository | **no** — no package exists |
| 3 | **Safe enough** for data that matters — encryption, provenance | **no** |
| 4 | **Complete enough** to replace what they use now | partly |
| 5 | **Stable** — a format that will not change under them | **no** — DRAFT |

---

## 3. The gap, measured

### 3.1 The Python chunker is a hundredfold slower than the format requires

64 MiB of incompressible data, this machine, today:

| writer | chunking | throughput | 1 TB would take |
|---|---|---|---|
| Python | fixed | 358 MiB/s | 49 minutes |
| **Python** | **`anla-cdc-1`** | **3.9 MiB/s** | **3 days** |
| Rust | `anla-cdc-1` | 61.7 MiB/s | 4.6 hours |

`anla-cdc-1` is the **default**, and it has to be: fixed chunking makes cross-snapshot
deduplication collapse — the measured difference is 280 KiB against 2.86 MiB for a
64-byte insertion. So the mode that makes the product worth having is the mode that
runs at 3.9 MiB/s.

The cause is a per-byte rolling-hash loop in pure Python. Rust does the identical
work sixteen times faster, which says the **format is fine and the implementation is
not**. Verification is unaffected (400–500 MiB/s) because it hashes whole chunks.

This inverts the project's architecture. Python is currently the primary
implementation and Rust is "the second one, for the freeze rule". For anything
commercial it must be the other way round: **Rust is the product, Python is the
reference and the conformance oracle.** That is also the better use of the Python
one — a readable, dependency-free implementation that a stranger can audit is worth
more as a specification companion than as a tool nobody can run at scale.

Even 61.7 MiB/s is not a strong number. `restic` and `borg` are in the hundreds. That
is a Phase 2 problem, not a Phase 1 one.

### 3.2 Nobody can install it

There is no `pyproject.toml`, no `setup.py`, no published crate. Installation is "clone
the repository and set `PYTHONPATH`". Every other item in this document is downstream
of that, because an artifact nobody can install has no users and therefore no feedback.

### 3.3 The differentiator does not exist

The whitepaper's claim is that **an AI plans the packing and a deterministic,
model-independent decoder undoes it exactly**. The decoder is built and proven. The
planner is Milestone 4 and has not been started — `grep` for it finds nothing.

So today ANLA is a well-verified deduplicating archive format **with no AI in it**,
competing against `restic`, `borg` and `kopia`, which are mature, fast and free. On
that field it is behind and its name does not describe it.

This is the strategic fact in the document. Everything ANLA can charge for lives in
the part that is not built.

### 3.4 Data people care about needs more than correctness

- **Encryption** (Q7, open). For backup this is not a feature, it is a precondition.
  The hard part is stated in the spec and is real: encrypting the manifest destroys
  partial access, and not encrypting it leaks every filename.
- **Signatures** (crypto, deferred). §5.3 already establishes that a signature must
  bind `snapshot_id` rather than `preservation_root`, so the analysis is done and the
  implementation is not. For a provenance story — *this archive is what that agent
  produced* — this is the mechanism.
- **Random access.** `INDX` is a reserved record type and nothing else. Extracting one
  file from a large archive currently means reading the manifest for the whole
  snapshot.
- **Repair.** Deliberately out of the core (Q8) with a good argument. But "damage to
  one chunk costs you only that chunk" needs to be *demonstrated on a damaged archive*,
  not only asserted, before anyone stores something irreplaceable.

### 3.5 It says DRAFT, and it should

Asking someone to adopt a format whose specification opens with "nothing here is
frozen" is asking them to accept a migration they cannot schedule. The three reasons
the draft gives are honest and two are now cheap to retire; §4 puts that last, on
purpose, because freezing before the planner exists would freeze the wrong format.

---

## 4. Which product — the decision this plan needs

Three coherent products, and they order the work differently.

**A. A format others adopt.** Ship the spec, the conformance suite and reference
implementations; earn nothing directly. Needs: freeze, a conformance badge, an RFC-ish
document, adoption work. *Honest assessment: this is a ten-year game and ANLA has no
distribution.*

**B. A backup tool.** Compete with `restic`/`borg`/`kopia`. Needs: speed parity,
encryption, pruning, remote back-ends, a restore UX. *Honest assessment: excellent
free incumbents, ANLA is 5–10× behind on throughput, and the thing it does better —
provable determinism — is not what buyers of backup tools shop for.*

**C. An artifact store for AI pipelines.** The whitepaper's actual claim: a model
chooses how to pack, the plan is recorded, validated and replayable, and a decoder
with no model in it returns every byte. Needs: the planner, plan validation,
signatures, provenance, and an SDK. *Honest assessment: no incumbent, the
differentiator is real and defensible, and every property already built —
determinism, the two-plane split, `strip`, the fidelity report, byte-identity across
implementations — is a requirement of this product rather than a nice-to-have.*

**Recommendation: C, built on B's engineering.** C is the only option where the work
already done is the moat rather than table stakes, and where "an AI planned this and a
deterministic decoder can prove exactly what it did" is something a buyer needs. A
follows from C for free — a format used by a real product gets adopted; a format
published and advocated does not.

---

## 5. The order of work

Each phase ends in a **measured demonstration against real alternatives, losing rows
included** — the standing rule, and the reason the benchmark exists.

### Phase 1 — Make it real (unblocks everything)

1. **`pyproject.toml`, `pip install anla`, a published crate.** Console scripts for
   `anla` and `anla1`. Wheels in CI on three platforms.
2. **Make Rust the production path.** `anla1` gains a native backend when the binary
   is available and keeps the pure-Python one as a documented fallback with its speed
   stated. **The byte comparison is what makes this safe** — it already proves the two
   produce identical archives, so switching which one runs is not a change in output.
3. **A streaming Rust writer.** Python streams; Rust still buffers the archive in RAM,
   so the fast path cannot pack a tree larger than memory. This is the one place where
   the two implementations' capabilities are inverted.
4. **Measure and publish throughput** on the `/bench/` page next to the ratios, against
   `restic`, `borg`, `tar+zstd`. Including where ANLA loses, which today is everywhere.

*Demonstration: pack, verify and restore 10 GB in one run, with the wall-clock time
and peak memory published beside restic's on the same corpus.*

### Phase 2 — Make it trustworthy for data that matters

5. **Signatures first, encryption second.** Signatures are the smaller job (the
   binding analysis is done in §5.3), they are what product C needs, and they can ship
   without answering Q7.
6. **Encryption, answering Q7 explicitly** — which fields stay in the clear so partial
   access survives, stated as a decision with its privacy cost written down.
7. **`INDX`, as a cache a reader may ignore** — already the design in §6. Extract one
   file from a 100 GB archive without reading the whole manifest.
8. **Demonstrate the damage claim.** Corrupt one chunk of a large archive and show
   exactly one file is affected and named. This is a test the project should already
   have and does not.

*Demonstration: a signed, encrypted 10 GB archive; one chunk destroyed; verify names
precisely what is lost; everything else restores byte for byte.*

### Phase 3 — Build the thing the name promises

9. **The planner, rule-based first.** A packing plan is already a first-class,
   validated, replayable object in the format — this is the part that fills it in.
10. **Plan validation and the decode-latency budget (Q13).** The spec calls Q13 "the
    most under-rated item on the list" and it is: without it a planner can trade
    extraction speed for ratio and nobody notices.
11. **A model-driven planner behind the same validator**, so the AI is a *proposer*
    and the format is the check. This is the whitepaper's architecture made real.
12. **Provenance**: which model, which prompt, which plan, which archive — signed, in
    the intelligence plane, droppable by `strip` without touching a preserved byte.

*Demonstration: the same corpus packed by a fixed policy and by a model-chosen plan,
with ratio **and** decode latency for both, and the model's plan rejected when it
violates the budget.*

### Phase 4 — Freeze, and stand behind it

13. Retire the draft's three reasons: get a **second author** to implement or review
    (the one weakness no amount of my own work can fix), close the Rust writer's
    remaining narrowness, and close §10.
14. **Freeze 1.0.** Conformance vectors, a version policy, a compatibility promise.

---

## 6. What this plan deliberately does not do

- **No GUI.** Product C's user is a pipeline, not a person at a window.
- **No cloud service.** Remote back-ends are Phase 2+ *if* a user asks; running
  storage is a different business with a different cost structure.
- **No new format features** before Phase 1. The format is not what is missing.

## 7. The one thing to be honest about

Three weeks of work produced a format that is very well verified and that nobody can
install, that runs its own default mode at 3.9 MiB/s, and whose distinguishing feature
is unimplemented. None of those is a criticism of the verification — the verification
is why the next phase can move fast without breaking what exists. But the ratio of
*proof* to *product* is currently extreme, and Phase 1 exists to correct it before any
more proof is added.
