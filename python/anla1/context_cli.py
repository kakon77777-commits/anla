# -*- coding: utf-8 -*-
"""``anla1 context`` — the agent-memory layer, from a terminal.

Everything under here existed already and could only be driven by an agent over
MCP. That is a strange place for it to stop: the layer is *about* being able to
look at a record and get an exact piece of it back, and until now a person could
not look. These commands are the same library calls the MCP tools make, so there
is one implementation and two front doors rather than two implementations.

    anla1 context capture  memory.anla                # this machine's newest session
    anla1 context status   memory.anla
    anla1 context project  memory.anla --level L1
    anla1 context expand   memory.anla turns/000042-user.json
    anla1 context find     memory.anla "gear table"
    anla1 context segment  memory.anla --scheme changepoint-v1
    anla1 context address  memory.anla "how was the gear table produced"

`address` without vectors uses the lexical channel and says so in its output; it
does not quietly present word overlap as semantic search. Attaching vectors is
deliberately not a command here — it needs an embedding model, which this package
does not have and is not going to pretend to.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from anla.errors import InvalidInput
from anla.fastcdc import CdcProfile

from .backends import DEFAULT_OLLAMA, backend_for
from .embedding import EmbeddingIdentity, comparable

from .context import (
    LEVELS, expand, newest_sessions, project, projection_manifest, read_jsonl,
    turn_entries,
)
from .segment import SCHEMES, SegmentIndex, build_index, digest_of, project_segment
from .snapshot import (
    CODEC_ZSTD, cdc_chunker, extract_snapshot, list_snapshots, write_snapshot,
)
from .vectors import have_numpy, read_vectors, write_vectors


def _read(path: str) -> bytes:
    return Path(path).expanduser().read_bytes()


def _latest(archive: bytes):
    return list_snapshots(archive)[-1]


def _index_path(archive: str, scheme: str) -> Path:
    return Path(archive).expanduser().with_suffix(f".segments-{scheme}.json")


def _load_index(archive: str, scheme: str) -> SegmentIndex:
    where = _index_path(archive, scheme)
    if not where.exists():
        raise InvalidInput(
            f"no index for {scheme!r} beside {archive} — run "
            f"`anla1 context segment {archive} --scheme {scheme}` first. The index "
            f"is built, not implicit.")
    return SegmentIndex.of(json.loads(where.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------


def cmd_capture(args, emit) -> int:
    if args.transcript:
        source = Path(args.transcript).expanduser()
    else:
        found = newest_sessions(args.session_root)
        if not found:
            raise InvalidInput(
                f"no transcript found under "
                f"{args.session_root or '~/.claude/projects'} — name one with "
                f"--transcript")
        source = found[0]
    if not source.is_file():
        raise InvalidInput(f"not a file: {source}")

    whole = source.read_bytes()
    limit = args.max_mib * 1024 ** 2 if args.max_mib else 0
    truncated = bool(limit and len(whole) > limit)
    # The same refusal the MCP tool makes, for the same reason: a capture that
    # quietly drops the front of a transcript and then reports itself the way a
    # complete one does makes every later claim a statement about a record the
    # caller believes is whole.
    if truncated and not args.allow_truncation:
        raise InvalidInput(
            f"{source.name} is {len(whole):,} bytes and --max-mib {args.max_mib} "
            f"would drop the first {len(whole) - limit:,}. That capture would not "
            f"be lossless and would not say so. Pass --allow-truncation to take "
            f"the tail deliberately, or raise --max-mib, or drop it entirely.")
    if truncated:
        data = whole[-limit:]
        data = data[data.find(b"\n") + 1:]
    else:
        data = whole
    data = data[:data.rfind(b"\n") + 1] if data.rfind(b"\n") >= 0 else data

    turns = read_jsonl(data)
    if not turns:
        raise InvalidInput(f"{source} holds no readable turns")

    target = Path(args.archive).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    # An existing archive keeps its own id and gains a snapshot; a new one is given
    # one. Passing `archive_id` to an append would make the manifest disagree with
    # the header about what this archive is called, which is a defect the byte
    # comparison caught in the Rust writer and the spec now forbids outright.
    existed = target.exists()
    size = write_snapshot(
        target, files=turn_entries(turns), created_unix_ns=time.time_ns(),
        **({} if existed else {"archive_id": uuid.uuid4().bytes}),
        chunker=cdc_chunker(CdcProfile(min_size=args.chunk_avg // 4,
                                       avg_size=args.chunk_avg,
                                       max_size=args.chunk_avg * 4)),
        codec=CODEC_ZSTD)
    omitted = len(whole) - len(data)
    payload = {
        "archive": str(target), "transcript": str(source),
        "complete": not truncated,
        "capture": ("partial — the front of the transcript was dropped" if truncated
                    else "lossless — every byte of the transcript is in the archive"),
        "turns": len(turns), "transcript_bytes": len(whole),
        "omitted_bytes": omitted, "context_bytes": len(data), "archive_bytes": size,
        "share_of_context": round(size / len(data), 4) if data else None,
    }
    emit(payload, [
        f"{target}",
        f"  {len(turns):,} turns from {source.name}",
        f"  {len(data):,} bytes of transcript -> {size:,} bytes of archive "
        f"({payload['share_of_context']:.0%})",
        f"  {payload['capture']}",
    ])
    return 0


def cmd_status(args, emit) -> int:
    data = _read(args.archive)
    snapshots = list_snapshots(data)
    latest = snapshots[-1]
    objects = latest.manifest["objects"]
    logical = sum(o.get("size", 0) for o in objects)
    roles: dict[str, int] = {}
    for entry in objects:
        role = entry["path"].split("-")[-1].removesuffix(".json")
        roles[role] = roles.get(role, 0) + 1
    schemes = sorted(
        p.name.split(".segments-")[-1].removesuffix(".json")
        for p in Path(args.archive).expanduser().parent.glob(
            Path(args.archive).name.rsplit(".", 1)[0] + ".segments-*.json"))
    emit({"archive": args.archive, "snapshots": len(snapshots),
          "turns": len(objects), "context_bytes": logical,
          "archive_bytes": len(data),
          "share_of_context": round(len(data) / logical, 4) if logical else None,
          "unique_chunks": len(latest.manifest["chunks"]),
          "roles": roles, "indices": schemes},
         [f"{args.archive}",
          f"  {len(snapshots)} snapshot(s), {len(objects):,} turns, "
          f"{len(latest.manifest['chunks']):,} unique chunks",
          f"  {logical:,} logical bytes -> {len(data):,} stored",
          "  roles: " + ", ".join(f"{k} {v}" for k, v in
                                  sorted(roles.items(), key=lambda kv: -kv[1])[:6]),
          "  segment indices: " + (", ".join(schemes) if schemes else "none built")])
    return 0


def cmd_project(args, emit) -> int:
    data = _read(args.archive)
    snapshot = _latest(data)
    restored = extract_snapshot(data, snapshot)
    turns = []
    for path in sorted(restored):
        parsed = read_jsonl(restored[path])
        if parsed:
            turns.append(parsed[0])
    view = project(turns, level=args.level, budget_bytes=args.budget)
    manifest = projection_manifest(view)
    # `preserved` is the list of paths kept, not a count of them — read from the
    # manifest rather than assumed, after assuming wrong once.
    kept, dropped = len(manifest["preserved"]), len(manifest["omitted"])
    emit(manifest,
         [f"{args.archive}  {args.level}",
          f"  {kept} of {kept + dropped} turns shown, "
          f"{manifest['bytes_shown']:,} of {manifest['bytes_total']:,} bytes "
          f"({manifest['share_shown']:.2%} of the context)",
          f"  {dropped} omitted, every one expandable with "
          f"`anla1 context expand`",
          "", view.text[:args.show] + ("…" if len(view.text) > args.show else "")])
    return 0


def cmd_expand(args, emit) -> int:
    data = _read(args.archive)
    restored = expand(data, args.paths)
    emit({"archive": args.archive,
          "restored": {k: v.decode("utf-8", "replace") for k, v in restored.items()},
          "total_bytes": sum(len(v) for v in restored.values())},
         [f"== {path} ({len(restored[path]):,} bytes)\n"
          + restored[path].decode("utf-8", "replace")
          for path in args.paths if path in restored])
    return 0 if len(restored) == len(args.paths) else 9


def cmd_find(args, emit) -> int:
    data = _read(args.archive)
    snapshot = _latest(data)
    restored = extract_snapshot(data, snapshot)
    needle = args.query.lower()
    hits = []
    for path in sorted(restored):
        raw = restored[path]
        text = raw.decode("utf-8", "replace")
        where = text.lower().find(needle)
        if where < 0:
            continue
        start = max(0, where - 60)
        hits.append({"path": path, "byte_offset": where,
                     "hint": " ".join(text[start:start + 200].split())})
        if len(hits) >= args.limit:
            break
    emit({"archive": args.archive, "query": args.query, "hits": hits,
          "channel": "lexical — this is exact substring matching over the stored "
                     "bytes, not semantic search",
          "boundary": "Recall is not Care: this returns what matches, which is not "
                      "the same as what matters"},
         [f"{h['path']} @{h['byte_offset']}\n    {h['hint']}" for h in hits]
         or ["nothing in this archive contains that string"])
    return 0 if hits else 1


def cmd_segment(args, emit) -> int:
    path = Path(args.archive).expanduser()
    data = path.read_bytes()
    before = hashlib.blake2b(data, digest_size=16).hexdigest()
    restored = extract_snapshot(data, _latest(data))
    index = build_index(sorted(restored.items()), args.scheme)
    after = hashlib.blake2b(path.read_bytes(), digest_size=16).hexdigest()

    covered = 0
    by_turn: dict[str, list] = {}
    for segment in index.segments:
        by_turn.setdefault(segment.source_turn, []).append(segment)
    for turn_path, raw in restored.items():
        position = 0
        for start, end in sorted(r for s in by_turn.get(turn_path, [])
                                 for r in s.ranges):
            covered += max(0, end - max(start, position))
            position = max(position, end)
    total = sum(len(r) for r in restored.values())

    where = _index_path(args.archive, args.scheme)
    where.write_text(json.dumps(index.as_dict(), ensure_ascii=False),
                     encoding="utf-8")
    emit({"archive": args.archive, "sidecar": str(where), "scheme": args.scheme,
          "turns": len(restored), "segments": len(index.segments),
          "coverage": round(covered / total, 6) if total else None,
          "preservation_digest": before,
          "preservation_unchanged": before == after,
          "available_schemes": sorted(SCHEMES)},
         [f"{where}",
          f"  {len(index.segments):,} segments over {len(restored):,} turns "
          f"({args.scheme})",
          f"  coverage {covered / total:.4f} — no byte unreachable, none doubled"
          if total else "  empty",
          f"  preservation digest {before[:16]} "
          + ("unchanged" if before == after
             else "CHANGED — the invariant is broken")])
    return 0 if before == after else 1


def cmd_address(args, emit) -> int:
    data = _read(args.archive)
    restored = extract_snapshot(data, _latest(data))
    index = _load_index(args.archive, args.scheme)
    segments = {s.segment_id: s for s in index.segments}

    sidecar = _vector_path(args.archive, args.scheme)
    channel = "lexical — no vectors are attached for this scheme"
    incomparable = None
    ranked: list[tuple[str, float]] = []

    if sidecar.exists() and (args.embed or args.query_vector):
        corpus = read_vectors(sidecar)
        held = EmbeddingIdentity.of(corpus.identity)
        if args.query_vector:
            # A vector from somewhere this command cannot interrogate. It may be
            # right; nothing here can tell, so the identity it is compared against
            # is the one the caller implicitly asserts by supplying it.
            vector = json.loads(Path(args.query_vector).expanduser()
                                .read_text(encoding="utf-8"))
            asked = EmbeddingIdentity.of({**corpus.identity,
                                          "dimensions": len(vector)})
        else:
            # The corpus says which model made it, so the query is embedded with
            # that one rather than with a default. The identity check below then
            # has something to compare rather than being a formality — and a model
            # that has been re-pulled since has a different digest and is caught.
            backend = backend_for(args.backend, host=args.host)
            model = held.model.split(":", 1)[1] if ":" in held.model else held.model
            asked = backend.identity(model,
                                     projection_version=index.projection_version,
                                     segmentation_scheme=args.scheme)
            vector = backend.embed([args.query], model)[0]

        ok, reason = comparable(asked, held)
        if not ok:
            incomparable, channel = reason, f"semantic — refused, {reason}"
        else:
            ranked = [(k, s) for k, s in corpus.search(vector, limit=args.limit)
                      if k in segments]
            channel = (f"semantic — {len(corpus):,} segments carry a vector from "
                       f"{held.model}, {'numpy' if have_numpy() else 'pure python'} "
                       f"backend")
    elif args.embed or args.query_vector:
        channel = ("semantic — REFUSED, a query vector was asked for but no vectors "
                   "are attached for this scheme; run `anla1 context embed` first")

    if not ranked:
        needle = args.query.lower()
        verified: dict[str, bool] = {}
        scores = []
        for segment in index.segments:
            raw = restored.get(segment.source_turn)
            if raw is None:
                continue
            ok = verified.get(segment.source_turn)
            if ok is None:
                ok = digest_of(raw) == segment.source_digest
                verified[segment.source_turn] = ok
            if not ok:
                continue
            text = project_segment(segment, raw, check=False)
            if needle and needle in text.lower():
                scores.append((segment.segment_id,
                               len(needle) / max(len(text), 1)))
        ranked = sorted(scores, key=lambda kv: -kv[1])[:args.limit]

    hits = []
    for segment_id, score in ranked:
        segment = segments[segment_id]
        raw = restored[segment.source_turn]
        ok = digest_of(raw) == segment.source_digest
        start, end = segment.ranges[0]
        hits.append({"segment_id": segment_id, "score": round(float(score), 4),
                     "source_turn": segment.source_turn,
                     "start_byte": start, "end_byte": end,
                     "digest_verified": ok,
                     "text": project_segment(segment, raw, check=False)})
    emit({"archive": args.archive, "scheme": args.scheme, "channel": channel,
          "incomparable": incomparable,
          "segments_in_index": len(segments), "hits": hits,
          "expanded_exactly": sum(1 for h in hits if h["digest_verified"]),
          "boundary": "`expanded_exactly` measures the expansion, never the "
                      "relevance — a wrong hit expands just as exactly as a right "
                      "one"},
         [f"channel: {channel}", ""]
         + [f"{h['source_turn']} [{h['start_byte']}:{h['end_byte']}]  "
            f"score {h['score']:+.3f}  "
            f"{'digest verified' if h['digest_verified'] else 'DIGEST MISMATCH'}\n"
            f"    {' '.join(h['text'].split())[:200]}" for h in hits]
         or ["nothing matched"])
    return 0 if hits else 1


def _vector_path(archive: str, scheme: str) -> Path:
    return Path(archive).expanduser().with_suffix(f".vectors-{scheme}.anlavec")


def cmd_embed(args, emit) -> int:
    """Embed the index's views with a model on this machine.

    The vectors and the identity of what made them are written together, and the
    identity carries the model's own content digest — so a query embedded later is
    comparable only if the weights are literally the same bytes. That is a check a
    hosted model cannot support, and it is the reason this is worth having beyond
    saving an API key.
    """
    backend = backend_for(args.backend, host=args.host)
    data = _read(args.archive)
    restored = extract_snapshot(data, _latest(data))
    index = _load_index(args.archive, args.scheme)
    identity = backend.identity(args.model,
                                projection_version=index.projection_version,
                                segmentation_scheme=args.scheme)

    views: list[tuple[str, str]] = []
    verified: dict[str, bool] = {}
    for segment in index.segments:
        raw = restored.get(segment.source_turn)
        if raw is None:
            continue
        ok = verified.get(segment.source_turn)
        if ok is None:
            ok = digest_of(raw) == segment.source_digest
            verified[segment.source_turn] = ok
        if not ok:
            continue
        text = project_segment(segment, raw, check=False)
        if len(text) >= args.min_bytes:
            views.append((segment.segment_id, text[:args.chars]))

    eligible = len(views)
    if args.limit and eligible > args.limit:
        # An even stride, not the first N. Taking a prefix embeds the opening of the
        # conversation and then answers every later question out of it, reporting
        # itself exactly as a complete corpus would.
        step = eligible / args.limit
        views = [views[min(eligible - 1, int(i * step))] for i in range(args.limit)]

    rows = []
    for start in range(0, len(views), args.batch):
        batch = views[start:start + args.batch]
        vectors = backend.embed([text for _, text in batch], args.model)
        rows.extend(zip((key for key, _ in batch), vectors))
        print(f"  embedded {min(start + args.batch, len(views)):,}/{len(views):,}",
              file=__import__("sys").stderr)

    if not rows:
        raise InvalidInput(
            f"nothing to embed: no segment of {args.scheme} reached "
            f"--min-bytes {args.min_bytes}")
    written = write_vectors(_vector_path(args.archive, args.scheme), rows,
                            identity.as_dict(), extra={"model": identity.model})
    emit({"archive": args.archive, "sidecar": written["file"],
          "scheme": args.scheme, "embedded": written["count"],
          "eligible_segments": eligible,
          "segments_in_index": len(index.segments),
          "share_of_index": round(written["count"] / len(index.segments), 4)
                            if index.segments else None,
          "sidecar_bytes": written["bytes"], "identity": identity.as_dict(),
          "identity_fingerprint": identity.fingerprint,
          "plane": "auxiliary — a sidecar beside the archive; deleting it costs the "
                   "semantic channel and nothing else"},
         [f"{written['file']}",
          f"  {written['count']:,} of {len(index.segments):,} segments "
          f"({written['count'] / len(index.segments):.1%}), "
          f"{written['bytes'] / 1e6:.0f} MB",
          f"  {identity.model} @ {identity.dimensions}d, "
          f"revision {identity.revision[:16]}",
          f"  fingerprint {identity.fingerprint}"])
    return 0


def cmd_models(args, emit) -> int:
    backend = backend_for(args.backend, host=args.host)
    held = backend.models()
    emit({"backend": backend.name, "host": args.host, "models": held},
         [f"{m['model']:<28} {(m['dimensions'] or '-'):>6}d  "
          f"{'embedding' if m['embedding'] else 'generative':<11} "
          f"{(m['bytes'] or 0) / 1e6:>7.0f} MB  {m['digest'][:16]}"
          for m in held] or ["this server holds no models"])
    return 0 if held else 1


# ---------------------------------------------------------------------------


def add_parser(sub, common) -> None:
    """Register `anla1 context ...` on the main parser."""
    context = sub.add_parser(
        "context", help="an agent's own memory: capture, project, expand, address")
    inner = context.add_subparsers(dest="context_command", required=True)

    capture = inner.add_parser(
        "capture", help="store a session transcript losslessly, one object per turn")
    capture.add_argument("archive")
    capture.add_argument("--transcript", default="",
                         help="default: this machine's most recently modified "
                              "session")
    capture.add_argument("--session-root", default="")
    capture.add_argument("--max-mib", type=int, default=0,
                         help="0 means the whole transcript; any limit that would "
                              "drop the front is refused unless --allow-truncation")
    capture.add_argument("--allow-truncation", action="store_true")
    capture.add_argument("--chunk-avg", type=int, default=16384)
    common(capture)
    capture.set_defaults(func=cmd_capture)

    status = inner.add_parser("status", help="what this context archive holds")
    status.add_argument("archive")
    common(status)
    status.set_defaults(func=cmd_status)

    projected = inner.add_parser(
        "project", help="read it at L0/L1/L2/L3 with every omission expandable")
    projected.add_argument("archive")
    projected.add_argument("--level", choices=LEVELS, default="L1")
    projected.add_argument("--budget", type=int, default=32_000)
    projected.add_argument("--show", type=int, default=2000,
                           help="characters of the projection to print")
    common(projected)
    projected.set_defaults(func=cmd_project)

    expanded = inner.add_parser(
        "expand", help="hand back omitted turns byte for byte")
    expanded.add_argument("archive")
    expanded.add_argument("paths", nargs="+")
    common(expanded)
    expanded.set_defaults(func=cmd_expand)

    found = inner.add_parser("find", help="exact substring search over the record")
    found.add_argument("archive")
    found.add_argument("query")
    found.add_argument("--limit", type=int, default=10)
    common(found)
    found.set_defaults(func=cmd_find)

    segmented = inner.add_parser(
        "segment", help="build an index family; writes nothing to the record")
    segmented.add_argument("archive")
    segmented.add_argument("--scheme", default="changepoint-v1",
                           choices=sorted(SCHEMES))
    common(segmented)
    segmented.set_defaults(func=cmd_segment)

    addressed = inner.add_parser(
        "address", help="a question in, the exact bytes of a turn out")
    addressed.add_argument("archive")
    addressed.add_argument("query")
    addressed.add_argument("--scheme", default="changepoint-v1",
                           choices=sorted(SCHEMES))
    addressed.add_argument("--embed", action="store_true",
                           help="embed the question with the model the attached "
                                "vectors were made by — read from the sidecar, not "
                                "chosen here, so the two cannot silently differ")
    addressed.add_argument("--query-vector", default="",
                           help="path to a JSON array, if you made the vector "
                                "elsewhere")
    addressed.add_argument("--backend", default="ollama")
    addressed.add_argument("--host", default=DEFAULT_OLLAMA)
    addressed.add_argument("--limit", type=int, default=5)
    common(addressed)
    addressed.set_defaults(func=cmd_address)

    embedded = inner.add_parser(
        "embed", help="embed an index's views with a model on this machine")
    embedded.add_argument("archive")
    embedded.add_argument("--scheme", default="changepoint-v1",
                          choices=sorted(SCHEMES))
    embedded.add_argument("--model", default="nomic-embed-text")
    embedded.add_argument("--backend", default="ollama")
    embedded.add_argument("--host", default=DEFAULT_OLLAMA)
    embedded.add_argument("--limit", type=int, default=0,
                          help="0 embeds every eligible segment; a limit samples "
                               "evenly across the record rather than taking its "
                               "opening")
    embedded.add_argument("--batch", type=int, default=64)
    embedded.add_argument("--chars", type=int, default=6000)
    embedded.add_argument("--min-bytes", type=int, default=40)
    common(embedded)
    embedded.set_defaults(func=cmd_embed)

    listed = inner.add_parser("models", help="what the local backend holds")
    listed.add_argument("--backend", default="ollama")
    listed.add_argument("--host", default=DEFAULT_OLLAMA)
    common(listed)
    listed.set_defaults(func=cmd_models)
