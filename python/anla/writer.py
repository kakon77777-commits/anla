# -*- coding: utf-8 -*-
"""The deterministic writer.

An AI planner may decide *how* to pack — chunk size, codec, what to exclude —
but it does not write bytes. It produces a :class:`PackPlan`, the plan is
validated, and this module is the only thing that emits an archive. Everything
here is a pure function of (objects, plan, uuid, timestamp), which is what makes
reproducible mode possible.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from .canonical import canonical_bytes
from .errors import InvalidInput
from .format import (
    CODEC_DEFLATE,
    CODECS,
    FORMAT_NAME,
    FORMAT_VERSION,
    HEADER_SIZE,
    build_footer,
    build_header,
    build_record,
    encode_chunk,
    safe_path,
    sha256_digest,
    sha256_hex,
    uuid_text,
)
from .globs import matches_any

__all__ = ["PackPlan", "SourceFile", "SourceTree", "PackResult", "pack", "collect_tree"]

COMPRESSION_MODES = ("auto", CODEC_DEFLATE, "store")


@dataclass(frozen=True)
class PackPlan:
    """A packing plan. Serialized verbatim into the manifest as audit evidence."""

    chunk_size: int = 1024 * 1024
    compression: str = "auto"
    deflate_level: int = 6
    exclude_globs: tuple[str, ...] = ()
    preserve_mode: bool = False
    preserve_mtime: bool = True
    verification: str = "full"
    plan_version: str = "0.1"

    def validate(self) -> None:
        if self.chunk_size < 1:
            raise InvalidInput("chunk_size must be at least 1 byte", chunk_size=self.chunk_size)
        if self.compression not in COMPRESSION_MODES:
            raise InvalidInput("unknown compression mode", mode=self.compression,
                               supported=list(COMPRESSION_MODES))
        if not 0 <= self.deflate_level <= 9:
            raise InvalidInput("deflate_level must be 0..9", level=self.deflate_level)
        if self.verification not in ("full", "quick"):
            raise InvalidInput("verification must be full or quick", value=self.verification)
        if self.preserve_mode:
            # SPEC.md section 8.1: this profile defines no mode metadata, so a
            # writer that accepted the flag would be claiming a fidelity it does
            # not deliver.
            raise InvalidInput("preserve_mode is not implemented by ANLA-MVP v0.1")

    def as_manifest_member(self) -> dict:
        return {
            "plan_version": self.plan_version,
            "chunk_size": self.chunk_size,
            "compression": self.compression,
            "deflate_level": self.deflate_level,
            "exclude_globs": list(self.exclude_globs),
            "preserve_mode": self.preserve_mode,
            "preserve_mtime": self.preserve_mtime,
            "verification": self.verification,
        }


@dataclass
class SourceFile:
    """One file to pack. *data* is the content; *path* is the archive path."""

    path: str
    data: bytes
    mtime_ns: int | None = None


@dataclass
class SourceTree:
    files: list[SourceFile] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    name: str = "workspace"
    #: Entries found on disk that this profile cannot represent, so they were
    #: left out of the declared object set instead of being misrepresented.
    skipped: list[str] = field(default_factory=list)


@dataclass
class PackResult:
    data: bytes
    manifest: dict
    statistics: dict

    @property
    def size(self) -> int:
        return len(self.data)


def _excluded(path: str, plan: PackPlan) -> bool:
    return matches_any(path, plan.exclude_globs)


def _sort_key(path: str) -> bytes:
    """Object ordering is by UTF-8 bytes (SPEC.md section 8.1).

    Not by locale collation: the original browser build used localeCompare,
    which made the manifest bytes depend on the machine that wrote them.
    """
    return path.encode("utf-8")


def collect_tree(root: str | os.PathLike[str], plan: PackPlan | None = None,
                 name: str | None = None, follow_symlinks: bool = False) -> SourceTree:
    """Read a directory tree from disk into a :class:`SourceTree`.

    Symbolic links are skipped by default and reported, because this profile
    cannot represent them ([SPEC.md section 8.1]). Silently following them would
    turn a link into a second copy of its target and quietly change what the
    archive means.
    """
    plan = plan or PackPlan()
    root_path = Path(root)
    if not root_path.is_dir():
        raise InvalidInput("source must be an existing directory", source=str(root_path))
    tree = SourceTree(name=name or root_path.name or "workspace")
    skipped: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=follow_symlinks):
        dirnames.sort()
        filenames.sort()
        here = Path(dirpath)
        for dirname in list(dirnames):
            entry = here / dirname
            rel = PurePosixPath(entry.relative_to(root_path).as_posix())
            if entry.is_symlink() and not follow_symlinks:
                skipped.append(str(rel))
                dirnames.remove(dirname)
                continue
            tree.directories.append(str(rel))
        for filename in filenames:
            entry = here / filename
            rel = str(PurePosixPath(entry.relative_to(root_path).as_posix()))
            if entry.is_symlink() and not follow_symlinks:
                skipped.append(rel)
                continue
            if not entry.is_file():
                skipped.append(rel)
                continue
            stat = entry.stat()
            tree.files.append(SourceFile(path=rel, data=entry.read_bytes(),
                                         mtime_ns=stat.st_mtime_ns))
    tree.files.sort(key=lambda f: _sort_key(f.path))
    tree.directories.sort(key=_sort_key)
    tree.skipped = sorted(skipped)
    return tree


def pack(tree: SourceTree, plan: PackPlan | None = None, *,
         archive_uuid: bytes | None = None, created_ns: int | None = None) -> PackResult:
    """Build an archive. Supplying both *archive_uuid* and *created_ns* makes the
    output byte-exact and reproducible (SPEC.md section 10)."""
    plan = plan or PackPlan()
    plan.validate()

    archive_uuid = archive_uuid if archive_uuid is not None else secrets.token_bytes(16)
    if len(archive_uuid) != 16:
        raise InvalidInput("archive UUID must be 16 bytes", got=len(archive_uuid))
    created_ns = created_ns if created_ns is not None else time.time_ns()

    pieces: list[bytes] = [build_header(archive_uuid)]
    offset = HEADER_SIZE
    sequence = 1
    logical_bytes = 0
    stored_payload_bytes = 0
    chunk_references = 0

    chunks: dict[str, dict] = {}
    objects: list[dict] = []
    decision_log: list[dict] = []

    seen_dirs: set[str] = set()
    for raw_dir in tree.directories:
        path = safe_path(raw_dir)
        if path in seen_dirs or _excluded(path, plan):
            continue
        seen_dirs.add(path)
        objects.append({"type": "directory", "path": path, "metadata": {}})

    for source in sorted(tree.files, key=lambda f: _sort_key(f.path)):
        path = safe_path(source.path)
        if _excluded(path, plan):
            continue
        data = source.data
        logical_bytes += len(data)
        file_chunks: list[dict] = []
        for start in range(0, len(data), plan.chunk_size):
            raw = data[start:start + plan.chunk_size]
            chunk_id = sha256_hex(raw)
            chunk_references += 1
            if chunk_id not in chunks:
                codec, payload = encode_chunk(raw, plan.compression, plan.deflate_level)
                payload_sha256 = sha256_hex(payload)
                record = build_record(
                    "CHNK",
                    {"chunk_id": chunk_id, "raw_size": len(raw),
                     "codec": codec, "payload_sha256": payload_sha256},
                    payload, sequence,
                )
                sequence += 1
                pieces.append(record)
                payload_offset = offset + (len(record) - len(payload))
                chunks[chunk_id] = {
                    "record_offset": offset,
                    "record_length": len(record),
                    "payload_offset": payload_offset,
                    "payload_length": len(payload),
                    "raw_size": len(raw),
                    "codec": codec,
                    "payload_sha256": payload_sha256,
                }
                decision_log.append({
                    "chunk_id": chunk_id,
                    "raw_size": len(raw),
                    "stored_size": len(payload),
                    "codec": codec,
                    "reason": _reason(plan.compression, codec),
                })
                offset += len(record)
                stored_payload_bytes += len(payload)
            file_chunks.append({"id": chunk_id, "length": len(raw)})

        metadata: dict = {}
        if plan.preserve_mtime and source.mtime_ns is not None:
            metadata["mtime_ns"] = str(int(source.mtime_ns))
        objects.append({
            "type": "file",
            "path": path,
            "size": len(data),
            "sha256": sha256_hex(data),
            "chunks": file_chunks,
            "metadata": metadata,
        })

    objects.sort(key=lambda o: (_sort_key(o["path"]), o["type"].encode("utf-8")))

    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "archive_uuid": uuid_text(archive_uuid),
        "created_unix_ns": str(created_ns),
        "hash_algorithm": "sha256",
        "manifest_encoding": "canonical-json",
        "snapshot_sequence": 1,
        "source_name": tree.name,
        "plan": plan.as_manifest_member(),
        "preservation": {
            "lossless": True,
            "decoder_requires_ai": False,
            "object_coverage": "all-selected-objects",
        },
        "objects": objects,
        "chunks": chunks,
        "statistics": {
            "objects": len(objects),
            "files": sum(1 for o in objects if o["type"] == "file"),
            "directories": sum(1 for o in objects if o["type"] == "directory"),
            "unique_chunks": len(chunks),
            "chunk_references": chunk_references,
            "logical_bytes": logical_bytes,
            "stored_payload_bytes": stored_payload_bytes,
        },
        "auxiliary": {"decision_log": decision_log, "disposable": True},
    }

    manifest_payload = canonical_bytes(manifest)
    manifest_record = build_record(
        "MANF",
        {"encoding": "canonical-json",
         "payload_sha256": sha256_hex(manifest_payload),
         "preservation_required": True},
        manifest_payload, sequence,
    )
    manifest_offset = offset
    pieces.append(manifest_record)
    offset += len(manifest_record)
    pieces.append(build_footer(manifest_offset, len(manifest_record),
                               archive_uuid, sha256_digest(manifest_payload)))

    data = b"".join(pieces)
    return PackResult(data=data, manifest=manifest, statistics=dict(manifest["statistics"]))


def _reason(mode: str, codec: str) -> str:
    if mode != "auto":
        return "forced-by-plan"
    return "smaller-representation" if codec == CODEC_DEFLATE else "compression-not-beneficial"


def pack_paths(paths: Iterable[str | os.PathLike[str]], root: str | os.PathLike[str],
               plan: PackPlan | None = None, **kwargs) -> PackResult:
    """Pack an explicit list of files, resolved relative to *root*."""
    plan = plan or PackPlan()
    root_path = Path(root)
    tree = SourceTree(name=root_path.name or "workspace")
    for item in paths:
        entry = Path(item)
        rel = str(PurePosixPath(entry.relative_to(root_path).as_posix()))
        stat = entry.stat()
        tree.files.append(SourceFile(path=rel, data=entry.read_bytes(), mtime_ns=stat.st_mtime_ns))
    return pack(tree, plan, **kwargs)


def known_codecs() -> Sequence[str]:
    return CODECS
