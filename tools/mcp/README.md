# ANLA over MCP

```bash
python tools/mcp/anla_mcp.py
```

Registered for this repository in [`.mcp.json`](../../.mcp.json), so an agent working
here has it without any setup. Needs `mcp`, `blake3` and `zstandard`; stdio only,
because it touches the filesystem and nothing here should be reachable over a network.

## Why this is not a CLI wrapper

The whitepaper's claim is that **a model may plan how to pack, and a deterministic
decoder with no model in it must return every declared byte.** The second half has
been built and proven for weeks. The first half did not exist: there was no planner,
and an agent's only way in was a command line designed for people.

The loop these tools make possible is the first half:

```
anla_survey   →  measured facts, and a recommended plan
   agent      →  chooses a plan, for reasons it can state
anla_pack     →  the plan is recorded IN the archive as `packing_plan`
anla_append   →  inherits that plan, so a later snapshot cannot cut differently
```

That last step is the point. A packing plan in a log is a memory; a packing plan in
the manifest is an artifact — an append that would cut at different boundaries is
*refused*, rather than quietly producing different chunk ids for identical bytes and
deduplicating against nothing while every check still passes.

## The tools

| tool | what it does |
|---|---|
| `anla_survey` | Packs a sample at four chunk sizes and reports what each cost. Returns a recommended plan and the measurement behind it. |
| `anla_pack` | New archive. Records the plan. `engine="rust"` is ~20× faster and byte-identical. |
| `anla_append` | Another snapshot, inheriting the archive's recorded chunking. |
| `anla_verify` | Every snapshot and chunk; optionally asks the independent Rust reader the same question. |
| `anla_extract` | Restore, and with `compare_with` check every restored byte against the source. |
| `anla_snapshots` / `anla_list` / `anla_diff` | The chain, one snapshot's objects, and what changed. |
| `anla_manifest` | The five roots, capabilities, the plan, and the fidelity report. |
| `anla_compare_writers` | Pack one tree with both implementations and diff the bytes. |

## Two rules these tools follow

**Every number was measured by the call that returned it.** No estimates and no
"typically". `anla_survey` really packs samples, because the pinned 256 KiB default
is wrong for prose by a factor of three and no amount of reasoning about file sizes
would have found that — it was found by measuring. On this repository's own
`test_demo/`, survey recommends a 16 KiB average: the second snapshot then costs
23,120 bytes where the default costs 54,936.

**A tool reports what it could not do.** The fidelity report, unapplied metadata
namespaces and unapplied native names come back rather than being dropped, because
*stored but not applied* and *not stored* are different facts, and conflating them
throws away whether the data still exists.

## Verifying it works

`tools/mcp/test_mcp.py` speaks JSON-RPC to the server over stdio, as a client does,
rather than importing the module and calling the functions. That distinction earned
itself immediately: the error-handling decorator was written without
`functools.wraps`, so FastMCP — which derives each tool's input schema from the
function signature — gave **all ten tools** a schema of `required: ["args",
"kwargs"]`. Every direct call worked perfectly. No client could have called a single
one.
