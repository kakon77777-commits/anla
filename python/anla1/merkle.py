# -*- coding: utf-8 -*-
"""The Merkle construction ANLA 1.0's roots are computed with.

Whitepaper open question 6 asked one root or several. Several — and once that is
decided, *how* the tree is built stops being an implementation detail and becomes
part of the format, for the same reason the gear table did: two implementations
that build the tree differently compute different roots for identical content, and
the disagreement is invisible until someone compares two archives.

So it is pinned, and three choices in it are load-bearing.

**Domain separation.** A leaf is hashed as `H(0x00 || data)` and an internal node
as `H(0x01 || left || right)`. Without the prefixes an attacker can present an
internal node as a leaf: a tree over two leaves and a tree over one leaf whose
"data" happens to be `left || right` produce the same root, so a proof for one is a
proof for the other. This is the classic Merkle second-preimage attack, and one
byte per hash is what it costs to close.

**Odd nodes are promoted, never duplicated.** With an odd count the last node moves
up a level unchanged. Duplicating it instead — Bitcoin's original choice — makes two
different leaf lists produce the same root (CVE-2012-2459). The promotion rule has
no such collision, and the test suite here asserts the collision is absent rather
than trusting that.

**The empty tree has a defined root**, `H(0x02)`, rather than being an error or a
zero. Empty is a legitimate state — an archive with no metadata namespaces, a
snapshot with no intelligence plane — and a construction with no answer for it
invites each implementation to invent one.

Leaf *order* is not decided here. It is the caller's, because the ordering rule
belongs to what is being hashed: objects sort by `object_id`, chunks by `chunk_id`,
and both are specified where those live.
"""

from __future__ import annotations

from typing import Callable, Sequence

from anla.errors import InvalidInput

__all__ = ["LEAF_PREFIX", "NODE_PREFIX", "EMPTY_PREFIX",
           "leaf_hash", "node_hash", "empty_root", "merkle_root", "merkle_path",
           "verify_path"]

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
EMPTY_PREFIX = b"\x02"

Hasher = Callable[[bytes], bytes]


def leaf_hash(data: bytes, hasher: Hasher) -> bytes:
    return hasher(LEAF_PREFIX + data)


def node_hash(left: bytes, right: bytes, hasher: Hasher) -> bytes:
    return hasher(NODE_PREFIX + left + right)


def empty_root(hasher: Hasher) -> bytes:
    return hasher(EMPTY_PREFIX)


def merkle_root(leaves: Sequence[bytes], hasher: Hasher, *, hashed: bool = False) -> bytes:
    """The root over *leaves*, in the order given.

    With ``hashed=False`` the entries are raw data and are leaf-hashed here. With
    ``hashed=True`` they are already leaf hashes — used when a caller has to hold
    the leaves for other reasons and should not hash them twice.
    """
    if not leaves:
        return empty_root(hasher)
    level = list(leaves) if hashed else [leaf_hash(entry, hasher) for entry in leaves]
    if hashed:
        width = len(level[0])
        if any(len(entry) != width for entry in level):
            raise InvalidInput("pre-hashed leaves are not all the same width")
    while len(level) > 1:
        nxt = []
        for index in range(0, len(level) - 1, 2):
            nxt.append(node_hash(level[index], level[index + 1], hasher))
        if len(level) % 2:
            # Promoted, not duplicated. Duplicating makes two different leaf lists
            # share a root; see the module docstring.
            nxt.append(level[-1])
        level = nxt
    return level[0]


def merkle_path(leaves: Sequence[bytes], index: int, hasher: Hasher,
                *, hashed: bool = False) -> list[tuple[str, bytes]]:
    """An inclusion proof for ``leaves[index]``: ``[("left"|"right", sibling), …]``.

    Present because a root nobody can produce a proof against is only a checksum.
    Partial materialization — extracting a few objects without reading the rest —
    needs to show that what it extracted belongs to the snapshot it claims.
    """
    if not 0 <= index < len(leaves):
        raise InvalidInput("leaf index out of range", index=index, leaves=len(leaves))
    level = list(leaves) if hashed else [leaf_hash(entry, hasher) for entry in leaves]
    path: list[tuple[str, bytes]] = []
    at = index
    while len(level) > 1:
        pairs = len(level) // 2
        nxt = []
        for pair in range(pairs):
            left, right = level[2 * pair], level[2 * pair + 1]
            if at == 2 * pair:
                path.append(("right", right))
            elif at == 2 * pair + 1:
                path.append(("left", left))
            nxt.append(node_hash(left, right, hasher))
        if len(level) % 2:
            # The odd node is promoted unchanged, so it has no sibling at this
            # level and contributes no path step. It lands at the end of the next
            # level, which is index `pairs`.
            nxt.append(level[-1])
        at = at // 2 if at < 2 * pairs else pairs
        level = nxt
    return path


def verify_path(leaf: bytes, path: Sequence[tuple[str, bytes]], root: bytes,
                hasher: Hasher, *, hashed: bool = False) -> bool:
    """True when *leaf* with *path* reproduces *root*."""
    current = leaf if hashed else leaf_hash(leaf, hasher)
    for side, sibling in path:
        if side == "right":
            current = node_hash(current, sibling, hasher)
        elif side == "left":
            current = node_hash(sibling, current, hasher)
        else:
            raise InvalidInput("path step is neither left nor right", side=side)
    return current == root
