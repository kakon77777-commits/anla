#!/usr/bin/env python3
"""Embed a JSON list of {key, text} rows into vectors.json, via the OpenAI API.

Written by ChatGPT in response to `PROMPT-embeddings.md`, which asks a web-side
assistant to refuse rather than fabricate vectors and to hand back a runnable
script when it cannot embed. It did exactly that, and this is its script — kept
close to as written, because it is good: atomic checkpointed writes, exact key and
order preservation, per-vector width validation, and a batch failure that falls
back to per-row retries so one bad row costs one row.

**One change, and the reason it matters at scale.** The original imported `time`
and never used it, which is the tell that retry was intended and dropped: there was
no handling for a rate limit. With a few thousand rows in batches of 64, a single
429 failed the batch, then failed each of its 64 rows individually, and recorded
all 64 as permanent omissions. A transient throttle became permanent loss — in the
one channel of this system that has no independent check on whether it is complete.
So transient failures now back off and retry, and only genuinely permanent ones
become omissions.

    python -m pip install -U openai
    export OPENAI_API_KEY=...
    python make_vectors.py exported.to-embed.json --output vectors.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "text-embedding-3-small"
DIMENSIONS = 768
DEFAULT_BATCH_SIZE = 64


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        raise ValueError("Input JSON must be a list.")

    checked = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i} is not an object.")
        if "key" not in row or "text" not in row:
            raise ValueError(f"Row {i} must contain exactly usable 'key' and 'text' fields.")
        if not isinstance(row["key"], str) or not isinstance(row["text"], str):
            raise ValueError(f"Row {i}: 'key' and 'text' must both be strings.")
        checked.append(row)
    return checked


#: Retried rather than recorded as an omission. A 400 means this input will never
#: embed and retrying is a waste; a 429 or a 5xx means try again shortly, and
#: treating the two the same is how a rate limit turns into missing data.
TRANSIENT = ("rate", "429", "timeout", "timed out", "connection", "temporarily",
             "500", "502", "503", "504", "overloaded", "unavailable")
MAX_ATTEMPTS = 6


def is_transient(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    if status is not None and 400 <= int(status) < 500:
        return False
    text = f"{type(error).__name__} {error}".lower()
    return any(marker in text for marker in TRANSIENT)


def embed_batch(client: OpenAI, batch):
    for attempt in range(MAX_ATTEMPTS):
        try:
            return _embed_once(client, batch)
        except Exception as error:
            if attempt == MAX_ATTEMPTS - 1 or not is_transient(error):
                raise
            pause = min(60.0, 2.0 ** attempt)
            print(f"  transient ({type(error).__name__}), waiting {pause:.0f}s "
                  f"before attempt {attempt + 2}/{MAX_ATTEMPTS}", file=sys.stderr)
            time.sleep(pause)


def _embed_once(client: OpenAI, batch):
    response = client.embeddings.create(
        model=MODEL,
        dimensions=DIMENSIONS,
        input=[row["text"] for row in batch],
    )
    data = sorted(response.data, key=lambda x: x.index)

    if len(data) != len(batch):
        raise RuntimeError(
            f"API returned {len(data)} embeddings for a batch of {len(batch)} rows."
        )

    out = []
    for row, item in zip(batch, data):
        vector = item.embedding
        if len(vector) != DIMENSIONS:
            raise RuntimeError(
                f"Key {row['key']!r}: expected {DIMENSIONS} dimensions, got {len(vector)}."
            )
        out.append({"key": row["key"], "vector": vector})
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Embed a JSON list of {'key','text'} rows into vectors.json."
    )
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("vectors.json"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive.")

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set.")

    rows = load_rows(args.input_json)
    client = OpenAI()

    payload = {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "vectors": [],
    }
    omissions = []

    # Start with a valid empty checkpoint. It will be replaced after every
    # successfully embedded batch, preserving input order.
    atomic_write_json(args.output, payload)

    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]

        try:
            embedded = embed_batch(client, batch)
            payload["vectors"].extend(embedded)
            atomic_write_json(args.output, payload)
            print(
                f"embedded {min(start + len(batch), len(rows))}/{len(rows)}",
                file=sys.stderr,
            )
            continue
        except Exception as batch_error:
            print(
                f"Batch starting at row {start} failed; retrying rows individually: "
                f"{batch_error}",
                file=sys.stderr,
            )

        # Never truncate or modify text. If one row cannot be embedded as-is,
        # report its exact key and continue with the remaining rows.
        for row in batch:
            try:
                embedded = embed_batch(client, [row])
                payload["vectors"].extend(embedded)
                atomic_write_json(args.output, payload)
            except Exception as row_error:
                omissions.append(
                    {"key": row["key"], "reason": f"{type(row_error).__name__}: {row_error}"}
                )
                print(
                    f"SKIPPED key={row['key']!r}: "
                    f"{type(row_error).__name__}: {row_error}",
                    file=sys.stderr,
                )

    print(f"model: {MODEL}", file=sys.stderr)
    print(f"dimensions: {DIMENSIONS}", file=sys.stderr)
    print(f"rows in: {len(rows)}", file=sys.stderr)
    print(f"vectors out: {len(payload['vectors'])}", file=sys.stderr)

    if omissions:
        print("omissions:", file=sys.stderr)
        for item in omissions:
            print(
                f"  {item['key']}: {item['reason']}",
                file=sys.stderr,
            )
        # Keep vectors.json exactly in the requested schema.
        omissions_path = args.output.with_name(args.output.stem + ".omissions.json")
        atomic_write_json(omissions_path, {"omissions": omissions})
        print(f"omissions file: {omissions_path}", file=sys.stderr)
        raise SystemExit(2)

    print("omissions: none", file=sys.stderr)


if __name__ == "__main__":
    main()
