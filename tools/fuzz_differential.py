# -*- coding: utf-8 -*-
"""Differential fuzzing across the two reference implementations.

    python tools/fuzz_differential.py                 # 2000 mutants, default seed
    python tools/fuzz_differential.py -n 20000        # longer run
    python tools/fuzz_differential.py --seed 12345    # a different corner
    python tools/fuzz_differential.py --keep          # write mutants to disk

The conformance suite proves the two implementations agree on the inputs someone
thought of. That is a weaker statement than it looks. This tool generates inputs
nobody thought of and asks a narrower question of each one:

    do both implementations reach the same verdict?

Not "is the verdict correct" — that would need an oracle, and the specification is
the oracle only where someone has already read it carefully. Agreement is checkable
without one, and disagreement is always a defect in at least one place: an
implementation, or the specification for having left the case open.

Two grades of finding:

* **Divergence.** One accepts, the other rejects. Unambiguous, and always a bug:
  either a reader accepts a malformed archive or it refuses a valid one.
* **Code mismatch.** Both reject, with different error codes. SPEC.md sections 3, 5
  and 8 fix the verification order, so for a mutant with a single defect the codes
  should match. When they do not, either an implementation checks out of order or
  the specification never said which check comes first.

Every finding is written out as a reproducible case, because a fuzzer whose
findings cannot be replayed is a random number generator with opinions.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python"))

from anla import Limits, open_archive  # noqa: E402
from anla.canonical import canonical_bytes  # noqa: E402
from anla.errors import AnlaError  # noqa: E402
from anla.format import (  # noqa: E402
    FOOTER_SIZE,
    HEADER_SIZE,
    build_footer,
    build_record,
    crc32,
    parse_record,
    sha256_digest,
    sha256_hex,
)

VECTORS = REPO / "conformance" / "vectors"
FINDINGS = REPO / "conformance" / "fuzz-findings"
RUNNER = REPO / "conformance" / "run_node.mjs"

#: Tight limits, so a mutant claiming a terabyte is refused in a millisecond
#: instead of being allocated. Both sides must use the same ones or the
#: comparison is meaningless.
LIMITS = Limits(max_output_bytes=8 * 1024 * 1024, max_objects=10_000,
                max_chunk_uncompressed=2 * 1024 * 1024)
JS_LIMITS = {"maxOutputBytes": 8 * 1024 * 1024, "maxObjects": 10_000,
             "maxChunkUncompressed": 2 * 1024 * 1024}


# ---------------------------------------------------------------------------
# mutations
# ---------------------------------------------------------------------------

def bitflip(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    out = bytearray(data)
    index = rng.randrange(len(out))
    out[index] ^= 1 << rng.randrange(8)
    return bytes(out), f"bitflip@{index}"


def truncate(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    at = rng.randrange(1, len(data))
    return data[:at], f"truncate@{at}"


def extend(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    extra = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 64)))
    return data + extra, f"extend+{len(extra)}"


def wild_field(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    """Overwrite a length or offset field with something hostile, then repair the
    CRC that covers it — so the mutant reaches the semantic checks instead of
    dying at the frame."""
    out = bytearray(data)
    wild = rng.choice([0, 1, 2 ** 16, 2 ** 31, 2 ** 32 - 1, 2 ** 53 - 1, 2 ** 63,
                       2 ** 64 - 1, len(data), len(data) + 1])
    region = rng.choice(["header", "footer", "record"])

    if region == "header":
        offset = rng.choice([8, 10, 12, 16, 24, 32, 40])
        size = 2 if offset in (8, 10) else 4
        struct.pack_into("<H" if size == 2 else "<I", out, offset,
                         wild % (2 ** (8 * size)))
        struct.pack_into("<I", out, 60, crc32(bytes(out[:60])))
        return bytes(out), f"header[{offset}]={wild}"

    if region == "footer":
        base = len(out) - FOOTER_SIZE
        offset = rng.choice([8, 10, 12, 16, 24, 80])
        if offset in (16, 24):
            struct.pack_into("<Q", out, base + offset, wild % (2 ** 64))
        elif offset in (8, 10):
            struct.pack_into("<H", out, base + offset, wild % (2 ** 16))
        else:
            struct.pack_into("<I", out, base + offset, wild % (2 ** 32))
        struct.pack_into("<I", out, base + 92, crc32(bytes(out[base:base + 92])))
        return bytes(out), f"footer[{offset}]={wild}"

    # A record frame: pick one by walking the stream, then corrupt a field.
    offsets = []
    at = HEADER_SIZE
    while at < len(data) - FOOTER_SIZE:
        try:
            record = parse_record(data, at)
        except AnlaError:
            break
        offsets.append(at)
        at += record.total_length
    if not offsets:
        return bitflip(data, rng)
    record_at = rng.choice(offsets)
    offset = rng.choice([8, 10, 12, 16, 24, 36])
    if offset in (16, 24):
        struct.pack_into("<Q", out, record_at + offset, wild % (2 ** 64))
    elif offset in (8, 10):
        struct.pack_into("<H", out, record_at + offset, wild % (2 ** 16))
    else:
        struct.pack_into("<I", out, record_at + offset, wild % (2 ** 32))
    return bytes(out), f"record@{record_at}[{offset}]={wild}"


MANIFEST_MUTATIONS = (
    "drop-member", "retype-member", "nudge-number", "duplicate-path",
    "unsafe-path", "unknown-codec", "unknown-object", "break-chunk-id",
    "break-coverage", "drop-chunk", "swap-paths", "negative-number",
    "float-number", "huge-number", "empty-objects", "null-member",
)


def mutate_manifest(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    """Rewrite the manifest with one structural defect, keeping every hash correct.

    This is where the interesting findings live. A byte flip usually dies at a CRC
    or a payload hash, which proves only that hashing works. A manifest that is
    internally consistent and semantically wrong is what actually exercises a
    decoder's judgement.
    """
    from anla.format import parse_footer, parse_header

    header = parse_header(data)
    footer = parse_footer(data, header)
    record = parse_record(data, footer.manifest_record_offset)
    payload = data[record.payload_offset:record.payload_offset + record.payload_length]
    manifest = json.loads(payload.decode("utf-8"))

    kind = rng.choice(MANIFEST_MUTATIONS)
    files = [o for o in manifest["objects"] if o.get("type") == "file"]
    chunk_ids = list(manifest["chunks"])

    if kind == "drop-member":
        key = rng.choice(list(manifest))
        manifest.pop(key)
        detail = f"drop {key}"
    elif kind == "retype-member":
        key = rng.choice(list(manifest))
        manifest[key] = rng.choice([[], {}, 0, "", True])
        detail = f"retype {key}"
    elif kind == "nudge-number" and files:
        target = rng.choice(files)
        target["size"] = target["size"] + rng.choice([-1, 1, 2])
        detail = "nudge size"
    elif kind == "duplicate-path" and manifest["objects"]:
        manifest["objects"].append(dict(rng.choice(manifest["objects"])))
        detail = "duplicate object"
    elif kind == "unsafe-path" and manifest["objects"]:
        rng.choice(manifest["objects"])["path"] = rng.choice(
            ["../escape", "/abs", "C:/x", "a//b", "a/./b", "", "a/../b"])
        detail = "unsafe path"
    elif kind == "unknown-codec" and chunk_ids:
        manifest["chunks"][rng.choice(chunk_ids)]["codec"] = rng.choice(
            ["zstd", "brotli", "", "STORE"])
        detail = "unknown codec"
    elif kind == "unknown-object" and manifest["objects"]:
        rng.choice(manifest["objects"])["type"] = rng.choice(
            ["symbolic-link", "sparse-file", "", "FILE"])
        detail = "unknown object type"
    elif kind == "break-chunk-id" and chunk_ids:
        old = rng.choice(chunk_ids)
        new = rng.choice([old.upper(), old[:-1] + "g", old[:63], old + "0", "0" * 64])
        manifest["chunks"][new] = manifest["chunks"].pop(old)
        for obj in files:
            for ref in obj["chunks"]:
                if ref["id"] == old:
                    ref["id"] = new
        detail = "break chunk id"
    elif kind == "break-coverage" and files:
        target = rng.choice([f for f in files if f["chunks"]] or files)
        if target["chunks"]:
            target["chunks"][rng.randrange(len(target["chunks"]))]["length"] += 1
        detail = "break coverage"
    elif kind == "drop-chunk" and chunk_ids:
        manifest["chunks"].pop(rng.choice(chunk_ids))
        detail = "drop chunk descriptor"
    elif kind == "swap-paths" and len(manifest["objects"]) >= 2:
        a, b = rng.sample(range(len(manifest["objects"])), 2)
        objs = manifest["objects"]
        objs[a]["path"], objs[b]["path"] = objs[b]["path"], objs[a]["path"]
        detail = "swap two paths"
    elif kind == "negative-number" and files:
        rng.choice(files)["size"] = -1
        detail = "negative size"
    elif kind == "float-number" and files:
        rng.choice(files)["size"] = 1.5
        detail = "float size"
    elif kind == "huge-number" and chunk_ids:
        manifest["chunks"][rng.choice(chunk_ids)]["raw_size"] = 2 ** 40
        detail = "huge raw_size"
    elif kind == "empty-objects":
        manifest["objects"] = []
        detail = "empty objects"
    else:
        manifest[rng.choice(list(manifest))] = None
        detail = "null member"

    try:
        new_payload = canonical_bytes(manifest)
    except Exception:
        # A float or a null cannot be canonically encoded, which is itself the
        # point of the profile; fall back to plain JSON so the mutant still
        # reaches both readers and both get to refuse it.
        new_payload = json.dumps(manifest, ensure_ascii=False,
                                 separators=(",", ":"), sort_keys=True).encode("utf-8")

    prefix = data[:footer.manifest_record_offset]
    rebuilt = build_record("MANF", {"encoding": "canonical-json",
                                    "payload_sha256": sha256_hex(new_payload),
                                    "preservation_required": True},
                           new_payload, record.sequence)
    tail = build_footer(len(prefix), len(rebuilt), header.archive_uuid,
                        sha256_digest(new_payload))
    return prefix + rebuilt + tail, f"manifest:{detail}"


STRATEGIES = (
    (bitflip, 30),
    (truncate, 10),
    (extend, 5),
    (wild_field, 25),
    (mutate_manifest, 30),
)


def mutate(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    functions, weights = zip(*STRATEGIES)
    strategy = rng.choices(functions, weights=weights, k=1)[0]
    try:
        return strategy(data, rng)
    except Exception as exc:  # a mutation that cannot be applied is not a finding
        return bitflip(data, rng)[0], f"{strategy.__name__}-failed:{type(exc).__name__}"


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    accepted: bool
    code: str = ""
    message: str = ""


def python_verdict(data: bytes) -> Verdict:
    try:
        archive = open_archive(data, full=True, limits=LIMITS)
        for obj in archive.files():
            archive.read(obj["path"])
        return Verdict(True)
    except AnlaError as exc:
        return Verdict(False, exc.code, exc.message[:200])
    except Exception as exc:
        # An exception that is not an AnlaError is itself a finding: the reader
        # crashed where it should have refused.
        return Verdict(False, f"UNCAUGHT_{type(exc).__name__}", str(exc)[:200])


def node_verdicts(directory: Path) -> dict[str, Verdict]:
    completed = subprocess.run(
        ["node", str(RUNNER), "fuzz", str(directory)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
    )
    if not completed.stdout.strip():
        raise SystemExit(f"node runner produced nothing:\n{completed.stderr[:2000]}")
    report = json.loads(completed.stdout)
    return {name: Verdict(v["accepted"], v.get("code", ""), v.get("message", ""))
            for name, v in report["verdicts"].items()}


@dataclass
class Findings:
    divergences: list[dict] = field(default_factory=list)
    code_mismatches: list[dict] = field(default_factory=list)
    uncaught: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run(count: int, seed: int, batch: int, keep: bool, quiet: bool = False) -> Findings:
    rng = random.Random(seed)
    seeds = sorted(VECTORS.glob("*.anla"))
    if not seeds:
        raise SystemExit("no seed vectors found")
    corpus = {path.name: path.read_bytes() for path in seeds}

    work = REPO / "conformance" / ".fuzz-work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    findings = Findings()
    stats = {"accepted-both": 0, "rejected-both": 0}
    produced = 0

    while produced < count:
        this_batch = min(batch, count - produced)
        cases: dict[str, tuple[bytes, str, str]] = {}
        for index in range(this_batch):
            origin, data = rng.choice(list(corpus.items()))
            mutant, how = mutate(data, rng)
            name = f"m{produced + index:06d}.anla"
            (work / name).write_bytes(mutant)
            cases[name] = (mutant, origin, how)

        js = node_verdicts(work)
        for name, (mutant, origin, how) in cases.items():
            py = python_verdict(mutant)
            other = js.get(name)
            if other is None:
                raise SystemExit(f"the JavaScript runner skipped {name}")
            record = {"seed": seed, "origin": origin, "mutation": how,
                      "python": py.__dict__, "javascript": other.__dict__,
                      "sha256": sha256_hex(mutant), "bytes": len(mutant)}
            if py.code.startswith("UNCAUGHT_"):
                findings.uncaught.append(record)
            elif py.accepted != other.accepted:
                findings.divergences.append(record)
            elif not py.accepted and py.code != other.code:
                findings.code_mismatches.append(record)
            else:
                stats["accepted-both" if py.accepted else "rejected-both"] += 1

        for name in cases:
            (work / name).unlink()
        produced += this_batch
        if not quiet:
            print(f"\r{produced}/{count} mutants · "
                  f"{stats['rejected-both']} refused by both · "
                  f"{stats['accepted-both']} accepted by both · "
                  f"{len(findings.divergences)} divergences · "
                  f"{len(findings.code_mismatches)} code mismatches · "
                  f"{len(findings.uncaught)} uncaught", end="", flush=True)

    if not quiet:
        print()

    interesting = findings.divergences + findings.code_mismatches + findings.uncaught
    if interesting and keep:
        FINDINGS.mkdir(parents=True, exist_ok=True)
        (FINDINGS / f"findings-seed{seed}.json").write_text(
            json.dumps({"seed": seed, "count": count,
                        "divergences": findings.divergences,
                        "code_mismatches": findings.code_mismatches,
                        "uncaught": findings.uncaught}, indent=2, sort_keys=True),
            encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--batch", type=int, default=250,
                        help="mutants per Node invocation; process spawn is the cost")
    parser.add_argument("--keep", action="store_true", help="write findings to disk")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    findings = run(args.count, args.seed, args.batch, args.keep, args.quiet)
    summary = {
        "seed": args.seed,
        "mutants": args.count,
        "divergences": len(findings.divergences),
        "code_mismatches": len(findings.code_mismatches),
        "uncaught_exceptions": len(findings.uncaught),
    }
    if args.json:
        json.dump({**summary,
                   "divergence_detail": findings.divergences[:20],
                   "code_mismatch_detail": findings.code_mismatches[:20],
                   "uncaught_detail": findings.uncaught[:20]},
                  sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for label, items in (("divergence", findings.divergences),
                             ("code mismatch", findings.code_mismatches),
                             ("uncaught", findings.uncaught)):
            for item in items[:12]:
                print(f"\n{label}: {item['mutation']}  (from {item['origin']})")
                print(f"  python:     {item['python']['code'] or 'accepted'}"
                      f"  {item['python']['message'][:100]}")
                print(f"  javascript: {item['javascript']['code'] or 'accepted'}"
                      f"  {item['javascript']['message'][:100]}")
        print("\n" + json.dumps(summary, indent=2, sort_keys=True))

    # A divergence or a crash fails the run. A code mismatch is reported and does
    # not: it may be a specification gap, and the triage belongs to a human.
    return 1 if (findings.divergences or findings.uncaught) else 0


if __name__ == "__main__":
    raise SystemExit(main())
