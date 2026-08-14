# -*- coding: utf-8 -*-
"""A local inspector for ANLA 1.0 — drive the real implementations from a browser.

    python tools/inspector/serve.py            # then open http://127.0.0.1:8731

Nothing here is simulated. Packing runs `anla1` in this process or `anla1-rs` as a
subprocess, against a directory on this machine, and every number the page shows was
measured by the run that produced it. That is the point: the project has a benchmark
that says what the format costs and a specification that says what it means, and
neither lets you *watch* it happen to your own files.

Deliberately not part of the published site. The site is served by a Worker with
`connect-src 'none'`, and a page that reads your filesystem has no business being
reachable from the internet. This binds to 127.0.0.1 and says so.

Standard library only, like the rest of the tooling here.
"""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import pathlib
import shutil
import socketserver
import subprocess
import sys
import tempfile
import time
import traceback
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "python"))

from anla.errors import AnlaError  # noqa: E402
from anla.fastcdc import CdcProfile  # noqa: E402
from anla1 import container as C  # noqa: E402
from anla1.fs import restore_tree, scan_tree  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    CODEC_STORE, CODEC_ZSTD, cdc_chunker, list_snapshots, single_chunk,
    verify_archive, write_snapshot,
)

RUST_DIR = ROOT / "rust" / "target" / "release"
WORK = pathlib.Path(tempfile.gettempdir()) / "anla-inspector"


def rust_binary() -> pathlib.Path | None:
    return next((RUST_DIR / n for n in ("anla1-rs.exe", "anla1-rs")
                 if (RUST_DIR / n).exists()), None)


def tree_size(root: pathlib.Path) -> tuple[int, int]:
    total = count = 0
    for entry in root.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            total += entry.stat().st_size
            count += 1
    return total, count


# ---------------------------------------------------------------------------
# the operations, each returning what it measured
# ---------------------------------------------------------------------------

def do_pack(body: dict) -> dict:
    source = pathlib.Path(body["source"]).expanduser()
    if not source.is_dir():
        raise ValueError(f"not a directory: {source}")
    logical, files = tree_size(source)
    if logical > 4 * 1024 ** 3:
        raise ValueError(f"{logical / 1024**3:.1f} GiB is more than this inspector "
                         f"will pack in a browser request; use the CLI")

    WORK.mkdir(parents=True, exist_ok=True)
    archive = WORK / "inspector.anla"
    archive.unlink(missing_ok=True)

    engine = body.get("engine", "python")
    chunking = body.get("chunking", "anla-cdc-1")
    codec = body.get("codec", "zstd")
    avg = int(body.get("chunk_avg") or 262144)

    started = time.perf_counter()
    if engine == "rust":
        binary = rust_binary()
        if binary is None:
            raise ValueError("the Rust binary is not built — run "
                             "`cargo build --release` in rust/")
        # `cdc` / `none` are what both CLIs call these, and `--chunk-avg` has to be
        # passed explicitly or Rust uses its own default and the two writers stop
        # agreeing — which is how the inspector's first run found that Rust silently
        # ignored `--chunking anla-cdc-1` altogether.
        command = [str(binary), "pack", str(source), "-o", str(archive),
                   "--chunking", "cdc" if chunking == "anla-cdc-1" else "none",
                   "--chunk-avg", str(avg), "--codec", codec,
                   "--uuid", "000102030405060708090a0b0c0d0e0f",
                   "--created-ns", "1", "--no-metadata"]
        done = subprocess.run(command, capture_output=True, encoding="utf-8",
                              errors="replace")
        if done.returncode != 0:
            raise ValueError((done.stdout or done.stderr or "").strip()[:400])
    else:
        tree = scan_tree(source, preserve_mtime=False, preserve_posix=False)
        write_snapshot(
            archive, **tree.as_source(), created_unix_ns=1,
            archive_id=bytes(range(16)),
            chunker=cdc_chunker(CdcProfile(
                min_size=max(1024, avg // 4), avg_size=avg, max_size=avg * 4))
            if chunking == "anla-cdc-1" else single_chunk,
            codec=CODEC_ZSTD if codec == "zstd" else CODEC_STORE)
    elapsed = time.perf_counter() - started

    data = archive.read_bytes()
    snapshot = list_snapshots(data)[-1]
    return {
        "archive": str(archive),
        "engine": engine,
        "seconds": round(elapsed, 3),
        "mib_per_second": round((logical / 1024 ** 2) / elapsed, 1) if elapsed else None,
        "logical_bytes": logical,
        "files": files,
        "archive_bytes": len(data),
        "ratio": round(len(data) / logical, 4) if logical else None,
        "snapshots": len(list_snapshots(data)),
        "chunks": len(snapshot.manifest["chunks"]),
        "objects": len(snapshot.manifest["objects"]),
    }


def do_verify(_body: dict) -> dict:
    archive = WORK / "inspector.anla"
    data = archive.read_bytes()
    started = time.perf_counter()
    report = verify_archive(data)
    elapsed = time.perf_counter() - started
    result = {
        "ok": True,
        "seconds": round(elapsed, 3),
        "mib_per_second": round((len(data) / 1024 ** 2) / elapsed, 1) if elapsed else None,
        "snapshots": len(report.snapshots),
    }
    binary = rust_binary()
    if binary is not None:
        # The second reader, on the same bytes. Two implementations agreeing is the
        # claim this whole project rests on, and it should be visible rather than
        # asserted in a README.
        done = subprocess.run([str(binary), "verify", str(archive)],
                              capture_output=True, encoding="utf-8", errors="replace")
        result["rust"] = (done.stdout or done.stderr or "").strip()[:300]
        result["rust_agrees"] = done.returncode == 0
    return result


def do_extract(_body: dict) -> dict:
    archive = WORK / "inspector.anla"
    data = archive.read_bytes()
    destination = WORK / "restored"
    shutil.rmtree(destination, ignore_errors=True)
    started = time.perf_counter()
    report = restore_tree(data, list_snapshots(data)[-1], destination)
    elapsed = time.perf_counter() - started
    return {
        "destination": str(destination),
        "seconds": round(elapsed, 3),
        "files": report.files,
        "directories": report.directories,
        "links": report.links,
        "bytes_written": report.bytes_written,
        "names_not_applied": report.names_not_applied,
        "metadata_not_applied": report.metadata_not_applied,
    }


def do_compare(body: dict) -> dict:
    """Did every restored byte match the source? Compared on disk, in binary.

    `verify` proves an archive is internally consistent; it cannot prove the bytes
    are the ones that went in, because a writer that consistently stored the wrong
    content would also have consistently hashed it. This is the other half.
    """
    source = pathlib.Path(body["source"]).expanduser()
    destination = WORK / "restored"
    if not destination.is_dir():
        raise ValueError("nothing has been extracted yet")

    mismatches, missing, checked = [], [], 0
    for entry in sorted(source.rglob("*")):
        if not entry.is_file() or entry.is_symlink():
            continue
        relative = entry.relative_to(source)
        landed = destination / relative
        if not landed.is_file():
            missing.append(str(relative).replace("\\", "/"))
            continue
        checked += 1
        if entry.read_bytes() != landed.read_bytes():
            mismatches.append(str(relative).replace("\\", "/"))
    return {
        "checked": checked,
        "identical": not mismatches and not missing,
        "mismatched": mismatches[:20],
        "missing": missing[:20],
    }


def do_append(body: dict) -> dict:
    """A second snapshot of a directory, to make deduplication visible."""
    source = pathlib.Path(body["source"]).expanduser()
    if not source.is_dir():
        raise ValueError(f"not a directory: {source}")
    archive = WORK / "inspector.anla"
    before = archive.stat().st_size

    tree = scan_tree(source, preserve_mtime=False, preserve_posix=False)
    started = time.perf_counter()
    after = write_snapshot(archive, **tree.as_source(), created_unix_ns=2,
                           chunker=cdc_chunker() if body.get("chunking") == "anla-cdc-1"
                           else single_chunk,
                           codec=CODEC_ZSTD if body.get("codec") == "zstd" else CODEC_STORE)
    elapsed = time.perf_counter() - started
    logical, _ = tree_size(source)
    return {
        "seconds": round(elapsed, 3),
        "archive_before": before,
        "archive_after": after,
        "added": after - before,
        "logical_bytes": logical,
        "share_of_input": round((after - before) / logical, 5) if logical else None,
        "snapshots": len(list_snapshots(archive.read_bytes())),
    }


def do_manifest(_body: dict) -> dict:
    """What the archive says about itself. The two planes, side by side."""
    data = (WORK / "inspector.anla").read_bytes()
    snapshots = list_snapshots(data)
    latest = snapshots[-1]
    manifest = latest.manifest
    header = C.parse_header(data)

    objects = [{
        "kind": entry["kind"],
        "path": entry["path"],
        "size": entry.get("size", 0),
        "chunks": len(entry.get("chunks", [])),
        "object_id": entry["object_id"].hex(),
        "native_name": entry["name"].hex() if "name" in entry else None,
    } for entry in manifest["objects"]]

    chunks = [{
        "chunk_id": cid.hex(),
        "raw_size": d["raw_size"],
        "stored": d["payload_length"],
        "codec": "zstd" if d["codec_id"] == 1 else "store",
        "offset": d["record_offset"],
    } for cid, d in list(manifest["chunks"].items())]

    return {
        "archive_uuid": header.archive_uuid.hex(),
        "snapshots": [{"sequence": s.sequence, "objects": len(s.manifest["objects"]),
                       "chunks": len(s.manifest["chunks"])} for s in snapshots],
        "roots": {name: manifest[name].hex() for name in (
            "objects_root", "chunks_root", "metadata_root",
            "preservation_root", "auxiliary_root")},
        "required_capabilities": manifest["required_capabilities"],
        "optional_capabilities": manifest["optional_capabilities"],
        "packing_plan": _plain(manifest.get("packing_plan")),
        "objects_list": sorted(objects, key=lambda o: -o["size"])[:400],
        "chunks_list": sorted(chunks, key=lambda c: c["offset"])[:400],
        "object_total": len(objects),
        "chunk_total": len(chunks),
    }


def _plain(value):
    """CBOR values into something `json` will take. Bytes become hex."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def do_both(body: dict) -> dict:
    """Pack the same tree with both writers and diff the bytes.

    This is the project's central claim — two implementations sharing no code below
    `blake3` and `zstd` emit identical archives — and it existed only as a CI script.
    Making it a button is not decoration: doing it by hand, once, immediately found
    that the Rust CLI silently ignored `--chunking anla-cdc-1` and wrote a manifest
    with no `packing_plan`, which is what stops a later append from cutting at
    different boundaries and deduplicating against nothing.

    `store` only. §8: compressed output is a function of the compressor, and the
    Rust crate and the Python wheel need not bundle the same libzstd, so a zstd
    difference is expected rather than a defect.
    """
    both = {}
    for engine in ("python", "rust"):
        result = do_pack({**body, "engine": engine, "codec": "store"})
        archive = pathlib.Path(result["archive"])
        kept = archive.with_name(f"compare-{engine}.anla")
        kept.write_bytes(archive.read_bytes())
        both[engine] = {"bytes": result["archive_bytes"],
                        "seconds": result["seconds"],
                        "mib_per_second": result["mib_per_second"],
                        "path": str(kept)}
    body = {**body, "_logical": tree_size(pathlib.Path(body["source"]).expanduser())[0]}
    a = pathlib.Path(both["python"]["path"]).read_bytes()
    b = pathlib.Path(both["rust"]["path"]).read_bytes()
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    if first is None and len(a) != len(b):
        first = min(len(a), len(b))
    return {
        "identical": a == b,
        "python": both["python"], "rust": both["rust"],
        "size_difference": len(a) - len(b),
        "first_differing_byte": first,
        "speedup": (round(both["rust"]["mib_per_second"] / both["python"]["mib_per_second"], 1)
                    if both["python"]["mib_per_second"] else None),
        # Below a few MiB the Rust number is mostly process startup — it is a
        # subprocess while the Python writer runs in this one — so the ratio says
        # more about `CreateProcess` than about either writer. Reporting it anyway
        # and letting the reader guess would be the unfair-benchmark mistake again,
        # in the other direction.
        "ratio_is_meaningful": body.get("_logical", 0) >= 16 * 1024 ** 2,
    }


ACTIONS = {
    "both": do_both,
    "pack": do_pack, "verify": do_verify, "extract": do_extract,
    "compare": do_compare, "append": do_append, "manifest": do_manifest,
}


# ---------------------------------------------------------------------------
# the server
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "anla-inspector"

    def log_message(self, fmt, *args):        # one line per action, not per asset
        if "/api/" in (self.path or ""):
            sys.stderr.write(f"  {self.path}\n")

    def handle_one_request(self) -> None:
        # A browser that navigates away mid-response aborts the connection, and the
        # default handler prints a full traceback for it. Harmless, and it buries
        # the one line per action this server is supposed to show.
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        name = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        target = (HERE / name).resolve()
        if HERE not in target.parents or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind.endswith("javascript"):
            kind += "; charset=utf-8"
        self._send(200, target.read_bytes(), kind)

    def do_POST(self) -> None:
        action = self.path.rsplit("/", 1)[-1]
        if not self.path.startswith("/api/") or action not in ACTIONS:
            self._send(404, b'{"error":"no such action"}', "application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            payload = ACTIONS[action](body)
            status = 200
        except AnlaError as exc:
            payload = {"error": exc.message, "code": exc.code,
                       "details": _plain(exc.details)}
            status = 400
        except Exception as exc:                       # noqa: BLE001 — shown, not swallowed
            payload = {"error": str(exc) or type(exc).__name__,
                       "traceback": traceback.format_exc()[-1500:]}
            status = 400
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-p", "--port", type=int, default=8731)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    binary = rust_binary()
    print(f"ANLA inspector — http://127.0.0.1:{args.port}")
    print("  python writer : in this process")
    print(f"  rust writer   : {binary if binary else 'not built (cargo build --release in rust/)'}")
    print(f"  work directory: {WORK}")
    print("  bound to 127.0.0.1 only; ctrl-c to stop\n")
    if not args.no_open:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    with Server(("127.0.0.1", args.port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
