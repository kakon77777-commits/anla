# ANLA for context: what this was actually for

Written 2026-08-14, when Neo said what the target is: **an AI natively compressing
its own context.** Everything before this document treated that as an archive format
looking for a market. It is not; it is the preservation half of a thing that does not
exist yet, and the other half is already written down in three of his other
specifications.

Plans in this repository are argued before they are coded, and every number below was
measured while writing it — including the one that says ANLA is the wrong tool for
half the job.

---

## 1. Why summarisation is the wrong primitive

When a context window fills, the state of the art is to summarise: a model reads what
is there and writes something shorter. Four properties of that operation, none of
which anyone would accept from a filesystem:

* **Lossy without a manifest.** Something was dropped. Nothing says what.
* **Irreversible.** The dropped part is gone. There is no expansion.
* **Model-dependent.** Run it twice, get two different contexts. Run it on a
  different model and the disagreement is unbounded.
* **Unverifiable.** No property of the result can be checked against the original,
  because the original is no longer there.

MNVP names the defect in one sentence, and it is the sentence this whole document
turns on:

> **永久刪除與可展開壓縮是不同操作。**
> *Permanent deletion and expandable compression are different operations.*
> — `MNVP_獨立理論_數值語義到認知投影_v0.1.md` §原則四

Today's context compression is the first, wearing the second's name.

---

## 2. The three related languages, and what each one contributes

From [efficientnewlanguage.org/related](https://efficientnewlanguage.org/related/),
all three of Neo's, all frozen at v1.0, all on disk under `D:\Ai\work together\`.

### MNVP — the contract a lossy projection owes

MNVP is a theory of *rendering numbers for people*, and it generalises exactly. Its
central object is a mapping

$$\mathcal V:\ \mathcal N\times\mathcal C\ \rightarrow\ \mathcal G$$

— semantically complete objects, crossed with a projection situation, into something
perceivable. Instantiated for context:

| MNVP | here |
|---|---|
| $\mathcal N$, semantically complete objects | the authoritative context: every turn, tool result, file read, decision |
| $\mathcal C$, projection situation | the token budget, the current task, what the model needs next |
| $\mathcal G$, the perceivable object | the compressed context the model actually reads |

Four of its rules become the specification:

* **原則三 — the task's critical semantics must survive.** $K_\tau(\mathbf N)\subseteq
  R(\mathbf G)$. A projection that drops what the current task needs is not a
  faithful projection, however short it is.
* **原則四 — progressive disclosure, not permanent omission.** $L_0\subseteq
  L_1\subseteq\dots\subseteq L_n$, and a lower level must keep *an expansion
  mechanism, an omission hint, a link to the full value, and machine-readable
  underlying data*.
* **§6.1 — four levels.** L0 core, L1 comparison, L2 explanation, L3 audit. For
  context: the answer; the answer with its neighbours; with why and from where; with
  the verbatim record and its provenance.
* **§6.3 — every output carries an omission declaration.**
  ```json
  {"preserved": [...], "omitted": [...], "expandable": true}
  ```
  Which is, to the field, **ANLA's fidelity report** — a thing this repository
  already built, already put in the preservation plane, and already proved `strip`
  cannot launder away.

### CAIR — a model's output is a candidate, not a commit

> "AI and UI edits become candidate proposals, never silent commits."

Applied here: **a compressed context is a projection, never a replacement.** A model
may propose what to drop; it may not delete its own history. The authoritative record
is written once and is append-only, which is the shape ANLA snapshots already have.

### ICNS — a comparison is allowed to fail

> `LT / EQ / GT / INCOMPARABLE`, extending to `DEFINITELY_LT / POSSIBLY_LT /
> OVERLAPPING / UNKNOWN`.

Applied here: *"is this projection faithful for this task?"* must be allowed to answer
**UNRESOLVED**, and the system must carry that answer rather than round it to yes. A
compressor that always claims fidelity is a compressor whose fidelity claim is worth
nothing — the same lesson as every unfalsifiable check this project has already found
in itself.

---

## 3. What ANLA already provides

Not by coincidence. The invariant was chosen for preservation and preservation is
what this needs.

| already built | what it does for context |
|---|---|
| `Extract(Pack(F, P)) = F` | the authoritative context survives the compression of it |
| preservation vs intelligence plane, `D(P,I)=D(P,∅)` proven | the record is required; summaries, indexes and embeddings are disposable and regenerable |
| the fidelity report, in the preservation plane | MNVP's omission declaration, in a place `strip` cannot remove |
| the recorded `packing_plan` | the model's compression decision is an auditable artifact, not a memory |
| append-only snapshots with a footer chain | a context is a sequence of checkpoints, never rewritten |
| cross-snapshot deduplication | measured below, and it is the whole game |
| two implementations, byte-identical | the decoder needs no model, and two of them agree |

---

## 4. Measured, including where it loses

A real corpus: a Claude Code session transcript from this machine — **149 MB, 39,387
records**. A 32 MiB slice of it, cut on a record boundary.

### One finished transcript: ANLA loses, badly

| | bytes | of raw |
|---|---|---|
| raw JSONL | 33,529,018 | 100% |
| gzip -9 | 8,045,814 | 24.0% |
| **zstd -10** | **4,873,412** | **14.5%** |
| ANLA, `anla-cdc-1` + zstd | 10,913,400 | 32.5% |

**More than twice as large as plain zstd**, and structurally so: zstd sees repetition
across the whole stream, ANLA compresses each chunk alone so any chunk can be read
without the others. §8 says this and the benchmark already carries the losing row.

If the job were "compress one finished transcript", the answer would be zstd and this
document would end here.

### Ten checkpoints of a growing context: ANLA wins

But a context is not delivered finished. It grows, and it is saved repeatedly. Ten
checkpoints of the same transcript, each ~10% longer than the last:

| checkpoint | context bytes | ANLA adds | zstd of the whole |
|---|---|---|---|
| 1 | 3,874,744 | 1,279,408 | 611,672 |
| 3 | 10,600,941 | 1,428,176 | 1,672,805 |
| 5 | 17,625,160 | 1,538,480 | 2,834,712 |
| 8 | 26,913,787 | 1,113,392 | 4,009,784 |
| 10 | 33,529,018 | **1,208,032** | **4,873,412** |

**ANLA's cost per checkpoint is flat; the alternative's grows with the context.** By
the tenth, keeping the new state costs 1.2 MB against 4.9 MB, and the gap widens for
as long as the conversation does.

| keeping all ten | bytes | |
|---|---|---|
| ANLA archive | 12,442,712 | |
| one zstd file per checkpoint | 28,491,393 | **2.3× ANLA** |
| only the newest zstd file | 4,873,412 | but the other nine are gone |

That last row is what summarisation is, and it is a different product: cheapest, and
it answers no question about what used to be there.

### What the numbers actually say

Deduplication is the right mechanism **because context is mostly a re-statement of
itself** — the same file read twice, the same tool result quoted, the same reasoning
restated. And the win is in the *keeping*, not in any single compression.

---

## 5. What is missing, honestly

1. **Addressable partial extraction.** `INDX` is a reserved record type and nothing
   else. Progressive disclosure is impossible without cheap random access: L0 is only
   a projection rather than a deletion if you can pull back the omitted turn without
   decompressing the archive. This moves from a Phase 2 nicety to **load-bearing**.
2. **An object model for context.** A conversation is not a filesystem tree. Turns,
   tool calls, results and file snapshots have an order and a causal structure that
   `path → bytes` does not express. This is new format work, and §5.2 is where it
   would go.
3. **The projection layer.** MNVP is a theory here and nothing implements it for
   text. This is the actual new product.
4. **Faithfulness is task-relative and that is the hard part.** $K_\tau(\mathbf N)
   \subseteq R(\mathbf G)$ requires knowing $\tau$, and only a model knows it — which
   is precisely where CAIR says to be careful, and why the projection must be a
   candidate that the authoritative record outlives.

---

## 6. What to build first

The smallest thing that is honest and useful, and it is not the whole product:

**Take a real Claude Code transcript, store it losslessly in ANLA, and emit an L0/L1/L2
projection with an omission manifest in which every omission is addressable.**

Then measure, against naive truncation and against a summariser:

* tokens in the projection, per level;
* what each level preserves and omits, as a manifest rather than a claim;
* and the property neither alternative has — **pick any omitted turn and get it back
  byte for byte**, which is the test that says this is compression rather than
  deletion.

That last measurement is the one that matters. Everything else is a ratio, and ratios
we already know how to publish.

---

## 7. Deferred, at Neo's instruction

**CCMSUSMS.** His words: theoretically possible, practically doubtful, *"有點麻煩"*,
and to be done later. Recorded here so it is not lost and not started.

---

## 8. What this changes about the commercial plan

`commercial-readiness-plan.md` picked product C — an artifact store for AI pipelines —
as the option where the work already done is the moat. That reading was right and too
small. Neo: commercialisation is a yardstick for progress, not the goal.

The order does not change much, which is a good sign for the plan rather than a
coincidence: signatures and `INDX` were already Phase 2, and the planner was already
Phase 3. What changes is *why*. `INDX` is not random access for its own sake, it is
what makes an omission expandable; the planner is not a packing optimiser, it is the
thing that decides what a context can afford to stop showing.
