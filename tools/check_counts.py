# -*- coding: utf-8 -*-
"""Every published test count must equal the number of tests that exist.

    python tools/check_counts.py
    python tools/check_counts.py --fix

The count appears on the landing page, in the README, and in both languages of the
site copy. It has been hand-edited four times in one day and was wrong on the
landing page by a factor of three the whole time — 201 where the suite had grown to
603 — which is the sort of number a reader checks first and trusts least afterwards.

So it is checked rather than remembered. `--fix` rewrites the stale ones, which
makes the check cheap enough to keep passing and removes the excuse for a number
that "will be updated later".
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Every place a total test count is published, with the pattern that finds it.
#: A new place to say it is a new line here — a published number with no entry is
#: a number nobody is checking.
SITES = (
    (ROOT / "README.md", re.compile(r"\b(\d{3,5}) tests\b")),
    (ROOT / "site" / "src" / "content.py", re.compile(r'"fact_tests_v": "(\d{3,5})')),
    (ROOT / "site" / "src" / "content.py", re.compile(r'"fact_tests_v": "(\d{3,5}) 項')),
)


def collected() -> int:
    """How many tests pytest actually collects, asked of pytest."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "python/tests", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True)
    # Two shapes, depending on the pytest version and whether `-q` is already in
    # addopts: a single "N tests collected" line, or one "path.py: N" line per file
    # and no total at all. Summing the per-file lines is not a fallback that guesses
    # — it is the same number, arrived at from the same output.
    total = re.search(r"^(\d+) tests? collected", result.stdout, re.M)
    if total:
        return int(total.group(1))
    per_file = re.findall(r"^\S+\.py: (\d+)$", result.stdout, re.M)
    if per_file:
        return sum(int(n) for n in per_file)
    print(result.stdout[-2000:], file=sys.stderr)
    raise SystemExit("could not read a collected count out of pytest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fix", action="store_true", help="rewrite stale counts")
    args = parser.parse_args(argv)

    total = collected()
    stale: list[str] = []
    for path, pattern in SITES:
        text = path.read_text(encoding="utf-8")
        found = pattern.findall(text)
        if not found:
            stale.append(f"{path.relative_to(ROOT)}: no count matched {pattern.pattern}")
            continue
        for value in found:
            if int(value) == total:
                continue
            where = f"{path.relative_to(ROOT)}: says {value}, suite has {total}"
            if args.fix:
                text = pattern.sub(
                    lambda m: m.group(0).replace(m.group(1), str(total)), text)
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"fixed  {where}")
            else:
                stale.append(where)

    if stale:
        for line in stale:
            print(line, file=sys.stderr)
        print("\nrun `python tools/check_counts.py --fix`", file=sys.stderr)
        return 1
    print(f"every published test count says {total}, which is how many there are")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
