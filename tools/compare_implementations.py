# -*- coding: utf-8 -*-
"""Assert the Python and Rust readers restore the same bytes.

    python tools/compare_implementations.py <archive> <rust-extract.json>

`anla1-rs extract` prints a BLAKE3 per path rather than the bytes, so the comparison
does not depend on how either side happens to serialise content — and a digest that
matches is a stronger statement than two files that look alike.

What this is for: the freeze rule at the top of `SPEC-1.0-DRAFT.md` needs two
independent implementations agreeing, and "agreeing" has to mean something checkable.
Verifying the same archive is the weaker half — both readers could be wrong in the
same way and both say `ok`. Restoring the same bytes for every path is the half that
would notice.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from anla1 import container as C  # noqa: E402
from anla1.snapshot import extract_snapshot, list_snapshots  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.splitlines()[2].strip(), file=sys.stderr)
        return 2
    archive, rust_output = Path(argv[0]), Path(argv[1])

    data = archive.read_bytes()
    snapshot = list_snapshots(data)[-1]
    python_side = {
        path: C.hash_bytes(content, snapshot.hash_algorithm).hex()
        for path, content in extract_snapshot(data, snapshot).items()
    }
    rust_side = {
        row["path"]: row["blake3"]
        for row in json.loads(rust_output.read_text(encoding="utf-8"))["files"]
    }

    only_python = sorted(set(python_side) - set(rust_side))
    only_rust = sorted(set(rust_side) - set(python_side))
    differing = sorted(
        path for path in set(python_side) & set(rust_side)
        if python_side[path] != rust_side[path]
    )

    if not python_side:
        # An empty comparison agrees with everything. This is the shape that has
        # caught this project out more than any other, so it fails rather than
        # passes.
        print("the archive restored no files, so nothing was compared", file=sys.stderr)
        return 1
    if only_python or only_rust or differing:
        print(f"only python: {only_python}", file=sys.stderr)
        print(f"only rust:   {only_rust}", file=sys.stderr)
        print(f"differing:   {differing}", file=sys.stderr)
        return 1

    print(f"two implementations, {len(python_side)} files, every BLAKE3 identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
