# -*- coding: utf-8 -*-
"""Embedding backends — what a backend must prove about itself, and what it must refuse.

Run against a stub server rather than a real Ollama, for the reason a mock is
usually wrong and is right here: these tests are about the **protocol contract** —
short answers, mixed widths, a missing model, a generative model asked for
embeddings — and a real server will not produce those on demand. The live path is
covered by actually using it (`anla1 context embed`), which no stub can stand in for.

The property worth the most here is that a local model can pin its own weights. A
hosted model is a *name*, and the weights behind it can change without the name
changing; Ollama reports a content digest, so `revision` becomes a hash of the thing
that made the vector. That is what makes a later query provably comparable, and it
is checked rather than assumed.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from anla1.backends import BackendUnavailable, OllamaBackend, backend_for

DIGEST = "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"

TAGS = {"models": [
    {"name": "nomic-embed-text:latest", "digest": DIGEST, "size": 274302450,
     "capabilities": ["embedding"],
     "details": {"embedding_length": 768, "quantization_level": "F16"}},
    {"name": "llama3:8b", "digest": "ff" * 32, "size": 4_700_000_000,
     "capabilities": ["completion"], "details": {"embedding_length": None}},
]}

#: What /api/embed should answer next. Set per test, so one stub covers every shape
#: of wrong answer the contract has to survive.
REPLY: dict = {}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *_):            # keep the test output readable
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(TAGS if self.path == "/api/tags" else {})

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        asked = json.loads(self.rfile.read(length) or b"{}")
        if REPLY.get("status", 200) != 200:
            return self._send({"error": REPLY.get("error", "no")}, REPLY["status"])
        if "embeddings" in REPLY:
            return self._send({"embeddings": REPLY["embeddings"]})
        width = REPLY.get("width", 768)
        self._send({"embeddings": [[0.1] * width for _ in asked.get("input", [])]})


@pytest.fixture()
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    REPLY.clear()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_identity_pins_the_weights_by_digest(server):
    """The reason a local backend is not merely cheaper."""
    identity = OllamaBackend(server).identity(
        "nomic-embed-text", projection_version="jsonl-slice-1",
        segmentation_scheme="changepoint-v1")
    assert identity.model == "ollama:nomic-embed-text:latest"
    assert identity.dimensions == 768
    assert identity.revision == DIGEST[:32], (
        "revision is the model's content digest, not 'unstated' — a hosted API "
        "cannot offer this and that is why the field exists")
    assert identity.projection_version == "jsonl-slice-1"
    assert identity.segmentation_scheme == "changepoint-v1"


def test_a_re_pulled_model_is_a_different_identity(server):
    """Two corpora embedded either side of a re-pull must not compare.

    Simulated by moving the digest, which is the only thing that would change:
    same name, same width, different weights.
    """
    from anla1.embedding import comparable
    before = OllamaBackend(server).identity("nomic-embed-text")
    TAGS["models"][0]["digest"] = "ab" * 32
    try:
        after = OllamaBackend(server).identity("nomic-embed-text")
    finally:
        TAGS["models"][0]["digest"] = DIGEST
    ok, reason = comparable(before, after)
    assert not ok and "revision" in reason


def test_a_model_it_does_not_hold_says_what_it_holds(server):
    with pytest.raises(BackendUnavailable) as refused:
        OllamaBackend(server).identity("some-other-model")
    assert "nomic-embed-text" in str(refused.value), (
        "the refusal lists what is available rather than only what is missing")
    assert "ollama pull" in str(refused.value)


def test_a_generative_model_is_refused_for_embeddings(server):
    """It would return numbers. They would not be embeddings, and nothing
    downstream could tell — the same shape as comparing two models by width."""
    with pytest.raises(RuntimeError, match="embedding capability"):
        OllamaBackend(server).identity("llama3:8b")


def test_a_short_answer_is_refused_rather_than_mis_paired(server):
    """Three texts in, two vectors back: every pairing after the gap is wrong, and
    a zip() would silently produce them. This is the defect that has no symptom."""
    REPLY["embeddings"] = [[0.1] * 768, [0.2] * 768]
    with pytest.raises(RuntimeError, match="mis-pairs"):
        OllamaBackend(server).embed(["a", "b", "c"], "nomic-embed-text")


def test_mixed_widths_in_one_batch_are_refused(server):
    REPLY["embeddings"] = [[0.1] * 768, [0.2] * 512]
    with pytest.raises(RuntimeError, match="mixed widths"):
        OllamaBackend(server).embed(["a", "b"], "nomic-embed-text")


def test_the_happy_path_returns_one_vector_per_text(server):
    got = OllamaBackend(server).embed(["a", "b", "c"], "nomic-embed-text")
    assert len(got) == 3 and {len(v) for v in got} == {768}
    assert all(isinstance(x, float) for x in got[0])


def test_no_texts_asks_nothing(server):
    assert OllamaBackend(server).embed([], "nomic-embed-text") == []


def test_an_http_error_is_reported_with_its_body(server):
    REPLY.update({"status": 400, "error": "model requires more system memory"})
    with pytest.raises(RuntimeError, match="more system memory"):
        OllamaBackend(server).embed(["a"], "nomic-embed-text")


def test_an_unreachable_server_is_distinguishable_from_a_refusal():
    """A caller can start a local server; it cannot conjure a model that said no.
    Those are different actions, so they are different exceptions."""
    backend = OllamaBackend("http://127.0.0.1:1")     # nothing listens on port 1
    assert backend.available() is False
    with pytest.raises(BackendUnavailable, match="no Ollama"):
        backend.models()


def test_available_is_true_when_it_is(server):
    assert OllamaBackend(server).available() is True


def test_an_unknown_backend_names_the_interface(server):
    with pytest.raises(ValueError) as refused:
        backend_for("some-other-provider")
    assert "identity" in str(refused.value) and "embed" in str(refused.value)
    assert isinstance(backend_for("ollama", host=server), OllamaBackend)
