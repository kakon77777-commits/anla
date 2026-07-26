# -*- coding: utf-8 -*-
"""The exclusion glob dialect (SPEC.md section 8.3).

Deliberately not :mod:`fnmatch`: fnmatch's ``*`` crosses ``/``, which would make
``.git/*`` mean something different here than it does in the JavaScript writer,
and the two writers must agree on which objects were declared into an archive.
"""

from __future__ import annotations

import re

__all__ = ["glob_to_regex", "matches_any"]

_SPECIAL = set(".+^$(){}[]|\\")


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translate one exclusion pattern to an anchored regular expression.

    ``**`` matches any run of characters including ``/``; ``*`` matches any run
    except ``/``; ``?`` matches exactly one character except ``/``; every other
    character is literal.
    """
    out: list[str] = ["^"]
    i = 0
    n = len(glob)
    while i < n:
        ch = glob[i]
        if ch == "*":
            if i + 1 < n and glob[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch in _SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(re.escape(ch) if not ch.isalnum() else ch)
        i += 1
    out.append("$")
    return re.compile("".join(out), re.DOTALL)


def matches_any(path: str, globs: object) -> bool:
    """True when *path* matches any pattern in *globs*."""
    return any(glob_to_regex(g).match(path) is not None for g in globs or ())
