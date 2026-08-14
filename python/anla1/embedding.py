# -*- coding: utf-8 -*-
"""Embedding identity: when two vectors are comparable, and when they are not.

Two vectors of the same width can come from different models, different revisions
of one model, or the same model with different preprocessing — and cosine will
return a confident number for any of them. That number is meaningless and nothing
downstream can tell. Width is not identity.

So a vector carries the identity of what produced it, comparison checks that
identity, and a mismatch is **INCOMPARABLE** rather than a number. This is ICNS's
rule — a comparison must be allowed to fail rather than be rounded to an answer —
applied to the one channel in this system that has no independent check on whether
it is right.

`projection_version` is the part that is easy to leave out and expensive to omit.
Two runs of the same model on the same text give different vectors if one lowercased
and the other did not, or one truncated at 1,200 characters and the other at 2,000,
or one embedded the extracted text and the other the raw bytes. That is not the
model's identity, it is the *pipeline's*, and it belongs in the identity for exactly
the same reason.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

__all__ = ["EmbeddingIdentity", "INCOMPARABLE", "comparable"]

#: The verdict when two vectors cannot honestly be compared. Not an exception and
#: not zero similarity: a caller has to be able to distinguish "these are unrelated"
#: from "this question cannot be answered", and a 0.0 conflates them.
INCOMPARABLE = "INCOMPARABLE"


@dataclass(frozen=True)
class EmbeddingIdentity:
    """Everything that has to match before two vectors may be compared.

    `segmentation_scheme` is here because a vector is `E_θ(π_σ(m))`, not `E_θ(m)`:
    the same model over the same memory under two different index schemes produces
    two different vectors, and comparing them silently compares two views rather
    than two memories.
    """

    model: str
    dimensions: int
    #: The model's own version, when the provider exposes one. Providers do change
    #: weights behind a stable name, and a vector produced before such a change is
    #: not comparable with one produced after it — `unstated` records that we do
    #: not know rather than implying stability.
    revision: str = "unstated"
    #: How the text was prepared before the model saw it.
    projection_version: str = "unstated"
    #: Which index scheme produced the view that was embedded.
    segmentation_scheme: str = "unstated"
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"model": self.model, "dimensions": self.dimensions,
                "revision": self.revision,
                "projection_version": self.projection_version,
                "segmentation_scheme": self.segmentation_scheme,
                **({"extra": self.extra} if self.extra else {})}

    @property
    def fingerprint(self) -> str:
        """A short stable digest of the whole identity, for storing beside vectors.

        Compared instead of the fields one at a time so that adding a field later
        cannot produce a pair that passes the check because nothing looked at the
        new field.
        """
        parts = "\x1f".join([
            self.model, str(self.dimensions), self.revision,
            self.projection_version, self.segmentation_scheme,
            repr(sorted(self.extra.items())),
        ])
        return hashlib.blake2b(parts.encode("utf-8"), digest_size=8).hexdigest()

    @classmethod
    def of(cls, payload: dict) -> "EmbeddingIdentity":
        return cls(
            model=str(payload.get("model") or "unstated"),
            dimensions=int(payload.get("dimensions") or 0),
            revision=str(payload.get("revision") or "unstated"),
            projection_version=str(payload.get("projection_version") or "unstated"),
            segmentation_scheme=str(payload.get("segmentation_scheme") or "unstated"),
            extra=dict(payload.get("extra") or {}),
        )


def comparable(a: EmbeddingIdentity, b: EmbeddingIdentity) -> tuple[bool, str]:
    """May these two be compared? If not, say which field disagreed.

    Returns `(True, "")` or `(False, reason)`. The reason is not decoration: a
    caller told only `INCOMPARABLE` will re-embed the wrong side of the pair.
    """
    if a.fingerprint == b.fingerprint:
        return True, ""
    for field_name in ("model", "dimensions", "revision", "projection_version",
                       "segmentation_scheme"):
        left, right = getattr(a, field_name), getattr(b, field_name)
        if left != right:
            return False, (f"{INCOMPARABLE}: {field_name} differs — "
                           f"{left!r} against {right!r}")
    if a.extra != b.extra:
        return False, f"{INCOMPARABLE}: extra metadata differs"
    return False, f"{INCOMPARABLE}: identities differ"
