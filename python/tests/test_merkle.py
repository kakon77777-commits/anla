# -*- coding: utf-8 -*-
"""The Merkle construction — SPEC-1.0-DRAFT.md §5.3.

Three of these tests are the reason the construction is pinned rather than left to
each implementation: domain separation, odd-node promotion, and a defined empty
root. Each closes a hole that a plausible alternative construction leaves open, and
two of those holes have CVE numbers attached to them in other projects.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import InvalidInput  # noqa: E402
from anla1.merkle import (  # noqa: E402
    EMPTY_PREFIX,
    LEAF_PREFIX,
    NODE_PREFIX,
    empty_root,
    leaf_hash,
    merkle_path,
    merkle_root,
    node_hash,
    verify_path,
)


def H(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaves(count: int) -> list[bytes]:
    return [f"leaf-{i}".encode() for i in range(count)]


# ---------------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------------

def test_the_empty_tree_has_a_defined_root():
    """Empty is a legitimate state — no metadata namespaces, no intelligence
    plane — and a construction with no answer for it invites each implementation to
    invent one."""
    assert merkle_root([], H) == H(EMPTY_PREFIX)
    assert empty_root(H) == H(EMPTY_PREFIX)


def test_one_leaf_is_its_leaf_hash():
    assert merkle_root([b"only"], H) == leaf_hash(b"only", H)


def test_two_leaves_are_one_node():
    a, b = b"a", b"b"
    assert merkle_root([a, b], H) == node_hash(leaf_hash(a, H), leaf_hash(b, H), H)


def test_three_leaves_promote_the_odd_one():
    a, b, c = leaves(3)
    expected = node_hash(node_hash(leaf_hash(a, H), leaf_hash(b, H), H),
                         leaf_hash(c, H), H)
    assert merkle_root([a, b, c], H) == expected


@pytest.mark.parametrize("count", list(range(0, 33)) + [64, 65, 100, 1000])
def test_any_count_produces_one_root(count):
    root = merkle_root(leaves(count), H)
    assert isinstance(root, bytes) and len(root) == 32


def test_order_matters():
    a, b = leaves(2)
    assert merkle_root([a, b], H) != merkle_root([b, a], H)


def test_pre_hashed_leaves_give_the_same_root():
    entries = leaves(7)
    assert merkle_root(entries, H) == merkle_root(
        [leaf_hash(e, H) for e in entries], H, hashed=True)


def test_pre_hashed_leaves_of_mixed_width_are_refused():
    with pytest.raises(InvalidInput, match="same width"):
        merkle_root([b"\x00" * 32, b"\x00" * 16], H, hashed=True)


# ---------------------------------------------------------------------------
# the three load-bearing choices
# ---------------------------------------------------------------------------

def test_a_leaf_cannot_be_confused_with_an_internal_node():
    """Domain separation, and the attack it closes.

    Without the prefixes, a tree over two leaves and a tree over one leaf whose
    data happens to be `left || right` have the same root — so a proof for one is a
    proof for the other. One byte per hash is what it costs to close.
    """
    a, b = b"left-side", b"right-side"
    two_leaf_root = merkle_root([a, b], H)
    forged_single_leaf = leaf_hash(a, H) + leaf_hash(b, H)
    assert merkle_root([forged_single_leaf], H) != two_leaf_root

    # And the prefixes really are what separates them: without domain separation
    # the two constructions collide.
    undomained_node = H(leaf_hash(a, H) + leaf_hash(b, H))
    assert undomained_node != two_leaf_root
    assert LEAF_PREFIX != NODE_PREFIX != EMPTY_PREFIX


def test_promotion_does_not_collide_the_way_duplication_does():
    """CVE-2012-2459 in one assertion.

    Bitcoin duplicated the odd node, which makes [a, b, c] and [a, b, c, c] produce
    the same root — two different leaf lists, one root. Promotion has no such
    collision.
    """
    a, b, c = leaves(3)
    assert merkle_root([a, b, c], H) != merkle_root([a, b, c, c], H)

    # Spelled out: the duplicating construction *would* collide, which is why this
    # one does not duplicate.
    def duplicating_root(entries):
        level = [leaf_hash(e, H) for e in entries]
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])
            level = [node_hash(level[i], level[i + 1], H) for i in range(0, len(level), 2)]
        return level[0]

    assert duplicating_root([a, b, c]) == duplicating_root([a, b, c, c])


def test_appending_a_duplicate_leaf_changes_the_root():
    entries = leaves(5)
    assert merkle_root(entries, H) != merkle_root(entries + [entries[-1]], H)


def test_a_different_hash_gives_a_different_root():
    """The construction is hash-agnostic, which is what lets BLAKE3 land later
    without touching this file."""
    entries = leaves(6)
    sha = merkle_root(entries, H)
    sha512 = merkle_root(entries, lambda d: hashlib.sha512(d).digest())
    assert len(sha) == 32 and len(sha512) == 64 and sha != sha512[:32]


# ---------------------------------------------------------------------------
# inclusion proofs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8, 9, 16, 17, 31, 32])
def test_every_leaf_has_a_working_inclusion_proof(count):
    entries = leaves(count)
    root = merkle_root(entries, H)
    for index, entry in enumerate(entries):
        path = merkle_path(entries, index, H)
        assert verify_path(entry, path, root, H), f"{index} of {count}"


def test_a_proof_for_the_wrong_leaf_fails():
    entries = leaves(8)
    root = merkle_root(entries, H)
    path = merkle_path(entries, 3, H)
    assert verify_path(entries[3], path, root, H)
    assert not verify_path(entries[4], path, root, H)


def test_a_tampered_proof_fails():
    entries = leaves(8)
    root = merkle_root(entries, H)
    path = merkle_path(entries, 2, H)
    tampered = [(side, bytes(32)) for side, _ in path]
    assert not verify_path(entries[2], tampered, root, H)


def test_a_proof_with_a_flipped_side_fails():
    entries = leaves(4)
    root = merkle_root(entries, H)
    path = merkle_path(entries, 1, H)
    flipped = [("left" if side == "right" else "right", sibling) for side, sibling in path]
    assert not verify_path(entries[1], flipped, root, H)


def test_an_out_of_range_index_is_refused():
    with pytest.raises(InvalidInput, match="out of range"):
        merkle_path(leaves(4), 4, H)
    with pytest.raises(InvalidInput, match="out of range"):
        merkle_path(leaves(4), -1, H)


def test_a_nonsense_path_step_is_refused():
    with pytest.raises(InvalidInput, match="neither left nor right"):
        verify_path(b"x", [("sideways", bytes(32))], bytes(32), H)


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_the_construction_is_pinned_to_published_values():
    """Three fixed points, so a third implementation can check itself against
    numbers rather than against our code.

    Written out rather than computed in the assertion: a test that recomputes what
    it is checking passes whatever the construction does, which is how a pinned
    value stops being pinned.
    """
    assert merkle_root([], H).hex() == \
        "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986"
    assert merkle_root([b"a"], H).hex() == \
        "022a6979e6dab7aa5ae4c3e5e45f7e977112a7e63593820dbec1ec738a24f93c"
    assert merkle_root([b"a", b"b", b"c"], H).hex() == \
        "36642e73c2540ab121e3a6bf9545b0a24982cd830eb13d3cd19de3ce6c021ec1"
