# anla — Agent-Native Lossless Archive

**An AI may plan how to pack. A public, deterministic, model-independent decoder must
recover every byte that was declared into the archive.**

```text
Extract(Pack(F, P)) = F
```

This is the **reference implementation**: dependency-light, readable, and the
executable half of the specification. A second implementation in Rust lives in the
same repository and produces byte-identical archives; the two are held to each other
by a conformance suite and a differential fuzzer.

- Site and browser workbench — <https://anla.evemisslab.com>
- Specification — <https://anla.evemisslab.com/spec/>
- Source, papers, conformance vectors — <https://github.com/kakon77777-commits/anla>

## Install

```bash
pip install "anla-archive[speed,zstd]"    # what you probably want
pip install anla-archive                  # no optional dependencies at all
```

Take the first line unless you have a reason not to. `anla1 pack` defaults to
Zstandard, so a bare install refuses that command until `zstandard` is present —
cleanly, naming the fix, rather than quietly storing uncompressed:

```
ANLA_UNSUPPORTED_REQUIRED_CAPABILITY: this archive uses zstd and the zstandard
library is not installed        {"install": "pip install zstandard"}
```

That refusal is the design, not a rough edge: an archive that uses a codec declares
it as a **required** capability, and a reader without it must say so rather than
guess. `--codec store` works on a bare install and produces archives any reader can
open.

The distribution is `anla-archive`; the import packages and the commands are `anla`
and `anla1`. PyPI refuses the bare name — it is one character from several existing
projects — and the two names are independent anyway.

```python
import anla, anla1          # after pip install anla-archive
```

Python 3.10+. No required dependencies: `blake3` and `zstandard` are optional, and
the package carries a readable pure-Python BLAKE3 so the format's hash can be checked
by reading rather than by trusting a compiled wheel.

## Two commands, two profiles

```bash
anla  pack ./project -o project.anla        # ANLA-MVP v0.1 — frozen
anla1 pack ./project -o project.anla        # ANLA 1.0 — draft
```

Separate commands rather than a flag, for the same reason 1.0 has its own magic
number: they are different formats, and one command switching between them on a flag
invites an archive written under one profile and read under the other.

`anla1` also carries the context layer — an agent's own history, stored losslessly
and addressable back to the exact bytes of a turn:

```bash
anla1 context capture  memory.anla
anla1 context segment  memory.anla --scheme changepoint-v1
anla1 context address  memory.anla "how was the gear table produced"
```

## Read the format from Python

```python
from anla1.snapshot import list_snapshots, extract_snapshot, verify_archive

data = open("project.anla", "rb").read()
report = verify_archive(data)                      # every chunk, every root
files = extract_snapshot(data, list_snapshots(data)[-1])
```

## Speed, stated rather than discovered

Content-defined chunking is the default, because fixed chunking destroys
deduplication. In this writer it is also the slow path, by a wide margin — measured
on 64 MiB of incompressible data:

| | MiB/s |
|---|---|
| this writer, fixed chunking | 64.4 |
| **this writer, `anla-cdc-1`** | **3.8** |
| the Rust writer, `anla-cdc-1` | 107.3 |
| this reader, verify | 538.1 |

So: use this package to read archives, to check the format, to embed in Python, and
for trees measured in megabytes. Use `anla1-rs` from the same repository for volume.
The two produce identical bytes; only one of them is worth an afternoon.

Every figure above is produced by `bench/run_bench.py` and republished at
<https://anla.evemisslab.com/bench/>, including the rows where ANLA loses.

## Status

`ANLA-MVP v0.1` is frozen. `ANLA 1.0` is a **draft** and says so: the freeze rule —
two independent implementations producing byte-identical archives with no verdict
divergence under differential fuzzing — is met, but two implementations by one author
are weaker evidence than two by two authors, and the specification records that
rather than rounding it up.

> This is a research profile. It is tested, but it is young. Do not make an ANLA
> archive the only copy of anything you cannot lose.

Apache-2.0.
