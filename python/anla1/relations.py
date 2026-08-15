# -*- coding: utf-8 -*-
"""Relation edges over a segment index — the context/index base, not phase.

`SegmentIndex.edges` has been reserved and empty since the index was written. This
fills it, and the theory that says what may go in it is in
`design/phase-and-relations.md`: under EveMissLab's Phase Canon these are the
context/index base $I_{\\mathrm{sem}}$ — the graph a transport would later be
defined *over* — and building them claims nothing about phase. No function in this
module may acquire that word.

Two rules the papers impose, both load-bearing here:

**Typed, not weighted.** Paper 02 §9 is explicit that a scalarisation is a task
choice made afterwards and never the structure itself, $D_T \\neq \\Delta\\Phi$. So
an edge carries a *kind* and the evidence that produced it. It does not carry a
score. ANLA's cosine already collapses a relation to one number in one place; doing
it again at the graph level would lose exactly what the graph is for.

**Derived, not guessed.** Every edge here comes from something the record states
outright — a message's parent id, a tool-call id, a literal path string. Nothing is
inferred by a model. That is what makes an edge checkable: `verify_edges` re-derives
the whole set and compares, so a stored graph that has drifted from its record fails
rather than being believed.

## What is deliberately not stored

Three of the six kinds originally reserved turn out to be **implied by the segment
tuple**, and storing them would be duplication rather than information:

* `same-turn` — two segments share `source_turn`; that is already in both of them.
* `next-in-turn` — consecutive `ordinal` within one turn.
* `next-turn` — the paths are zero-padded, so archive order *is* conversation order.

Emitting those would roughly double the index to say what a reader can compute with
a comparison. An edge earns its bytes only if it is not a function of the tuple.

And three cannot be derived at all:

* `supersedes`, `supports`, `contradicts` — these are judgements about content, not
  facts the record states. A model could propose them; the record cannot yield them.
  They stay unpopulated, and `EDGE_KINDS` says why, rather than being quietly
  dropped from the list.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Sequence

from .segment import (SEGMENT_SCHEMA_VERSION, PROJECTION_VERSION, Segment,
                      digest_of, project_segment)

__all__ = ["EDGE_KINDS", "DERIVED_KINDS", "COMMON_PATH_LIMIT",
           "derive_edges", "verify_edges", "edges_for_turn", "neighbours"]

#: Every kind the design names, with what it would take to produce one. Kept whole
#: rather than trimmed to what is implemented, because a list of only the easy cases
#: reads as though the hard ones were never wanted.
EDGE_KINDS: dict[str, str] = {
    "replies-to": "derived — the record states parentUuid",
    "tool-result-of": "derived — tool_use.id matches tool_result.tool_use_id",
    "mentions-path": "derived — the same literal path string appears in both",
    "same-turn": "not stored — implied by source_turn",
    "next-in-turn": "not stored — implied by consecutive ordinal",
    "next-turn": "not stored — implied by the zero-padded path order",
    "supersedes": "not derivable — a judgement about content, not a stated fact",
    "supports": "not derivable — a judgement about content, not a stated fact",
    "contradicts": "not derivable — a judgement about content, not a stated fact",
}

DERIVED_KINDS = tuple(k for k, v in EDGE_KINDS.items() if v.startswith("derived"))

#: A path in this corpus, conservatively: two or more components, a separator, and an
#: extension — so `src/foo.py` matches while `and/or`, `he/she`, `TCP/IP` and `24/7`
#: do not. A loose pattern would fill the graph with edges nobody can check by eye,
#: which is the same failure as an unchecked score.
#:
#: The awkward middle branch exists because this repository lives under
#: `D:/Ai/work together/ANLA`, so an interior component may contain a space — and
#: allowing spaces naively is worse than banning them: `src/a.py and src/b.py` then
#: matches *once*, as a single 33-character "path", so the two real files it names
#: produce no edge at all. What separates a directory name from prose sitting between
#: two paths is the dot: `work together` has none, `a.py and` does. So a spaced
#: component's words are dotless, and every other component is a plain one.
#:
#: A file whose own *name* contains a space is not matched. Missing it is the right
#: failure — the alternative is emitting `docs/my` for `docs/my file.md`.
_PATH = re.compile(
    r"[A-Za-z0-9_.\-]+"
    r"(?:[/\\]+(?:[A-Za-z0-9_\-]+(?: [A-Za-z0-9_\-]+)+|[A-Za-z0-9_.\-]+))*"
    r"[/\\]+[A-Za-z0-9_.\-]+\.[A-Za-z0-9]{1,6}")

#: Paths named in more turns than this are vocabulary rather than reference. On the
#: pinned corpus 22 paths exceed it — `site/build.py` appears in 128 turns — and
#: those are the files the whole session was about, so a shared mention of one says
#: nothing about which two turns belong together.
#:
#: Not a size control. The mention structure below is a *spanning chain*, so n turns
#: cost n−1 edges and the cap saves 1,285 of roughly 10,400: twelve per cent, for a
#: reason that is about signal. A clique would be the size argument, and this is not
#: one.
COMMON_PATH_LIMIT = 40


def _normalise(path: str) -> str:
    """One spelling per file.

    Separator *runs* collapse, not single separators: the same path reaches this
    function as `D:\\Ai\\x.py` from a JSON-escaped source and `D:/Ai/x.py` from
    projected text, and a naive per-character swap turns the first into `d://ai//x.py`
    — so the two spellings of one file would produce no edge at all. That is the
    quiet kind of failure, since a missing edge looks exactly like two turns that
    genuinely have nothing in common.
    """
    trimmed = re.sub(r"[/\\]+", "/", path).strip()
    # Asymmetric on purpose. A trailing dot is the sentence ending; a leading one is
    # part of the name, and stripping both turned `.github/workflows/ci.yml` into a
    # different file from itself.
    return trimmed.lstrip("(（\"'").rstrip(".,;:)）\"'").lower()


def _turn_records(turns: Sequence) -> dict[str, dict]:
    """One parsed JSON record per turn path, for the fields edges come from."""
    out: dict[str, dict] = {}
    for turn in turns:
        try:
            out[turn.path] = json.loads(turn.raw.decode("utf-8", "replace"))
        except (ValueError, AttributeError):
            continue
    return out


def _blocks(record: dict) -> list[dict]:
    content = (record.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _turn_text(turn) -> str:
    """The Semantic State layer for a whole turn — projected, not raw.

    A whole-turn synthetic segment rather than the index's own segments, so the
    result does not depend on which scheme is loaded. An edge derived here is a fact
    about the record; if re-segmenting changed the edge set, it would instead be a
    fact about the segmenter, and §33's lineage branching would apply to a graph
    that is supposed to be the base the schemes are compared *over*.
    """
    whole = Segment(
        segment_id=f"{turn.path}#whole", source_turn=turn.path,
        source_digest=digest_of(turn.raw), scheme_id="whole-turn-v1",
        scheme_version=SEGMENT_SCHEMA_VERSION, ranges=((0, len(turn.raw)),),
        kind="turn", ordinal=0, projection_version=PROJECTION_VERSION)
    return project_segment(whole, turn.raw)


def derive_edges(turns: Sequence, index=None, *, include_paths: bool = True) -> list[dict]:
    """Every edge the record states outright, at turn granularity.

    Turn granularity rather than segment: `parentUuid` and `tool_use_id` are facts
    about messages, and attaching them to one arbitrary segment of a turn would
    invent a precision the record does not have. A caller that wants segments walks
    from the turn, which `edges_for_turn` does.

    At most one edge per `(kind, from, to)`. Two turns naming three files in common
    are related once, for three reasons — so `evidence` is a list. The alternative,
    three parallel edges, is a count of coincidences dressed as structure, and a
    consumer that summed them would have reinvented the weight §9 refuses.
    """
    records = _turn_records(turns)
    by_uuid = {r.get("uuid"): path for path, r in records.items() if r.get("uuid")}
    merged: dict[tuple[str, str, str], list[dict]] = {}

    def add(kind: str, source: str, target: str, evidence: dict) -> None:
        bucket = merged.setdefault((kind, source, target), [])
        if evidence not in bucket:
            bucket.append(evidence)

    # 1. the conversation DAG, exactly as the record states it
    for path, record in records.items():
        parent = record.get("parentUuid")
        if parent and parent in by_uuid and by_uuid[parent] != path:
            add("replies-to", path, by_uuid[parent], {"parentUuid": parent})

    # 2. tool calls and their results, paired by the id the record carries
    call_of: dict[str, str] = {}
    for path, record in records.items():
        for block in _blocks(record):
            if block.get("type") == "tool_use" and block.get("id"):
                call_of[block["id"]] = path
    for path, record in records.items():
        for block in _blocks(record):
            if block.get("type") != "tool_result":
                continue
            call = call_of.get(block.get("tool_use_id"))
            if call and call != path:
                add("tool-result-of", path, call,
                    {"tool_use_id": block["tool_use_id"],
                     "tool": _tool_name(records[call], block["tool_use_id"])})

    # 3. the same file named in two turns
    if include_paths:
        mentions: dict[str, set[str]] = {}
        for turn in turns:
            if turn.path not in records:
                continue
            for found in set(_normalise(m) for m in _PATH.findall(_turn_text(turn))):
                mentions.setdefault(found, set()).add(turn.path)
        # A spanning chain in conversation order, not the full symmetric relation.
        # Every turn naming a file stays reachable from every other, at linear cost —
        # but one hop reaches only the chain's neighbours, so a caller wanting all
        # mentioners of a file must walk the component rather than read a degree.
        for named, holders in sorted(mentions.items()):
            if not 2 <= len(holders) <= COMMON_PATH_LIMIT:
                continue
            ordered = sorted(holders)
            for earlier, later in zip(ordered, ordered[1:]):
                add("mentions-path", later, earlier, {"path": named})

    return [{"kind": k, "from": f, "to": t, "evidence": ev}
            for (k, f, t), ev in sorted(merged.items())]


def _tool_name(record: dict, call_id: str) -> str:
    for block in _blocks(record):
        if block.get("type") == "tool_use" and block.get("id") == call_id:
            return str(block.get("name") or "")
    return ""


def verify_edges(turns: Sequence, index=None, stored: Iterable[dict] = ()) -> dict:
    """Re-derive the graph and compare it with what was stored.

    Compares whole edges, evidence included, and separately counts duplicate keys.
    An earlier version compared `(kind, from, to)` as a *set*, which reported
    `identical` on a list holding 1,680 more edges than it expected: a set cannot see
    multiplicity, so the one defect the comparison was most likely to face was the
    one it could not detect.

    `identical` also requires the graph to be non-empty. Two empty sets match, so a
    derivation that silently produced nothing would otherwise pass the check meant to
    catch it — and a check that cannot fail is invisible to a drill.
    """
    expected = derive_edges(turns, index)
    key = lambda e: (e["kind"], e["from"], e["to"])                       # noqa: E731
    whole = lambda e: (*key(e), json.dumps(e.get("evidence"), sort_keys=True,
                                           ensure_ascii=False))           # noqa: E731
    stored = list(stored)
    mine, theirs = {whole(e) for e in expected}, {whole(e) for e in stored}
    missing, extra = sorted(mine - theirs), sorted(theirs - mine)
    duplicates = len(stored) - len({key(e) for e in stored})
    show = lambda ks: [dict(zip(("kind", "from", "to"), k)) for k in ks[:10]]  # noqa: E731
    return {
        "edges_expected": len(expected), "edges_stored": len(stored),
        "duplicate_keys": duplicates,
        "identical": bool(expected) and not missing and not extra and not duplicates,
        "vacuous": not expected,
        "missing": show(missing), "unexplained": show(extra),
        "missing_total": len(missing), "unexplained_total": len(extra),
    }


def edges_for_turn(edges: Sequence[dict], path: str) -> list[dict]:
    return [e for e in edges if e["from"] == path or e["to"] == path]


def neighbours(edges: Sequence[dict], path: str, kinds: Sequence[str] = ()) -> list[str]:
    """Turns one hop away, in the order the edges were derived.

    No ranking. Which neighbour matters is the caller's task question, and deciding
    it here would be the scalarisation the design document refuses.
    """
    wanted = set(kinds) if kinds else None
    out: list[str] = []
    for edge in edges:
        if wanted and edge["kind"] not in wanted:
            continue
        other = (edge["to"] if edge["from"] == path
                 else edge["from"] if edge["to"] == path else None)
        if other and other not in out:
            out.append(other)
    return out
