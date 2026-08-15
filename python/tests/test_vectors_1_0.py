# -*- coding: utf-8 -*-
"""The vector plane: a format that survives one real conversation, and a refusal.

Two properties, and the second is the one that was missing:

* the sidecar round-trips exactly (within float32) and refuses a corrupt or
  mislabelled file rather than reading garbage as vectors;
* a search projected to run past a stated time budget **says so**, and the
  projection is arithmetic the reader can redo. That last part is not decoration:
  the first version of this module defended its threshold with "73 minutes for one
  query", which was 70.9 µs × 61,458 read as 4,357 s instead of **4.4 s**. The
  threshold was wrong because nobody could multiply the number it rested on.
"""

from __future__ import annotations

import json
import random

import pytest

from anla1.vectors import (
    MAGIC, PURE_PYTHON_BUDGET_SECONDS, PURE_PYTHON_SECONDS_PER_ELEMENT, VectorSet,
    pure_python_projection, read_vectors, write_vectors,
)


def rows(count: int, width: int = 16, seed: int = 3):
    rng = random.Random(seed)
    return [(f"seg-{i:05d}", [rng.gauss(0, 1) for _ in range(width)])
            for i in range(count)]


def test_round_trip_keeps_keys_order_and_values(tmp_path):
    original = rows(40)
    written = write_vectors(tmp_path / "v.anlavec", original,
                            {"model": "m", "dimensions": 16})
    loaded = read_vectors(tmp_path / "v.anlavec")

    assert loaded.keys == [k for k, _ in original]
    assert loaded.width == 16 and len(loaded) == 40
    assert written["bytes"] == written["header_bytes"] + 40 * 16 * 4
    for i, (_, vector) in enumerate(original):
        assert max(abs(a - b) for a, b in zip(vector, loaded.row(i))) < 1e-6


def test_the_identity_travels_with_the_vectors(tmp_path):
    identity = {"model": "text-embedding-3-small", "dimensions": 16,
                "revision": "2024-01", "projection_version": "jsonl-slice-1",
                "segmentation_scheme": "changepoint-v1"}
    write_vectors(tmp_path / "v.anlavec", rows(4), identity)
    assert read_vectors(tmp_path / "v.anlavec").identity == identity


def test_mixed_width_is_refused_at_write(tmp_path):
    bad = [("a", [0.1] * 8), ("b", [0.1] * 12)]
    with pytest.raises(ValueError, match="did not come from one model"):
        write_vectors(tmp_path / "v.anlavec", bad, {"model": "m"})


def test_a_truncated_file_is_refused_rather_than_read_short(tmp_path):
    path = tmp_path / "v.anlavec"
    write_vectors(path, rows(10), {"model": "m"})
    path.write_bytes(path.read_bytes()[:-64])
    with pytest.raises(ValueError, match="declares"):
        read_vectors(path)


def test_a_file_of_another_kind_is_refused(tmp_path):
    path = tmp_path / "v.anlavec"
    path.write_bytes(json.dumps({"kind": "something:else", "width": 1, "count": 0,
                                 "keys": []}).encode() + b"\n")
    with pytest.raises(ValueError, match=MAGIC):
        read_vectors(path)


def test_search_finds_the_vector_it_was_given(tmp_path):
    data = rows(200, width=32)
    write_vectors(tmp_path / "v.anlavec", data, {"model": "m", "dimensions": 32})
    loaded = read_vectors(tmp_path / "v.anlavec")
    key, vector = data[77]
    assert loaded.search(vector, limit=1)[0][0] == key


def test_a_query_of_the_wrong_width_is_refused(tmp_path):
    write_vectors(tmp_path / "v.anlavec", rows(8, width=16), {"model": "m"})
    loaded = read_vectors(tmp_path / "v.anlavec")
    with pytest.raises(ValueError, match="not one vector space"):
        loaded.search([0.1] * 4)


def test_the_projection_is_arithmetic_anyone_can_check():
    """The number the refusal is built on, stated so it can be disagreed with.

    The first version of this module claimed the pure-Python search took 73 minutes
    over 61,458 vectors. It takes about 4 seconds: 70.9 µs × 61,458 was read as
    4,357 s instead of 4.4 s, and a refusal threshold was set to defend the wrong
    figure. A constant nobody can multiply is a constant nobody can catch.
    """
    assert pure_python_projection(61_458, 768) == pytest.approx(11.3, rel=0.1)
    assert pure_python_projection(8_000, 768) < 2.0, (
        "the old 8,000-vector limit fired at about 1.5 s, which is not a hang")
    # Linear in both arguments, so the message's arithmetic is the model's.
    assert pure_python_projection(2000, 10) == pytest.approx(
        2 * pure_python_projection(1000, 10))
    assert pure_python_projection(1000, 20) == pytest.approx(
        2 * pure_python_projection(1000, 10))


def test_pure_python_refuses_only_past_the_stated_budget():
    """Constructed rather than written to disk, so the budget is drilled without a
    gigabyte of fixture.

    `data` is a plain list, so `hasattr(data, "shape")` is False and the NumPy path
    is not taken even where NumPy is installed — this asserts the fallback's own
    behaviour rather than whichever backend happens to be present.
    """
    width = 64
    over = int(PURE_PYTHON_BUDGET_SECONDS
               / (PURE_PYTHON_SECONDS_PER_ELEMENT * width)) + 1000
    fake = VectorSet(keys=[f"k{i}" for i in range(over)],
                     data=[0.0] * (over * width), width=width, header={})
    with pytest.raises(RuntimeError) as caught:
        fake.search([0.1] * width)
    message = str(caught.value)
    assert "numpy" in message
    assert f"{over:,}" in message, "the refusal states the size that caused it"
    assert f"{PURE_PYTHON_BUDGET_SECONDS:.0f} s budget" in message, (
        "the refusal states the budget it is comparing against")


def test_just_under_the_budget_still_answers():
    """The budget must be a budget, not a wall the tests never approach from below."""
    count = 64
    fake = VectorSet(keys=[f"k{i}" for i in range(count)],
                     data=[float(i % 7) for i in range(count * 4)], width=4,
                     header={})
    assert pure_python_projection(count, 4) < PURE_PYTHON_BUDGET_SECONDS
    assert len(fake.search([1.0, 0.0, 0.0, 0.0], limit=3)) == 3
