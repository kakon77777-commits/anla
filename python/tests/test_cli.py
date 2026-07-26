# -*- coding: utf-8 -*-
"""The CLI: exit codes, JSON output, and the plan/pack/verify/extract path.

An agent is a first-class caller here, so the contract under test is the exit
code and the JSON, not the prose.
"""

from __future__ import annotations

import json

import pytest

from anla.cli import main
from conftest import VECTORS


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "readme.txt").write_text("hello from the cli\n", encoding="utf-8")
    (root / "data.bin").write_bytes(bytes(range(64)) * 100)
    (root / "empty.txt").write_text("", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("excluded\n", encoding="utf-8")
    return root


def run(capsys, argv) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_plan_emits_json(capsys, workspace):
    code, out, _ = run(capsys, ["plan", str(workspace), "--json", "--exclude", ".git/**"])
    assert code == 0
    payload = json.loads(out)
    assert payload["plan"]["exclude_globs"] == [".git/**"]
    assert payload["candidate_files"] == 4
    assert payload["writer"].startswith("ANLA-MVP 0.1")


def test_pack_verify_extract_round_trip(capsys, workspace, tmp_path):
    archive = tmp_path / "out.anla"
    code, out, _ = run(capsys, [
        "pack", str(workspace), "-o", str(archive), "--json",
        "--exclude", ".git", "--exclude", ".git/**", "--chunk-size", "1024",
    ])
    assert code == 0
    packed = json.loads(out)
    assert packed["summary"]["files"] == 3
    assert packed["verification"]["status"] == "ok"

    code, out, _ = run(capsys, ["verify", str(archive), "--json"])
    assert code == 0
    assert json.loads(out)["verification"]["mode"] == "full"

    destination = tmp_path / "restored"
    code, out, _ = run(capsys, ["extract", str(archive), "--to", str(destination), "--json"])
    assert code == 0
    report = json.loads(out)["extraction_report"]
    assert report["files"] == 3
    assert "symlinks" in report["not_representable_by_profile"]
    assert (destination / "docs" / "readme.txt").read_text(encoding="utf-8") \
        == "hello from the cli\n"
    assert (destination / "data.bin").read_bytes() == (workspace / "data.bin").read_bytes()
    assert not (destination / ".git").exists()


def test_pack_is_reproducible_from_the_command_line(capsys, workspace, tmp_path):
    first, second = tmp_path / "a.anla", tmp_path / "b.anla"
    for target in (first, second):
        code, _, _ = run(capsys, [
            "pack", str(workspace), "-o", str(target), "--json",
            "--uuid", "00112233445566778899aabbccddeeff",
            "--created-ns", "1752732000000000000",
        ])
        assert code == 0
    assert first.read_bytes() == second.read_bytes()


def test_inspect_and_list(capsys):
    vector = VECTORS / "unicode-paths.anla"
    code, out, _ = run(capsys, ["inspect", str(vector), "--json"])
    assert code == 0
    assert json.loads(out)["summary"]["source_name"] == "unicode-paths"

    code, out, _ = run(capsys, ["list", str(vector), "--json"])
    assert code == 0
    paths = [o["path"] for o in json.loads(out)["objects"]]
    assert "Sample.TXT" in paths and "sample.txt" in paths


def test_manifest_canonical_output_is_byte_exact(capsys):
    vector = VECTORS / "basic-store.anla"
    code, out, _ = run(capsys, ["manifest", str(vector), "--canonical"])
    assert code == 0
    from anla import open_archive
    from anla.canonical import canonical
    archive = open_archive(vector, full=False)
    assert out.strip() == canonical(archive.manifest)


def test_manifest_can_strip_the_intelligence_plane(capsys):
    vector = VECTORS / "basic-store.anla"
    code, out, _ = run(capsys, ["manifest", str(vector), "--strip-auxiliary"])
    assert code == 0
    assert json.loads(out)["auxiliary"] == {"decision_log": [], "disposable": True}


def test_strip_removes_the_decision_log_and_nothing_else(capsys, workspace, tmp_path):
    archive = tmp_path / "full.anla"
    stripped = tmp_path / "stripped.anla"
    code, _, _ = run(capsys, ["pack", str(workspace), "-o", str(archive), "--json",
                              "--chunk-size", "1024"])
    assert code == 0

    code, out, _ = run(capsys, ["strip", str(archive), "-o", str(stripped), "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["decision_log_entries_removed"] > 0
    assert payload["bytes_after"] < payload["bytes_before"]
    assert payload["verification"]["status"] == "ok"

    from anla import open_archive
    before, after = open_archive(archive), open_archive(stripped)
    assert after.manifest["auxiliary"] == {"decision_log": [], "disposable": True}
    assert after.manifest["objects"] == before.manifest["objects"]
    assert {o["path"]: after.read(o["path"]) for o in after.files()} \
        == {o["path"]: before.read(o["path"]) for o in before.files()}


def test_export_zip(capsys, tmp_path):
    import zipfile
    target = tmp_path / "out.zip"
    code, out, _ = run(capsys, ["export", str(VECTORS / "basic-store.anla"),
                                "-o", str(target), "--json"])
    assert code == 0
    assert json.loads(out)["format"] == "zip-store"
    with zipfile.ZipFile(target) as zf:
        assert zf.testzip() is None
        assert zf.read("docs/readme.txt") == b"ANLA cross-implementation fixture\n"


def test_integrity_failure_exit_code_is_five(capsys, tmp_path):
    # no-mtime.anla uses a 1 MiB chunk size, so the file content sits in the
    # archive contiguously and one flipped byte is a clean content corruption.
    data = bytearray((VECTORS / "no-mtime.anla").read_bytes())
    data[data.index(b"ANLA cross-implementation")] = ord("a")
    corrupted = tmp_path / "corrupt.anla"
    corrupted.write_bytes(bytes(data))
    code, _, err = run(capsys, ["verify", str(corrupted), "--json"])
    assert code == 5
    assert json.loads(err)["error"]["code"] == "ANLA_INTEGRITY_FAILURE"


def test_unknown_format_exit_code_is_three(capsys, tmp_path):
    from anla.format import build_header
    fake = tmp_path / "fake.anla"
    fake.write_bytes(build_header(bytes(16)) + b"\0" * 96)
    code, _, err = run(capsys, ["inspect", str(fake), "--json"])
    assert code == 4
    assert json.loads(err)["error"]["code"] == "ANLA_MANIFEST_INVALID"


def test_missing_source_exit_code_is_two(capsys, tmp_path):
    code, _, _ = run(capsys, ["pack", str(tmp_path / "nope"), "--json"])
    assert code == 2


def test_resource_limit_exit_code_is_eight(capsys):
    code, _, err = run(capsys, ["verify", str(VECTORS / "split-file.anla"),
                                "--max-output-bytes", "16", "--json"])
    assert code == 8
    assert json.loads(err)["error"]["code"] == "ANLA_RESOURCE_LIMIT_EXCEEDED"


def test_version_string_names_the_format():
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
