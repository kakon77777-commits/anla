# -*- coding: utf-8 -*-
"""Shared fixtures: the language-neutral conformance cases, and the Node bridge."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anla import PackPlan, SourceFile, SourceTree  # noqa: E402
from anla.fastcdc import CdcProfile  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CONFORMANCE = REPO / "conformance"
FIXTURES_FILE = CONFORMANCE / "fixtures.json"
VECTORS = CONFORMANCE / "vectors"
NODE_RUNNER = CONFORMANCE / "run_node.mjs"


@dataclass(frozen=True)
class Case:
    id: str
    tree_name: str
    plan: PackPlan
    archive_uuid: bytes
    created_ns: int
    byte_exact: bool


def _lcg(spec: dict) -> bytes:
    """A pinned linear congruential generator.

    Lets a fixture carry a kilobyte of pseudo-random bytes as two numbers instead
    of a wall of base64, without either implementation inventing its own idea of
    "random". JavaScript must use Math.imul here: a plain 32-bit multiply exceeds
    2**53 and would silently diverge from this.
    """
    state = int(spec["seed"]) & 0xFFFFFFFF
    out = bytearray(int(spec["length"]))
    for index in range(len(out)):
        state = (1103515245 * state + 12345) & 0xFFFFFFFF
        out[index] = (state >> 16) & 0xFF
    return bytes(out)

def _content(entry: dict) -> bytes:
    if "concat" in entry:
        return b"".join(_content(part) for part in entry["concat"])
    if "lcg" in entry:
        return _lcg(entry["lcg"])
    if "text" in entry:
        return entry["text"].encode("utf-8")
    if "base64" in entry:
        return base64.b64decode(entry["base64"])
    if "repeat" in entry:
        pattern = base64.b64decode(entry["repeat"]["pattern_base64"])
        length = entry["repeat"]["length"]
        return (pattern * (length // len(pattern) + 1))[:length]
    raise AssertionError(f"fixture entry has no content: {entry}")


def _path(entry: dict) -> str:
    if "path_codepoints" in entry:
        return "".join(chr(cp) for cp in entry["path_codepoints"])
    return entry["path"]


def load_fixtures() -> dict:
    return json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))


def build_tree(spec: dict) -> SourceTree:
    if "directories_codepoints" in spec:
        directories = ["".join(chr(cp) for cp in cps) for cps in spec["directories_codepoints"]]
    else:
        directories = list(spec.get("directories", []))
    return SourceTree(
        name=spec["name"],
        directories=directories,
        files=[
            SourceFile(path=_path(entry), data=_content(entry),
                       mtime_ns=int(entry["mtime_ns"]) if "mtime_ns" in entry else None)
            for entry in spec.get("files", [])
        ],
    )


def load_cases() -> list[Case]:
    fixtures = load_fixtures()
    cases = []
    for raw in fixtures["cases"]:
        plan_spec = raw["plan"]
        cases.append(Case(
            id=raw["id"],
            tree_name=raw["tree"],
            plan=PackPlan(
                chunk_size=plan_spec["chunk_size"],
                chunking=(CdcProfile(
                    min_size=plan_spec["chunking"]["min"],
                    avg_size=plan_spec["chunking"]["avg"],
                    max_size=plan_spec["chunking"]["max"],
                    normalization=plan_spec["chunking"]["normalization"],
                ) if "chunking" in plan_spec else None),
                compression=plan_spec["compression"],
                deflate_level=plan_spec["deflate_level"],
                exclude_globs=tuple(plan_spec["exclude_globs"]),
                preserve_mtime=plan_spec["preserve_mtime"],
            ),
            archive_uuid=bytes.fromhex(raw["uuid"]),
            created_ns=int(raw["created_ns"]),
            byte_exact=bool(raw["byte_exact_across_implementations"]),
        ))
    return cases


CASES = load_cases()
TREES = load_fixtures()["trees"]


@pytest.fixture(scope="session")
def fixtures() -> dict:
    return load_fixtures()


@pytest.fixture(scope="session")
def cases() -> list[Case]:
    return CASES


@pytest.fixture(scope="session")
def node() -> str:
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node is not on PATH; the cross-implementation tests need it")
    return exe


@pytest.fixture(scope="session")
def node_pack(node, tmp_path_factory) -> dict:
    """Run the JavaScript writer over every fixture case once per session."""
    outdir = tmp_path_factory.mktemp("js-archives")
    result = run_node(node, ["pack", str(outdir)])
    return {"outdir": outdir, "report": result,
            "by_id": {c["id"]: c for c in result["cases"]}}


def run_node_allow_failure(node: str, args: list[str]) -> tuple[int, dict]:
    """Run the Node driver and return its exit status alongside its JSON report."""
    completed = subprocess.run(
        [node, str(NODE_RUNNER), *args],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
        env={**os.environ, "NODE_OPTIONS": ""},
    )
    if not completed.stdout.strip():
        raise AssertionError(
            f"node runner produced no report ({completed.returncode}):\n{completed.stderr}"
        )
    return completed.returncode, json.loads(completed.stdout)


def run_node(node: str, args: list[str]) -> dict:
    code, report = run_node_allow_failure(node, args)
    if code != 0:
        raise AssertionError(
            f"node runner failed ({code}):\n{json.dumps(report, indent=2, ensure_ascii=False)}"
        )
    return report


def pack_case(case: Case):
    from anla import pack
    tree = build_tree(TREES[case.tree_name])
    return pack(tree, case.plan, archive_uuid=case.archive_uuid, created_ns=case.created_ns)
