# -*- coding: utf-8 -*-
"""Speak Streamable HTTP to the ANLA MCP server, the way a remote client does.

    python tools/mcp/test_mcp_http.py

`test_mcp.py` covers stdio, which is one client and one process. This covers the
transport two clients share — Claude Code and Codex pointed at one URL — and the
thing that only exists because of it: **authentication**.

Three properties, and the third is the one worth having a test for:

* the server serves, and a real tool call round-trips over HTTP with a session id;
* a bearer token is enforced — no token and a wrong token are both 401, and the
  right one is 200. Drilled in all three directions, because a guard tested only
  with the correct credential passes just as well when it is checking nothing;
* **binding beyond loopback without a token is refused**, not warned about. These
  tools read and write arbitrary paths; on loopback that is the local agent's own
  authority, and on any other interface it is remote code acting as the user.

Exits non-zero on the first thing that does not hold.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "tools" / "mcp" / "anla_mcp.py"
TOKEN = "test-token-not-a-secret"

failures: list[str] = []


def expect(condition: bool, what: str) -> None:
    if not condition:
        failures.append(what)
    print(f"  {'ok  ' if condition else 'FAIL'} {what}")


class Client:
    def __init__(self, url: str, token: str = ""):
        self.url, self.token, self.session = url, token, None

    def post(self, payload, notify=False, want_status=False):
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        if self.session:
            request.add_header("mcp-session-id", self.session)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                self.session = response.headers.get("mcp-session-id") or self.session
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as failure:
            return failure.code if want_status else {"http_error": failure.code}
        if want_status:
            return status
        if notify:
            return None
        for line in raw.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        return json.loads(raw) if raw.strip() else None

    def handshake(self):
        hello = self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05",
                                      "capabilities": {},
                                      "clientInfo": {"name": "test_mcp_http",
                                                     "version": "0"}}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                  notify=True)
        return hello

    def call(self, tool, **arguments):
        reply = self.post({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                           "params": {"name": tool, "arguments": arguments}})
        content = reply["result"]["content"]
        return json.loads(content[0]["text"]) if content else {}


def serve(port: int, token: str = "", share: str = "") -> subprocess.Popen:
    command = [sys.executable, str(SERVER), "--http", "--port", str(port)]
    if token:
        command += ["--token", token]
    if share:
        command += ["--share", share]
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8")
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(60):
        if process.poll() is not None:
            raise SystemExit(f"server exited: {(process.stderr.read() or '')[-500:]}")
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="GET"),
                                   timeout=2)
            break
        except urllib.error.HTTPError:
            break                      # answered, which is all we are waiting for
        except Exception:              # noqa: BLE001
            time.sleep(0.5)
    return process


print("open server, no auth, loopback")
plain = serve(8894)
try:
    client = Client("http://127.0.0.1:8894/mcp")
    hello = client.handshake()
    print(f"  server: {hello['result']['serverInfo']}")
    expect(hello["result"]["serverInfo"]["name"] == "anla", "it is the anla server")
    expect(bool(client.session), "the server issued a session id")

    tools = client.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                         "params": {}})["result"]["tools"]
    expect(len(tools) >= 20, f"all the tools are there over HTTP ({len(tools)})")
    generic = [t["name"] for t in tools
               if set(t["inputSchema"].get("required", [])) & {"args", "kwargs"}]
    expect(not generic, f"no tool advertises a generic schema ({generic})")

    # A real call, not just a handshake: the transport has to carry a measured
    # result back, and `survey` is the one that actually packs samples to answer.
    surveyed = client.call("anla_survey", source=str(ROOT / "test_demo"),
                           sample_mib=4)
    print(f"  survey: {json.dumps(surveyed.get('recommended'), ensure_ascii=False)}")
    expect((surveyed.get("recommended") or {}).get("chunking") == "cdc",
           "a real tool call round-trips over HTTP with a measured answer")
finally:
    plain.terminate()

print("\nwith a bearer token")
guarded = serve(8895, TOKEN)
try:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "t", "version": "0"}}}
    url = "http://127.0.0.1:8895/mcp"
    none_given = Client(url).post(payload, want_status=True)
    wrong = Client(url, "not-the-token").post(payload, want_status=True)
    right = Client(url, TOKEN).post(payload, want_status=True)
    print(f"  none {none_given} · wrong {wrong} · right {right}")
    expect(none_given == 401, "no token is refused")
    expect(wrong == 401, "a wrong token is refused, so the guard compares rather "
                         "than merely checks for presence")
    expect(right == 200, "the right token is accepted, so the guard is not "
                         "refusing everything")
finally:
    guarded.terminate()

print("\nexposure requires authentication")
refused = subprocess.run(
    [sys.executable, str(SERVER), "--http", "--host", "0.0.0.0"], cwd=str(ROOT),
    capture_output=True, text=True, encoding="utf-8", timeout=120)
message = (refused.stderr or "") + (refused.stdout or "")
print(f"  exit {refused.returncode}: {message.strip().splitlines()[-1][:100]}")
expect(refused.returncode != 0, "binding 0.0.0.0 without a token exits non-zero")
expect("--token" in message and "authentication" in message,
       "the refusal names the fix rather than only the problem")

with_token = subprocess.run(
    [sys.executable, str(SERVER), "--http", "--host", "0.0.0.0", "--token", TOKEN,
     "--port", "8896", "--help"], cwd=str(ROOT), capture_output=True, text=True,
    encoding="utf-8", timeout=120)
expect(with_token.returncode == 0,
       "the same host with a token is allowed, so the refusal is about the missing "
       "token and not about the host")

print("\nshare mode: read-only, confined")
SHARE = ROOT / "test_demo"
shared = serve(8897, share=str(SHARE))
try:
    client = Client("http://127.0.0.1:8897/mcp")
    client.handshake()
    names = {t["name"] for t in client.post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
         "params": {}})["result"]["tools"]}
    print(f"  {len(names)} tools offered")

    # The writing tools must be ABSENT, not merely refusing. A tool that is not
    # advertised cannot be attempted by a model that reaches the URL; a tool that
    # refuses is one whose refusal has to be right every single time.
    import importlib.util
    spec = importlib.util.spec_from_file_location("anla_mcp_probe", SERVER)
    probe = importlib.util.module_from_spec(spec)
    sys.modules["anla_mcp_probe"] = probe
    spec.loader.exec_module(probe)
    declared = set(probe.WRITING_TOOLS)
    expect(not (names & declared),
           f"every declared writing tool is absent from share mode "
           f"({sorted(names & declared) or 'none leaked'})")
    expect(len(names) >= 10, f"the read-only tools are still there ({len(names)})")

    # Re-derived from the source rather than trusted. The hand-written list was
    # wrong once — it omitted a tool that takes an `out` path and writes it — and a
    # grep for write calls was wrong in the other direction, missing a write that
    # happens inside a helper. This asserts the two agree, so the next tool that
    # grows a write has to be classified before this passes.
    import re
    source = SERVER.read_text(encoding="utf-8")
    bodies = re.split(r"\n@mcp\.tool\(\)\n@_guard\ndef ", source)
    pattern = re.compile(r"write_text|write_bytes|write_snapshot|restore_tree|"
                         r"write_vectors|shutil\.(?:copy|move)|\.rename\(")
    suspected = set()
    for chunk in bodies[1:]:
        tool = chunk.split("(")[0]
        body = chunk.split("\n@mcp.tool")[0]
        if pattern.search(body) and "tempfile" not in body:
            suspected.add(tool)
    missing = suspected - declared
    print(f"  source says {len(suspected)} write to a caller-named path; "
          f"WRITING_TOOLS declares {len(declared)}")
    expect(not missing,
           f"no tool writes to a caller-named path without being declared "
           f"({sorted(missing) or 'none'})")

    # And the confinement, on a tool that is still available.
    inside = client.call("anla_survey", source=str(SHARE), sample_mib=2)
    expect("error" not in inside, "a path inside the shared root is served")
    outside = client.call("anla_survey", source=str(ROOT / "python"))
    print(f"  outside: {str(outside.get('error'))[:88]}")
    expect("outside the shared root" in str(outside.get("error", "")),
           "a path outside the shared root is refused")
    traversal = client.call("anla_survey", source=str(SHARE / ".." / "python"))
    expect("outside the shared root" in str(traversal.get("error", "")),
           "`..` does not get around it, because the check is on the resolved path")
finally:
    shared.terminate()

print()
if failures:
    print(f"{len(failures)} failed:")
    for line in failures:
        print(f"  - {line}")
    raise SystemExit(1)
print("every check passed")
