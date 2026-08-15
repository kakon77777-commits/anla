# -*- coding: utf-8 -*-
"""ANLA over MCP — the point at which "agent-native" stops being a name.

    python tools/mcp/anla_mcp.py                     # stdio, one client
    python tools/mcp/anla_mcp.py --http              # http://127.0.0.1:8791/mcp

The whitepaper's claim is that **a model may plan how to pack, and a deterministic
decoder with no model in it must return every declared byte**. Until now the second
half was built and proven and the first half did not exist: there was no planner, and
an agent's only way in was a command line designed for people.

This is the first half. An agent surveys a tree and is told *measured* facts about it,
proposes a packing plan, and the plan is recorded in the archive it produces — so what
the model decided is an auditable, replayable part of the artifact rather than a
choice that happened once in a log nobody kept. The decoder still needs no model.

Two design rules, both learned the hard way in this repository:

* **Every number a tool returns was measured by the call that returned it.** No
  estimates, no cached figures, no "typically". `survey` really packs samples at
  several chunk sizes, because the pinned 256 KiB default is wrong for prose by a
  factor of three and no amount of reasoning about file sizes would have found that.
* **A tool reports what it could not do.** The fidelity report, unapplied metadata
  and unapplied native names are returned rather than dropped, because "stored but
  not applied" and "not stored" are different facts and conflating them throws away
  whether the data still exists.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import hashlib
import json
import math
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from collections import namedtuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

try:                                                            # noqa: E402
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:                                      # pragma: no cover
    # `mcp` 2.0 moved this entry point and CI found it by installing an unpinned
    # `mcp` and getting 2.0.0. Rather than guess at where it went — a shim I could
    # not test is a guess with a comment on it — say precisely what is wrong.
    import importlib.metadata as _meta
    try:
        _found = _meta.version("mcp")
    except Exception:                                           # noqa: BLE001
        _found = "not installed"
    raise SystemExit(
        f"this server is written against the mcp 1.x API and found {_found}: "
        f"`mcp.server.fastmcp.FastMCP` does not exist here. "
        f"Install `pip install 'mcp>=1.10,<2'`, or port it — the 2.x entry point "
        f"has moved and nothing here has been tested against it."
    ) from exc

from anla.errors import AnlaError  # noqa: E402
from anla.fastcdc import CdcProfile  # noqa: E402
from anla1 import container as C  # noqa: E402
from anla1.fs import restore_tree, scan_tree  # noqa: E402
from anla1.context import (  # noqa: E402
    expand, newest_sessions, project, projection_manifest, read_jsonl,
    turn_entries,
)
from anla1.backends import DEFAULT_OLLAMA, backend_for  # noqa: E402
from anla1.embedding import EmbeddingIdentity, comparable  # noqa: E402
from anla1.relations import (  # noqa: E402
    EDGE_KINDS, derive_edges, neighbours, verify_edges,
)
from anla1.resonance import (  # noqa: E402
    Candidate, classify_persistence, resonant_domain,
)
from anla1.segment import (  # noqa: E402
    SCHEMES, SegmentIndex, build_index, digest_of, project_segment,
)
from anla1.vectors import (  # noqa: E402
    PURE_PYTHON_BUDGET_SECONDS, have_numpy, pure_python_projection, read_vectors,
    write_vectors,
)
from anla1.snapshot import (  # noqa: E402
    CODEC_STORE, CODEC_ZSTD, cdc_chunker, diff as snapshot_diff, extract_snapshot,
    list_snapshots, single_chunk, verify_archive, write_snapshot,
)

mcp = FastMCP("anla")

RUST_DIR = ROOT / "rust" / "target" / "release"
#: Chunk sizes `survey` actually tries. The pinned default is 256 KiB with a 64 KiB
#: floor, which makes every file below 64 KiB a single chunk — so on a corpus of
#: 30 KB papers, content-defined chunking does nothing at all and editing one
#: paragraph rewrites the whole file. That was found by measuring, not by thinking.
CANDIDATES = (262144, 65536, 16384, 4096)


def _rust() -> pathlib.Path | None:
    return next((RUST_DIR / n for n in ("anla1-rs.exe", "anla1-rs")
                 if (RUST_DIR / n).exists()), None)


#: Set by `--share DIR`. While it is set, every path any tool resolves must land
#: inside it. `None` means unrestricted, which is correct for stdio and for loopback
#: — there the server has exactly the local agent's own authority and pretending
#: otherwise would be theatre.
SHARE_ROOT: pathlib.Path | None = None

#: Tools that create or modify a file at a path the **caller** named.
#:
#: The first version of this list was written from memory and was wrong: it left out
#: `context_export_for_embedding`, which takes an `out` path and writes it — a
#: write-anywhere tool sitting in a set labelled read-only, which is precisely the
#: failure the comment above it was warning about. A grep for write calls then
#: disagreed with the list in *both* directions: it caught that one and missed
#: `context_attach_vectors`, whose write happens inside `write_vectors`.
#:
#: So neither the memory nor the pattern is the authority. The list below is the
#: union, and `test_mcp_http.py` re-derives it from the source at test time and
#: fails if the two disagree — the check is the thing that keeps it true, not the
#: care taken writing it.
#:
#: `anla_survey` and `anla_compare_writers` write only inside a temporary directory
#: they create and remove, so they stay available: they cannot touch anything the
#: caller can name.
WRITING_TOOLS = frozenset({
    "anla_pack", "anla_append", "anla_extract",
    "context_capture", "context_segment", "context_segment_export",
    "context_attach_vectors", "context_export_for_embedding", "context_embed",
    "context_relate",
})


def _confine(resolved: pathlib.Path) -> pathlib.Path:
    """Refuse a path that resolves outside the shared root.

    Checked after `resolve()`, so `..`, a drive-relative path and a symlink pointing
    out of the tree are all the same case: whatever the string looked like, this is
    where it actually landed.
    """
    if SHARE_ROOT is None:
        return resolved
    try:
        inside = resolved.is_relative_to(SHARE_ROOT)
    except ValueError:                                          # different drive
        inside = False
    if not inside:
        raise ValueError(
            f"{resolved} is outside the shared root {SHARE_ROOT}. This server was "
            f"started with --share, so it can only see paths under that directory "
            f"— the check is on the resolved path, so `..` and symlinks do not get "
            f"around it.")
    return resolved


def _directory(path: str) -> pathlib.Path:
    resolved = _confine(pathlib.Path(path).expanduser().resolve())
    if not resolved.is_dir():
        raise ValueError(f"not a directory: {resolved}")
    return resolved


def _archive(path: str) -> pathlib.Path:
    resolved = _confine(pathlib.Path(path).expanduser().resolve())
    if not resolved.is_file():
        raise ValueError(f"not a file: {resolved}")
    return resolved


def _chunker(chunking: str, average: int):
    if chunking == "none":
        return single_chunk
    if chunking != "cdc":
        raise ValueError(f"chunking must be 'cdc' or 'none', not {chunking!r}")
    return cdc_chunker(CdcProfile(min_size=max(1024, average // 4),
                                  avg_size=average, max_size=average * 4))


def _codec(name: str) -> int:
    if name == "zstd":
        return CODEC_ZSTD
    if name == "store":
        return CODEC_STORE
    raise ValueError(f"codec must be 'store' or 'zstd', not {name!r}")


def _plain(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _guard(fn):
    """Turn an ANLA refusal into an answer rather than a stack trace.

    An agent can act on `{"error": ..., "code": "ANLA_UNSAFE_PATH_OR_OBJECT"}`; it
    can do nothing with a traceback, and the codes are the format's own vocabulary.

    **`functools.wraps` is load-bearing here, not tidiness.** FastMCP builds each
    tool's input schema by inspecting the function's signature, and a plain
    `def wrapped(*args, **kwargs)` gave every one of the ten tools a schema of
    `required: ["args", "kwargs"]` — so no client could call any of them. Calling
    these functions directly from a test would have worked perfectly and said
    nothing; only speaking JSON-RPC to the real server showed it. `wraps` sets
    `__wrapped__`, which `inspect.signature` follows.
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AnlaError as exc:
            return {"error": exc.message, "code": exc.code,
                    "details": _plain(exc.details)}
        except Exception as exc:                              # noqa: BLE001
            return {"error": str(exc) or type(exc).__name__,
                    "code": "TOOL_ERROR"}
    return wrapped


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

@mcp.tool()
@_guard
def anla_survey(source: str, sample_mib: int = 24) -> dict:
    """Measure a directory and recommend a packing plan.

    This is what an agent needs before it can plan, and it is not derivable from
    file listings: the right chunk size depends on how the *content* cuts, so this
    packs a sample at four averages and reports what each one actually cost. On a
    corpus of 30 KB papers the pinned 256 KiB default makes every file a single
    chunk and content-defined chunking does nothing; 4 KiB is three times better.
    Nothing here is a rule of thumb.

    Returns the tree's shape, a measured table of chunk sizes, and a `recommended`
    plan you can hand straight to `anla_pack`.

    `sample_mib` bounds the work: the largest files up to that budget are packed
    for the comparison, because the whole tree can be large and the ranking does
    not change.
    """
    root = _directory(source)
    files, total, by_extension = [], 0, {}
    for entry in root.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            size = entry.stat().st_size
            files.append((size, entry))
            total += size
            suffix = entry.suffix.lower() or "(none)"
            row = by_extension.setdefault(suffix, {"files": 0, "bytes": 0})
            row["files"] += 1
            row["bytes"] += size
    if not files:
        return {"error": "no regular files under that directory", "code": "TOOL_ERROR"}

    files.sort(reverse=True)
    budget, sample = sample_mib * 1024 ** 2, []
    for size, entry in files:
        if budget <= 0:
            break
        sample.append(entry)
        budget -= size

    from anla1.snapshot import SourceEntry
    payloads = [SourceEntry.of(str(e.relative_to(root)).replace("\\", "/"),
                               e.read_bytes()) for e in sample]
    sampled = sum(len(p.read()) for p in payloads)

    table = []
    with tempfile.TemporaryDirectory() as work:
        for average in CANDIDATES:
            target = pathlib.Path(work) / f"{average}.anla"
            started = time.perf_counter()
            first = write_snapshot(target, files=payloads, created_unix_ns=1,
                                   archive_id=bytes(16),
                                   chunker=_chunker("cdc", average),
                                   codec=CODEC_ZSTD)
            # The question is not "how big is one snapshot" — it is "what does the
            # *next* one cost", because that is what deduplication is for and it is
            # the only number a chunk size really moves. So: edit the largest file
            # a little and append.
            edited = list(payloads)
            body = edited[0].read()
            edited[0] = SourceEntry.of(edited[0].path,
                                       body[:len(body) // 2] + b"\n<edited>\n"
                                       + body[len(body) // 2:])
            second = write_snapshot(target, files=edited, created_unix_ns=2,
                                    chunker=_chunker("cdc", average),
                                    codec=CODEC_ZSTD)
            table.append({
                "chunk_avg": average,
                "first_snapshot_bytes": first,
                "second_snapshot_cost": second - first,
                "seconds": round(time.perf_counter() - started, 2),
            })

    best = min(table, key=lambda row: row["second_snapshot_cost"])
    return {
        "source": str(root),
        "files": len(files),
        "logical_bytes": total,
        "largest_file": files[0][0],
        "median_file": files[len(files) // 2][0],
        "by_extension": dict(sorted(by_extension.items(),
                                    key=lambda kv: -kv[1]["bytes"])[:15]),
        "sampled_bytes": sampled,
        "sampled_files": len(payloads),
        "chunk_size_trial": table,
        "recommended": {"chunking": "cdc", "chunk_avg": best["chunk_avg"],
                        "codec": "zstd"},
        "why": (f"{best['chunk_avg']} byte average made the second snapshot cost "
                f"{best['second_snapshot_cost']:,} bytes, against "
                f"{max(r['second_snapshot_cost'] for r in table):,} at the worst "
                f"candidate. Measured on {len(payloads)} of {len(files)} files "
                f"({sampled:,} bytes)."),
        "engine_note": ("the python writer packs at single-digit MiB/s with cdc; "
                        "pass engine='rust' to anla_pack for anything large"
                        if _rust() else "the rust writer is not built"),
    }


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

@mcp.tool()
@_guard
def anla_pack(source: str, archive: str, chunking: str = "cdc",
              chunk_avg: int = 262144, codec: str = "zstd",
              engine: str = "python", overwrite: bool = False,
              archive_id: str = "", created_unix_ns: int = 0) -> dict:
    """Pack a directory into a new ANLA 1.0 archive.

    The plan you choose is recorded *in the archive* as `packing_plan`, so a later
    append that would cut at different boundaries is refused rather than quietly
    deduplicating against nothing. That is the difference between an agent's
    decision being an artifact and being a memory.

    `engine="rust"` is roughly twenty times faster with content-defined chunking and
    produces byte-identical output; `engine="python"` is the reference implementation.

    A new archive gets a fresh random `archive_id` unless you pin one (32 hex
    characters), and is stamped with the current time unless you pin
    `created_unix_ns`. Pin both when you want the *same tree to produce the same
    bytes* — reproducibility is a property of the inputs, and the identity and the
    timestamp are inputs like any other.
    """
    root = _directory(source)
    target = pathlib.Path(archive).expanduser().resolve()
    if target.exists() and not overwrite:
        raise ValueError(f"{target} exists; pass overwrite=true to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    identity = (bytes.fromhex(archive_id) if archive_id else uuid.uuid4().bytes)
    if len(identity) != 16:
        raise ValueError("archive_id must be 32 hex characters (16 bytes)")
    stamp = created_unix_ns or time.time_ns()

    started = time.perf_counter()
    if engine == "rust":
        binary = _rust()
        if binary is None:
            raise ValueError("the rust writer is not built (cargo build --release)")
        done = subprocess.run(
            [str(binary), "pack", str(root), "-o", str(target),
             "--chunking", chunking, "--chunk-avg", str(chunk_avg),
             "--codec", codec, "--uuid", identity.hex(),
             "--created-ns", str(stamp)], capture_output=True, encoding="utf-8",
            errors="replace")
        if done.returncode != 0:
            raise ValueError((done.stdout or done.stderr or "").strip()[:400])
        skipped = []
    else:
        tree = scan_tree(root, allow_unsupported=True)
        write_snapshot(target, **tree.as_source(), created_unix_ns=stamp,
                       archive_id=identity,
                       chunker=_chunker(chunking, chunk_avg), codec=_codec(codec))
        skipped = tree.skipped
    elapsed = time.perf_counter() - started

    data = target.read_bytes()
    snapshot = list_snapshots(data)[-1]
    logical = sum(o.get("size", 0) for o in snapshot.manifest["objects"])
    return {
        "archive": str(target),
        "archive_id": identity.hex(),
        "engine": engine,
        "archive_bytes": len(data),
        "logical_bytes": logical,
        "ratio": round(len(data) / logical, 4) if logical else None,
        "objects": len(snapshot.manifest["objects"]),
        "chunks": len(snapshot.manifest["chunks"]),
        "seconds": round(elapsed, 3),
        "mib_per_second": round((logical / 1024 ** 2) / elapsed, 1) if elapsed else None,
        "packing_plan": _plain(snapshot.manifest.get("packing_plan")),
        # What the writer could not keep. In the archive as well, but an agent that
        # has to ask a second time will not.
        "not_stored": skipped,
    }


@mcp.tool()
@_guard
def anla_append(archive: str, source: str, codec: str = "zstd") -> dict:
    """Add a snapshot of a directory to an existing archive.

    Chunking is inherited from the archive's recorded plan — an append that used a
    different rule would produce different chunk ids for identical bytes, so
    deduplication would silently do nothing while every check still passed.
    """
    target = _archive(archive)
    root = _directory(source)
    before = target.stat().st_size
    plan = list_snapshots(target.read_bytes())[-1].manifest.get("packing_plan") or {}
    average = plan.get("avg")

    tree = scan_tree(root, allow_unsupported=True)
    started = time.perf_counter()
    after = write_snapshot(target, **tree.as_source(), created_unix_ns=time.time_ns(),
                           chunker=_chunker("cdc", average) if average else single_chunk,
                           codec=_codec(codec))
    elapsed = time.perf_counter() - started
    logical = sum(len(f.read()) for f in tree.files)
    return {
        "archive": str(target),
        "archive_before": before, "archive_after": after, "added": after - before,
        "logical_bytes": logical,
        "share_of_input": round((after - before) / logical, 5) if logical else None,
        "snapshots": len(list_snapshots(target.read_bytes())),
        "seconds": round(elapsed, 3),
        "inherited_chunk_avg": average,
        "not_stored": tree.skipped,
    }


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

@mcp.tool()
@_guard
def anla_verify(archive: str, cross_check: bool = True) -> dict:
    """Verify every snapshot and every chunk.

    With `cross_check`, the independent Rust reader is asked the same question about
    the same bytes. Two implementations sharing no code below `blake3` and `zstd`
    agreeing is the claim the format rests on, and it is cheap to actually make.

    Note what verification is: proof that the archive is *internally consistent*.
    It cannot prove the bytes are the ones that went in — a writer that stored the
    wrong content would also have hashed the wrong content. For that, extract and
    compare against the source.
    """
    target = _archive(archive)
    data = target.read_bytes()
    started = time.perf_counter()
    report = verify_archive(data)
    elapsed = time.perf_counter() - started
    result = {
        "archive": str(target), "ok": True,
        "snapshots": len(report.snapshots),
        "archive_bytes": len(data),
        "seconds": round(elapsed, 3),
        "mib_per_second": round((len(data) / 1024 ** 2) / elapsed, 1) if elapsed else None,
    }
    binary = _rust() if cross_check else None
    if binary is not None:
        done = subprocess.run([str(binary), "verify", str(target)],
                              capture_output=True, encoding="utf-8", errors="replace")
        result["second_implementation"] = {
            "agrees": done.returncode == 0,
            "said": (done.stdout or done.stderr or "").strip()[:300],
        }
    return result


@mcp.tool()
@_guard
def anla_extract(archive: str, destination: str, snapshot: int | None = None,
                 compare_with: str | None = None) -> dict:
    """Restore a snapshot to a directory.

    `compare_with` names the source tree; every restored file is then compared
    against it **in binary**, and the result says how many matched. That is the
    check verification cannot make, and it is the one worth having.

    Anything the archive held but this machine could not apply — a native filename
    it cannot represent, a metadata namespace it does not know — is reported rather
    than dropped. The data is still in the archive; what was lost is this restore.
    """
    target = _archive(archive)
    data = target.read_bytes()
    snapshots = list_snapshots(data)
    chosen = snapshots[-1] if snapshot is None else next(
        (s for s in snapshots if s.sequence == snapshot), None)
    if chosen is None:
        raise ValueError(f"no snapshot {snapshot}; this archive has "
                         f"{[s.sequence for s in snapshots]}")
    where = pathlib.Path(destination).expanduser().resolve()
    started = time.perf_counter()
    report = restore_tree(data, chosen, where)
    elapsed = time.perf_counter() - started

    result = {
        "destination": str(where), "snapshot": chosen.sequence,
        "files": report.files, "directories": report.directories,
        "links": report.links, "bytes_written": report.bytes_written,
        "seconds": round(elapsed, 3),
        "names_not_applied": report.names_not_applied,
        "metadata_not_applied": report.metadata_not_applied,
    }
    if compare_with:
        source = _directory(compare_with)
        same = differ = missing = 0
        examples = []
        for entry in source.rglob("*"):
            if not entry.is_file() or entry.is_symlink():
                continue
            landed = where / entry.relative_to(source)
            if not landed.is_file():
                missing += 1
                if len(examples) < 10:
                    examples.append({"path": str(entry.relative_to(source)), "why": "missing"})
            elif entry.read_bytes() == landed.read_bytes():
                same += 1
            else:
                differ += 1
                if len(examples) < 10:
                    examples.append({"path": str(entry.relative_to(source)), "why": "differs"})
        result["byte_comparison"] = {
            "identical": differ == 0 and missing == 0,
            "matched": same, "differed": differ, "missing": missing,
            "examples": examples,
        }
    return result


@mcp.tool()
@_guard
def anla_snapshots(archive: str) -> dict:
    """The snapshot chain: what is in this archive and in what order."""
    data = _archive(archive).read_bytes()
    header = C.parse_header(data)
    return {
        "archive_uuid": header.archive_uuid.hex(),
        "archive_bytes": len(data),
        "snapshots": [{
            "sequence": s.sequence,
            "created_unix_ns": s.manifest["created_unix_ns"],
            "objects": len(s.manifest["objects"]),
            "chunks": len(s.manifest["chunks"]),
            "snapshot_id": s.snapshot_id.hex(),
            "parent": (s.manifest.get("parent_snapshot") or b"").hex() or None,
        } for s in list_snapshots(data)],
    }


@mcp.tool()
@_guard
def anla_list(archive: str, snapshot: int | None = None, limit: int = 200,
              prefix: str = "") -> dict:
    """The objects in one snapshot: path, kind, size, chunk count."""
    data = _archive(archive).read_bytes()
    snapshots = list_snapshots(data)
    chosen = snapshots[-1] if snapshot is None else next(
        (s for s in snapshots if s.sequence == snapshot), None)
    if chosen is None:
        raise ValueError(f"no snapshot {snapshot}")
    entries = [{
        "path": o["path"], "kind": o["kind"], "size": o.get("size", 0),
        "chunks": len(o.get("chunks", [])),
        "native_name": o["name"].hex() if "name" in o else None,
    } for o in chosen.manifest["objects"] if o["path"].startswith(prefix)]
    return {"snapshot": chosen.sequence, "total": len(entries),
            "shown": min(limit, len(entries)), "objects": entries[:limit]}


@mcp.tool()
@_guard
def anla_diff(archive: str, older: int, newer: int) -> dict:
    """What changed between two snapshots.

    Derived from the two manifests rather than stored, so there is no summary that
    can disagree with the archive.
    """
    data = _archive(archive).read_bytes()
    snapshots = {s.sequence: s for s in list_snapshots(data)}
    for wanted in (older, newer):
        if wanted not in snapshots:
            raise ValueError(f"no snapshot {wanted}; have {sorted(snapshots)}")
    changed = snapshot_diff(snapshots[older], snapshots[newer])
    return {
        "older": older, "newer": newer,
        "added": changed.added, "removed": changed.removed,
        "modified": changed.modified, "unchanged": len(changed.unchanged),
        # Chunk-level, which is the interesting half: how much of the newer snapshot
        # was genuinely new content rather than a path that happened to change.
        "new_chunks": len(changed.new_chunks),
        "shared_chunks": len(changed.shared_chunks),
    }


@mcp.tool()
@_guard
def anla_manifest(archive: str, snapshot: int | None = None) -> dict:
    """The manifest's structure: the five roots, capabilities, and the packing plan.

    `required_capabilities` is what a reader must understand or refuse.
    `optional_capabilities` is what it can verify and extract around — metadata
    namespaces and native names live there, because a reader that has never heard of
    one still returns every byte, it simply cannot *apply* what it verified.
    """
    data = _archive(archive).read_bytes()
    snapshots = list_snapshots(data)
    chosen = snapshots[-1] if snapshot is None else next(
        (s for s in snapshots if s.sequence == snapshot), None)
    if chosen is None:
        raise ValueError(f"no snapshot {snapshot}")
    m = chosen.manifest
    fidelity = [b for b in m["metadata"] if b.get("namespace") == "fidelity"]
    return {
        "snapshot": chosen.sequence,
        "anla_version": m["anla_version"],
        "archive_id": m["archive_id"].hex(),
        "hash_algorithms": m["hash_algorithms"],
        "roots": {k: m[k].hex() for k in ("objects_root", "chunks_root",
                                          "metadata_root", "preservation_root",
                                          "auxiliary_root")},
        "required_capabilities": m["required_capabilities"],
        "optional_capabilities": m["optional_capabilities"],
        "packing_plan": _plain(m.get("packing_plan")),
        "objects": len(m["objects"]), "chunks": len(m["chunks"]),
        "auxiliary_entries": len(m["auxiliary"]),
        # What the archive says it does NOT hold. Only the writer could know it, so
        # it is in the preservation plane and `strip` cannot launder it away.
        "fidelity_report": _plain(fidelity[0]["entries"]) if fidelity else [],
    }


@mcp.tool()
@_guard
def anla_compare_writers(source: str) -> dict:
    """Pack one tree with both implementations and diff the bytes.

    The format's central claim, made on demand. `store` only: §8 says compressed
    output is a function of the compressor, and the two do not necessarily bundle
    the same libzstd, so a zstd difference is expected rather than a defect.
    """
    binary = _rust()
    if binary is None:
        raise ValueError("the rust writer is not built (cargo build --release)")
    root = _directory(source)
    with tempfile.TemporaryDirectory() as work:
        py = pathlib.Path(work) / "python.anla"
        rs = pathlib.Path(work) / "rust.anla"
        tree = scan_tree(root, preserve_mtime=False, preserve_posix=False,
                         allow_unsupported=True)
        write_snapshot(py, **tree.as_source(), created_unix_ns=1,
                       archive_id=bytes(range(16)),
                       chunker=_chunker("cdc", 262144), codec=CODEC_STORE)
        done = subprocess.run(
            [str(binary), "pack", str(root), "-o", str(rs), "--chunking", "cdc",
             "--chunk-avg", "262144", "--codec", "store", "--no-metadata",
             "--skip-unsupported",
             "--uuid", "000102030405060708090a0b0c0d0e0f", "--created-ns", "1"],
            capture_output=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            raise ValueError((done.stdout or done.stderr or "").strip()[:400])
        a, b = py.read_bytes(), rs.read_bytes()
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    if first is None and len(a) != len(b):
        first = min(len(a), len(b))
    return {"identical": a == b, "python_bytes": len(a), "rust_bytes": len(b),
            "first_differing_byte": first}


# ---------------------------------------------------------------------------
# context — an agent's own history, kept whole and read as a projection
# ---------------------------------------------------------------------------
#
# `design/context-compression.md` has the argument. The short version is MNVP
# 原則四: 永久刪除與可展開壓縮是不同操作 — permanent deletion and expandable
# compression are different operations, and summarising a context is the first.
#
# These five tools are the second. The whole record goes into an archive; what a
# model reads is a projection that names what it left out; and any omission comes
# back byte for byte, from the archive, with no model involved in the returning.

def _sessions(root: str = "") -> list[pathlib.Path]:
    # One definition, in the library, because the `anla1 context` commands need the
    # same answer and "the newest session" written twice is two definitions that
    # agree right up until one of them is edited.
    return newest_sessions(root)


@mcp.tool()
@_guard
def context_capture(archive: str, transcript: str = "", session_root: str = "",
                    max_mib: int = 0, chunk_avg: int = 16384,
                    allow_truncation: bool = False) -> dict:
    """Store a conversation transcript losslessly, one object per turn.

    With no `transcript`, takes the most recently modified session on this machine —
    which for an agent running inside one is its own. That is the point: an agent
    can capture the context it is currently living in.

    Every turn becomes its own archive object, so any single one can be handed back
    later without reading the rest. Identical turns — the same file read twice, the
    same tool result repeated — are stored once, which is where a transcript's
    redundancy actually lives.

    Appends when the archive exists, so calling this repeatedly through a long
    session costs roughly what changed rather than the whole context again.
    """
    found = _sessions(session_root)
    source = pathlib.Path(transcript).expanduser() if transcript else (
        found[0] if found else None)
    if source is None or not source.is_file():
        raise ValueError(f"no transcript found (looked in {session_root or '~/.claude/projects'})")

    whole = source.read_bytes()
    limit = max_mib * 1024 ** 2 if max_mib else 0
    truncated = bool(limit and len(whole) > limit)

    # A capture that quietly drops the front of a transcript and then reports itself
    # the way a complete one does is the worst defect this system can have: every
    # downstream claim — the projection's share, the omission manifest, "expand any
    # turn" — is then stated over a record the caller believes is whole. So a limit
    # must be asked for and reported, or refused.
    if truncated and not allow_truncation:
        raise ValueError(
            f"{source.name} is {len(whole):,} bytes and max_mib={max_mib} would drop "
            f"the first {len(whole) - limit:,}. That capture would not be lossless "
            f"and would not say so. Pass allow_truncation=true to take the tail "
            f"deliberately — the result is then reported as partial — or raise "
            f"max_mib, or leave it 0 for the whole transcript.")

    if truncated:
        # From the end: the recent part is what a projection is usually about.
        data = whole[-limit:]
        data = data[data.find(b"\n") + 1:]
    else:
        data = whole
    omitted_bytes = len(whole) - len(data)

    turns = read_jsonl(data)
    if not turns:
        raise ValueError(f"{source} holds no turns")

    target = pathlib.Path(archive).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    before = target.stat().st_size if existed else 0

    started = time.perf_counter()
    size = write_snapshot(
        target, files=turn_entries(turns),
        created_unix_ns=time.time_ns(),
        **({} if existed else {"archive_id": uuid.uuid4().bytes}),
        chunker=_chunker("cdc", chunk_avg), codec=CODEC_ZSTD)
    elapsed = time.perf_counter() - started

    snapshot = list_snapshots(target.read_bytes())[-1]
    return {
        "archive": str(target),
        "transcript": str(source),
        # Stated on every capture, not only the truncated ones — a field that
        # appears only when something is wrong is a field nobody checks for.
        "complete": not truncated,
        "capture": "partial — the front of the transcript was dropped" if truncated
                   else "lossless — every byte of the transcript is in the archive",
        "transcript_bytes": len(whole),
        "omitted_bytes": omitted_bytes,
        "omitted_range": {"start_byte": 0, "end_byte": omitted_bytes} if truncated
                         else None,
        "turns": len(turns),
        "context_bytes": len(data),
        "archive_bytes": size,
        "added": size - before,
        "share_of_context": round(size / len(data), 4) if data else None,
        "unique_chunks": len(snapshot.manifest["chunks"]),
        "deduplicated_turns": len(turns) - len(snapshot.manifest["chunks"]),
        "snapshots": len(list_snapshots(target.read_bytes())),
        "seconds": round(elapsed, 2),
    }


@mcp.tool()
@_guard
def context_project(archive: str, level: str = "L1", budget_bytes: int = 32000,
                    keep_recent: int = 6) -> dict:
    """Read the context as a projection, with a manifest of what it leaves out.

    `L0` core, `L1` comparison, `L2` explanation, `L3` audit — MNVP §6.1, and a
    higher level never preserves less than a lower one.

    The returned `omitted` list is the point. It is not a count: every entry carries
    the `path` that restores that turn byte for byte through `context_expand`, plus
    a short hint so you can decide whether it is worth restoring. A projection that
    could only tell you *how much* it dropped would be a summary.
    """
    data = _archive(archive).read_bytes()
    snapshot = list_snapshots(data)[-1]
    turns = _turns_of(data, snapshot)
    projection = project(turns, level=level, budget_bytes=budget_bytes,
                         keep_recent=keep_recent)
    manifest = projection_manifest(projection)
    return {
        "level": projection.level,
        "text": projection.text,
        "preserved": len(projection.preserved),
        "omitted": manifest["omitted"],
        "expandable": manifest["expandable"],
        "bytes_shown": manifest["bytes_shown"],
        "bytes_total": manifest["bytes_total"],
        "share_shown": manifest["share_shown"],
    }


@mcp.tool()
@_guard
def context_expand(archive: str, paths: list[str]) -> dict:
    """Hand back omitted turns, byte for byte.

    This is what makes the projection a compression rather than a deletion. It
    reads whole objects out of the archive — no model, no reconstruction, no
    approximation — so what comes back is what went in.
    """
    data = _archive(archive).read_bytes()
    restored = expand(data, paths)
    return {
        "restored": {path: raw.decode("utf-8", "replace")
                     for path, raw in restored.items()},
        "bytes": {path: len(raw) for path, raw in restored.items()},
        "total_bytes": sum(len(raw) for raw in restored.values()),
    }


@mcp.tool()
@_guard
def context_find(archive: str, query: str = "", moment: str = "", limit: int = 12,
                 threshold: float = 0.18,
                 query_vector: list[float] | None = None) -> dict:
    """Which of this shared history belongs in the present moment.

    Not a search. Paper 05 of Neo's 符號記憶判定耦合系列 defines

        𝓔_AB^(τ) = { m ∈ 𝔐_AB : Ψ_τ(m) ≥ θ_τ }

    — the shared history is 𝔐, what belongs in the shared *present* is the small
    subset 𝓔 whose appropriateness clears a threshold. 「還在記憶庫裡」不等於
    「仍在共同現在」.

    This replaced an ordering. The first version ranked by recency and returned the
    latest echo of a thing rather than where it was decided; the second ranked
    chronologically, which is a better sort and still the wrong axis. Time is one
    of Ψ's eight terms and enters through an item's own **persistence class**
    (paper 06: instantaneous state / active context / persistent method / long-term
    trajectory), because recency distortion is w(m|t) failing to match
    τ_persistence(m), not recent outweighing old.

    `moment` is what is in front of us now, and it carries its own term. Passing it
    is the difference between "what mentions this" and "what belongs here".

    **The two channels that matter most are absent and say so.** Semantic vectors
    and phase are the mechanism this stands in for — 共感 is resonance and
    resonance is a phase phenomenon — and there is no embedding model here, so they
    are reported missing rather than approximated by word overlap wearing their
    name. Every hit carries the terms that produced it, so a retrieval carried by
    weak channels is visible instead of confident.

    Paper 07's boundary holds over the whole thing: Recall ≠ Care. This says a
    memory is appropriate to surface. Nothing about a relationship follows.
    """
    data = _archive(archive).read_bytes()
    snapshot = list_snapshots(data)[-1]
    turns = _turns_of(data, snapshot)
    if not turns:
        raise ValueError("this archive holds no turns")

    # Vectors, when something outside supplied them. Auxiliary plane: their absence
    # costs the semantic channel and nothing else.
    sidecar = _archive(archive).with_suffix(".vectors.json")
    supplied, model = {}, ""
    if sidecar.exists():
        loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        supplied, model = loaded.get("vectors", {}), loaded.get("model", "")

    total = len(turns)
    candidates = [
        Candidate(vector=supplied.get(turn.path), key=turn.path,
                  text=(turn.text or turn.raw.decode("utf-8", "replace"))[:4000],
                  position=index, total=total,
                  persistence=classify_persistence(turn.text or ""))
        for index, turn in enumerate(turns)]

    # With no moment given, the tail of the conversation is the moment — which is
    # what an agent asking mid-session actually has in front of it.
    here = [moment] if moment else [t.text or "" for t in turns[-6:]]
    domain, report = resonant_domain(candidates, query=query, moment=here,
                                     threshold=threshold, limit=limit,
                                     query_vector=query_vector)

    by_path = {t.path: t for t in turns}
    return {
        "query": query,
        "in_domain": [{
            **r.as_dict(),
            "path": r.key,
            "index": by_path[r.key].index,
            "role": by_path[r.key].role,
            "hint": " ".join((by_path[r.key].text or "").split())[:160],
        } for r in domain],
        "considered": report["considered"],
        "share_of_history": report["share_of_history"],
        "threshold": report["threshold"],
        "channels": report["channels"],
        "absent": report["absent"],
        "embedding_model": model or None,
        "turns_with_vectors": report["embedded"],
        "boundary": report["boundary"],
        "disclosure": (
            "nothing in this history clears the threshold for this moment"
            if not domain else
            "carried by weak channels — the semantic and phase channels that would "
            "answer a question like this are absent"
            if all(r.terms.get("R", 0) < 0.05 for r in domain) else
            "content relevance contributed"),
    }


@mcp.tool()
@_guard
def context_export_for_embedding(archive: str, out: str = "", limit: int = 0,
                                 chars: int = 1200) -> dict:
    """Write out the turns to be embedded, for a model that can embed them.

    Nothing here computes embeddings and nothing here is going to. The model
    holding the conversation is the one with an embedder, and UTF-8X states the
    division this follows: 「AI 負責策略生成，解碼由確定性、版本化、可雜湊驗證的
    轉換器完成 —— AI 不參與解碼」. The vectors are the AI's contribution; the
    resonance computation over them is deterministic and local.

    Produces JSON of `{key, text}`. Hand it to whatever can embed, and bring the
    result back through `context_attach_vectors`.
    """
    data = _archive(archive).read_bytes()
    snapshot = list_snapshots(data)[-1]
    turns = _turns_of(data, snapshot)
    if limit:
        turns = turns[-limit:]
    rows = [{"key": turn.path,
             "text": " ".join((turn.text or
                               turn.raw.decode("utf-8", "replace")).split())[:chars]}
            for turn in turns]
    rows = [row for row in rows if row["text"]]

    target = pathlib.Path(out).expanduser() if out else (
        _archive(archive).with_suffix(".to-embed.json"))
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"file": str(target), "turns": len(rows),
            "characters": sum(len(r["text"]) for r in rows),
            "next": "embed each `text`, then call context_attach_vectors with "
                    "[{key, vector}] — same model for all of them, and for the "
                    "query later, or the comparison is between two vector spaces"}


@mcp.tool()
@_guard
def context_attach_vectors(archive: str, vectors: str, model: str = "",
                           scheme: str = "", revision: str = "unstated") -> dict:
    """Attach supplied vectors to an archive's turns.

    They go into the **auxiliary** plane, which is exactly where they belong:
    `D(P, I) = D(P, ∅)` — dropping the intelligence plane changes nothing a decoder
    extracts, and an embedding is derived, disposable and regenerable.

    Concretely: a sidecar file *beside* the archive, not a record inside it. So
    discarding the whole intelligence plane is deleting one file, the archive's bytes
    are untouched by construction rather than by a rewrite that has to be checked,
    and the only thing lost is the semantic channel — which then reports itself
    absent instead of silently degrading into word overlap.

    `vectors` is a path to JSON in either shape:

        {"model": "...", "dimensions": 768, "vectors": [{"key": ..., "vector": [...]}]}
        [{"key": ..., "vector": [...]}]

    The first is preferred and is what `PROMPT-embeddings.md` asks for, because it
    carries the model — and a vector without the model that produced it cannot be
    compared with anything later. Both are accepted because the prompt and this
    tool disagreed about the shape on the first end-to-end run, which would have
    produced a file the tool rejected after a model had spent real work on it.

    `model` here overrides whatever the file says; the file's own value is used
    when this is left empty.

    With `scheme`, the keys are segment ids from that index rather than turn paths,
    and the stored identity records the projection version and the scheme as well as
    the model — because a vector is `E_θ(π_σ(m))`, and two schemes over one memory
    produce two different vectors that cosine will happily compare.
    """
    target = _archive(archive)
    loaded = json.loads(pathlib.Path(vectors).expanduser().read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        rows = loaded.get("vectors")
        model = model or str(loaded.get("model") or "")
    else:
        rows = loaded
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected {\"vectors\": [{key, vector}, ...]} or a "
                         "non-empty list of {key, vector}")

    widths, cleaned = set(), {}
    for row in rows:
        key, vector = row.get("key"), row.get("vector")
        if not key or not isinstance(vector, list) or not vector:
            raise ValueError(f"every row needs a key and a non-empty vector: {str(row)[:80]}")
        widths.add(len(vector))
        cleaned[key] = [float(x) for x in vector]
    if len(widths) > 1:
        raise ValueError(f"vectors of mixed width {sorted(widths)} — these did not "
                         f"come from one model, and comparing them would be a "
                         f"confident number from an incoherent comparison")

    projection_version = "unstated"
    if scheme:
        index_file = _segment_sidecar(target, scheme)
        if not index_file.exists():
            raise ValueError(f"no index for {scheme!r}; call context_segment first")
        index = SegmentIndex.of(json.loads(index_file.read_text(encoding="utf-8")))
        projection_version = index.projection_version
        known = {s.segment_id for s in index.segments}
        noun, sidecar = "segments", target.with_suffix(f".vectors-{scheme}.anlavec")
    else:
        data = target.read_bytes()
        snapshot = list_snapshots(data)[-1]
        known = {o["path"] for o in snapshot.manifest["objects"]}
        noun, sidecar = "turns", target.with_suffix(".vectors.json")

    unknown = sorted(set(cleaned) - known)
    if unknown:
        raise ValueError(f"{len(unknown)} keys are not {noun} in this archive, "
                         f"e.g. {unknown[:3]}")

    width = widths.pop()
    identity = EmbeddingIdentity(model=model or "unstated", dimensions=width,
                                 revision=revision,
                                 projection_version=projection_version,
                                 segmentation_scheme=scheme or "unstated")
    # float32 rows behind a JSON header, not a JSON array of decimals. Measured at
    # 61,458×768: 192 MB against 978 MB, and 0.52 s to load against 38.1 s.
    written = write_vectors(sidecar, cleaned.items(), identity.as_dict(),
                            extra={"model": model or "unstated"})
    return {
        "archive": str(target),
        "sidecar": str(sidecar),
        "sidecar_bytes": written["bytes"],
        "attached": len(cleaned),
        "scope": noun,
        f"{noun}_in_archive": len(known),
        "coverage": round(len(cleaned) / len(known), 4) if known else None,
        "model": model or "unstated",
        "identity": identity.as_dict(),
        "identity_fingerprint": identity.fingerprint,
        "search_backend": "numpy" if have_numpy() else
                          (f"pure python — projected "
                           f"{pure_python_projection(len(cleaned), width):.1f}s per "
                           f"query for this corpus; refused past "
                           f"{PURE_PYTHON_BUDGET_SECONDS:.0f}s, install numpy for more"),
        "plane": "auxiliary — a sidecar beside the archive, not a record inside it; "
                 "deleting this file discards the whole intelligence plane and the "
                 "archive's bytes are unchanged by construction",
        "note": "context_address (segments) and context_find (turns) will use the "
                "semantic channel when a query vector is given too, and will say so "
                "in their channel report",
    }


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"width {len(a)} against {len(b)} — not one vector space")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


#: A turn read back out of an archive: the stored path and the bytes under it,
#: which is all the relation layer needs.
_Stored = namedtuple("_Stored", "path raw")


def _preserved(archive: str) -> tuple[pathlib.Path, dict[str, bytes]]:
    target = _archive(archive)
    data = target.read_bytes()
    return target, extract_snapshot(data, list_snapshots(data)[-1])


def _segment_sidecar(target: pathlib.Path, scheme: str) -> pathlib.Path:
    return target.with_suffix(f".segments-{scheme}.json")


def _project_all(segments, preserved: dict[str, bytes], min_bytes: int = 0):
    """Project many segments, verifying each turn's digest **once**.

    `project_segment` re-hashes the whole turn on every call, which is right for one
    call and wrong for sixty thousand: a turn with ten segments was hashed ten times,
    and the change-point scheme cuts this repository's transcript into 61,458
    segments over 6,581 turns. The check is not weakened — every turn is still
    verified against what the index was built from before a byte of it is read, and
    a turn that fails is skipped entirely rather than projected unchecked.
    """
    verified: dict[str, bool] = {}
    for segment in segments:
        raw = preserved.get(segment.source_turn)
        if raw is None:
            continue
        ok = verified.get(segment.source_turn)
        if ok is None:
            ok = digest_of(raw) == segment.source_digest
            verified[segment.source_turn] = ok
        if not ok:
            continue
        try:
            text = project_segment(segment, raw, check=False)
        except ValueError:
            continue
        if len(text) >= min_bytes:
            yield segment, text


@mcp.tool()
@_guard
def context_segment(archive: str, scheme: str = "changepoint-v1",
                    out: str = "") -> dict:
    """Build an index family σ over the turns. Writes nothing to the record.

    From Neo's 同一性微積分, 切割 = 索引: a segment is a perspective on a preserved
    turn, never a newly preserved fragment. So this produces `(source_turn, ranges)`
    — raw byte offsets — in the **auxiliary** plane, and the archive is byte-identical
    before and after. That is checked here rather than asserted, because it is the
    property the whole design rests on and it would fail silently.

    Several schemes coexist over one memory. Running this again with a different
    `scheme` adds a second index; it does not migrate the first, and it cannot,
    because neither one owns the bytes.
    """
    target, preserved = _preserved(archive)
    before = hashlib.blake2b(target.read_bytes(), digest_size=16).hexdigest()
    index = build_index(sorted(preserved.items()), scheme)
    after = hashlib.blake2b(target.read_bytes(), digest_size=16).hexdigest()

    # Coverage, measured. A byte no segment covers is a memory that cannot be
    # retrieved by any embedder, and nothing downstream would report it missing.
    covered, uncovered = 0, []
    by_turn: dict[str, list] = {}
    for segment in index.segments:
        by_turn.setdefault(segment.source_turn, []).append(segment)
    for path, raw in preserved.items():
        spans = sorted(r for s in by_turn.get(path, []) for r in s.ranges)
        reach, position = 0, 0
        for start, end in spans:
            reach += max(0, end - max(start, position))
            position = max(position, end)
        covered += reach
        if reach != len(raw):
            uncovered.append({"turn": path, "bytes": len(raw), "reachable": reach})

    sidecar = pathlib.Path(out).expanduser() if out else _segment_sidecar(target, scheme)
    sidecar.write_text(json.dumps(index.as_dict(), ensure_ascii=False),
                       encoding="utf-8")
    total = sum(len(r) for r in preserved.values())
    return {
        "archive": str(target),
        "sidecar": str(sidecar),
        "scheme": scheme,
        "available_schemes": sorted(SCHEMES),
        "turns": len(preserved),
        "segments": len(index.segments),
        "median_segment_bytes": (statistics.median(s.byte_length
                                                   for s in index.segments)
                                 if index.segments else None),
        "coverage": round(covered / total, 6) if total else None,
        "turns_not_fully_reachable": uncovered[:5],
        "preservation_digest": before,
        "preservation_unchanged": before == after,
        "plane": "auxiliary — 切割 = 索引; the record was read, not rewritten",
        "next": "context_segment_export → embed → context_attach_vectors(scheme=...) "
                "→ context_address",
    }


@mcp.tool()
@_guard
def context_relate(archive: str, scheme: str = "changepoint-v1") -> dict:
    """Derive typed relation edges onto an existing index. Writes nothing to the record.

    The edges are the **context/index base** of EveMissLab's Phase Canon — the graph a
    transport would later be defined over — and nothing here is a phase. Each edge
    carries a *kind* and the evidence that produced it, never a score: Paper 02 §9 puts
    scalarization after the structure as a task choice, so a weight stored on the edge
    would collapse exactly what the graph is for.

    Only what the record states outright: `replies-to` from `parentUuid`,
    `tool-result-of` from matching tool ids, `mentions-path` from a literal path in
    both turns. `supersedes`, `supports` and `contradicts` are judgements about content
    that the record cannot yield, so they are reported as unavailable rather than
    guessed by a model and shipped looking the same as the derived ones.
    """
    target, preserved = _preserved(archive)
    before = hashlib.blake2b(target.read_bytes(), digest_size=16).hexdigest()
    turns = [_Stored(path, raw) for path, raw in sorted(preserved.items())]

    sidecar = _segment_sidecar(target, scheme)
    if not sidecar.exists():
        return {"error": f"no index for scheme {scheme!r}; run context_segment first",
                "code": "ANLA_NO_SEGMENT_INDEX", "archive": str(target)}
    index = SegmentIndex.of(json.loads(sidecar.read_text(encoding="utf-8")))
    index.edges = derive_edges(turns)
    report = verify_edges(turns, None, index.edges)
    after = hashlib.blake2b(target.read_bytes(), digest_size=16).hexdigest()
    sidecar.write_text(json.dumps(index.as_dict(), ensure_ascii=False),
                       encoding="utf-8")

    counts: dict[str, int] = {}
    for edge in index.edges:
        counts[edge["kind"]] = counts.get(edge["kind"], 0) + 1
    return {
        "archive": str(target), "sidecar": str(sidecar), "scheme": scheme,
        "turns": len(turns), "edges": len(index.edges), "by_kind": counts,
        "kinds": dict(EDGE_KINDS),
        "reproducible": report["identical"],
        "reproducibility_detail": {k: report[k] for k in
                                   ("missing_total", "unexplained_total",
                                    "duplicate_keys", "vacuous")},
        "preservation_digest": before,
        "preservation_unchanged": before == after,
        "plane": "auxiliary — the edges describe the record and do not touch it",
        "not_a_phase": "context/index base I_sem; no transport, no holonomy, and "
                       "the phase channel stays ABSENT",
        "next": "context_relations(turn=...) to walk it",
    }


@mcp.tool()
@_guard
def context_relations(archive: str, turn: str = "", kinds: list[str] | None = None,
                      scheme: str = "changepoint-v1", limit: int = 40) -> dict:
    """What the record says is related to a turn, and why.

    Reads the edges `context_relate` stored. If none are stored — which is the normal
    case under `--share`, where every writing tool is withdrawn — they are derived in
    memory instead and the answer says so, because a caller comparing two responses
    should be able to see that one of them cost a full pass over the archive.

    Neighbours come back in derivation order and are not ranked. Which one matters is
    the caller's question, and answering it here would be the scalarization §9 keeps
    outside the structure.
    """
    target, preserved = _preserved(archive)
    turns = [_Stored(path, raw) for path, raw in sorted(preserved.items())]

    sidecar = _segment_sidecar(target, scheme)
    stored, source = [], "derived in memory — no index sidecar holds edges"
    if sidecar.exists():
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        stored = list(payload.get("edges") or [])
        if stored:
            source = str(sidecar)
    edges = stored or derive_edges(turns)

    if turn and turn not in preserved:
        near = [p for p in preserved if turn in p][:5]
        return {"error": f"no turn {turn!r} in this archive", "code": "ANLA_NO_TURN",
                "did_you_mean": near, "turns": len(preserved)}

    wanted = set(kinds) if kinds else None
    if wanted and not wanted <= set(EDGE_KINDS):
        return {"error": f"unknown kind(s) {sorted(wanted - set(EDGE_KINDS))}",
                "code": "ANLA_UNKNOWN_EDGE_KIND", "kinds": dict(EDGE_KINDS)}

    selected = [e for e in edges
                if (not turn or turn in (e["from"], e["to"]))
                and (not wanted or e["kind"] in wanted)]
    counts: dict[str, int] = {}
    for edge in selected:
        counts[edge["kind"]] = counts.get(edge["kind"], 0) + 1
    return {
        "archive": str(target), "scheme": scheme, "turn": turn or None,
        "edges_source": source, "edges_in_graph": len(edges),
        "matched": len(selected), "by_kind": counts,
        "edges": selected[:limit],
        "truncated": len(selected) > limit,
        "neighbours": neighbours(selected, turn, kinds or ()) if turn else [],
        "unavailable_kinds": {k: v for k, v in EDGE_KINDS.items()
                              if v.startswith("not derivable")},
        "ranking": "none — the edges are typed, not weighted (Paper 02 §9)",
    }


@mcp.tool()
@_guard
def context_segment_export(archive: str, scheme: str = "changepoint-v1",
                           out: str = "", limit: int = 0, chars: int = 6000,
                           min_bytes: int = 40, sample: str = "spread") -> dict:
    """Write out the segment views π_σ(m) to be embedded, with their identity.

    The unit matters and was measured: embedding whole turns put the best real match
    below the 95th percentile of random pairs — the same model over segments answers
    the same questions. So what leaves here is `E_θ(π_σ(m))`, not `E_θ(m)`.

    The identity block must come back with the vectors. A vector whose projection
    version or scheme is unknown cannot honestly be compared with a query vector,
    and cosine will not say so on its own.

    `limit` is where this tool nearly told a lie. Taking the first N segments of a
    60,000-segment conversation exports the first eight per cent of it, and a later
    search then answers every question out of the opening hour and reports itself
    exactly as a complete search would — the nearest hit inside a corpus that could
    not contain the answer. So `sample="spread"` is the default: an even stride
    across the whole record. `"head"` and `"tail"` remain available and are named in
    the result, and the turn range covered is reported for all three.
    """
    target, preserved = _preserved(archive)
    sidecar = _segment_sidecar(target, scheme)
    if not sidecar.exists():
        raise ValueError(f"no index for {scheme!r}; call context_segment first")
    index = SegmentIndex.of(json.loads(sidecar.read_text(encoding="utf-8")))

    rows = [{"key": segment.segment_id, "text": text[:chars]}
            for segment, text in _project_all(index.segments, preserved, min_bytes)]

    eligible = len(rows)
    if limit and eligible > limit:
        if sample == "head":
            rows = rows[:limit]
        elif sample == "tail":
            rows = rows[-limit:]
        elif sample == "spread":
            # Deterministic even stride, so re-running gives the same corpus and two
            # measurements are of the same thing.
            step = eligible / limit
            rows = [rows[min(eligible - 1, int(i * step))] for i in range(limit)]
        else:
            raise ValueError(f"sample must be 'spread', 'head' or 'tail', not "
                             f"{sample!r}")

    turns_covered = {r["key"].split("#")[0] for r in rows}
    where = pathlib.Path(out).expanduser() if out else (
        target.with_suffix(f".to-embed-{scheme}.json"))
    where.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "file": str(where),
        "segments": len(rows),
        "eligible_segments": eligible,
        "skipped_too_short": len(index.segments) - eligible,
        "characters": sum(len(r["text"]) for r in rows),
        # Stated on every export, because a corpus that covers part of the record
        # returns the nearest hit inside that part and looks like a whole search.
        "sample": sample if limit and eligible > limit else "all eligible segments",
        "share_of_index": round(len(rows) / len(index.segments), 4)
                          if index.segments else None,
        "turns_covered": len(turns_covered),
        "turns_in_archive": len(preserved),
        "turn_span": [min(turns_covered), max(turns_covered)] if turns_covered else [],
        "identity": {"projection_version": index.projection_version,
                     "segmentation_scheme": scheme},
        "next": "embed each `text`; return {model, dimensions, revision, vectors:"
                "[{key, vector}]} to context_attach_vectors(scheme=...). The same "
                "model must produce the query vector later, or the comparison is "
                "between two vector spaces and cosine will not mention it",
    }


@mcp.tool()
@_guard
def context_address(archive: str, query: str = "", scheme: str = "changepoint-v1",
                    query_vector: list[float] | None = None, limit: int = 5,
                    model: str = "", revision: str = "unstated",
                    embed: bool = True, backend: str = "ollama",
                    host: str = DEFAULT_OLLAMA) -> dict:
    """Semantic address → the exact bytes of the authoritative turn.

    This is the whole of S1 in one call: **Remember → Index → Retrieve → Expand
    exactly.** Each hit comes back as a byte range in a named turn, with the turn's
    digest re-checked against what the index was built from — so what is returned is
    the record itself, not the retriever's copy of it. A retriever that found the
    right passage but could not return the record verbatim would be a search engine
    over a lossy copy, and this system would have no reason to exist.

    With `query_vector` the semantic channel is used; with only `query` it falls back
    to lexical matching over the same segments and says so. The fallback is named in
    the response rather than blended in, because a weak channel that looks like a
    strong one is the failure that has no symptom.
    """
    target, preserved = _preserved(archive)
    sidecar = _segment_sidecar(target, scheme)
    if not sidecar.exists():
        raise ValueError(f"no index for {scheme!r}; call context_segment first")
    index = SegmentIndex.of(json.loads(sidecar.read_text(encoding="utf-8")))
    segments = {s.segment_id: s for s in index.segments}

    vectors_file = target.with_suffix(f".vectors-{scheme}.anlavec")
    corpus = read_vectors(vectors_file) if vectors_file.exists() else None

    # Two different facts, and the first version of this reported one as the other:
    # "no vectors attached for this scheme" was the default channel string, printed
    # whenever the caller passed no vector — including when the corpus was fully
    # embedded. Found by using it: this conversation had 14,000 vectors attached and
    # every query came back saying there were none.
    if corpus is None:
        channel = "lexical — no vectors are attached for this scheme"
    else:
        channel = (f"lexical — {len(corpus):,} segments carry a vector, but no query "
                   f"vector was supplied and embed=False")
    incomparable = None
    ranked: list[tuple[str, float]] = []

    # Embed the question here rather than making the caller do it. Without this an
    # agent over MCP cannot reach the semantic channel at all: it would have to run
    # the same model itself and pass the vector in, which is the one part of the
    # loop this server is best placed to do. The model is read from the sidecar, so
    # query and corpus cannot come from different ones.
    embedded_identity = None
    if corpus is not None and embed and not query_vector and query:
        stored = EmbeddingIdentity.of(corpus.identity)
        name = stored.model.split(":", 1)[1] if ":" in stored.model else stored.model
        try:
            engine = backend_for(backend, host=host)
            # The backend's own identity, not a string rebuilt from the model name.
            # Building it by hand dropped the backend prefix — `nomic-embed-text`
            # against the stored `ollama:nomic-embed-text` — and the comparison
            # correctly refused a corpus that was in fact the same one. The check
            # was right and the thing it was handed was wrong.
            embedded_identity = engine.identity(
                name, projection_version=index.projection_version,
                segmentation_scheme=scheme)
            query_vector = engine.embed([query], name)[0]
        except Exception as unreachable:                          # noqa: BLE001
            channel = (f"lexical — could not embed the question ({unreachable}); "
                       f"pass query_vector, or start the backend")

    if query_vector and corpus:
        asked = embedded_identity or EmbeddingIdentity(
            model=model or str(corpus.header.get("model") or "unstated"),
            dimensions=len(query_vector), revision=revision,
            projection_version=index.projection_version, segmentation_scheme=scheme)
        held = EmbeddingIdentity.of(corpus.identity)
        ok, reason = comparable(asked, held)
        if not ok:
            incomparable, channel = reason, f"semantic — refused, {reason}"
        else:
            # Centred on this corpus before comparing. Measured, not assumed: without
            # centring the 95th percentile of random pairs sat at +0.453 and the real
            # matches were inside it.
            ranked = [(k, s) for k, s in corpus.search(query_vector, limit=limit)
                      if k in segments]
            channel = (f"semantic — {len(corpus):,} segments carry a vector, "
                       f"{'numpy' if have_numpy() else 'pure python'} backend")
    elif query_vector and not corpus:
        channel = ("semantic — REFUSED, a query vector was given but no segment "
                   "vectors are attached for this scheme")

    if not ranked and query:
        needle = query.lower()
        scores = [(segment.segment_id, len(needle) / max(len(text), 1))
                  for segment, text in _project_all(index.segments, preserved)
                  if needle in text.lower()]
        ranked = sorted(scores, key=lambda kv: -kv[1])[:limit]

    hits = []
    for segment_id, score in ranked:
        segment = segments[segment_id]
        raw = preserved[segment.source_turn]
        verified = digest_of(raw) == segment.source_digest
        start, end = segment.ranges[0]
        hits.append({
            "segment_id": segment_id,
            "score": round(float(score), 4),
            # The address. Everything else in this row is derived from it.
            "source_turn": segment.source_turn,
            "start_byte": start,
            "end_byte": end,
            "digest_verified": verified,
            "expand": "exact — read out of the preserved turn's own bytes" if verified
                      else "REFUSED — this turn is not the one the index was built "
                           "against; the offsets no longer mean what they meant",
            "text": project_segment(segment, raw),
        })

    semantic = bool(corpus) and channel.startswith("semantic —") and not incomparable
    searched = len(corpus) if semantic else len(segments)
    turns_reachable = (len({segments[k].source_turn for k in corpus.keys
                            if k in segments}) if corpus else None)
    return {
        "archive": str(target),
        "scheme": scheme,
        "segments_in_index": len(segments),
        "segments_searched": searched,
        # What the semantic channel could *not* see. A vectorised corpus covering
        # part of the record still returns its nearest hit, and that answer is
        # indistinguishable from a complete search unless the share is stated.
        "semantic_corpus_share": (round(len(corpus) / len(segments), 4)
                                  if segments and corpus else 0.0),
        "search_backend": "numpy" if have_numpy() else "pure python",
        "turns_reachable_semantically": turns_reachable,
        "turns_in_archive": len(preserved),
        "channel": channel,
        "incomparable": incomparable,
        "hits": hits,
        "expanded_exactly": sum(1 for h in hits if h["digest_verified"]),
        "boundary": "Recall is not Care (paper 07): this returns what resonates "
                    "with the query, which is not the same as what matters. "
                    "`expanded_exactly` measures the expansion, never the relevance "
                    "— a hit from a partial corpus expands just as exactly as a "
                    "right one",
    }


@mcp.tool()
@_guard
def context_embed(archive: str, scheme: str = "changepoint-v1",
                  model: str = "nomic-embed-text", backend: str = "ollama",
                  host: str = DEFAULT_OLLAMA, limit: int = 0, batch: int = 64,
                  chars: int = 6000, min_bytes: int = 40) -> dict:
    """Embed this index's views with a model on **this machine**, in one call.

    The rest of the loop already worked without an external service; this was the
    one step that did not, and it is the step that decides whether the whole thing
    can run on a record that must not leave the machine. Embedding a transcript
    through a hosted API means sending the whole conversation to somebody else.

    The identity written beside the vectors carries the model's **content digest**,
    so a query embedded later is comparable only if the weights are the same bytes.
    A hosted model is a name, and a name can be re-pointed silently; this is the
    one backend where `revision` means something.

    Still no embedding is computed here. ANLA asks; the model answers; everything
    downstream of the vector is deterministic and local.
    """
    target, preserved = _preserved(archive)
    sidecar = _segment_sidecar(target, scheme)
    if not sidecar.exists():
        raise ValueError(f"no index for {scheme!r}; call context_segment first")
    index = SegmentIndex.of(json.loads(sidecar.read_text(encoding="utf-8")))

    engine = backend_for(backend, host=host)
    identity = engine.identity(model, projection_version=index.projection_version,
                               segmentation_scheme=scheme)

    views = [(segment.segment_id, text[:chars]) for segment, text
             in _project_all(index.segments, preserved, min_bytes)]
    eligible = len(views)
    if limit and eligible > limit:
        step = eligible / limit
        views = [views[min(eligible - 1, int(i * step))] for i in range(limit)]

    rows = []
    for start in range(0, len(views), batch):
        chunk = views[start:start + batch]
        rows.extend(zip((key for key, _ in chunk),
                        engine.embed([text for _, text in chunk], model)))
    if not rows:
        raise ValueError(f"no segment of {scheme} reached min_bytes={min_bytes}")

    written = write_vectors(target.with_suffix(f".vectors-{scheme}.anlavec"), rows,
                            identity.as_dict(), extra={"model": identity.model})
    return {
        "archive": str(target), "sidecar": written["file"], "scheme": scheme,
        "embedded": written["count"], "eligible_segments": eligible,
        "segments_in_index": len(index.segments),
        "share_of_index": (round(written["count"] / len(index.segments), 4)
                           if index.segments else None),
        "sampling": "even stride across the record" if limit and eligible > limit
                    else "every eligible segment",
        "sidecar_bytes": written["bytes"],
        "identity": identity.as_dict(),
        "identity_fingerprint": identity.fingerprint,
        "ran_locally": backend == "ollama",
        "plane": "auxiliary — a sidecar beside the archive; the record is untouched",
        "next": "context_address with a query_vector from the same model; the "
                "identity is checked and a mismatch answers INCOMPARABLE",
    }


@mcp.tool()
@_guard
def context_status(archive: str) -> dict:
    """What this context archive holds: snapshots, turns, and what it cost."""
    data = _archive(archive).read_bytes()
    snapshots = list_snapshots(data)
    latest = snapshots[-1]
    turns = _turns_of(data, latest)
    logical = sum(len(t.raw) for t in turns)
    roles: dict[str, int] = {}
    for turn in turns:
        roles[turn.role] = roles.get(turn.role, 0) + 1
    return {
        "archive": str(_archive(archive)),
        "snapshots": len(snapshots),
        "turns": len(turns),
        "context_bytes": logical,
        "archive_bytes": len(data),
        "share_of_context": round(len(data) / logical, 4) if logical else None,
        "unique_chunks": len(latest.manifest["chunks"]),
        "roles": dict(sorted(roles.items(), key=lambda kv: -kv[1])[:10]),
    }


def _around(haystack: str, turn, needle: str) -> str:
    """A window around where the match actually is.

    Drawn from `text` when there is text and from the matched region otherwise —
    because searching the raw record while hinting from the extracted text produced
    a *blank hint* on exactly the hits the extractor could not see, which is the
    subset the raw search was added to reach. A hit an agent cannot judge is a hit
    it cannot use.
    """
    where = haystack.find(needle)
    if where < 0:
        source, where = (turn.text or turn.raw.decode("utf-8", "replace")), 0
    else:
        source = haystack
    start = max(0, where - 60)
    return " ".join(source[start:start + 180].split())


def _turns_of(data: bytes, snapshot) -> list:
    """Rebuild the turn list from the archive, in conversation order.

    Order comes from the paths, which are zero-padded so the archive's own object
    ordering (§5.2.1, by UTF-8 path bytes) *is* the conversation's. Nothing stores
    the sequence separately, so nothing can disagree with it.
    """
    restored = extract_snapshot(data, snapshot)
    turns = []
    for path in sorted(restored):
        parsed = read_jsonl(restored[path])
        if parsed:
            turn = parsed[0]
            turns.append(type(turn)(index=int(path.split("/")[1][:6]), role=turn.role,
                                    raw=turn.raw, tool=turn.tool, text=turn.text))
    return turns


def _bearer_guard(app, token: str):
    """Require `Authorization: Bearer <token>` on every request.

    A shared secret, not OAuth. It exists because of what these tools can do: they
    read and write arbitrary paths on the host, pack directories and extract over
    them. On loopback that is exactly the local agent's own authority and needs
    nothing. The moment the socket leaves the machine it is remote code acting as
    the user, so `--host` beyond loopback *requires* a token below rather than
    warning about it — a warning is a thing you scroll past.
    """
    import hmac

    async def guarded(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        offered = headers.get("authorization", "")
        prefix = "bearer "
        # Constant-time, so the comparison does not leak the token's prefix to
        # something timing the responses.
        ok = (offered[:len(prefix)].lower() == prefix
              and hmac.compare_digest(offered[len(prefix):].strip(), token))
        if not ok:
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length",
                                     str(len(body)).encode("ascii")),
                                    (b"www-authenticate", b'Bearer realm="anla"')]})
            return await send({"type": "http.response.body", "body": body})
        return await app(scope, receive, send)

    return guarded


def _serve_http(host: str, port: int, path: str, token: str,
                allow_hosts: list[str]) -> None:
    import uvicorn
    mcp.settings.host, mcp.settings.port = host, port
    mcp.settings.streamable_http_path = path
    if allow_hosts:
        # FastMCP allow-lists loopback Host headers and answers anything else with
        # 421, which is DNS-rebinding protection and worth keeping: without it a web
        # page could point a name at 127.0.0.1 and drive this server through the
        # visitor's own browser. Behind a tunnel the Host is the public name, so the
        # fix is to *name* the hostname you expect — not to switch the check off,
        # which is the other thing the internet will tell you to do.
        security = mcp.settings.transport_security
        security.allowed_hosts = list(security.allowed_hosts) + allow_hosts
        security.allowed_origins = list(security.allowed_origins) + [
            f"https://{h}" for h in allow_hosts]
    app = mcp.streamable_http_app()
    if token:
        app = _bearer_guard(app, token)
    where = f"http://{host}:{port}{path}"
    print(f"anla MCP on {where}", file=sys.stderr)
    # "loopback only" was a lie the moment a tunnel was pointed at it, and that is
    # exactly when the line matters. --allow-host is the operator saying a public
    # name will arrive, so the banner says what that means.
    if token:
        reach = "bearer token required"
    elif allow_hosts:
        reach = (f"NONE — and reachable as {', '.join(allow_hosts)}, so anything "
                 f"with that URL can call these tools")
    else:
        reach = "none needed (loopback only)"
    print(f"  auth: {reach}", file=sys.stderr)
    print(f"  tools: {len(asyncio.run(mcp.list_tools()))}"
          + (f"  (read-only, confined to {SHARE_ROOT})" if SHARE_ROOT else ""),
          file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="anla_mcp", description="ANLA over MCP — stdio by default, HTTP for "
                                     "clients that want a URL")
    parser.add_argument("--http", action="store_true",
                        help="serve Streamable HTTP instead of stdio, so more than "
                             "one client can use one running server")
    parser.add_argument("--host", default="127.0.0.1",
                        help="default 127.0.0.1; anything else requires --token")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--path", default="/mcp")
    parser.add_argument("--token", default=os.environ.get("ANLA_MCP_TOKEN", ""),
                        help="shared secret; also read from ANLA_MCP_TOKEN")
    parser.add_argument("--allow-host", action="append", default=[],
                        metavar="HOST", dest="allow_hosts",
                        help="an extra Host header to accept, for when a tunnel or "
                             "proxy puts a public name in front. Repeatable. "
                             "Loopback is always accepted; this adds to it rather "
                             "than replacing the DNS-rebinding check.")
    parser.add_argument("--share", metavar="DIR", default="",
                        help="read-only, and confined to DIR. One flag rather than "
                             "two, because half of this configuration is worse than "
                             "neither: writable-but-confined still lets a caller "
                             "overwrite what is in there, and read-only-but-"
                             "unconfined still reads the whole disk.")
    args = parser.parse_args(argv)

    if args.share:
        global SHARE_ROOT
        SHARE_ROOT = pathlib.Path(args.share).expanduser().resolve()
        if not SHARE_ROOT.is_dir():
            parser.error(f"--share {SHARE_ROOT} is not a directory")
        # Removed, not refused at call time: a tool that is absent cannot be
        # attempted, cannot appear in tools/list, and cannot be talked into running
        # by anything that reaches the URL. A tool that refuses is still a tool
        # whose refusal has to be correct every time.
        for name in sorted(WRITING_TOOLS):
            mcp._tool_manager.remove_tool(name)

    if os.environ.get("ANLA_MCP_SELFTEST"):
        print(json.dumps(sorted(t.name for t in asyncio.run(mcp.list_tools()))))
        return 0

    if not args.http:
        # stdio: one client, one process, the client's own authority. No change.
        mcp.run()
        return 0

    loopback = args.host in ("127.0.0.1", "::1", "localhost")
    if not loopback and not args.token:
        parser.error(
            f"--host {args.host} would expose tools that read and write arbitrary "
            f"paths on this machine to anything that can reach the port, with no "
            f"authentication. Pass --token (or set ANLA_MCP_TOKEN) so callers have "
            f"to prove they are you, or leave --host at 127.0.0.1 and put a tunnel "
            f"in front of it. This is refused rather than warned about because a "
            f"warning is a thing you scroll past.")
    _serve_http(args.host, args.port, args.path, args.token, args.allow_hosts)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
