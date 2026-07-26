# -*- coding: utf-8 -*-
"""The ANLA 1.0 snapshot manifest — SPEC-1.0-DRAFT.md §5.

The manifest is where the format's two planes meet, and the shape of this module is
that meeting made structural:

    objects_root ┐
    chunks_root  ├─► preservation_root       ← what a decoder must reproduce
    metadata_root┘
    auxiliary_root                            ← outside it, on purpose

`D(P, I) = D(P, ∅)` — dropping the intelligence plane changes nothing a decoder
extracts — is the whitepaper's central claim. With the roots arranged this way it
becomes a *comparison* rather than an argument: rewrite a manifest with `auxiliary`
emptied and `preservation_root` is unchanged, byte for byte, and one equality check
says so. MVP could only demonstrate the same property by re-deriving the entire
manifest and diffing what came out.

What is deliberately still a sketch: the name model. Whitepaper open question 4 asks
how Windows NT names and POSIX byte names share a minimal representation, and it is
not settled, so an object here carries one `path` and this module says plainly that
`object_id` will change when that question is answered. Freezing an identity
computation over a representation still under discussion is how a format acquires a
mistake it cannot remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from anla.errors import IntegrityFailure, InvalidInput, ManifestInvalid

from .cbor import decode, encode
from .merkle import merkle_root

__all__ = [
    "OBJECT_ID_PREFIX", "PRESERVATION_PREFIX",
    "ObjectEntry", "ChunkEntry", "Roots",
    "object_id_for", "object_leaf", "chunk_leaf",
    "compute_roots", "build_manifest", "verify_manifest", "without_auxiliary",
]

#: Domain separation again, for the same reason as in the Merkle tree: an object id
#: and a Merkle leaf must not be computable from one another.
OBJECT_ID_PREFIX = b"\x10"
PRESERVATION_PREFIX = b"\x03"

Hasher = Callable[[bytes], bytes]

MANIFEST_VERSION = [1, 0]


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObjectEntry:
    """One filesystem object.

    `path` is the portable UTF-8 name and is the only name form this draft carries.
    Open question 4 will add the native and legacy forms, and doing so *will* change
    `object_id` — which is why nothing in the container depends on an object id
    being stable across draft revisions.
    """

    kind: str
    path: str
    size: int = 0
    content_hash: bytes = b""
    chunks: tuple[bytes, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def identity(self) -> dict:
        """The fields an object id is computed over — everything but the id."""
        body: dict[str, Any] = {"kind": self.kind, "path": self.path}
        if self.kind == "regular-file":
            body["size"] = self.size
            body["content_hash"] = self.content_hash
            body["chunks"] = list(self.chunks)
        if self.metadata:
            body["metadata"] = dict(self.metadata)
        return body

    def as_manifest_entry(self, hasher: Hasher) -> dict:
        return {"object_id": object_id_for(self, hasher), **self.identity()}


@dataclass(frozen=True)
class ChunkEntry:
    chunk_id: bytes
    record_offset: int
    record_length: int
    payload_offset: int
    payload_length: int
    raw_size: int
    codec_id: int
    payload_hash: bytes

    def as_manifest_entry(self) -> dict:
        return {
            "record_offset": self.record_offset,
            "record_length": self.record_length,
            "payload_offset": self.payload_offset,
            "payload_length": self.payload_length,
            "raw_size": self.raw_size,
            "codec_id": self.codec_id,
            "payload_hash": self.payload_hash,
        }


def object_id_for(entry: ObjectEntry, hasher: Hasher) -> bytes:
    return hasher(OBJECT_ID_PREFIX + encode(entry.identity()))


def object_leaf(manifest_entry: dict) -> bytes:
    """The bytes an object contributes to `objects_root`.

    The whole entry, including its id — so a manifest that lists an object with a
    correct id but altered contents produces a different root, rather than an id
    that silently disagrees with what it identifies.
    """
    return encode(manifest_entry)


def chunk_leaf(chunk_id: bytes, descriptor: dict) -> bytes:
    return encode([chunk_id, descriptor])


# ---------------------------------------------------------------------------
# roots
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Roots:
    objects_root: bytes
    chunks_root: bytes
    metadata_root: bytes
    preservation_root: bytes
    auxiliary_root: bytes


def compute_roots(objects: list[dict], chunks: dict[bytes, dict],
                  metadata: list[dict], auxiliary: list[dict],
                  hasher: Hasher) -> Roots:
    """The five roots, from the manifest's own contents.

    Leaf order is part of the definition and is not the caller's choice here:
    objects sort by `object_id`, chunks by `chunk_id`, metadata by its namespace
    key. Sorting by encoded bytes, as everywhere else in this format, because that
    is the order two implementations can agree on without agreeing on a collation.
    """
    object_leaves = [object_leaf(entry) for entry in
                     sorted(objects, key=lambda e: e["object_id"])]
    chunk_leaves = [chunk_leaf(chunk_id, chunks[chunk_id])
                    for chunk_id in sorted(chunks)]
    metadata_leaves = [encode(entry) for entry in
                       sorted(metadata, key=lambda e: encode(e))]
    auxiliary_leaves = [encode(entry) for entry in auxiliary]

    objects_root = merkle_root(object_leaves, hasher)
    chunks_root = merkle_root(chunk_leaves, hasher)
    metadata_root = merkle_root(metadata_leaves, hasher)
    preservation_root = hasher(
        PRESERVATION_PREFIX + objects_root + chunks_root + metadata_root)
    return Roots(objects_root, chunks_root, metadata_root, preservation_root,
                 merkle_root(auxiliary_leaves, hasher))


# ---------------------------------------------------------------------------
# building and verifying
# ---------------------------------------------------------------------------

def build_manifest(*, archive_id: bytes, snapshot_sequence: int, created_unix_ns: int,
                   objects: Iterable[ObjectEntry], chunks: Iterable[ChunkEntry],
                   hasher: Hasher, hash_algorithm: str,
                   required_capabilities: Iterable[str] = (),
                   optional_capabilities: Iterable[str] = (),
                   metadata: Iterable[dict] = (),
                   auxiliary: Iterable[dict] = (),
                   parent_snapshot: bytes | None = None,
                   packing_plan: dict | None = None) -> dict:
    """A complete manifest, with every root computed from its own contents."""
    object_entries = [entry.as_manifest_entry(hasher) for entry in objects]
    seen_paths = set()
    for entry in object_entries:
        if entry["path"] in seen_paths:
            raise InvalidInput("duplicate object path", path=entry["path"])
        seen_paths.add(entry["path"])
    object_entries.sort(key=lambda e: e["object_id"])

    chunk_map: dict[bytes, dict] = {}
    for chunk in chunks:
        if chunk.chunk_id in chunk_map:
            raise InvalidInput("duplicate chunk id", chunk_id=chunk.chunk_id.hex())
        chunk_map[chunk.chunk_id] = chunk.as_manifest_entry()

    metadata_list = list(metadata)
    auxiliary_list = list(auxiliary)
    roots = compute_roots(object_entries, chunk_map, metadata_list, auxiliary_list,
                          hasher)

    manifest: dict[str, Any] = {
        "anla_version": MANIFEST_VERSION,
        "archive_id": archive_id,
        "snapshot_sequence": snapshot_sequence,
        "created_unix_ns": created_unix_ns,
        "hash_algorithms": [hash_algorithm],
        "required_capabilities": sorted(required_capabilities),
        "optional_capabilities": sorted(optional_capabilities),
        "objects": object_entries,
        "chunks": chunk_map,
        "metadata": metadata_list,
        "auxiliary": auxiliary_list,
        "objects_root": roots.objects_root,
        "chunks_root": roots.chunks_root,
        "metadata_root": roots.metadata_root,
        "preservation_root": roots.preservation_root,
        "auxiliary_root": roots.auxiliary_root,
    }
    # Absent means absent: the CBOR profile has no null, so an optional field is
    # either present with a value or not present at all.
    if parent_snapshot is not None:
        manifest["parent_snapshot"] = parent_snapshot
    if packing_plan is not None:
        manifest["packing_plan"] = packing_plan
        manifest["packing_plan_digest"] = hasher(encode(packing_plan))
    return manifest


REQUIRED_MEMBERS = (
    "anla_version", "archive_id", "snapshot_sequence", "created_unix_ns",
    "hash_algorithms", "required_capabilities", "optional_capabilities",
    "objects", "chunks", "metadata", "auxiliary",
    "objects_root", "chunks_root", "metadata_root", "preservation_root",
    "auxiliary_root",
)


def verify_manifest(manifest: dict, hasher: Hasher) -> Roots:
    """Recompute every root from the manifest's contents and compare.

    A manifest whose declared roots disagree with what it lists is refused. The
    alternative — trusting the declared root because the footer's hash covered the
    manifest bytes — would mean a root that says nothing: it would only prove the
    manifest had not been edited, not that it describes what it claims to.
    """
    if not isinstance(manifest, dict):
        raise ManifestInvalid("manifest is not a CBOR map")
    for member in REQUIRED_MEMBERS:
        if member not in manifest:
            raise ManifestInvalid(f"manifest is missing required member: {member}")
    if manifest["anla_version"] != MANIFEST_VERSION:
        raise ManifestInvalid("unsupported manifest version",
                              found=manifest["anla_version"])
    if not isinstance(manifest["objects"], list) or not isinstance(manifest["chunks"], dict):
        raise ManifestInvalid("objects must be an array and chunks a map")

    for entry in manifest["objects"]:
        if not isinstance(entry, dict) or "object_id" not in entry:
            raise ManifestInvalid("object entry has no object_id")
        identity = {k: v for k, v in entry.items() if k != "object_id"}
        if hasher(OBJECT_ID_PREFIX + encode(identity)) != entry["object_id"]:
            raise IntegrityFailure("object_id does not match the object it identifies",
                                   path=entry.get("path"))

    recomputed = compute_roots(manifest["objects"], manifest["chunks"],
                               manifest["metadata"], manifest["auxiliary"], hasher)
    for name in ("objects_root", "chunks_root", "metadata_root", "preservation_root",
                 "auxiliary_root"):
        if manifest[name] != getattr(recomputed, name):
            raise IntegrityFailure(f"{name} disagrees with the manifest contents",
                                   declared=manifest[name].hex()[:16],
                                   computed=getattr(recomputed, name).hex()[:16])
    return recomputed


def without_auxiliary(manifest: dict, hasher: Hasher) -> dict:
    """The manifest with the intelligence plane emptied, roots updated.

    `preservation_root` is *not* recomputed differently — it cannot change, because
    the auxiliary plane is not one of its inputs. That is the property this
    arrangement exists for, and `test_manifest.py` asserts it rather than assuming
    it.
    """
    stripped = dict(manifest)
    stripped["auxiliary"] = []
    stripped["auxiliary_root"] = merkle_root([], hasher)
    return stripped


def manifest_bytes(manifest: dict) -> bytes:
    return encode(manifest)


def parse_manifest(payload: bytes) -> dict:
    value = decode(payload)
    if not isinstance(value, dict):
        raise ManifestInvalid("manifest is not a CBOR map")
    return value
