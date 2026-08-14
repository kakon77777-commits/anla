# -*- coding: utf-8 -*-
"""The resonant memory domain: which of a shared history belongs in this moment.

From Neo's 符號記憶判定耦合系列 papers 05–07, and it replaces an order-based
retriever that was wrong on the axis it chose rather than wrong in its details.

Paper 05 defines the domain:

    𝓔_AB^(τ) = { m ∈ 𝔐_AB : Ψ_τ(m) ≥ θ_τ }

The shared history is 𝔐; what belongs in the shared *present* is 𝓔, the subset
whose appropriateness clears a threshold — and 𝓔 is normally a very small subset,
changes as τ moves even when the store does not, and is not a function of time
except through one of its eight terms:

    Ψ_τ(m) = f(R_τ, S_τ, C_τ, D_τ, H_AB, P_τ, O_τ, I_τ)

    R content relevance    S relational salience   C local context match
    D current judgement    H position in shared history
    P temporal position and evolution state
    O still valid, or superseded
    I the risk that surfacing this is intrusive

**「還在記憶庫裡」不等於「仍在共同現在」.** Being in the store is not being in the
shared present, and that distinction is the whole module.

Paper 06 supplies the correction that matters most here. Recency distortion is not
that recent outweighs old:

    w(m | t) 與 τ_persistence(m) 不匹配

— it is that an item's *weight* fails to match that item's own persistence
timescale. An instantaneous state should decay in hours; a stable working method
should not be overwritten by one counterexample. So every memory carries a
persistence class (paper 06 §1.2: S instantaneous, C active context, P persistent
structure, H long-term trajectory) and time enters through that, not through a sort.

Paper 07 sets three boundaries this module must not be read as crossing:

    Recall ≠ Care
    PerceivedCare ≠ ActualCare
    RelationalSignal ≠ RelationshipOntology

A high score here means a memory is *appropriate to surface*. It does not mean the
system cares, and nothing about the relationship follows from it.

**What is missing, and it is the main thing.** Neo's mechanism is 相位 and
語義向量 — phase and semantic vectors — and the paper's title says why the word is
literal: 共感 is *resonance*, and resonance is a phase phenomenon. A memory joins
the present when it is in phase with it, not when it is lexically similar to it.
There is no embedding model wired in here, so `semantic` and `phase` are declared
absent rather than approximated by word overlap wearing their name. Every channel
below says whether it is present, and the absent ones are the honest part.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "PERSISTENCE", "Candidate", "Resonance", "classify_persistence",
    "resonant_domain", "CHANNELS",
]

#: Paper 06 §1.2, with the timescale each class is *allowed* to be weighted on.
#: The number is not a decay rate — it is the scale a weight has to match, and a
#: mismatch in either direction is the distortion the paper names.
PERSISTENCE = {
    "S": ("instantaneous state", 3_600),             # minutes / hours
    "C": ("active context", 30 * 86_400),            # days / weeks / months
    "P": ("persistent preference or method", 365 * 86_400),
    "H": ("long-term trajectory", 10 * 365 * 86_400),
}

#: Named so a caller can see what did and did not contribute. DRVS's rule: a
#: missing channel degrades structurally and never fabricates, and the ones that
#: are absent are stated rather than silently skipped.
CHANNELS = {
    "R": "content relevance — lexical, present",
    "C": "local context match — overlap with the current moment, present",
    "H": "position in shared history — present",
    "P": "persistence class against the asking timescale — present",
    "O": "superseded by something later — present, crude",
    "S": "relational salience — absent, needs a relation graph",
    "D": "current judgement domain — absent, needs the task stated",
    "I": "intrusion risk — absent, and not approximable from text",
    "semantic": "semantic vectors — present when supplied, ABSENT otherwise",
    "phase": "phase / resonance — ABSENT, and deliberately not invented",
}

_WORD = re.compile(r"[\w一-鿿]+", re.UNICODE)

#: Markers that a turn states something durable rather than something momentary.
#: Deliberately small and legible: this is a placeholder for a classifier, and a
#: long opaque list would hide that.
_DURABLE = ("always", "never", "從此", "以後", "標準", "規則", "原則", "policy",
            "convention", "standing", "must", "一律", "每次")
_MOMENTARY = ("now", "today", "this turn", "現在", "今天", "這次", "先", "暫時",
              "just", "quick")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 1}


@dataclass
class Candidate:
    """One memory in the shared history, with what is known about it."""

    key: str
    text: str
    position: int
    total: int
    age_seconds: float = 0.0
    persistence: str = "C"
    superseded_by: str | None = None
    #: A semantic vector, when something outside supplied one. Nothing here
    #: computes embeddings — the model that can is the one holding the
    #: conversation, and UTF-8X's rule applies: the AI produces the strategy, the
    #: deterministic side consumes it. So this arrives, it is not derived.
    vector: Sequence[float] | None = None


@dataclass
class Resonance:
    """Why this memory did or did not enter the shared present."""

    key: str
    score: float
    terms: dict[str, float] = field(default_factory=dict)
    why: str = ""
    persistence: str = "C"

    def as_dict(self) -> dict:
        return {"key": self.key, "score": round(self.score, 4),
                "terms": {k: round(v, 4) for k, v in self.terms.items()},
                "why": self.why, "persistence": self.persistence,
                "persistence_meaning": PERSISTENCE[self.persistence][0]}


def classify_persistence(text: str) -> str:
    """Which timescale this memory's weight is allowed to live on.

    Crude on purpose and replaceable: paper 06's point is that the *class* must
    exist and the weight must match it, not that any particular classifier is
    right. Getting this wrong costs a misweighted memory; not having it at all
    costs the distinction between "you were tired that day" and "you always want
    it this way", which is the distortion the paper is about.
    """
    lowered = (text or "").lower()
    if any(marker in lowered for marker in _DURABLE):
        return "P"
    if any(marker in lowered for marker in _MOMENTARY):
        return "S"
    return "C"


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, refusing rather than guessing on a length mismatch.

    Two embeddings of different width did not come from the same model, and
    silently comparing their overlapping prefix would produce a confident number
    from an incoherent comparison — ICNS's point that a comparison must be allowed
    to fail rather than be rounded to an answer.
    """
    if len(a) != len(b):
        raise ValueError(f"vectors of different width: {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def resonant_domain(candidates: Sequence[Candidate], query: str = "",
                    moment: Iterable[str] = (), threshold: float = 0.18,
                    limit: int = 20, asking_scale: float = 30 * 86_400,
                    query_vector: Sequence[float] | None = None,
                    ) -> tuple[list[Resonance], dict]:
    """𝓔^(τ): the memories that belong in this moment, and why.

    `moment` is the present — the turns currently in view — and it matters as much
    as `query`. A retriever that only reads the query answers "what mentions this";
    Ψ is asking "what belongs here now", and the difference is C_τ.

    Returns the domain and a report of which channels contributed. The report is
    not decoration: with `semantic` and `phase` absent, this is a stand-in whose
    limits a caller has to be able to see.

    Ψ is **evidence × modulation**, not a weighted sum of everything. R, C and
    semantic are evidence that this memory belongs here; H, P and O scale it. The
    first version added all six, which gave an irrelevant memory a score of 0.30
    from being un-superseded and of an ordinary persistence class alone — so 𝓔 was
    the whole history rather than a small subset of it.
    """
    wanted = _words(query)
    present = set()
    for piece in moment:
        present |= _words(piece)

    scored: list[Resonance] = []
    for candidate in candidates:
        words = _words(candidate.text)
        if not words:
            continue
        terms: dict[str, float] = {}

        # R — content relevance. Lexical, and named as lexical.
        terms["R"] = (len(wanted & words) / len(wanted)) if wanted else 0.0

        # C — does it match the moment we are actually in, rather than the query.
        terms["C"] = (len(present & words) / min(len(present), 400)) if present else 0.0

        # H — position in the shared history. Not recency: both ends of a long
        # relationship carry weight the middle does not, because the beginning is
        # where things were established and the present is where they are used.
        where = candidate.position / max(1, candidate.total - 1)
        terms["H"] = 0.5 + 0.5 * abs(2 * where - 1)

        # P — the paper 06 term. A weight is only allowed to decay on the scale its
        # own persistence class lives on; asking on a longer scale than the memory
        # persists is what turns "the recent you" into "the whole you".
        scale = PERSISTENCE[candidate.persistence][1]
        decay = math.exp(-candidate.age_seconds / scale) if candidate.age_seconds else 1.0
        mismatch = min(1.0, asking_scale / scale) if scale else 1.0
        terms["P"] = decay * (1.0 - 0.5 * (1.0 - mismatch))

        # O — superseded. Still in 𝔐, no longer in 𝓔.
        terms["O"] = 0.0 if candidate.superseded_by else 1.0

        # Evidence and modulation are different kinds of term, and adding them
        # together was a defect a test caught immediately: H, P and O each give
        # about 1.0 to a *completely irrelevant* memory, so every memory cleared
        # the threshold and 𝓔 was the whole history up to the limit rather than
        # paper 05's 極小子集.
        #
        # "Nothing later replaced it" is not a reason to surface something. It is a
        # condition on surfacing it. So R, C and semantic are evidence, H, P and O
        # scale it, and a memory with no evidence scores ~0 however well-preserved
        # and un-superseded it is.
        if query_vector is not None and candidate.vector is not None:
            terms["semantic"] = max(0.0, _cosine(query_vector, candidate.vector))
            evidence = (0.55 * terms["semantic"] + 0.20 * terms["R"]
                        + 0.25 * terms["C"])
        else:
            evidence = 0.65 * terms["R"] + 0.35 * terms["C"]

        # H nudges rather than decides: position in the shared history says a
        # memory is the kind of place things get established, not that this one is
        # relevant.
        modulation = (0.75 + 0.25 * terms["H"]) * terms["P"] * terms["O"]
        score = evidence * modulation
        terms["evidence"] = evidence
        terms["modulation"] = modulation

        why = _why(terms, candidate)
        scored.append(Resonance(key=candidate.key, score=score, terms=terms,
                                why=why, persistence=candidate.persistence))

    scored.sort(key=lambda r: -r.score)
    domain = [r for r in scored if r.score >= threshold][:limit]
    embedded = sum(1 for c in candidates if c.vector is not None)
    channels = dict(CHANNELS)
    if query_vector is not None and embedded:
        channels["semantic"] = (f"semantic vectors — PRESENT, {embedded} of "
                                f"{len(candidates)} memories carry one")
    return domain, {
        "embedded": embedded,
        "threshold": threshold,
        "considered": len(scored),
        "in_domain": len(domain),
        "share_of_history": (round(len(domain) / len(scored), 4) if scored else None),
        "channels": channels,
        "absent": [k for k, v in channels.items() if "ABSENT" in v],
        # Paper 07. Stated in the output because the output is what gets read.
        "boundary": "Recall ≠ Care. This ranks what is appropriate to surface, "
                    "and nothing about a relationship follows from it.",
    }


def _why(terms: dict[str, float], candidate: Candidate) -> str:
    """A reason naming what contributed, in DRVS's discipline: never a bare number."""
    if candidate.superseded_by:
        return f"superseded by {candidate.superseded_by}, so it is history not present"
    ranked = sorted(terms.items(), key=lambda kv: -kv[1])
    names = {"R": "the words match", "semantic": "it means the same thing",
             "C": "it matches what is in front of us now",
             "H": "it sits where things were established",
             "P": f"it reads as {PERSISTENCE[candidate.persistence][0]}",
             "O": "nothing later replaced it"}
    return "; ".join(names[k] for k, v in ranked[:2] if v > 0.05) or "weak on every channel"
