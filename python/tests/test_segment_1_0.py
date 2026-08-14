# -*- coding: utf-8 -*-
"""Segments are indices — the properties that make that claim checkable.

The design says a segment is a perspective on a preserved turn rather than a new
preserved fragment. That is a sentence until something can fail. Three things can:

* **Reachability.** The ranges of one scheme must tile the turn exactly — no gaps,
  no overlaps. A byte no segment covers is a memory that cannot be retrieved no
  matter how good the embedder is, and nothing downstream would report it missing;
  the retrieval benchmark would simply score slightly worse and look like a tuning
  problem. This is the invisible failure, so it is the first test.
* **Checkability.** `π_σ` must refuse to read offsets computed against different
  bytes. Reading them anyway returns plausible text from the wrong place.
* **Independence.** Changing the scheme must not change the record, and the ids
  must be the same on a rebuild — otherwise an index is a migration.
"""

from __future__ import annotations

import pytest

from anla1.segment import (
    PROJECTION_VERSION, SCHEMES, Segment, SegmentIndex, build_index, digest_of,
    project_segment,
)

TURN = (
    b'{"role":"user","content":"# Heading one\\n\\nA first paragraph that is long '
    b'enough to clear the two hundred byte floor without being padded, because a '
    b'floor that everything trips over measures the floor.\\n\\n## Heading two\\n\\n'
    b'A second paragraph, about a different subject entirely: rolling hashes, gear '
    b'tables and the reason a constant table is derived rather than copied.\\n\\n'
    b'```python\\nassert derived == copied\\n```\\n\\n- \xe4\xb8\xad\xe6\x96\x87 '
    b'\xe4\xb9\x9f\xe8\xa6\x81\xe8\xa2\xab\xe6\xb8\xac\xe8\xa9\xa6\xef\xbc\x8c'
    b'\xe5\x9b\xa0\xe7\x82\ba\xe5\xad\x97\xe5\x85\x83\xe5\x81\x8f\xe7\xa7\xbb'
    b'\xe8\xb7\x9f\xe7\xb5\x84\xe4\xbd\x8d\xe5\x85\x83\xe7\xb5\x84\xe5\x81\x8f'
    b'\xe7\xa7\xbb\xe4\xb8\x8d\xe4\xb8\x80\xe6\xa8\xa3\xe3\x80\x82"}'
)


def tiling_fault(segments, total: int) -> str | None:
    """Say what is wrong with a tiling, or nothing. Used as an assertion *and*
    drilled below against a deliberately broken tiling, because a checker that
    cannot say no has not said yes."""
    spans = sorted(r for s in segments for r in s.ranges)
    if not spans:
        return "no segments at all"
    if spans[0][0] != 0:
        return f"starts at {spans[0][0]}, so the first {spans[0][0]} bytes are lost"
    if spans[-1][1] != total:
        return f"ends at {spans[-1][1]} of {total}, so the tail is unreachable"
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if start > end:
            return f"gap at {end}:{start} — those bytes are in no segment"
        if start < end:
            return f"overlap at {start}:{end} — those bytes are counted twice"
    return None


def test_the_tiling_checker_can_fail():
    """The NULL control. Every fault the real test relies on, produced on purpose."""
    def seg(start, end):
        return Segment("s", "t", "d", "x", 1, ((start, end),), "k", 0, "p")

    assert tiling_fault([], 100) is not None
    assert "lost" in tiling_fault([seg(10, 100)], 100)
    assert "unreachable" in tiling_fault([seg(0, 90)], 100)
    assert "gap" in tiling_fault([seg(0, 40), seg(50, 100)], 100)
    assert "overlap" in tiling_fault([seg(0, 60), seg(50, 100)], 100)
    assert tiling_fault([seg(0, 50), seg(50, 100)], 100) is None


@pytest.mark.parametrize("scheme", sorted(SCHEMES))
def test_every_scheme_covers_the_whole_turn_exactly_once(scheme):
    """No byte of the record is unreachable through the index, and none is doubled.

    Run for every scheme rather than the good one: a scheme is allowed to cut
    badly, since a bad cut is only a bad perspective. It is not allowed to hide
    part of the record, because that is a lossy copy wearing an index's clothes.
    """
    index = build_index([("turns/000001-user.json", TURN)], scheme)
    fault = tiling_fault(index.segments, len(TURN))
    assert fault is None, f"{scheme}: {fault}"


@pytest.mark.parametrize("scheme", sorted(SCHEMES))
def test_projection_reads_the_record_and_ids_are_unique(scheme):
    index = build_index([("turns/000001-user.json", TURN)], scheme)
    ids = [s.segment_id for s in index.segments]
    assert len(ids) == len(set(ids))
    for segment in index.segments:
        assert segment.source_digest == digest_of(TURN)
        assert segment.projection_version == PROJECTION_VERSION
        project_segment(segment, TURN)


def test_reading_against_different_bytes_is_refused():
    """The failure with no symptom: offsets into a turn that has since changed.

    Checked on every read rather than at write, because the read is where the
    wrong text would be returned, and it would look entirely reasonable.
    """
    index = build_index([("turns/000001-user.json", TURN)], "structural-v1")
    segment = index.segments[-1]
    other = TURN.replace(b"Heading one", b"Heading ONE")
    assert len(other) == len(TURN), "the drill must change content, not length"

    with pytest.raises(ValueError) as caught:
        project_segment(segment, other)
    assert "indexed against a different turn" in str(caught.value)
    # and the same call succeeds against the bytes it was computed from, so the
    # refusal is about the digest rather than about the range.
    assert project_segment(segment, TURN)


def test_an_out_of_bounds_range_is_refused_even_with_a_matching_digest():
    short = b"x" * 300
    segment = Segment("s#0", "t", digest_of(short), "structural-v1", 1,
                      ((0, 4000),), "prose", 0, PROJECTION_VERSION)
    with pytest.raises(ValueError, match="not inside"):
        project_segment(segment, short)


def test_re_segmenting_leaves_the_record_and_the_ids_alone():
    """『無限細切只是生成無限多個索引——本體層連被驚動都沒有。』

    Four schemes over one turn, then the first scheme again: the record's digest is
    the same, and the rebuilt ids are identical. If ids drifted between builds,
    every stored vector would silently detach from what it describes.
    """
    before = digest_of(TURN)
    pairs = [("turns/000001-user.json", TURN)]
    first = build_index(pairs, "structural-v1")
    for scheme in SCHEMES:
        build_index(pairs, scheme)
    again = build_index(pairs, "structural-v1")

    assert digest_of(TURN) == before
    assert [s.segment_id for s in again.segments] == \
           [s.segment_id for s in first.segments]
    assert [s.ranges for s in again.segments] == [s.ranges for s in first.segments]


def test_schemes_disagree_about_where_to_cut():
    """Otherwise the benchmark compared one scheme with itself under four names."""
    cuts = {name: {s.ranges for s in build_index([("t", TURN)], name).segments}
            for name in SCHEMES}
    assert len({frozenset(v) for v in cuts.values()}) > 1, cuts


def test_index_survives_a_round_trip_through_its_stored_shape():
    index = build_index([("turns/000001-user.json", TURN)], "changepoint-v1")
    index.edges.append({"kind": "adjacency", "from": index.segments[0].segment_id,
                        "to": index.segments[-1].segment_id})
    restored = SegmentIndex.of(index.as_dict())
    assert restored.segments == index.segments
    assert restored.edges == index.edges
    assert restored.scheme_id == index.scheme_id


def test_an_unknown_scheme_is_an_error_rather_than_a_default():
    with pytest.raises(ValueError, match="unknown scheme"):
        build_index([("t", TURN)], "the-one-that-does-not-exist")
