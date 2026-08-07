# -*- coding: utf-8 -*-
"""The codec registry — SPEC-1.0-DRAFT.md §8.

Numeric ids, so a codec costs two bytes in a chunk descriptor rather than a string
per chunk. `store` is 0 and `zstd` is 1; both are core, everything else is a
capability an archive has to declare.

Three things here are not obvious until you write them.

**A chunk id is the hash of the *raw* chunk, never of the stored bytes.** So a codec
cannot reach a chunk id or an `objects_root`: the tree's identity is independent of
how it was stored.

It *can* reach `chunks_root`, and therefore `preservation_root`. A chunk descriptor
carries `codec_id`, `payload_length`, `payload_hash` and an offset, all of which are
facts about storage, and compressing changes every one of them. This was measured
rather than assumed — an earlier version of this paragraph claimed
`preservation_root` was invariant and the test that checked it said otherwise.

The consequence is worth stating plainly, because it is what the freeze rule now has
to be phrased over. `preservation_root` is the identity of *this snapshot as stored*,
not of the tree in the abstract; `objects_root` is the tree. So two implementations
on different libzstd builds agree on `objects_root` and on every chunk id, and
legitimately disagree on the archive's bytes and on `preservation_root`. Byte
identity across implementations is a claim about `store`.

**A compressed chunk that grew is stored.** Random bytes come out of zstd 10 bytes
longer than they went in, and a format that "compressed" them anyway would be paying
for the privilege. The writer keeps whichever is smaller and records which it chose.

**Bomb protection is a header read, not an output limit.** `zstandard`'s
`max_output_size` is *ignored* for a frame that declares its content size — which is
every frame this writer produces — so bounding the output does nothing at all
against the case that matters. The size is read out of the frame header first and
compared with the descriptor's `raw_size`, and nothing is allocated until they
agree. A frame that declares no size is refused rather than decoded blind.

Unlike BLAKE3, there is **no dependency-free reference implementation here and there
is not going to be one**: zstd is not something to reimplement in Python for the sake
of a specification's readability. So an archive using it declares
`anla:codec:zstd:1` as a *required* capability, and a reader without the library
refuses cleanly instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from anla.errors import (
    InvalidInput,
    ResourceLimitExceeded,
    UnsupportedCapability,
)

__all__ = [
    "CODEC_STORE", "CODEC_ZSTD", "CODECS", "DEFAULT_LEVEL",
    "codec_name", "have_zstd", "zstd_library_version",
    "plan_for", "compress_chunk", "decompress_chunk",
]

CODEC_STORE = 0
CODEC_ZSTD = 1

#: Level 10 rather than zstd's default 3: an archive is written once and read for
#: years, so the asymmetry runs the other way from a network protocol's. Recorded
#: in the plan either way, because a level nobody wrote down is a level nobody can
#: reproduce.
DEFAULT_LEVEL = 10


@dataclass(frozen=True)
class Codec:
    id: int
    name: str
    capability: str | None


CODECS: dict[int, Codec] = {
    CODEC_STORE: Codec(CODEC_STORE, "store", "anla:codec:store:1"),
    CODEC_ZSTD: Codec(CODEC_ZSTD, "zstd", "anla:codec:zstd:1"),
}


def codec_name(codec_id: int) -> str:
    codec = CODECS.get(codec_id)
    if codec is None:
        raise UnsupportedCapability("unknown codec id", codec_id=codec_id,
                                    known=sorted(CODECS))
    return codec.name


def _zstd():
    try:
        import zstandard
    except ImportError as exc:                       # pragma: no cover - env dependent
        raise UnsupportedCapability(
            "this archive uses zstd and the zstandard library is not installed",
            install="pip install zstandard") from exc
    return zstandard


def have_zstd() -> bool:
    try:
        import zstandard
    except ImportError:                              # pragma: no cover - env dependent
        return False
    return zstandard is not None


def zstd_library_version() -> str | None:
    """The libzstd build, recorded in the plan.

    Not decoration. Compressed bytes are a function of the compressor, so this is
    the field that says whether another writer could be expected to reproduce them
    — and it is the honest answer to why byte-identity across implementations is a
    claim about `store` and about `preservation_root`, not about compressed payloads.
    """
    if not have_zstd():                              # pragma: no cover - env dependent
        return None
    return ".".join(str(part) for part in _zstd().ZSTD_VERSION)


def plan_for(codec_id: int, level: int = DEFAULT_LEVEL) -> dict:
    """The `packing_plan.codec` block: everything a second writer would need."""
    if codec_id == CODEC_STORE:
        return {"id": CODEC_STORE, "name": "store"}
    if codec_id != CODEC_ZSTD:
        raise UnsupportedCapability("unknown codec id", codec_id=codec_id)
    if not 1 <= level <= 22:
        raise InvalidInput("zstd level must be between 1 and 22", level=level)
    plan = {"id": CODEC_ZSTD, "name": "zstd", "level": level}
    version = zstd_library_version()
    if version is not None:
        plan["library"] = f"libzstd {version}"
    return plan


def compress_chunk(raw: bytes, codec_id: int, level: int = DEFAULT_LEVEL,
                   ) -> tuple[int, bytes]:
    """Returns the codec actually used and the bytes to store.

    `store` is chosen whenever compression did not help. A chunk of random bytes
    comes back from zstd slightly *longer*, and storing that would mean paying a
    decompression step for a larger file.
    """
    if codec_id == CODEC_STORE or not raw:
        return CODEC_STORE, raw
    if codec_id != CODEC_ZSTD:
        raise UnsupportedCapability("unknown codec id", codec_id=codec_id)
    packed = _zstd().ZstdCompressor(level=level).compress(raw)
    if len(packed) >= len(raw):
        return CODEC_STORE, raw
    return CODEC_ZSTD, packed


def decompress_chunk(payload: bytes, codec_id: int, raw_size: int) -> bytes:
    """Restore one chunk, refusing anything that would decode to the wrong size.

    The size check happens **before** any allocation, by reading the frame header.
    `zstandard`'s `max_output_size` is ignored for a frame that declares its content
    size, so limiting the output would be protection that looks real and is not.
    """
    if codec_id == CODEC_STORE:
        if len(payload) != raw_size:
            raise ResourceLimitExceeded("stored chunk is not its declared size",
                                        declared=raw_size, actual=len(payload))
        return payload
    if codec_id != CODEC_ZSTD:
        raise UnsupportedCapability("unknown codec id", codec_id=codec_id)

    zstandard = _zstd()
    try:
        declared = zstandard.get_frame_parameters(payload).content_size
    except zstandard.ZstdError as exc:
        raise InvalidInput("not a zstd frame", detail=str(exc)) from exc
    # 2**64-1 is zstd's "unknown". A writer that omitted the size leaves a reader
    # with no way to know what it is about to allocate, so it is refused rather
    # than decoded and measured afterwards.
    if declared == (1 << 64) - 1:
        raise ResourceLimitExceeded(
            "zstd frame declares no content size, so its output is unbounded")
    if declared != raw_size:
        raise ResourceLimitExceeded(
            "zstd frame and its descriptor disagree about the decoded size",
            frame=declared, descriptor=raw_size)

    raw = zstandard.ZstdDecompressor().decompress(payload)
    if len(raw) != raw_size:                         # pragma: no cover - defence
        raise ResourceLimitExceeded("zstd decoded to the wrong size",
                                    got=len(raw), expected=raw_size)
    return raw


def deterministic_across_builds(codec_id: int) -> bool:
    """Whether two writers can be expected to produce identical stored bytes.

    `store` yes, always. `zstd` **no**: the encoder's output depends on the library
    that produced it, and two conforming writers on different libzstd versions may
    disagree byte for byte while both being entirely correct.

    Two such archives still agree on every chunk id and on `objects_root`, because
    those are computed from raw content. They disagree on `chunks_root` and on
    `preservation_root`, which cover the descriptors — storage facts, which a codec
    is precisely in the business of changing.

    So the freeze rule's byte-identity clause is a claim about `store`. What holds
    for a compressed archive is that the *tree* is identical, and that is what a
    cross-implementation check should compare. This function exists so a caller
    checks rather than assumes which of the two it is entitled to.
    """
    return codec_id == CODEC_STORE
