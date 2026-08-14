# -*- coding: utf-8 -*-
"""Append-only snapshots — SPEC-1.0-DRAFT.md section 6, the layer above the chain.

The container knows how to write a footer that points at the previous one. This
module decides what goes *into* an appended snapshot, which is where all the
questions actually are. `design/milestone-3-plan.md` argues the five decisions; the
two that shape this file:

**A manifest describes its whole snapshot, never a delta.** Snapshot 7's manifest
lists every object and every chunk descriptor it needs, including descriptors
pointing at `CHNK` records written for snapshot 1. So extracting any snapshot reads
exactly one manifest, and `preservation_root` covers a tree the document it sits in
actually contains.

**`CHNK` records are written once per archive.** That is the whole space saving, and
it is why the delta is in the payload records rather than in the manifest — which is
also what the draft's own `S(t+1) = (S(t), ΔO, ΔC, ΔM)` says.

Everything else here is checking. Append-only makes a set of claims into arithmetic
a reader can do from what it is already holding — no chunk record may live at or
past the manifest that references it, sequences never restart, a parent link must
match the chain it claims to follow — and this format has already been bitten once
by an invariant that was written down and checked by nobody.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from anla.errors import IntegrityFailure, InvalidInput, ManifestInvalid

from . import container as C
from .cbor import encode
from .codecs import (
    CODEC_STORE,
    CODEC_ZSTD,
    CODECS,
    DEFAULT_LEVEL,
    compress_chunk,
    decompress_chunk,
    plan_for,
)
from .manifest import (
    ChunkEntry,
    ObjectEntry,
    build_manifest,
    check_fidelity,
    sorted_by_path,
    NATIVE_NAME_CAPABILITY,
    parse_manifest,
    verify_manifest,
)

__all__ = [
    "Snapshot", "Diff", "ArchiveReport", "SourceEntry",
    "single_chunk", "cdc_chunker",
    "create_archive", "append_snapshot",
    "snapshot_id_of", "read_snapshot", "list_snapshots", "latest_snapshot",
    "extract_snapshot", "verify_archive", "diff", "write_snapshot",
    "CODEC_STORE", "CODEC_ZSTD",
]

Chunker = Callable[[bytes], list[bytes]]

#: The capability an archive with more than one snapshot requires. A reader that
#: does not understand the chain must refuse rather than report snapshot 1 as the
#: whole archive.
SNAPSHOT_CAPABILITY = "anla:core:snapshots:1"

STORE_CODEC = CODEC_STORE


@dataclass(frozen=True)
class SourceEntry:
    """One file offered to the writer, read on demand.

    The writer takes these rather than a path-to-bytes mapping so that a tree does
    not have to fit in memory before packing can start: `read()` is called once, at
    the moment that file is chunked, and the bytes are dropped before the next.

    The bound is therefore the largest single file, not the tree. It is not zero —
    the archive itself is still assembled in memory, which `SPEC-1.0-DRAFT.md`'s
    table records as not yet done — and a mapping is still accepted for the cases
    where holding everything is obviously fine, such as the tests.
    """

    path: str
    read: Callable[[], bytes]
    mtime_ns: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, path: str, data: bytes, metadata: Mapping[str, Any] | None = None,
           ) -> "SourceEntry":
        return cls(path=path, read=lambda: data, metadata=dict(metadata or {}))


def single_chunk(data: bytes) -> list[bytes]:
    """One chunk per file. The default, so this module can be read without also
    reading the chunker."""
    return [data] if data else []


def cdc_chunker(profile: Any = None) -> Chunker:
    """Content-defined chunking with `anla-cdc-1`, the profile MVP pinned.

    Reused unchanged rather than re-derived: cross-snapshot deduplication is exactly
    the workload content-defined chunking exists for, and a second boundary rule
    would mean the same bytes cutting differently depending on which profile packed
    them.
    """
    from anla.fastcdc import DEFAULT_PROFILE, cut_points

    chosen = profile or DEFAULT_PROFILE

    def chunk(data: bytes) -> list[bytes]:
        return [data[start:end] for start, end in cut_points(data, chosen)]

    # Carried on the function so the writer can record it without being told twice.
    # An archive whose snapshots were cut by different rules deduplicates against
    # nothing, and that is invisible in every check except the size.
    chunk.plan = chosen.as_manifest_member()
    return chunk


# ---------------------------------------------------------------------------
# where the bytes go
# ---------------------------------------------------------------------------

class _Sink:
    """Somewhere to put a snapshot's bytes, that also knows the current offset.

    The writer needs `tell()` as much as `write()`: every chunk descriptor records
    where its record landed, so the position *is* part of the output. Behind this
    interface that is either a growing buffer or a real file, and the two produce
    identical bytes because they are the same code — which the byte comparison
    between the Python and Rust writers then proves rather than assumes.
    """

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def tell(self) -> int:
        raise NotImplementedError


class _MemorySink(_Sink):
    def __init__(self, prefix: bytes) -> None:
        self._buffer = bytearray(prefix)

    def write(self, data: bytes) -> None:
        self._buffer += data

    def tell(self) -> int:
        return len(self._buffer)

    def finish(self, archive_id: bytes, footer_offset: int) -> bytes:
        return C.with_footer_hint(bytes(self._buffer), footer_offset)


class _FileSink(_Sink):
    """Writes in place, and *does not rewrite what is already there*.

    An append seeks to the end of the newest complete snapshot, truncates whatever
    a torn write left after it, and writes only the new records — then patches the
    64-byte header. The in-memory path rebuilds the whole file to do the same thing,
    which for a hundred-gigabyte archive is a hundred gigabytes of pointless
    copying to add one manifest.
    """

    def __init__(self, handle, resume_at: int) -> None:
        self._handle = handle
        self._handle.seek(resume_at)
        self._handle.truncate(resume_at)
        self._position = resume_at

    def write(self, data: bytes) -> None:
        self._handle.write(data)
        self._position += len(data)

    def tell(self) -> int:
        return self._position

    def finish(self, archive_id: bytes, footer_offset: int) -> bytes:
        # The hint is a property of the header, and the header is 64 bytes at offset
        # zero. Nothing else in the file moves, which is the whole point.
        self._handle.seek(0)
        self._handle.write(C.build_header(archive_id, latest_footer_hint=footer_offset))
        self._handle.flush()
        return b""


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    sequence: int
    snapshot_id: bytes
    manifest: dict
    footer: C.Footer
    hash_algorithm: str

    @property
    def parent_snapshot(self) -> bytes | None:
        return self.manifest.get("parent_snapshot")

    @property
    def paths(self) -> list[str]:
        return sorted(entry["path"] for entry in self.manifest["objects"])


def snapshot_id_of(manifest: dict) -> bytes:
    """`snapshot_id` — the hash of the canonical manifest encoding.

    It cannot live inside the manifest, since it is a hash of the whole thing, which
    is why the parent link is what carries lineage.
    """
    algorithms = manifest.get("hash_algorithms")
    if (not isinstance(algorithms, list) or len(algorithms) != 1
            or not isinstance(algorithms[0], str)):
        raise ManifestInvalid("hash_algorithms must be a list of exactly one name",
                              got=repr(algorithms)[:64])
    return C.hash_bytes(encode(manifest), algorithms[0])


def read_snapshot(data: bytes, footer: C.Footer) -> Snapshot:
    """The manifest a footer points at, fully verified against that footer."""
    record = C.parse_record(data, footer.manifest_offset)
    if record.type != "MANF":
        raise ManifestInvalid("footer does not point at a MANF record",
                              offset=footer.manifest_offset, found=record.type)
    if record.total_length != footer.manifest_length:
        raise ManifestInvalid("footer disagrees with the manifest record's length",
                              footer=footer.manifest_length,
                              record=record.total_length)

    algorithm = record.header.get("hash_algorithm")
    if not isinstance(algorithm, str):
        raise ManifestInvalid("manifest record does not name its hash algorithm",
                              offset=footer.manifest_offset)
    payload = data[record.payload_offset:record.payload_offset + record.payload_length]
    expected = record.header.get("payload_hash")
    if not isinstance(expected, bytes):
        raise ManifestInvalid("manifest record header has no payload hash")
    if C.hash_bytes(payload, algorithm) != expected:
        raise IntegrityFailure("manifest payload hash mismatch",
                               offset=footer.manifest_offset)

    manifest = parse_manifest(payload)
    # Named in two places, so the two must agree. Otherwise a reader could verify
    # with one algorithm and interpret with the other, and both would look fine.
    if manifest["hash_algorithms"] != [algorithm]:
        raise IntegrityFailure("the manifest and its record disagree about the hash",
                               manifest=manifest["hash_algorithms"], record=algorithm)

    def hasher(payload_bytes: bytes) -> bytes:
        return C.hash_bytes(payload_bytes, algorithm)

    verify_manifest(manifest, hasher)
    C.check_capabilities(manifest)

    if footer.preservation_root != manifest["preservation_root"]:
        raise IntegrityFailure("footer and manifest disagree about preservation_root",
                               offset=footer.offset)
    if (footer.auxiliary_root is not None
            and footer.auxiliary_root != manifest["auxiliary_root"]):
        raise IntegrityFailure("footer and manifest disagree about auxiliary_root",
                               offset=footer.offset)
    # Named in two places — the bootstrap header and the manifest — so the two must
    # agree. Nothing checked this until a writer got it wrong: an append wrote a
    # manifest claiming a different `archive_id` than the header, and both readers
    # verified it happily. Same shape as the hash algorithm being named twice.
    header = C.parse_header(data)
    if manifest["archive_id"] != header.archive_uuid:
        raise IntegrityFailure("the manifest and the header disagree about archive_id",
                               header=header.archive_uuid.hex(),
                               manifest=manifest["archive_id"].hex())
    if footer.snapshot_sequence != manifest["snapshot_sequence"]:
        raise IntegrityFailure("footer and manifest disagree about the sequence",
                               footer=footer.snapshot_sequence,
                               manifest=manifest["snapshot_sequence"])
    # `snapshot_id` is the hash of the *stored* bytes, so re-encoding must reproduce
    # them. The strict decoder already refuses non-canonical input, which makes this
    # a consequence rather than an extra rule — and a consequence worth asserting,
    # because if it ever stops holding, every lineage link silently stops matching.
    if encode(manifest) != payload:
        raise ManifestInvalid("manifest bytes are not the canonical encoding",
                              offset=footer.manifest_offset)

    return Snapshot(sequence=footer.snapshot_sequence,
                    snapshot_id=C.hash_bytes(payload, algorithm),
                    manifest=manifest, footer=footer, hash_algorithm=algorithm)


def list_snapshots(data: bytes) -> list[Snapshot]:
    """Every snapshot, **oldest first**, with the lineage rules enforced."""
    footers = C.walk_footers(data)              # newest first
    snapshots = [read_snapshot(data, footer) for footer in reversed(footers)]
    _check_lineage(snapshots)
    _check_chunk_placement(snapshots)
    return snapshots


def latest_snapshot(data: bytes) -> Snapshot:
    return read_snapshot(data, C.find_latest_footer(data))


def _check_lineage(snapshots: list[Snapshot]) -> None:
    """Parent links must match the chain they claim to follow.

    Without this `parent_snapshot` is decoration: an archive could name any ancestor,
    or none, and every hash would still check out. It is the same defect the
    differential fuzzer found in record `sequence` — specified, and checked by
    nobody — caught this time before a writer existed to produce it.
    """
    first = snapshots[0]
    # Single-volume only. Whitepaper question 9 (multi-volume atomicity) is open, and
    # a volume that begins part-way through a chain is exactly what would relax this.
    if first.sequence != 1:
        raise ManifestInvalid("the oldest snapshot in the chain is not sequence 1",
                              found=first.sequence)
    if "parent_snapshot" in first.manifest:
        raise ManifestInvalid("the first snapshot declares a parent")

    for previous, current in zip(snapshots, snapshots[1:]):
        if current.sequence != previous.sequence + 1:
            raise ManifestInvalid("snapshot sequence is not contiguous",
                                  previous=previous.sequence, current=current.sequence)
        parent = current.manifest.get("parent_snapshot")
        if parent is None:
            raise ManifestInvalid("a snapshot after the first declares no parent",
                                  sequence=current.sequence)
        if parent != previous.snapshot_id:
            raise IntegrityFailure("parent_snapshot does not match the chain",
                                   sequence=current.sequence,
                                   declared=parent.hex()[:16],
                                   chain=previous.snapshot_id.hex()[:16])
        if current.hash_algorithm != previous.hash_algorithm:
            # Chunk ids *are* hashes. Two algorithms in one archive means two
            # namespaces of chunk id sharing a lookup, so identical bytes get
            # stored twice and deduplication quietly stops working. Hash agility is
            # per archive, not per snapshot.
            raise ManifestInvalid("snapshots use different hash algorithms",
                                  previous=previous.hash_algorithm,
                                  current=current.hash_algorithm)


def _check_chunk_placement(snapshots: list[Snapshot]) -> None:
    """No forward references, and one descriptor per chunk id.

    In an append-only file every byte a snapshot depends on was written before it, so
    a chunk record at or past its own manifest is impossible rather than merely
    unusual — which makes it arithmetic a reader can check while holding one manifest
    and one footer.
    """
    descriptors: dict[bytes, tuple[int, dict]] = {}
    for snapshot in snapshots:
        limit = snapshot.footer.manifest_offset
        for chunk_id, descriptor in snapshot.manifest["chunks"].items():
            end = descriptor["record_offset"] + descriptor["record_length"]
            if descriptor["record_offset"] >= limit or end > limit:
                raise ManifestInvalid(
                    "chunk record is not before the manifest that references it",
                    sequence=snapshot.sequence, chunk_id=chunk_id.hex()[:16],
                    record_offset=descriptor["record_offset"], manifest_offset=limit)
            known = descriptors.get(chunk_id)
            if known is None:
                descriptors[chunk_id] = (snapshot.sequence, descriptor)
            elif known[1] != descriptor:
                # Same content id, different stored bytes or a different place to
                # find them: one of the two snapshots is lying about what it stored,
                # and a content-addressed format cannot shrug at that.
                raise IntegrityFailure("one chunk id with two different descriptors",
                                       chunk_id=chunk_id.hex()[:16],
                                       first_seen=known[0], again=snapshot.sequence)


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def create_archive(archive_id: bytes) -> bytes:
    """A header and nothing else. Valid, and not yet readable as a snapshot."""
    return C.build_header(archive_id)


def _as_entries(files: Mapping[str, bytes] | Iterable[SourceEntry],
                metadata: Mapping[str, dict] | None,
                ) -> list[SourceEntry]:
    """Accept either input form and produce one, sorted by UTF-8 path bytes.

    Ordering is fixed here rather than left to the caller: it decides the offsets
    every chunk record lands at, so two writers that disagree about it produce
    different archives from the same tree.
    """
    if isinstance(files, Mapping):
        entries = [SourceEntry.of(path, files[path], (metadata or {}).get(path))
                   for path in files]
    else:
        entries = list(files)
        if metadata:
            raise InvalidInput("metadata belongs on the entries when entries are given")
    return sorted_by_path(entries)


def append_snapshot(data: bytes, *,
                    files: Mapping[str, bytes] | Iterable[SourceEntry],
                    directories: Iterable[str] = (),
                    created_unix_ns: int,
                    metadata: Mapping[str, dict] | None = None,
                    prior: "list[Snapshot] | None" = None,
                    objects: Iterable[ObjectEntry] = (),
                    native_names: Mapping[str, bytes] | None = None,
                    fidelity: Iterable[dict] = (),
                    auxiliary: Iterable[dict] = (),
                    sink: "_Sink | None" = None,
                    chunker: Chunker = single_chunk,
                    codec: int = CODEC_STORE,
                    level: int = DEFAULT_LEVEL,
                    hash_algorithm: str | None = None,
                    archive_id: bytes | None = None) -> bytes:
    """Append one snapshot, reusing every chunk the archive already contains.

    Old bytes are never rewritten — not the records, not the footers, not even the
    header, except for its hint, which is advisory by specification and which no
    reader is permitted to trust for deciding what is latest.
    """
    if prior is not None:
        # The caller already read the chain and has since let go of the archive —
        # `write_snapshot` must, because Windows refuses to truncate a file while it
        # is memory-mapped. So the identity comes from what it read, not from bytes
        # nobody is holding any more.
        archive_id = prior[-1].manifest["archive_id"]
        started = True
    elif data:
        header = C.parse_header(data)
        if archive_id is not None and archive_id != header.archive_uuid:
            raise InvalidInput("archive_id does not match the archive",
                               given=archive_id.hex(), found=header.archive_uuid.hex())
        archive_id = header.archive_uuid
        started = len(data) > header.header_size
    else:
        if archive_id is None:
            raise InvalidInput("a new archive needs an archive_id")
        data = create_archive(archive_id)
        started = False

    if prior is not None:
        started = True
    if started:
        previous = prior if prior is not None else list_snapshots(data)
        parent = previous[-1]
        # An archive that already chose an algorithm has chosen it for its chunk ids.
        if hash_algorithm is None:
            hash_algorithm = parent.hash_algorithm
        elif hash_algorithm != parent.hash_algorithm:
            raise InvalidInput("an archive uses one hash algorithm for its chunk ids",
                               archive=parent.hash_algorithm, given=hash_algorithm)
        known = {chunk_id: descriptor
                 for snapshot in previous
                 for chunk_id, descriptor in snapshot.manifest["chunks"].items()}
        sequence = parent.footer.record.sequence + 1
        snapshot_sequence = parent.sequence + 1
        parent_id: bytes | None = parent.snapshot_id
        previous_footer: int | None = parent.footer.offset
        resume_at = parent.footer.record.end
        if resume_at % C.RECORD_ALIGNMENT:
            raise ManifestInvalid("the newest snapshot does not end on an alignment "
                                  "boundary, so nothing can be appended after it",
                                  offset=resume_at)
    else:
        hash_algorithm = hash_algorithm or C.CORE_HASH
        known = {}
        sequence, snapshot_sequence, parent_id = 1, 1, None
        previous_footer = None

    def hasher(payload: bytes) -> bytes:
        return C.hash_bytes(payload, hash_algorithm)

    # An append begins at the end of the newest complete snapshot, **not** at the end
    # of the file. Everything past that footer belongs to no snapshot — it is a
    # previous append that did not finish — so dropping it discards nothing anyone
    # can reference, and keeping it would be worse than untidy in two ways:
    #
    # a torn write leaves the file at an arbitrary length, so appending onto the end
    # of it puts every subsequent record at an offset that is not a multiple of
    # eight. `find_latest_footer` scans backwards in alignment-sized steps, so a
    # misaligned footer is not merely inelegant, it is *invisible*: the archive
    # silently reads as the older snapshot with every hash checking out. Found by
    # appending to a deliberately torn archive; nothing in the container's own tests
    # could have shown it, because they never write at a bad offset.
    #
    # And failed appends would otherwise accumulate forever, since no later snapshot
    # ever has a reason to reclaim them.
    # A sink rather than a buffer. `None` means the caller wants bytes back, which
    # is every test and the in-memory API; a `_FileSink` means the archive is being
    # written where it will live and never exists in memory at all.
    if sink is None:
        sink = _MemorySink(data[:resume_at] if started else data)
    out = sink
    chunk_entries: dict[bytes, ChunkEntry] = {}
    # One mapping for every kind, applied where the entries are built. A directory
    # is a bare string with no entry to hang a field on, so plumbing the native name
    # through three separate paths would have meant three chances to forget one —
    # and an object that lost its native name would restore under the escaped label
    # with nothing saying it had been possible to do better. An explicit `name` on a
    # caller-supplied `ObjectEntry` wins over the mapping.
    natives = dict(native_names or {})
    tree_objects = [ObjectEntry(kind="directory", path=path, name=natives.get(path))
                    for path in sorted_by_path(directories, lambda p: p)]
    tree_objects += [entry if entry.name is not None or entry.path not in natives
                     else replace(entry, name=natives[entry.path])
                     for entry in objects]
    # A complete manifest: descriptors for chunks written now *and* for chunks
    # written by an earlier snapshot, so that reading this snapshot needs no other.
    referenced: list[ChunkEntry] = []
    listed: set[bytes] = set()

    for source in _as_entries(files, metadata):
        payload = source.read()        # read once — see SourceEntry on the bound
        ids: list[bytes] = []
        for piece in chunker(payload):
            # The chunk id is the hash of the *raw* chunk, before any codec touches
            # it. That is what makes compression unable to change a chunk id, an
            # objects_root, or a preservation_root — see codecs.py.
            chunk_id = hasher(piece)
            ids.append(chunk_id)
            if chunk_id in known or chunk_id in chunk_entries:
                continue                       # already in the archive: never twice
            used, stored = compress_chunk(piece, codec, level)
            payload_hash = hasher(stored)
            offset = out.tell()
            record = C.build_record(
                "CHNK",
                {"chunk_id": chunk_id, "codec_id": used,
                 "raw_size": len(piece), "payload_hash": payload_hash},
                stored, sequence)
            out.write(record)
            parsed = C.parse_record(record, 0)
            chunk_entries[chunk_id] = ChunkEntry(
                chunk_id=chunk_id, record_offset=offset, record_length=len(record),
                payload_offset=offset + parsed.payload_offset,
                payload_length=len(stored), raw_size=len(piece),
                codec_id=used, payload_hash=payload_hash)
            sequence += 1
        tree_objects.append(ObjectEntry(
            kind="regular-file", path=source.path, size=len(payload),
            content_hash=hasher(payload), chunks=tuple(ids),
            name=natives.get(source.path),
            metadata=dict(source.metadata)))
        for chunk_id in ids:
            if chunk_id in listed:
                continue
            listed.add(chunk_id)
            entry = chunk_entries.get(chunk_id)
            referenced.append(entry if entry is not None
                              else _entry_from_descriptor(chunk_id, known[chunk_id]))
        del payload

    capabilities = ["anla:core:objects:1", "anla:core:chunks:1", SNAPSHOT_CAPABILITY,
                    f"anla:hash:{hash_algorithm}:1", "anla:codec:store:1"]
    # Declared from what was *used*, not from what was asked for: a pack where every
    # chunk turned out incompressible stores nothing with zstd and must not require
    # a reader to have it.
    for entry in referenced:
        capability = CODECS[entry.codec_id].capability
        if capability and capability not in capabilities:
            capabilities.append(capability)
    if any(entry.kind == "symbolic-link" for entry in tree_objects):
        # Required, because a reader that does not know the kind refuses the whole
        # manifest anyway. Saying so is the difference between a clear refusal and
        # an obscure one.
        capabilities.append("anla:object:symlink:1")

    # Metadata namespaces are *optional* capabilities. An object's metadata is
    # inside its `object_id`, so a reader that has never heard of `posix` computes
    # the same id over the same bytes, verifies, and extracts every byte — it just
    # cannot apply what it verified. Requiring them would refuse an archive that
    # reader could restore perfectly. See design/milestone-2-plan.md decision 3.
    # The chunking rule is recorded for the same reason the hash algorithm is: two
    # snapshots cut by different boundaries produce different chunk ids for
    # identical bytes, so deduplication silently does nothing while every check
    # still passes. Found by running the corpus in test_demo/ and noticing that a
    # one-paragraph edit cost a whole paper.
    plan = getattr(chunker, "plan", None)
    if plan is not None or codec != CODEC_STORE:
        plan = dict(plan or {})
        plan["codec"] = plan_for(codec, level)
    if started and previous:
        earlier = parent.manifest.get("packing_plan")
        if earlier is not None and plan is not None and earlier != plan:
            raise InvalidInput(
                "an archive uses one chunking rule for its chunk boundaries",
                archive=earlier, given=plan,
                hint="appending with different boundaries stores every file again")
        if plan is None:
            plan = earlier

    namespaces = {ns for entry in tree_objects for ns in entry.metadata}
    optional = [f"anla:metadata:{ns}:1" for ns in sorted(namespaces)]
    if any(entry.name is not None for entry in tree_objects):
        optional.append(NATIVE_NAME_CAPABILITY)

    metadata_blocks: list[dict] = []
    report = list(fidelity)
    if report:
        # In the preservation plane, never in `auxiliary`: `auxiliary` is defined as
        # disposable and `strip` empties it, so a record of what the archive does
        # *not* hold would be droppable — turning a declared-incomplete archive into
        # an apparently complete one, which is worse than either.
        # Checked before it is sorted, or a malformed entry raises a KeyError from
        # the sort key instead of the refusal the caller is owed.
        check_fidelity(report)
        metadata_blocks.append({"namespace": "fidelity",
                                "entries": sorted(report, key=lambda e: e["path"])})

    manifest = build_manifest(
        archive_id=archive_id, snapshot_sequence=snapshot_sequence,
        created_unix_ns=created_unix_ns, objects=tree_objects, chunks=referenced,
        hasher=hasher, hash_algorithm=hash_algorithm,
        required_capabilities=capabilities, optional_capabilities=optional,
        metadata=metadata_blocks, auxiliary=auxiliary,
        parent_snapshot=parent_id, packing_plan=plan)

    payload = encode(manifest)
    manifest_offset = out.tell()
    manifest_record = C.build_record(
        "MANF", {"hash_algorithm": hash_algorithm, "payload_hash": hasher(payload)},
        payload, sequence)
    out.write(manifest_record)
    sequence += 1

    footer_offset = out.tell()
    out.write(C.build_footer_record(
        sequence=sequence, snapshot_sequence=snapshot_sequence,
        manifest_offset=manifest_offset, manifest_length=len(manifest_record),
        preservation_root=manifest["preservation_root"],
        auxiliary_root=manifest["auxiliary_root"],
        previous_footer_offset=previous_footer, hash_algorithm=hash_algorithm))
    return out.finish(archive_id, footer_offset)


DESCRIPTOR_FIELDS = ("record_offset", "record_length", "payload_offset",
                     "payload_length", "raw_size", "codec_id", "payload_hash")




def write_snapshot(archive: "os.PathLike[str] | str", **kwargs) -> int:
    """Write or append a snapshot straight to a file, never holding it in memory.

    Returns the archive's size in bytes.

    The in-memory `append_snapshot` needs *archive + largest file* live at once,
    which means a tree larger than RAM cannot be packed at all. This needs the
    largest single file and a page or two, because the records go to disk as they
    are produced and the existing archive is memory-mapped rather than read.

    It must produce byte-identical output to the in-memory path — it is the same
    code behind a different sink — and `tools/compare_writers.py` is what says so,
    since a streaming refactor that changed one byte would be a broken one.
    """
    import mmap
    import os as _os

    path = Path(archive)
    exists = path.exists() and path.stat().st_size > 0
    if not exists:
        # `x+b` would refuse an existing empty file; the truncating open is correct
        # here because there is nothing in it to lose.
        with open(path, "wb") as handle:
            handle.write(C.build_header(kwargs["archive_id"]))
    # Two phases, and the split is not stylistic. **Windows refuses to truncate a
    # file that is memory-mapped**, so the mapping has to be gone before the writer
    # can reclaim a torn append. Read what an append needs, let go, then write.
    #
    # The clean-append case hid this: truncating to the file's existing length is a
    # no-op and succeeds. Only a *torn* archive — where there is something after the
    # last footer to reclaim — actually shrinks the file, and that is the test that
    # found it.
    prior = None
    with open(path, "rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            # The reader is slice-based, so a memory map is a drop-in for `bytes`
            # and the operating system decides what is resident.
            resume_at = _resume_offset(mapped)
            if resume_at > C.HEADER_SIZE:
                prior = list_snapshots(mapped)

    with open(path, "r+b") as handle:
        append_snapshot(b"", prior=prior, sink=_FileSink(handle, resume_at),
                        **({**kwargs, "archive_id": None} if prior else kwargs))
    return _os.path.getsize(path)


def _resume_offset(data) -> int:
    """Where a new snapshot starts: the end of the newest complete footer.

    Not the end of the file. Everything past that footer belongs to no snapshot —
    it can only be an append that did not finish — so it is reclaimed, and that is
    also what keeps the next record eight-byte aligned (SPEC §4.4).
    """
    header = C.parse_header(data)
    if len(data) <= header.header_size:
        return header.first_record_offset
    return C.find_latest_footer(data).record.end


def _entry_from_descriptor(chunk_id: bytes, descriptor: Mapping[str, Any]) -> ChunkEntry:
    """A descriptor decoded from an earlier snapshot's manifest, back as an entry.

    Named field by field rather than splatted into the constructor: a manifest is
    input, and input that decides which keyword arguments a constructor receives has
    stopped being input.
    """
    try:
        values = {name: descriptor[name] for name in DESCRIPTOR_FIELDS}
    except KeyError as exc:
        raise ManifestInvalid("chunk descriptor is missing a field",
                              chunk_id=chunk_id.hex()[:16], field=str(exc)) from exc
    return ChunkEntry(chunk_id=chunk_id, **values)


# ---------------------------------------------------------------------------
# extraction, verification, comparison
# ---------------------------------------------------------------------------

def extract_snapshot(data: bytes, snapshot: Snapshot) -> dict[str, bytes]:
    """Every regular file in one snapshot, each verified against its own hashes."""
    def hasher(payload: bytes) -> bytes:
        return C.hash_bytes(payload, snapshot.hash_algorithm)

    restored: dict[str, bytes] = {}
    for entry in snapshot.manifest["objects"]:
        if entry["kind"] != "regular-file":
            continue
        parts = []
        for chunk_id in entry["chunks"]:
            descriptor = snapshot.manifest["chunks"][chunk_id]
            record = C.parse_record(data, descriptor["record_offset"])
            if record.type != "CHNK":
                raise ManifestInvalid("chunk descriptor points at a non-CHNK record",
                                      found=record.type)
            stored = data[descriptor["payload_offset"]:
                          descriptor["payload_offset"] + descriptor["payload_length"]]
            # The stored bytes and the raw bytes are hashed separately, and both are
            # checked: `payload_hash` catches damage to what is on disk, `chunk_id`
            # catches a codec that decoded to something else entirely.
            if hasher(stored) != descriptor["payload_hash"]:
                raise IntegrityFailure("stored chunk does not match its payload hash",
                                       chunk_id=chunk_id.hex()[:16])
            raw = decompress_chunk(stored, descriptor["codec_id"],
                                   descriptor["raw_size"])
            if hasher(raw) != chunk_id:
                raise IntegrityFailure("chunk content does not match its id",
                                       chunk_id=chunk_id.hex()[:16])
            parts.append(raw)
        content = b"".join(parts)
        if hasher(content) != entry["content_hash"]:
            raise IntegrityFailure("file content hash mismatch", path=entry["path"])
        restored[entry["path"]] = content
    return restored


@dataclass
class ArchiveReport:
    snapshots: list[Snapshot] = field(default_factory=list)
    unique_chunks: int = 0
    chunk_bytes: int = 0
    archive_bytes: int = 0

    @property
    def logical_bytes(self) -> int:
        """What the snapshots would occupy if none of them shared anything."""
        return sum(entry.get("size", 0)
                   for snapshot in self.snapshots
                   for entry in snapshot.manifest["objects"]
                   if entry["kind"] == "regular-file")


def verify_archive(data: bytes) -> ArchiveReport:
    """Every snapshot, every lineage rule, every chunk's bytes.

    Also the record-sequence rules from section 4.3, which are checkable only by a
    pass like this one and were, in MVP, checkable by nothing at all.
    """
    snapshots = list_snapshots(data)
    # Structure before content, and the order is load-bearing rather than tidy.
    # An archive damaged in two places at once gets whichever verdict its reader
    # happens to reach first, and "the bytes of this chunk are wrong" is not a
    # statement anyone can act on about a file whose record framing has not been
    # validated. The differential fuzzer found the two implementations reporting
    # different codes for the same mutant six times out of two thousand, purely
    # because they checked in different orders.
    _check_record_sequences(data, snapshots)
    seen: dict[bytes, dict] = {}
    chunk_bytes = 0
    for snapshot in snapshots:
        for chunk_id, descriptor in snapshot.manifest["chunks"].items():
            if chunk_id in seen:
                continue
            record = C.parse_record(data, descriptor["record_offset"])
            if record.type != "CHNK":
                raise ManifestInvalid("chunk descriptor points at a non-CHNK record",
                                      offset=descriptor["record_offset"],
                                      found=record.type)
            if record.header.get("chunk_id") != chunk_id:
                raise IntegrityFailure("chunk record disagrees with its descriptor",
                                       chunk_id=chunk_id.hex()[:16])
            stored = data[descriptor["payload_offset"]:
                          descriptor["payload_offset"] + descriptor["payload_length"]]
            if C.hash_bytes(stored, snapshot.hash_algorithm) != descriptor["payload_hash"]:
                raise IntegrityFailure("stored chunk does not match its payload hash",
                                       chunk_id=chunk_id.hex()[:16])
            raw = decompress_chunk(stored, descriptor["codec_id"],
                                   descriptor["raw_size"])
            if C.hash_bytes(raw, snapshot.hash_algorithm) != chunk_id:
                raise IntegrityFailure("chunk content does not match its id",
                                       chunk_id=chunk_id.hex()[:16])
            seen[chunk_id] = descriptor
            chunk_bytes += descriptor["payload_length"]
    return ArchiveReport(snapshots=snapshots, unique_chunks=len(seen),
                         chunk_bytes=chunk_bytes, archive_bytes=len(data))


def _check_record_sequences(data: bytes, snapshots: list[Snapshot]) -> None:
    """Section 4.3: contiguous and unique within a snapshot, never restarting.

    Stated as arithmetic over a walk, because "strictly increasing" is unenforceable
    by a reader that seeks to offsets — which is exactly what the fuzzer found in
    MVP, where both implementations shared the omission with the tests.
    """
    header = C.parse_header(data)
    start = header.first_record_offset
    highest = 0
    for snapshot in snapshots:
        end = snapshot.footer.record.end
        sequences = [record.sequence for record in C.walk_records(data[:end], header)
                     if record.offset >= start]
        if not sequences:
            raise ManifestInvalid("a snapshot contains no records",
                                  snapshot=snapshot.sequence)
        if sorted(sequences) != list(range(min(sequences), min(sequences) + len(sequences))):
            raise ManifestInvalid("record sequences are not contiguous and unique",
                                  snapshot=snapshot.sequence)
        if min(sequences) <= highest:
            raise ManifestInvalid("record sequences restart across snapshots",
                                  snapshot=snapshot.sequence)
        footer_record = C.parse_record(data, snapshot.footer.offset)
        if footer_record.sequence != max(sequences):
            raise ManifestInvalid("the footer is not the highest sequence in its snapshot",
                                  snapshot=snapshot.sequence)
        highest, start = max(sequences), end


@dataclass(frozen=True)
class Diff:
    added: list[str]
    removed: list[str]
    modified: list[str]
    unchanged: list[str]
    new_chunks: list[bytes]
    shared_chunks: list[bytes]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified)


def diff(older: Snapshot, newer: Snapshot) -> Diff:
    """What changed between two snapshots — derived, not stored.

    Two complete manifests are enough, which is the payoff of decision 1: no walk,
    no index, and no way for a stored summary to disagree with the archive.
    """
    def by_path(snapshot: Snapshot) -> dict[str, dict]:
        return {entry["path"]: entry for entry in snapshot.manifest["objects"]}

    before, after = by_path(older), by_path(newer)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    common = sorted(set(before) & set(after))
    modified = [path for path in common
                if before[path]["object_id"] != after[path]["object_id"]]
    unchanged = [path for path in common if path not in set(modified)]

    old_chunks = set(older.manifest["chunks"])
    new_chunks = sorted(set(newer.manifest["chunks"]) - old_chunks)
    shared = sorted(set(newer.manifest["chunks"]) & old_chunks)
    return Diff(added=added, removed=removed, modified=modified, unchanged=unchanged,
                new_chunks=new_chunks, shared_chunks=shared)
