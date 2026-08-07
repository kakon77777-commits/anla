# test_demo — the corpus

Put real files here. Anything: papers, source, PDFs, images, whatever ANLA is going
to have to hold one day. Then:

```bash
python test_demo/run.py            # pack, verify, extract, compare, report
python test_demo/run.py --keep     # and leave the artifacts in _out/
```

It reports **per file extension**, so a new kind of file arrives as its own row
rather than dissolving into a total. A round trip that works for Markdown and not
for PDF should look exactly like that.

Every comparison is against the file **on disk, re-read, in binary**. Not against
what the scanner captured on the way in — comparing an archive to the copy the
archiver is holding is a check that cannot fail for the reason anyone cares about.
Binary, because these papers are UTF-8 with CJK in them and a text-mode read on a
cp950 host would turn a byte-exact round trip into two mojibake strings agreeing.

`python/tests/test_corpus_demo.py` runs the same check as part of the ordinary
suite, so the corpus is exercised on every run and on every CI platform.

## What the first run found

The papers are 18–36 KiB. The pinned chunking default averages 256 KiB with a
**64 KiB floor** — so every paper was entirely below the floor, was a single chunk,
and content-defined chunking did nothing at all. Inserting one paragraph into the
36 KiB whitepaper cost 40 KiB: the whole file, again.

The harness now sweeps chunk sizes and prints the curve. `anla-cdc-1` is not what
changes — it pins the gear table and the boundary rule, which is the part two
implementations must agree on. The sizes are declared per archive and are supposed
to fit the corpus, and nothing had ever checked whether the default fitted *this*
one.

`anla1 pack --chunk-avg 4096` is how you say so.

## `_out/`

Generated, git-ignored, deleted and rebuilt on every `--keep` run. Everything else
in this folder is corpus — including `run.py` itself, because a Python source file
is exactly the sort of thing going in here next.
