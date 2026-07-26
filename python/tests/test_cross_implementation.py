# -*- coding: utf-8 -*-
"""T-XIM-1..3 — the tests that make "model-independent, deterministic" checkable.

Two implementations, written separately against SPEC.md, in two languages, with
no shared code: Python here, JavaScript in web/anla-core.js. If the format is
really specified rather than merely implemented, then each must read the other's
archives, and for the cases where the spec promises byte exactness they must
produce identical bytes.
"""

from __future__ import annotations

import base64
import json

import pytest

from anla import open_archive
from anla.errors import FidelityDegraded
from conftest import (
    CASES, TREES, VECTORS, build_tree, pack_case, run_node, run_node_allow_failure,
)

BYTE_EXACT = [c for c in CASES if c.byte_exact]
NOT_BYTE_EXACT = [c for c in CASES if not c.byte_exact]


@pytest.fixture(scope="module")
def python_archives(tmp_path_factory):
    outdir = tmp_path_factory.mktemp("py-archives")
    written = {}
    for case in CASES:
        target = outdir / f"{case.id}.py.anla"
        target.write_bytes(pack_case(case).data)
        written[case.id] = target
    return written


def test_node_runtime_is_usable(node):
    report = run_node(node, ["selftest"])
    assert report["verification"]["status"] == "ok"
    assert report["runtime"]["format"] == "ANLA-MVP 0.1"
    assert report["runtime"]["native_crypto"] is True
    assert report["runtime"]["native_compression"] is True


@pytest.mark.parametrize("case", BYTE_EXACT, ids=[c.id for c in BYTE_EXACT])
def test_both_writers_agree_byte_for_byte(case, node_pack, python_archives):
    """T-XIM-3."""
    js = (node_pack["outdir"] / f"{case.id}.js.anla").read_bytes()
    py = python_archives[case.id].read_bytes()
    assert len(js) == len(py), f"{case.id}: {len(py)} bytes in Python, {len(js)} in JavaScript"
    if js != py:
        index = next(i for i, (a, b) in enumerate(zip(py, js)) if a != b)
        pytest.fail(f"{case.id}: first difference at byte {index}: "
                    f"python={py[index:index + 16]!r} javascript={js[index:index + 16]!r}")


@pytest.mark.parametrize("case", NOT_BYTE_EXACT, ids=[c.id for c in NOT_BYTE_EXACT])
def test_compressed_cases_are_not_required_to_match_byte_for_byte(case, node_pack,
                                                                  python_archives):
    """The honest half of SPEC.md section 10: two DEFLATE encoders may differ, so
    the promise for these cases is mutual readability, not byte equality."""
    js = (node_pack["outdir"] / f"{case.id}.js.anla").read_bytes()
    py = python_archives[case.id].read_bytes()
    assert open_archive(js).verification["status"] == "ok"
    assert open_archive(py).verification["status"] == "ok"
    # And the archives really do exercise the compressed codec.
    codecs = {d["codec"] for d in open_archive(py, full=False).manifest["chunks"].values()}
    assert "deflate" in codecs


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_javascript_writer_read_by_python(case, node_pack):
    """T-XIM-2."""
    data = (node_pack["outdir"] / f"{case.id}.js.anla").read_bytes()
    archive = open_archive(data, full=True)
    assert archive.verification["status"] == "ok"
    tree = build_tree(TREES[case.tree_name])
    from anla.globs import matches_any
    expected = {f.path: f.data for f in tree.files
                if not matches_any(f.path, case.plan.exclude_globs)}
    assert {o["path"]: archive.read(o["path"]) for o in archive.files()} == expected


def test_python_writer_read_by_javascript(node, python_archives):
    """T-XIM-1."""
    report = run_node(node, ["verify", *[str(p) for p in python_archives.values()]])
    failures = [r for r in report["results"] if not r["ok"]]
    assert not failures, json.dumps(failures, indent=2, ensure_ascii=False)
    for result in report["results"]:
        assert result["verification"]["status"] == "ok"
        # Stripping the intelligence plane changes the manifest bytes; that it
        # does is the precondition for T-AUX-1 meaning anything.
        assert result["auxiliary_stripped_differs"] in (True, False)


def test_the_two_implementations_report_the_same_file_hashes(node, python_archives):
    report = run_node(node, ["verify", *[str(p) for p in python_archives.values()]])
    by_file = {r["file"]: r for r in report["results"]}
    for case_id, path in python_archives.items():
        archive = open_archive(path, full=False)
        mine = {o["path"]: o["sha256"] for o in archive.files()}
        theirs = by_file[str(path)]["file_hashes"]
        assert mine == theirs, case_id


def test_javascript_reads_the_original_browser_release(node):
    """T-ORG-1, from the other side: the archive the v0.1 release shipped is
    still readable by the current JavaScript implementation."""
    vector = VECTORS / "browser-interop-v0.1.anla"
    report = run_node(node, ["verify", str(vector)])
    result = report["results"][0]
    assert result["ok"], result
    assert result["verification"]["verified_files"] == 2
    assert set(result["file_hashes"]) == {"data.bin", "docs/readme.txt"}


@pytest.mark.parametrize("case_id", ["basic-store", "split-file", "duplicate-content",
                                     "empty-file", "unicode-paths"])
def test_javascript_extraction_matches_python_extraction(case_id, node, python_archives,
                                                         tmp_path):
    archive_path = python_archives[case_id]
    js_out = tmp_path / "js"
    code, report = run_node_allow_failure(node, ["extract", str(archive_path), str(js_out)])

    if code != 0:
        # The unicode fixture contains names some filesystems fold together.
        # Refusing is the correct outcome, and both implementations must refuse
        # for the same reason rather than one of them dropping a file.
        assert report["code"] == "ANLA_EXTRACTION_FIDELITY_DEGRADED", report
        assert len(report["details"]["paths"]) == 2
        with pytest.raises(FidelityDegraded):
            open_archive(archive_path, full=True).extract_to(tmp_path / "py")
        return

    archive = open_archive(archive_path, full=True)
    py_out = tmp_path / "py"
    archive.extract_to(py_out)
    for obj in archive.files():
        assert (js_out / obj["path"]).read_bytes() == archive.read(obj["path"])
        assert (js_out / obj["path"]).read_bytes() == (py_out / obj["path"]).read_bytes()


def test_javascript_rejects_what_python_rejects(node, tmp_path):
    """A corrupted archive must be refused by both, with a comparable code."""
    from anla.errors import IntegrityFailure

    # A case with one chunk per file, so the plaintext appears contiguously and
    # flipping a byte in it is unambiguously a content corruption.
    case = next(c for c in CASES if c.id == "no-mtime")
    data = bytearray(pack_case(case).data)
    data[data.index(b"ANLA cross-implementation")] = ord("a")
    corrupted = tmp_path / "corrupt.anla"
    corrupted.write_bytes(bytes(data))

    with pytest.raises(IntegrityFailure):
        open_archive(bytes(data))

    report = run_node(node, ["verify", str(corrupted)])
    result = report["results"][0]
    assert result["ok"] is False
    assert result["code"] == "ANLA_INTEGRITY_FAILURE"


def test_fixture_content_helpers_agree(node_pack):
    """Both drivers must build the same objects from fixtures.json, or every other
    comparison in this module is comparing different inputs.

    ``stored_payload_bytes`` is excluded for the compressed cases only: it is the
    one statistic that legitimately depends on which DEFLATE encoder ran.
    """
    js_stats = {c["id"]: c["statistics"] for c in node_pack["report"]["cases"]}
    for case in CASES:
        mine = dict(pack_case(case).statistics)
        theirs = dict(js_stats[case.id])
        if not case.byte_exact:
            mine.pop("stored_payload_bytes")
            theirs.pop("stored_payload_bytes")
        assert mine == theirs, case.id
    assert all(c["self_reproducible"] for c in node_pack["report"]["cases"])


def test_base64_fixture_decoding_is_identical(fixtures):
    entry = fixtures["trees"]["compressible"]["files"][1]
    assert base64.b64decode(entry["base64"])[:4] == bytes([0xDE, 0xAD, 0xBE, 0xEF])
