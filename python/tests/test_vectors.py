# -*- coding: utf-8 -*-
"""The frozen vectors: T-ORG-1, and the guarantee that "frozen" is true.

A format profile that cannot read the artifact it shipped with has not frozen
anything, and a set of vectors that drifts silently with the writer is a
changelog, not a test suite.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys

import pytest

from anla import Limits, open_archive
from conftest import CASES, REPO, VECTORS, run_node

ORIGINAL = VECTORS / "browser-interop-v0.1.anla"
SUMS = VECTORS / "SHA256SUMS"
BYTE_EXACT = [c for c in CASES if c.byte_exact]


def test_the_original_release_archive_still_verifies():
    """T-ORG-1."""
    archive = open_archive(ORIGINAL, full=True)
    assert archive.summary["format"] == "ANLA-MVP"
    assert archive.summary["format_version"] == "0.1"
    assert archive.verification == {
        "status": "ok", "mode": "full",
        "verified_chunks": 7, "verified_files": 2, "logical_bytes": 29,
    }
    assert archive.read("docs/readme.txt") == b"ANLA browser interop\n"
    assert archive.read("data.bin") == bytes([1, 2, 3, 4, 1, 2, 3, 4])


def test_the_original_release_archive_is_deduplicated():
    """data.bin is 1,2,3,4,1,2,3,4 at a 4-byte chunk size: two references, one
    chunk. The dedup claim was true in the first release and stays checkable."""
    archive = open_archive(ORIGINAL, full=False)
    data_bin = next(o for o in archive.files() if o["path"] == "data.bin")
    assert [c["id"] for c in data_bin["chunks"]] == [data_bin["chunks"][0]["id"]] * 2
    assert archive.summary["chunk_references"] > archive.summary["unique_chunks"]


def test_the_original_release_archive_is_not_reproducible_by_the_current_writer():
    """Documented in SPEC.md section 13: the original writer sorted objects with
    localeCompare, so its byte layout was locale-dependent. It stays readable; it
    is not a reproducibility vector, and this test pins that distinction so nobody
    later "fixes" it by regenerating the file."""
    archive = open_archive(ORIGINAL, full=False)
    assert archive.manifest["plan"]["chunk_size"] == 4
    assert ORIGINAL.read_bytes()[:8] == bytes([0x41, 0x4E, 0x4C, 0x41, 0x0D, 0x0A, 0x1A, 0x0A])


@pytest.mark.parametrize("case", BYTE_EXACT, ids=[c.id for c in BYTE_EXACT])
def test_every_frozen_vector_verifies(case):
    vector = VECTORS / f"{case.id}.anla"
    assert vector.exists(), f"missing frozen vector: {vector.name}"
    assert open_archive(vector, full=True).verification["status"] == "ok"


def test_frozen_vectors_still_match_the_current_writer():
    """If this fails, either the writer changed or a vector was edited. Both are
    format-version events, not routine test failures."""
    result = subprocess.run(
        [sys.executable, str(REPO / "conformance" / "make_vectors.py"), "--check", "--json"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sha256sums_matches_the_files_on_disk():
    listed = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split("  ", 1)
        listed[name] = digest
    on_disk = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in VECTORS.glob("*.anla")}
    assert listed == on_disk


def test_javascript_verifies_every_frozen_vector(node):
    vectors = sorted(VECTORS.glob("*.anla"))
    report = run_node(node, ["verify", *[str(v) for v in vectors]])
    failed = [r for r in report["results"] if not r["ok"]]
    assert not failed, failed
    assert len(report["results"]) == len(vectors)


def test_vectors_are_readable_under_tight_limits():
    """Every vector is small, so a decoder with conservative limits must still
    accept all of them. A limit that rejects the format's own vectors is wrong."""
    limits = Limits(max_output_bytes=1 << 20, max_objects=100,
                    max_chunk_uncompressed=1 << 16)
    for vector in VECTORS.glob("*.anla"):
        assert open_archive(vector, full=True, limits=limits).verification["status"] == "ok"
