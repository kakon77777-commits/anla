# Register the ANLA MCP server — fill-in-the-blanks

Everything below is already filled in for **this machine** (Windows, Python 3.14 at
`C:\Users\kakon\AppData\Local\Python\pythoncore-3.14-64`, repo at
`D:\Ai\work together\ANLA`). Copy, paste, restart, done.

Verified on 2026-08-15: `mcp` 1.28.1, `numpy` 2.4.6 and `uvicorn` 0.51 are installed;
the server starts from **any** working directory and advertises **20 tools** over
both transports.

---

## 0. Which transport — read this first

| | stdio | HTTP |
|---|---|---|
| how it starts | the client launches its own copy | you start it once, clients connect |
| how many clients | one per process | **many at one URL** |
| what it is for | a single agent on this machine | Claude Code **and** Codex together |

**For what you asked — Claude Code and Codex both using it — start the HTTP server
once and point both at the URL.** Two stdio registrations would give you two
processes that cannot see each other's work: one indexes an archive, the other does
not know the index exists.

```bash
python "D:/Ai/work together/ANLA/tools/mcp/anla_mcp.py" --http
```

```
anla MCP on http://127.0.0.1:8791/mcp
  auth: none (loopback only)
  tools: 20
```

Leave that window open. Then §1a and §1b, and both clients are on the same server.

### Claude Code → the HTTP server

```bash
claude mcp add --transport http anla --scope user http://127.0.0.1:8791/mcp
```

### Codex → the same HTTP server

Codex 0.148 (the build on this machine) takes a URL directly:

```bash
"C:/Users/kakon/AppData/Local/OpenAI/Codex/bin/3cff67e9f778ef0e/codex.exe" mcp add anla --url http://127.0.0.1:8791/mcp
```

or by hand in `C:\Users\kakon\.codex\config.toml`, beside the `[mcp_servers.*]`
entries already there:

```toml
[mcp_servers.anla]
url = "http://127.0.0.1:8791/mcp"
```

Check it: `codex mcp list`.

### Why it binds to 127.0.0.1, and what happens if you change that

These twenty tools read and write arbitrary paths on this machine — they pack
directories, extract over them, and capture whatever transcript they are pointed at.
On loopback that is exactly the authority the local agent already has. On any other
interface it is **remote code acting as you**, so:

```bash
python tools/mcp/anla_mcp.py --http --host 0.0.0.0
# anla_mcp: error: --host 0.0.0.0 would expose tools that read and write arbitrary
# paths on this machine to anything that can reach the port, with no authentication.
```

It **refuses**, rather than warning, because a warning is a thing you scroll past.
To actually reach it from elsewhere:

```bash
# 1. a secret, generated rather than chosen
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. the server, bound wide, with that secret required on every request
set ANLA_MCP_TOKEN=<the secret>
python tools/mcp/anla_mcp.py --http --host 0.0.0.0

# 3. the client, same secret
claude mcp add --transport http anla --scope user https://your-host/mcp --header "Authorization: Bearer <the secret>"
codex mcp add anla --url https://your-host/mcp --bearer-token-env-var ANLA_MCP_TOKEN
```

**Prefer a tunnel over opening a port.** Keep `--host 127.0.0.1` and put Cloudflare
Tunnel in front of it, so the machine has no inbound port at all and the tunnel
carries TLS. Set a token anyway: the tunnel authenticates the *transport*, not the
caller.

Wrong token and no token are both `401`; that is drilled in all three directions by
`tools/mcp/test_mcp_http.py`, because a guard tested only with the correct
credential passes just as well when it is checking nothing.

---

## The rest of this file is the single-client stdio setup

Use it if you want one client with its own private server, or if the HTTP route is
not working and you want to isolate the problem.

## 1. Claude Desktop

**File:** `%APPDATA%\Claude\claude_desktop_config.json`
(that is `C:\Users\kakon\AppData\Roaming\Claude\claude_desktop_config.json`)

That file already exists and has `coworkUserFilesPath` and `preferences` in it, and
**no `mcpServers` key yet**. So add the `"mcpServers"` block as a *sibling* of those
two — do not replace the file:

```json
{
  "coworkUserFilesPath": "C:\\Users\\kakon\\Claude",
  "preferences": { "...leave whatever is already here...": true },

  "mcpServers": {
    "anla": {
      "command": "C:\\Users\\kakon\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe",
      "args": ["D:\\Ai\\work together\\ANLA\\tools\\mcp\\anla_mcp.py"]
    }
  }
}
```

Then **quit Claude Desktop completely and reopen it** — it only reads this file at
startup.

Three things that will bite otherwise:

* **Backslashes must be doubled** in JSON. `D:\Ai` is invalid; `D:\\Ai` is correct.
* **Use the full path to `python.exe`.** Claude Desktop does not inherit the PATH you
  have in a terminal, so a bare `"python"` often resolves to nothing.
* **A trailing comma anywhere makes the whole file invalid**, and the app will start
  with *no* MCP servers rather than complaining.

---

## 2. Claude Code

One command, from anywhere:

```bash
claude mcp add anla --scope user -- "C:/Users/kakon/AppData/Local/Python/pythoncore-3.14-64/python.exe" "D:/Ai/work together/ANLA/tools/mcp/anla_mcp.py"
```

`--scope user` means it works in every project, not just this repo. (The repo also
carries a project-scoped `.mcp.json`, but that one only applies when Claude Code is
started **inside** `D:\Ai\work together\ANLA` — if you usually start it in `D:\Ai`,
use the command above.)

Check it took:

```bash
claude mcp list
```

---

## 3. Any other MCP client

It speaks plain **stdio JSON-RPC**. Command and one argument:

```
C:\Users\kakon\AppData\Local\Python\pythoncore-3.14-64\python.exe
D:\Ai\work together\ANLA\tools\mcp\anla_mcp.py
```

No network, no port, no environment variables. It touches the local filesystem, which
is why it is stdio and not a socket.

---

## 4. Thirty-second smoke test, before trusting any of it

```bash
cd "D:/Ai/work together/ANLA"
ANLA_MCP_SELFTEST=1 python tools/mcp/anla_mcp.py
```

Prints a JSON array of 20 tool names and exits. If you get that, the server is fine
and anything still broken is the client's config file.

The full wire test — the one that speaks real JSON-RPC and checks every claim:

```bash
python tools/mcp/test_mcp.py
```

Ends with `every check passed`. Takes a couple of minutes, because it captures a real
session off this machine and indexes it.

---

## 5. What to ask it first

Once it is registered, these are the things worth trying, in order.

**Remember this conversation.** With no `transcript`, it takes the newest session on
this machine — which, for an agent inside one, is its own:

```
context_capture(archive="D:/Ai/tmp/mymemory.anla")
```

It reports `complete: true` and how many turns it stored. If you pass `max_mib` and it
would drop the front, it refuses rather than truncating quietly.

**Look at it without reading all of it:**

```
context_project(archive="D:/Ai/tmp/mymemory.anla", level="L1", budget_bytes=8000)
```

An L1 projection of a real session is around **0.04 %** of it, and every omission
comes back with the path that restores it.

**Get any omitted turn back, byte for byte:**

```
context_expand(archive="D:/Ai/tmp/mymemory.anla", paths=["turns/000042-user.json"])
```

**Then the semantic half:**

```
context_segment(archive="...", scheme="changepoint-v1")
context_segment_export(archive="...", scheme="changepoint-v1", limit=6000)
   → embed the `text` of each row with whatever model you have
context_attach_vectors(archive="...", vectors="...vectors.json", scheme="changepoint-v1")
context_address(archive="...", scheme="changepoint-v1",
                query="the question", query_vector=[...])
```

`context_address` answers with `(source_turn, start_byte, end_byte)` and the turn's
digest re-checked — so what comes back is the record, not a summary of it.

**Without any embedding model**, `context_address` still works on the lexical channel
and says so in `channel`; `context_find` does the same over whole turns. Neither
pretends to be the semantic channel when it is not.

---

## 6. If it does not appear

| what you see | what it is |
|---|---|
| HTTP client cannot connect | the server window is closed — HTTP mode is a process you keep running, unlike stdio which the client launches |
| `401` on every HTTP call | a token is set on the server and not on the client, or the other way round |
| `--host 0.0.0.0` exits immediately | working as designed; set `ANLA_MCP_TOKEN` or keep it on loopback behind a tunnel |
| Two clients disagree about what exists | they are on **two stdio servers**, not one HTTP server — that is the whole reason for §0 |
| No `anla` server at all in the client | the config file is invalid JSON — a trailing comma or a single backslash |
| Server listed but every call fails | `command` is not resolving; use the full `python.exe` path |
| `this server is written against the mcp 1.x API` | `pip install "mcp>=1.10,<2"` — 2.x moved the entry point |
| Semantic search refuses with a projection in the message | no NumPy in *that* Python; `pip install numpy`, or search a smaller corpus |
| `no index for 'changepoint-v1'` | run `context_segment` first — the index is built, not implicit |
