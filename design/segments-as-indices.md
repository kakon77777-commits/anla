# Segments are indices, not pieces

Written before the code, after Neo pointed me at his 同一性微積分 series. It changes
the design I was about to build, and it removes a cost I was braced for.

## What I was going to do, and why it was wrong

The measured problem: 2,182 turns embedded, and random pairs scored **0.317** cosine
while the best match for a real question scored 0.485 — the signal inside the noise,
because a whole turn covers a defect, a measurement, a decision and an aside, so its
vector means "technical conversation" and nothing narrower.

The obvious fix is to embed smaller units. My instinct was: **split each turn into
segment objects**. More objects, each with one subject, each addressable.

That is *separation-type* cutting, and the paper has a criterion that rejects it:

> **同一性判據**：對系統中的任意碎片 a、b，若剝除全部索引資訊後 a 與 b 不可區辨且
> 均等同於整體，則該系統的切割是索引型切割…若剝除索引後 a、b 仍有殘餘差異，則該
> 切割是分離型切割，應交給測度論處理。

Splitting a turn into stored fragments leaves residual difference when the index is
stripped — fragment 1 holds different bytes from fragment 2. It is separation. And
separation costs exactly what the measure-theoretic warning says: the pieces stop
being the whole, the archive stores the same content twice, and every re-segmentation
rewrites the record.

## What the framework says instead

> 切割 = **索引**。一刀下去，X 完好如初地存在於本體層，呈現層多出了兩個視角。
> 你切的不是蛋糕，你切的是看蛋糕的方式。

A segment is **the whole turn plus a perspective**, not a part of it. So:

| | |
|---|---|
| **ontological layer** | the turn, stored whole, in the preservation plane — untouched by any cutting |
| **presentation layer** | segments as `(turn, start, end)` indices, in the auxiliary plane |

The two operators name what this system already does:

* **d, 索引算子** — cutting into perspectives. Segmentation is `d`. It outputs
  *perspectives, not parts*: 「d 不輸出部分…每個輸出都本體論地等於輸入，少掉的
  東西嚴格為零。」
* **∫, 遺忘算子** — dropping the index and seeing the record whole.
  **∫ ∘ d = id, and it is not a theorem but a consequence of the definition**,
  because `d` never separated anything and `∫` has no reconstruction to do.
* **d ∘ ∫ ≠ id**, and that is the correct asymmetry — the record keeps no trace of
  how it has been viewed. Which is *why* an omission manifest must carry its paths
  explicitly: the projection cannot be inverted from the projection.

## Four consequences that change the code

**1. The object count does not grow.** I was braced for segmentation to multiply
objects and make the manifest cost worse — that cost is already 352 bytes per turn
per checkpoint and linear in the conversation. With index-type cutting the
preservation plane is unchanged: segments are auxiliary. The problem I was about to
make worse, I do not make at all.

**2. Re-segmentation is free.** 「無限細切只是生成無限多個索引——本體層連被驚動都
沒有。」 A better segmenter later re-indexes; it does not rewrite a byte of the
record. Which means the segmenter can be wrong and it costs nothing permanent — the
opposite of the situation where I would have had to get it right before storing.

**3. Several segmentations can coexist.** Index families over one object. A
coarse one for projection, a fine one for retrieval, a task-specific one — 「重索引」
and 「細化」 are presentation-layer operators, cheap by construction.

**4. Projection already had a name.** 選擇, the fourth presentation-layer operator:
「注意一個碎片不是把世界縮小到碎片，而是暫時只用一個取景框看完整的世界。」 That is
what `project()` does and it is what makes an omission expandable. MNVP's
progressive disclosure and this arrive at the same place from different directions.

## Where the difficulty actually is

> 困難沒有消失——它遷移到了「選哪個索引方案最能揭示呈現層的結構」這個問題上…
> 地基平凡，樓上自由。

The foundation is trivial and the choice of scheme is everything. So the segmenter is
the whole problem, and the framework's contribution is that **choosing it badly is
cheap** — a bad index scheme is discarded and re-cut, not migrated.

## The acceptance test, fixed before building

The numbers this was written against, on 2,182 turns of this conversation with
`text-embedding-3-small` at 768 dimensions:

| | then | required |
|---|---|---|
| random-pair cosine, centred | mean 0.000, **p95 +0.238** | p95 below +0.15 |
| best match for a real question | **+0.316 centred**, below random p95 raw | clearly above random p95 |

If segmenting does not move those, it did not work, and no amount of reweighting will
be offered as though it had.

## What was measured

`bench/segment_retrieval.py`, twelve labelled queries, `text-embedding-3-small` at
768 dimensions, 5,000 segments embedded per scheme. Each question is about a fact in
this conversation and its ground truth is located by exact search for a distinctive
anchor — `anla-gear-1`, `functools.wraps`, `0.317` — while the *question* is written
to avoid the anchor entirely. The label therefore comes from a string match the
retriever never sees, and the query is exactly the case lexical matching cannot
answer.

One corpus for all four rows — 6,581 turns, digest `38c5455779cbe268` — because the
transcript is the session that is writing this and it grows between runs. Rows
measured days apart are rows about different corpora, and the whole output is a
comparison between rows, so the digest is recorded and a merge across digests is
refused.

| scheme | segments | p95 centred | R@1 | R@5 | MRR | median rank |
|---|---|---|---|---|---|---|
| `whole-turn-v1` (baseline) | 6,581 | +0.443 | 0.17 | 0.42 | 0.280 | 7.5 |
| `structural-v1` | 18,814 | +0.356 | 0.50 | 0.58 | 0.545 | 2.0 |
| `sized-900-v1` (control) | 23,036 | +0.361 | 0.58 | 0.75 | 0.656 | 1.0 |
| **`changepoint-v1`** | 61,458 | **+0.219** | **0.75** | **1.00** | **0.847** | **1.0** |

**Segmentation works, and the margin is not subtle.** Against the whole-turn baseline
measured by the same harness on the same corpus, the change-point scheme takes
Recall@1 from 0.17 to 0.75, Recall@5 from 0.42 to **1.00**, MRR from 0.280 to 0.847,
and the median rank of the right passage from 7.5 to 1.

**The control beat the structural scheme, and that is a result about the structural
scheme.** `sized-900-v1` exists to answer "would cutting every ~900 bytes have done
as well?" — and it did better: R@1 0.58 against 0.50, MRR 0.656 against 0.545. So the
document's own headings, paragraph breaks and fences were **not** carrying the
information; the scheme that reads them earned none of its extra complexity over a
ruler. What does work is cutting where the *vocabulary* changes, which is the only
one of the three that looks at content.

**The stated p95 gate failed — for every scheme, including the winner.** It is
reported as failed and the JSON records `gate_p95: false` on all four rows.

What the gate got wrong is worth stating precisely, because the temptation is to
relabel it. It required p95 below +0.15, calibrated against a turn-level baseline of
**+0.238** measured on 2,182 turns. On this corpus the turn-level baseline is
**+0.443** — the quantity the threshold was set against moved by more than the
threshold itself, so a scheme could halve the crowding and still miss. `changepoint-v1`
did halve it, from +0.443 to +0.219, and that is the number the gate was reaching for;
but a gate is not allowed to be re-read after the fact as whatever the result
supports. **A quantity compared only to its own earlier value is pinned by nothing**,
and this gate was exactly that.

So: the gate as written failed, the defect is mine, and the claim rests on the
retrieval measurements — Recall@1, Recall@5 and MRR — which were also fixed in
advance, are measured against ground truth the retriever never sees, and answer
directly the question p95 was only ever a proxy for.

## The end-to-end run says something the benchmark does not

`bench/native_context.py` drives the whole loop over MCP against the live transcript,
with no guarantee that the answer-bearing segment is in the embedded corpus — which
`segment_retrieval.py` deliberately does guarantee, so that recall is measured against
a large haystack without paying to embed all of it. The end-to-end number is lower,
and both are true of different questions:

* the benchmark answers *does segmenting improve retrieval, holding the corpus fixed*
* the end-to-end run answers *what does an agent actually get, today, on its own
  history* — including that the corpus contains near-duplicates of every topic,
  because a development transcript discusses the same defect a dozen times.

The second is the honest headline for a user and the first is the honest headline for
the design decision. Neither replaces the other, and the gap between them is a
measurement, not an embarrassment: it is the distance between "the unit is right" and
"the retriever is good".

On the 6,000-segment run it addressed 5 of 5 questions to digest-verified exact bytes
and got **1 of 5 right at rank 1**, against R@1 0.75 in the benchmark. Both numbers
are honest and they measure different things; the run prints them separately and
prints how much of the index carried a vector, because a nearest hit inside a tenth
of the record is indistinguishable from a complete search unless the share is stated.

Three hazards found by running it, none of which the benchmark could have shown:

1. **The transcript contains the benchmark's own questions** — in the source file, in
   earlier runs' output, in the discussion of them — and an embedding matches a
   question to itself far more strongly than to its answer. The first end-to-end run
   duly addressed the line of `QUESTIONS` rather than the passage. Same class as the
   sentinel string that matched the turn where it was typed. Dropped by exact match
   now, and the count is printed, since a silent exclusion is a thumb on the scale in
   the other direction.
2. **`limit` took a prefix.** Exporting the first 5,000 of 61,458 segments searched
   the opening eight per cent of the conversation and reported itself exactly as a
   complete search would. Sampling now spreads across the record by default and names
   which part it covered.
3. **A JSON vector sidecar does not survive one conversation.** Measured at 61,458 ×
   768, both formats written and read at full scale rather than extrapolated:

   | | size | write | load | search |
   |---|---|---|---|---|
   | JSON array of decimals | 978 MB | 85.7 s | 24.3 s | — |
   | `float32` behind a JSON header | **192 MB** | 16.6 s | **0.10 s** | **152 ms** |

   **5.1× smaller and two orders of magnitude faster to load.** NumPy stays
   optional: the preservation plane must never need it, and the pure-Python search
   is about **11 s** on that corpus — slow, but usable, and it refuses only when its
   projection passes a stated 30-second budget.

   **That last sentence is a correction.** The first version of this claimed the
   pure-Python search was *73 minutes* and refused above 8,000 vectors on that
   basis. The arithmetic was 70.9 µs × 61,458 read as 4,357 seconds when it is
   **4.4 seconds** — wrong by a factor of a thousand, and the 8,000-vector refusal
   would have fired at 1.5 seconds. It was caught by writing a harness that computes
   the projection from a measured per-element cost instead of restating a number I
   had multiplied in my head. **A constant nobody can re-derive is a constant nobody
   can catch**, so the threshold is now a time budget and the refusal quotes its own
   projection.

## On 相位

Neo named 相位 as the mechanism. Chapter 5 of this paper is **無相變原理** — the
no-*phase-transition* principle — and it is a different word: 相變 is a transition,
相位 is an angle. I am not going to treat one as the other.

What chapter 5 does contribute is a licence rather than a mechanism: 「呈現層允許任意
劇烈的不連續，本體層吸收全部連續性責任」, and an apparent phase transition decomposes
into 遺忘—再索引 with the same object running through both ends. That is exactly why
consequence 2 above holds. The mechanism 相位 names is still Neo's to state.
