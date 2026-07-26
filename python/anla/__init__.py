# -*- coding: utf-8 -*-
"""ANLA — Agent-Native Lossless Archive, reference implementation of ANLA-MVP v0.1.

    from anla import PackPlan, collect_tree, pack, open_archive

    tree = collect_tree("my-project")
    result = pack(tree, PackPlan(chunk_size=1 << 20, compression="auto"))
    archive = open_archive(result.data)          # verifies on open
    archive.extract_to("restored")

The format is specified in SPEC.md at the repository root. This package is
written against that document, not against the JavaScript implementation in
web/anla-core.js; the conformance suite is what holds the two together.
"""

from __future__ import annotations

from .canonical import canonical, canonical_bytes
from .errors import (
    AnlaError,
    FidelityDegraded,
    IntegrityFailure,
    InvalidInput,
    ManifestInvalid,
    ResourceLimitExceeded,
    UnsafeObject,
    UnsupportedCapability,
)
from .format import (
    ARCHIVE_MAGIC,
    CODECS,
    FOOTER_MAGIC,
    FOOTER_SIZE,
    FORMAT_NAME,
    FORMAT_VERSION,
    HEADER_SIZE,
    RECORD_FRAME_SIZE,
    RECORD_MAGIC,
    VERSION_MAJOR,
    VERSION_MINOR,
    safe_path,
)
from .reader import Archive, ExtractionReport, Limits, open_archive
from .writer import PackPlan, PackResult, SourceFile, SourceTree, collect_tree, pack
from .zipexport import export_zip, export_zip_bytes

__version__ = "0.1.0"
__format__ = f"{FORMAT_NAME} {FORMAT_VERSION}"

__all__ = [
    "__version__", "__format__",
    "PackPlan", "PackResult", "SourceFile", "SourceTree", "collect_tree", "pack",
    "Archive", "ExtractionReport", "Limits", "open_archive",
    "export_zip", "export_zip_bytes",
    "canonical", "canonical_bytes", "safe_path",
    "AnlaError", "InvalidInput", "UnsupportedCapability", "ManifestInvalid",
    "IntegrityFailure", "ResourceLimitExceeded", "UnsafeObject", "FidelityDegraded",
    "ARCHIVE_MAGIC", "RECORD_MAGIC", "FOOTER_MAGIC",
    "HEADER_SIZE", "RECORD_FRAME_SIZE", "FOOTER_SIZE",
    "VERSION_MAJOR", "VERSION_MINOR", "FORMAT_NAME", "FORMAT_VERSION", "CODECS",
]
