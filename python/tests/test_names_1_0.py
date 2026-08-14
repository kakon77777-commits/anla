# -*- coding: utf-8 -*-
"""Names that are not UTF-8 — whitepaper Q4, `design/q4-name-model.md`.

A POSIX filename is an arbitrary byte string and a Windows filename is a UTF-16
sequence that may hold unpaired surrogates. Neither is "a UTF-8 string", and the
manifest's `path` is CBOR text, which must be. So there are real filenames with no
`path`, and this file is about what happens to them.

What used to happen was a `UnicodeEncodeError` from inside a sort key, four layers
below the caller. These tests exist so that stays fixed, and so it stays fixed at
*every* entrance rather than the one that was reported.
"""

from __future__ import annotations

import json

import pytest

from anla.errors import UnsafeObject
from anla1.manifest import ObjectEntry, check_object_path, sorted_by_path
from anla1.snapshot import SourceEntry, append_snapshot

#: What `os.listdir` hands you on Linux for a file whose name is latin-1 `café.txt`.
#: Python represents the undecodable byte as the lone surrogate U+DCE9, which is a
#: `str` that cannot be encoded back to UTF-8 — the whole difficulty in one value.
LATIN1_NAME = b"caf\xe9.txt".decode("utf-8", "surrogateescape")


def pack(**kwargs):
    return append_snapshot(b"", created_unix_ns=1, archive_id=bytes(16), **kwargs)


def test_the_name_really_is_unencodable():
    """The premise, asserted rather than assumed.

    Without this, every test below would pass just as happily against a name that
    encodes fine, and the file would prove nothing.
    """
    with pytest.raises(UnicodeEncodeError):
        LATIN1_NAME.encode("utf-8")
    assert LATIN1_NAME.encode("utf-8", "surrogateescape") == b"caf\xe9.txt"


def test_check_object_path_refuses_what_it_cannot_encode():
    with pytest.raises(UnsafeObject, match="cannot be encoded"):
        check_object_path(LATIN1_NAME)


@pytest.mark.parametrize("kwargs", [
    {"files": [SourceEntry.of(LATIN1_NAME, b"x")]},
    {"files": [], "directories": [LATIN1_NAME]},
    {"files": [], "objects": [ObjectEntry(kind="symbolic-link", path=LATIN1_NAME,
                                          target=b"elsewhere")]},
])
def test_every_way_in_refuses_rather_than_crashes(kwargs):
    """Three entrances, one answer.

    The first version of this fix repaired the file path only, and directories still
    crashed — a different sort key, the same defect. Parametrising by entrance is
    what makes the next entrance someone adds fail here instead of in production.
    """
    with pytest.raises(UnsafeObject, match="cannot be encoded"):
        pack(**kwargs)


def test_the_refusal_can_itself_be_reported():
    """An error report that crashes is worse than the error it was reporting.

    The CLI serialises `as_dict()` with `ensure_ascii=False` (cli.py:459), so a
    detail field holding the raw surrogate would raise `UnicodeEncodeError` inside
    the error handler — the same defect one level up, and this time with nothing
    left to catch it. `ascii()`-escaping the path at the point of refusal is what
    keeps that from happening, and it costs the reader nothing: they see
    `'caf\\udce9.txt'`, which is exactly what they need to find the file.
    """
    with pytest.raises(UnsafeObject) as caught:
        check_object_path(LATIN1_NAME)
    assert "udce9" in caught.value.details["path"]

    payload = json.dumps(caught.value.as_dict(), ensure_ascii=False)
    payload.encode("utf-8")  # what the CLI does to stderr; raises if the escape is gone


def test_the_check_lives_in_the_ordering_helper_not_the_call_sites():
    """The class, not the instance.

    Five separate sort keys encoded a path for ordering and all five assumed it was
    encodable. `sorted_by_path` is the one operation they now share, so a sixth call
    site inherits the check instead of repeating the bug.
    """
    with pytest.raises(UnsafeObject, match="cannot be encoded"):
        sorted_by_path([LATIN1_NAME], lambda p: p)
    # And it is genuinely an ordering helper, not just a validator: SPEC §5.2.1
    # orders by UTF-8 *bytes*, which is not Python's default string order.
    assert sorted_by_path(["Z", "a", "B"], lambda p: p) == ["B", "Z", "a"]


def test_names_that_are_utf_8_are_untouched():
    """The negative control.

    A check that refuses everything also passes every test above. These are names
    that look awkward and are perfectly legal, and they must still pack.
    """
    fine = ["中文.txt", "emoji-🌏.bin", "espaćo.txt", "a b\tc.txt"]
    archive = pack(files=[SourceEntry.of(name, b"x") for name in fine])
    assert len(archive) > 0
    for name in fine:
        assert check_object_path(name) == name
