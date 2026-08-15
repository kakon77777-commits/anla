# -*- coding: utf-8 -*-
"""Call context_relate and context_relations over real stdio JSON-RPC.

Calling the functions directly would have worked perfectly and said nothing: the
`functools.wraps` defect that gave every tool a schema of `required: [args, kwargs]`
was invisible to in-process tests and only showed up when a client spoke the
protocol. So this speaks the protocol.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
#: An archive with the real record shape — uuids, tool ids, paths. Pass one as
#: argv[1]; without it there is nothing to derive edges from and the script says
#: so rather than passing on an empty graph, which every comparison would accept.
if len(sys.argv) < 2:
    raise SystemExit("usage: test_mcp_relations.py <archive.anla>  "
                     "(build one with `anla1 context capture` then `context segment`)")
ARCHIVE = str(pathlib.Path(sys.argv[1]).expanduser().resolve())

proc = subprocess.Popen(
    [sys.executable, str(ROOT / "tools" / "mcp" / "anla_mcp.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", bufsize=1, cwd=str(ROOT))


def call(method, params, ident):
    proc.stdin.write(json.dumps(
        {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit(f"server closed: {proc.stderr.read()[:2000]}")
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("id") == ident:
            return message


def tool(name, arguments, ident):
    reply = call("tools/call", {"name": name, "arguments": arguments}, ident)
    if "error" in reply:
        return {"_rpc_error": reply["error"]}
    content = reply["result"]["content"][0]["text"]
    return json.loads(content)


call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "0"}}, 1)
proc.stdin.write(json.dumps(
    {"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
proc.stdin.flush()

listed = call("tools/list", {}, 2)["result"]["tools"]
names = {t["name"] for t in listed}
print(f"{len(names)} tools offered")
for wanted in ("context_relate", "context_relations"):
    schema = next(t for t in listed if t["name"] == wanted)["inputSchema"]
    print(f"  {wanted}: properties {sorted(schema.get('properties', {}))}, "
          f"required {schema.get('required', [])}")
    assert "kwargs" not in schema.get("properties", {}), "wraps regression"

failures = []


def check(label, condition, detail=""):
    print(f"  {'ok ' if condition else 'BAD'} {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


print("\ncontext_relate")
related = tool("context_relate", {"archive": ARCHIVE, "scheme": "changepoint-v1"}, 3)
check("returns a graph", related.get("edges", 0) > 0, str(related.get("edges")))
check("re-derives identically", related.get("reproducible") is True)
check("the record is untouched", related.get("preservation_unchanged") is True)
check("the unbuildable kinds are named",
      "supersedes" in json.dumps(related.get("kinds", {})))

print("\ncontext_relations — a turn with a tool result")
target = None
for edge in tool("context_relations",
                 {"archive": ARCHIVE, "kinds": ["tool-result-of"], "limit": 1}, 4
                 ).get("edges", []):
    target = edge["from"]
walk = tool("context_relations", {"archive": ARCHIVE, "turn": target}, 5)
check("finds the turn", walk.get("matched", 0) > 0, f"{target} -> {walk.get('matched')}")
check("returns neighbours", bool(walk.get("neighbours")),
      str(walk.get("neighbours", [])[:3]))
check("reads the stored sidecar rather than re-deriving",
      str(walk.get("edges_source", "")).endswith(".json"), walk.get("edges_source"))
check("says it does not rank", "none" in walk.get("ranking", ""))

print("\nrefusals")
missing = tool("context_relations", {"archive": ARCHIVE, "turn": "turns/999999-x.json"}, 6)
check("an unknown turn is a structured refusal, not a traceback",
      missing.get("code") == "ANLA_NO_TURN", str(missing)[:120])
bad = tool("context_relations", {"archive": ARCHIVE, "kinds": ["phase"]}, 7)
check("an unknown kind is refused", bad.get("code") == "ANLA_UNKNOWN_EDGE_KIND")
check("and the refusal lists what is valid", "replies-to" in json.dumps(bad))

proc.stdin.close()
proc.wait(timeout=20)
print("\n" + ("every check passed" if not failures else f"FAILED: {failures}"))
raise SystemExit(1 if failures else 0)
