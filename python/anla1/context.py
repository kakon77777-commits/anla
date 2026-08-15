# -*- coding: utf-8 -*-
"""A context store: the authoritative record, and projections of it.

This is the half of `design/context-compression.md` that Neo asked for first — the
automatic capture and compression of an AI's own context. The other half,
reconstruction and 顯影, is DRVS's and comes later.

The operation everything here exists to distinguish, from MNVP 原則四:

    永久刪除與可展開壓縮是不同操作。
    Permanent deletion and expandable compression are different operations.

Summarising a context is the first. This module does the second: the whole record
goes into an ANLA archive, and what a model reads is a *projection* of it that says
what it left out and can hand any of it back byte for byte.

Three decisions, and each earns its place:

**A turn is an object.** Not a byte range in a log. Each one gets its own path, its
own `object_id` and its own chunk list, so `extract` can produce exactly one turn
without reading the rest — which is what makes an omission expandable, and it needed
no new format work. MS3E's framing is what made this obvious: a transcript is linear
media you can only seek along, and the fix is to compile it into addressable state.

**Identical content is stored once.** A transcript re-reads the same file, repeats
the same tool result, restates the same reasoning. Content-defined chunking across
turns is exactly the workload deduplication exists for, and `bench/context_growth.py`
measures what it saves: the cost of a checkpoint stays flat while recompressing the
whole context grows with it.

**A projection declares its omissions.** `{"preserved": …, "omitted": …,
"expandable": true}` — MNVP §6.3, which is field-for-field the fidelity report this
package already had. A projection that cannot say what it dropped is a summary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from anla.errors import InvalidInput

from .snapshot import SourceEntry, extract_snapshot, list_snapshots

__all__ = [
    "Turn", "LEVELS", "read_jsonl", "turn_entries", "Projection", "project",
    "expand", "projection_manifest", "newest_sessions",
]


def newest_sessions(root: str = "") -> list:
    """Session transcripts on this machine, newest first.

    Here rather than in the MCP server because the command line needs the same
    answer, and "the newest session" defined twice is two definitions that agree
    until one of them is edited. Returns paths; deciding what to do with them —
    including whether taking the newest one is appropriate — is the caller's.
    """
    import pathlib
    where = (pathlib.Path(root).expanduser() if root
             else pathlib.Path.home() / ".claude/projects")
    if not where.exists():
        return []
    return sorted(where.rglob("*.jsonl"), key=lambda f: -f.stat().st_mtime)

#: MNVP §6.1's four levels, named for context rather than for numbers.
#:
#: L0 core        — the minimum this task needs
#: L1 comparison  — with the neighbours that give it scale
#: L2 explanation — with why, and where it came from
#: L3 audit       — the verbatim record and its provenance
#:
#: `R(L0) ⊆ R(L1) ⊆ R(L2) ⊆ R(L3)`: a higher level never preserves *less*. The test
#: suite asserts that rather than trusting the ordering of a tuple.
LEVELS = ("L0", "L1", "L2", "L3")


@dataclass(frozen=True)
class Turn:
    """One record of a context, as it was.

    `raw` is the bytes the transcript actually held. Everything else is derived and
    may be wrong without costing anything, because `raw` is what gets stored and
    what comes back — the derived fields steer the projection, they are not the
    record.
    """

    index: int
    role: str
    raw: bytes
    #: Set when this turn's content is a tool result, which is the bulk of a coding
    #: transcript and the first thing a projection should be willing to drop.
    tool: str | None = None
    text: str = ""

    @property
    def path(self) -> str:
        """Where this turn lives in the archive.

        Zero-padded so the archive's own path ordering is the conversation's
        ordering — objects are sorted by UTF-8 path bytes (§5.2.1), and `turn-9`
        sorts after `turn-10` unless the width is fixed.
        """
        return f"turns/{self.index:06d}-{self.role}.json"


def read_jsonl(data: bytes) -> list[Turn]:
    """Parse a JSONL transcript into turns, keeping every original byte.

    A line that will not parse still becomes a turn. It is part of the record, and a
    reader that silently dropped it would make the archive a claim about the
    transcript rather than a copy of it.
    """
    turns: list[Turn] = []
    for index, line in enumerate(data.splitlines(keepends=True)):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            turns.append(Turn(index=index, role="unparsed", raw=line))
            continue
        turns.append(Turn(
            index=index,
            role=str(parsed.get("type") or parsed.get("role") or "unknown"),
            raw=line,
            tool=_tool_name(parsed),
            text=_text_of(parsed),
        ))
    return turns


def _tool_name(record: dict) -> str | None:
    message = record.get("message")
    blocks = (message or {}).get("content") if isinstance(message, dict) else None
    for block in blocks or []:
        if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
            return str(block.get("name") or block.get("tool_use_id") or "tool")
    return None


def _text_of(record: dict) -> str:
    """A plain-text rendering, for the projection to work from.

    Best effort on purpose: this steers what a projection shows, and the archive
    still holds `raw`, so being wrong here costs a worse summary and never a byte.
    """
    message = record.get("message")
    if isinstance(message, str):
        return message
    content = (message or {}).get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    pieces = []
    for block in content or []:
        if isinstance(block, dict):
            if isinstance(block.get("text"), str):
                pieces.append(block["text"])
            elif block.get("type") == "tool_result":
                inner = block.get("content")
                pieces.append(inner if isinstance(inner, str) else json.dumps(inner)[:400])
    return "\n".join(pieces)


def turn_entries(turns: Iterable[Turn]) -> list[SourceEntry]:
    """Turns as objects the writer can pack, one object each."""
    return [SourceEntry.of(turn.path, turn.raw) for turn in turns]


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------

@dataclass
class Projection:
    """What a model reads, and the declaration of what it does not.

    `omitted` is not a count. It names every turn that was left out and how to get
    it back, because MNVP 原則四 requires a lower level to keep *an expansion
    mechanism, an omission hint, a link to the full value, and machine-readable
    underlying data* — and a number satisfies none of those.
    """

    level: str
    text: str
    preserved: list[str] = field(default_factory=list)
    omitted: list[dict] = field(default_factory=list)
    bytes_shown: int = 0
    bytes_total: int = 0

    @property
    def expandable(self) -> bool:
        """Every omission carries the path that restores it. Always true here, and
        stated rather than assumed: a projection whose omissions were not
        addressable would be a deletion, and this is the field that would say so."""
        return all("path" in entry for entry in self.omitted)

    def as_manifest(self) -> dict:
        return {
            "level": self.level,
            "preserved": self.preserved,
            "omitted": self.omitted,
            "expandable": self.expandable,
            "bytes_shown": self.bytes_shown,
            "bytes_total": self.bytes_total,
            "share_shown": (round(self.bytes_shown / self.bytes_total, 4)
                            if self.bytes_total else None),
        }


def projection_manifest(projection: Projection) -> dict:
    """MNVP §6.3's omission declaration, for the archive's auxiliary plane.

    The *auxiliary* plane, deliberately. A projection is disposable and regenerable
    from the record; `D(P, I) = D(P, ∅)` says dropping it changes nothing a decoder
    extracts. The archive's own fidelity report — what the *writer* could not keep —
    stays in the preservation plane where `strip` cannot reach it. Those are
    different facts and this package has already been bitten by conflating them.
    """
    return {"kind": "anla:context:projection:1", **projection.as_manifest()}


def project(turns: Sequence[Turn], level: str = "L1", budget_bytes: int = 32_000,
            keep_recent: int = 6) -> Projection:
    """Choose what to show, and record what that leaves out.

    The policy here is deliberately dull — newest first, tool results dropped before
    prose, everything that does not fit named in `omitted`. It is a *placeholder for
    a model*, which is the whole architecture: an AI proposes the projection, and a
    deterministic mechanism produces and reverses it. Neo's UTF-8X states the same
    rule for representations — 「AI 負責策略生成…AI 不參與解碼」 — and CAIR states
    why it has to be a proposal: an AI edit is a candidate, never a silent commit.

    So a better policy replaces this function and changes nothing else. That is the
    point of it being this dull.
    """
    if level not in LEVELS:
        raise InvalidInput(f"level must be one of {LEVELS}", got=level)
    turns = list(turns)
    total = sum(len(turn.raw) for turn in turns)

    # Ranked by what a lower level is willing to lose first. Recency wins, then
    # prose over tool output — a tool result is usually the largest thing in a
    # coding transcript and the most reconstructible.
    order = sorted(
        range(len(turns)),
        key=lambda i: (
            0 if i >= len(turns) - keep_recent else 1,
            1 if turns[i].tool else 0,
            -i,
        ),
    )
    allowance = {"L0": 0.25, "L1": 1.0, "L2": 2.5, "L3": float("inf")}[level]
    room = budget_bytes * allowance

    shown: set[int] = set()
    used = 0
    for i in order:
        piece = _render(turns[i], level)
        if used + len(piece) > room and i < len(turns) - keep_recent:
            continue
        shown.add(i)
        used += len(piece)

    body, preserved, omitted = [], [], []
    for i, turn in enumerate(turns):
        if i in shown:
            body.append(_render(turn, level))
            preserved.append(turn.path)
        else:
            omitted.append({
                "path": turn.path,
                "index": turn.index,
                "role": turn.role,
                "bytes": len(turn.raw),
                "tool": turn.tool,
                # A hint, not a summary. Enough to decide whether to expand it,
                # short enough that the hints do not become the thing being
                # compressed.
                "hint": (turn.text or "").strip().replace("\n", " ")[:120],
            })

    return Projection(level=level, text="\n".join(body), preserved=preserved,
                      omitted=omitted, bytes_shown=used, bytes_total=total)


def _render(turn: Turn, level: str) -> str:
    """One turn, at one level. Higher levels never show less."""
    text = (turn.text or "").strip()
    label = f"[{turn.index} {turn.role}{'/' + turn.tool if turn.tool else ''}]"
    if level == "L0":
        return f"{label} {text[:200]}"
    if level == "L1":
        return f"{label} {text[:1000]}"
    if level == "L2":
        return f"{label} {text[:6000]}"
    return f"{label} {turn.raw.decode('utf-8', 'replace')}"


def expand(archive: bytes, paths: Sequence[str], snapshot: Any | None = None
           ) -> dict[str, bytes]:
    """Hand back omitted turns, byte for byte.

    The test that says this is compression rather than deletion. It reads whole
    objects out of the archive, so what comes back is what went in — not a
    reconstruction, and nothing that requires a model.
    """
    chosen = snapshot or list_snapshots(archive)[-1]
    wanted = set(paths)
    missing = wanted - {o["path"] for o in chosen.manifest["objects"]}
    if missing:
        raise InvalidInput("the archive does not hold these turns",
                           paths=sorted(missing)[:10])
    return {path: data for path, data in extract_snapshot(archive, chosen).items()
            if path in wanted}
