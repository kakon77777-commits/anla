# -*- coding: utf-8 -*-
"""Assert zstd is present and behaves as the format assumes, on this machine.

    python tools/check_zstd.py

`test_codecs_1_0.py` skips itself when `zstandard` is missing, which is right for a
contributor's laptop and wrong for CI: a skipped module and a passing one look
identical in a green run. The same hole `tools/check_blake3.py` closes.

It also re-asserts the two library behaviours the reader's safety depends on, rather
than trusting that they are still true of whatever version got installed:

* `max_output_size` is **ignored** for a frame that declares its content size, so
  bounding the output is not bomb protection;
* a frame *does* declare its content size, so reading the header is.

If a future zstandard release changed either, `decompress_chunk` would still pass
its tests while protecting nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))


def main() -> int:
    try:
        import zstandard
    except ImportError:
        print("the zstandard library is not installed, so the codec tests skipped "
              "and this run proves nothing about zstd", file=sys.stderr)
        return 1

    from anla1.codecs import CODEC_ZSTD, compress_chunk, decompress_chunk

    body = ("a paragraph of prose. " * 2000).encode()
    used, packed = compress_chunk(body, CODEC_ZSTD)
    if used != CODEC_ZSTD or len(packed) >= len(body):
        print(f"prose did not compress: {len(packed)} of {len(body)}", file=sys.stderr)
        return 1
    if decompress_chunk(packed, CODEC_ZSTD, len(body)) != body:
        print("a compressed chunk did not round trip", file=sys.stderr)
        return 1

    declared = zstandard.get_frame_parameters(packed).content_size
    if declared != len(body):
        print(f"a frame no longer declares its size ({declared}) — the reader's "
              f"bomb check reads that header and would stop working",
              file=sys.stderr)
        return 1

    bomb = zstandard.ZstdCompressor(level=3).compress(b"\0" * 50_000_000)
    try:
        zstandard.ZstdDecompressor().decompress(bomb, max_output_size=1000)
        ignored = True
    except zstandard.ZstdError:
        ignored = False
    if not ignored:
        print("NOTE: max_output_size is now enforced for size-declaring frames. "
              "The header check is still correct, but the comment explaining why "
              "it is necessary is out of date.", file=sys.stderr)

    version = ".".join(str(part) for part in zstandard.ZSTD_VERSION)
    print(f"zstandard {zstandard.__version__} / libzstd {version}: prose "
          f"{len(body)} -> {len(packed)} bytes, frame declares its size, "
          f"round trip exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
