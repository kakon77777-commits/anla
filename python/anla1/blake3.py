# -*- coding: utf-8 -*-
"""BLAKE3-256 — the core hash of ANLA 1.0, as a dependency-free reference.

Whitepaper open question 1 chose BLAKE3-256 as the required core hash, with
SHA-256 as a declarable capability rather than a second mandatory one. This module
is that decision in code.

**Why a pure-Python implementation when a fast one exists.** The `blake3` package
is a Rust extension and is used automatically when installed — nobody should hash a
gigabyte through this file. But a format specification whose hash is only available
as a compiled wheel has a hole in it: someone checking the specification cannot read
what it says the hash is. This file is the readable answer, and `test_blake3.py`
asserts it agrees with the Rust one byte for byte over every length that matters,
which is worth more than either implementation alone.

It is the same shape as the JavaScript SHA-256 fallback in `web/anla-core.js`: a
readable reference, plus a fast path when the platform has one.

The structure is BLAKE3's own: input is cut into 1024-byte chunks, each chunk is
compressed 64 bytes at a time, and the chunk chaining values form a binary tree
whose root is the hash. The flags — CHUNK_START, CHUNK_END, PARENT, ROOT — are what
keep a leaf from being confusable with a parent, which is the same domain-separation
concern as `merkle.py`, solved inside the compression function rather than around
it.
"""

from __future__ import annotations

from typing import Iterable, Sequence

__all__ = ["blake3_256", "Blake3", "OUT_LEN", "KEY_LEN", "BLOCK_LEN", "CHUNK_LEN",
           "using_native"]

OUT_LEN = 32
KEY_LEN = 32
BLOCK_LEN = 64
CHUNK_LEN = 1024

CHUNK_START = 1 << 0
CHUNK_END = 1 << 1
PARENT = 1 << 2
ROOT = 1 << 3

MASK = 0xFFFFFFFF

IV = (0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
      0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)

MSG_PERMUTATION = (2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8)


def _rotr(value: int, count: int) -> int:
    return ((value >> count) | (value << (32 - count))) & MASK


def _g(state: list[int], a: int, b: int, c: int, d: int, mx: int, my: int) -> None:
    state[a] = (state[a] + state[b] + mx) & MASK
    state[d] = _rotr(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & MASK
    state[b] = _rotr(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b] + my) & MASK
    state[d] = _rotr(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & MASK
    state[b] = _rotr(state[b] ^ state[c], 7)


def _round(state: list[int], m: Sequence[int]) -> None:
    _g(state, 0, 4, 8, 12, m[0], m[1])       # columns
    _g(state, 1, 5, 9, 13, m[2], m[3])
    _g(state, 2, 6, 10, 14, m[4], m[5])
    _g(state, 3, 7, 11, 15, m[6], m[7])
    _g(state, 0, 5, 10, 15, m[8], m[9])      # diagonals
    _g(state, 1, 6, 11, 12, m[10], m[11])
    _g(state, 2, 7, 8, 13, m[12], m[13])
    _g(state, 3, 4, 9, 14, m[14], m[15])


def _permute(m: Sequence[int]) -> list[int]:
    return [m[MSG_PERMUTATION[i]] for i in range(16)]


def _compress(chaining_value: Sequence[int], block_words: Sequence[int],
              counter: int, block_len: int, flags: int) -> list[int]:
    state = [
        chaining_value[0], chaining_value[1], chaining_value[2], chaining_value[3],
        chaining_value[4], chaining_value[5], chaining_value[6], chaining_value[7],
        IV[0], IV[1], IV[2], IV[3],
        counter & MASK, (counter >> 32) & MASK, block_len, flags,
    ]
    block = list(block_words)
    for _ in range(6):
        _round(state, block)
        block = _permute(block)
    _round(state, block)                     # seven rounds, six permutations
    for i in range(8):
        state[i] ^= state[i + 8]
        state[i + 8] ^= chaining_value[i]
    return state


def _words_from_block(block: bytes) -> list[int]:
    return [int.from_bytes(block[i:i + 4], "little") for i in range(0, BLOCK_LEN, 4)]


class _Output:
    """A node that has not been finalized: it may become a chaining value, or the
    root, and the flags differ between those two — which is why it is a thing
    rather than a call."""

    __slots__ = ("input_chaining_value", "block_words", "counter", "block_len", "flags")

    def __init__(self, input_chaining_value, block_words, counter, block_len, flags):
        self.input_chaining_value = input_chaining_value
        self.block_words = block_words
        self.counter = counter
        self.block_len = block_len
        self.flags = flags

    def chaining_value(self) -> list[int]:
        return _compress(self.input_chaining_value, self.block_words,
                         self.counter, self.block_len, self.flags)[:8]

    def root_output_bytes(self, length: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < length:
            words = _compress(self.input_chaining_value, self.block_words,
                              counter, self.block_len, self.flags | ROOT)
            for word in words:
                out += word.to_bytes(4, "little")
                if len(out) >= length:
                    break
            counter += 1
        return bytes(out[:length])


class _ChunkState:
    __slots__ = ("chaining_value", "chunk_counter", "block", "block_len",
                 "blocks_compressed", "flags")

    def __init__(self, key_words: Sequence[int], chunk_counter: int, flags: int):
        self.chaining_value = list(key_words)
        self.chunk_counter = chunk_counter
        self.block = bytearray(BLOCK_LEN)
        self.block_len = 0
        self.blocks_compressed = 0
        self.flags = flags

    def length(self) -> int:
        return BLOCK_LEN * self.blocks_compressed + self.block_len

    def start_flag(self) -> int:
        return CHUNK_START if self.blocks_compressed == 0 else 0

    def update(self, data: bytes) -> None:
        at = 0
        while at < len(data):
            if self.block_len == BLOCK_LEN:
                self.chaining_value = _compress(
                    self.chaining_value, _words_from_block(bytes(self.block)),
                    self.chunk_counter, BLOCK_LEN,
                    self.flags | self.start_flag())[:8]
                self.blocks_compressed += 1
                self.block = bytearray(BLOCK_LEN)
                self.block_len = 0
            take = min(BLOCK_LEN - self.block_len, len(data) - at)
            self.block[self.block_len:self.block_len + take] = data[at:at + take]
            self.block_len += take
            at += take

    def output(self) -> _Output:
        return _Output(self.chaining_value, _words_from_block(bytes(self.block)),
                       self.chunk_counter, self.block_len,
                       self.flags | self.start_flag() | CHUNK_END)


def _parent_output(left: Sequence[int], right: Sequence[int],
                   key_words: Sequence[int], flags: int) -> _Output:
    return _Output(key_words, list(left) + list(right), 0, BLOCK_LEN, PARENT | flags)


class Blake3:
    """An incremental BLAKE3 hasher, unkeyed.

    Keyed hashing and key derivation are not implemented: ANLA 1.0 uses neither,
    and an unused mode is a surface with no test behind it.
    """

    __slots__ = ("chunk_state", "key_words", "cv_stack", "flags")

    def __init__(self) -> None:
        self.key_words = list(IV)
        self.flags = 0
        self.chunk_state = _ChunkState(self.key_words, 0, self.flags)
        self.cv_stack: list[list[int]] = []

    def _add_chunk_chaining_value(self, new_cv: list[int], total_chunks: int) -> None:
        # A subtree is complete exactly when its chunk count is even, so merging
        # while the low bit is clear folds the stack the same way the tree does.
        while total_chunks & 1 == 0:
            new_cv = _parent_output(self.cv_stack.pop(), new_cv,
                                    self.key_words, self.flags).chaining_value()
            total_chunks >>= 1
        self.cv_stack.append(new_cv)

    def update(self, data: bytes) -> "Blake3":
        view = memoryview(bytes(data))
        while len(view):
            if self.chunk_state.length() == CHUNK_LEN:
                chunk_cv = self.chunk_state.output().chaining_value()
                total_chunks = self.chunk_state.chunk_counter + 1
                self._add_chunk_chaining_value(chunk_cv, total_chunks)
                self.chunk_state = _ChunkState(self.key_words, total_chunks, self.flags)
            take = min(CHUNK_LEN - self.chunk_state.length(), len(view))
            self.chunk_state.update(bytes(view[:take]))
            view = view[take:]
        return self

    def digest(self, length: int = OUT_LEN) -> bytes:
        output = self.chunk_state.output()
        remaining = len(self.cv_stack)
        while remaining > 0:
            remaining -= 1
            output = _parent_output(self.cv_stack[remaining], output.chaining_value(),
                                    self.key_words, self.flags)
        return output.root_output_bytes(length)

    def hexdigest(self, length: int = OUT_LEN) -> str:
        return self.digest(length).hex()


# ---------------------------------------------------------------------------
# the fast path
# ---------------------------------------------------------------------------

try:  # pragma: no cover - depends on the environment
    import blake3 as _native

    def _native_digest(data: bytes) -> bytes:
        return _native.blake3(data).digest()

    using_native = True
except ImportError:  # pragma: no cover
    _native_digest = None
    using_native = False


def blake3_256(data: bytes) -> bytes:
    """BLAKE3, 32 bytes.

    Uses the Rust extension when it is installed. The two are asserted to agree in
    `test_blake3.py`, so which one ran is a performance question and never a
    correctness one — if that ever stops being true, the test says so before an
    archive does.
    """
    if _native_digest is not None:
        return _native_digest(data)
    return Blake3().update(data).digest()


def blake3_256_reference(data: bytes) -> bytes:
    """The pure-Python path, whatever is installed. For the cross-check."""
    return Blake3().update(data).digest()


def blake3_256_chunks(chunks: Iterable[bytes]) -> bytes:
    """Hash a sequence of pieces without joining them first."""
    hasher = Blake3()
    for piece in chunks:
        hasher.update(piece)
    return hasher.digest()
