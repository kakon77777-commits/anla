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

import json
import pathlib
import subprocess
import sys
import tempfile
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
            raise SystemExit("server closed: " + (proc.stderr.read() or "")[-600:])
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
captured = call("context_capture", archive=ctx, max_mib=4)
if "error" in captured:
    print(f"  skipped: {captured['error'][:90]}")
else:
    show("capture", captured, ["turns", "context_bytes", "archive_bytes",
                               "deduplicated_turns"])
    expect(captured.get("turns", 0) > 0, "a transcript was found and turned into turns")

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
    expect("disclosure" in hunted and hunted.get("channels_absent"),
           "search discloses its confidence and which channels it does not have")
    # Generated, not written down. A literal sentinel string appears in this file,
    # this file's edits appear in the transcript, and the archive is *of* the
    # transcript — so a hardcoded "matches nothing" query matched the turn where it
    # was typed. Now that search reads the raw record rather than extracted text,
    # a corpus that contains its own test is a real hazard rather than a joke.
    absent_query = "nomatch-" + uuid.uuid4().hex
    nothing = call("context_find", archive=ctx, query=absent_query)
    expect(nothing.get("hits") == [] and "no turn matched" in nothing.get("disclosure", ""),
           "a query matching nothing says so rather than returning a bare zero")

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
