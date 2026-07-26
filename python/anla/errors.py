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
                "details": self.details,
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
