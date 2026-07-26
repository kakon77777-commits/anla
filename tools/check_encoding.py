# -*- coding: utf-8 -*-
"""Fail if any text I/O in this repository omits an explicit encoding.

Python's text mode defaults to the platform encoding. On a Traditional Chinese
Windows host that is cp950, which cannot represent most of what this repository
contains — so code that reads a paper or writes a manifest without saying
`encoding="utf-8"` works in CI and raises on a real machine. A green Linux run
proves nothing about that, which is exactly why this check exists.

    python tools/check_encoding.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", "dist", "node_modules", ".pytest_cache",
             "_extract", ".wrangler"}

# Calls that open text streams and silently accept the platform default.
TEXT_CALLS = {
    "open": ("mode", "encoding"),
    "read_text": (None, "encoding"),
    "write_text": (None, "encoding"),
    "TextIOWrapper": (None, "encoding"),
}


def is_binary_mode(call: ast.Call) -> bool:
    for index, argument in enumerate(call.args):
        if index == 1 and isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return "b" in argument.value
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return "b" in str(keyword.value.value)
    return False


def has_encoding(call: ast.Call) -> bool:
    return any(keyword.arg == "encoding" for keyword in call.keywords)


def called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def check(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: cannot parse: {exc.msg}"]
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = called_name(node)
        if name not in TEXT_CALLS:
            continue
        if is_binary_mode(node) or has_encoding(node):
            continue
        problems.append(
            f"{path.relative_to(REPO).as_posix()}:{node.lineno}: "
            f"{name}() in text mode without encoding="
        )
    return problems


def main() -> int:
    problems: list[str] = []
    scanned = 0
    for path in sorted(REPO.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        scanned += 1
        problems += check(path)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"checked {scanned} Python files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
