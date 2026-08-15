# -*- coding: utf-8 -*-
"""Relation edges — the properties that keep them facts rather than guesses.

`relations.py` claims two things the design document requires, and each is a
sentence until something can fail:

* **Derived, not guessed.** Every edge traces to something the record states. The
  test for this is not that edges appear — it is that `verify_edges` goes *red* when
  the graph and the record disagree, in each of the three ways they can: an edge
  missing, an edge nobody can explain, and an edge stored twice. The third is here
  because the first version of `verify_edges` compared sets and reported `identical`
  on a list holding 1,680 more edges than it expected.

* **Typed, not weighted.** Paper 02 §9: a scalarization is a task choice made after,
  never the structure. So no edge may carry a number, and `test_no_edge_carries_a_score`
  reads the emitted graph rather than the source, because a docstring promising it is
  not a check.

And one property that is easy to lose by accident: the edge set must not depend on
which segmentation scheme is loaded. If it did, the graph would describe the
segmenter rather than the record, and it is supposed to be the base the schemes are
compared over.
"""

from __future__ import annotations

import json
from collections import namedtuple

import pytest

from anla1.relations import (
    COMMON_PATH_LIMIT, DERIVED_KINDS, EDGE_KINDS, _normalise, derive_edges,
    edges_for_turn, neighbours, verify_edges,
)
from anla1.segment import build_index

Stored = namedtuple("Stored", "path raw")


def turn(index: int, role: str, uuid: str, parent: str | None = None,
         text: str = "", blocks: list | None = None) -> Stored:
    """One transcript line, shaped the way the real records are."""
    message: dict = {"role": role}
    message["content"] = blocks if blocks is not None else text
    record = {"type": role, "uuid": uuid, "parentUuid": parent, "message": message}
    return Stored(f"turns/{index:06d}-{role}.json",
                  json.dumps(record, ensure_ascii=False).encode("utf-8"))


@pytest.fixture
def conversation() -> list[Stored]:
    """A record containing exactly one edge of each derivable kind.

    Written by hand rather than sampled, so the expected count is arithmetic a
    reader can do — a fixture whose edge count is whatever the deriver produced
    would be the check comparing a quantity only to itself.
    """
    long = "padding that keeps every turn well clear of any length floor. " * 4
    return [
        turn(1, "user", "u1", None, f"please read src/alpha.py {long}"),
        turn(2, "assistant", "a1", "u1", blocks=[
            {"type": "text", "text": f"reading it now {long}"},
            {"type": "tool_use", "id": "call_1", "name": "Read",
             "input": {"file_path": "src/alpha.py"}}]),
        turn(3, "user", "u2", "a1", blocks=[
            {"type": "tool_result", "tool_use_id": "call_1",
             "content": f"contents of the file {long}"}]),
        turn(4, "assistant", "a2", "u2", f"src/alpha.py defines the thing {long}"),
    ]


# ---------------------------------------------------------------------------
# derived, not guessed
# ---------------------------------------------------------------------------

def test_each_derivable_kind_appears_with_the_count_the_fixture_implies(conversation):
    edges = derive_edges(conversation)
    counted = {kind: sum(1 for e in edges if e["kind"] == kind)
               for kind in DERIVED_KINDS}
    # three parent links, one tool pairing, and a three-turn chain over one path
    assert counted == {"replies-to": 3, "tool-result-of": 1, "mentions-path": 2}


def test_the_tool_edge_names_the_call_it_was_paired_by(conversation):
    edge, = [e for e in derive_edges(conversation) if e["kind"] == "tool-result-of"]
    assert edge["from"] == "turns/000003-user.json"
    assert edge["to"] == "turns/000002-assistant.json"
    assert edge["evidence"] == [{"tool_use_id": "call_1", "tool": "Read"}]


def test_an_unmatched_tool_result_yields_no_edge():
    """A result whose call is not in the record is not paired with a guess."""
    orphan = [turn(1, "user", "u1", None, blocks=[
        {"type": "tool_result", "tool_use_id": "call_missing", "content": "x" * 300}])]
    assert not [e for e in derive_edges(orphan) if e["kind"] == "tool-result-of"]


def test_a_parent_outside_the_record_yields_no_edge():
    """Truncated transcripts are ordinary; a dangling parent is not an edge."""
    orphan = [turn(1, "user", "u1", "gone-with-the-earlier-session", "text " * 60)]
    assert not derive_edges(orphan)


@pytest.mark.parametrize("damage,expected", [
    ("drop", "missing_total"),
    ("invent", "unexplained_total"),
    ("duplicate", "duplicate_keys"),
])
def test_verify_goes_red_for_the_reason_named(conversation, damage, expected):
    """Three ways a stored graph can disagree with its record, three red lights.

    Parametrised over the damage rather than written once, because a single
    catch-all assertion passes when the check fires for the wrong reason — and a
    defect low in the chain shielding the one you aimed at is how a suite ends up
    with checks nobody has watched fail.
    """
    edges = [dict(e) for e in derive_edges(conversation)]
    if damage == "drop":
        edges.pop()
    elif damage == "invent":
        edges.append({"kind": "replies-to", "from": "turns/000001-user.json",
                      "to": "turns/000004-assistant.json", "evidence": []})
    else:
        edges.append(dict(edges[0]))

    report = verify_edges(conversation, None, edges)
    assert report["identical"] is False
    assert report[expected] > 0
    # and only for that reason — otherwise the parametrisation proves nothing
    others = {"missing_total", "unexplained_total", "duplicate_keys"} - {expected}
    assert all(report[k] == 0 for k in others), report


def test_altered_evidence_is_caught_even_though_the_endpoints_match(conversation):
    """The endpoints are the easy part; the justification is what can be forged."""
    edges = [dict(e) for e in derive_edges(conversation)]
    victim = next(e for e in edges if e["kind"] == "mentions-path")
    victim["evidence"] = [{"path": "src/never-mentioned.py"}]
    report = verify_edges(conversation, None, edges)
    assert report["identical"] is False
    assert report["missing_total"] == report["unexplained_total"] == 1


def test_an_empty_graph_does_not_pass_by_matching_an_empty_expectation():
    """Two empty sets match, so `identical` requires the graph to be non-empty.

    Without this the check meant to catch a derivation that silently produced
    nothing would report success on exactly that case — vacuously true, and
    invisible to any drill, since a drill asks whether a check *fails*.
    """
    empty = verify_edges([], None, [])
    assert empty["vacuous"] is True
    assert empty["identical"] is False


def test_a_correct_graph_passes(conversation):
    """The control. Without it the red lights above could be a broken verifier."""
    report = verify_edges(conversation, None, derive_edges(conversation))
    assert report["identical"] is True
    assert report["vacuous"] is False


# ---------------------------------------------------------------------------
# typed, not weighted
# ---------------------------------------------------------------------------

def test_no_edge_carries_a_score(conversation):
    """§9: D_T ≠ ΔΦ. A weight here would repeat the collapse one level up.

    Reads the emitted edges rather than the source: the rule is about what ships.
    """
    for edge in derive_edges(conversation):
        assert set(edge) == {"kind", "from", "to", "evidence"}
        for piece in edge["evidence"]:
            assert not any(isinstance(v, (int, float)) and not isinstance(v, bool)
                           for v in piece.values()), edge


def test_two_turns_sharing_several_files_are_related_once_for_several_reasons():
    """One edge, a list of evidence — not a count of coincidences posing as strength."""
    long = "filler text to clear any floor. " * 12
    pair = [turn(1, "user", "u1", None, f"src/a.py and src/b.py and src/c.py {long}"),
            turn(2, "user", "u2", None, f"again src/a.py src/b.py src/c.py {long}")]
    edges = [e for e in derive_edges(pair) if e["kind"] == "mentions-path"]
    assert len(edges) == 1
    assert sorted(p["path"] for p in edges[0]["evidence"]) == [
        "src/a.py", "src/b.py", "src/c.py"]


def test_the_unbuildable_kinds_are_listed_with_a_reason_rather_than_dropped():
    """A list of only the easy cases reads as though the hard ones were never wanted."""
    for kind in ("supersedes", "supports", "contradicts"):
        assert EDGE_KINDS[kind].startswith("not derivable")
        assert kind not in DERIVED_KINDS
    for kind in ("same-turn", "next-in-turn", "next-turn"):
        assert EDGE_KINDS[kind].startswith("not stored")


def test_no_kind_outside_the_declared_set_is_ever_emitted(conversation):
    assert {e["kind"] for e in derive_edges(conversation)} <= set(DERIVED_KINDS)


# ---------------------------------------------------------------------------
# a fact about the record, not about the segmenter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["structural-v1", "sized-900-v1",
                                    "changepoint-v1", "whole-turn-v1"])
def test_the_graph_is_the_same_under_every_scheme(conversation, scheme):
    """Re-segmenting produces a new index family; it must not produce a new record.

    Passing the index at all is the risk this guards: the moment path extraction
    reads the index's segments instead of the whole turn, a scheme whose segments
    do not tile silently drops edges.
    """
    index = build_index([(t.path, t.raw) for t in conversation], scheme)
    assert derive_edges(conversation, index) == derive_edges(conversation, None)


def test_edges_survive_a_round_trip_through_the_index_sidecar(conversation):
    from anla1.segment import SegmentIndex

    index = build_index([(t.path, t.raw) for t in conversation], "changepoint-v1")
    index.edges = derive_edges(conversation)
    reloaded = SegmentIndex.of(json.loads(json.dumps(index.as_dict(),
                                                     ensure_ascii=False)))
    assert verify_edges(conversation, None, reloaded.edges)["identical"] is True


# ---------------------------------------------------------------------------
# path matching
# ---------------------------------------------------------------------------

def test_the_two_spellings_of_one_windows_path_are_the_same_file():
    """`D:\\Ai\\x.py` and `D:/Ai/x.py` must not be two files.

    A per-character separator swap turns the JSON-escaped spelling into `d://ai//x.py`
    and produces no edge at all — which looks exactly like two turns that genuinely
    have nothing in common, so nothing downstream would report it.
    """
    assert _normalise(r"D:\Ai\work\x.py") == _normalise("D:/Ai/work/x.py")
    assert _normalise(r"D:\\Ai\\work\\x.py") == "d:/ai/work/x.py"


@pytest.mark.parametrize("prose", ["and/or", "he/she", "TCP/IP", "24/7", "1/2"])
def test_prose_with_a_slash_is_not_a_path(prose):
    """A loose pattern fills the graph with edges nobody can check by eye."""
    long = "surrounding sentence that gives the line some length. " * 8
    pair = [turn(1, "user", "u1", None, f"{prose} {long}"),
            turn(2, "user", "u2", None, f"{prose} {long}")]
    assert not [e for e in derive_edges(pair) if e["kind"] == "mentions-path"]


@pytest.mark.parametrize("text,expected", [
    # the defect that made this table: allowing spaces in a component matched all
    # three of these as one 33-character "path", so the files produced no edge
    ("src/a.py and src/b.py and src/c.py", ["src/a.py", "src/b.py", "src/c.py"]),
    ("read src/a.py then open lib/b.py", ["src/a.py", "lib/b.py"]),
    ("compare a.py and b.py in src/x.py", ["src/x.py"]),
    # and the reason spaces are allowed at all — this repository's own location
    ("D:/Ai/work together/ANLA/site/build.py",
     ["ai/work together/anla/site/build.py"]),
    ("D:\\Ai\\work together\\ANLA\\site\\build.py",
     ["ai/work together/anla/site/build.py"]),
    ("D:\\\\Ai\\\\work together\\\\ANLA\\\\site\\\\build.py",
     ["ai/work together/anla/site/build.py"]),
    ("D:/Ai/work together/my notes/x.md", ["ai/work together/my notes/x.md"]),
    # dots inside a name and inside a directory
    ("docs/theory/ACCR_MCP_Contracts_v0.1.md",
     ["docs/theory/accr_mcp_contracts_v0.1.md"]),
    (".github/workflows/ci.yml", [".github/workflows/ci.yml"]),
    ("see python/anla1/relations.py now", ["python/anla1/relations.py"]),
    # a spaced filename is missed rather than half-matched into `docs/my`
    ("open docs/my file.md now", []),
])
def test_what_counts_as_a_path(text, expected):
    """The extractor, table-driven, because each row here was once wrong.

    Three separate defects came out of this: the greedy-space merge above, two
    spellings of one Windows path normalising to different keys, and a variant that
    truncated `v0.1.md` to `v0.1`. None of them raised anything — a missing edge
    looks exactly like two turns with nothing in common.
    """
    from anla1.relations import _PATH
    assert sorted(set(_normalise(m) for m in _PATH.findall(text))) == sorted(expected)


def test_a_path_named_everywhere_is_vocabulary_and_is_dropped():
    """Above the cap a shared mention says nothing about which turns belong together."""
    long = "body text of the turn, long enough to matter. " * 6
    crowd = [turn(i, "user", f"u{i}", None, f"see site/build.py {long}")
             for i in range(COMMON_PATH_LIMIT + 2)]
    assert not [e for e in derive_edges(crowd) if e["kind"] == "mentions-path"]

    # and directly below it, the same turns are related — so the test is measuring
    # the threshold rather than some other reason the edges never appeared
    assert [e for e in derive_edges(crowd[:COMMON_PATH_LIMIT])
            if e["kind"] == "mentions-path"]


def test_include_paths_false_leaves_the_exact_kinds_untouched(conversation):
    exact = [e for e in derive_edges(conversation, include_paths=False)]
    assert {e["kind"] for e in exact} == {"replies-to", "tool-result-of"}
    assert exact == [e for e in derive_edges(conversation)
                     if e["kind"] != "mentions-path"]


# ---------------------------------------------------------------------------
# walking
# ---------------------------------------------------------------------------

def test_neighbours_does_not_rank(conversation):
    """Which neighbour matters is the caller's task question, per §9."""
    edges = derive_edges(conversation)
    found = neighbours(edges, "turns/000002-assistant.json")
    assert "turns/000001-user.json" in found
    assert "turns/000003-user.json" in found
    assert found == list(dict.fromkeys(found))          # no repeats, no ordering claim


def test_neighbours_filters_by_kind(conversation):
    edges = derive_edges(conversation)
    only = neighbours(edges, "turns/000003-user.json", kinds=["tool-result-of"])
    assert only == ["turns/000002-assistant.json"]


def test_edges_for_turn_finds_both_directions(conversation):
    edges = derive_edges(conversation)
    touching = edges_for_turn(edges, "turns/000002-assistant.json")
    assert any(e["from"] == "turns/000002-assistant.json" for e in touching)
    assert any(e["to"] == "turns/000002-assistant.json" for e in touching)
