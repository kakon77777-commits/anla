# -*- coding: utf-8 -*-
"""The ``anla`` command line interface.

Every subcommand can emit JSON, because the first-class caller of this tool is
an agent, not a person. Exit codes come from :mod:`anla.errors` and match the
table in the whitepaper, so a failure is machine-classifiable without parsing
prose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .canonical import canonical
from .errors import AnlaError, InvalidInput
from .format import FORMAT_NAME, FORMAT_VERSION
from .reader import Limits, open_archive
from .writer import PackPlan, collect_tree, pack
from .zipexport import export_zip

PROGRAM = "anla"


def _plan_from_args(args: argparse.Namespace) -> PackPlan:
    return PackPlan(
        chunk_size=args.chunk_size,
        compression=args.compression,
        deflate_level=args.deflate_level,
        exclude_globs=tuple(args.exclude or ()),
        preserve_mtime=not args.no_mtime,
    )


def _limits_from_args(args: argparse.Namespace) -> Limits:
    defaults = Limits()
    return Limits(
        max_output_bytes=getattr(args, "max_output_bytes", None) or defaults.max_output_bytes,
        max_chunk_uncompressed=(getattr(args, "max_chunk_bytes", None)
                                or defaults.max_chunk_uncompressed),
    )


def _emit(payload: dict, as_json: bool, lines: list[str]) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for line in lines:
            print(line)


def _uuid_arg(value: str | None) -> bytes | None:
    if value is None:
        return None
    text = value.replace("-", "").strip()
    try:
        raw = bytes.fromhex(text)
    except ValueError as exc:
        raise InvalidInput("--uuid must be 16 bytes of hex", value=value) from exc
    if len(raw) != 16:
        raise InvalidInput("--uuid must be 16 bytes of hex", value=value)
    return raw


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    plan.validate()
    tree = collect_tree(args.source, plan, name=args.name)
    payload = {
        "plan": plan.as_manifest_member(),
        "source": str(Path(args.source)),
        "source_name": tree.name,
        "candidate_files": len(tree.files),
        "candidate_directories": len(tree.directories),
        "candidate_bytes": sum(len(f.data) for f in tree.files),
        "skipped_not_representable": tree.skipped,
        "writer": f"{FORMAT_NAME} {FORMAT_VERSION} (python {__version__})",
    }
    _emit(payload, args.json, [
        f"plan for {payload['source']}",
        f"  files            {payload['candidate_files']}",
        f"  directories      {payload['candidate_directories']}",
        f"  bytes            {payload['candidate_bytes']}",
        f"  chunk size       {plan.chunk_size}",
        f"  compression      {plan.compression}",
        f"  excluded globs   {list(plan.exclude_globs) or '—'}",
        f"  skipped entries  {len(tree.skipped)}",
    ])
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    tree = collect_tree(args.source, plan, name=args.name)
    result = pack(tree, plan, archive_uuid=_uuid_arg(args.uuid), created_ns=args.created_ns)
    output = Path(args.output) if args.output else Path(f"{tree.name}.anla")
    # Verify what we are about to hand over, from the bytes, not from memory.
    archive = open_archive(result.data, full=True, limits=_limits_from_args(args))
    output.write_bytes(result.data)
    payload = {
        "output": str(output),
        "summary": archive.summary,
        "verification": archive.verification,
        "skipped_not_representable": tree.skipped,
    }
    stats = result.statistics
    ratio = (len(result.data) / stats["logical_bytes"]) if stats["logical_bytes"] else 0.0
    _emit(payload, args.json, [
        f"wrote {output}  ({len(result.data)} bytes)",
        f"  files {stats['files']}  directories {stats['directories']}"
        f"  unique chunks {stats['unique_chunks']}/{stats['chunk_references']}",
        f"  logical {stats['logical_bytes']} B  archive {len(result.data)} B"
        f"  ratio {ratio:.3f}",
        f"  verified: {archive.verification['verified_chunks']} chunks,"
        f" {archive.verification['verified_files']} files",
    ])
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    archive = open_archive(args.archive, full=False, limits=_limits_from_args(args))
    payload = {
        "summary": archive.summary,
        "plan": archive.manifest["plan"],
        "preservation": archive.manifest["preservation"],
        "auxiliary_disposable": archive.manifest.get("auxiliary", {}).get("disposable"),
        "decision_log_entries": len(archive.manifest.get("auxiliary", {}).get("decision_log", [])),
        "verification": archive.verification,
    }
    s = archive.summary
    _emit(payload, args.json, [
        f"{s['format']} {s['format_version']}  {s['archive_uuid']}",
        f"  source name      {s['source_name']}",
        f"  archive bytes    {s['archive_bytes']}",
        f"  objects          {s['objects']} ({s['files']} files, {s['directories']} directories)",
        f"  chunks           {s['unique_chunks']} unique / {s['chunk_references']} references",
        f"  logical bytes    {s['logical_bytes']}",
        f"  decoder needs AI {s['decoder_requires_ai']}",
        "  (structure and stored-payload hashes checked; run `verify` for a full decode)",
    ])
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    archive = open_archive(args.archive, full=False, limits=_limits_from_args(args))
    objects = [
        {"type": o["type"], "path": o["path"], "size": o.get("size"),
         "sha256": o.get("sha256"), "chunks": len(o.get("chunks", []))}
        for o in archive.manifest["objects"]
    ]
    _emit({"objects": objects}, args.json, [
        (f"{'d' if o['type'] == 'directory' else '-'} "
         f"{(o['size'] if o['size'] is not None else ''):>12} "
         f"{(o['sha256'] or '')[:16]:16} {o['path']}")
        for o in objects
    ])
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    full = args.mode == "full"
    archive = open_archive(args.archive, full=full, limits=_limits_from_args(args))
    payload = {"verification": archive.verification, "summary": archive.summary}
    v = archive.verification
    _emit(payload, args.json, [
        f"OK  {args.archive}",
        f"  mode             {v['mode']}",
        f"  verified chunks  {v['verified_chunks']}",
        f"  verified files   {v['verified_files']}",
        f"  logical bytes    {v['logical_bytes']}",
    ])
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    archive = open_archive(args.archive, full=True, limits=_limits_from_args(args))
    report = archive.extract_to(args.to, overwrite=args.overwrite)
    payload = {"extraction_report": report.as_dict(), "verification": archive.verification}
    _emit(payload, args.json, [
        f"restored into {report.destination}",
        f"  files {report.files}  directories {report.directories}"
        f"  bytes {report.bytes_written}",
        "  metadata profile: mtime only — this profile stores no permissions,"
        " links or extended attributes",
    ] + [f"  note: {n}" for n in report.notes])
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    archive = open_archive(args.archive, full=True, limits=_limits_from_args(args))
    size = export_zip(archive, args.output)
    _emit({"output": args.output, "bytes": size, "format": "zip-store"}, args.json, [
        f"wrote {args.output}  ({size} bytes, ZIP stored)",
    ])
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    archive = open_archive(args.archive, full=False, limits=_limits_from_args(args))
    manifest = archive.without_auxiliary() if args.strip_auxiliary else archive.manifest
    if args.canonical:
        sys.stdout.write(canonical(manifest) + "\n")
    else:
        json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=f"Agent-Native Lossless Archive — {FORMAT_NAME} {FORMAT_VERSION} "
                    f"reference implementation {__version__}",
    )
    parser.add_argument("--version", action="version",
                        version=f"{PROGRAM} {__version__} ({FORMAT_NAME} {FORMAT_VERSION})")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_limits(p: argparse.ArgumentParser) -> None:
        p.add_argument("--max-output-bytes", type=int, default=None,
                       help="refuse an archive that would restore more than this")
        p.add_argument("--max-chunk-bytes", type=int, default=None,
                       help="refuse a chunk that decodes to more than this")

    def add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="emit a JSON result")

    def add_plan_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--chunk-size", type=int, default=1024 * 1024)
        p.add_argument("--compression", choices=("auto", "deflate", "store"), default="auto")
        p.add_argument("--deflate-level", type=int, default=6)
        p.add_argument("--exclude", action="append", metavar="GLOB",
                       help="exclusion pattern; may be repeated. ** crosses /, * does not")
        p.add_argument("--no-mtime", action="store_true", help="do not preserve mtimes")
        p.add_argument("--name", default=None, help="source name recorded in the manifest")

    p_plan = sub.add_parser("plan", help="produce a packing plan without writing an archive")
    p_plan.add_argument("source")
    add_plan_args(p_plan)
    add_json(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_pack = sub.add_parser("pack", help="pack a directory into an archive")
    p_pack.add_argument("source")
    p_pack.add_argument("-o", "--output", default=None)
    add_plan_args(p_pack)
    p_pack.add_argument("--uuid", default=None,
                        help="fixed archive UUID (hex) — for reproducible output")
    p_pack.add_argument("--created-ns", type=int, default=None,
                        help="fixed creation timestamp in ns — for reproducible output")
    add_limits(p_pack)
    add_json(p_pack)
    p_pack.set_defaults(func=cmd_pack)

    p_inspect = sub.add_parser("inspect", help="read the manifest and check structure")
    p_inspect.add_argument("archive")
    add_limits(p_inspect)
    add_json(p_inspect)
    p_inspect.set_defaults(func=cmd_inspect)

    p_list = sub.add_parser("list", help="list the objects in an archive")
    p_list.add_argument("archive")
    add_limits(p_list)
    add_json(p_list)
    p_list.set_defaults(func=cmd_list)

    p_verify = sub.add_parser("verify", help="verify an archive")
    p_verify.add_argument("archive")
    p_verify.add_argument("--mode", choices=("full", "quick"), default="full")
    add_limits(p_verify)
    add_json(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    p_extract = sub.add_parser("extract", help="verify, then restore an archive")
    p_extract.add_argument("archive")
    p_extract.add_argument("--to", required=True)
    p_extract.add_argument("--overwrite", action="store_true")
    add_limits(p_extract)
    add_json(p_extract)
    p_extract.set_defaults(func=cmd_extract)

    p_export = sub.add_parser("export", help="export a verified archive as a ZIP")
    p_export.add_argument("archive")
    p_export.add_argument("-o", "--output", required=True)
    add_limits(p_export)
    add_json(p_export)
    p_export.set_defaults(func=cmd_export)

    p_manifest = sub.add_parser("manifest", help="print the manifest")
    p_manifest.add_argument("archive")
    p_manifest.add_argument("--canonical", action="store_true",
                            help="print canonical JSON, byte-for-byte as stored")
    p_manifest.add_argument("--strip-auxiliary", action="store_true",
                            help="print the manifest with the intelligence plane emptied")
    add_limits(p_manifest)
    p_manifest.set_defaults(func=cmd_manifest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AnlaError as exc:
        json.dump(exc.as_dict(), sys.stderr, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stderr.write("\n")
        return exc.exit_code
    except FileNotFoundError as exc:
        sys.stderr.write(f"{PROGRAM}: no such file: {exc.filename}\n")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
