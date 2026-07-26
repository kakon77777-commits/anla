# Milestone 3 — append-only snapshots and cross-snapshot deduplication

Status: **implemented in one implementation** — [`python/anla1/snapshot.py`](../python/anla1/snapshot.py),
28 tests. Written before the code so the decisions below could be argued with rather
than discovered afterwards; the record of what implementing them changed is at the
bottom. All five decisions survived. The specification gained §6.1–§6.6 from them and
§4.4 from a defect they did not predict.

`SPEC-1.0-DRAFT.md` §6 specified the footer chain; this document specified the layer
above it, which the draft had left as one line: `S(t+1) = (S(t), ΔO, ΔC, ΔM)`.

## Why this before metadata namespaces

Snapshots are structural: they change what a manifest means, what `verify` has to
walk, and what a chunk descriptor is allowed to point at. Metadata namespaces are
breadth — more fields, same shape. Doing breadth first means doing it twice, once
per snapshot model.

## What already exists

The container layer is done and tested, so none of the byte-level work is new:

- `build_footer_record` / `parse_footer_record` with `previous_footer_offset`
- `find_latest_footer` — scans backwards, never trusts `latest_footer_hint`
- `walk_footers` — enumerates the chain, refuses a cycle, requires descent
- interrupted-append survival: a trailing partial footer reads as the previous
  snapshot rather than as damage
- `parent_snapshot` already accepted by `build_manifest`, and already unused

What is missing is everything that decides *what goes in* the appended snapshot.

---

## Decision 1 — a manifest always describes its whole snapshot

A snapshot's `MANF` lists every object in the tree and every chunk it references,
even chunks whose `CHNK` records were written for an earlier snapshot. It is never a
delta.

The alternative — a manifest listing only what changed — makes extracting snapshot
N require reading all N manifests, and makes `preservation_root` cover a tree the
manifest does not actually contain. A root that describes something not in the
document it is in is not a root.

**So the delta is in the payload records, not in the manifest.** That is where the
bytes are, and it matches the draft's own `ΔC`.

The cost is real: a 100k-file tree re-lists 100k objects per snapshot. Two things
absorb it. `FLAG_COMPRESSED_METADATA` already exists in the container and is
currently set by nothing — this is what gives it a reason. And the objects array is
highly repetitive across snapshots, which is the case compression is good at.

## Decision 2 — `CHNK` records are written once per archive

If a chunk id is already present anywhere in the archive, the new snapshot's
manifest points its descriptor at the existing record. No copy, no rewrite.

This is the whole space saving, and it needs a lookup from chunk id to descriptor
across all prior snapshots. Two ways to get it:

- **walk every prior manifest on append.** Correct, needs nothing new, O(all
  snapshots) per append.
- **an `INDX` record**, cumulative, pointed at by the footer's `index_offset`. The
  record type and the footer fields are already reserved.

Start with the walk. Add `INDX` only when a measurement says the walk is the
bottleneck, and when it arrives it is a **cache**: a reader must produce identical
results with it ignored, and a disagreement between index and manifest is resolved
in favour of the manifest, then reported. A second source of truth that is allowed
to win is a second format.

## Decision 3 — lineage is checked, not decorative

`parent_snapshot` MUST equal the `snapshot_id` of the snapshot the footer chain
points back to. Absent exactly when `snapshot_sequence == 1`. `snapshot_sequence`
MUST be exactly the parent's plus one.

Without this the field is a comment — the same defect the fuzzer found in record
`sequence`, which was specified and checked by nobody.

## Decision 4 — no forward references

A chunk descriptor in snapshot N MUST NOT point at a record offset at or beyond
snapshot N's own `MANF` offset.

In an append-only file every byte a snapshot depends on was written before it. This
makes that arithmetic rather than an assumption, and it is checkable by a reader
holding one manifest and one footer, which is the standard §4.3 established.

## Decision 5 — one chunk id, one descriptor

If two snapshots reference the same chunk id, every field of the descriptor must
agree except nothing — they must be identical. Same content id with different bytes
or different offsets means one of the two is lying about what it stored, and a
content-addressed format cannot shrug at that.

---

## Rejections this milestone owes

Each gets a test before the writer that would produce it exists:

| condition | error |
|---|---|
| `parent_snapshot` absent, `snapshot_sequence > 1` | manifest invalid |
| `parent_snapshot` ≠ previous footer's `snapshot_id` | integrity failure |
| `snapshot_sequence` not previous + 1 | manifest invalid |
| chunk descriptor at or past its own `MANF` offset | manifest invalid |
| same chunk id, differing descriptors across snapshots | integrity failure |
| footer chain cycle | already done |
| chunk record referenced by a later snapshot fails its hash | integrity failure |

## Work order

1. `append_snapshot()` in a new `python/anla1/snapshot.py`: read the existing
   archive's chain, build the chunk-id lookup, write only new `CHNK` records, write
   a complete `MANF`, write a `FOOT` chained to the previous one, update the hint.
2. `read_snapshot(data, sequence)` — extract *any* snapshot, not only the latest.
   Two snapshots of the same tree must restore identical bytes.
3. The rejection table above.
4. `diff(a, b)` over two manifests: objects added, removed, modified, and bytes
   actually appended. Pure derivation from two manifests; no format change.
5. Crash simulation: truncate an append at every 64-byte boundary within the new
   region and assert the archive still reads as the previous snapshot, for every
   truncation point. This is the property the footer chain exists for and it has
   only been tested at a handful of offsets.

---

## What implementing it changed

The five decisions held. Two things they did not anticipate came out of the code, and
both are now in the specification rather than only in this document.

**A writer must resume an append at the end of the newest complete snapshot, not at
the end of the file** — now `SPEC-1.0-DRAFT.md` §4.4 and §6.6. Step 5's crash
simulation was supposed to test only that a torn archive still *reads*; the test that
went one further and appended to a torn archive failed. A torn write leaves the file
at an arbitrary length, so resuming at its end puts every following record at an
offset that is not a multiple of eight — and `find_latest_footer` scans backwards in
alignment-sized steps, so the new footer is never probed. The archive keeps reading
as the older snapshot, every hash in it correct, nothing reporting an error.

This is the third member of a family: `latest_footer_hint`, record `sequence`, and
now record alignment. Each was a rule that looked like a consequence of another rule
— padding implies alignment, the way "strictly increasing" implied checkability — and
each turned out to need its own sentence about how a reader checks it. "Records are
padded to eight bytes" is not "records begin at multiples of eight"; the first is
about what a writer emits and the second is what a reader depends on.

**Deduplication needs a stable chunk-id hash within an archive.** Two hash algorithms
in one archive means two namespaces of chunk id sharing one lookup, so identical bytes
get stored twice and deduplication quietly stops working while everything verifies.
Hash agility is per archive, not per snapshot — §6.2. It is the first boundary the
agility from Milestone 0 has hit, and it comes from content addressing rather than
from the container.

One test bug worth recording because it is the vacuous-assertion shape again: the
content-defined sharing test first used arithmetic content, on which the gear
fingerprint cycles through too few values to satisfy the boundary condition. Every
cut landed on `max_size`, chunking degenerated to fixed-size, a shifted copy shared
nothing — and the test was asserting that it shared almost everything. It failed
loudly, which is the only reason this is a note rather than a defect: an assertion
one constant away from passing vacuously is not a strong test.

## The freeze rule still applies

None of this is frozen when it works. `SPEC-1.0-DRAFT.md` freezes when a second
implementation produces byte-identical archives and the differential fuzzer finds no
verdict divergence. Milestone 3 makes the fuzzer's job larger — a mutated
`previous_footer_offset` is a new class of mutant — and `tools/fuzz_differential.py`
should learn to emit multi-snapshot archives once step 1 exists.
