# -*- coding: utf-8 -*-
"""The vector plane: a format that survives one real conversation, and a refusal.

Two properties, and the second is the one that was missing:

* the sidecar round-trips exactly (within float32) and refuses a corrupt or
  mislabelled file rather than reading garbage as vectors;
* a search too large for the available backend **says so**. The pure-Python cosine
  is 71 µs a pair, so 61,149 vectors is seventy-two minutes for one query — and an
  agent that waits seventy-two minutes cannot tell a slow search from a hung one.
  A refusal naming the fix is strictly better than an answer nobody receives.
"""

from __future__ import annotations

import json
import random

import pytest

from anla1.vectors import (
    MAGIC, PURE_PYTHON_LIMIT, VectorSet, read_vectors, write_vectors,
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


def test_pure_python_refuses_a_corpus_it_cannot_search_in_time():
    """The whole point of the file. Constructed rather than written to disk, so the
    limit is drilled without producing a gigabyte of test fixture.

    `data` is a plain list, so `hasattr(data, "shape")` is False and the NumPy path
    is not taken even where NumPy is installed — this asserts the fallback's own
    behaviour rather than whichever backend happens to be present.
    """
    count = PURE_PYTHON_LIMIT + 1
    fake = VectorSet(keys=[f"k{i}" for i in range(count)],
                     data=[0.0] * (count * 4), width=4, header={})
    with pytest.raises(RuntimeError) as caught:
        fake.search([0.1] * 4)
    message = str(caught.value)
    assert "numpy" in message and "minutes" in message
    assert f"{count:,}" in message, "the refusal states the size that caused it"


def test_just_under_the_limit_still_answers():
    """The limit must be a limit, not a wall the tests never approach from below."""
    count = 64
    fake = VectorSet(keys=[f"k{i}" for i in range(count)],
                     data=[float(i % 7) for i in range(count * 4)], width=4,
                     header={})
    assert len(fake.search([1.0, 0.0, 0.0, 0.0], limit=3)) == 3
