# -*- coding: utf-8 -*-
"""The resonant memory domain — Neo's 符號記憶判定耦合系列, papers 05–07.

What is being checked is that retrieval is *relational* rather than ordered, that
time enters through an item's own persistence class rather than a sort, and that
the channels which are missing say so. The last one matters most: this stands in
for semantic vectors and phase, and a stand-in that cannot be told apart from the
real thing is worse than none.
"""

from __future__ import annotations

import pytest

from anla1.resonance import (
    CHANNELS, Candidate, classify_persistence, resonant_domain,
)


def history(count: int = 60) -> list[Candidate]:
    """A shared history where the thing worth finding sits early, not late."""
    items = []
    for i in range(count):
        if i == 3:
            text = "the gear table is derived from sha-256 of the profile name"
        elif i == count - 2:
            text = "as noted the gear table came up again in passing"
        else:
            text = f"unrelated turn {i} about something else entirely"
        items.append(Candidate(key=f"turns/{i:06d}.json", text=text,
                               position=i, total=count))
    return items


def test_the_domain_is_a_small_subset_of_the_history():
    """Paper 05 §3.3: 𝓔 is normally a very small subset of 𝔐. A retriever that
    returns most of the history has not decided anything."""
    domain, report = resonant_domain(history(), query="gear table derived")
    assert 0 < len(domain) < 10
    assert report["share_of_history"] < 0.2


def test_the_earliest_statement_outranks_the_later_mention():
    """The defect this module replaced, as a property.

    An order-based retriever returns the most recent echo of a thing. Ψ is asked
    where it was *established*, and the answer here is turn 3 rather than turn 58 —
    not because earlier is better, but because content relevance and position in
    the shared history are terms and recency is not one.
    """
    domain, _ = resonant_domain(history(), query="gear table derived from sha-256")
    assert domain, "nothing cleared the threshold"
    assert domain[0].key == "turns/000003.json", [d.key for d in domain[:3]]


def test_nothing_is_ranked_by_time():
    """Reversing the conversation must not reorder the domain.

    The strongest available statement of 「不用執著順序」: if position in the
    sequence were doing the ranking, this would fail.
    """
    forward = history()
    backward = [Candidate(key=c.key, text=c.text, position=len(forward) - 1 - c.position,
                          total=c.total) for c in forward]
    a, _ = resonant_domain(forward, query="gear table derived")
    b, _ = resonant_domain(backward, query="gear table derived")
    assert {r.key for r in a} == {r.key for r in b}


@pytest.mark.parametrize("text,expected", [
    ("we always do it this way", "P"),
    ("just for now, quickly", "S"),
    ("packing the corpus this week", "C"),
    ("這是標準做法", "P"),
    ("先這樣", "S"),
])
def test_a_memory_carries_its_own_persistence_class(text, expected):
    """Paper 06 §1.2. Recency distortion is w(m|t) failing to match
    τ_persistence(m), so the class has to exist before the weight can match it."""
    assert classify_persistence(text) == expected


def test_an_instantaneous_state_decays_and_a_method_does_not():
    """The paper's actual claim, as an inequality.

    Same age, same words: the momentary note fades and the standing rule does not.
    A single sort by time cannot express this, which is why there is not one.
    """
    old = 20 * 86_400
    momentary = Candidate(key="a", text="tired today, keep it short", position=0,
                          total=2, age_seconds=old, persistence="S")
    standing = Candidate(key="b", text="always keep it short", position=1,
                         total=2, age_seconds=old, persistence="P")
    domain, _ = resonant_domain([momentary, standing], query="keep it short",
                                threshold=0.0)
    scores = {r.key: r.terms["P"] for r in domain}
    assert scores["b"] > scores["a"]


def test_something_superseded_leaves_the_present_without_leaving_the_store():
    """「還在記憶庫裡」不等於「仍在共同現在」, as a test rather than a quotation."""
    items = history(20)
    items[3] = Candidate(key=items[3].key, text=items[3].text, position=3, total=20,
                         superseded_by="turns/000019.json")
    domain, _ = resonant_domain(items, query="gear table derived", threshold=0.0)
    replaced = next(r for r in domain if r.key == "turns/000003.json")
    assert replaced.terms["O"] == 0.0
    assert "superseded" in replaced.why


def test_the_missing_channels_are_named_rather_than_approximated():
    """The honest part. Semantic vectors and phase are the mechanism this stands in
    for; word overlap wearing their name would make the stand-in undetectable."""
    _, report = resonant_domain(history(), query="gear")
    assert "semantic" in report["absent"] and "phase" in report["absent"]
    assert "ABSENT" in CHANNELS["phase"]


def test_every_member_says_which_terms_put_it_there():
    """DRVS's rule: never an opaque number. A caller has to be able to see that a
    retrieval was carried by weak channels."""
    domain, _ = resonant_domain(history(), query="gear table derived")
    for member in domain:
        assert member.terms and member.why
        assert set(member.terms) >= {"R", "C", "H", "P", "O"}


def test_supplied_vectors_turn_the_semantic_channel_on():
    """Nothing here computes embeddings — they arrive from whatever can. When they
    do, the channel reports itself present and stops being in the absent list."""
    items = history(20)
    with_vectors = [Candidate(key=c.key, text=c.text, position=c.position,
                              total=c.total, vector=[float(len(c.text)), 1.0, 0.5])
                    for c in items]
    _, without = resonant_domain(items, query="gear")
    _, with_them = resonant_domain(with_vectors, query="gear",
                                   query_vector=[40.0, 1.0, 0.5])
    assert "semantic" in without["absent"]
    assert "semantic" not in with_them["absent"]
    assert with_them["embedded"] == len(items)


def test_vectors_of_different_widths_are_refused():
    """ICNS: a comparison must be allowed to fail rather than be rounded to an
    answer. Two widths did not come from one model, and quietly comparing the
    overlapping prefix would be a confident number from an incoherent comparison."""
    items = [Candidate(key="a", text="hello", position=0, total=1, vector=[1.0, 2.0])]
    with pytest.raises(ValueError, match="different width"):
        resonant_domain(items, query="hello", query_vector=[1.0, 2.0, 3.0])


def test_the_relational_boundary_is_in_the_output():
    """Paper 07. The boundary belongs where it will be read, not in a comment."""
    _, report = resonant_domain(history(), query="gear")
    assert "Recall" in report["boundary"] and "Care" in report["boundary"]
