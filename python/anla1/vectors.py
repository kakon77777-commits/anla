# -*- coding: utf-8 -*-
"""The vector plane, at the size one real conversation actually is.

Written after measuring the thing it replaces. A JSON sidecar of 61,149 vectors at
768 dimensions is **939 MB**, and a pure-Python cosine over that corpus takes
**72 minutes for one query** — 70.9 µs per pair, measured, times 61,149. The loop
closed at 6,000 segments and could not have closed at 61,149, which means the
demonstration was quietly running on a tenth of the record and the design had a
ceiling nobody had walked into yet.

So the vector plane gets a format and a search:

* **Format.** One JSON header line — identity, keys, width, dtype — then the raw
  little-endian `float32` rows. 188 MB for the same corpus, and it loads by
  `frombuffer` rather than by parsing nine hundred megabytes of decimal text.
* **Search.** NumPy when it is installed, one matrix product; otherwise the pure
  loop with a size limit and an error that says what to install. **Not** a silent
  fallback that appears to hang: an agent given no answer for seventy minutes cannot
  tell a slow search from a broken one, and that is the failure mode this file
  exists to remove.

NumPy is optional on purpose. The preservation plane must never need it — this is
the auxiliary plane, `D(P, I) = D(P, ∅)`, and a channel that cannot run says so
rather than degrading into something indistinguishable from working.
"""

from __future__ import annotations

import array
import json
import math
import pathlib
from typing import Iterable, Sequence

__all__ = ["MAGIC", "PURE_PYTHON_LIMIT", "have_numpy", "write_vectors",
           "read_vectors", "VectorSet"]

MAGIC = "anla:context:vectors:1"

#: Above this many vectors, the pure-Python path refuses instead of running. 8,000
#: pairs is about half a second per query; 61,149 is seventy-two minutes. The limit
#: is where the answer stops arriving while the caller is still waiting for it.
PURE_PYTHON_LIMIT = 8_000


def have_numpy() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("numpy") is not None
    except (ImportError, ValueError):
        return False


class VectorSet:
    """Keys and their vectors, plus the identity of whatever produced them."""

    def __init__(self, keys: list[str], data, width: int, header: dict):
        self.keys = keys
        self.data = data                # numpy (n, w) or array('f') of n*w
        self.width = width
        self.header = header

    def __len__(self) -> int:
        return len(self.keys)

    @property
    def identity(self) -> dict:
        return self.header.get("identity") or {}

    def row(self, i: int) -> list[float]:
        if hasattr(self.data, "shape"):
            return [float(x) for x in self.data[i]]
        return list(self.data[i * self.width:(i + 1) * self.width])

    def get(self, key: str) -> list[float] | None:
        try:
            return self.row(self.keys.index(key))
        except ValueError:
            return None

    def mean(self) -> list[float]:
        """The corpus centroid, subtracted before every comparison.

        Centring is not a refinement. Uncentred, the 95th percentile of random pairs
        sat at +0.453 and real matches were inside it — the whole corpus pointed the
        same way and cosine was measuring "this is a technical conversation".
        """
        if hasattr(self.data, "shape"):
            return [float(x) for x in self.data.mean(axis=0)]
        total = [0.0] * self.width
        for i in range(len(self.keys)):
            base = i * self.width
            for j in range(self.width):
                total[j] += self.data[base + j]
        return [x / len(self.keys) for x in total]

    def search(self, query: Sequence[float], limit: int = 5,
               centre: Sequence[float] | None = None) -> list[tuple[str, float]]:
        """Top `limit` keys by centred cosine. Refuses rather than crawls."""
        if len(query) != self.width:
            raise ValueError(f"query is {len(query)}-wide and this corpus is "
                             f"{self.width}-wide — not one vector space")
        mean = list(centre) if centre is not None else self.mean()
        centred_query = [q - m for q, m in zip(query, mean)]

        if hasattr(self.data, "shape"):
            import numpy as np
            matrix = self.data - np.asarray(mean, dtype="float32")
            vector = np.asarray(centred_query, dtype="float32")
            norms = np.linalg.norm(matrix, axis=1) * float(np.linalg.norm(vector))
            with np.errstate(divide="ignore", invalid="ignore"):
                scores = np.where(norms > 0, matrix @ vector / norms, 0.0)
            top = np.argsort(-scores)[:limit]
            return [(self.keys[int(i)], float(scores[int(i)])) for i in top]

        if len(self.keys) > PURE_PYTHON_LIMIT:
            raise RuntimeError(
                f"{len(self.keys):,} vectors and no NumPy. The pure-Python search is "
                f"~71 µs per pair, so this query would take about "
                f"{len(self.keys) * 71e-6 / 60:.0f} minutes and would look like a "
                f"hang rather than an answer. Install numpy, or search a corpus "
                f"under {PURE_PYTHON_LIMIT:,} vectors.")
        scored = []
        qn = math.sqrt(sum(x * x for x in centred_query))
        for i, key in enumerate(self.keys):
            row = [x - m for x, m in zip(self.row(i), mean)]
            rn = math.sqrt(sum(x * x for x in row))
            dot = sum(a * b for a, b in zip(centred_query, row))
            scored.append((key, dot / (qn * rn) if qn and rn else 0.0))
        return sorted(scored, key=lambda kv: -kv[1])[:limit]


def write_vectors(path: pathlib.Path, rows: Iterable[tuple[str, Sequence[float]]],
                  identity: dict, extra: dict | None = None) -> dict:
    """Header line, then raw float32. Returns what was written, measured."""
    keys, flat, width = [], array.array("f"), None
    for key, vector in rows:
        if width is None:
            width = len(vector)
        elif len(vector) != width:
            raise ValueError(f"{key} is {len(vector)}-wide against {width} — these "
                             f"did not come from one model, and comparing them "
                             f"would be a confident number from an incoherent "
                             f"comparison")
        keys.append(key)
        flat.extend(float(x) for x in vector)
    if width is None:
        raise ValueError("no vectors to write")

    # float32 is the storage decision and it is a lossy one, so it is stated: the
    # vectors are auxiliary and regenerable, cosine at 1e-7 relative error changes
    # no ranking that was not already a tie, and the alternative is 2× the bytes.
    header = {"kind": MAGIC, "identity": identity, "dtype": "float32",
              "byte_order": "little", "width": width, "count": len(keys),
              "keys": keys, **(extra or {})}
    blob = json.dumps(header, ensure_ascii=False).encode("utf-8") + b"\n"
    if array.array("f").itemsize != 4:
        raise RuntimeError("this platform's float is not 4 bytes")
    import sys as _sys
    if _sys.byteorder != "little":
        flat.byteswap()
    path.write_bytes(blob + flat.tobytes())
    return {"file": str(path), "count": len(keys), "width": width,
            "bytes": len(blob) + flat.itemsize * len(flat),
            "header_bytes": len(blob)}


def read_vectors(path: pathlib.Path) -> VectorSet:
    raw = path.read_bytes()
    split = raw.find(b"\n")
    if split < 0:
        raise ValueError(f"{path.name} has no header line — not an {MAGIC} file")
    header = json.loads(raw[:split].decode("utf-8"))
    if header.get("kind") != MAGIC:
        raise ValueError(f"{path.name} is {header.get('kind')!r}, not {MAGIC!r}")
    width, count = int(header["width"]), int(header["count"])
    body = raw[split + 1:]
    if len(body) != width * count * 4:
        raise ValueError(f"{path.name} declares {count}×{width} float32 "
                         f"({width * count * 4:,} bytes) and carries {len(body):,}")

    if have_numpy():
        import numpy as np
        data = np.frombuffer(body, dtype="<f4").reshape(count, width)
    else:
        data = array.array("f")
        data.frombytes(body)
        import sys as _sys
        if _sys.byteorder != "little":
            data.byteswap()
    return VectorSet(list(header["keys"]), data, width, header)
