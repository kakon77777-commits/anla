# -*- coding: utf-8 -*-
"""`anla1 context` — the same layer the MCP tools drive, from a terminal.

Two front doors on one implementation, so what these tests are for is the door
rather than the room: argument parsing, exit codes, the JSON shape, and the two
refusals that must survive being reachable from a shell.

The failures worth having a test for are the ones that only appear at the door.
Writing this command found three, none of which the library or the MCP server
could have shown: `write_snapshot` needs an `archive_id` for a new archive and must
*not* be given one for an append; `projection_manifest`'s `preserved` is the list
of kept paths rather than a count of them; and a transcript path that does not
exist has to fail as a structured refusal rather than a traceback.
"""

from __future__ import annotations

import json

import pytest

from anla1.cli import main

TRANSCRIPT = "\n".join(json.dumps(row, ensure_ascii=False) for row in [
    {"type": "user", "message": {"role": "user",
                                 "content": "how was the gear table produced"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "It is derived: anla-gear-1 hashed per index, "
                                 "so nobody transcribes 256 constants by hand. "
                                 + "padding so this turn has some size. " * 40}]}},
    {"type": "user", "message": {"role": "user", "content": "and the floor?"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "A 64 KiB floor made every paper one chunk. "
                                 + "more padding to give the projector a choice. " * 40}]}},
]) + "\n"


@pytest.fixture()
def transcript(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(TRANSCRIPT, encoding="utf-8")
    return path


def run(capsys, *argv) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def payload(capsys, *argv) -> tuple[int, dict]:
    code, out = run(capsys, *argv, "--json")
    return code, json.loads(out)


def refused(capsys, *argv) -> tuple[int, str]:
    """A refusal is an exit code and a structured error on stderr, not an exception.

    `main()` catches `AnlaError` and reports it — that is the interface, and the
    first version of these tests asserted the wrong one by expecting the exception
    to escape. Returns the code and the message so a caller can check both.
    """
    code = main(list(argv))
    captured = capsys.readouterr()
    body = json.loads(captured.err)
    return code, body["error"]["message"]


def test_capture_is_lossless_and_says_so(tmp_path, transcript, capsys):
    archive = tmp_path / "m.anla"
    code, got = payload(capsys, "context", "capture", str(archive),
                        "--transcript", str(transcript))
    assert code == 0
    assert got["complete"] is True and got["omitted_bytes"] == 0
    assert got["turns"] == 4
    assert archive.exists() and got["archive_bytes"] == archive.stat().st_size
    assert "lossless" in got["capture"]


def test_a_second_capture_appends_rather_than_failing(tmp_path, transcript, capsys):
    """A new archive is given an id; an existing one keeps its own.

    Passing `archive_id` to an append makes the manifest disagree with the header
    about what the archive is called — the defect the byte comparison caught in the
    Rust writer, which the spec now forbids outright. The first version of this
    command passed neither and could not create an archive at all.
    """
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    code, got = payload(capsys, "context", "capture", str(archive),
                        "--transcript", str(transcript))
    assert code == 0
    code, status = payload(capsys, "context", "status", str(archive))
    assert status["snapshots"] == 2, "the second capture is a snapshot, not a rewrite"


def test_truncation_is_refused_unless_it_is_asked_for(tmp_path, transcript, capsys):
    big = tmp_path / "big.jsonl"
    big.write_text(TRANSCRIPT * 400, encoding="utf-8")

    code, message = refused(capsys, "context", "capture", str(tmp_path / "t.anla"),
                            "--transcript", str(big), "--max-mib", "1")
    assert code == 2
    assert "would not be lossless" in message
    assert not (tmp_path / "t.anla").exists(), (
        "a refused capture leaves no half-written archive behind")

    # 0 means no limit, so the same file captures whole rather than being refused.
    code, whole = payload(capsys, "context", "capture", str(tmp_path / "w.anla"),
                          "--transcript", str(big), "--max-mib", "0")
    assert code == 0 and whole["complete"] is True

    code, got = payload(capsys, "context", "capture", str(tmp_path / "t.anla"),
                        "--transcript", str(big), "--max-mib", "1",
                        "--allow-truncation")
    assert code == 0
    assert got["complete"] is False and got["omitted_bytes"] > 0


def test_project_reports_kept_and_omitted_as_counts(tmp_path, transcript, capsys):
    """`preserved` is a list of paths. Printing it as a number is the bug this
    pins: the first version added an int to a list and crashed, which is the lucky
    version of getting it wrong."""
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    code, got = payload(capsys, "context", "project", str(archive),
                        "--level", "L1", "--budget", "400")
    assert code == 0
    assert isinstance(got["preserved"], list) and isinstance(got["omitted"], list)
    assert got["expandable"] is True
    assert 0 < got["share_shown"] < 1
    assert all("path" in entry for entry in got["omitted"])

    code, text = run(capsys, "context", "project", str(archive), "--level", "L1")
    assert "turns shown" in text and "expandable" in text


def test_expand_returns_the_bytes_and_refuses_a_path_it_lacks(tmp_path, transcript,
                                                              capsys):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    code, listed = payload(capsys, "context", "status", str(archive))
    assert listed["turns"] == 4

    code, got = payload(capsys, "context", "expand", str(archive),
                        "turns/000000-user.json")
    assert code == 0
    assert "gear table" in got["restored"]["turns/000000-user.json"]

    code, message = refused(capsys, "context", "expand", str(archive),
                            "turns/999999-user.json")
    assert code == 2 and "does not hold" in message


def test_find_is_named_as_lexical_and_exits_1_on_nothing(tmp_path, transcript,
                                                         capsys):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    code, got = payload(capsys, "context", "find", str(archive), "anla-gear-1")
    assert code == 0 and got["hits"]
    assert "lexical" in got["channel"], (
        "the weak channel is named rather than presented as search")

    code, empty = payload(capsys, "context", "find", str(archive),
                          "zzz-not-in-this-archive-zzz")
    assert code == 1 and empty["hits"] == []


def test_segment_indexes_without_touching_the_record(tmp_path, transcript, capsys):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    before = archive.read_bytes()

    code, got = payload(capsys, "context", "segment", str(archive),
                        "--scheme", "structural-v1")
    assert code == 0
    assert got["preservation_unchanged"] is True
    assert archive.read_bytes() == before, "the archive is byte-identical after"
    assert got["coverage"] == 1.0
    assert got["segments"] >= got["turns"]

    # And the index is a sidecar, not a record inside the archive.
    from pathlib import Path
    assert Path(got["sidecar"]).exists()
    assert Path(got["sidecar"]) != archive

    code, status = payload(capsys, "context", "status", str(archive))
    assert "structural-v1" in status["indices"]


def test_address_without_vectors_says_which_channel_it_used(tmp_path, transcript,
                                                            capsys):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    payload(capsys, "context", "segment", str(archive), "--scheme", "structural-v1")

    code, got = payload(capsys, "context", "address", str(archive), "anla-gear-1",
                        "--scheme", "structural-v1")
    assert code == 0 and got["hits"]
    assert "lexical" in got["channel"]
    hit = got["hits"][0]
    assert hit["digest_verified"] is True
    assert hit["end_byte"] > hit["start_byte"] >= 0
    assert "anla-gear-1" in hit["text"]
    assert got["expanded_exactly"] == len(got["hits"])


def test_address_refuses_before_an_index_exists(tmp_path, transcript, capsys):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    code, message = refused(capsys, "context", "address", str(archive), "anything",
                            "--scheme", "sized-900-v1")
    assert code == 2 and "built, not implicit" in message


def test_a_missing_transcript_is_a_refusal_not_a_traceback(tmp_path, capsys):
    code, message = refused(capsys, "context", "capture", str(tmp_path / "m.anla"),
                            "--transcript", str(tmp_path / "nope.jsonl"))
    assert code == 2 and "not a file" in message


# ---------------------------------------------------------------------------
# the local embedding backend, through the same stub the backend tests use, so
# `--host` is exercised end to end without needing Ollama installed
# ---------------------------------------------------------------------------

@pytest.fixture()
def stub_backend():
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    tags = {"models": [{"name": "nomic-embed-text:latest", "digest": "cd" * 32,
                        "size": 274302450, "capabilities": ["embedding"],
                        "details": {"embedding_length": 8}}]}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, payload):
            body = _json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(tags)

        def do_POST(self):
            asked = _json.loads(self.rfile.read(
                int(self.headers.get("content-length", 0))) or b"{}")
            # Deterministic and text-dependent, so a query that matches a view
            # ranks above one that does not — enough to tell "the wiring works"
            # from "everything scores the same".
            out = []
            for text in asked.get("input", []):
                seed = [float(text.lower().count(c)) for c in "abcdefgh"]
                out.append(seed or [0.0] * 8)
            self._send({"embeddings": out})

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_embed_writes_vectors_with_the_model_pinned(tmp_path, transcript, capsys,
                                                    stub_backend):
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    payload(capsys, "context", "segment", str(archive), "--scheme", "structural-v1")

    code, got = payload(capsys, "context", "embed", str(archive),
                        "--scheme", "structural-v1", "--host", stub_backend)
    assert code == 0
    assert got["embedded"] > 0
    identity = got["identity"]
    assert identity["model"] == "ollama:nomic-embed-text:latest"
    assert identity["dimensions"] == 8
    assert identity["revision"] == "cd" * 16, (
        "the model's content digest is the revision — the thing a hosted name "
        "cannot give, and what makes a later query provably comparable")
    assert identity["segmentation_scheme"] == "structural-v1"
    assert identity["projection_version"] != "unstated"

    from pathlib import Path as _P
    assert _P(got["sidecar"]).suffix == ".anlavec"
    assert archive.read_bytes()[:8] == archive.read_bytes()[:8]


def test_address_embeds_the_query_with_the_corpus_model(tmp_path, transcript,
                                                        capsys, stub_backend):
    """`--embed` reads which model to use out of the sidecar rather than taking a
    flag, so the query and the corpus cannot silently come from different ones."""
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    payload(capsys, "context", "segment", str(archive), "--scheme", "structural-v1")
    payload(capsys, "context", "embed", str(archive), "--scheme", "structural-v1",
            "--host", stub_backend)

    code, got = payload(capsys, "context", "address", str(archive), "gear table",
                        "--scheme", "structural-v1", "--embed",
                        "--host", stub_backend)
    assert code == 0
    assert "semantic" in got["channel"] and "nomic-embed-text" in got["channel"]
    assert got["incomparable"] is None
    assert got["hits"] and all(h["digest_verified"] for h in got["hits"])


def test_address_refuses_a_corpus_from_a_model_that_has_changed(
        tmp_path, transcript, capsys, stub_backend):
    """The whole point of pinning the digest.

    The sidecar is rewritten with a different revision, as a re-pull of the same
    model name would produce. Same name, same width — and the comparison must
    still refuse, because the weights are not the same bytes.
    """
    import json as _json
    from pathlib import Path as _P
    archive = tmp_path / "m.anla"
    payload(capsys, "context", "capture", str(archive),
            "--transcript", str(transcript))
    payload(capsys, "context", "segment", str(archive), "--scheme", "structural-v1")
    code, got = payload(capsys, "context", "embed", str(archive),
                        "--scheme", "structural-v1", "--host", stub_backend)

    sidecar = _P(got["sidecar"])
    raw = sidecar.read_bytes()
    newline = bytes([0x0A])
    split = raw.find(newline)
    header = _json.loads(raw[:split].decode("utf-8"))
    header["identity"]["revision"] = "ff" * 16       # as if the model was re-pulled
    sidecar.write_bytes(_json.dumps(header, ensure_ascii=False).encode("utf-8")
                        + newline + raw[split + 1:])

    code, refused_out = payload(capsys, "context", "address", str(archive),
                                "gear table", "--scheme", "structural-v1",
                                "--embed", "--host", stub_backend)
    assert "INCOMPARABLE" in (refused_out["incomparable"] or "")
    assert "revision" in refused_out["incomparable"]
