# -*- coding: utf-8 -*-
"""The ANLA 1.0 container: header, record frame, footer chain, capabilities.

Byte level only — nothing here knows about files, trees or codecs, so the writer
and the reader share exactly one definition of the layout. Specified in
SPEC-1.0-DRAFT.md sections 3, 4, 6 and 9.

Three things differ from MVP in ways that changed the design rather than the
constants, and each is the reason 1.0 needs its own magic number:

**Records carry flags, and the default is refusal.** A reader that meets a record
type it does not know consults `REQUIRED_FOR_EXTRACTION` and
`AUXILIARY_DISPOSABLE`. With neither set it refuses, because a writer that wanted
the record skippable had a bit to say so; guessing is how a preservation format
loses data quietly.

**There is one footer per snapshot, chained backwards.** Old footers are never
rewritten, which is what makes an interrupted append safe: the archive reads as
the previous snapshot rather than as damaged. The consequence is that the footer is
no longer at a fixed offset, so it has to be *found*.

**The header's `latest_footer_hint` is never used to decide which snapshot is
latest.** It is only a starting guess. The reader determines the latest footer by
scanning backwards from the end, and a hint that disagrees is ignored rather than
believed — because an interrupted append leaves a hint pointing at a footer that
was never finished, and a reader that trusts it reports an older snapshot as
current with every hash checking out.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from anla.errors import (  # the error vocabulary is shared: same codes, same exit codes
    AnlaError,
    IntegrityFailure,
    InvalidInput,
    ManifestInvalid,
    ResourceLimitExceeded,
    UnsupportedCapability,
)

from .blake3 import blake3_256
from .cbor import CborError, decode, encode

__all__ = [
    "ARCHIVE_MAGIC", "RECORD_MAGIC", "HEADER_SIZE", "RECORD_FRAME_SIZE",
    "VERSION_MAJOR", "VERSION_MINOR", "MAX_RECORD_HEADER",
    "FLAG_REQUIRED_FOR_EXTRACTION", "FLAG_REQUIRED_FOR_VERIFICATION",
    "FLAG_ENCRYPTED", "FLAG_COMPRESSED_METADATA", "FLAG_AUXILIARY_DISPOSABLE",
    "RECORD_TYPES", "KNOWN_CAPABILITIES", "HASHES", "CORE_HASH",
    "Header", "Record", "Footer",
    "build_header", "parse_header", "with_footer_hint",
    "build_record", "parse_record", "padding_for", "record_disposition",
    "build_footer_record", "parse_footer_record",
    "find_latest_footer", "walk_footers", "check_capabilities", "hash_bytes",
]

ARCHIVE_MAGIC = bytes([0x41, 0x4E, 0x4C, 0x41, 0x31, 0x0D, 0x0A, 0x1A])  # ANLA1\r\n\x1a
RECORD_MAGIC = b"ANLR"

HEADER_SIZE = 64
RECORD_FRAME_SIZE = 40
RECORD_ALIGNMENT = 8

VERSION_MAJOR = 1
VERSION_MINOR = 0
RECORD_VERSION = 1

MAX_RECORD_HEADER = 16 * 1024 * 1024

FLAG_REQUIRED_FOR_EXTRACTION = 1 << 0
FLAG_REQUIRED_FOR_VERIFICATION = 1 << 1
FLAG_ENCRYPTED = 1 << 2
FLAG_COMPRESSED_METADATA = 1 << 3
FLAG_AUXILIARY_DISPOSABLE = 1 << 4
FLAGS_DEFINED = (FLAG_REQUIRED_FOR_EXTRACTION | FLAG_REQUIRED_FOR_VERIFICATION
                 | FLAG_ENCRYPTED | FLAG_COMPRESSED_METADATA
                 | FLAG_AUXILIARY_DISPOSABLE)

#: Types this implementation knows. Anything else is handled by its flags, which
#: is the whole point of having them.
RECORD_TYPES = ("CHNK", "MANF", "FOOT", "INDX", "META", "AUXI", "SIGN", "PARI")

KNOWN_CAPABILITIES = frozenset({
    "anla:core:objects:1",
    "anla:core:chunks:1",
    "anla:core:snapshots:1",
    "anla:hash:blake3-256:1",
    "anla:hash:sha256:1",
    "anla:codec:store:1",
    "anla:codec:zstd:1",
    "anla:chunking:anla-cdc-1",
    # A reader that does not know this kind refuses the manifest outright, so it is
    # required rather than optional — unlike a metadata namespace, which an
    # ignorant reader can verify and extract around.
    "anla:object:symlink:1",
    # Metadata namespaces are *optional* capabilities on purpose. Metadata lives
    # inside `object_id`, so a reader that has never heard of one verifies exactly
    # the same bytes and only loses the ability to apply it. Requiring them would
    # refuse an archive this reader could restore the contents of perfectly.
    "anla:metadata:common:1",
    "anla:metadata:posix:1",
})

#: Hash agility, and the footer names its own: a footer is read *before* the
#: manifest that would declare `hash_algorithms`, so it cannot inherit the
#: choice from it. Found while implementing the footer, not while writing the
#: draft — see SPEC-1.0-DRAFT.md section 6.
#:
#: This table being the only place that had to change when BLAKE3 arrived is the
#: agility claim paying off: no container field moved, and archives written with
#: SHA-256 before it existed still read.
HASHES: dict[str, Callable[[bytes], bytes]] = {
    "blake3-256": blake3_256,          # the core hash (SPEC-1.0-DRAFT.md section 7)
    "sha256": lambda data: hashlib.sha256(data).digest(),
}

#: The core hash a conforming 1.0 reader must implement. Declared separately from
#: the table so that "what we happen to support" and "what the format requires"
#: cannot drift into each other.
CORE_HASH = "blake3-256"


def hash_bytes(data: bytes, algorithm: str) -> bytes:
    """Hash with the *named* algorithm.

    There is deliberately no default. Every caller has read the name from the
    archive — a footer's record header, or the manifest's `hash_algorithms` — and a
    default here would be an invitation to skip that read, which is precisely the
    mistake MVP made by inferring the hash from the profile version.
    """
    function = HASHES.get(algorithm)
    if function is None:
        raise UnsupportedCapability("unsupported hash algorithm", algorithm=algorithm,
                                    supported=sorted(HASHES))
    return function(data)


def crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# bootstrap header
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Header:
    version_major: int
    version_minor: int
    header_size: int
    global_flags: int
    first_record_offset: int
    latest_footer_hint: int
    archive_uuid: bytes


def build_header(archive_uuid: bytes, *, latest_footer_hint: int = 0) -> bytes:
    if len(archive_uuid) != 16:
        raise InvalidInput("archive UUID must be 16 bytes", got=len(archive_uuid))
    if latest_footer_hint < 0:
        raise InvalidInput("footer hint must not be negative", hint=latest_footer_hint)
    buf = bytearray(HEADER_SIZE)
    buf[0:8] = ARCHIVE_MAGIC
    struct.pack_into("<HHI", buf, 8, VERSION_MAJOR, VERSION_MINOR, HEADER_SIZE)
    struct.pack_into("<QQQ", buf, 16, 0, HEADER_SIZE, latest_footer_hint)
    buf[40:56] = archive_uuid
    struct.pack_into("<I", buf, 56, crc32(bytes(buf[0:56])))
    return bytes(buf)


def parse_header(data: bytes) -> Header:
    if len(data) < HEADER_SIZE:
        raise ManifestInvalid("archive is shorter than a bootstrap header",
                              size=len(data), minimum=HEADER_SIZE)
    head = data[:HEADER_SIZE]
    if head[:8] != ARCHIVE_MAGIC:
        raise ManifestInvalid("invalid ANLA 1.0 magic", found=head[:8].hex())
    major, minor, header_size = struct.unpack_from("<HHI", head, 8)
    if major != VERSION_MAJOR:
        raise UnsupportedCapability("unsupported major version", found=major,
                                    supported=VERSION_MAJOR)
    if crc32(head[:56]) != struct.unpack_from("<I", head, 56)[0]:
        raise IntegrityFailure("bootstrap header CRC mismatch")
    global_flags, first_record_offset, hint = struct.unpack_from("<QQQ", head, 16)
    if global_flags != 0:
        # Reserved means reserved: a reader that ignores an unknown global flag is
        # a reader that will one day ignore the flag that mattered.
        raise UnsupportedCapability("unknown global flags are set", flags=global_flags)
    if header_size < HEADER_SIZE or header_size > len(data):
        raise ManifestInvalid("header_size is not inside the archive", header_size=header_size)
    if first_record_offset < header_size:
        raise ManifestInvalid("first record overlaps the header",
                              first_record_offset=first_record_offset,
                              header_size=header_size)
    return Header(major, minor, header_size, global_flags, first_record_offset,
                  hint, head[40:56])


def with_footer_hint(data: bytes, hint: int) -> bytes:
    """Return *data* with the header's footer hint updated and its CRC repaired.

    A writer appending a snapshot rewrites this one 64-byte prefix. That the hint
    can therefore be stale — or torn, if the process dies mid-write — is exactly
    why no reader is permitted to believe it (`find_latest_footer`).
    """
    header = parse_header(data)
    return build_header(header.archive_uuid, latest_footer_hint=hint) + data[HEADER_SIZE:]


# ---------------------------------------------------------------------------
# record frame
# ---------------------------------------------------------------------------

def padding_for(unpadded_length: int) -> int:
    """Bytes of zero padding needed to reach the next 8-byte boundary."""
    return (-unpadded_length) % RECORD_ALIGNMENT


@dataclass(frozen=True)
class Record:
    offset: int
    type: str
    version: int
    flags: int
    header: dict
    header_length: int
    payload_offset: int
    payload_length: int
    sequence: int

    @property
    def unpadded_length(self) -> int:
        return RECORD_FRAME_SIZE + self.header_length + self.payload_length

    @property
    def total_length(self) -> int:
        return self.unpadded_length + padding_for(self.unpadded_length)

    @property
    def end(self) -> int:
        return self.offset + self.total_length


def build_record(record_type: str, header: dict, payload: bytes, sequence: int,
                 flags: int = FLAG_REQUIRED_FOR_EXTRACTION) -> bytes:
    if len(record_type) != 4 or not record_type.isascii():
        raise InvalidInput("record type must be four ASCII bytes", got=record_type)
    if sequence < 1:
        raise InvalidInput("record sequence must be at least 1", sequence=sequence)
    if flags & ~FLAGS_DEFINED:
        raise InvalidInput("undefined record flags", flags=flags)
    if (flags & FLAG_REQUIRED_FOR_EXTRACTION) and (flags & FLAG_AUXILIARY_DISPOSABLE):
        raise InvalidInput("a record cannot be both required and disposable", flags=flags)
    header_bytes = encode(header)
    if len(header_bytes) > MAX_RECORD_HEADER:
        raise InvalidInput("record header exceeds 16 MiB", size=len(header_bytes))
    frame = bytearray(RECORD_FRAME_SIZE)
    frame[0:4] = RECORD_MAGIC
    frame[4:8] = record_type.encode("ascii")
    struct.pack_into("<HHI", frame, 8, RECORD_VERSION, flags, len(header_bytes))
    struct.pack_into("<QQ", frame, 16, len(payload), sequence)
    struct.pack_into("<II", frame, 32, crc32(header_bytes), 0)
    body = bytes(frame) + header_bytes + payload
    return body + bytes(padding_for(len(body)))


def parse_record(data: bytes, offset: int) -> Record:
    """Parse one record. Every declared length is bounded before it is used."""
    if offset < 0 or offset + RECORD_FRAME_SIZE > len(data):
        raise ManifestInvalid("record frame lies outside the archive", offset=offset)
    if offset % RECORD_ALIGNMENT:
        raise ManifestInvalid("record offset is not 8-byte aligned", offset=offset)
    frame = data[offset:offset + RECORD_FRAME_SIZE]
    if frame[:4] != RECORD_MAGIC:
        raise ManifestInvalid("invalid record magic", offset=offset, found=frame[:4].hex())
    version, flags, header_length = struct.unpack_from("<HHI", frame, 8)
    payload_length, sequence = struct.unpack_from("<QQ", frame, 16)
    expected_crc, reserved = struct.unpack_from("<II", frame, 32)
    if reserved != 0:
        raise ManifestInvalid("reserved record field is not zero", offset=offset)
    if flags & ~FLAGS_DEFINED:
        raise UnsupportedCapability("undefined record flags are set",
                                    offset=offset, flags=flags)
    if (flags & FLAG_REQUIRED_FOR_EXTRACTION) and (flags & FLAG_AUXILIARY_DISPOSABLE):
        raise ManifestInvalid("record claims to be both required and disposable",
                              offset=offset, flags=flags)
    if sequence < 1:
        raise ManifestInvalid("record sequence must be at least 1",
                              offset=offset, sequence=sequence)
    if header_length > MAX_RECORD_HEADER:
        # A declared limit being exceeded is a resource limit, not a malformed
        # manifest. The two readers classified this differently and the fuzzer said
        # so; the caller's next move differs, which is the whole reason the codes
        # are separate — one says "find another copy", the other says "this was
        # written by something broken".
        raise ResourceLimitExceeded("record header exceeds 16 MiB", offset=offset,
                                    size=header_length, limit=MAX_RECORD_HEADER)
    unpadded = RECORD_FRAME_SIZE + header_length + payload_length
    end = offset + unpadded + padding_for(unpadded)
    if end > len(data):
        raise ManifestInvalid("record extent lies outside the archive", offset=offset,
                              declared_end=end, archive_size=len(data))
    header_bytes = data[offset + RECORD_FRAME_SIZE:offset + RECORD_FRAME_SIZE + header_length]
    if crc32(header_bytes) != expected_crc:
        raise IntegrityFailure("record header CRC mismatch", offset=offset)
    if any(data[offset + unpadded:end]):
        raise ManifestInvalid("record padding is not zero", offset=offset)
    try:
        header = decode(header_bytes) if header_length else {}
    except CborError as exc:
        raise ManifestInvalid(f"record header is not canonical CBOR: {exc}",
                             offset=offset) from exc
    if not isinstance(header, dict):
        raise ManifestInvalid("record header is not a CBOR map", offset=offset)
    # §4: a record type is four ASCII bytes. `errors="replace"` used to stand here,
    # which turned a malformed type into U+FFFD and carried on — the writer checked
    # it and the reader repaired it, which is the same asymmetry the strict CBOR
    # decoder exists to refuse. Found by the Rust reader, which checked it, and the
    # 1.0 differential fuzzer, which noticed the two disagreeing.
    try:
        record_type = frame[4:8].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ManifestInvalid("record type is not four ASCII bytes", offset=offset,
                              found=frame[4:8].hex()) from exc
    return Record(offset=offset, type=record_type,
                  version=version, flags=flags, header=header,
                  header_length=header_length,
                  payload_offset=offset + RECORD_FRAME_SIZE + header_length,
                  payload_length=payload_length, sequence=sequence)


def record_disposition(record: Record) -> str:
    """``"known"``, ``"skip"`` or ``"fail"`` — SPEC-1.0-DRAFT.md section 4.2.

    The default is refusal. A record that says nothing about itself is treated as
    required, because a writer that wanted it skippable had a bit for that.
    """
    if record.type in RECORD_TYPES:
        return "known"
    if record.flags & FLAG_AUXILIARY_DISPOSABLE:
        return "skip"
    return "fail"


def walk_records(data: bytes, header: Header | None = None) -> Iterator[Record]:
    """Every record from the front, in order. Used for recovery and for tests."""
    header = header or parse_header(data)
    at = header.first_record_offset
    while at < len(data):
        record = parse_record(data, at)
        yield record
        at = record.end


# ---------------------------------------------------------------------------
# footer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Footer:
    record: Record
    snapshot_sequence: int
    manifest_offset: int
    manifest_length: int
    previous_footer_offset: int | None
    preservation_root: bytes
    auxiliary_root: bytes | None
    index_offset: int | None
    hash_algorithm: str

    @property
    def offset(self) -> int:
        return self.record.offset


def build_footer_record(*, sequence: int, snapshot_sequence: int,
                        manifest_offset: int, manifest_length: int,
                        preservation_root: bytes,
                        previous_footer_offset: int | None = None,
                        auxiliary_root: bytes | None = None,
                        index_offset: int | None = None,
                        index_length: int | None = None,
                        hash_algorithm: str = CORE_HASH) -> bytes:
    """One `FOOT` record. Absent values are omitted, never encoded as null."""
    payload_map: dict[str, Any] = {
        "snapshot_sequence": snapshot_sequence,
        "manifest_offset": manifest_offset,
        "manifest_length": manifest_length,
        "preservation_root": preservation_root,
    }
    if previous_footer_offset is not None:
        payload_map["previous_footer_offset"] = previous_footer_offset
    if auxiliary_root is not None:
        payload_map["auxiliary_root"] = auxiliary_root
    if index_offset is not None:
        payload_map["index_offset"] = index_offset
        payload_map["index_length"] = index_length or 0
    payload = encode(payload_map)
    # The footer names its own hash algorithm. It is read before the manifest that
    # declares `hash_algorithms`, so it cannot inherit the choice from it — a
    # consequence of hash agility that only appears once you write the reader.
    header = {"hash_algorithm": hash_algorithm,
              "payload_hash": hash_bytes(payload, hash_algorithm)}
    return build_record("FOOT", header, payload, sequence)


def parse_footer_record(data: bytes, offset: int) -> Footer:
    record = parse_record(data, offset)
    if record.type != "FOOT":
        raise ManifestInvalid("record is not a FOOT", offset=offset, found=record.type)
    algorithm = record.header.get("hash_algorithm")
    if not isinstance(algorithm, str):
        raise ManifestInvalid("footer does not name its hash algorithm", offset=offset)
    payload = data[record.payload_offset:record.payload_offset + record.payload_length]
    expected = record.header.get("payload_hash")
    if not isinstance(expected, bytes):
        raise ManifestInvalid("footer header has no payload hash", offset=offset)
    if hash_bytes(payload, algorithm) != expected:
        raise IntegrityFailure("footer payload hash mismatch", offset=offset)
    try:
        body = decode(payload)
    except CborError as exc:
        raise ManifestInvalid(f"footer payload is not canonical CBOR: {exc}",
                             offset=offset) from exc
    if not isinstance(body, dict):
        raise ManifestInvalid("footer payload is not a CBOR map", offset=offset)
    for required in ("snapshot_sequence", "manifest_offset", "manifest_length",
                     "preservation_root"):
        if required not in body:
            raise ManifestInvalid(f"footer is missing {required}", offset=offset)
    root = body["preservation_root"]
    if not isinstance(root, bytes):
        raise ManifestInvalid("preservation_root is not a byte string", offset=offset)
    return Footer(record=record,
                  snapshot_sequence=_as_index(body["snapshot_sequence"], "snapshot_sequence"),
                  manifest_offset=_as_index(body["manifest_offset"], "manifest_offset"),
                  manifest_length=_as_index(body["manifest_length"], "manifest_length"),
                  previous_footer_offset=(
                      _as_index(body["previous_footer_offset"], "previous_footer_offset")
                      if "previous_footer_offset" in body else None),
                  preservation_root=root,
                  auxiliary_root=body.get("auxiliary_root"),
                  index_offset=(_as_index(body["index_offset"], "index_offset")
                                if "index_offset" in body else None),
                  hash_algorithm=algorithm)


def find_latest_footer(data: bytes) -> Footer:
    """Locate the newest complete footer.

    By scanning backwards, never by trusting the header's hint. The hint is
    checked afterwards and a disagreement is ignored, because an interrupted
    append leaves a hint pointing at a footer that was never finished — and a
    reader that believes it reports an older snapshot as current with every hash
    checking out.
    """
    header = parse_header(data)
    at = (len(data) - (len(data) % RECORD_ALIGNMENT)) - RECORD_FRAME_SIZE
    at -= at % RECORD_ALIGNMENT
    while at >= header.first_record_offset:
        if data[at:at + 4] == RECORD_MAGIC and data[at + 4:at + 8] == b"FOOT":
            try:
                footer = parse_footer_record(data, at)
            except AnlaError:
                # Every refusal, not a list of three. This is a *search*: anything
                # that fails to parse at a candidate offset means "not a footer
                # here", and the reason is irrelevant to the search.
                #
                # It used to name three exception types, which was accidentally
                # complete until the 16 MiB header limit was reclassified from
                # `ManifestInvalid` to `ResourceLimitExceeded` — at which point that
                # one refusal started escaping the loop and aborting the scan. The
                # differential fuzzer found it within an hour of the reclassification.
                #
                # The general lesson: catching by exception type couples control flow
                # to classification, so changing what an error *is called* silently
                # changes behaviour somewhere that never mentioned it.
                # A torn or corrupt trailing footer is not the latest footer; it is
                # a failed append. Keep looking backwards for the last good one.
                at -= RECORD_ALIGNMENT
                continue
            if footer.record.end <= len(data):
                return footer
        at -= RECORD_ALIGNMENT
    raise ManifestInvalid("no complete footer found", archive_size=len(data))


def walk_footers(data: bytes) -> list[Footer]:
    """Every snapshot, newest first, following `previous_footer_offset`.

    Refuses a cycle rather than following one, and refuses a chain that does not
    descend — both are the sort of thing a crafted archive does and an honest one
    never needs.
    """
    footers = [find_latest_footer(data)]
    seen = {footers[0].offset}
    while footers[-1].previous_footer_offset is not None:
        previous = footers[-1].previous_footer_offset
        if previous in seen:
            raise ManifestInvalid("footer chain contains a cycle", offset=previous)
        if previous >= footers[-1].offset:
            raise ManifestInvalid("footer chain does not descend",
                                  previous=previous, current=footers[-1].offset)
        footer = parse_footer_record(data, previous)
        if footer.snapshot_sequence >= footers[-1].snapshot_sequence:
            raise ManifestInvalid("snapshot sequence does not decrease along the chain",
                                  previous=footer.snapshot_sequence,
                                  current=footers[-1].snapshot_sequence)
        seen.add(previous)
        footers.append(footer)
    return footers


def _as_index(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestInvalid(f"{field_name} must be a non-negative integer",
                              got=repr(value)[:64])
    return value


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------

@dataclass
class CapabilityReport:
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    ignored_optional: list[str] = field(default_factory=list)


def check_capabilities(manifest: dict, known: frozenset[str] = KNOWN_CAPABILITIES,
                       ) -> CapabilityReport:
    """Refuse unknown required capabilities; ignore unknown optional ones silently.

    "Silently" is doing work in that sentence: an unknown optional capability must
    not produce a warning that a caller might treat as a failure, and must not be
    dropped from the report either. It is recorded as ignored.
    """
    required = manifest.get("required_capabilities", [])
    optional = manifest.get("optional_capabilities", [])
    for name, value in (("required_capabilities", required),
                        ("optional_capabilities", optional)):
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ManifestInvalid(f"{name} must be a list of strings")
    unknown = [name for name in required if name not in known]
    if unknown:
        raise UnsupportedCapability("archive requires capabilities this reader lacks",
                                    missing=sorted(unknown), known=sorted(known))
    return CapabilityReport(required=list(required), optional=list(optional),
                            ignored_optional=[n for n in optional if n not in known])


def bounded(value: int, limit: int, what: str) -> int:
    if value > limit:
        raise ResourceLimitExceeded(f"{what} exceeds its limit", value=value, limit=limit)
    return value
