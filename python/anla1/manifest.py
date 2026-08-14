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

from anla.errors import IntegrityFailure, InvalidInput, ManifestInvalid, UnsafeObject
from anla.format import safe_path

from .cbor import decode_untrusted, encode
from .merkle import merkle_root

__all__ = [
    "OBJECT_ID_PREFIX", "PRESERVATION_PREFIX", "OBJECT_KINDS",
    "METADATA_NAMESPACES", "FIDELITY_REASONS",
    "ObjectEntry", "ChunkEntry", "Roots",
    "object_id_for", "object_leaf", "chunk_leaf", "check_object_path", "sorted_by_path",
    "derive_path", "check_native_name", "native_name_for", "NATIVE_NAME_CAPABILITY",
    "check_metadata", "check_fidelity", "fidelity_of",
    "compute_roots", "build_manifest", "verify_manifest", "without_auxiliary",
]

#: What 1.0 can represent. Anything else — devices, sockets, FIFOs — is refused
#: rather than approximated, because an archive that stored one as an empty file
#: would have changed what the tree means without saying so.
OBJECT_KINDS = ("regular-file", "directory", "symbolic-link")

#: Metadata namespaces this implementation understands. A namespace it does not
#: know is *not* an error: metadata lives inside `object_id`, so an unknown
#: namespace verifies exactly the same, it simply cannot be applied. That is why
#: namespaces belong in `optional_capabilities` and never in `required` — see
#: `design/milestone-2-plan.md` decision 3, which retires the draft's guess that
#: `metadata_root` should be split per namespace.
METADATA_NAMESPACES = ("common", "posix", "fidelity")

#: Reasons an object can be missing from an archive that was otherwise packed.
#: Free text would make the report unsummarisable, which is most of what a report
#: is for.
FIDELITY_REASONS = ("kind-not-representable", "read-failed", "excluded-by-policy")


#: A native name is an *optional* capability. A reader that ignores it restores
#: the object under `path` — the content is intact, the archive still holds the
#: true name, and what is lost is the ability to *apply* it. That is the same
#: "stored but not applied" state metadata namespaces are in, and for the same
#: reason: requiring it would refuse an archive this reader could restore
#: perfectly. See design/q4-name-model.md decision 3.
NATIVE_NAME_CAPABILITY = "anla:object:native-name:1"


def derive_path(name: bytes) -> str:
    """The portable rendering of a name that may not be UTF-8.

    Decode as UTF-8; write each byte that will not decode as `%XX`, uppercase.

    The obvious objection is ambiguity — a file genuinely called `caf%E9.txt`
    derives what `caf<0xE9>.txt` derives. It does not matter, and the reason is
    worth stating rather than escaping around: **when `name` is present, `path` is
    not the object's identity.** `name` is. A derived `path` is a label, and a label
    only has to be unique within the snapshot, which §5.2.1's duplicate-path rule
    already enforces — loudly, at write time, naming both. So this needs no
    escape-the-escape rule; it needs a uniqueness check, and that check already
    exists and is already tested.
    """
    if not isinstance(name, (bytes, bytearray)):
        raise InvalidInput("a native name is bytes", got=type(name).__name__)
    # `surrogateescape` puts each undecodable byte at U+DC00+byte, which is exactly
    # the set this then rewrites — so the round trip is byte-exact by construction
    # rather than by a table someone has to keep in step.
    return "".join(
        f"%{ord(ch) - 0xDC00:02X}" if 0xDC80 <= ord(ch) <= 0xDCFF else ch
        for ch in bytes(name).decode("utf-8", "surrogateescape"))


def check_native_name(name: object, *, path: str) -> bytes:
    """`name` is legal only if `path` is what it derives.

    That relation is the whole safety argument, and without it the two-field model
    is worse than one field. A reader that prefers `name` and a reader that falls
    back to `path` must place the object in the *same* location; if the two were
    independent, an archive could carry a harmless `path` and a traversing `name`
    and the two conforming readers would disagree about where the file goes — with
    every hash verifying. Tying them together also means `path`'s safety check
    covers `name`, because the derivation escapes only undecodable bytes and never
    removes a `/` or a `.`: a traversing name derives a traversing path, and that
    path is refused.

    A `name` equal to `path` encoded is refused as well. It carries nothing, and a
    manifest with two ways to say the same thing has two encodings of one archive.
    """
    if not isinstance(name, (bytes, bytearray)):
        raise ManifestInvalid("a native name must be a byte string", path=path,
                              got=type(name).__name__)
    name = bytes(name)
    if not name:
        raise UnsafeObject("a native name must not be empty", path=path)
    if name == path.encode("utf-8"):
        raise ManifestInvalid(
            "a native name equal to the path carries nothing and is omitted",
            path=path)
    derived = derive_path(name)
    if derived != path:
        raise ManifestInvalid("the path is not this name's derivation",
                              path=path, derived=derived)
    return name


def native_name_for(name: bytes) -> tuple[str, bytes | None]:
    """Split a native name into the pair an object carries.

    Returns `(path, name_or_None)`. **`None` whenever the name is already UTF-8**,
    which is not a size optimisation: it means `object_id` is unchanged for every
    object whose name needed no answer to question 4, so answering it invalidates
    no existing archive that did not have the problem. Always emitting `name` would
    have changed every object id ever written, to fix a case most archives do not
    have.
    """
    path = derive_path(name)
    return path, None if path.encode("utf-8") == bytes(name) else bytes(name)


def check_object_path(path: object) -> str:
    """One definition of a legal object path, used on the way in and on the way out.

    `safe_path` is MVP's rule (SPEC.md §9), reused rather than restated. It *returns
    a normalized path*, and the check here is equality with what it returned — a
    path it had to change is refused rather than quietly accepted in its rewritten
    form. That distinction matters more than it looks: `safe_path` turns backslashes
    into separators, so a POSIX file genuinely named `a\\b` would otherwise be
    stored as `a/b` and restored as a file `b` inside a directory `a`. Refusing is
    the honest answer until whitepaper question 4 settles the name model.

    The read-side call is the security boundary. The write-side call is a courtesy
    that turns bad input into an error instead of an artifact.
    """
    normalized = safe_path(path)
    if normalized != path:
        raise UnsafeObject("object path is not stored in normalized form",
                           path=path, normalized=normalized)
    # And it must be *encodable*. `safe_path` checks a path's structure and never
    # asked whether it could become bytes, so a POSIX name that is not UTF-8 — which
    # `os.listdir` hands back as lone surrogates — passed this function and then
    # crashed four layers down in the CBOR encoder with a UnicodeEncodeError. A
    # crash where a refusal is owed. See `design/q4-name-model.md`.
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise UnsafeObject(
            "object path cannot be encoded as UTF-8",
            path=ascii(normalized), detail=str(exc),
            hint="a name that is not UTF-8 needs the native-name model, "
                 "design/q4-name-model.md") from exc
    return normalized


def sorted_by_path(items: Iterable[Any], path_of: Callable[[Any], str] = lambda e: e.path) -> list:
    """Validate, then order — the single place a path becomes bytes for sorting.

    SPEC §5.2.1 orders objects by their UTF-8 path bytes, so `encode("utf-8")` in a
    sort key is the *first* thing in the writer that assumes a path is encodable. It
    was written five separate times, and all five raised `UnicodeEncodeError` from
    inside a lambda instead of the refusal a caller is owed. Patching them one at a
    time would have left the sixth to be written later with the same defect, so the
    validation lives here, in the operation that needs it, and the call sites cannot
    order a path without it.
    """
    items = list(items)
    for item in items:
        check_object_path(path_of(item))
    return sorted(items, key=lambda item: path_of(item).encode("utf-8"))


#: Domain separation again, for the same reason as in the Merkle tree: an object id
#: and a Merkle leaf must not be computable from one another.
OBJECT_ID_PREFIX = b"\x10"
PRESERVATION_PREFIX = b"\x03"

Hasher = Callable[[bytes], bytes]

MANIFEST_VERSION = [1, 0]


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

def check_metadata(metadata: object, *, path: str) -> None:
    """Namespaced, and shaped the same on the way in as on the way out.

    An unknown namespace is deliberately **allowed**: metadata is inside
    `object_id`, so a reader that has never heard of it verifies identically and
    only loses the ability to apply it. What is refused is metadata that is not
    namespaced at all, because a bare `mode` key means something different on every
    platform and gives a reader nowhere to record that it could not use it.
    """
    if not isinstance(metadata, dict):
        raise ManifestInvalid("object metadata must be a map", path=path)
    for namespace, entries in metadata.items():
        if not isinstance(namespace, str) or not namespace:
            raise ManifestInvalid("metadata namespace must be a non-empty string",
                                  path=path, namespace=repr(namespace)[:40])
        if not isinstance(entries, dict):
            raise ManifestInvalid("a metadata namespace must hold a map",
                                  path=path, namespace=namespace)
        for key in entries:
            if not isinstance(key, str):
                raise ManifestInvalid("metadata keys must be strings",
                                      path=path, namespace=namespace)


def check_fidelity(entries: object) -> list[dict]:
    """The record of what the writer could not keep.

    Every entry needs a path and a reason from a closed set. Free text would make
    the report unsummarisable, and a report nobody can summarise is one nobody
    reads — which for a record of *absence* means it may as well not exist.
    """
    if not isinstance(entries, list):
        raise ManifestInvalid("the fidelity report must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ManifestInvalid("a fidelity entry must be a map")
        for required in ("path", "reason"):
            if not isinstance(entry.get(required), str) or not entry[required]:
                raise ManifestInvalid(f"a fidelity entry needs a {required}",
                                      entry=repr(entry)[:80])
        if entry["reason"] not in FIDELITY_REASONS:
            raise ManifestInvalid("unknown fidelity reason", reason=entry["reason"],
                                  known=list(FIDELITY_REASONS))
    return entries


def fidelity_of(manifest: dict) -> list[dict]:
    """The report, or an empty list. Never `None` — absence is completeness."""
    for block in manifest.get("metadata", []):
        if isinstance(block, dict) and block.get("namespace") == "fidelity":
            return list(block.get("entries", []))
    return []


@dataclass(frozen=True)
class ObjectEntry:
    """One filesystem object.

    Two fields, two jobs. `path` is the portable name: always present, always valid
    UTF-8, always §5.2.1-safe, and what a reader displays, a person greps for, and a
    restore onto a *different* platform uses. `name` is the native bytes, and it is
    what an exact restore on the source platform uses.

    Neither can do the other's job, which is why one field was never enough: a UTF-8
    string cannot represent a name that is not UTF-8, and a byte string can but makes
    every path in every manifest unreadable to pay for a case most archives do not
    have. `name` is therefore **absent whenever it would be redundant**, so
    `object_id` is unchanged for every object whose name is already UTF-8.
    """

    kind: str
    path: str
    #: The native bytes, present only when they differ from `path` encoded as UTF-8.
    #: `path` must be `derive_path(name)` — see `check_native_name` for why that
    #: relation is the safety argument and not merely a convention.
    name: bytes | None = None
    size: int = 0
    content_hash: bytes = b""
    chunks: tuple[bytes, ...] = ()
    #: Namespaced: `{"common": {"mtime_ns": …}, "posix": {"mode": …}}`. Flat keys
    #: are refused, because "mode" means something different on every platform and
    #: a bare key gives a reader nowhere to put that fact.
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: For `symbolic-link` only: the target exactly as the operating system gave it.
    #: Bytes, not a path — see the class docstring.
    target: bytes | None = None

    def identity(self) -> dict:
        """The fields an object id is computed over — everything but the id."""
        # Checked *here*, where the encoding happens, not in `build_manifest` which
        # validates the entries after `as_manifest_entry` has already encoded them.
        # An unencodable path therefore reached the CBOR encoder first and came back
        # as a UnicodeEncodeError. A check placed after the thing it is meant to
        # guard is not a check.
        check_object_path(self.path)
        body: dict[str, Any] = {"kind": self.kind, "path": self.path}
        if self.name is not None:
            body["name"] = check_native_name(self.name, path=self.path)
        if self.kind == "regular-file":
            body["size"] = self.size
            body["content_hash"] = self.content_hash
            body["chunks"] = list(self.chunks)
        if self.kind == "symbolic-link":
            if self.target is None:
                raise InvalidInput("a symbolic link needs a target", path=self.path)
            body["target"] = bytes(self.target)
        if self.metadata:
            # Checked here rather than trusted, because the flat `{"mtime_ns": …}`
            # shape this replaced is exactly what a caller written against the
            # previous draft still passes — and it would otherwise reach the encoder
            # as a plausible-looking map and be stored.
            check_metadata(self.metadata, path=self.path)
            body["metadata"] = {ns: dict(entries)
                                for ns, entries in sorted(self.metadata.items())}
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
        check_object_path(entry["path"])
        if entry["kind"] not in OBJECT_KINDS:
            raise InvalidInput("unsupported object kind", kind=entry["kind"],
                               path=entry["path"], supported=list(OBJECT_KINDS))
        if "metadata" in entry:
            check_metadata(entry["metadata"], path=entry["path"])
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
    for block in metadata_list:
        if block.get("namespace") == "fidelity":
            check_fidelity(block.get("entries"))
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

    seen_paths: set[str] = set()
    for entry in manifest["objects"]:
        if not isinstance(entry, dict) or "object_id" not in entry:
            raise ManifestInvalid("object entry has no object_id")
        # Absence and illegality are different answers, and this line used to give
        # the same one to both: `entry.get("path")` returns `None` for a manifest
        # with no `path` member at all, and `check_object_path` reported that as an
        # *unsafe path* — a security event — when what had actually happened was a
        # required member going missing. Rust called it `manifest-invalid`, Rust was
        # right, and the hostile-writer mutator is what made the two disagree out
        # loud. A caller acts differently on the two: one says an archive tried to
        # escape, the other says these bytes are broken.
        if not isinstance(entry.get("path"), str):
            raise ManifestInvalid("object entry has no path",
                                  found=type(entry.get("path")).__name__)
        # *Now* the security boundary. Until Milestone 1 nothing put a real
        # filesystem path into a 1.0 archive, so nothing had yet needed to say what
        # a legal one is — an omission, not a decision.
        path = check_object_path(entry["path"])
        if "name" in entry:
            check_native_name(entry["name"], path=path)
        if entry.get("kind") not in OBJECT_KINDS:
            raise ManifestInvalid("unsupported object kind", kind=entry.get("kind"),
                                  path=path, supported=list(OBJECT_KINDS))
        if path in seen_paths:
            raise UnsafeObject("duplicate object path", path=path)
        seen_paths.add(path)
        if entry["kind"] == "symbolic-link" and not isinstance(entry.get("target"), bytes):
            raise ManifestInvalid("a symbolic link needs a byte-string target",
                                  path=path)
        if "metadata" in entry:
            check_metadata(entry["metadata"], path=path)
        identity = {k: v for k, v in entry.items() if k != "object_id"}
        if hasher(OBJECT_ID_PREFIX + encode(identity)) != entry["object_id"]:
            raise IntegrityFailure("object_id does not match the object it identifies",
                                   path=entry.get("path"))

    seen_namespaces: set[str] = set()
    for block in manifest["metadata"]:
        if not isinstance(block, dict) or not isinstance(block.get("namespace"), str):
            raise ManifestInvalid("an archive metadata block needs a namespace")
        if block["namespace"] in seen_namespaces:
            raise ManifestInvalid("a metadata namespace appears twice",
                                  namespace=block["namespace"])
        seen_namespaces.add(block["namespace"])
        if block["namespace"] == "fidelity":
            check_fidelity(block.get("entries"))

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
    """Decode a manifest, and refuse one that is missing a member §5 requires.

    The presence check used to live only in `verify_manifest`, which runs *after*
    `read_snapshot` has already read `manifest["hash_algorithms"]` to cross-check it
    against the record header. A manifest without that member therefore reached an
    unguarded subscript and left the CLI as a `KeyError` traceback while Rust
    answered `manifest-invalid` — the third defect of exactly this shape, after the
    UTF-8 path and the missing `path` member.

    All three were one mistake repeated: a required member read somewhere other than
    the one place that checks required members are there. Putting the check in the
    *constructor* rather than the validator is what ends the pattern — downstream
    code cannot obtain a manifest that lacks a member, so it cannot forget to ask.
    """
    value = decode_untrusted(payload, what="manifest")
    if not isinstance(value, dict):
        raise ManifestInvalid("manifest is not a CBOR map")
    for member in REQUIRED_MEMBERS:
        if member not in value:
            raise ManifestInvalid(f"manifest is missing required member: {member}")
    return value
