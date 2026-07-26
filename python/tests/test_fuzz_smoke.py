# -*- coding: utf-8 -*-
"""A bounded differential fuzz run, in the suite — T-FUZZ-1.

The full campaign is `python tools/fuzz_differential.py -n 20000`, which takes
minutes and belongs in a human's hands. This is the version that runs on every
commit: few enough mutants to be quick, on fixed seeds so a failure is
reproducible rather than a rumour.

It exists because the two findings this tool produced were both invisible to the
hand-written suite. One was a code misclassification; the other was a stated
invariant — record sequence — that *neither* implementation checked, which no
amount of writing more tests by hand was going to surface, because the tests and
the implementations shared the same blind spot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))


@pytest.fixture(scope="module")
def fuzzer(node):
    """The fuzz driver, with Node available — it needs both implementations."""
    import fuzz_differential
    return fuzz_differential


# Two seeds, small counts. The point is to keep the mechanism alive on every
# commit, not to search the space here.
@pytest.mark.parametrize("seed", [20260726, 31337])
def test_no_divergence_between_the_implementations(fuzzer, seed):
    findings = fuzzer.run(count=120, seed=seed, batch=120, keep=False, quiet=True)

    assert not findings.uncaught, (
        "a reader raised something that is not an AnlaError — it crashed where it "
        f"should have refused: {findings.uncaught[:3]}")
    assert not findings.divergences, (
        "one implementation accepted an archive the other refused; that is always a "
        f"defect in one of them: {findings.divergences[:3]}")
    assert not findings.code_mismatches, (
        "both refused, with different error codes. SPEC.md fixes the verification "
        "order, so either an implementation checks out of order or the "
        f"specification never said which check comes first: {findings.code_mismatches[:3]}")


def test_the_fuzzer_would_notice_a_planted_divergence(fuzzer, monkeypatch):
    """A fuzzer that cannot fail is a progress bar.

    Make the Python verdict always "accepted" and confirm the comparison reports
    divergences — otherwise a green run above proves only that the loop ran.
    """
    monkeypatch.setattr(fuzzer, "python_verdict", lambda data: fuzzer.Verdict(True))
    findings = fuzzer.run(count=60, seed=99, batch=60, keep=False, quiet=True)
    assert findings.divergences, "the comparison did not notice a rigged verdict"
