"""Opaque file_id <-> workspace-relative-path mapping with realpath containment (TECH.md 8)."""
from __future__ import annotations

import base64
import datetime
import mimetypes
import os
from pathlib import Path

from app.cli_runner import workspace_dir


def encode_file_id(relpath: str) -> str:
    return base64.urlsafe_b64encode(relpath.encode()).decode().rstrip("=")


def _decode_file_id(file_id: str) -> str:
    padded = file_id + "=" * (-len(file_id) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode()


def resolve_file_id(user_id: int, file_id: str) -> Path | None:
    """Return the real, contained path for file_id, or None if invalid/escaping/missing."""
    ws = workspace_dir(user_id)
    ws_real = Path(os.path.realpath(ws))
    try:
        relpath = _decode_file_id(file_id)
    except Exception:
        return None
    if not relpath or relpath.startswith("/"):
        return None
    candidate = ws / relpath
    real = Path(os.path.realpath(candidate))
    if real != ws_real and ws_real not in real.parents:
        return None
    if not real.is_file():
        return None
    return real


class WorkspaceFileEntry:
    def __init__(self, file_id: str, name: str, relpath: str, size_bytes: int, modified_at: datetime.datetime):
        self.file_id = file_id
        self.name = name
        self.relpath = relpath
        self.size_bytes = size_bytes
        self.modified_at = modified_at

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "relpath": self.relpath,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at.isoformat(),
        }


def list_workspace_files(user_id: int) -> list[WorkspaceFileEntry]:
    ws = workspace_dir(user_id)
    entries: list[WorkspaceFileEntry] = []
    for root, _dirs, files in os.walk(ws):
        for fname in files:
            full = Path(root) / fname
            try:
                stat = full.stat()
            except OSError:
                continue
            relpath = str(full.relative_to(ws))
            entries.append(
                WorkspaceFileEntry(
                    file_id=encode_file_id(relpath),
                    name=fname,
                    relpath=relpath,
                    size_bytes=stat.st_size,
                    modified_at=datetime.datetime.fromtimestamp(
                        stat.st_mtime, tz=datetime.timezone.utc
                    ),
                )
            )
    entries.sort(key=lambda e: e.modified_at, reverse=True)
    return entries


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"
