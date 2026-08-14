# -*- coding: utf-8 -*-
"""A projection is not a summary, and these are the properties that make it so.

`design/context-compression.md` argues why; this checks it. The load-bearing one is
`test_every_omitted_turn_comes_back_byte_for_byte` — everything else here is a ratio,
and a ratio is what a summariser can also produce.
"""

from __future__ import annotations

import json

import pytest

from anla.errors import InvalidInput
from anla1.context import (
    LEVELS, Turn, expand, project, projection_manifest, read_jsonl, turn_entries,
)
from anla1.snapshot import append_snapshot, list_snapshots


def transcript(count: int = 40) -> bytes:
    """A synthetic transcript with the shape a real one has: a few big repeated tool
    results, some prose, and one line that will not parse."""
    lines = []
    for i in range(count):
        if i % 7 == 3:
            # The same tool result twice over, which is what a coding transcript is
            # mostly made of and where deduplication earns its keep.
            body = {"type": "user", "message": {"content": [
                {"type": "tool_result", "name": "Read", "content": "X" * 4000}]}}
        elif i == count // 2:
            lines.append(b"{this line is not json\n")
            continue
        else:
            body = {"type": "assistant" if i % 2 else "user",
                    "message": {"content": [{"type": "text", "text": f"turn {i} " + "y" * 200}]}}
        lines.append(json.dumps(body).encode("utf-8") + b"\n")
    return b"".join(lines)


def archive_of(turns) -> bytes:
    return append_snapshot(b"", files=turn_entries(turns), created_unix_ns=1,
                           archive_id=bytes(16))


def test_every_byte_of_the_transcript_becomes_a_turn():
    """Including the line that will not parse.

    A reader that silently dropped it would make the archive a claim about the
    transcript rather than a copy of it — and the whole point is that the record is
    the record.
    """
    data = transcript()
    turns = read_jsonl(data)
    assert b"".join(t.raw for t in turns) == data
    assert any(t.role == "unparsed" for t in turns), "the bad line must still be a turn"


def test_turn_paths_sort_in_conversation_order():
    """§5.2.1 orders objects by UTF-8 path bytes, and `turn-9` sorts after `turn-10`
    unless the index is zero-padded. The archive's own ordering is then the
    conversation's, which is why nothing has to store a sequence separately."""
    turns = read_jsonl(transcript(120))
    paths = [t.path for t in turns]
    assert paths == sorted(paths)


def test_every_omitted_turn_comes_back_byte_for_byte():
    """The claim. Everything else in this file is a ratio.

    A summariser can produce a short context too; what it cannot do is hand back
    what it dropped. This asks the archive for *every* omitted turn — not a sample —
    and compares against the bytes that went in.
    """
    turns = read_jsonl(transcript(60))
    archive = archive_of(turns)
    projection = project(turns, level="L0", budget_bytes=2_000)
    assert projection.omitted, "a tight budget must actually omit something"

    original = {t.path: t.raw for t in turns}
    restored = expand(archive, [entry["path"] for entry in projection.omitted])
    assert len(restored) == len(projection.omitted)
    for path, data in restored.items():
        assert data == original[path], path


def test_an_omission_is_addressable_or_the_projection_says_it_is_not():
    """`expandable` is computed, not asserted.

    A projection whose omissions carried no path would be a deletion, and this is
    the field that would have to say so. Constructed by hand because the real
    `project` cannot produce one — which is the point, and is why the field is
    computed from the entries rather than hardcoded to `True`.
    """
    projection = project(read_jsonl(transcript(20)), level="L0", budget_bytes=500)
    assert projection.expandable
    projection.omitted.append({"index": 999, "role": "ghost", "bytes": 0})
    assert not projection.expandable, "an entry with no path must flip this"


@pytest.mark.parametrize("lower,higher", list(zip(LEVELS, LEVELS[1:])))
def test_a_higher_level_never_preserves_less(lower, higher):
    """MNVP §6.2: `R(L0) ⊆ R(L1) ⊆ R(L2) ⊆ R(L3)`.

    Checked as a subset rather than trusted to the order of a tuple, because the
    inclusion is the property that makes the levels a *disclosure* rather than four
    unrelated renderings.
    """
    turns = read_jsonl(transcript(80))
    a = set(project(turns, level=lower, budget_bytes=4_000).preserved)
    b = set(project(turns, level=higher, budget_bytes=4_000).preserved)
    assert a <= b, f"{higher} dropped {len(a - b)} turns that {lower} kept"


def test_the_deepest_level_omits_nothing():
    """L3 is the audit level. If it left anything out there would be no level at
    which the projection and the record agree."""
    turns = read_jsonl(transcript(30))
    projection = project(turns, level="L3", budget_bytes=1)
    assert projection.omitted == []
    assert len(projection.preserved) == len(turns)


def test_identical_turns_are_stored_once():
    """The reason deduplication is the right mechanism for context: a transcript is
    largely a restatement of itself."""
    turns = read_jsonl(transcript(60))
    snapshot = list_snapshots(archive_of(turns))[-1]
    assert len(snapshot.manifest["chunks"]) < len(turns), (
        "no turn deduplicated against another, so this corpus cannot show the "
        "property the test is for")


def test_the_manifest_carries_the_omissions_not_a_count():
    """MNVP §6.3. A number satisfies none of what 原則四 asks a lower level to keep —
    an expansion mechanism, an omission hint, a link to the full value."""
    turns = read_jsonl(transcript(50))
    manifest = projection_manifest(project(turns, level="L0", budget_bytes=1_500))
    assert manifest["kind"] == "anla:context:projection:1"
    assert manifest["expandable"] is True
    assert isinstance(manifest["omitted"], list) and manifest["omitted"]
    for entry in manifest["omitted"]:
        assert entry["path"] and "hint" in entry and "bytes" in entry


def test_expanding_something_the_archive_does_not_hold_is_refused():
    turns = read_jsonl(transcript(10))
    with pytest.raises(InvalidInput, match="does not hold"):
        expand(archive_of(turns), ["turns/999999-nope.json"])


def test_an_unknown_level_is_refused_rather_than_defaulted():
    with pytest.raises(InvalidInput, match="level must be"):
        project([Turn(index=0, role="user", raw=b"{}")], level="L9")
