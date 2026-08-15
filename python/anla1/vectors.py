# -*- coding: utf-8 -*-
"""The vector plane, at the size one real conversation actually is.

Written after measuring the thing it replaces, at full scale rather than by
extrapolation. 61,458 vectors at 768 dimensions, both formats written and read:

    JSON array of decimals   978 MB   write 85.7 s   load 24.3 s
    float32 + JSON header    192 MB   write 16.6 s   load  0.10 s   search 152 ms

**5.1× smaller and it loads two orders of magnitude faster**, which is the whole
case for the format: a JSON array of decimals is a gigabyte of text to parse before
the first comparison.

* **Format.** One JSON header line — identity, keys, width, dtype — then the raw
  little-endian `float32` rows, loaded by `frombuffer`.
* **Search.** NumPy when it is installed, one matrix product; otherwise the pure
  loop, which is projected from a measured per-element cost and refused when that
  projection exceeds a stated budget.

**A correction, because the first version of this file got it wrong by a factor of
a thousand.** It said the pure-Python search was "73 minutes for one query" and
refused above 8,000 vectors on that basis. The arithmetic was 70.9 µs × 61,458 read
as 4,357 seconds; it is **4.4 seconds**. Under load the same corpus measures 186 µs
a pair and **11 seconds** — slow, worth a warning, and nothing like a hang. The
refusal at 8,000 vectors would have fired at **1.5 seconds**.

So the limit is no longer a magic number defended by a wrong story. It is a time
budget: project `count × width × PURE_PYTHON_SECONDS_PER_ELEMENT`, refuse only if
that exceeds `PURE_PYTHON_BUDGET_SECONDS`, and put the projection in the message so
the caller can judge it rather than take the threshold on trust.

NumPy is optional on purpose. The preservation plane must never need it — this is
the auxiliary plane, `D(P, I) = D(P, ∅)`, and a channel that cannot run says so
rather than degrading into something indistinguishable from working.
"""

from __future__ import annotations

import array
import json
import math
import pathlib
import sys
from typing import Iterable, Sequence

__all__ = ["MAGIC", "PURE_PYTHON_BUDGET_SECONDS", "PURE_PYTHON_SECONDS_PER_ELEMENT",
           "have_numpy", "pure_python_projection", "write_vectors", "read_vectors",
           "VectorSet"]

#: Imported here, at module import, and never inside a function.
#:
#: It was lazy at first — `import numpy` inside `read_vectors`, which reads as the
#: polite way to keep an optional dependency optional. Over MCP that deadlocked.
#: FastMCP runs a synchronous tool in a worker thread, so the *first* numpy import
#: in the server process happened off the main thread, and the call never returned:
#: the client sat in `readline` and the server sat at 37 s of CPU and stopped. The
#: identical call took 0.2 s in-process, which is why it survived every test that
#: imported the module instead of speaking to the server.
#:
#: Optional still means optional — `None` here is a supported state and the search
#: falls back and says so. What is not supported is discovering that at an
#: unpredictable moment on an unpredictable thread.
try:
    import numpy as _np
except ImportError:                                             # pragma: no cover
    _np = None

MAGIC = "anla:context:vectors:1"

#: Measured, at width 768, on a loaded Windows host: 186 µs per pair ÷ 768 elements.
#: Per *element* rather than per pair, because the cost scales with the width and a
#: per-pair constant silently assumes one.
PURE_PYTHON_SECONDS_PER_ELEMENT = 2.4e-7

#: How long a search may take before the pure-Python path refuses instead of running.
#: Thirty seconds is the point where a caller stops reading the answer as slow and
#: starts reading it as broken. It is a *stated* budget: the refusal quotes its own
#: projection, so a caller can disagree with the number rather than with a constant.
PURE_PYTHON_BUDGET_SECONDS = 30.0


def have_numpy() -> bool:
    return _np is not None


def pure_python_projection(count: int, width: int) -> float:
    """Seconds the pure-Python search is expected to take. Public, so a caller can
    ask before committing to it rather than discovering it by waiting."""
    return count * width * PURE_PYTHON_SECONDS_PER_ELEMENT


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
            matrix = self.data - _np.asarray(mean, dtype="float32")
            vector = _np.asarray(centred_query, dtype="float32")
            norms = _np.linalg.norm(matrix, axis=1) * float(_np.linalg.norm(vector))
            with _np.errstate(divide="ignore", invalid="ignore"):
                scores = _np.where(norms > 0, matrix @ vector / norms, 0.0)
            top = _np.argsort(-scores)[:limit]
            return [(self.keys[int(i)], float(scores[int(i)])) for i in top]

        projected = pure_python_projection(len(self.keys), self.width)
        if projected > PURE_PYTHON_BUDGET_SECONDS:
            raise RuntimeError(
                f"{len(self.keys):,} vectors × {self.width} without NumPy projects to "
                f"about {projected:.0f} s for this one query, over the "
                f"{PURE_PYTHON_BUDGET_SECONDS:.0f} s budget — long enough to read as "
                f"a hang rather than an answer. Install numpy, or search a smaller "
                f"corpus. The projection is "
                f"{PURE_PYTHON_SECONDS_PER_ELEMENT * 1e9:.0f} ns per element, "
                f"measured; disagree with it by measuring your own.")
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
    if sys.byteorder != "little":
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

    if _np is not None:
        data = _np.frombuffer(body, dtype="<f4").reshape(count, width)
    else:
        data = array.array("f")
        data.frombytes(body)
        if sys.byteorder != "little":
            data.byteswap()
    return VectorSet(list(header["keys"]), data, width, header)
