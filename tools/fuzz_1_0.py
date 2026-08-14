# -*- coding: utf-8 -*-
"""Differential fuzzing for ANLA 1.0 — Python against Rust.

    python tools/fuzz_1_0.py -n 2000
    python tools/fuzz_1_0.py -n 20000 --seed 7 --json --keep

Mutate a valid archive and ask both implementations one question: **do you accept
this?** Agreement needs no oracle. Disagreement is always a defect in one of them or
an ambiguity in the specification, and there is no third possibility — which is what
makes this the most valuable tool in the repository and why 1.0 not having it was
the real cost of having only one implementation.

Two grades of finding:

* **divergence** — one accepted and the other refused. Always a defect.
* **code mismatch** — both refused, for different reasons. Usually a specification
  gap: two readers that disagree about *why* an archive is broken have read the same
  sentence differently, and one of them will eventually act on it.

Code mismatches do not fail the run. They are for a person to triage, so they are
written out rather than counted and forgotten.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from anla1.cli import main as anla1_main  # noqa: E402
from anla1.fs import scan_tree  # noqa: E402
from anla.errors import AnlaError
from anla1 import container as C
from anla1.blake3 import blake3_256
from anla1.snapshot import append_snapshot, cdc_chunker  # noqa: E402

RUST = ROOT / "rust" / "target" / "release" / (
    "anla1-rs.exe" if sys.platform == "win32" else "anla1-rs")

FIXED_UUID = bytes(range(16))
FIXED_TIME = 1_785_000_000_000_000_000


def build_seeds() -> list[tuple[str, bytes]]:
    """Archives worth mutating: several shapes, all built by the Python writer."""
    from anla.fastcdc import CdcProfile
    from anla1.codecs import CODEC_STORE, CODEC_ZSTD
    from anla1.snapshot import SourceEntry

    corpus = ROOT / "test_demo"
    tree = scan_tree(corpus, exclude=("_out", "_out/**", "__pycache__", "__pycache__/**",
                                      "*.pyc"))
    small = cdc_chunker(CdcProfile(min_size=1024, avg_size=4096, max_size=16384))

    seeds: list[tuple[str, bytes]] = []
    one = append_snapshot(b"", **tree.as_source(), created_unix_ns=FIXED_TIME,
                          chunker=small, codec=CODEC_ZSTD, archive_id=FIXED_UUID)
    seeds.append(("corpus-zstd", one))
    seeds.append(("corpus-store", append_snapshot(
        b"", **tree.as_source(),
        created_unix_ns=FIXED_TIME, chunker=small, codec=CODEC_STORE,
        archive_id=FIXED_UUID)))
    # A second snapshot, so the footer chain and the lineage rules get mutated too.
    edited = [SourceEntry(path=e.path, read=(lambda r=e.read()[:100] + b"edited\n": r))
              if i == 0 else e for i, e in enumerate(tree.files)]
    # `as_source()` then overridden, rather than listing the fields again: this is
    # the site that would have silently dropped `native_names` had it kept spelling
    # them out, and a seed archive missing a field the others have is a hole in the
    # corpus nothing reports.
    seeds.append(("two-snapshots", append_snapshot(
        one, **{**tree.as_source(), "files": edited},
        created_unix_ns=FIXED_TIME + 1, chunker=small, codec=CODEC_ZSTD)))
    # Something tiny, because most mutations of a big archive land in payload.
    seeds.append(("minimal", append_snapshot(
        b"", files=[SourceEntry.of("a.txt", b"one line\n")],
        created_unix_ns=FIXED_TIME, archive_id=FIXED_UUID)))
    return seeds


# ---------------------------------------------------------------------------
# the two verdicts
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    accepted: bool
    code: str


def python_verdict(path: Path) -> Verdict:
    """Run the Python reader in-process, but through the CLI, so the comparison is
    between the two *programs* rather than between one program and a library call
    the other has no equivalent of."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = anla1_main(["verify", str(path), "--json"])
    except Exception as exc:                      # noqa: BLE001 - a crash is a verdict
        return Verdict(False, f"crash:{type(exc).__name__}")
    if code == 0:
        return Verdict(True, "ok")
    try:
        payload = json.loads(err.getvalue() or "{}")
        return Verdict(False, str(payload.get("code", f"exit:{code}")))
    except json.JSONDecodeError:
        return Verdict(False, f"exit:{code}")


def rust_verdict(path: Path) -> Verdict:
    result = subprocess.run([str(RUST), "verify", str(path)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        return Verdict(True, "ok")
    if result.returncode in (101, -1073741819):   # a Rust panic, or a Windows fault
        return Verdict(False, "crash:panic")
    try:
        payload = json.loads(result.stderr or "{}")
        return Verdict(False, str(payload.get("code", f"exit:{result.returncode}")))
    except json.JSONDecodeError:
        return Verdict(False, f"exit:{result.returncode}")


#: The two sides name the same conditions differently — one by exit code, one by
#: name — so a comparison of the raw strings would report a "mismatch" for every
#: single refusal. The first run of this fuzzer did exactly that: 284 of them, all
#: of which were the instrument rather than the implementations. Normalise both to
#: one vocabulary, and a mismatch that survives is a real disagreement.
EQUIVALENT = {
    "integrity-failure": "integrity", "exit:5": "integrity",
    "manifest-invalid": "manifest", "exit:4": "manifest",
    "unsupported-capability": "capability", "exit:3": "capability",
    "resource-limit-exceeded": "limit", "exit:8": "limit",
    "unsafe-object": "unsafe", "exit:9": "unsafe",
    "invalid-input": "input", "exit:2": "input",
    "fidelity-degraded": "fidelity", "exit:11": "fidelity",
    "ok": "ok",
}


def family(code: str) -> str:
    return EQUIVALENT.get(code, code)


# ---------------------------------------------------------------------------
# mutations
# ---------------------------------------------------------------------------

def bitflip(rng: random.Random, data: bytes) -> bytes:
    out = bytearray(data)
    for _ in range(rng.randint(1, 4)):
        at = rng.randrange(len(out))
        out[at] ^= 1 << rng.randrange(8)
    return bytes(out)


def truncate(rng: random.Random, data: bytes) -> bytes:
    return data[:rng.randrange(0, len(data))]


def extend(rng: random.Random, data: bytes) -> bytes:
    return data + bytes(rng.randrange(256) for _ in range(rng.randint(1, 64)))


def wild_field(rng: random.Random, data: bytes) -> bytes:
    """Overwrite an aligned 8-byte window with a hostile integer.

    Lengths and offsets are where a forged archive does its work, and a random bit
    flip almost never produces an interesting one.
    """
    out = bytearray(data)
    if len(out) < 16:
        return bytes(out)
    at = rng.randrange(0, len(out) - 8) & ~7
    value = rng.choice([0, 1, 2 ** 32 - 1, 2 ** 63, 2 ** 64 - 1,
                        len(out), len(out) + 1, 2 ** 31])
    out[at:at + 8] = value.to_bytes(8, "little")
    return bytes(out)


def splice(rng: random.Random, data: bytes) -> bytes:
    """Move a block. Produces plausible-looking records at wrong offsets."""
    out = bytearray(data)
    if len(out) < 128:
        return bytes(out)
    size = rng.randint(8, min(256, len(out) // 4)) & ~7
    src = rng.randrange(0, len(out) - size) & ~7
    dst = rng.randrange(0, len(out) - size) & ~7
    out[dst:dst + size] = data[src:src + size]
    return bytes(out)


def rehashed_manifest(rng: random.Random, data: bytes) -> bytes:
    """Mutate the manifest payload and then *repair* its hash.

    Every other strategy here is defeated by the integrity layer before it can be
    interesting. A random flip inside a manifest fails the payload hash, both
    readers answer `integrity-failure`, they agree, and the mutant is scored as a
    success — while the CBOR decoder, the canonical-form rules, the path rules and
    the root arithmetic behind that hash are never executed at all. Sixteen thousand
    mutants had reached none of them.

    So this one plays the part the threat model actually cares about: not a corrupt
    disk, but a *writer that is lying*, with correct hashes over illegal content.
    That is the only mutation class that can reach the parser, and the first archive
    built this way found a real divergence — Python raised an unhandled
    `UnicodeDecodeError`, exit 1; Rust answered `manifest-invalid`, exit 4.
    """
    try:
        record = C.parse_record(data, C.find_latest_footer(data).manifest_offset)
    except AnlaError:
        return bytes(data)          # nothing to lie about; leave it to another strategy
    payload = bytearray(data[record.payload_offset:
                             record.payload_offset + record.payload_length])
    if not payload:
        return bytes(data)
    at = rng.randrange(len(payload))
    payload[at] ^= 1 << rng.randrange(8)
    header = dict(record.header)
    header["payload_hash"] = blake3_256(bytes(payload))
    try:
        rebuilt = C.build_record(record.type, header, bytes(payload),
                                 record.sequence, record.flags)
    except AnlaError:
        return bytes(data)
    span = ((record.unpadded_length + 7) // 8) * 8
    if len(rebuilt) != span:
        return bytes(data)          # a length change would move every later offset
    out = bytearray(data)
    out[record.offset:record.offset + span] = rebuilt
    return bytes(out)


STRATEGIES = ([bitflip] * 30 + [truncate] * 10 + [extend] * 5
              + [wild_field] * 30 + [splice] * 15 + [rehashed_manifest] * 20)


# ---------------------------------------------------------------------------

@dataclass
class Findings:
    mutants: int = 0
    accepted_by_both: int = 0
    refused_by_both: int = 0
    divergences: list[dict] = field(default_factory=list)
    code_mismatches: list[dict] = field(default_factory=list)
    crashes: list[dict] = field(default_factory=list)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--count", type=int, default=500)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--keep", action="store_true",
                        help="write findings to conformance/fuzz-1.0-findings/")
    args = parser.parse_args(argv)

    if not RUST.exists():
        print(f"{RUST} is not built — run `cargo build --release` in rust/",
              file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    seeds = build_seeds()
    findings = Findings()
    keep = ROOT / "conformance" / "fuzz-1.0-findings"

    with tempfile.TemporaryDirectory(prefix="anla1-fuzz-") as tmp:
        target = Path(tmp) / "mutant.anla"
        for index in range(args.count):
            name, seed = rng.choice(seeds)
            mutant = rng.choice(STRATEGIES)(rng, seed)
            if not mutant:
                continue
            target.write_bytes(mutant)
            findings.mutants += 1

            py, rs = python_verdict(target), rust_verdict(target)
            record = {"seed": args.seed, "index": index, "corpus": name,
                      "python": py.code, "rust": rs.code, "bytes": len(mutant)}

            if py.code.startswith("crash") or rs.code.startswith("crash"):
                findings.crashes.append(record)
            if py.accepted != rs.accepted:
                findings.divergences.append(record)
            elif py.accepted:
                findings.accepted_by_both += 1
            else:
                findings.refused_by_both += 1
                if family(py.code) != family(rs.code):
                    findings.code_mismatches.append(record)

            # Every finding keeps its mutant, mismatches included. The first run
            # kept only divergences, so the one code mismatch it found could not be
            # reproduced afterwards — a finding you cannot reopen is a note.
            if args.keep and record in (findings.divergences[-1:] + findings.crashes[-1:]
                                        + findings.code_mismatches[-1:]):
                keep.mkdir(parents=True, exist_ok=True)
                (keep / f"mutant-{args.seed}-{index}.anla").write_bytes(mutant)

            if not args.json and index % 250 == 0 and index:
                print(f"  {index}/{args.count} · {len(findings.divergences)} divergences"
                      f" · {len(findings.code_mismatches)} code mismatches",
                      file=sys.stderr)

    payload = {
        "seed": args.seed,
        "mutants": findings.mutants,
        "accepted_by_both": findings.accepted_by_both,
        "refused_by_both": findings.refused_by_both,
        "divergences": len(findings.divergences),
        "code_mismatches": len(findings.code_mismatches),
        "crashes": len(findings.crashes),
        "divergence_detail": findings.divergences[:20],
        "code_mismatch_detail": findings.code_mismatches[:20],
        "crash_detail": findings.crashes[:20],
    }
    if args.keep and (findings.divergences or findings.code_mismatches):
        keep.mkdir(parents=True, exist_ok=True)
        (keep / f"findings-{args.seed}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")

    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"{findings.mutants} mutants · {findings.accepted_by_both} accepted by both"
              f" · {findings.refused_by_both} refused by both"
              f" · {len(findings.divergences)} divergences"
              f" · {len(findings.code_mismatches)} code mismatches"
              f" · {len(findings.crashes)} crashes")
        for row in findings.divergences[:10]:
            print(f"  DIVERGENCE  python={row['python']:<24} rust={row['rust']}")
        for row in findings.code_mismatches[:10]:
            print(f"  code        python={row['python']:<24} rust={row['rust']}")

    # Divergences fail the run. Code mismatches are for a person.
    return 1 if findings.divergences or findings.crashes else 0


if __name__ == "__main__":
    raise SystemExit(main())
