# -*- coding: utf-8 -*-
"""An agent compressing its own context, through MCP, on this very conversation.

    python bench/native_context.py [--budget 5000] [--scheme changepoint-v1]

Everything here goes over stdio JSON-RPC to `tools/mcp/anla_mcp.py`, because the
question is not whether the library works — that is what the test suite is for — but
whether **an agent with nothing but the tool list can remember, index, address and
expand its own history.** Calling the Python functions directly would answer a
different question and would have missed, among other things, ten tools that
advertised the wrong schema and could not be called by any client at all.

The loop, and what each step has to prove:

    context_capture           the whole transcript, losslessly, and it says so
    context_segment           an index over it, and the archive is byte-identical
    context_segment_export    the views π_σ(m), with the identity to echo back
    <embed>                   the only step that needs a model
    context_attach_vectors    into the auxiliary plane, keyed by segment
    context_address           a question in, a byte range out, digest verified

The last line is the whole claim. Not "the retriever found something relevant" —
`(turn, start_byte, end_byte)` in the preserved record, with the turn's digest
checked against what the index was built from. What comes back is the record.

Needs OPENAI_API_KEY only for the embedding step. That backend is a **test**
backend; the identity travels with the vectors precisely so a local or browser
model can replace it without anything silently comparing across the two.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = ROOT / "tools" / "mcp" / "anla_mcp.py"

#: (question, anchor). None of the questions share vocabulary with the passage that
#: answers them — the case lexical matching cannot serve. The anchor is a distinctive
#: string the retriever never sees, used only to say afterwards whether the addressed
#: bytes were the right ones. Without it this script would report five confident
#: addresses and could not tell a correct one from the nearest thing in the corpus.
QUESTIONS = [
    ("how was the rolling-hash constant table produced instead of copied",
     "anla-gear-1"),
    ("why did every tool end up advertising the wrong parameters",
     "functools.wraps"),
    ("what did Windows refuse to do to a file that was mapped into memory",
     "memory-mapped"),
    ("the distinction between throwing something away and folding it up",
     "永久刪除與可展開壓縮"),
    ("what happened when a write failed halfway and the tests still passed",
     "write_text"),
]


class Wire:
    """The client half of stdio JSON-RPC. Deliberately small and unforgiving.

    stderr is drained by a thread rather than read at the end: a child's stderr pipe
    holds about 64 KB, and a child that fills it blocks inside its own write while
    the parent blocks in `readline`, both at zero CPU, looking exactly like a slow
    query.

    That was my first theory when a full-scale run stalled, and measuring killed it:
    the server emits **480 bytes** of stderr across capture, segment and export of a
    61,458-segment transcript. Two better-supported explanations turned up
    afterwards, both real and neither ruled out for that particular stall — a 429
    that the harness had no backoff for, and the host being down to 528 MB of free
    RAM because of an unrelated process, which stalls every process on the machine
    at zero CPU in exactly the same way. The drain stays because the hazard is one
    log line away from being real; it is not credited with a fix it did not make.
    """

    def __init__(self, server: pathlib.Path):
        self.proc = subprocess.Popen(
            [sys.executable, str(server)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT),
            text=True, encoding="utf-8", bufsize=1)
        self.errors: collections.deque[str] = collections.deque(maxlen=200)
        drain = threading.Thread(target=self._drain, daemon=True)
        drain.start()
        self.id = 0
        self.send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "native_context", "version": "0"}})
        self.send("notifications/initialized", {}, notify=True)

    def _drain(self):
        for line in self.proc.stderr:
            self.errors.append(line.rstrip())

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
                raise SystemExit("server closed: " +
                                 " | ".join(self.errors)[-800:])
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == self.id:
                return payload

    def call(self, tool, **arguments):
        reply = self.send("tools/call", {"name": tool, "arguments": arguments})
        if "error" in reply:
            raise SystemExit(f"{tool}: {reply['error']}")
        content = reply["result"]["content"]
        result = json.loads(content[0]["text"]) if content else {}
        if isinstance(result, dict) and "error" in result:
            raise SystemExit(f"{tool}: {result['error']}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--transcript", default="")
    parser.add_argument("--scheme", default="changepoint-v1")
    parser.add_argument("--budget", type=int, default=5000)
    parser.add_argument("--sample", default="spread", choices=("spread", "head", "tail"),
                        help="which part of the record the embedded corpus covers")
    parser.add_argument("--depth", type=int, default=20,
                        help="how deep to look for the answer before calling it a miss")
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=768)
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set (needed only for the embed step)")
    from openai import OpenAI
    # 60 s, not the 600 s default. A run that stops answering must fail while
    # someone is still watching it: at the default, two retries of one throttled
    # request is half an hour of a process at zero CPU. 429s are real here — one
    # killed a benchmark run outright — so retries go up and the ceiling comes down.
    client = OpenAI(timeout=60.0, max_retries=6)

    work = pathlib.Path(tempfile.mkdtemp())
    archive = str(work / "self.anla")
    wire = Wire(SERVER)

    captured = wire.call("context_capture", archive=archive,
                         **({"transcript": args.transcript} if args.transcript else {}))
    print(f"capture   {captured['turns']:,} turns, {captured['transcript_bytes']:,} "
          f"bytes -> {captured['archive_bytes']:,}  {captured['capture']}")
    if not captured["complete"]:
        raise SystemExit("the capture was partial; the rest of this would be a "
                         "claim about a record that is missing its front")

    indexed = wire.call("context_segment", archive=archive, scheme=args.scheme)
    print(f"index     {indexed['segments']:,} segments, median "
          f"{indexed['median_segment_bytes']:.0f} bytes, coverage "
          f"{indexed['coverage']:.4f}, preservation "
          f"{'UNCHANGED' if indexed['preservation_unchanged'] else 'CHANGED'}")

    exported = wire.call("context_segment_export", archive=archive,
                         scheme=args.scheme, limit=args.budget, sample=args.sample)
    rows = json.loads(pathlib.Path(exported["file"]).read_text(encoding="utf-8"))
    print(f"export    {len(rows):,} of {exported['eligible_segments']:,} views "
          f"({exported['sample']}), covering {exported['turns_covered']:,} of "
          f"{exported['turns_in_archive']:,} turns, {exported['characters']:,} chars")

    # The corpus is a transcript of the session that wrote this file, so it contains
    # these questions verbatim — in the source, in the output of earlier runs, in the
    # discussion of them. Embedding matches a question to itself far more strongly
    # than to its answer, and the first run of this script duly addressed the line of
    # `QUESTIONS` rather than the passage. Same class as the sentinel string that
    # matched the turn where it was typed: a live corpus that contains its own test.
    # Dropped by exact match, and counted, because a silent exclusion is a thumb on
    # the scale in the other direction.
    asked = [q.lower() for q, _ in QUESTIONS]
    keep = [r for r in rows if not any(q in r["text"].lower() for q in asked)]
    self_reference = len(rows) - len(keep)
    rows = keep
    print(f"          dropped {self_reference} segment(s) quoting the questions "
          f"themselves — this transcript records its own benchmark")

    vectors = []
    for i in range(0, len(rows), 128):
        batch = rows[i:i + 128]
        reply = client.embeddings.create(model=args.model, dimensions=args.dimensions,
                                         input=[r["text"] for r in batch])
        vectors.extend({"key": r["key"], "vector": item.embedding}
                       for r, item in zip(batch, sorted(reply.data,
                                                        key=lambda x: x.index)))
        print(f"          embedded {len(vectors)}/{len(rows)}", file=sys.stderr)
    vector_file = work / "vectors.json"
    vector_file.write_text(json.dumps({"model": args.model,
                                       "dimensions": args.dimensions,
                                       "vectors": vectors}), encoding="utf-8")

    attached = wire.call("context_attach_vectors", archive=archive,
                         vectors=str(vector_file), scheme=args.scheme)
    print(f"attach    {attached['attached']:,} of {attached['segments_in_archive']:,} "
          f"segments, identity {attached['identity_fingerprint']}, "
          f"plane {attached['scope']}/auxiliary\n")

    corpus = {r["key"]: r["text"] for r in rows}
    exact, answered, reachable, ranks = 0, 0, 0, []
    for question, anchor in QUESTIONS:
        # Is the answer even in the corpus? If it is not, a miss says nothing about
        # the retriever, and reporting it as one would be a lie in the other
        # direction.
        present = any(anchor.lower() in text.lower() for text in corpus.values())
        reachable += present
        print("          embedding the question…", file=sys.stderr)
        qv = client.embeddings.create(model=args.model, dimensions=args.dimensions,
                                      input=[question]).data[0].embedding
        print("          addressing…", file=sys.stderr)
        found = wire.call("context_address", archive=archive, scheme=args.scheme,
                          query=question, query_vector=qv, limit=args.depth,
                          model=args.model)
        if not found["hits"]:
            print(f"Q  {question}\n   nothing addressed\n")
            continue
        answered += 1
        hit = found["hits"][0]
        exact += bool(hit["digest_verified"])
        # Rank of the first hit that actually carries the answer. Reported instead
        # of a hit/miss, because "the right passage was third" and "the right
        # passage was nowhere" are different results and the first is usable.
        rank = next((i + 1 for i, h in enumerate(found["hits"])
                     if anchor.lower() in h["text"].lower()), None)
        ranks.append(rank if present else "unreachable")
        print(f"Q  {question}")
        print(f"   channel  {found['channel']}, "
              f"{found['semantic_corpus_share']:.1%} of the index carries a vector")
        print(f"   address  {hit['source_turn']} [{hit['start_byte']}:"
              f"{hit['end_byte']}]  score {hit['score']:+.3f}")
        print(f"   text     {' '.join(hit['text'].split())[:100]}")
        print(f"   expand   {hit['expand']}")
        print(f"   rank     {'the answer is not in the corpus at all' if not present
                             else f'{rank} of {len(found['hits'])} returned'
                             if rank else f'not in the top {len(found["hits"])}'}\n")

    # The mismatch case, on purpose: the same question, a query vector of a
    # different width. Cosine would happily return a number; this must not.
    refused = wire.call("context_address", archive=archive, scheme=args.scheme,
                        query=QUESTIONS[0][0], query_vector=[0.01] * 64,
                        model=args.model)
    print(f"identity  a 64-wide query against 768-wide corpus -> "
          f"{refused['incomparable'] or refused['channel']}")

    status = wire.call("context_status", archive=archive)
    print(f"\nrecord    {status['turns']:,} turns, {status['archive_bytes']:,} bytes, "
          f"{status['share_of_context']:.3f} of the raw context")
    hit_ranks = [r for r in ranks if isinstance(r, int)]
    print(f"addressed {answered}/{len(QUESTIONS)} questions")
    print(f"expanded  {exact}/{len(QUESTIONS)} to digest-verified exact bytes "
          f"(this is the invariant, and it holds regardless of relevance)")
    print(f"retrieval R@1 {sum(1 for r in hit_ranks if r == 1)}/{reachable}  "
          f"R@5 {sum(1 for r in hit_ranks if r <= 5)}/{reachable}  "
          f"R@{args.depth} {len(hit_ranks)}/{reachable}  ranks {ranks}")

    # The gate is the invariant, not the accuracy: this script exists to show that an
    # agent can drive the loop over MCP and get the record back verbatim. Retrieval
    # quality is measured with a labelled query set in bench/segment_retrieval.py,
    # and is reported above rather than folded into a pass.
    ok = (exact == len(QUESTIONS) and indexed["preservation_unchanged"]
          and refused["incomparable"] is not None)
    print("\nAI-native context compression over MCP: "
          + ("the loop closes" if ok else "NOT CLOSED"))
    missed = reachable - sum(1 for r in hit_ranks if r == 1)
    if missed:
        print(f"          {missed} question(s) had their answer in the corpus and "
              f"were not first — retrieval quality, not the loop")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
