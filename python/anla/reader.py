# -*- coding: utf-8 -*-
"""The model-independent reader.

This is the module the whole format exists to make possible: it opens an
archive, verifies it end to end, and restores it — with no model, no network, no
plugin, and no trust in anything the archive says about itself that it cannot
prove.

The verification order matters and is fixed by SPEC.md sections 3, 5 and 8:
header, footer, manifest hash, manifest identity, chunk descriptors, chunk
payload hashes, raw chunk hashes, then per-file coverage and hashes. Nothing is
written to disk until all of it passes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .canonical import canonical_bytes
from .errors import (
    FidelityDegraded,
    IntegrityFailure,
    ManifestInvalid,
    ResourceLimitExceeded,
    UnsafeObject,
    UnsupportedCapability,
)
from .format import (
    CODECS,
    FORMAT_NAME,
    FORMAT_VERSION,
    Footer,
    Header,
    build_footer,
    build_record,
    decode_chunk,
    parse_footer,
    parse_header,
    parse_record,
    safe_path,
    sha256_digest,
    sha256_hex,
)

__all__ = ["Limits", "Archive", "ExtractionReport", "open_archive"]

_HEX64 = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class Limits:
    """Decoder resource limits (SPEC.md section 11). Exceeding one is an error,
    never a warning, and never a reason to relax the limit automatically."""

    max_output_bytes: int = 100 * 1024 ** 3
    max_objects: int = 1_000_000
    max_path_depth: int = 256
    max_name_bytes: int = 4096
    max_chunk_uncompressed: int = 64 * 1024 * 1024
    max_total_ratio: int = 1000


@dataclass
class ExtractionReport:
    """What actually happened, per object. A decoder that cannot apply something
    says so here rather than dropping it silently."""

    destination: str
    files: int = 0
    directories: int = 0
    bytes_written: int = 0
    entries: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "destination": self.destination,
            "files": self.files,
            "directories": self.directories,
            "bytes_written": self.bytes_written,
            "metadata_profile": "mtime-only",
            "not_representable_by_profile": [
                "symlinks", "hard links", "permissions", "ACLs",
                "extended attributes", "alternate data streams", "sparse ranges",
            ],
            "entries": self.entries,
            "notes": self.notes,
        }


class Archive:
    """A verified ANLA-MVP v0.1 archive held in memory."""

    def __init__(self, data: bytes, *, full: bool = True, limits: Limits | None = None):
        self.data = data
        self.limits = limits or Limits()
        self.header: Header = parse_header(data)
        self.footer: Footer = parse_footer(data, self.header)
        self.manifest: dict = self._read_manifest()
        self._chunks: dict[str, bytes] = {}
        self.verified_chunks = 0
        self.verified_files = 0
        self.logical_bytes = 0
        self._verify(full=full)
        self.full_verification = full

    # -- opening ----------------------------------------------------------

    @classmethod
    def from_path(cls, path: str | os.PathLike[str], **kwargs) -> "Archive":
        return cls(Path(path).read_bytes(), **kwargs)

    def _read_manifest(self) -> dict:
        record = parse_record(self.data, self.footer.manifest_record_offset)
        if record.type != "MANF":
            raise ManifestInvalid("footer does not point at a MANF record",
                                  found=record.type, offset=record.offset)
        if record.total_length != self.footer.manifest_record_length:
            raise ManifestInvalid("manifest record length disagrees with the footer",
                                  record=record.total_length,
                                  footer=self.footer.manifest_record_length)
        payload = self.data[record.payload_offset:record.payload_offset + record.payload_length]
        if sha256_digest(payload) != self.footer.manifest_payload_sha256:
            raise IntegrityFailure("manifest SHA-256 does not match the footer")
        try:
            manifest = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ManifestInvalid(f"manifest is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ManifestInvalid("manifest is not a JSON object")
        if manifest.get("format") != FORMAT_NAME or manifest.get("format_version") != FORMAT_VERSION:
            raise UnsupportedCapability(
                "archive declares a different format profile",
                format=manifest.get("format"), format_version=manifest.get("format_version"),
                supported=f"{FORMAT_NAME} {FORMAT_VERSION}",
            )
        if manifest.get("archive_uuid") != self.header.uuid_text:
            raise IntegrityFailure("manifest UUID does not match the bootstrap header",
                                   manifest=manifest.get("archive_uuid"),
                                   header=self.header.uuid_text)
        for member in ("objects", "chunks", "statistics", "preservation", "plan"):
            if member not in manifest:
                raise ManifestInvalid(f"manifest is missing required member: {member}")
        if not isinstance(manifest["objects"], list) or not isinstance(manifest["chunks"], dict):
            raise ManifestInvalid("manifest objects must be an array and chunks an object")
        # SPEC.md section 4.3: the stream is one CHNK per unique chunk then one
        # MANF, so the manifest's sequence is determined rather than merely
        # increasing. Checked here because a reader that jumps straight to the
        # manifest can check it, and one that cannot check an invariant does not
        # have one.
        expected_sequence = len(manifest["chunks"]) + 1
        if record.sequence != expected_sequence:
            raise ManifestInvalid("manifest record sequence is not len(chunks) + 1",
                                  sequence=record.sequence, expected=expected_sequence)
        if len(manifest["objects"]) > self.limits.max_objects:
            raise ResourceLimitExceeded("archive declares more objects than the limit allows",
                                        objects=len(manifest["objects"]),
                                        limit=self.limits.max_objects)
        return manifest

    # -- verification -----------------------------------------------------

    def _verify(self, full: bool) -> None:
        self._verify_chunks(full=full)
        self._verify_objects(full=full)

    def _verify_chunks(self, full: bool) -> None:
        declared_raw = 0
        seen_sequences: set[int] = set()
        for chunk_id, descriptor in self.manifest["chunks"].items():
            if len(chunk_id) != 64 or not set(chunk_id) <= _HEX64:
                raise ManifestInvalid("chunk id is not lowercase 64-hex", chunk_id=chunk_id[:80])
            if not isinstance(descriptor, dict):
                raise ManifestInvalid("chunk descriptor is not an object", chunk_id=chunk_id)
            for key in ("record_offset", "record_length", "payload_offset",
                        "payload_length", "raw_size", "codec", "payload_sha256"):
                if key not in descriptor:
                    raise ManifestInvalid(f"chunk descriptor is missing {key}", chunk_id=chunk_id)
            codec = descriptor["codec"]
            if codec not in CODECS:
                raise UnsupportedCapability("unsupported codec", codec=codec, chunk_id=chunk_id)
            raw_size = _as_int(descriptor["raw_size"], "raw_size")
            if raw_size > self.limits.max_chunk_uncompressed:
                raise ResourceLimitExceeded("chunk exceeds the per-chunk size limit",
                                            chunk_id=chunk_id, raw_size=raw_size,
                                            limit=self.limits.max_chunk_uncompressed)
            declared_raw += raw_size
            if declared_raw > self.limits.max_output_bytes:
                raise ResourceLimitExceeded("archive declares more raw bytes than the limit allows",
                                            declared=declared_raw,
                                            limit=self.limits.max_output_bytes)

            record = parse_record(self.data, _as_int(descriptor["record_offset"], "record_offset"))
            if record.type != "CHNK":
                raise ManifestInvalid("chunk descriptor points at a non-CHNK record",
                                      chunk_id=chunk_id, found=record.type)
            if record.total_length != _as_int(descriptor["record_length"], "record_length"):
                raise IntegrityFailure("chunk record length disagrees with the descriptor",
                                       chunk_id=chunk_id)
            if not 1 <= record.sequence <= len(self.manifest["chunks"]):
                raise ManifestInvalid("chunk record sequence is out of range",
                                      chunk_id=chunk_id, sequence=record.sequence,
                                      chunks=len(self.manifest["chunks"]))
            if record.sequence in seen_sequences:
                raise ManifestInvalid("two chunk records share a sequence number",
                                      chunk_id=chunk_id, sequence=record.sequence)
            seen_sequences.add(record.sequence)
            if (record.header.get("chunk_id") != chunk_id
                    or record.header.get("codec") != codec
                    or record.header.get("raw_size") != raw_size):
                raise IntegrityFailure("chunk record header disagrees with the descriptor",
                                       chunk_id=chunk_id)
            # The descriptor's offsets are convenience; the parsed record is the
            # authority, so they are checked rather than trusted.
            if (record.payload_offset != _as_int(descriptor["payload_offset"], "payload_offset")
                    or record.payload_length != _as_int(descriptor["payload_length"],
                                                        "payload_length")):
                raise IntegrityFailure("chunk payload extent disagrees with the descriptor",
                                       chunk_id=chunk_id)

            payload = self.data[record.payload_offset:record.payload_offset + record.payload_length]
            if sha256_hex(payload) != descriptor["payload_sha256"]:
                raise IntegrityFailure("stored chunk payload hash mismatch", chunk_id=chunk_id)
            if full:
                raw = decode_chunk(payload, codec, raw_size,
                                   max_chunk_output=self.limits.max_chunk_uncompressed)
                if sha256_hex(raw) != chunk_id:
                    raise IntegrityFailure("raw chunk hash does not match its content id",
                                           chunk_id=chunk_id)
                self._chunks[chunk_id] = raw
                self.verified_chunks += 1

    def _verify_objects(self, full: bool) -> None:
        seen: set[str] = set()
        total = 0
        for obj in self.manifest["objects"]:
            if not isinstance(obj, dict):
                raise ManifestInvalid("object entry is not an object")
            path = safe_path(obj.get("path"))
            if path != obj.get("path"):
                raise UnsafeObject("object path is not stored in normalized form", path=obj["path"])
            if len(path.encode("utf-8")) > self.limits.max_name_bytes:
                raise ResourceLimitExceeded("object path exceeds the name length limit", path=path)
            if path.count("/") + 1 > self.limits.max_path_depth:
                raise ResourceLimitExceeded("object path exceeds the depth limit", path=path)
            if path in seen:
                raise UnsafeObject("duplicate object path", path=path)
            seen.add(path)

            kind = obj.get("type")
            if kind == "directory":
                continue
            if kind != "file":
                raise UnsupportedCapability("unsupported object type", type=kind, path=path)

            size = _as_int(obj.get("size"), "size")
            refs = obj.get("chunks")
            if not isinstance(refs, list):
                raise ManifestInvalid("file object has no chunk reference list", path=path)
            length = 0
            parts: list[bytes] = []
            for ref in refs:
                if not isinstance(ref, dict) or "id" not in ref or "length" not in ref:
                    raise ManifestInvalid("malformed chunk reference", path=path)
                descriptor = self.manifest["chunks"].get(ref["id"])
                if descriptor is None:
                    raise ManifestInvalid("chunk reference points at an unknown chunk",
                                          path=path, chunk_id=ref["id"])
                if descriptor["raw_size"] != _as_int(ref["length"], "length"):
                    raise IntegrityFailure("chunk reference length disagrees with the chunk",
                                           path=path, chunk_id=ref["id"])
                length += descriptor["raw_size"]
                if full:
                    parts.append(self._chunks[ref["id"]])
            if length != size:
                raise IntegrityFailure("chunk coverage does not add up to the file size",
                                       path=path, covered=length, size=size)
            total += size
            if total > self.limits.max_output_bytes:
                raise ResourceLimitExceeded("archive restores more bytes than the limit allows",
                                            declared=total, limit=self.limits.max_output_bytes)
            if full:
                content = b"".join(parts)
                if sha256_hex(content) != obj.get("sha256"):
                    raise IntegrityFailure("file content hash mismatch", path=path)
                self.verified_files += 1
        self.logical_bytes = total

    # -- accessors --------------------------------------------------------

    @property
    def summary(self) -> dict:
        stats = self.manifest.get("statistics", {})
        return {
            "archive_uuid": self.header.uuid_text,
            "archive_bytes": len(self.data),
            "format": self.manifest["format"],
            "format_version": self.manifest["format_version"],
            "source_name": self.manifest.get("source_name"),
            "created_unix_ns": self.manifest.get("created_unix_ns"),
            "hash_algorithm": self.manifest.get("hash_algorithm"),
            "snapshot_sequence": self.manifest.get("snapshot_sequence"),
            "decoder_requires_ai": self.manifest["preservation"].get("decoder_requires_ai"),
            **{k: stats[k] for k in sorted(stats)},
        }

    @property
    def verification(self) -> dict:
        return {
            "status": "ok",
            "mode": "full" if self.full_verification else "quick",
            "verified_chunks": self.verified_chunks,
            "verified_files": self.verified_files,
            "logical_bytes": self.logical_bytes,
        }

    def files(self) -> Iterator[dict]:
        for obj in self.manifest["objects"]:
            if obj.get("type") == "file":
                yield obj

    def directories(self) -> Iterator[dict]:
        for obj in self.manifest["objects"]:
            if obj.get("type") == "directory":
                yield obj

    def read(self, path: str) -> bytes:
        """Return one file's verified content."""
        for obj in self.files():
            if obj["path"] == path:
                if not self.full_verification:
                    raise IntegrityFailure("archive was opened without full verification")
                return b"".join(self._chunks[ref["id"]] for ref in obj["chunks"])
        raise ManifestInvalid("no such object in the archive", path=path)

    def without_auxiliary(self) -> dict:
        """The manifest with the intelligence plane emptied.

        Used by the conformance suite to prove the plane is disposable: the
        manifest bytes change, what a decoder extracts does not.
        """
        stripped = dict(self.manifest)
        stripped["auxiliary"] = {"decision_log": [], "disposable": True}
        return stripped

    def rewrite_without_auxiliary(self) -> bytes:
        """Return a new, valid archive with the intelligence plane emptied.

        This is the disposability claim as an operation rather than an assertion.
        A planner's decision log records what a model was told and what it chose,
        which is exactly the sort of thing you might not want to hand to someone
        along with the data — so being able to drop it, and still have an archive
        that verifies and extracts identically, is a feature and not only a test.

        Only the manifest record and the footer are rebuilt. Every chunk record
        keeps its bytes and its offset, so the chunk descriptors stay true.
        """
        manifest = self.without_auxiliary()
        payload = canonical_bytes(manifest)
        record = parse_record(self.data, self.footer.manifest_record_offset)
        prefix = self.data[:self.footer.manifest_record_offset]
        rebuilt = build_record(
            "MANF",
            {"encoding": "canonical-json",
             "payload_sha256": sha256_hex(payload),
             "preservation_required": True},
            payload, record.sequence,
        )
        return prefix + rebuilt + build_footer(
            len(prefix), len(rebuilt), self.header.archive_uuid, sha256_digest(payload))

    # -- extraction -------------------------------------------------------

    def extract_to(self, destination: str | os.PathLike[str], *,
                   overwrite: bool = False) -> ExtractionReport:
        """Restore the archive under *destination*.

        Nothing is written until the whole archive has verified, and every path
        is re-validated and confined to the destination before it is opened.
        """
        if not self.full_verification:
            raise IntegrityFailure("refusing to extract an archive that was not fully verified")
        root = Path(destination).resolve()
        root.mkdir(parents=True, exist_ok=True)
        report = ExtractionReport(destination=str(root))
        # Identity of every file this run has written, so that a filesystem which
        # cannot tell two archive paths apart is caught instead of silently
        # collapsing them. Windows folds case; macOS folds NFC against NFD. Both
        # would make one file overwrite the other, which is exactly the loss this
        # format exists to prevent — so it is an error naming both paths.
        written_identity: dict[tuple[int, int], str] = {}

        for obj in self.manifest["objects"]:
            path = safe_path(obj["path"])
            target = (root / path).resolve()
            if root != target and root not in target.parents:
                raise UnsafeObject("object path escapes the destination", path=path)
            if obj["type"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
                report.directories += 1
                report.entries.append({"path": path, "kind": "directory", "result": "created"})
                continue
            if target.exists():
                stat = target.stat()
                collided = written_identity.get((stat.st_dev, stat.st_ino))
                if collided is not None:
                    raise FidelityDegraded(
                        "two distinct archive paths collide on the target filesystem",
                        paths=[collided, path], target=str(target),
                        reason="the destination cannot represent both names distinctly",
                    )
                if not overwrite:
                    raise UnsafeObject("destination file already exists", path=path)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = self.read(obj["path"])
            target.write_bytes(content)
            stat = target.stat()
            written_identity[(stat.st_dev, stat.st_ino)] = path
            report.files += 1
            report.bytes_written += len(content)
            entry = {"path": path, "kind": "file", "result": "restored",
                     "content": "verified", "bytes": len(content)}
            mtime_ns = obj.get("metadata", {}).get("mtime_ns")
            if mtime_ns is not None:
                try:
                    os.utime(target, ns=(int(mtime_ns), int(mtime_ns)))
                    entry["mtime"] = "restored"
                except (OSError, ValueError):
                    entry["mtime"] = "unsupported-on-target"
                    report.notes.append(f"could not apply mtime to {path}")
            else:
                entry["mtime"] = "not-in-archive"
            report.entries.append(entry)

        if report.files != self.verified_files:
            raise IntegrityFailure("extracted file count does not match the verified count",
                                   extracted=report.files, verified=self.verified_files)
        return report


def _as_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestInvalid(f"{field_name} must be an integer", got=repr(value)[:80])
    if value < 0:
        raise ManifestInvalid(f"{field_name} must not be negative", value=value)
    return value


def open_archive(path_or_bytes, **kwargs) -> Archive:
    """Open an archive from a path, a file object, or bytes."""
    if isinstance(path_or_bytes, (bytes, bytearray, memoryview)):
        return Archive(bytes(path_or_bytes), **kwargs)
    if hasattr(path_or_bytes, "read"):
        return Archive(path_or_bytes.read(), **kwargs)
    return Archive.from_path(path_or_bytes, **kwargs)
