# -*- coding: utf-8 -*-
"""Canonical JSON, exactly as SPEC.md section 6 defines it.

The whole point of this module is that two independent implementations must
produce identical bytes for the same logical structure, because the manifest
hash in the footer is computed over those bytes. So it is written out longhand
rather than delegating to ``json.dumps(sort_keys=True, separators=...)``: the
latter would work today, but it leaves the number and escaping rules implicit,
and those are the rules the JavaScript side has to match.
"""

from __future__ import annotations

import json

__all__ = ["canonical", "canonical_bytes", "CanonicalJSONError", "MAX_SAFE_INT"]

MAX_SAFE_INT = 2 ** 53 - 1


class CanonicalJSONError(ValueError):
    """A value cannot be represented in the canonical JSON profile."""


def _string(value: str) -> str:
    # json.dumps with ensure_ascii=False escapes exactly the set the spec
    # requires: the quote, the backslash, and the C0 controls (short forms
    # where they exist, \u00XX otherwise). Everything else, including all
    # non-ASCII, is emitted literally as UTF-8 — same as JSON.stringify.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:  # lone surrogates, e.g. from os.listdir
        raise CanonicalJSONError(
            f"string is not encodable as UTF-8 and cannot be canonicalized: {value!r}"
        ) from exc
    return json.dumps(value, ensure_ascii=False)


def canonical(value) -> str:
    """Serialize *value* to a canonical JSON string."""
    # bool before int: isinstance(True, int) is True in Python.
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        raise CanonicalJSONError("null is not used by ANLA-MVP v0.1")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        if not -MAX_SAFE_INT <= value <= MAX_SAFE_INT:
            raise CanonicalJSONError(
                f"integer {value} is outside the safe range; carry it as a decimal string"
            )
        return str(value)
    if isinstance(value, float):
        raise CanonicalJSONError("floating point numbers must not appear in an archive")
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = list(value.keys())
        for key in keys:
            if not isinstance(key, str):
                raise CanonicalJSONError(f"object keys must be strings, got {type(key).__name__}")
        if len(set(keys)) != len(keys):
            raise CanonicalJSONError("duplicate object key")
        # sorted() on str orders by Unicode code point, which is what the spec
        # requires. All keys in this profile are ASCII, where code-point order
        # and UTF-16 code-unit order (JavaScript's default sort) agree.
        return "{" + ",".join(f"{_string(k)}:{canonical(value[k])}" for k in sorted(keys)) + "}"
    raise CanonicalJSONError(f"type {type(value).__name__} has no canonical JSON form")


def canonical_bytes(value) -> bytes:
    """Serialize *value* to canonical JSON encoded as UTF-8."""
    return canonical(value).encode("utf-8")
