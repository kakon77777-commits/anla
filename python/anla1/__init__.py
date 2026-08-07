# -*- coding: utf-8 -*-
"""ANLA 1.0 — the draft profile, specified in `SPEC-1.0-DRAFT.md`.

Separate from :mod:`anla`, which is the frozen `ANLA-MVP v0.1` profile, because the
two are different container formats with different magic numbers. They share an
error vocabulary and a path-safety rule and nothing else; neither reads the other's
archives, and both refuse to try.

**Nothing here is frozen.** The freeze rule is written into the specification: no
part of 1.0 is final until two independent implementations produce byte-identical
archives from the same input and a differential fuzzer finds no verdict divergence
between them. There is one implementation. `SPEC-1.0-DRAFT.md` opens with a table of
exactly what exists.
"""

from __future__ import annotations

#: Not a release version. The draft's own identifier, which changes when the bytes
#: change — and which will be replaced by a real version at the freeze, not before.
__profile__ = "ANLA 1.0 (draft)"
__draft__ = "2026-08-07"

__all__ = ["__profile__", "__draft__"]
