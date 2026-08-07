# Milestone 2 — metadata namespaces and the fidelity report

Status: **planned, not started.** Written before the code, as with
[Milestone 3](milestone-3-plan.md), so the decisions can be argued with rather than
discovered. That worked: all five of Milestone 3's decisions survived contact with
the implementation, and the two things it got wrong were things it had not thought
about at all.

## What is actually broken today

`anla1 pack` refuses any tree containing a symbolic link. That is the correct
behaviour for a format that cannot represent one — silently omitting it would leave
the archive claiming `Extract(Pack(F, P)) = F` while holding less than it was given
— but it means the tool cannot pack most real projects, including several in this
repository's own family.

`--skip-unsupported` exists and exits 11, so nothing is lost silently. But **the
archive itself has no record of what was left out.** The operator was told once, in
a terminal, on the day. Six months later the archive says nothing. That is the hole
this milestone is really about, and metadata namespaces are the structure that makes
closing it possible rather than the point.

---

## Decision 1 — the fidelity report is in the preservation plane

Not in `auxiliary`. `auxiliary` is the intelligence plane and is defined as
disposable: `D(P, I) = D(P, ∅)`, and `anla strip` empties it. A record of what the
archive does *not* contain must not be droppable, because dropping it converts a
declared incomplete archive into an apparently complete one, which is worse than
either.

So the report is covered by `metadata_root`, and therefore by `preservation_root`.
Removing it changes the snapshot's identity.

This is the same shape as the `snapshot_id` finding in §5.3: what a signature binds
decides what can be quietly rewritten. Here, what a root covers decides what can be
quietly removed.

## Decision 2 — three states, not two

Today an entry is representable or it is not. With namespaces there are three, and
a report that conflates them is useless:

| state | meaning | whose problem |
|---|---|---|
| **stored and applied** | the archive holds it and the restore target took it | nobody's |
| **stored, not applied** | the archive holds it; *this* reader or filesystem cannot use it | the restore environment |
| **not stored** | the writer could not represent it at all | the format's, or the operator's |

"Stored but not applied" is recoverable elsewhere; "not stored" is gone. A report
that says only "these paths are imperfect" has thrown away the distinction that
decides whether you go and get the data again.

The consequence: **the writer records the first two, and only the writer can record
the third.** A reader can always determine "not applied" for itself, so it does not
need to be in the archive; what must be in the archive is what the writer chose not
to keep.

## Decision 3 — namespaced metadata, and **no** per-namespace roots

```text
object.metadata: {"common": {"mtime_ns": …}, "posix": {"mode": …}}
```

`SPEC-1.0-DRAFT.md` §5.3 left open whether `metadata_root` should be per namespace,
and guessed it probably should, so that "metadata a reader cannot apply is a subtree
it reports on rather than a verification failure".

**That premise is wrong, and this plan is where it gets retired.** Verification is
hashing, not interpretation. An object's metadata is already inside `object_id`, and
a reader that has never heard of `posix` computes exactly the same `object_id` over
exactly the same canonical CBOR. It verifies perfectly. It simply cannot *apply*
what it verified. An unknown namespace has never been able to cause a verification
failure, so a root per namespace buys nothing.

The thing that *can* wrongly refuse such an archive is a capability, and that is
where the granularity belongs:

- **metadata namespaces go in `optional_capabilities`, never `required`.** A reader
  that lacks `anla:metadata:posix:1` still verifies, still extracts every byte, and
  reports the namespace as ignored — which `check_capabilities` already returns as
  `ignored_optional` and nothing has yet used.

The only thing a per-namespace root would genuinely enable is dropping a namespace
without disturbing the rest, the way `auxiliary` can be dropped. Metadata is in the
preservation plane; dropping it is loss. So that capability is not wanted either.

Namespaces here: `common` (times), `posix` (mode, symlink target). `windows` is in
the registry and unimplemented, and the registry says so rather than its absence
being inferred.

**Where the fidelity report goes falls out of this.** The manifest already has an
archive-level `metadata` array, covered by `metadata_root`, that has been empty
since it was defined. It is the natural home: `{"namespace": "fidelity", "entries":
[…]}`. No root construction changes, no new member, and the empty slot turns out to
have been waiting for exactly this.

## Decision 4 — a symlink stores its target verbatim and resolves nothing

New object kind `symbolic-link`, carrying the raw target as **bytes**, exactly as the
operating system returned it. Not normalized, not resolved, not validated as a path.

A symlink target is not a path in the archive's namespace — it is an opaque string
the target filesystem interprets. It may be absolute, may escape the tree, may point
at nothing. Rewriting it to be "safe" would store a different link, which is the
`a\b` mistake from §5.2.1 with worse consequences.

**Restoring one is a separate decision from storing one.** A target that is absolute
or escapes the destination is refused on restore by default, because creating it is
what makes it dangerous, and refusing at restore keeps the archive an honest record
of what was there. `--allow-external-links` is the operator saying they meant it.

## Decision 5 — `--skip-unsupported` gets weaker, not stronger

Once symlinks are representable, most of what the flag was for is gone. What remains
— devices, sockets, FIFOs — stays refused by default, and skipping still exits 11,
**but now the omission is written into the archive** rather than only into the exit
code. The flag stops being "trust me" and becomes "record that I did this".

---

## Rejections this milestone owes

| condition | error |
|---|---|
| an unknown namespace in `required_capabilities` | unsupported capability |
| `metadata_roots` disagrees with the namespaces present | integrity failure |
| a namespace listed twice | manifest invalid |
| `symbolic-link` object with no target | manifest invalid |
| restoring a link whose target escapes, without the flag | unsafe object |
| a fidelity report entry with no path or no reason | manifest invalid |
| an archive declaring completeness while carrying a report | manifest invalid |

That last one is the point of the milestone in one line.

## Work order

1. Namespaced metadata and per-namespace roots, with the `metadata_root`
   construction pinned and tested — including a reader that skips a namespace it
   does not know and still verifies everything else.
2. The fidelity report: written by the scanner, covered by `metadata_root`, surfaced
   by `anla1 verify` and `anla1 list` without being asked.
3. `symbolic-link` as an object kind, stored verbatim, restored under policy.
4. POSIX mode. Deliberately after links: mode is a number, links change the object
   model, and doing the easy one first would settle nothing.
5. Re-run `bench/run_bench.py` — a milestone with no measurement is not finished
   ([the standing rule](../bench/run_bench.py)). This one should move no compression
   number at all, and that is worth publishing too: it is the milestone that makes
   the tool able to pack trees it previously refused.

## The freeze rule still applies

Unchanged, and now with more surface: a second implementation has to agree about
namespace ordering, the metadata root construction, and the report's canonical form.
Every one of those is a place two implementations can differ while both look right.
