# -*- coding: utf-8 -*-
"""Structured errors and the exit-code table.

Exit codes follow the table in the ANLA whitepaper (chapter 38) so that the
Python CLI and any later Rust CLI report the same numbers for the same
conditions.
"""

from __future__ import annotations

__all__ = [
    "AnlaError",
    "InvalidInput",
    "UnsupportedCapability",
    "ManifestInvalid",
    "IntegrityFailure",
    "ResourceLimitExceeded",
    "UnsafeObject",
    "FidelityDegraded",
    "EXIT_OK",
]

EXIT_OK = 0


def reportable(value: object) -> object:
    """A detail value that will survive being reported.

    **An error report that raises while reporting is worse than the error it was
    reporting**, and this has now happened twice. First a lone surrogate in a path,
    which `json.dump(..., ensure_ascii=False)` cannot encode; that was fixed at the
    one raise site that produced it. Then a `bytes` object in an object's `kind`,
    found by the differential fuzzer — the reader refused the archive correctly and
    then died formatting the refusal, with nothing left to catch it.

    Fixing it at the raise site fixed one field. Fixing it here fixes every field,
    including the ones nobody has written yet, which is the only version of this fix
    that stays fixed.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return raw.hex() if len(raw) <= 64 else raw[:64].hex() + f"…+{len(raw) - 64}"
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return ascii(value)          # lone surrogates, from a POSIX filename
        return value
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [reportable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): reportable(v) for k, v in value.items()}
    return repr(value)


class AnlaError(Exception):
    """Base class. Carries a stable code and the CLI exit status."""

    code = "ANLA_ERROR"
    exit_code = 1

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def as_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": False,
                "archive_safe": True,
                "details": {str(k): reportable(v) for k, v in self.details.items()},
            }
        }


class InvalidInput(AnlaError):
    code = "ANLA_INVALID_INPUT"
    exit_code = 2


class UnsupportedCapability(AnlaError):
    code = "ANLA_UNSUPPORTED_REQUIRED_CAPABILITY"
    exit_code = 3


class ManifestInvalid(AnlaError):
    code = "ANLA_MANIFEST_INVALID"
    exit_code = 4


class IntegrityFailure(AnlaError):
    code = "ANLA_INTEGRITY_FAILURE"
    exit_code = 5


class ResourceLimitExceeded(AnlaError):
    code = "ANLA_RESOURCE_LIMIT_EXCEEDED"
    exit_code = 8


class UnsafeObject(AnlaError):
    code = "ANLA_UNSAFE_PATH_OR_OBJECT"
    exit_code = 9


class FidelityDegraded(AnlaError):
    code = "ANLA_EXTRACTION_FIDELITY_DEGRADED"
    exit_code = 11
