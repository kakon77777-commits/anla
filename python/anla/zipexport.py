# -*- coding: utf-8 -*-
"""Export a verified archive as a ZIP.

ZIP is the interchange format, not the archival one: it is what you hand to
something that has never heard of ANLA. Entries are stored uncompressed —
the point of the export is fidelity and speed, and the content has already been
through whatever compression the plan chose.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .reader import Archive

__all__ = ["export_zip", "export_zip_bytes"]

_DOS_EPOCH = (1980, 1, 1, 0, 0, 0)


def _zip_time(mtime_ns: str | None) -> tuple[int, int, int, int, int, int]:
    if mtime_ns is None:
        return _DOS_EPOCH
    try:
        moment = datetime.fromtimestamp(int(mtime_ns) / 1_000_000_000, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return _DOS_EPOCH
    if moment.year < 1980:
        return _DOS_EPOCH
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def export_zip_bytes(archive: Archive) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        for obj in archive.manifest["objects"]:
            metadata = obj.get("metadata") or {}
            date_time = _zip_time(metadata.get("mtime_ns"))
            if obj["type"] == "directory":
                info = zipfile.ZipInfo(obj["path"].rstrip("/") + "/", date_time=date_time)
                info.external_attr = (0o040755 << 16) | 0x10
                zf.writestr(info, b"")
                continue
            info = zipfile.ZipInfo(obj["path"], date_time=date_time)
            info.external_attr = 0o100644 << 16
            zf.writestr(info, archive.read(obj["path"]))
    return buffer.getvalue()


def export_zip(archive: Archive, destination: str | Path) -> int:
    data = export_zip_bytes(archive)
    Path(destination).write_bytes(data)
    return len(data)
