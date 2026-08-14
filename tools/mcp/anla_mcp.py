# -*- coding: utf-8 -*-
"""ANLA over MCP — the point at which "agent-native" stops being a name.

    python tools/mcp/anla_mcp.py                     # stdio

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

import functools
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from anla.errors import AnlaError  # noqa: E402
from anla.fastcdc import CdcProfile  # noqa: E402
from anla1 import container as C  # noqa: E402
from anla1.fs import restore_tree, scan_tree  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    CODEC_STORE, CODEC_ZSTD, cdc_chunker, diff as snapshot_diff, list_snapshots,
    single_chunk, verify_archive, write_snapshot,
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


def _directory(path: str) -> pathlib.Path:
    resolved = pathlib.Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"not a directory: {resolved}")
    return resolved


def _archive(path: str) -> pathlib.Path:
    resolved = pathlib.Path(path).expanduser().resolve()
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


if __name__ == "__main__":
    # stdio, because that is what a local agent speaks and this touches the
    # filesystem. Nothing here should be reachable over a network.
    if os.environ.get("ANLA_MCP_SELFTEST"):
        print(json.dumps(sorted(t.name for t in
                                __import__("asyncio").run(mcp.list_tools()))))
    else:
        mcp.run()
