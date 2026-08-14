# -*- coding: utf-8 -*-
"""Speak JSON-RPC to the ANLA MCP server over stdio, the way a client does.

    python tools/mcp/test_mcp.py

Importing `anla_mcp` and calling its functions would test the functions. This tests
the *server*: the handshake, the input schemas FastMCP derives from the signatures,
and the JSON that actually crosses the pipe.

The distinction paid for itself on the first run. The error-handling decorator was
written without `functools.wraps`, so every one of the ten tools ended up advertising
a schema of `required: ["args", "kwargs"]`. Each function still worked perfectly when
called directly, and no client could have called any of them.

Exits non-zero on the first thing that does not hold, so CI can run it.
"""

import collections
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "tools" / "mcp" / "anla_mcp.py"
_scratch = tempfile.TemporaryDirectory()
WORK = pathlib.Path(_scratch.name)

failures: list[str] = []


def expect(condition: bool, what: str) -> None:
    if not condition:
        failures.append(what)
    print(f"  {'ok  ' if condition else 'FAIL'} {what}")


proc = subprocess.Popen(
    [sys.executable, str(SERVER)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=str(ROOT), text=True, encoding="utf-8", bufsize=1,
)

# stderr is drained continuously rather than read once at the end. The pipe holds
# about 64 KB; a child that fills it blocks inside its own write and stops
# answering, and this script would block in readline waiting for a reply that never
# comes — both processes at zero CPU, indistinguishable from a slow call.
#
# Measured, because a full-scale run did stall and this was my first theory for it:
# the server emits **480 bytes** of stderr across capture + segment + export of a
# 61,458-segment transcript, so it was not the cause. (The stall had two better
# candidates, both real: an un-retried 429, and the host down to 528 MB of free RAM
# from an unrelated process.) The drain stays because the hazard is one log line
# away from being real; it is not credited with a fix it did not make.
_stderr: collections.deque[str] = collections.deque(maxlen=200)
threading.Thread(target=lambda: [_stderr.append(line.rstrip()) for line in proc.stderr],
                 daemon=True).start()

_id = 0


def send(method, params=None, notify=False):
    global _id
    message = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    if not notify:
        _id += 1
        message["id"] = _id
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("server closed: " + " | ".join(_stderr)[-600:])
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("id") == _id:
            return payload


def call(tool, **arguments):
    reply = send("tools/call", {"name": tool, "arguments": arguments})
    if "error" in reply:
        return {"error": str(reply["error"]), "code": "RPC_ERROR"}
    content = reply["result"]["content"]
    text = content[0]["text"] if content else "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": text, "code": "NOT_JSON"}


def show(label, data, keys=None):
    # A failure is never hidden behind a key filter, whatever keys were asked for.
    if isinstance(data, dict) and "error" in data:
        keys = None
    if keys:
        data = {k: data.get(k) for k in keys if k in data}
    print(f"  {label:<24} {json.dumps(data, ensure_ascii=False)[:260]}")


print("handshake")
hello = send("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test_mcp", "version": "0"},
})
print("  server:", hello["result"]["serverInfo"])
send("notifications/initialized", {}, notify=True)

tools = send("tools/list", {})["result"]["tools"]
print(f"\nschemas ({len(tools)} tools)")
expect(len(tools) >= 10, f"at least ten tools are advertised (got {len(tools)})")
generic = [t["name"] for t in tools
           if set(t["inputSchema"].get("required", [])) & {"args", "kwargs"}]
expect(not generic, f"no tool advertises a generic *args/**kwargs schema ({generic})")
expect(set(next(t for t in tools if t["name"] == "anla_diff")["inputSchema"]["required"])
       == {"archive", "older", "newer"}, "anla_diff advertises its real parameters")

corpus = str(ROOT / "test_demo")
archive = str(WORK / "agent.anla")

print("\nsurvey")
survey = call("anla_survey", source=corpus, sample_mib=8)
trial = survey.get("chunk_size_trial") or []
expect(len(trial) == 4, "four chunk sizes were actually packed and measured")
expect(len({r["second_snapshot_cost"] for r in trial}) > 1,
       "the candidates disagree, so the recommendation is not a constant")
plan = survey.get("recommended") or {}
best = min(trial, key=lambda r: r["second_snapshot_cost"])["chunk_avg"] if trial else None
expect(plan.get("chunk_avg") == best,
       "the recommendation is the candidate that actually measured best")
show("recommended", plan)
show("why", {"why": survey.get("why")})

print("\npack, with the plan the survey recommended")
packed = call("anla_pack", source=corpus, archive=archive, overwrite=True, **plan)
show("packed", packed, ["archive_bytes", "logical_bytes", "ratio", "objects", "chunks"])
expect(packed.get("archive_bytes", 0) > 0, "the archive was written")
expect((packed.get("packing_plan") or {}).get("avg") == plan.get("chunk_avg"),
       "the plan the agent chose is recorded IN the archive")

print("\nverify")
verified = call("anla_verify", archive=archive)
show("verify", verified, ["ok", "snapshots", "second_implementation"])
expect(verified.get("ok") is True, "the archive verifies")
second = verified.get("second_implementation")
expect(second is None or second["agrees"], "the independent reader agrees")

print("\nappend the same tree again")
appended = call("anla_append", archive=archive, source=corpus)
show("append", appended, ["added", "share_of_input", "snapshots", "inherited_chunk_avg"])
expect(appended.get("inherited_chunk_avg") == plan.get("chunk_avg"),
       "the append inherited the archive's recorded chunking rather than a default")
expect(0 < appended.get("share_of_input", 1) < 0.2,
       "a second snapshot of an unchanged tree costs a small fraction of it")

print("\ndiff 1 -> 2")
changed = call("anla_diff", archive=archive, older=1, newer=2)
show("diff", changed, ["added", "removed", "modified", "unchanged",
                       "new_chunks", "shared_chunks"])
expect(changed.get("new_chunks") == 0, "an unchanged tree stored no new chunks at all")

print("\nextract and compare against the source")
restored = call("anla_extract", archive=archive,
                destination=str(WORK / "restored"), compare_with=corpus)
show("extract", restored, ["files", "bytes_written", "byte_comparison"])
comparison = restored.get("byte_comparison") or {}
expect(comparison.get("identical") is True,
       f"every restored byte matches the source ({comparison.get('matched')} files)")

print("\nmanifest")
manifest = call("anla_manifest", archive=archive)
show("capabilities", manifest, ["required_capabilities", "optional_capabilities"])
expect(len((manifest.get("roots") or {}).get("preservation_root", "")) == 64,
       "the manifest reports a preservation root")

print("\ncompare the two writers")
compared = call("anla_compare_writers", source=corpus)
show("compare", compared, ["identical", "python_bytes", "rust_bytes"])
if "error" in compared:
    print("       skipped: the rust writer is not built")
else:
    expect(compared.get("identical") is True, "both writers emit identical bytes")

print("\ncontext: an agent capturing its own")
ctx = str(WORK / "ctx.anla")

# A limit that would drop the front must refuse rather than return a partial
# capture that reports itself like a whole one. Drilled first, with a limit small
# enough that any real session exceeds it, so this asserts the refusal rather than
# hoping for it.
refused = call("context_capture", archive=str(WORK / "trunc.anla"), max_mib=1)
show("truncation refused", refused)
expect("error" in refused and "would not be lossless" in refused.get("error", ""),
       "a capture that would silently drop the front of a transcript is refused")

partial = call("context_capture", archive=str(WORK / "trunc.anla"), max_mib=1,
               allow_truncation=True)
show("truncation declared", partial, ["complete", "transcript_bytes", "omitted_bytes"])
expect(partial.get("complete") is False and partial.get("omitted_bytes", 0) > 0
       and partial.get("omitted_range", {}).get("end_byte") == partial["omitted_bytes"],
       "a deliberate truncation names the byte range it dropped")

captured = call("context_capture", archive=ctx)
if "error" in captured:
    print(f"  skipped: {captured['error'][:90]}")
else:
    show("capture", captured, ["turns", "context_bytes", "archive_bytes",
                               "deduplicated_turns", "complete", "omitted_bytes"])
    expect(captured.get("turns", 0) > 0, "a transcript was found and turned into turns")
    expect(captured.get("complete") is True and captured.get("omitted_bytes") == 0,
           "the default capture states that it is lossless, and it is")

    projected = call("context_project", archive=ctx, level="L1", budget_bytes=8000)
    show("project", projected, ["preserved", "bytes_shown", "share_shown", "expandable"])
    expect(projected.get("expandable") is True,
           "every omission carries the path that restores it")
    expect(0 < projected.get("share_shown", 1) < 0.2,
           "the projection is a small fraction of the whole context")
    expect(all("path" in o and "hint" in o for o in projected.get("omitted", [])),
           "the manifest names its omissions rather than counting them")

    # MNVP §6.2 through the wire, not only inside the library.
    wide = call("context_project", archive=ctx, level="L2", budget_bytes=8000)
    expect(wide.get("preserved", 0) >= projected.get("preserved", 0),
           "L2 preserves at least as much as L1")

    paths = [o["path"] for o in projected.get("omitted", [])[:4]]
    if paths:
        back = call("context_expand", archive=ctx, paths=paths)
        show("expand", back, ["total_bytes"])
        expect(len(back.get("restored", {})) == len(paths),
               "every omitted turn asked for came back")

    hunted = call("context_find", archive=ctx, query="the")
    expect("boundary" in hunted and "Recall" in hunted.get("boundary", ""),
           "retrieval carries paper 07's boundary: Recall is not Care")
    expect(any("ABSENT" in v for v in hunted.get("channels", {}).values()),
           "the semantic and phase channels are declared absent, not approximated")
    expect(0 < (hunted.get("share_of_history") or 1) < 0.2,
           "the resonant domain is a small subset of the shared history")
    expect(all(h.get("terms") and h.get("why") for h in hunted.get("in_domain", [])),
           "every memory says which terms of psi put it there")
    # Generated, not written down. A literal sentinel string appears in this file,
    # this file's edits appear in the transcript, and the archive is *of* the
    # transcript — so a hardcoded "matches nothing" query matched the turn where it
    # was typed. Now that search reads the raw record rather than extracted text,
    # a corpus that contains its own test is a real hazard rather than a joke.
    absent_query = "nomatch-" + uuid.uuid4().hex
    nothing = call("context_find", archive=ctx, query=absent_query, moment=absent_query,
                   threshold=0.9)
    expect(nothing.get("in_domain") == []
           and "clears the threshold" in nothing.get("disclosure", ""),
           "nothing clearing the threshold says so rather than returning a bare zero")

    print("\nsemantic addressing: index, address, expand to exact bytes")
    # Deliberately the 1 MiB archive rather than `ctx`. `context_capture` with no
    # transcript takes whatever session on this machine is newest, so `ctx` has been
    # anything from 6,000 to 10,569 turns between runs of this file — and a test
    # whose runtime is set by which conversation someone had last is a test that
    # eventually gets skipped. The declared-partial archive is a real archive with
    # real turns and a bounded size; the assertions below are about the index and
    # the addressing, not about how much history there is.
    small = str(WORK / "trunc.anla")
    indexed = call("context_segment", archive=small, scheme="structural-v1")
    show("segment", indexed, ["segments", "coverage", "preservation_unchanged",
                              "median_segment_bytes"])
    expect(indexed.get("preservation_unchanged") is True,
           "indexing the record did not change one byte of it")
    expect(indexed.get("coverage") == 1.0 and not indexed.get("turns_not_fully_reachable"),
           "every byte of every turn is reachable through some segment")
    expect(indexed.get("segments", 0) > indexed.get("turns", 0),
           "the index is finer than the turn it indexes")

    # A second family over the same memory. σ₁ and σ₂ coexist; neither is a
    # migration, and the first index must still be readable afterwards.
    second = call("context_segment", archive=small, scheme="sized-900-v1")
    expect(second.get("preservation_unchanged") is True
           and second.get("segments") != indexed.get("segments"),
           "a second scheme adds a second index rather than replacing the first")

    # The needle is taken OUT of this archive rather than written down. The first
    # version searched for "preservation plane", which is a fact about the corpus
    # the harness does not control: `context_capture` takes the machine's newest
    # session, that turned out to be an unrelated 10,569-turn conversation, the
    # phrase was not in it, and the run returned zero hits — while the assertion
    # `all(needle in h["text"] for h in hits)` passed, because every element of an
    # empty list satisfies anything.
    # Paths from a projection of *this* archive. The first attempt reused the
    # omission list from `ctx`, whose turn paths do not exist in `small`, so the
    # expansion came back empty and the needle came back empty with it.
    inside = call("context_project", archive=small, level="L1", budget_bytes=4000)
    sample = call("context_expand", archive=small,
                  paths=[o["path"] for o in inside.get("omitted", [])[:8]])
    words = sorted({w.lower() for w in
                    "".join((sample.get("restored") or {}).values()).split()
                    if len(w) >= 9 and w.isalpha()})
    # No fallback to a common word. The first version fell back to "the", which
    # every segment contains, so the search would have "found" its needle no matter
    # what the code did — a passing assertion measuring nothing. Better to fail and
    # say the archive gave the test nothing distinctive to look for.
    expect(bool(words), "the archive yielded a distinctive word to search for")
    needle = words[len(words) // 2] if words else ""

    addressed = call("context_address", archive=small, scheme="structural-v1",
                     query=needle, limit=3)
    show("address", addressed, ["channel", "expanded_exactly", "segments_searched"])
    expect("lexical" in addressed.get("channel", ""),
           "with no vectors attached the weak channel is named, not blended in")
    hits = addressed.get("hits", [])
    expect(len(hits) > 0,
           f"a string taken out of this archive is found in it again ({needle!r})")
    expect(len(hits) > 0 and all(h["digest_verified"] for h in hits),
           "every hit's turn digest matches what the index was built against")
    expect(len(hits) > 0 and all(needle in h["text"].lower() for h in hits),
           "the addressed bytes really contain what was asked for")

    # Expand exactly: go from the address back to the record through a *different*
    # tool, and check the byte range against the turn that context_expand returns.
    top = hits[0]
    restored = call("context_expand", archive=small, paths=[top["source_turn"]])
    body = (restored.get("restored") or {}).get(top["source_turn"], "")
    expect(bool(body), "the addressed turn came back from the record")
    expect(0 <= top["start_byte"] < top["end_byte"] <= len(body.encode("utf-8")),
           "the address is a byte range inside the turn as the record stores it")

    refused = call("context_address", archive=small, scheme="structural-v1",
                   query=needle, query_vector=[0.1] * 8)
    expect("REFUSED" in refused.get("channel", ""),
           "a query vector with no corpus vectors is refused rather than ignored")

    # D(P, I) = D(P, ∅), checked rather than asserted. Vectors are attached, the
    # archive's bytes are compared before and after, then the whole intelligence
    # plane is deleted and the record is compared again. Eight fabricated vectors
    # are enough: this measures where they are stored, not what they mean.
    import hashlib as _h
    before_bytes = _h.blake2b(pathlib.Path(small).read_bytes(), digest_size=16).hexdigest()
    keys = [h["segment_id"] for h in hits]
    fake = WORK / "fake-vectors.json"
    fake.write_text(json.dumps({
        "model": "fabricated-for-this-test", "dimensions": 8,
        "vectors": [{"key": k, "vector": [(i + j) / 10 for j in range(8)]}
                    for i, k in enumerate(keys)]}), encoding="utf-8")
    stored = call("context_attach_vectors", archive=small, vectors=str(fake),
                  scheme="structural-v1", model="fabricated-for-this-test")
    show("attach", stored, ["attached", "sidecar_bytes", "identity_fingerprint",
                            "search_backend"])
    after_bytes = _h.blake2b(pathlib.Path(small).read_bytes(), digest_size=16).hexdigest()
    expect(after_bytes == before_bytes,
           "attaching the intelligence plane left the archive byte-identical")
    expect(pathlib.Path(stored["sidecar"]).exists()
           and pathlib.Path(stored["sidecar"]).suffix == ".anlavec",
           "the vectors are a sidecar beside the archive, not a record inside it")

    # A query from a different model at the same width is the trap: cosine would
    # answer. Width here is 8 either way, and only the model name differs.
    mismatched = call("context_address", archive=small, scheme="structural-v1",
                      query=needle, query_vector=[0.2] * 8, model="a-different-model")
    expect("INCOMPARABLE" in (mismatched.get("incomparable") or ""),
           "same width, different model -> INCOMPARABLE rather than a number")

    pathlib.Path(stored["sidecar"]).unlink()
    without = call("context_address", archive=small, scheme="structural-v1",
                   query=needle, limit=1)
    gone = _h.blake2b(pathlib.Path(small).read_bytes(), digest_size=16).hexdigest()
    expect(gone == before_bytes and len(without.get("hits", [])) > 0,
           "deleting the whole intelligence plane leaves the record intact and "
           "readable")
    expect("lexical" in without.get("channel", ""),
           "with the vectors gone the semantic channel says so instead of degrading")

print("\nerrors an agent can act on")
absent = call("anla_verify", archive=str(WORK / "nope.anla"))
show("missing archive", absent)
expect("error" in absent and "code" in absent,
       "a bad path comes back as a structured error, not a traceback")
bad_codec = call("anla_pack", source=corpus, archive=str(WORK / "x.anla"),
                 codec="gzip", overwrite=True)
show("unknown codec", bad_codec)
expect("error" in bad_codec, "an unknown codec is refused rather than guessed at")

proc.stdin.close()
proc.terminate()

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print("every check passed")
