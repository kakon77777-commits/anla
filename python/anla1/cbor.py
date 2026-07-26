# -*- coding: utf-8 -*-
"""Canonical CBOR for ANLA 1.0 — the encoding the manifest is hashed over.

Whitepaper open question 2 asked which deterministic CBOR profile to adopt. The
answer recorded in design/decisions-for-1.0.md is RFC 8949 §4.2.1 core
deterministic encoding, plus three restrictions of our own. This module is that
answer as code, in both directions:

* **The encoder** emits exactly one byte sequence for any given value. Integers in
  their shortest form, definite lengths only, map keys sorted by their *encoded
  bytes*, and no floats.

* **The decoder is strict by default, and that is the point.** It refuses
  non-canonical input — a non-shortest integer, an indefinite length, map keys out
  of order or repeated — rather than accepting it and producing the same object a
  canonical encoding would have produced.

That second property is the one worth arguing for. The manifest hash is computed
over manifest *bytes*. A decoder that accepts two different encodings of the same
logical manifest is a decoder through which two archives with different hashes can
mean the same thing — and a decoder that accepts what a signer never anticipated is
where parser-differential attacks live. Strictness here is not fastidiousness; it
is the property that makes a hash over an encoding worth computing.

Written without dependencies, and deliberately: this file defines part of the
format's identity, so it should be readable end to end by someone checking the
specification against it.

Not supported, on purpose:

* floats — a value whose bytes depend on how it was computed has no place in a
  preservation plane;
* `null` and `undefined` — absence is expressed by omitting the key, as in MVP;
* tags — nothing in the manifest needs one, and an unknown tag is a semantic
  question a container should not have to answer;
* indefinite lengths — a streaming writer wants them, a signature over a manifest
  cannot afford them.
"""

from __future__ import annotations

import struct
from typing import Any

__all__ = [
    "encode", "decode", "CborError", "NotCanonical",
    "MAJOR_UINT", "MAJOR_NEGINT", "MAJOR_BYTES", "MAJOR_TEXT",
    "MAJOR_ARRAY", "MAJOR_MAP", "MAJOR_SIMPLE",
]

MAJOR_UINT = 0
MAJOR_NEGINT = 1
MAJOR_BYTES = 2
MAJOR_TEXT = 3
MAJOR_ARRAY = 4
MAJOR_MAP = 5
MAJOR_TAG = 6
MAJOR_SIMPLE = 7


class CborError(ValueError):
    """The input is not CBOR this profile can represent."""


class NotCanonical(CborError):
    """The input is valid CBOR but not in the canonical form this profile requires."""


# ---------------------------------------------------------------------------
# encoding
# ---------------------------------------------------------------------------

def _head(major: int, argument: int) -> bytes:
    """The initial byte plus its shortest possible argument."""
    if argument < 0:
        raise CborError(f"negative argument: {argument}")
    if argument < 24:
        return bytes([(major << 5) | argument])
    if argument <= 0xFF:
        return bytes([(major << 5) | 24, argument])
    if argument <= 0xFFFF:
        return bytes([(major << 5) | 25]) + struct.pack(">H", argument)
    if argument <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + struct.pack(">I", argument)
    if argument <= 0xFFFFFFFFFFFFFFFF:
        return bytes([(major << 5) | 27]) + struct.pack(">Q", argument)
    raise CborError(f"argument exceeds 64 bits: {argument}")


def encode(value: Any) -> bytes:
    """Encode *value* canonically."""
    # bool before int: isinstance(True, int) is True in Python, and CBOR encodes
    # them in entirely different major types.
    if value is True:
        return b"\xf5"
    if value is False:
        return b"\xf4"
    if value is None:
        raise CborError("null is not used by ANLA 1.0; omit the key instead")
    if isinstance(value, float):
        raise CborError("floating point must not appear in a preservation plane")
    if isinstance(value, int):
        if value >= 0:
            return _head(MAJOR_UINT, value)
        return _head(MAJOR_NEGINT, -value - 1)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return _head(MAJOR_BYTES, len(raw)) + raw
    if isinstance(value, str):
        raw = value.encode("utf-8", errors="strict")
        return _head(MAJOR_TEXT, len(raw)) + raw
    if isinstance(value, (list, tuple)):
        return _head(MAJOR_ARRAY, len(value)) + b"".join(encode(item) for item in value)
    if isinstance(value, dict):
        # RFC 8949 §4.2.1: sort by the *encoded* key bytes, bytewise. Not by the
        # Python value — that would order 10 before 9 for integer keys, and would
        # order text keys by code point rather than by their UTF-8 encoding.
        items = []
        for key, item in value.items():
            encoded_key = encode(key)
            items.append((encoded_key, encode(item)))
        items.sort(key=lambda pair: pair[0])
        # Unreachable from a Python dict — two keys that encode identically are the
        # same dict key — but kept for any future caller that passes pairs rather
        # than a mapping. Cheap, and the alternative is a silent collision.
        for earlier, later in zip(items, items[1:]):
            if earlier[0] == later[0]:
                raise CborError("duplicate map key")
        return _head(MAJOR_MAP, len(items)) + b"".join(k + v for k, v in items)
    raise CborError(f"type {type(value).__name__} has no canonical CBOR form")


# ---------------------------------------------------------------------------
# decoding
# ---------------------------------------------------------------------------

#: Nesting deeper than this is refused. A manifest is a handful of levels deep;
#: anything approaching this bound is an attack rather than a document. The limit
#: exists because recursion depth is an input, and a decoder fed by strangers must
#: refuse rather than let the interpreter run out of stack.
MAX_DEPTH = 64


class _Reader:
    def __init__(self, data: bytes, strict: bool, max_depth: int):
        self.data = data
        self.at = 0
        self.strict = strict
        self.max_depth = max_depth
        self.depth = 0

    def take(self, count: int) -> bytes:
        if count < 0 or self.at + count > len(self.data):
            raise CborError(f"truncated: wanted {count} bytes at offset {self.at}")
        chunk = self.data[self.at:self.at + count]
        self.at += count
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def argument(self, initial: int) -> int:
        """Read the argument, refusing a longer encoding than the value needs."""
        info = initial & 0x1F
        if info < 24:
            return info
        if info == 24:
            value = self.byte()
            minimum = 24
            width = 1
        elif info == 25:
            value = struct.unpack(">H", self.take(2))[0]
            minimum = 0x100
            width = 2
        elif info == 26:
            value = struct.unpack(">I", self.take(4))[0]
            minimum = 0x10000
            width = 4
        elif info == 27:
            value = struct.unpack(">Q", self.take(8))[0]
            minimum = 0x100000000
            width = 8
        elif info == 31:
            raise CborError("indefinite lengths are not part of this profile")
        else:
            raise CborError(f"reserved additional information: {info}")
        if self.strict and value < minimum:
            raise NotCanonical(
                f"{value} encoded in {width} byte(s) where a shorter form exists")
        return value

    def item(self) -> Any:
        if self.depth > self.max_depth:
            raise CborError(f"nesting deeper than {self.max_depth} levels")
        initial = self.byte()
        major = initial >> 5
        if major == MAJOR_UINT:
            return self.argument(initial)
        if major == MAJOR_NEGINT:
            return -1 - self.argument(initial)
        if major == MAJOR_BYTES:
            return self.take(self.argument(initial))
        if major == MAJOR_TEXT:
            raw = self.take(self.argument(initial))
            try:
                return raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise CborError(f"text string is not valid UTF-8: {exc}") from exc
        if major == MAJOR_ARRAY:
            count = self.argument(initial)
            self.depth += 1
            try:
                return [self.item() for _ in range(count)]
            finally:
                self.depth -= 1
        if major == MAJOR_MAP:
            count = self.argument(initial)
            self.depth += 1
            try:
                return self._map(count)
            finally:
                self.depth -= 1
        if major == MAJOR_TAG:
            self.argument(initial)
            raise CborError("tags are not part of this profile")
        return self._simple(initial)

    def _map(self, count: int) -> dict:
            out: dict = {}
            previous: bytes | None = None
            for _ in range(count):
                start = self.at
                key = self.item()
                encoded_key = self.data[start:self.at]
                if not isinstance(key, (int, str, bytes)):
                    raise CborError(f"map key of type {type(key).__name__}")
                if self.strict and previous is not None:
                    if encoded_key == previous:
                        raise CborError("duplicate map key")
                    if encoded_key < previous:
                        raise NotCanonical("map keys are not in canonical order")
                elif key in out:
                    raise CborError("duplicate map key")
                previous = encoded_key
                out[key] = self.item()
            return out

    def _simple(self, initial: int) -> Any:
        """Major type 7: simple values, and the floats this profile forbids."""
        info = initial & 0x1F
        if info == 20:
            return False
        if info == 21:
            return True
        if info == 22:
            raise CborError("null is not used by ANLA 1.0")
        if info == 23:
            raise CborError("undefined is not part of this profile")
        if info in (25, 26, 27):
            raise CborError("floating point must not appear in a preservation plane")
        raise CborError(f"unsupported simple value: {info}")


def decode(data: bytes, *, strict: bool = True, max_depth: int = MAX_DEPTH) -> Any:
    """Decode one canonical CBOR item, refusing trailing bytes.

    With ``strict`` (the default) a non-canonical encoding of a representable value
    is an error rather than something quietly normalized on the way in.
    """
    reader = _Reader(bytes(data), strict, max_depth)
    value = reader.item()
    if reader.at != len(reader.data):
        raise CborError(f"{len(reader.data) - reader.at} trailing byte(s) after the item")
    return value
