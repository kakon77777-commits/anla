# Whitepaper Q4 — the object name model

Status: **implemented**, in `SPEC-1.0-DRAFT.md` §5.2.1.1, both implementations, on
2026-08-14. Written before the code, like Milestones 2 and 3, because the answer had
to be argued rather than discovered.

**All four decisions below survived contact with the code.** One was found
incomplete: decision 1 gives `path` and `name` two jobs but never says how they are
related, and unrelated they are *worse than one field* — an archive could carry a
harmless `path` and a traversing `name`, and a reader that prefers `name` would
write outside the destination while one that falls back would not, with every hash
verifying for both. The rule that closes it is **`path` MUST be `derive_path(name)`**,
which decision 2 had already described as a derivation without ever requiring it.
Requiring it also makes §5.2.1's existing path check cover `name`, so the native name
needs no traversal rule of its own.

The Rust reader accepted all four hostile cases until it was told the rule. That is
the second clause of the freeze rule doing exactly what it is for, and it is the
reason step 5 below was written as a step rather than an afterthought.

## What is broken, precisely

A POSIX filename is an arbitrary byte string — anything but NUL and `/`. A Windows
filename is a UTF-16 sequence that may contain unpaired surrogates. **Neither is "a
UTF-8 string."** The manifest's `path` is CBOR text, which must be valid UTF-8, so
there exist real filenames that have no `path` at all.

Today that is not a refusal. It is a crash:

```python
>>> name = b"caf\xe9.txt".decode("utf-8", "surrogateescape")   # what listdir gives you
>>> check_object_path(name)
'caf\udce9.txt'                                                 # accepted
>>> append_snapshot(files=[SourceEntry.of(name, b"x")], ...)
UnicodeEncodeError: 'utf-8' codec can't encode character '\udce9'
```

`check_object_path` checks the *structure* of a path and never asks whether it can
be encoded, so the failure surfaces four layers down in the CBOR encoder as a
traceback. On Linux, one latin-1 filename anywhere in a tree kills the pack.

This is the same shape as every other finding in this repository: **a rule that was
checked for one property and assumed for another.**

---

## Decision 1 — two fields, two jobs

```text
path   the portable name. Always present, always valid UTF-8, always §5.2.1-safe.
name   the native bytes. Present only when they differ from path encoded as UTF-8.
```

`path` is what a reader displays, what a person greps for, and what a restore onto a
*different* platform uses. `name` is what an exact restore on the source platform
uses. Neither can do the other's job, which is why one field was never going to be
enough:

- One UTF-8 string cannot represent a name that is not UTF-8.
- One byte string can, but then every path in every manifest becomes unreadable, and
  the overwhelming majority of names *are* UTF-8. Paying for the rare case in every
  archive is the wrong trade for a format whose manifests are meant to be inspected.

**`name` is absent whenever it would be redundant.** That is not a size
optimisation. It means **`object_id` is unchanged for every object whose name is
already UTF-8**, so answering Q4 does not invalidate a single existing archive that
did not need the answer. The alternative — always emitting `name` — would change
every `object_id` in every archive ever written, to fix a case most of them do not
have.

## Decision 2 — a derived `path` need not be reversible

When the native bytes are not UTF-8, `path` is derived: decode as UTF-8, and replace
each undecodable byte with `%XX`, uppercase hex.

The obvious objection is that this is ambiguous — a file genuinely named `caf%E9.txt`
derives the same `path` as one named `caf<0xE9>.txt`. That is true and it does not
matter, for a reason worth stating rather than working around:

**`path` is not the identity of the object when `name` is present.** `name` is. The
derived `path` is a label, and a label only has to be *unique within the snapshot*,
which the duplicate-path rule (§5.2.1) already enforces. Two objects that derive the
same `path` produce a refusal — loudly, at write time, naming both — and that is the
correct outcome for a preservation format that must never let one file quietly
become another.

So the escaping does not need an escape-the-escape rule. It needs a uniqueness check,
and that check already exists and is already tested.

## Decision 3 — a native name is an *optional* capability

`anla:object:native-name:1`, in `optional_capabilities`.

A reader that ignores `name` restores the file under `path`. The content is intact,
the archive still holds the true name, and what has been lost is the reader's ability
to *apply* it — which is exactly the "stored but not applied" state §5.2.2 already
defines for metadata, and exactly the reason metadata namespaces are optional too.

Requiring it would refuse an archive that such a reader could restore the contents of
perfectly, and refusing a whole archive because one filename is unusual is a worse
failure than restoring it under a portable name and saying so.

**Saying so is required.** A restore that used `path` where `name` was available
MUST report it. That is a `RestoreReport` field, not an archive field, because only
the reader knows it happened.

## Decision 4 — `path` must be *encodable*, and that is checked

`check_object_path` gains the check it never had: `path` must survive
`str.encode("utf-8")`. A lone surrogate is refused there, with the error the caller
is owed, rather than four layers down.

This is the actual bug fix, and it is separable from everything above: even if every
other decision here were rejected, a crash where a refusal is owed is still a defect.

---

## Rejections this owes

| condition | error |
|---|---|
| `path` contains a lone surrogate, or is otherwise not encodable | unsafe object |
| `name` present and equal to `path` encoded — redundant, so non-canonical | manifest invalid |
| `name` present but not a byte string | manifest invalid |
| two objects deriving the same `path` | unsafe object, naming both |
| `name` containing NUL, or empty | unsafe object |

## Work order

1. ~~**The crash fix alone**, with its test. It stands on its own merits.~~
   **Done**, and it turned out not to be alone. The check went into
   `manifest.sorted_by_path` rather than into `check_object_path`'s callers, because
   the encode-in-a-sort-key was written **five times** and every copy assumed. Then
   the read side needed the same distinction and did not have it: a `path` member
   that was *absent* was being reported as an *unsafe path*, a security claim about
   a path that did not exist. Fixing that exposed a third of the same shape, a
   `KeyError` on a missing `hash_algorithms`, and the presence check moved out of
   `verify_manifest` and into `parse_manifest` so downstream code cannot be handed
   an incomplete manifest at all.

   None of the three was reachable by the differential fuzzer, for a reason worth
   more than the fixes: the payload hash is checked before the payload is parsed, so
   no random mutation ever reached the parser. See
   [`hostile-writer-fuzzing.md`](hostile-writer-fuzzing.md). Steps 2–6 below now
   have an instrument that can actually grade them.
2. ~~`name` in the object model, absent when redundant, with the proof that
   `object_id` is unchanged for every UTF-8 name.~~ **Done**, and the proof is an
   equality in `test_native_names_1_0.py` rather than an argument.
3. ~~The derivation, and the collision refusal.~~ **Done.** The collision refusal
   needed no new code — two native names deriving one path is the duplicate-path
   rule, which already existed and already named both offenders.
4. ~~Restore: prefer `name`, fall back to `path`, report the fallback.~~ **Done.**
   Which branch runs is a property of the filesystem, not of the archive: POSIX
   recovers the byte through a surrogate and writes the true name, Windows cannot
   and writes the escaped label. So the test asserts the invariant that holds on
   both — **applied, or reported; never neither** — because asserting either outcome
   would fail on one platform for a reason that is not a defect.
5. ~~Both implementations, and the byte comparison.~~ **Done, and it earned its
   place.** Rust accepted every hostile name — a traversing `name` behind a harmless
   `path`, a redundant one, a text one — until it was taught the rule. The byte
   comparison could not have found this, because the Rust *writer* emits no native
   names: what compares is the rule, via `tools/compare_names.py`, which writes 386
   awkward names from Python and has Rust re-derive every one. Its control forges an
   archive Rust must refuse, so a pass cannot be vacuous — the first version checked
   that *Python* refuses a mismatch, which is true and says nothing about Rust.
6. ~~Re-measure.~~ **Done, and the prediction held exactly**: on the four benchmark
   scenarios whose inputs are fixed, not one of 79 size values moved. The two that
   moved pack the live repository, whose contents this work changed — a property of
   the instrument now recorded on the rows themselves.

## What this does not settle

Whitepaper Q4 also asks about **case-insensitive and normalization-folding target
filesystems** — restoring `A.txt` and `a.txt` onto Windows, or NFC and NFD onto
macOS. That is already handled, and elsewhere: the restore side refuses by device and
inode when two archive paths collide on the target (§5.2.1). This document is about
what a name *is*, not about what a filesystem will accept.
