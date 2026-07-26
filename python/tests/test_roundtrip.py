# -*- coding: utf-8 -*-
"""Round trips and the preservation invariants: T-EMP, T-DUP, T-BIG, T-UNI, T-AUX, T-REP."""

from __future__ import annotations

import pytest

from anla import PackPlan, SourceFile, SourceTree, export_zip_bytes, open_archive, pack
from anla.errors import FidelityDegraded
from conftest import CASES, TREES, build_tree, pack_case


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_every_fixture_case_round_trips(case, tmp_path):
    result = pack_case(case)
    archive = open_archive(result.data, full=True)
    tree = build_tree(TREES[case.tree_name])

    expected = {f.path: f.data for f in tree.files
                if not _excluded(f.path, case.plan.exclude_globs)}
    restored = {o["path"]: archive.read(o["path"]) for o in archive.files()}
    assert restored == expected

    destination = tmp_path / case.id
    try:
        report = archive.extract_to(destination)
    except FidelityDegraded as degraded:
        # The unicode fixture deliberately contains pairs that some filesystems
        # cannot tell apart (case-only on Windows, NFC/NFD on macOS). Refusing is
        # the correct outcome; losing one of the two would not be.
        collided = degraded.details["paths"]
        assert len(collided) == 2 and collided[0] != collided[1]
        assert _filesystem_folds(tmp_path, *collided), \
            f"reported a collision on a filesystem that keeps {collided} distinct"
        return

    assert report.files == len(expected)
    for path, data in expected.items():
        assert (destination / path).read_bytes() == data


def _filesystem_folds(tmp_path, first, second):
    """True when the filesystem really does conflate these two names."""
    probe = tmp_path / "fold-probe"
    probe.mkdir(exist_ok=True)
    (probe / first.replace("/", "_")).write_bytes(b"a")
    target = probe / second.replace("/", "_")
    return target.exists()


def _excluded(path, globs):
    from anla.globs import matches_any
    return matches_any(path, globs)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_reproducible_within_this_implementation(case):
    """T-REP-1: same input, same (uuid, created_ns), byte-identical output."""
    assert pack_case(case).data == pack_case(case).data


def test_empty_archive():
    """T-EMP-2."""
    result = pack(SourceTree(name="nothing"), PackPlan(),
                  archive_uuid=bytes(16), created_ns=0)
    archive = open_archive(result.data)
    assert archive.summary["objects"] == 0
    assert archive.verification["verified_files"] == 0
    assert archive.summary["archive_bytes"] == len(result.data)


def test_empty_file_has_no_chunk_references():
    """T-EMP-1."""
    tree = SourceTree(name="hollow", files=[SourceFile("nothing.txt", b"")])
    archive = open_archive(pack(tree).data)
    obj = next(archive.files())
    assert obj["size"] == 0 and obj["chunks"] == []
    assert archive.read("nothing.txt") == b""
    assert archive.summary["unique_chunks"] == 0


def test_identical_content_stores_one_chunk():
    """T-DUP-1."""
    payload = b"identical content across two paths\n"
    tree = SourceTree(name="dup", files=[
        SourceFile("a.txt", payload), SourceFile("b.txt", payload),
    ])
    archive = open_archive(pack(tree).data)
    assert archive.summary["unique_chunks"] == 1
    assert archive.summary["chunk_references"] == 2
    assert archive.read("a.txt") == archive.read("b.txt") == payload


def test_file_larger_than_chunk_size_splits_and_restores():
    """T-BIG-1."""
    data = bytes(range(256)) * 40  # 10240 bytes, no two chunks alike
    tree = SourceTree(name="big", files=[SourceFile("big.bin", data)])
    archive = open_archive(pack(tree, PackPlan(chunk_size=4096, compression="store")).data)
    obj = next(archive.files())
    assert [c["length"] for c in obj["chunks"]] == [4096, 4096, 2048]
    assert archive.read("big.bin") == data


def test_unicode_paths_round_trip_byte_exact():
    """T-UNI-1: NFC and NFD are distinct paths, and neither is normalized."""
    nfc = 'café.txt'    # e-acute as a single code point
    nfd = 'café.txt'   # e followed by a combining acute
    tree = SourceTree(name="unicode", files=[
        SourceFile(nfc, b"precomposed"), SourceFile(nfd, b"decomposed"),
        SourceFile("文件/會話.txt", "內容".encode("utf-8")),
    ], directories=["文件"])
    archive = open_archive(pack(tree).data)
    paths = [o["path"] for o in archive.files()]
    assert nfc in paths and nfd in paths
    assert archive.read(nfc) == b"precomposed"
    assert archive.read(nfd) == b"decomposed"
    assert archive.read("文件/會話.txt").decode("utf-8") == "內容"


def test_auxiliary_plane_is_disposable():
    """T-AUX-1: emptying the intelligence plane changes no extracted byte."""
    tree = build_tree(TREES["compressible"])
    archive = open_archive(pack(tree, PackPlan(chunk_size=16384)).data)
    before = {o["path"]: archive.read(o["path"]) for o in archive.files()}
    stripped = archive.without_auxiliary()

    from anla.canonical import canonical_bytes
    assert canonical_bytes(stripped) != canonical_bytes(archive.manifest)
    assert stripped["objects"] == archive.manifest["objects"]
    assert stripped["chunks"] == archive.manifest["chunks"]
    # And the decision log carried real content, so this is not a vacuous pass.
    assert archive.manifest["auxiliary"]["decision_log"]

    after = {o["path"]: archive.read(o["path"]) for o in archive.files()}
    assert after == before


def test_decision_log_records_a_real_codec_choice():
    tree = build_tree(TREES["compressible"])
    archive = open_archive(pack(tree, PackPlan(chunk_size=16384, compression="auto")).data)
    reasons = {entry["reason"] for entry in archive.manifest["auxiliary"]["decision_log"]}
    assert "smaller-representation" in reasons
    assert "compression-not-beneficial" in reasons


def test_zip_export_matches_archive_content():
    import io
    import zipfile

    tree = build_tree(TREES["basic"])
    archive = open_archive(pack(tree).data)
    with zipfile.ZipFile(io.BytesIO(export_zip_bytes(archive))) as zf:
        assert zf.testzip() is None
        for obj in archive.files():
            assert zf.read(obj["path"]) == archive.read(obj["path"])


def test_quick_mode_skips_decoding_but_still_checks_stored_hashes():
    result = pack(build_tree(TREES["basic"]))
    archive = open_archive(result.data, full=False)
    assert archive.verification["mode"] == "quick"
    assert archive.verification["verified_chunks"] == 0
    with pytest.raises(Exception):
        archive.read("data.bin")


def test_extract_refuses_to_overwrite_by_default(tmp_path):
    result = pack(SourceTree(name="x", files=[SourceFile("a.txt", b"one")]))
    archive = open_archive(result.data)
    archive.extract_to(tmp_path / "out")
    with pytest.raises(Exception):
        archive.extract_to(tmp_path / "out")
    archive.extract_to(tmp_path / "out", overwrite=True)


def test_mtime_is_restored(tmp_path):
    mtime = 1_700_000_000_000_000_000
    tree = SourceTree(name="t", files=[SourceFile("a.txt", b"x", mtime_ns=mtime)])
    archive = open_archive(pack(tree).data)
    archive.extract_to(tmp_path / "out")
    written = (tmp_path / "out" / "a.txt").stat().st_mtime_ns
    # Filesystem timestamp granularity varies; a second of slack is enough to
    # show the value came from the archive rather than from the clock.
    assert abs(written - mtime) < 1_000_000_000


def test_excluded_paths_are_absent_from_the_manifest():
    tree = build_tree(TREES["excluded"])
    globs = (".git", ".git/**", "node_modules", "node_modules/**")
    archive = open_archive(pack(tree, PackPlan(exclude_globs=globs)).data)
    paths = {o["path"] for o in archive.manifest["objects"]}
    assert paths == {"src", "src/main.js", "notes.md"}
    # The plan records what was excluded, so "not packed" stays distinguishable
    # from "packed losslessly" (SPEC.md section 8.3).
    assert archive.manifest["plan"]["exclude_globs"] == list(globs)


def test_exclusion_is_per_path_so_a_directory_survives_its_contents():
    """A directory is its own path: excluding what is inside it does not remove
    it. Stated here because it is the kind of thing people discover by accident."""
    tree = build_tree(TREES["excluded"])
    archive = open_archive(pack(tree, PackPlan(exclude_globs=(".git/**",))).data)
    paths = {o["path"] for o in archive.manifest["objects"]}
    assert ".git" in paths
    assert not any(p.startswith(".git/") for p in paths)


def test_single_star_does_not_cross_a_slash():
    from anla.globs import glob_to_regex
    assert glob_to_regex(".git/*").match(".git/config")
    assert not glob_to_regex(".git/*").match(".git/objects/deep/blob")
    assert glob_to_regex(".git/**").match(".git/objects/deep/blob")
    assert glob_to_regex("a?c").match("abc")
    assert not glob_to_regex("a?c").match("a/c")
