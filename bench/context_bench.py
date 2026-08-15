# -*- coding: utf-8 -*-
"""Measure the context layer end to end, and write what the site renders from.

    python bench/context_bench.py <transcript.jsonl>

Same discipline as `bench/run_bench.py`: every number on the page was produced by
this file, into `bench/context_addressing.json`, stamped with the revision and the
corpus it was measured against. The page cannot say anything this did not measure.

What is measured, and why each one is here rather than asserted:

* **the record** — turns in, archive out, and whether the capture was lossless;
* **the index** — segments, coverage, and the archive's digest before and after,
  because "indexing does not touch the record" is the claim the design rests on;
* **the vector plane** — both sidecar formats written and read at full scale, since
  a JSON array of decimals was the original design and its cost was estimated;
* **the search** — NumPy and the pure-Python fallback, timed, because the fallback's
  cost is the reason the refusal threshold exists;
* **the wire** — `context_address` driven over stdio JSON-RPC, which is the only
  path an agent actually has and the only one where a lazy import in a worker
  thread showed up.

The vectors are random. That is deliberate and it is stated in the output: this
measures the transport, the formats and the search, and says nothing about
retrieval quality. Retrieval quality is `bench/segment_retrieval.py`, which needs
labelled queries and an embedding model, and is reported separately.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from anla1.segment import PROJECTION_VERSION  # noqa: E402
from anla1.vectors import (  # noqa: E402
    PURE_PYTHON_BUDGET_SECONDS, have_numpy, read_vectors, write_vectors,
)

SERVER = ROOT / "tools" / "mcp" / "anla_mcp.py"
WIDTH = 768
SCHEME = "changepoint-v1"


class Wire:
    """stdio JSON-RPC to the MCP server — the path an agent has."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT),
            text=True, encoding="utf-8", bufsize=1)
        self.errors: collections.deque[str] = collections.deque(maxlen=100)
        threading.Thread(
            target=lambda: [self.errors.append(x.rstrip()) for x in self.proc.stderr],
            daemon=True).start()
        self.id = 0
        self.send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "context_bench",
                                                "version": "0"}})
        self.send("notifications/initialized", {}, notify=True)

    def send(self, method, params=None, notify=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notify:
            self.id += 1
            message["id"] = self.id
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SystemExit("server closed: " + " | ".join(self.errors)[-600:])
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == self.id:
                return payload

    def call(self, tool, **arguments):
        started = time.perf_counter()
        reply = self.send("tools/call", {"name": tool, "arguments": arguments})
        elapsed = time.perf_counter() - started
        if "error" in reply:
            raise SystemExit(f"{tool}: {reply['error']}")
        content = reply["result"]["content"]
        result = json.loads(content[0]["text"]) if content else {}
        if isinstance(result, dict) and "error" in result:
            raise SystemExit(f"{tool}: {result['error']}")
        return result, elapsed


def revision() -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=20)
        return done.stdout.strip() or "unknown"
    except Exception:                                            # noqa: BLE001
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path,
                        default=ROOT / "bench" / "context_addressing.json")
    parser.add_argument("--queries", type=int, default=5)
    args = parser.parse_args()

    import numpy as np
    if not have_numpy():                                         # pragma: no cover
        raise SystemExit("this harness measures the NumPy path too; install numpy")

    raw = args.transcript.read_bytes()
    raw = raw[:raw.rfind(b"\n") + 1]
    corpus_digest = hashlib.blake2b(raw, digest_size=16).hexdigest()
    work = pathlib.Path(tempfile.mkdtemp())
    pinned = work / "corpus.jsonl"
    pinned.write_bytes(raw)

    wire = Wire()
    archive = work / "context.anla"
    print("capture…", flush=True)
    captured, capture_seconds = wire.call("context_capture", archive=str(archive),
                                          transcript=str(pinned))
    print("index…", flush=True)
    indexed, index_seconds = wire.call("context_segment", archive=str(archive),
                                       scheme=SCHEME)

    index = json.loads(pathlib.Path(indexed["sidecar"]).read_text(encoding="utf-8"))
    keys = [s["segment_id"] for s in index["segments"]]
    block = np.random.default_rng(11).standard_normal((len(keys), WIDTH),
                                                      dtype=np.float32)

    print(f"vector plane, {len(keys):,} × {WIDTH}…", flush=True)
    identity = {"model": "synthetic-not-an-embedding", "dimensions": WIDTH,
                "revision": "unstated", "projection_version": PROJECTION_VERSION,
                "segmentation_scheme": SCHEME}

    as_json = work / "vectors.json"
    started = time.perf_counter()
    with as_json.open("w", encoding="utf-8") as handle:
        json.dump({"model": identity["model"], "dimensions": WIDTH,
                   "vectors": [{"key": k, "vector": [float(x) for x in block[i]]}
                               for i, k in enumerate(keys)]}, handle)
    json_write = time.perf_counter() - started
    started = time.perf_counter()
    json.loads(as_json.read_text(encoding="utf-8"))
    json_load = time.perf_counter() - started
    json_bytes = as_json.stat().st_size
    as_json.unlink()

    sidecar = archive.with_suffix(f".vectors-{SCHEME}.anlavec")
    started = time.perf_counter()
    written = write_vectors(sidecar, ((k, block[i]) for i, k in enumerate(keys)),
                            identity, extra={"model": identity["model"]})
    binary_write = time.perf_counter() - started
    started = time.perf_counter()
    loaded = read_vectors(sidecar)
    binary_load = time.perf_counter() - started

    probe = [float(x) for x in block[len(keys) // 3]]
    started = time.perf_counter()
    loaded.search(probe, limit=5)
    numpy_search = time.perf_counter() - started

    # The pure-Python cost, measured on a sample and stated as a projection rather
    # than run to completion — running it to completion is the seventy minutes the
    # refusal exists to avoid, and saying so is more honest than a round number.
    sample, mean = 2000, loaded.mean()
    started = time.perf_counter()
    for i in range(sample):
        row = loaded.row(i)
        centred = [x - m for x, m in zip(row, mean)]
        sum(a * b for a, b in zip(probe, centred))
    per_pair = (time.perf_counter() - started) / sample

    print("address over the wire…", flush=True)
    timings, correct, verified = [], 0, 0
    for i in range(args.queries):
        which = (i * 7919) % len(keys)
        found, seconds = wire.call("context_address", archive=str(archive),
                                   scheme=SCHEME, query="",
                                   query_vector=[float(x) for x in block[which]],
                                   limit=5, model=identity["model"])
        timings.append(seconds)
        top = found["hits"][0]
        correct += top["segment_id"] == keys[which]
        verified += bool(top["digest_verified"])

    refused, _ = wire.call("context_address", archive=str(archive), scheme=SCHEME,
                           query="", query_vector=[0.1] * 64,
                           model=identity["model"])

    document = {
        "kind": "anla:bench:context-addressing:1",
        "revision": revision(),
        "generated_at_unix_ns": time.time_ns(),
        "corpus": {
            "digest": corpus_digest,
            "transcript_bytes": captured["transcript_bytes"],
            "turns": captured["turns"],
            "archive_bytes": captured["archive_bytes"],
            "lossless": captured["complete"],
            "share_of_transcript": round(
                captured["archive_bytes"] / captured["transcript_bytes"], 4),
            "capture_seconds": round(capture_seconds, 2),
        },
        "index": {
            "scheme": SCHEME,
            "segments": indexed["segments"],
            "median_segment_bytes": indexed["median_segment_bytes"],
            "coverage": indexed["coverage"],
            "preservation_unchanged": indexed["preservation_unchanged"],
            "turns_not_fully_reachable": len(indexed["turns_not_fully_reachable"]),
            "index_seconds": round(index_seconds, 2),
        },
        "vector_plane": {
            "vectors": written["count"],
            "dimensions": WIDTH,
            "json_bytes": json_bytes,
            "json_write_seconds": round(json_write, 2),
            "json_load_seconds": round(json_load, 2),
            "binary_bytes": written["bytes"],
            "binary_write_seconds": round(binary_write, 2),
            "binary_load_seconds": round(binary_load, 3),
            "smaller_by": round(json_bytes / written["bytes"], 1),
            "loads_faster_by": round(json_load / binary_load, 0),
        },
        "search": {
            "numpy_seconds": round(numpy_search, 3),
            "pure_python_microseconds_per_pair": round(per_pair * 1e6, 1),
            "pure_python_sampled_pairs": sample,
            # Reported in seconds, from the sampled cost times the corpus size. In
            # minutes it rounded to zero, and the version of this claim that was
            # written by hand instead of computed here said seventy-three minutes
            # for a search that takes about eleven seconds.
            "pure_python_projected_seconds": round(per_pair * len(keys), 1),
            "pure_python_budget_seconds": PURE_PYTHON_BUDGET_SECONDS,
            "numpy_faster_by": round(per_pair * len(keys) / numpy_search, 0),
        },
        "wire": {
            "queries": args.queries,
            "median_seconds": round(statistics.median(timings), 2),
            "slowest_seconds": round(max(timings), 2),
            "self_retrieved": correct,
            "digest_verified": verified,
            "incomparable_on_width_mismatch": refused["incomparable"],
        },
        "honesty": {
            "vectors": "random, not embeddings — this measures the transport, the "
                       "formats and the search, and says nothing about retrieval "
                       "quality",
            "retrieval_quality": "bench/segment_retrieval.json, measured separately "
                                 "against twelve labelled queries",
        },
    }
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    c, ix, v, se, w = (document["corpus"], document["index"],
                       document["vector_plane"], document["search"],
                       document["wire"])
    print(f"\nrecord    {c['turns']:,} turns, {c['transcript_bytes']:,} → "
          f"{c['archive_bytes']:,} bytes ({c['share_of_transcript']:.0%}), "
          f"{'lossless' if c['lossless'] else 'PARTIAL'}")
    print(f"index     {ix['segments']:,} segments, median "
          f"{ix['median_segment_bytes']:.0f} B, coverage {ix['coverage']}, "
          f"preservation {'unchanged' if ix['preservation_unchanged'] else 'CHANGED'}")
    print(f"vectors   json {v['json_bytes']/1e6:.0f} MB / {v['json_load_seconds']}s "
          f"load   binary {v['binary_bytes']/1e6:.0f} MB / "
          f"{v['binary_load_seconds']}s load   {v['smaller_by']}× smaller, "
          f"{v['loads_faster_by']:.0f}× faster")
    print(f"search    numpy {se['numpy_seconds']*1000:.0f} ms   pure python "
          f"{se['pure_python_microseconds_per_pair']} µs/pair → "
          f"~{se['pure_python_projected_seconds']:.0f} s for this corpus "
          f"({se['numpy_faster_by']:.0f}x)")
    print(f"wire      {w['queries']} queries, median {w['median_seconds']}s, "
          f"{w['self_retrieved']}/{w['queries']} self-retrieved, "
          f"{w['digest_verified']}/{w['queries']} digest-verified")
    print(f"identity  {w['incomparable_on_width_mismatch']}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
