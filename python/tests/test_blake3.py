# -*- coding: utf-8 -*-
"""BLAKE3-256 — the core hash of ANLA 1.0.

Two implementations again, for the same reason as everywhere else in this project:
a pure-Python reference anyone can read against the specification, and the Rust
extension for anything larger than a test. The tests that matter are the ones
asserting they agree, and the ones at 1024-byte boundaries — BLAKE3 is a tree over
1024-byte chunks, so a tree-logic bug is invisible below the first boundary and
wrong at every length above it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla1.blake3 import (  # noqa: E402
    CHUNK_LEN,
    Blake3,
    blake3_256,
    blake3_256_chunks,
    blake3_256_reference,
    using_native,
)

native = pytest.importorskip("blake3", reason="the Rust extension is the oracle here")


def pattern(length: int) -> bytes:
    """The BLAKE3 test-vector filler: bytes 0..250 repeating."""
    return bytes(i % 251 for i in range(length))


# ---------------------------------------------------------------------------
# published values
# ---------------------------------------------------------------------------

def test_the_empty_input_matches_the_published_value():
    """The most widely published BLAKE3 value there is; if this is wrong, nothing
    below matters."""
    assert blake3_256_reference(b"").hex() == \
        "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"


def test_abc_matches_the_published_value():
    assert blake3_256_reference(b"abc").hex() == \
        "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"


# ---------------------------------------------------------------------------
# the cross-check that makes both implementations worth having
# ---------------------------------------------------------------------------

BOUNDARIES = [
    0, 1, 2, 3, 31, 32, 63, 64, 65, 127, 128, 129, 255, 256,
    1023, 1024, 1025,               # the chunk boundary, where tree logic starts
    2047, 2048, 2049,               # two chunks
    3071, 3072, 3073,               # three: the odd-subtree case
    4095, 4096, 4097,
    6144, 8191, 8192, 8193,
    16384, 16385, 31744,
]


@pytest.mark.parametrize("length", BOUNDARIES)
def test_the_reference_agrees_with_the_rust_extension(length):
    data = pattern(length)
    assert blake3_256_reference(data) == native.blake3(data).digest(), length


def test_they_agree_on_random_lengths_too():
    """Boundaries are where bugs hide, but not the only place they live."""
    import random
    rng = random.Random(20260728)
    for _ in range(60):
        data = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 5000)))
        assert blake3_256_reference(data) == native.blake3(data).digest()


def test_the_dispatching_helper_matches_both():
    for length in (0, 100, 1024, 5000):
        data = pattern(length)
        assert blake3_256(data) == native.blake3(data).digest()
        assert blake3_256(data) == blake3_256_reference(data)


def test_the_native_path_is_the_one_in_use_here():
    """Not an assertion about correctness — about which path this run exercised, so
    a green suite on a machine without the extension is not mistaken for one with
    it."""
    assert using_native is True


# ---------------------------------------------------------------------------
# incremental use
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("split", [1, 7, 63, 64, 65, 512, 1023, 1024, 1025, 4096])
def test_feeding_in_pieces_gives_the_same_digest(split):
    data = pattern(9000)
    pieces = [data[i:i + split] for i in range(0, len(data), split)]
    assert blake3_256_chunks(pieces) == blake3_256_reference(data), split


def test_an_empty_update_changes_nothing():
    hasher = Blake3()
    hasher.update(b"")
    hasher.update(b"abc")
    hasher.update(b"")
    assert hasher.digest() == blake3_256_reference(b"abc")


def test_update_returns_the_hasher_so_it_chains():
    assert Blake3().update(b"a").update(b"bc").digest() == blake3_256_reference(b"abc")


def test_hexdigest_matches_digest():
    hasher = Blake3().update(pattern(2000))
    assert hasher.hexdigest() == hasher.digest().hex()


# ---------------------------------------------------------------------------
# extendable output
# ---------------------------------------------------------------------------

def test_longer_output_extends_rather_than_replaces():
    """BLAKE3 is an XOF: 64 bytes of output begins with the same 32 bytes. ANLA
    only ever asks for 32, but a reference that quietly disagreed with the real
    algorithm here would be wrong in a way no ANLA test would catch."""
    data = pattern(1500)
    long_output = Blake3().update(data).digest(64)
    assert long_output[:32] == blake3_256_reference(data)
    assert long_output == native.blake3(data).digest(length=64)


def test_output_lengths_that_cross_a_block():
    data = b"cross the 64-byte output block"
    for length in (1, 31, 32, 33, 63, 64, 65, 131):
        assert Blake3().update(data).digest(length) \
            == native.blake3(data).digest(length=length), length


# ---------------------------------------------------------------------------
# the property the tree is for
# ---------------------------------------------------------------------------

def test_a_single_flipped_bit_changes_everything():
    a = pattern(CHUNK_LEN * 3)
    b = bytearray(a)
    b[CHUNK_LEN * 2 + 7] ^= 0x01
    first, second = blake3_256_reference(a), blake3_256_reference(bytes(b))
    assert first != second
    differing_bits = sum(bin(x ^ y).count("1") for x, y in zip(first, second))
    # An avalanche, not a local edit: roughly half the bits should move.
    assert 96 <= differing_bits <= 160, differing_bits


def test_length_extension_does_not_apply():
    """Appending to the input is not a small change to the digest, which is the
    property a Merkle-Damgård hash lacks and this one has."""
    base = pattern(1024)
    assert blake3_256_reference(base) != blake3_256_reference(base + b"\x00")
