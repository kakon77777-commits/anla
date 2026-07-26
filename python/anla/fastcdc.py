# -*- coding: utf-8 -*-
"""Content-defined chunking: the `anla-cdc-1` profile.

Fixed-size chunking deduplicates badly. Insert one byte at the front of a file
and every chunk boundary after it moves, so every chunk gets a new content id and
nothing is shared with the previous version. Content-defined chunking cuts on the
data itself, so an edit only disturbs the chunks around it.

The whitepaper (chapter 14.3) lists this as a target and its open question 3 asks
how FastCDC parameters can become a permanently stable profile. That question is
not academic: a chunker whose boundaries depend on an unstated table is a chunker
whose output depends on which implementation ran. That is the same class of defect
as the locale-dependent object ordering this project already had to correct once —
found late, and only because two implementations were compared byte for byte.

So this profile pins everything, and pins it in a form a third party can check
without trusting us:

* **Fingerprint.** 32-bit unsigned, ``fp = ((fp >> 1) + gear[byte]) mod 2**32``.
  32 bits because JavaScript's bitwise operators are exactly 32-bit, so both
  reference implementations can be exact and fast without bignum arithmetic.

* **Gear table.** Not a magic blob of 256 constants copied between codebases —
  *derived*: ``gear[i] = big-endian uint32 of SHA-256(b"anla-gear-1\\x00" + i)``.
  Anyone can regenerate it in three lines and confirm ours was not tampered with.
  ``GEAR_TABLE_DIGEST`` pins the result.

* **Boundary predicate.** ``(fp >> (32 - k)) == 0``, i.e. the top *k* bits are
  zero, giving an expected chunk length of ``2**k``. The top bits are used rather
  than the bottom because in gear hashing the accumulated history lives in the
  high bits; masking the low bits would cut on almost nothing.

* **Normalization.** Before the average size is reached the predicate uses
  ``k + normalization`` bits, after it ``k - normalization``. This is FastCDC's
  normalized chunking: it pulls the size distribution towards the average instead
  of the exponential tail plain CDC produces.

The paper's spread masks are deliberately not used. They are tuned for a 64-bit
fingerprint, and reproducing a mask constant across implementations by hand is
exactly the failure this profile exists to avoid. The gear table already provides
the diffusion; the mask only needs to be unambiguous.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from .errors import InvalidInput

__all__ = [
    "PROFILE_ID", "GEAR_TABLE_ID", "GEAR_TABLE_DIGEST", "GEAR",
    "CdcProfile", "DEFAULT_PROFILE", "build_gear_table", "next_cut", "cut_points",
]

PROFILE_ID = "anla-cdc-1"
GEAR_TABLE_ID = "anla-gear-1"
MASK32 = 0xFFFFFFFF


def build_gear_table(table_id: str = GEAR_TABLE_ID) -> tuple[int, ...]:
    """Derive the 256-entry gear table from its identifier.

    Three lines, no constants to copy, and independently checkable.
    """
    seed = table_id.encode("ascii") + b"\x00"
    return tuple(
        struct.unpack(">I", hashlib.sha256(seed + bytes([index])).digest()[:4])[0]
        for index in range(256)
    )


GEAR = build_gear_table()

#: SHA-256 over the 256 gear words, big-endian, concatenated. A third
#: implementation that matches this has the same table, whatever else it does.
GEAR_TABLE_DIGEST = hashlib.sha256(
    b"".join(struct.pack(">I", word) for word in GEAR)
).hexdigest()


@dataclass(frozen=True)
class CdcProfile:
    """A fully specified content-defined chunking configuration."""

    min_size: int = 64 * 1024
    avg_size: int = 256 * 1024
    max_size: int = 1024 * 1024
    normalization: int = 2
    algorithm: str = "fastcdc"
    version: str = PROFILE_ID
    gear_table_id: str = GEAR_TABLE_ID

    def __post_init__(self) -> None:
        if self.algorithm != "fastcdc":
            raise InvalidInput("unsupported chunking algorithm", algorithm=self.algorithm)
        if self.version != PROFILE_ID or self.gear_table_id != GEAR_TABLE_ID:
            raise InvalidInput("unknown chunking profile",
                               version=self.version, gear_table_id=self.gear_table_id)
        if not 1 <= self.min_size <= self.avg_size <= self.max_size:
            raise InvalidInput("chunking sizes must satisfy 1 <= min <= avg <= max",
                               min=self.min_size, avg=self.avg_size, max=self.max_size)
        if self.avg_size & (self.avg_size - 1):
            raise InvalidInput("avg_size must be a power of two", avg_size=self.avg_size)
        bits = self.avg_size.bit_length() - 1
        if not 0 <= self.normalization <= 3 or bits - self.normalization < 1 \
                or bits + self.normalization > 31:
            raise InvalidInput("normalization is out of range for this average size",
                               normalization=self.normalization, avg_bits=bits)

    @property
    def bits(self) -> int:
        return self.avg_size.bit_length() - 1

    def as_manifest_member(self) -> dict:
        """The plan's `chunking` member. Every value a second implementation needs."""
        return {
            "algorithm": self.algorithm,
            "version": self.version,
            "gear_table_id": self.gear_table_id,
            "gear_table_sha256": GEAR_TABLE_DIGEST,
            "min": self.min_size,
            "avg": self.avg_size,
            "max": self.max_size,
            "normalization": self.normalization,
            "fingerprint": "gear32",
            "boundary": "top-bits-zero",
        }


DEFAULT_PROFILE = CdcProfile()


def next_cut(data: bytes, start: int, profile: CdcProfile = DEFAULT_PROFILE) -> int:
    """Return the index one past the end of the chunk beginning at *start*.

    Deliberately written as the plainest possible loop. This function's output is
    part of the format's identity, so it is the last place to be clever.
    """
    remaining = len(data) - start
    if remaining <= profile.min_size:
        return len(data)

    limit = start + min(remaining, profile.max_size)
    normal_end = start + min(remaining, profile.avg_size)
    bits = profile.bits
    strict_shift = 32 - (bits + profile.normalization)
    loose_shift = 32 - (bits - profile.normalization)

    fingerprint = 0
    index = start + profile.min_size
    while index < normal_end:
        fingerprint = ((fingerprint >> 1) + GEAR[data[index]]) & MASK32
        if (fingerprint >> strict_shift) == 0:
            return index + 1
        index += 1
    while index < limit:
        fingerprint = ((fingerprint >> 1) + GEAR[data[index]]) & MASK32
        if (fingerprint >> loose_shift) == 0:
            return index + 1
        index += 1
    return limit


def cut_points(data: bytes, profile: CdcProfile = DEFAULT_PROFILE) -> list[tuple[int, int]]:
    """Split *data* into ``(start, end)`` ranges. Ranges tile the input exactly."""
    ranges: list[tuple[int, int]] = []
    at = 0
    total = len(data)
    while at < total:
        end = next_cut(data, at, profile)
        ranges.append((at, end))
        at = end
    return ranges
