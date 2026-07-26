# -*- coding: utf-8 -*-
"""Binary layout of ANLA-MVP v0.1: header, record frame, footer, codecs, paths.

Nothing in here knows about files or trees. It is the byte level only, so that
the writer and the reader share exactly one definition of the layout.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_bytes
from .errors import (
    IntegrityFailure,
    InvalidInput,
    ManifestInvalid,
    ResourceLimitExceeded,
    UnsafeObject,
    UnsupportedCapability,
)

__all__ = [
    "ARCHIVE_MAGIC", "RECORD_MAGIC", "FOOTER_MAGIC",
    "HEADER_SIZE", "RECORD_FRAME_SIZE", "FOOTER_SIZE",
    "VERSION_MAJOR", "VERSION_MINOR", "RECORD_VERSION",
    "FORMAT_NAME", "FORMAT_VERSION", "MAX_RECORD_HEADER",
    "CODEC_STORE", "CODEC_DEFLATE", "CODECS",
    "crc32", "sha256_hex", "sha256_digest",
    "build_header", "parse_header", "build_footer", "parse_footer",
    "build_record", "parse_record", "Record", "Header", "Footer",
    "encode_chunk", "decode_chunk", "safe_path", "uuid_text",
]

ARCHIVE_MAGIC = bytes([0x41, 0x4E, 0x4C, 0x41, 0x0D, 0x0A, 0x1A, 0x0A])  # ANLA\r\n\x1a\n
RECORD_MAGIC = b"ANLR"
FOOTER_MAGIC = b"ANLAFTR\0"

HEADER_SIZE = 64
RECORD_FRAME_SIZE = 40
FOOTER_SIZE = 96

VERSION_MAJOR = 0
VERSION_MINOR = 1
RECORD_VERSION = 1

FORMAT_NAME = "ANLA-MVP"
FORMAT_VERSION = "0.1"

MAX_RECORD_HEADER = 16 * 1024 * 1024

CODEC_STORE = "store"
CODEC_DEFLATE = "deflate"
CODECS = (CODEC_STORE, CODEC_DEFLATE)


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

def crc32(data: bytes) -> int:
    """CRC-32 (ISO-HDLC), the same polynomial zlib and PNG use."""
    return zlib.crc32(data) & 0xFFFFFFFF


def sha256_digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def uuid_text(raw: bytes) -> str:
    if len(raw) != 16:
        raise InvalidInput("archive UUID must be 16 bytes", got=len(raw))
    h = raw.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ---------------------------------------------------------------------------
# bootstrap header
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Header:
    version_major: int
    version_minor: int
    archive_uuid: bytes

    @property
    def uuid_text(self) -> str:
        return uuid_text(self.archive_uuid)


def build_header(archive_uuid: bytes) -> bytes:
    if len(archive_uuid) != 16:
        raise InvalidInput("archive UUID must be 16 bytes", got=len(archive_uuid))
    buf = bytearray(HEADER_SIZE)
    buf[0:8] = ARCHIVE_MAGIC
    struct.pack_into("<HHI", buf, 8, VERSION_MAJOR, VERSION_MINOR, 0)
    buf[16:32] = archive_uuid
    struct.pack_into("<I", buf, 60, crc32(bytes(buf[0:60])))
    return bytes(buf)


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_SIZE + FOOTER_SIZE:
        raise ManifestInvalid("archive is smaller than a header plus a footer",
                             size=len(data), minimum=HEADER_SIZE + FOOTER_SIZE)
    head = data[:HEADER_SIZE]
    if head[:8] != ARCHIVE_MAGIC:
        raise ManifestInvalid("invalid ANLA bootstrap magic", found=head[:8].hex())
    major, minor, _reserved = struct.unpack_from("<HHI", head, 8)
    if (major, minor) != (VERSION_MAJOR, VERSION_MINOR):
        raise ManifestInvalid("unsupported ANLA version",
                              found=f"{major}.{minor}", supported=f"{VERSION_MAJOR}.{VERSION_MINOR}")
    if crc32(head[:60]) != struct.unpack_from("<I", head, 60)[0]:
        raise IntegrityFailure("bootstrap header CRC mismatch")
    return Header(major, minor, head[16:32])


# ---------------------------------------------------------------------------
# record frame
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Record:
    offset: int
    type: str
    version: int
    flags: int
    header: dict
    header_bytes: bytes
    payload_offset: int
    payload_length: int
    sequence: int

    @property
    def total_length(self) -> int:
        return RECORD_FRAME_SIZE + len(self.header_bytes) + self.payload_length


def build_record(record_type: str, header: dict, payload: bytes, sequence: int) -> bytes:
    if len(record_type) != 4 or not record_type.isascii():
        raise InvalidInput("record type must be four ASCII bytes", got=record_type)
    header_bytes = canonical_bytes(header)
    if len(header_bytes) > MAX_RECORD_HEADER:
        raise InvalidInput("record header exceeds 16 MiB", size=len(header_bytes))
    frame = bytearray(RECORD_FRAME_SIZE)
    frame[0:4] = RECORD_MAGIC
    frame[4:8] = record_type.encode("ascii")
    struct.pack_into("<HHI", frame, 8, RECORD_VERSION, 0, len(header_bytes))
    struct.pack_into("<QQ", frame, 16, len(payload), sequence)
    struct.pack_into("<II", frame, 32, crc32(header_bytes), 0)
    return bytes(frame) + header_bytes + payload


def parse_record(data: bytes, offset: int) -> Record:
    """Parse one record. Every declared length is bounded before it is used."""
    if offset < 0 or offset + RECORD_FRAME_SIZE > len(data):
        raise ManifestInvalid("record frame lies outside the archive", offset=offset)
    frame = data[offset:offset + RECORD_FRAME_SIZE]
    if frame[:4] != RECORD_MAGIC:
        raise ManifestInvalid("invalid record magic", offset=offset, found=frame[:4].hex())
    version, flags, header_length = struct.unpack_from("<HHI", frame, 8)
    payload_length, sequence = struct.unpack_from("<QQ", frame, 16)
    expected_crc, _reserved = struct.unpack_from("<II", frame, 32)
    if header_length > MAX_RECORD_HEADER:
        raise ManifestInvalid("record header exceeds 16 MiB", offset=offset, size=header_length)
    end = offset + RECORD_FRAME_SIZE + header_length + payload_length
    if end > len(data):
        raise ManifestInvalid("record extent lies outside the archive",
                              offset=offset, declared_end=end, archive_size=len(data))
    if sequence < 1:
        raise ManifestInvalid("record sequence must be at least 1",
                              offset=offset, sequence=sequence)
    header_bytes = data[offset + RECORD_FRAME_SIZE:offset + RECORD_FRAME_SIZE + header_length]
    if crc32(header_bytes) != expected_crc:
        raise IntegrityFailure("record header CRC mismatch", offset=offset)
    try:
        header = _json_object(header_bytes)
    except ValueError as exc:
        raise ManifestInvalid(f"record header is not a JSON object: {exc}", offset=offset) from exc
    record_type = frame[4:8].decode("ascii", errors="replace")
    return Record(
        offset=offset,
        type=record_type,
        version=version,
        flags=flags,
        header=header,
        header_bytes=header_bytes,
        payload_offset=offset + RECORD_FRAME_SIZE + header_length,
        payload_length=payload_length,
        sequence=sequence,
    )


def _json_object(raw: bytes) -> dict:
    import json
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# footer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Footer:
    manifest_record_offset: int
    manifest_record_length: int
    archive_uuid: bytes
    manifest_payload_sha256: bytes


def build_footer(manifest_offset: int, manifest_length: int,
                 archive_uuid: bytes, manifest_hash: bytes) -> bytes:
    if len(manifest_hash) != 32:
        raise InvalidInput("manifest hash must be 32 bytes", got=len(manifest_hash))
    buf = bytearray(FOOTER_SIZE)
    buf[0:8] = FOOTER_MAGIC
    struct.pack_into("<HHI", buf, 8, VERSION_MAJOR, VERSION_MINOR, 0)
    struct.pack_into("<QQ", buf, 16, manifest_offset, manifest_length)
    buf[32:48] = archive_uuid
    buf[48:80] = manifest_hash
    struct.pack_into("<I", buf, 92, crc32(bytes(buf[0:92])))
    return bytes(buf)


def parse_footer(data: bytes, header: Header) -> Footer:
    foot = data[len(data) - FOOTER_SIZE:]
    if foot[:8] != FOOTER_MAGIC:
        raise ManifestInvalid("invalid ANLA footer magic", found=foot[:8].hex())
    major, minor, _reserved = struct.unpack_from("<HHI", foot, 8)
    if (major, minor) != (VERSION_MAJOR, VERSION_MINOR):
        raise ManifestInvalid("unsupported footer version", found=f"{major}.{minor}")
    if crc32(foot[:92]) != struct.unpack_from("<I", foot, 92)[0]:
        raise IntegrityFailure("footer CRC mismatch")
    manifest_offset, manifest_length = struct.unpack_from("<QQ", foot, 16)
    if foot[32:48] != header.archive_uuid:
        raise IntegrityFailure("header and footer disagree about the archive UUID")
    return Footer(manifest_offset, manifest_length, foot[32:48], foot[48:80])


# ---------------------------------------------------------------------------
# codecs
# ---------------------------------------------------------------------------

def encode_chunk(raw: bytes, compression: str, deflate_level: int = 6) -> tuple[str, bytes]:
    """Return ``(codec, payload)`` for one raw chunk.

    ``auto`` keeps the compressed representation only when it saves more than
    the eight-byte margin defined in SPEC.md section 8.3.
    """
    if compression == CODEC_STORE:
        return CODEC_STORE, raw
    compressed = zlib.compress(raw, deflate_level)
    if compression == CODEC_DEFLATE:
        return CODEC_DEFLATE, compressed
    if compression == "auto":
        if len(compressed) + 8 < len(raw):
            return CODEC_DEFLATE, compressed
        return CODEC_STORE, raw
    raise InvalidInput("unknown compression mode", mode=compression)


def decode_chunk(payload: bytes, codec: str, raw_size: int,
                 max_chunk_output: int | None = None) -> bytes:
    """Decode one chunk payload.

    *max_chunk_output* is refused up front, on the declared size, so a hostile
    archive never gets as far as allocating. The decompression itself is then
    bounded by ``raw_size``: a chunk that expands past what it declared is
    stopped mid-stream rather than after the fact.
    """
    if max_chunk_output is not None and raw_size > max_chunk_output:
        raise ResourceLimitExceeded("chunk declares more raw bytes than the limit allows",
                                    declared_raw_size=raw_size, limit=max_chunk_output)
    if codec == CODEC_STORE:
        if len(payload) != raw_size:
            raise IntegrityFailure("stored chunk length mismatch",
                                   declared=raw_size, actual=len(payload))
        return payload
    if codec != CODEC_DEFLATE:
        raise UnsupportedCapability("unsupported codec", codec=codec)
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(payload, raw_size + 1)
    if len(raw) > raw_size or not decompressor.eof or decompressor.unconsumed_tail:
        raise ResourceLimitExceeded("chunk decodes to more bytes than it declares",
                                    declared_raw_size=raw_size, produced_at_least=len(raw))
    if len(raw) != raw_size:
        raise IntegrityFailure("decompressed chunk length mismatch",
                               declared=raw_size, actual=len(raw))
    return raw


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

_RESERVED_FIRST = ("/", "\\")


def safe_path(path: Any) -> str:
    """Validate a manifest path per SPEC.md section 9, returning it normalized.

    This is called by the writer before packing and by the reader before any
    extraction. The reader's call is the security boundary; the writer's is a
    courtesy that turns a bad input into an error instead of an artifact.
    """
    if not isinstance(path, str) or not path:
        raise UnsafeObject("object path must be a non-empty string", path=repr(path))
    if "\0" in path:
        raise UnsafeObject("object path contains NUL", path=repr(path))
    if path[0] in _RESERVED_FIRST:
        raise UnsafeObject("object path is absolute or a UNC path", path=path)
    if len(path) >= 2 and path[1] == ":" and path[0].isascii() and path[0].isalpha():
        raise UnsafeObject("object path carries a drive letter", path=path)
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise UnsafeObject("unsafe object path component", path=path, component=part)
    return "/".join(parts)
