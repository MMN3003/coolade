"""Generic opaque file_id <-> root-relative-path resolver with realpath containment.

Originally workspace_files.py's resolve_file_id was hardwired to the user
workspace root. Issue I (اصلاحیهٔ ۴) generalizes it into a parametric-root
resolver reused by both /api/workspace/files (root = user workspace) and the
team-memory endpoints (root = /data/teams/<id>/memory) — TECH.md section 8/10:
"generalize the existing opaque file_id resolver (resolve_file_id) to a
parametric-root resolver reused by both workspace and team memory."

`resolve_file_id`/`list_files` never trust the caller's notion of which root is
"allowed" — the caller (workspace_files.py, team_files.py) is responsible for
computing the correct root for the current principal (user id / team id) and
any membership check; this module only enforces that the resolved real path
stays under whatever root it was given.
"""
from __future__ import annotations

import base64
import datetime
import mimetypes
import os
import re
from pathlib import Path


def encode_file_id(relpath: str) -> str:
    return base64.urlsafe_b64encode(relpath.encode()).decode().rstrip("=")


def decode_file_id(file_id: str) -> str | None:
    try:
        padded = file_id + "=" * (-len(file_id) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        return None


def resolve_file_id(root: Path, file_id: str) -> Path | None:
    """Return the real, contained path for file_id under `root`, or None if
    invalid/escaping/missing (TECH.md 8's file_id containment contract)."""
    root_real = Path(os.path.realpath(root))
    relpath = decode_file_id(file_id)
    if not relpath or relpath.startswith("/"):
        return None
    candidate = root / relpath
    real = Path(os.path.realpath(candidate))
    if real != root_real and root_real not in real.parents:
        return None
    if not real.is_file():
        return None
    return real


def resolve_writable_path(root: Path, relpath: str) -> Path | None:
    """Return the real, contained target path for a (possibly not-yet-existing)
    workspace file at `relpath` under `root`, or None if it escapes containment
    (اصلاحیهٔ ۶ / amendment 6: web editor save). Unlike resolve_file_id this does
    NOT require the file to exist, but it enforces the same realpath containment on
    the resolved path AND on its parent, and refuses to overwrite a directory. The
    caller creates parent dirs as needed."""
    if not relpath or relpath.startswith("/") or ".." in Path(relpath).parts:
        return None
    root_real = Path(os.path.realpath(root))
    candidate = root / relpath
    # Resolve the parent (it may not exist yet only up to the last component).
    parent_real = Path(os.path.realpath(candidate.parent))
    if parent_real != root_real and root_real not in parent_real.parents:
        return None
    real = parent_real / candidate.name
    if real.is_dir():
        return None
    return real


class FileEntry:
    def __init__(
        self,
        file_id: str,
        name: str,
        relpath: str,
        size_bytes: int,
        modified_at: datetime.datetime,
    ):
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


def list_files(root: Path) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for r, _dirs, files in os.walk(root):
        for fname in files:
            full = Path(r) / fname
            try:
                stat = full.stat()
            except OSError:
                continue
            relpath = str(full.relative_to(root))
            entries.append(
                FileEntry(
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


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name) or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    return cleaned[:200] or "file"
