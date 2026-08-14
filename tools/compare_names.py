# -*- coding: utf-8 -*-
"""Do the two implementations derive the same path from the same native bytes?

SPEC §5.2.1 says a native name's `path` is its derivation, and both readers check
that relation — Python by decoding with `surrogateescape` and rewriting the
surrogates, Rust by walking the bytes and testing each window with `from_utf8`.
Two routes to one definition, which is exactly the situation that produces a rule
tight enough to state and loose enough to implement two ways.

Nothing new is needed to compare them. If the derivations disagree for some name,
the archive Python wrote carries a `path` that Rust will not derive, and Rust
refuses it. So: put every awkward name into one archive and hand it over.

    python tools/compare_names.py [-n COUNT]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "python"))

from anla.errors import AnlaError  # noqa: E402
from anla1.manifest import check_object_path, native_name_for  # noqa: E402
from anla1.snapshot import SourceEntry, append_snapshot  # noqa: E402

RUST = pathlib.Path(__file__).resolve().parent.parent / "rust" / "target" / "release"
FIXED_UUID = bytes(range(16))


def lcg(seed: int):
    """A named generator, because `(i * k + c) % 256` written inline has been
    mistaken for entropy in this repository three times — once in the very file
    that warned about it."""
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (2 ** 64)
        yield (state >> 33) & 0xFF


def awkward_names(count: int) -> list[bytes]:
    """Names chosen to sit on the boundaries of UTF-8 decoding.

    Random bytes alone would be almost entirely invalid sequences, which tests one
    branch. The interesting cases are the ones where a *prefix* decodes and the rest
    does not, because that is where a byte-walking implementation and a
    surrogate-decoding one can disagree about how much to consume.
    """
    fixed = [
        b"plain.txt",
        "café.txt".encode("utf-8"),
        "中文-漢字.txt".encode("utf-8"),
        "🌏.bin".encode("utf-8"),
        b"caf\xe9.txt",
        b"\xff\xfe.bin",
        b"a\x80b\x81c",
        b"\xc3",                      # a lead byte with nothing after it
        b"\xc3\x28",                  # a lead byte with a bad continuation
        b"\xe4\xb8",                  # two thirds of a three-byte sequence
        b"\xe4\xb8\xad\xe6",          # a valid char then a truncated one
        b"\xf0\x9f\x8c",              # three quarters of an emoji
        b"\xed\xa0\x80",              # a UTF-16 surrogate encoded as UTF-8
        b"\xf4\x90\x80\x80",          # beyond U+10FFFF
        b"\xc0\x80",                  # overlong NUL
        b"%41.txt",                   # already looks escaped — the ambiguity case
        b"%E9.txt",
        b"dir/\xe9/file.txt",
        "混合-caf".encode("utf-8") + b"\xe9.txt",
    ]
    out = list(fixed)
    stream = lcg(20260814)
    for i in range(max(0, count - len(fixed))):
        length = 1 + next(stream) % 12
        raw = bytes(next(stream) for _ in range(length))
        # No NUL and no leading `/`: those are refused for reasons that have nothing
        # to do with the derivation, and a refusal is not a comparison.
        raw = raw.replace(b"\x00", b"_").lstrip(b"/\\.")
        if raw:
            out.append(raw + b".dat")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--count", type=int, default=400)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    binary = next((RUST / n for n in ("anla1-rs.exe", "anla1-rs") if (RUST / n).exists()),
                  None)
    if binary is None:
        print("rust binary not built; run `cargo build --release` in rust/",
              file=sys.stderr)
        return 2

    names = awkward_names(args.count)
    # One archive holding every name. Deduplicated by derived path, because two
    # native names deriving one path is a *different* rule (§5.2.1 duplicate paths)
    # and mixing the two would make a refusal ambiguous.
    entries, natives, by_path = [], {}, {}
    collisions = 0
    for raw in names:
        try:
            path, native = native_name_for(raw)
            # Refused for a *different* rule — a trailing dot, an empty component,
            # a `..` the escaping never touched. Filtering here rather than letting
            # the pack raise keeps this comparison about the derivation and nothing
            # else; the first run died on one of these and said nothing about
            # whether the two implementations agreed.
            check_object_path(path)
        except AnlaError:
            continue
        if path in by_path:
            collisions += 1
            continue
        by_path[path] = raw
        entries.append(SourceEntry.of(path, b"x"))
        if native is not None:
            natives[path] = native

    archive = append_snapshot(b"", files=entries, native_names=natives,
                              created_unix_ns=1, archive_id=FIXED_UUID)
    with tempfile.TemporaryDirectory() as work:
        target = pathlib.Path(work) / "names.anla"
        target.write_bytes(archive)
        done = subprocess.run([str(binary), "verify", str(target)],
                              capture_output=True, text=True)

    agreed = done.returncode == 0
    result = {
        "names_offered": len(names),
        "names_compared": len(entries),
        "with_native_name": len(natives),
        "derived_path_collisions_skipped": collisions,
        "rust_accepts": agreed,
        "rust_says": (done.stdout or done.stderr).strip()[:200],
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"  {len(entries)} names, {len(natives)} of them not UTF-8")
        if collisions:
            print(f"  {collisions} skipped: two native names derive one path, which "
                  f"is the duplicate-path rule and not this one")
        print(f"  rust: {'agrees on every derivation' if agreed else result['rust_says']}")
    if not agreed:
        return 1
    # "Rust accepted the archive" is evidence only if Rust would have refused a
    # wrong one, so the control hands it exactly that. The weak version of this
    # checked that *Python* refuses a mismatched name at write time — true, and
    # entirely silent about the implementation this tool exists to grade.
    control = _rust_refuses_a_mismatch(binary)
    print("  control: a path that is not the name's derivation -> "
          + ("refused by rust, so the comparison above can fail"
             if control else "ACCEPTED BY RUST — the comparison above proves nothing"))
    return 0 if control else 1


def _rust_refuses_a_mismatch(binary: pathlib.Path) -> bool:
    """Forge a manifest whose `path` is not its `name`'s derivation — every hash and
    every root correct — and confirm Rust refuses it for that reason."""
    from anla1 import container as C
    from anla1.blake3 import blake3_256 as H
    from anla1.cbor import decode, encode
    from anla1.manifest import OBJECT_ID_PREFIX, compute_roots

    archive = append_snapshot(b"", files=[SourceEntry.of("hello.txt", b"x" * 40)],
                              created_unix_ns=1, archive_id=FIXED_UUID)
    footer = C.find_latest_footer(archive)
    record = C.parse_record(archive, footer.manifest_offset)
    manifest = decode(archive[record.payload_offset:
                              record.payload_offset + record.payload_length])
    for entry in manifest["objects"]:
        if entry["kind"] == "regular-file":
            entry["name"] = b"not-the-derivation.txt"
            identity = {k: v for k, v in entry.items() if k != "object_id"}
            entry["object_id"] = H(OBJECT_ID_PREFIX + encode(identity))
    roots = compute_roots(manifest["objects"], manifest["chunks"],
                          manifest["metadata"], manifest["auxiliary"], H)
    for field_name in ("objects_root", "chunks_root", "metadata_root",
                       "preservation_root", "auxiliary_root"):
        manifest[field_name] = getattr(roots, field_name)
    payload = encode(manifest)
    header = dict(record.header)
    header["payload_hash"] = H(payload)
    rebuilt = C.build_record(record.type, header, payload, record.sequence,
                             record.flags)
    tail = C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=footer.snapshot_sequence,
        manifest_offset=record.offset, manifest_length=len(rebuilt),
        preservation_root=roots.preservation_root,
        previous_footer_offset=footer.previous_footer_offset,
        auxiliary_root=roots.auxiliary_root, hash_algorithm=footer.hash_algorithm)
    forged = C.with_footer_hint(
        bytes(archive[:record.offset]) + rebuilt + tail, record.offset + len(rebuilt))

    with tempfile.TemporaryDirectory() as work:
        target = pathlib.Path(work) / "control.anla"
        target.write_bytes(forged)
        done = subprocess.run([str(binary), "verify", str(target)],
                              capture_output=True, text=True)
    # The reason matters as much as the refusal: a rejection for a root mismatch
    # would mean the forgery was broken, not that the rule was enforced.
    return done.returncode != 0 and "derivation" in (done.stdout + done.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
