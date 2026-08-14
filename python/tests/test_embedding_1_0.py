# -*- coding: utf-8 -*-
"""Embedding identity — the one channel with no independent check on itself.

Cosine returns a confident number for any two vectors of equal width, including
two that came from different models, different revisions of one model, or one
model over two different projections. Nothing downstream can tell, and the wrong
answer arrives with the same shape as the right one.

So the tests here are about *refusal*: every field of the identity must be able to
turn a comparison into `INCOMPARABLE`, and the refusal must name the field, because
a caller told only that it failed will re-embed the wrong side.
"""

from __future__ import annotations

import pytest

from anla1.embedding import INCOMPARABLE, EmbeddingIdentity, comparable

BASE = EmbeddingIdentity(model="text-embedding-3-small", dimensions=768,
                         revision="2024-01", projection_version="jsonl-slice-1",
                         segmentation_scheme="changepoint-v1")

DIFFERENT = {
    "model": {"model": "text-embedding-3-large"},
    "dimensions": {"dimensions": 1536},
    "revision": {"revision": "2025-06"},
    "projection_version": {"projection_version": "jsonl-slice-2"},
    "segmentation_scheme": {"segmentation_scheme": "structural-v1"},
}


def test_an_identity_matches_itself():
    ok, reason = comparable(BASE, EmbeddingIdentity.of(BASE.as_dict()))
    assert ok and reason == ""


@pytest.mark.parametrize("field_name", sorted(DIFFERENT))
def test_every_field_can_refuse_the_comparison(field_name):
    """Parametrised over the fields rather than spot-checked, so adding a field to
    the identity without adding it to the check shows up as a missing case here."""
    other = EmbeddingIdentity.of({**BASE.as_dict(), **DIFFERENT[field_name]})
    ok, reason = comparable(BASE, other)
    assert not ok
    assert reason.startswith(INCOMPARABLE)
    assert field_name in reason, reason


@pytest.mark.parametrize("field_name", sorted(DIFFERENT))
def test_the_fingerprint_moves_when_any_field_moves(field_name):
    """The fingerprint is what gets stored beside a vector. If it collided across
    a field, the stored form would lose the distinction the dataclass keeps."""
    other = EmbeddingIdentity.of({**BASE.as_dict(), **DIFFERENT[field_name]})
    assert other.fingerprint != BASE.fingerprint


def test_same_width_from_two_models_is_incomparable_not_similar():
    """768 == 768 is the trap. Width is not identity."""
    other = EmbeddingIdentity(model="bge-m3", dimensions=768, revision="2024-01",
                              projection_version="jsonl-slice-1",
                              segmentation_scheme="changepoint-v1")
    ok, reason = comparable(BASE, other)
    assert not ok and "model" in reason


def test_extra_metadata_is_part_of_the_identity():
    other = EmbeddingIdentity.of({**BASE.as_dict(), "extra": {"pooling": "mean"}})
    ok, reason = comparable(BASE, other)
    assert not ok and reason.startswith(INCOMPARABLE)


def test_missing_metadata_reads_as_unstated_rather_than_as_agreement():
    """A vector that arrived without provenance must not compare equal to one that
    has it. `unstated` records that we do not know; it is not a wildcard."""
    bare = EmbeddingIdentity.of({"model": "text-embedding-3-small",
                                 "dimensions": 768})
    assert bare.revision == "unstated"
    assert bare.projection_version == "unstated"
    assert bare.segmentation_scheme == "unstated"
    ok, reason = comparable(BASE, bare)
    assert not ok and "revision" in reason


def test_the_verdict_is_a_word_and_not_a_number():
    """`0.0` would conflate 'unrelated' with 'cannot be answered' — ICNS's rule
    that a comparison must be allowed to fail rather than be rounded to a value."""
    assert INCOMPARABLE == "INCOMPARABLE"
    assert not isinstance(INCOMPARABLE, (int, float))
