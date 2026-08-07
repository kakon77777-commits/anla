# -*- coding: utf-8 -*-
"""Metadata namespaces, symbolic links and the fidelity report — Milestone 2.

Everything here is the format layer, so it runs on every platform including the ones
that will not create a symbolic link. `test_fs_1_0.py` covers the filesystem side and
skips where it must; this file cannot skip, because the questions it asks are about
bytes rather than about an operating system.

Two of these tests are the milestone's actual argument.

`test_an_unknown_metadata_namespace_still_verifies` is the one that retired an open
question in the specification. §5.3 guessed `metadata_root` should be split per
namespace so that metadata a reader cannot apply would be "a subtree it reports on
rather than a verification failure". Verification is hashing, not interpretation, so
the failure it was guarding against cannot happen — and this test is what says so.

`test_the_fidelity_report_cannot_be_stripped` is the reason the report is in the
preservation plane. An archive that records what it does not hold, and lets that
record be dropped, is worse than one that never recorded it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla.errors import (  # noqa: E402
    IntegrityFailure,
    InvalidInput,
    ManifestInvalid,
    UnsupportedCapability,
)
from anla1 import container as C  # noqa: E402
from anla1.cbor import encode  # noqa: E402
from anla1.manifest import (  # noqa: E402
    ObjectEntry,
    build_manifest,
    fidelity_of,
    verify_manifest,
    without_auxiliary,
)
from anla1.snapshot import (  # noqa: E402
    SourceEntry,
    append_snapshot,
    extract_snapshot,
    latest_snapshot,
    verify_archive,
)

ARCHIVE_ID = bytes(range(16))
CREATED = 1_785_000_000_000_000_000
H = lambda data: C.hash_bytes(data, C.CORE_HASH)  # noqa: E731


def build(*, objects=(), fidelity=(), files=None, metadata=None):
    return append_snapshot(
        b"", files=files if files is not None else [SourceEntry.of("a.txt", b"a\n")],
        objects=list(objects), fidelity=list(fidelity), metadata=metadata,
        created_unix_ns=CREATED, archive_id=ARCHIVE_ID)


LINK = ObjectEntry(kind="symbolic-link", path="link.txt", target=b"docs/real.txt")


# ---------------------------------------------------------------------------
# symbolic links
# ---------------------------------------------------------------------------

def test_a_symbolic_link_round_trips():
    data = build(objects=[LINK])
    snapshot = latest_snapshot(data)
    verify_archive(data)
    entry = [e for e in snapshot.manifest["objects"] if e["kind"] == "symbolic-link"][0]
    assert entry["path"] == "link.txt"
    assert entry["target"] == b"docs/real.txt"
    # A link carries no content, so extraction must not invent one for it.
    assert "link.txt" not in extract_snapshot(data, snapshot)


@pytest.mark.parametrize("target", [
    b"../../../etc/passwd",         # climbs out
    b"/absolute/path",              # absolute
    b"C:\\Windows\\System32",       # a drive letter and backslashes
    b"does/not/exist",              # dangling
    b"a\\b",                        # a backslash that is part of the name
    bytes([0xFF, 0xFE, 0x80]),      # not valid UTF-8 at all
])
def test_a_link_target_is_stored_exactly_as_given(target):
    """Not normalized, not resolved, not validated.

    A link target is not a name in the archive's namespace — it is an opaque string
    the *target* filesystem interprets. `check_object_path` would rewrite half of
    these and refuse the rest, and either would store a different link than the one
    that was there. Whether such a link may be *created* is a restore-time question,
    because creating it is what makes it dangerous.
    """
    data = build(objects=[ObjectEntry(kind="symbolic-link", path="l", target=target)])
    stored = [e for e in latest_snapshot(data).manifest["objects"]
              if e["kind"] == "symbolic-link"][0]
    assert stored["target"] == target


def test_a_symbolic_link_without_a_target_is_refused():
    with pytest.raises(InvalidInput, match="needs a target"):
        build(objects=[ObjectEntry(kind="symbolic-link", path="l")])


def test_a_link_makes_its_capability_required():
    """Required, not optional: a reader that does not know the kind refuses the
    whole manifest, so the archive should say why rather than let it be obscure."""
    assert "anla:object:symlink:1" in \
        latest_snapshot(build(objects=[LINK])).manifest["required_capabilities"]
    assert "anla:object:symlink:1" not in \
        latest_snapshot(build()).manifest["required_capabilities"]


def test_a_reader_without_the_symlink_capability_refuses():
    manifest = latest_snapshot(build(objects=[LINK])).manifest
    without = frozenset(c for c in C.KNOWN_CAPABILITIES if "symlink" not in c)
    with pytest.raises(UnsupportedCapability, match="capabilities this reader lacks"):
        C.check_capabilities(manifest, without)


# ---------------------------------------------------------------------------
# namespaces
# ---------------------------------------------------------------------------

def test_flat_metadata_is_refused():
    """The shape this milestone replaced. A bare `mtime_ns` gives a reader nowhere
    to record that it did not understand it."""
    with pytest.raises(ManifestInvalid, match="namespace must hold a map"):
        build(files=[SourceEntry("a.txt", lambda: b"a\n",
                                 metadata={"mtime_ns": 1})])


def test_namespaced_metadata_survives_the_round_trip():
    data = build(files=[SourceEntry("a.txt", lambda: b"a\n", metadata={
        "common": {"mtime_ns": 7}, "posix": {"mode": 0o644}})])
    entry = [e for e in latest_snapshot(data).manifest["objects"]
             if e["path"] == "a.txt"][0]
    assert entry["metadata"] == {"common": {"mtime_ns": 7}, "posix": {"mode": 0o644}}


def test_metadata_namespaces_are_optional_capabilities():
    data = build(files=[SourceEntry("a.txt", lambda: b"a\n",
                                    metadata={"posix": {"mode": 0o600}})])
    manifest = latest_snapshot(data).manifest
    assert "anla:metadata:posix:1" in manifest["optional_capabilities"]
    assert "anla:metadata:posix:1" not in manifest["required_capabilities"]


def test_an_unknown_metadata_namespace_still_verifies():
    """The test that retired SPEC-1.0-DRAFT §5.3's open question.

    The draft guessed `metadata_root` should be per namespace so metadata a reader
    cannot apply would be a reported subtree rather than a verification failure.
    But metadata is inside `object_id`, and `object_id` is a hash over canonical
    CBOR: a reader that has never heard of `made-up` computes exactly the same id
    over exactly the same bytes. It verifies. It simply cannot apply what it
    verified — which is a capability question, not a root question.
    """
    data = build(files=[SourceEntry("a.txt", lambda: b"a\n", metadata={
        "made-up-by-someone-else": {"whatever": 1}})])
    snapshot = latest_snapshot(data)
    verify_archive(data)                       # full verification, unknown namespace

    without = frozenset(c for c in C.KNOWN_CAPABILITIES)
    report = C.check_capabilities(snapshot.manifest, without)
    assert "anla:metadata:made-up-by-someone-else:1" in report.ignored_optional
    assert extract_snapshot(data, snapshot) == {"a.txt": b"a\n"}


def test_a_namespace_listed_twice_is_refused():
    manifest = build_manifest(
        archive_id=ARCHIVE_ID, snapshot_sequence=1, created_unix_ns=CREATED,
        objects=[ObjectEntry(kind="directory", path="d")], chunks=(),
        hasher=H, hash_algorithm=C.CORE_HASH,
        metadata=[{"namespace": "common", "entries": []},
                  {"namespace": "common", "entries": []}])
    with pytest.raises(ManifestInvalid, match="appears twice"):
        verify_manifest(manifest, H)


# ---------------------------------------------------------------------------
# the fidelity report
# ---------------------------------------------------------------------------

ABSENT = {"path": "dev/null", "reason": "kind-not-representable",
          "kind": "special file"}


def test_the_report_is_carried_in_the_archive():
    snapshot = latest_snapshot(build(fidelity=[ABSENT]))
    assert fidelity_of(snapshot.manifest) == [ABSENT]
    assert fidelity_of(latest_snapshot(build()).manifest) == []


def test_the_fidelity_report_cannot_be_stripped():
    """Decision 1, made checkable.

    `auxiliary` is the disposable plane: emptying it leaves `preservation_root`
    unchanged, which is the property `anla strip` relies on. A record of what the
    archive does *not* hold must not live there, because dropping it turns a
    declared-incomplete archive into an apparently complete one — worse than either.
    So the report is in the preservation plane, and removing it changes the
    snapshot's identity.
    """
    complete = latest_snapshot(build()).manifest
    incomplete = latest_snapshot(build(fidelity=[ABSENT])).manifest

    # It is inside preservation_root, so the two snapshots are not the same snapshot.
    assert complete["preservation_root"] != incomplete["preservation_root"]

    # And stripping the intelligence plane does not touch it — which is the same
    # check from the other side: `strip` cannot be used to launder the report away.
    stripped = without_auxiliary(incomplete, H)
    assert fidelity_of(stripped) == [ABSENT]
    assert stripped["preservation_root"] == incomplete["preservation_root"]


@pytest.mark.parametrize("entry, match", [
    ({"reason": "kind-not-representable"}, "needs a path"),
    ({"path": "x"}, "needs a reason"),
    ({"path": "x", "reason": "because I said so"}, "unknown fidelity reason"),
    ({"path": "", "reason": "read-failed"}, "needs a path"),
])
def test_a_malformed_fidelity_entry_is_refused(entry, match):
    """A closed set of reasons, because a report nobody can summarise is a report
    nobody reads — and for a record of absence that is the same as not having one."""
    with pytest.raises(ManifestInvalid, match=match):
        build(fidelity=[entry])


def test_a_forged_report_does_not_survive_verification():
    """Adding or removing entries after the fact changes metadata_root."""
    data = build(fidelity=[ABSENT])
    manifest = dict(latest_snapshot(data).manifest)
    manifest["metadata"] = [{"namespace": "fidelity", "entries": []}]
    with pytest.raises(IntegrityFailure, match="metadata_root"):
        verify_manifest(manifest, H)
    # And the bytes it would have to produce are different ones.
    assert encode(manifest) != encode(latest_snapshot(data).manifest)
