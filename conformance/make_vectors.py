# -*- coding: utf-8 -*-
"""Regenerate the frozen conformance vectors.

    python conformance/make_vectors.py            # write vectors/ and SHA256SUMS
    python conformance/make_vectors.py --check     # verify without writing

Only the reproducible cases become vectors: a vector whose bytes depend on which
DEFLATE encoder produced it could not be frozen, and freezing it anyway would
make a third implementation fail a test it should pass.

`browser-interop-v0.1.anla` is not generated. It is the archive the original v0.1
browser release shipped, kept as a read-compatibility vector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "python"))
sys.path.insert(0, str(REPO / "python" / "tests"))

from anla import open_archive  # noqa: E402
from conftest import CASES, TREES, build_tree  # noqa: E402
from anla import pack  # noqa: E402

VECTORS = HERE / "vectors"
SUMS = VECTORS / "SHA256SUMS"
NOT_GENERATED = ("browser-interop-v0.1.anla",)
HEADER = (
    "# Frozen ANLA-MVP v0.1 conformance vectors.\n"
    "# Regenerate with: python conformance/make_vectors.py\n"
    "# browser-interop-v0.1.anla is not generated — it is the archive the\n"
    "# original v0.1 browser release shipped, kept as a read-compatibility vector.\n"
)


def build() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for case in CASES:
        if not case.byte_exact:
            continue
        tree = build_tree(TREES[case.tree_name])
        result = pack(tree, case.plan, archive_uuid=case.archive_uuid,
                      created_ns=case.created_ns)
        # A vector nobody can read is not a vector.
        open_archive(result.data, full=True)
        out[f"{case.id}.anla"] = result.data
    return out


def sums_text(vectors: dict[str, bytes]) -> str:
    lines = [HEADER]
    for name in sorted([*vectors, *NOT_GENERATED]):
        data = vectors.get(name) or (VECTORS / name).read_bytes()
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed vectors differ")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    vectors = build()
    VECTORS.mkdir(parents=True, exist_ok=True)
    report = {"generated": [], "unchanged": [], "differs": [], "missing": []}

    for name, data in sorted(vectors.items()):
        target = VECTORS / name
        if target.exists() and target.read_bytes() == data:
            report["unchanged"].append(name)
            continue
        if args.check:
            report["differs" if target.exists() else "missing"].append(name)
            continue
        target.write_bytes(data)
        report["generated"].append(name)

    expected_sums = sums_text(vectors)
    if args.check:
        actual = SUMS.read_text(encoding="utf-8") if SUMS.exists() else ""
        if actual != expected_sums:
            report["differs"].append("SHA256SUMS")
    else:
        SUMS.write_text(expected_sums, encoding="utf-8", newline="\n")

    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for key in ("generated", "unchanged", "differs", "missing"):
            if report[key]:
                print(f"{key}: {', '.join(report[key])}")

    if report["differs"] or report["missing"]:
        print("frozen vectors do not match the current writer", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
