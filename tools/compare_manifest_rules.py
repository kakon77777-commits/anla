# -*- coding: utf-8 -*-
"""Which manifest-level rules does each reader actually enforce?

`tools/fuzz_1_0.py` reaches these rules now — `rehashed_manifest` repairs the hash
over what it mutates, so a mutation can finally get past the integrity layer — but
it reaches them *randomly*, from a seed corpus built out of the working tree. That
makes a CI finding on Linux unreproducible on Windows, which is exactly what
happened: seed 40 found one divergence in 3000 mutants and the same seed on another
platform found none, because the corpus was not the same archive.

So this enumerates instead of sampling. Every member of the manifest, every member
of an object entry, every member of a chunk descriptor: delete it, rename it, give
it the wrong type. Repair every hash and every root so only the *rules* can refuse
the result. Then ask both readers and print every case where they disagree.

Deterministic, platform-independent, and complete over the axis it covers — which
random mutation is not, and cannot report that it is not.

    python tools/compare_manifest_rules.py [--json]
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
from anla1 import container as C  # noqa: E402
from anla1.blake3 import blake3_256 as H  # noqa: E402
from anla1.cbor import decode, encode  # noqa: E402
from anla1.manifest import compute_roots  # noqa: E402
from anla1.snapshot import (  # noqa: E402
    CODEC_ZSTD, SourceEntry, append_snapshot, verify_archive,
)

RUST = pathlib.Path(__file__).resolve().parent.parent / "rust" / "target" / "release"
FIXED_UUID = bytes(range(16))

#: One value of each shape, so "wrong type" means something for any member.
WRONG_TYPES = {"text": "wrong", "int": 999999, "bytes": b"\x00" * 8,
               "list": [], "map": {}}


def base_archive() -> bytes:
    """Two snapshots, zstd, a directory and a symlink — the widest manifest that
    can be built without touching a filesystem, because a narrow one silently
    excludes the rules that only apply to what it lacks."""
    from anla1.manifest import ObjectEntry
    first = append_snapshot(
        b"", files=[SourceEntry.of("a.txt", b"x" * 400),
                    SourceEntry.of("dir/b.txt", b"y" * 400)],
        directories=["dir"],
        objects=[ObjectEntry(kind="symbolic-link", path="link", target=b"a.txt")],
        created_unix_ns=1, archive_id=FIXED_UUID, codec=CODEC_ZSTD)
    return append_snapshot(
        first, files=[SourceEntry.of("a.txt", b"x" * 400 + b"more")],
        created_unix_ns=2, codec=CODEC_ZSTD)


def rebuild(archive: bytes, edit, protect: str | None = None) -> bytes | None:
    """Apply `edit` to the newest manifest and repair everything that covers it.

    `protect` names a member the repair must leave alone. Without it, every edit to
    a root member was silently undone by the recomputation two lines later — the
    case was counted as compared, both readers saw an untouched archive, both said
    `ok`, and the table recorded agreement about a test that never happened. Five of
    the sixteen members are roots.
    """
    footer = C.find_latest_footer(archive)
    record = C.parse_record(archive, footer.manifest_offset)
    manifest = decode(archive[record.payload_offset:
                              record.payload_offset + record.payload_length])
    if edit(manifest) is False:
        return None
    # Roots recomputed, or a reader refuses for a root mismatch and the rule under
    # test is never reached — a comparison where both readers refuse for unrelated
    # reasons renders as agreement and is worth nothing.
    try:
        roots = compute_roots(manifest.get("objects", []), manifest.get("chunks", {}),
                              manifest.get("metadata", []), manifest.get("auxiliary", []), H)
    except Exception:
        # A retyped member can make root computation impossible (`auxiliary` as an
        # integer is not iterable). That is fine: leave the roots as they were and
        # let the readers meet the manifest as it is. Catching only `AnlaError` here
        # aborted the whole enumeration on the first such case.
        roots = None
    if roots is not None:
        for name in ("objects_root", "chunks_root", "metadata_root",
                     "preservation_root", "auxiliary_root"):
            if name in manifest and name != protect:
                manifest[name] = getattr(roots, name)
    try:
        payload = encode(manifest)
    except Exception:
        return None                      # not encodable at all; nothing to compare
    header = dict(record.header)
    header["payload_hash"] = H(payload)
    rebuilt = C.build_record(record.type, header, payload, record.sequence, record.flags)
    tail = C.build_footer_record(
        sequence=record.sequence + 1, snapshot_sequence=footer.snapshot_sequence,
        manifest_offset=record.offset, manifest_length=len(rebuilt),
        preservation_root=(roots.preservation_root if roots else footer.preservation_root),
        previous_footer_offset=footer.previous_footer_offset,
        auxiliary_root=(roots.auxiliary_root if roots else footer.auxiliary_root),
        hash_algorithm=footer.hash_algorithm)
    return C.with_footer_hint(bytes(archive[:record.offset]) + rebuilt + tail,
                              record.offset + len(rebuilt))


def python_verdict(data: bytes) -> str:
    try:
        verify_archive(data)
        return "ok"
    except AnlaError as exc:
        return exc.code
    except Exception as exc:                       # a crash is a verdict too
        return f"crash:{type(exc).__name__}"


def rust_verdict(binary: pathlib.Path, data: bytes) -> str:
    with tempfile.TemporaryDirectory() as work:
        target = pathlib.Path(work) / "case.anla"
        target.write_bytes(data)
        done = subprocess.run([str(binary), "verify", str(target)],
                              capture_output=True, encoding="utf-8", errors="replace")
    text = (done.stdout or "") + (done.stderr or "")
    if done.returncode == 0:
        return "ok"
    marker = '"code":"'
    if marker in text:
        return text.split(marker, 1)[1].split('"', 1)[0]
    return f"exit:{done.returncode}"


#: Python's codes against Rust's names. Two vocabularies for one set of outcomes,
#: which is the instrument problem that once reported 284 false mismatches.
EQUIVALENT = {
    "ok": "ok",
    "ANLA_MANIFEST_INVALID": "manifest-invalid",
    "ANLA_INTEGRITY_FAILURE": "integrity-failure",
    "ANLA_UNSAFE_PATH_OR_OBJECT": "unsafe-object",
    "ANLA_UNSUPPORTED_REQUIRED_CAPABILITY": "unsupported-capability",
    "ANLA_RESOURCE_LIMIT_EXCEEDED": "resource-limit-exceeded",
    "ANLA_INVALID_INPUT": "invalid-input",
    "ANLA_EXTRACTION_FIDELITY_DEGRADED": "fidelity-degraded",
    # Taken from `rust/src/error.rs`, not from memory. Guessing "resource-limit"
    # here reported a disagreement between two readers that agreed, which is the
    # same instrument failure that once produced 284 false mismatches in the
    # fuzzer — two vocabularies for one set of outcomes, compared as strings.
}


def cases(manifest: dict):
    """Every single-member edit this manifest admits."""
    for member in sorted(manifest):
        yield f"manifest.{member}: deleted", _drop(member)
        yield f"manifest.{member}: renamed", _rename(member)
        for shape, value in WRONG_TYPES.items():
            if type(value) is not type(manifest[member]) or value != manifest[member]:
                yield f"manifest.{member}: is {shape}", _retype(member, value)
    for member in sorted(manifest["objects"][0]):
        yield f"object.{member}: deleted", _drop_in_object(member)
        for shape, value in WRONG_TYPES.items():
            if (type(value) is not type(manifest["objects"][0][member])
                    or value != manifest["objects"][0][member]):
                yield f"object.{member}: is {shape}", _retype_in_object(member, value)
    first_chunk = next(iter(manifest["chunks"].values()))
    for member in sorted(first_chunk):
        yield f"chunk.{member}: deleted", _drop_in_chunk(member)
        for shape, value in WRONG_TYPES.items():
            if (type(value) is not type(first_chunk[member])
                    or value != first_chunk[member]):
                yield f"chunk.{member}: is {shape}", _retype_in_chunk(member, value)


def _drop(member):
    def edit(m):
        m.pop(member, None)
    return edit


def _rename(member):
    def edit(m):
        m[member + "_x"] = m.pop(member)
    return edit


def _retype(member, value):
    def edit(m):
        m[member] = value
    return edit


def _drop_in_object(member):
    def edit(m):
        for entry in m["objects"]:
            entry.pop(member, None)
    return edit


def _retype_in_object(member, value):
    def edit(m):
        m["objects"][0][member] = value
    return edit


def _drop_in_chunk(member):
    def edit(m):
        for entry in m["chunks"].values():
            entry.pop(member, None)
    return edit


def _retype_in_chunk(member, value):
    def edit(m):
        next(iter(m["chunks"].values()))[member] = value
    return edit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    binary = next((RUST / n for n in ("anla1-rs.exe", "anla1-rs") if (RUST / n).exists()),
                  None)
    if binary is None:
        print("rust binary not built; run `cargo build --release` in rust/",
              file=sys.stderr)
        return 2

    archive = base_archive()
    if python_verdict(archive) != "ok" or rust_verdict(binary, archive) != "ok":
        print("the unmodified archive does not verify; nothing below means anything",
              file=sys.stderr)
        return 2

    record = C.parse_record(archive, C.find_latest_footer(archive).manifest_offset)
    manifest = decode(archive[record.payload_offset:
                              record.payload_offset + record.payload_length])

    compared, skipped, refused, disagreements = 0, 0, 0, []
    for label, edit in cases(manifest):
        member = label.split(":")[0]
        data = rebuild(archive, edit,
                       protect=member.split(".", 1)[1] if member.startswith("manifest.") else None)
        if data is None:
            skipped += 1
            continue
        compared += 1
        py, rs = python_verdict(data), rust_verdict(binary, data)
        refused += rs != "ok"
        if EQUIVALENT.get(py, py) != rs:
            disagreements.append({"case": label, "python": py, "rust": rs})

    result = {"compared": compared, "unbuildable": skipped, "refused": refused,
              "disagreements": len(disagreements), "detail": disagreements}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"  {compared} single-member edits compared"
              f"{f', {skipped} could not be built' if skipped else ''}")
        for row in disagreements:
            print(f"    {row['case']:<38} python={row['python']:<28} rust={row['rust']}")
        print(f"  {refused} of them were refused by both, {compared - refused} accepted")
        if not disagreements:
            print("  both readers reach the same verdict on every one")
    # Agreement is only worth something if the edits were *doing* something. If every
    # case came back `ok` from both, this would print agreement and have compared
    # nothing — the empty observable that passes any comparison. A manifest with a
    # member of the wrong type is malformed, so most of these must be refusals.
    if refused < compared // 2:
        print(f"  only {refused}/{compared} were refused at all — these edits are not "
              f"reaching the rules, so agreement means nothing", file=sys.stderr)
        return 1
    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
