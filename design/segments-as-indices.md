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

The current numbers, on 2,182 turns of this conversation with
`text-embedding-3-small` at 768 dimensions:

| | now | required |
|---|---|---|
| random-pair cosine, centred | mean 0.000, **p95 +0.238** | p95 below +0.15 |
| best match for a real question | **+0.316 centred**, below random p95 raw | clearly above random p95 |

If segmenting does not move those, it did not work, and no amount of reweighting will
be offered as though it had.

## On 相位

Neo named 相位 as the mechanism. Chapter 5 of this paper is **無相變原理** — the
no-*phase-transition* principle — and it is a different word: 相變 is a transition,
相位 is an angle. I am not going to treat one as the other.

What chapter 5 does contribute is a licence rather than a mechanism: 「呈現層允許任意
劇烈的不連續，本體層吸收全部連續性責任」, and an apparent phase transition decomposes
into 遺忘—再索引 with the same object running through both ends. That is exactly why
consequence 2 above holds. The mechanism 相位 names is still Neo's to state.
