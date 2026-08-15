# -*- coding: utf-8 -*-
"""Segments as indices into preserved turns — S1, Indexed Semantic Addressing.

    𝓜 --d_σ--> 𝓘_σ --π_σ--> 𝓧_σ --E_θ--> 𝓥_σ,θ --Ψ_τ--> 𝓔^(τ)

The invariant this module exists to hold:

    **a segment is an index / a perspective, never a newly preserved fragment.**

From Neo's 同一性微積分: 切割 = 索引. A cut does not divide the object; it adds
perspectives to the presentation layer while the object stays whole in the
ontological layer. The 同一性判據 rejects the alternative directly — if stripping
the index leaves residual difference between two fragments, the cut was separation
and belongs to measure theory, not here. Stored fragments hold different bytes, so
storing them would be separation.

Three things follow, and they are why this module writes nothing to the
preservation plane:

* **The authoritative turn is never modified or copied.** A segment is
  `(source_turn, ranges)` — raw byte offsets — and `π_σ` reads the bytes back out.
* **Re-segmentation rewrites nothing.** 「無限細切只是生成無限多個索引——本體層連被
  驚動都沒有。」 A better segmenter later produces a new index family; the record is
  untouched, so a segmenter is allowed to be wrong.
* **Several schemes coexist over one memory.** σ₁ … σₙ are index families, not
  competing copies, and choosing between them is a measurement rather than a
  migration.

The canonical locator is a **raw byte offset into the turn as stored**. Not a
character offset, not an offset into extracted text: those depend on a decoder and
a text extractor, and an index whose meaning depends on the tool that reads it is
not an index into the record. `source_digest` pins the turn the offsets were
computed against, so an index can be *checked* rather than trusted.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

__all__ = [
    "SEGMENT_SCHEMA_VERSION", "Segment", "SegmentIndex", "SCHEMES",
    "structural_segments", "sized_segments", "changepoint_segments",
    "build_index", "project_segment", "digest_of",
]

#: Bumped when the stored shape changes, so an index written by an older version
#: is recognisable rather than silently misread.
SEGMENT_SCHEMA_VERSION = 1


def digest_of(raw: bytes) -> str:
    """What the offsets were computed against. Checked, not assumed."""
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


@dataclass(frozen=True)
class Segment:
    """One perspective on one preserved turn.

    `ranges` is a list from the start even though every scheme here emits exactly
    one: a quoted passage answered by a later reply, a tool call and its result, an
    argument split by an interruption — these are one view over discontiguous bytes,
    and a schema that has to change shape to express them would make the first such
    scheme a migration instead of a scheme.
    """

    segment_id: str
    source_turn: str
    source_digest: str
    scheme_id: str
    scheme_version: int
    ranges: tuple[tuple[int, int], ...]
    kind: str
    ordinal: int
    projection_version: str

    @property
    def byte_length(self) -> int:
        return sum(end - start for start, end in self.ranges)

    def as_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "source_turn": self.source_turn,
            "source_digest": self.source_digest,
            "scheme_id": self.scheme_id,
            "scheme_version": self.scheme_version,
            "ranges": [{"start_byte": s, "end_byte": e} for s, e in self.ranges],
            "kind": self.kind,
            "ordinal": self.ordinal,
            "projection_version": self.projection_version,
        }

    @classmethod
    def of(cls, payload: dict) -> "Segment":
        return cls(
            segment_id=payload["segment_id"],
            source_turn=payload["source_turn"],
            source_digest=payload["source_digest"],
            scheme_id=payload["scheme_id"],
            scheme_version=int(payload["scheme_version"]),
            ranges=tuple((int(r["start_byte"]), int(r["end_byte"]))
                         for r in payload["ranges"]),
            kind=payload["kind"],
            ordinal=int(payload["ordinal"]),
            projection_version=payload["projection_version"],
        )


@dataclass
class SegmentIndex:
    """One index family σ over one memory. Auxiliary plane, always."""

    scheme_id: str
    scheme_version: int
    projection_version: str
    segments: list[Segment] = field(default_factory=list)
    #: Typed relations between turns, from `relations.derive_edges` — the
    #: context/index base, never a phase. Populated by the caller rather than by
    #: `build_index`, because the edges are a fact about the record and re-deriving
    #: them per scheme would make them a fact about the segmenter instead.
    #: `relations.EDGE_KINDS` lists which kinds are derivable and which are not.
    edges: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": "anla:context:segment-index:1",
            "schema_version": SEGMENT_SCHEMA_VERSION,
            "scheme_id": self.scheme_id,
            "scheme_version": self.scheme_version,
            "projection_version": self.projection_version,
            "segments": [s.as_dict() for s in self.segments],
            "edges": self.edges,
            "plane": "auxiliary — the preservation plane holds the turns and is "
                     "not touched by any of this; D(P, I) = D(P, ∅)",
        }

    @classmethod
    def of(cls, payload: dict) -> "SegmentIndex":
        return cls(scheme_id=payload["scheme_id"],
                   scheme_version=int(payload["scheme_version"]),
                   projection_version=payload["projection_version"],
                   segments=[Segment.of(s) for s in payload["segments"]],
                   edges=list(payload.get("edges") or []))


# ---------------------------------------------------------------------------
# π_σ — reading a view back out of the record
# ---------------------------------------------------------------------------

def project_segment(segment: Segment, raw: bytes, *, check: bool = True) -> str:
    """π_σ: the text this segment indexes, read out of the preserved turn.

    Verifies the digest first. An index computed against different bytes than the
    ones it is now being read against produces plausible text from the wrong
    place — the failure mode that has no symptom, so it is checked every time
    rather than at write.
    """
    if check and digest_of(raw) != segment.source_digest:
        raise ValueError(
            f"{segment.segment_id} was indexed against a different turn: digest "
            f"{segment.source_digest[:16]} but this turn is "
            f"{digest_of(raw)[:16]}. The offsets do not mean what they meant.")
    pieces = []
    for start, end in segment.ranges:
        if start < 0 or end > len(raw) or start >= end:
            raise ValueError(f"{segment.segment_id}: range {start}:{end} is not "
                             f"inside a {len(raw)}-byte turn")
        pieces.append(raw[start:end].decode("utf-8", "replace"))
    return _unescape("\n".join(pieces))


#: The turns are JSONL, so a slice of the raw bytes carries JSON escapes. Undone
#: for the *view* only — the record keeps its bytes, and the offsets keep pointing
#: at them. This is the projection, and its version is recorded with every vector
#: because two runs that unescape differently produce different vectors from one
#: model.
PROJECTION_VERSION = "jsonl-slice-unescape-1"

_ESCAPES = ((r"\\n", "\n"), (r"\\t", "\t"), (r"\\r", ""), (r"\\\"", '"'),
            (r"\\/", "/"), (r"\\\\", "\\"))


def _unescape(text: str) -> str:
    for pattern, replacement in _ESCAPES:
        text = re.sub(pattern, replacement.replace("\\", "\\\\"), text)
    return text.strip()


# ---------------------------------------------------------------------------
# d_σ — the index families
# ---------------------------------------------------------------------------

#: Boundaries visible in the raw JSONL bytes. A paragraph break inside a JSON
#: string is the two characters `\` `n` twice, not a newline, so these look for what
#: is actually in the bytes rather than what the decoded text would contain.
_STRUCTURAL = (
    (rb"```", "code-fence"),
    (rb"\\n\\n", "paragraph"),
    (rb"\\n#{1,6} ", "heading"),
    (rb"\\n[-*] ", "list"),
    (rb"\\n\d+\. ", "list"),
)


def _spans(raw: bytes, cuts: Sequence[int], minimum: int) -> list[tuple[int, int]]:
    """Turn cut points into ranges, merging anything below the floor forward.

    A 12-byte segment embeds to noise, so the floor is not tuning — it is the point
    below which the view has no content to be about.
    """
    bounds = sorted({0, *cuts, len(raw)})
    spans: list[tuple[int, int]] = []
    start = bounds[0]
    for end in bounds[1:]:
        if end - start < minimum and end != len(raw):
            continue
        spans.append((start, end))
        start = end
    if start < len(raw):
        if spans and len(raw) - start < minimum:
            spans[-1] = (spans[-1][0], len(raw))
        else:
            spans.append((start, len(raw)))
    return [(s, e) for s, e in spans if e > s]


def structural_segments(raw: bytes, minimum: int = 200) -> list[tuple[int, int, str]]:
    """σ_structural: cut where the document says it changes subject.

    Headings, paragraph breaks, code fences and list items — the boundaries the
    author already put there. Deterministic, needs no model, and is the baseline
    everything else has to beat.
    """
    cuts, kinds = [], {}
    for pattern, kind in _STRUCTURAL:
        for match in re.finditer(pattern, raw):
            cuts.append(match.start())
            kinds[match.start()] = kind
    spans = _spans(raw, cuts, minimum)
    return [(s, e, kinds.get(s, "prose")) for s, e in spans]


def sized_segments(raw: bytes, target: int = 900, minimum: int = 200
                   ) -> list[tuple[int, int, str]]:
    """σ_sized: fixed target size, snapped to the nearest structural boundary.

    The control for the structural scheme. If cutting every ~900 bytes does as well,
    then the structure was not carrying the information and the structural scheme
    has not earned its complexity.
    """
    boundaries = sorted({m.start() for pattern, _ in _STRUCTURAL
                         for m in re.finditer(pattern, raw)})
    cuts, position = [], target
    while position < len(raw):
        nearby = [b for b in boundaries if abs(b - position) <= target // 3]
        cuts.append(min(nearby, key=lambda b: abs(b - position)) if nearby else position)
        position = cuts[-1] + target
    return [(s, e, "sized") for s, e in _spans(raw, cuts, minimum)]


def changepoint_segments(raw: bytes, window: int = 400, minimum: int = 200,
                         sensitivity: float = 0.55) -> list[tuple[int, int, str]]:
    """σ_changepoint: cut where the vocabulary changes, without a model.

    A sliding comparison of the token sets either side of each candidate point; a
    cut goes where the overlap drops. This is the cheap stand-in for semantic
    change-point detection — it needs no embeddings, which is the point, since it
    has to be available before the embedding backend is decided.
    """
    text = raw.decode("utf-8", "replace")
    tokens = [(m.start(), m.group(0).lower())
              for m in re.finditer(r"[\w\u4e00-\u9fff]+", text)]
    if len(tokens) < 40:
        return [(0, len(raw), "whole")]

    step = max(12, window // 40)
    cuts = []
    for i in range(step * 2, len(tokens) - step * 2, step):
        before = {t for _, t in tokens[i - step * 2:i]}
        after = {t for _, t in tokens[i:i + step * 2]}
        union = before | after
        if not union:
            continue
        overlap = len(before & after) / len(union)
        if overlap < (1 - sensitivity) * 0.5:
            # Token offsets are into the decoded string; the record is bytes, so
            # convert rather than assuming they coincide. They do not for CJK.
            cuts.append(len(text[:tokens[i][0]].encode("utf-8")))
    return [(s, e, "changepoint") for s, e in _spans(raw, cuts, minimum)]


#: The families, so a benchmark can iterate them rather than name them one at a
#: time. AI-proposed segmentation joins this table later and competes on the same
#: measurements — it is not the baseline and does not get to be.
SCHEMES: dict[str, Callable[[bytes], list[tuple[int, int, str]]]] = {
    "structural-v1": structural_segments,
    "sized-900-v1": sized_segments,
    "changepoint-v1": changepoint_segments,
    "whole-turn-v1": lambda raw: [(0, len(raw), "turn")],
}


def build_index(turns: Iterable[tuple[str, bytes]], scheme_id: str,
                scheme_version: int = 1) -> SegmentIndex:
    """d_σ: apply one scheme across a memory, producing one index family.

    Writes nothing. Returns an index that a caller stores in the auxiliary plane —
    and `whole-turn-v1` is in the table so the thing being replaced is measured by
    the same harness as its replacements, rather than remembered.
    """
    if scheme_id not in SCHEMES:
        raise ValueError(f"unknown scheme {scheme_id!r}; have {sorted(SCHEMES)}")
    cut = SCHEMES[scheme_id]
    index = SegmentIndex(scheme_id=scheme_id, scheme_version=scheme_version,
                         projection_version=PROJECTION_VERSION)
    for path, raw in turns:
        digest = digest_of(raw)
        for ordinal, (start, end, kind) in enumerate(cut(raw)):
            index.segments.append(Segment(
                segment_id=f"{path}#{scheme_id}:{ordinal:04d}",
                source_turn=path, source_digest=digest,
                scheme_id=scheme_id, scheme_version=scheme_version,
                ranges=((start, end),), kind=kind, ordinal=ordinal,
                projection_version=PROJECTION_VERSION))
    return index
