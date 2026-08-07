# -*- coding: utf-8 -*-
"""The ``anla1`` command line — `python/anla1/cli.py`.

Driven through `main(argv)` and its exit code rather than by calling the functions
underneath, because the exit code *is* the interface for the caller this tool is
built for. An agent that runs `anla1 pack` gets a number and a JSON document, and if
the number is wrong nothing else about the command matters.

Two of them are load-bearing here. **9** is an object the format cannot represent —
a refusal, with no archive written. **11** is fidelity degraded, which is what a
deliberately incomplete pack returns *even though it succeeded*, so that a script
cannot treat a partial archive as a complete one without noticing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla1.cli import main  # noqa: E402

UUID = "00112233445566778899aabbccddeeff"
CREATED = "1785000000000000000"


def run(capsys, *argv: str) -> tuple[int, dict]:
    """Run one command and return its exit code and parsed JSON."""
    code = main([*argv, "--json"])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


def make_tree(root: Path) -> dict[str, bytes]:
    files = {"readme.txt": b"anla1 cli\n",
             "docs/guide.md": b"# guide\n",
             "docs/copy.md": b"# guide\n",
             "blob.bin": bytes(range(256)) * 60}
    for name, payload in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return files


@pytest.fixture()
def tree(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    make_tree(source)
    return source


# ---------------------------------------------------------------------------

def test_pack_verify_extract_round_trip(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    code, packed = run(capsys, "pack", str(tree), "-o", str(archive))
    assert code == 0 and packed["snapshot"] == 1 and packed["files"] == 4

    code, verified = run(capsys, "verify", str(archive))
    assert code == 0 and verified["ok"] and verified["snapshots"] == 1

    out = tmp_path / "out"
    code, extracted = run(capsys, "extract", str(archive), "--to", str(out))
    assert code == 0 and extracted["files"] == 4
    for name, payload in make_tree(tmp_path / "expected").items():
        assert (out / name).read_bytes() == payload


def test_the_same_inputs_produce_the_same_bytes(capsys, tmp_path, tree):
    """The property the freeze rule is stated in terms of.

    Not a debugging convenience: `--uuid` and `--created-ns` exist so that a second
    implementation can be handed the same tree and compared byte for byte, which is
    the only way "two independent implementations agree" can ever be checked.
    """
    first, second = tmp_path / "one.anla", tmp_path / "two.anla"
    for output in (first, second):
        code, _ = run(capsys, "pack", str(tree), "-o", str(output),
                      "--uuid", UUID, "--created-ns", CREATED)
        assert code == 0
    assert first.read_bytes() == second.read_bytes()


def test_pack_refuses_to_replace_an_existing_archive(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    assert run(capsys, "pack", str(tree), "-o", str(archive))[0] == 0
    original = archive.read_bytes()

    code = main(["pack", str(tree), "-o", str(archive), "--json"])
    assert code == 2                                   # InvalidInput
    assert archive.read_bytes() == original

    assert run(capsys, "pack", str(tree), "-o", str(archive), "--force",
               "--uuid", UUID, "--created-ns", CREATED)[0] == 0
    assert archive.read_bytes() != original


def test_append_snapshots_diff_and_extract_an_older_snapshot(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    run(capsys, "pack", str(tree), "-o", str(archive))
    before = archive.stat().st_size

    (tree / "readme.txt").write_bytes(b"anla1 cli, revised\n")
    (tree / "added.txt").write_bytes(b"new in snapshot 2\n")
    code, appended = run(capsys, "append", str(archive), str(tree))
    assert code == 0
    assert appended["snapshot"] == 2
    assert appended["added"] == ["added.txt"]
    assert appended["modified"] == ["readme.txt"]
    assert appended["shared_chunks"] >= 2
    # The 15 KB blob is in there once, so the second snapshot is small.
    assert appended["grew_by"] < 4096
    assert archive.stat().st_size > before

    code, listed = run(capsys, "snapshots", str(archive))
    assert code == 0 and [s["sequence"] for s in listed["snapshots"]] == [1, 2]
    assert listed["snapshots"][1]["parent"] == listed["snapshots"][0]["snapshot_id"]

    code, changes = run(capsys, "diff", str(archive), "--from", "1", "--to", "2")
    assert code == 0 and changes["added"] == ["added.txt"]

    out = tmp_path / "old"
    code, _ = run(capsys, "extract", str(archive), "--to", str(out), "-s", "1")
    assert code == 0
    assert (out / "readme.txt").read_bytes() == b"anla1 cli\n"
    assert not (out / "added.txt").exists()


def test_list_reports_one_snapshot_at_a_time(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    run(capsys, "pack", str(tree), "-o", str(archive))
    (tree / "later.txt").write_bytes(b"later\n")
    run(capsys, "append", str(archive), str(tree))

    paths = lambda payload: {o["path"] for o in payload["objects"]}  # noqa: E731
    assert "later.txt" not in paths(run(capsys, "list", str(archive), "-s", "1")[1])
    assert "later.txt" in paths(run(capsys, "list", str(archive))[1])


def test_asking_for_a_snapshot_that_is_not_there(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    run(capsys, "pack", str(tree), "-o", str(archive))
    assert main(["list", str(archive), "-s", "9", "--json"]) == 2


def test_excluding_paths(capsys, tmp_path, tree):
    (tree / ".git").mkdir()
    (tree / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    archive = tmp_path / "a.anla"
    code, _ = run(capsys, "pack", str(tree), "-o", str(archive),
                  "--exclude", ".git", "--exclude", ".git/**")
    assert code == 0
    _, listed = run(capsys, "list", str(archive))
    assert not [o for o in listed["objects"] if o["path"].startswith(".git")]


# ---------------------------------------------------------------------------
# the exit codes that carry meaning
# ---------------------------------------------------------------------------

def test_an_unrepresentable_entry_refuses_and_writes_nothing(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    try:
        (tree / "link.txt").symlink_to(tree / "readme.txt")
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        pytest.skip("Windows without developer mode cannot create a symbolic link")

    assert main(["pack", str(tree), "-o", str(archive), "--json"]) == 9
    assert not archive.exists(), "a refused pack must not leave an archive behind"


def test_skipping_deliberately_still_reports_degraded_fidelity(capsys, tmp_path, tree):
    """It produced an archive, and it still does not exit 0.

    An operator asked for an incomplete pack and got one; a script that treats
    non-zero as failure therefore cannot mistake it for a complete archive. The
    in-archive fidelity report that would make this a recorded fact rather than a
    remembered one is Milestone 2.
    """
    archive = tmp_path / "a.anla"
    try:
        (tree / "link.txt").symlink_to(tree / "readme.txt")
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            raise
        pytest.skip("Windows without developer mode cannot create a symbolic link")

    code, packed = run(capsys, "pack", str(tree), "-o", str(archive),
                       "--skip-unsupported")
    assert code == 11
    assert [s["path"] for s in packed["skipped"]] == ["link.txt"]
    assert archive.exists()
    assert run(capsys, "verify", str(archive))[0] == 0


def test_a_corrupted_chunk_fails_verification_with_the_integrity_code(
        capsys, tmp_path, tree):
    """Exit 5 exactly, not "some error".

    The flipped byte is chosen from the manifest so it lands inside a chunk payload
    every time. A byte flipped at an arbitrary offset would sometimes hit a record
    header instead and return 4, and an assertion that accepts either has stopped
    distinguishing "the bytes are wrong" from "the structure is wrong" — which is
    the whole point of having separate codes.
    """
    from anla1.snapshot import latest_snapshot

    archive = tmp_path / "a.anla"
    run(capsys, "pack", str(tree), "-o", str(archive))
    data = bytearray(archive.read_bytes())
    chunks = latest_snapshot(bytes(data)).manifest["chunks"]
    descriptor = chunks[sorted(chunks)[0]]
    data[descriptor["payload_offset"]] ^= 0xFF
    archive.write_bytes(bytes(data))
    assert main(["verify", str(archive), "--json"]) == 5


def test_a_missing_archive_is_not_a_crash(capsys, tmp_path):
    assert main(["verify", str(tmp_path / "nope.anla"), "--json"]) == 2


def test_mtime_is_optional_in_both_directions(capsys, tmp_path, tree):
    archive = tmp_path / "a.anla"
    when = 1_600_000_000_000_000_000
    os.utime(tree / "readme.txt", ns=(when, when))

    run(capsys, "pack", str(tree), "-o", str(archive), "--no-mtime")
    _, listed = run(capsys, "list", str(archive))
    assert listed["objects"]                       # it packed
    out = tmp_path / "out"
    run(capsys, "extract", str(archive), "--to", str(out))
    assert (out / "readme.txt").stat().st_mtime_ns != when
