# -*- coding: utf-8 -*-
"""Assert that both BLAKE3 paths are present and agree, on this machine, this run.

    python tools/check_blake3.py

`test_blake3.py` skips itself when the Rust extension is missing, which is right
for a contributor's laptop and wrong for CI: a skipped module and a passing one look
identical in a green run, so "the two implementations agree" would be a claim about
some other machine.

This is the step that makes it a claim about this one. It exists as a file rather
than a one-liner in the workflow because the workflow runs under bash on Linux and
PowerShell on Windows, and a command that quotes correctly in both is a command
nobody can read.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from anla1.blake3 import blake3_256_reference, using_native  # noqa: E402

# Lengths that cross BLAKE3's 1024-byte chunk boundary, where the tree logic that
# distinguishes a real implementation from a plausible one starts to matter.
LENGTHS = (0, 1, 63, 64, 1023, 1024, 1025, 2048, 3072, 4096, 8192, 16385)


def main() -> int:
    try:
        import blake3 as native
    except ImportError:
        print("the Rust blake3 extension is not installed, so the cross-check "
              "cannot run and the suite's agreement claim is untested here",
              file=sys.stderr)
        return 1

    if not using_native:
        print("anla1.blake3 did not pick up the extension even though it imports",
              file=sys.stderr)
        return 1

    for length in LENGTHS:
        data = bytes(i % 251 for i in range(length))
        mine, theirs = blake3_256_reference(data), native.blake3(data).digest()
        if mine != theirs:
            print(f"disagreement at length {length}:\n"
                  f"  reference {mine.hex()}\n"
                  f"  extension {theirs.hex()}", file=sys.stderr)
            return 1

    version = getattr(native, "__version__", "unknown")
    print(f"blake3 {version} agrees with the pure-Python reference "
          f"at {len(LENGTHS)} lengths up to {max(LENGTHS)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
