# -*- coding: utf-8 -*-
"""The real-corpus round trip — `test_demo/`.

Everything else in this suite tests the format against inputs the suite invented.
This one tests it against files a person put in a folder because they actually want
to keep them, which is a different question and the only one that finally matters.

It runs on every platform in CI, so the answer to "do Neo's papers survive a round
trip" is not a claim about one Windows laptop.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "test_demo"))

CORPUS = ROOT / "test_demo"


@pytest.fixture(scope="module")
def report():
    if not CORPUS.is_dir():
        pytest.fail(f"{CORPUS} is missing — the corpus is part of the repository")
    from run import check_corpus

    return check_corpus(CORPUS)


def test_every_file_in_the_corpus_comes_back_byte_for_byte(report):
    assert not report.mismatches, report.mismatches
    assert report.compared == report.files
    assert report.files > 0, "an empty corpus proves nothing and must not pass"


def test_the_corpus_covers_more_than_one_kind_of_file(report):
    """A guard on the corpus rather than on the code.

    The point of this folder is that it grows: papers first, then programs, then
    whatever else. If it ever collapses to a single file type, the round-trip test
    above is quietly checking much less than it looks like it is.
    """
    assert len(report.by_extension) >= 2, report.by_extension
    for extension, row in report.by_extension.items():
        assert row["round_tripped"] == row["files"], (extension, row)


def test_an_earlier_draft_survives_a_later_one(report):
    """The workload a paper actually has: it gets rewritten, repeatedly."""
    assert report.revision["first_draft_still_exact"]
    assert report.revision["shared_chunks"] > 0, \
        "a second draft that shares nothing means deduplication is doing nothing"


def test_the_default_chunk_size_is_measured_against_this_corpus(report):
    """Not an assertion about which size wins — an assertion that we looked.

    The pinned default has a 64 KiB floor, and every paper here is smaller than
    that, so the default made each one a single chunk and a one-paragraph edit cost
    the whole file. That was invisible until something measured it on real files.
    """
    sizes = {row["avg_size"]: row for row in report.profiles}
    assert 262144 in sizes and 4096 in sizes
    assert sizes[4096]["chunks"] > sizes[262144]["chunks"], \
        "a smaller average must produce more chunks, or the sweep is not sweeping"
