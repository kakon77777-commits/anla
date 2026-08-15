# -*- coding: utf-8 -*-
"""Embedding backends — where vectors come from, and what they can prove about themselves.

Nothing in ANLA computes an embedding. The division is UTF-8X's: 「AI 負責策略生成⋯
**AI 不參與解碼**」 — the model's contribution is the vector, and everything
downstream of it is deterministic and local. So this module does not *implement*
embedding; it names the ways of asking something else for one, and insists that
whatever answers can say who it is.

The identity is the point, not a formality. Two vectors of the same width from
different models compare to a confident, meaningless number that nothing downstream
can detect, so `EmbeddingIdentity` has to be filled in honestly or the comparison
must refuse. What a backend can honestly fill in differs:

* **A local model can pin its own weights.** Ollama reports a content digest per
  model, so `revision` is a hash of the thing that produced the vector rather than
  a name someone might quietly re-point. That is strictly better evidence than any
  hosted API offers, and it is the reason a local backend is not merely cheaper.
* **A hosted model cannot.** `text-embedding-3-small` is a name; the weights behind
  it can change without the name changing, and a vector made before such a change
  is not comparable with one made after it. `revision="unstated"` records that we do
  not know, rather than implying stability.

A backend is anything with `name`, `identity(model)` and `embed(texts, model)`. That
is deliberately small: the design has to admit a browser, a local server, or a
hosted API without any of them being privileged, and a fat interface would privilege
whichever one it was written against.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .embedding import EmbeddingIdentity

__all__ = ["OllamaBackend", "BackendUnavailable", "backend_for",
           "DEFAULT_OLLAMA"]

DEFAULT_OLLAMA = "http://127.0.0.1:11434"


class BackendUnavailable(RuntimeError):
    """The backend is not reachable. Distinct from "it answered with an error":
    a caller can start a local server, and cannot conjure a model that refused."""


class OllamaBackend:
    """Vectors from a model running on this machine.

    The transcripts this system archives are whole conversations. Embedding them
    through a hosted API means sending every one of them somewhere else — so a local
    backend is not only about cost or keys, it is the difference between a record
    that stays on the machine and one that does not.
    """

    name = "ollama"

    def __init__(self, host: str = DEFAULT_OLLAMA, timeout: float = 300.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    # -- plumbing ---------------------------------------------------------

    def _get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(f"{self.host}{path}",
                                        timeout=min(self.timeout, 15)) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError) as unreachable:
            raise BackendUnavailable(
                f"no Ollama at {self.host} ({unreachable}). Start it with "
                f"`ollama serve`, or point --host somewhere else.") from None

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.host}{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as failure:
            detail = failure.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{self.host}{path}: {failure.code} {detail}") from None
        except (urllib.error.URLError, OSError) as unreachable:
            raise BackendUnavailable(f"no Ollama at {self.host} "
                                     f"({unreachable})") from None

    # -- interface --------------------------------------------------------

    def available(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except BackendUnavailable:
            return False

    def models(self) -> list[dict]:
        """Every model this server holds, with the fields identity needs."""
        return [
            {"model": entry["name"],
             "digest": entry.get("digest", ""),
             "dimensions": (entry.get("details") or {}).get("embedding_length"),
             "embedding": "embedding" in (entry.get("capabilities") or []),
             "bytes": entry.get("size")}
            for entry in self._get("/api/tags").get("models", [])]

    def identity(self, model: str, *, projection_version: str = "unstated",
                 segmentation_scheme: str = "unstated") -> EmbeddingIdentity:
        """Who produced these vectors, pinned as tightly as this backend allows.

        `revision` is the model's **content digest**, so a corpus embedded today and
        a query embedded next month are comparable only if the weights are literally
        the same bytes. A hosted API cannot offer this, which is why the field
        exists at all.
        """
        found = next((m for m in self.models()
                      if m["model"] == model or m["model"].split(":")[0] == model),
                     None)
        if found is None:
            held = ", ".join(m["model"] for m in self.models()) or "none"
            raise BackendUnavailable(
                f"{self.host} has no model {model!r} — it holds: {held}. "
                f"`ollama pull {model}` first.")
        if not found["embedding"]:
            raise RuntimeError(
                f"{found['model']} does not declare the embedding capability. A "
                f"generative model will still return numbers if asked, and they "
                f"will not be embeddings.")
        return EmbeddingIdentity(
            model=f"{self.name}:{found['model']}",
            dimensions=int(found["dimensions"] or 0),
            revision=found["digest"][:32] or "unstated",
            projection_version=projection_version,
            segmentation_scheme=segmentation_scheme)

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        reply = self._post("/api/embed", {"model": model, "input": texts})
        vectors = reply.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RuntimeError(
                f"asked for {len(texts)} embeddings and got "
                f"{len(vectors) if isinstance(vectors, list) else type(vectors).__name__}"
                f" — a partial answer silently mis-pairs every vector after the gap")
        widths = {len(v) for v in vectors}
        if len(widths) != 1:
            raise RuntimeError(f"mixed widths {sorted(widths)} in one batch")
        return [[float(x) for x in v] for v in vectors]


def backend_for(name: str = "ollama", **options):
    if name != "ollama":
        raise ValueError(
            f"unknown backend {name!r}. Only 'ollama' is implemented; the interface "
            f"is `name`, `identity(model)` and `embed(texts, model)`, and it is "
            f"small on purpose so a browser or a hosted API can be added without "
            f"either being privileged.")
    return OllamaBackend(**options)
