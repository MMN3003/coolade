"""Opaque file_id <-> workspace-relative-path mapping with realpath containment
(TECH.md 8). Thin wrapper over app.file_store's parametric-root resolver, root =
this user's workspace dir — generalized in اصلاحیهٔ ۴ / Issue I so the same
resolver is reused for team memory (see app/team_files.py)."""
from __future__ import annotations

from pathlib import Path

from app.cli_runner import workspace_dir
from app.file_store import FileEntry, encode_file_id, guess_mime, list_files
from app.file_store import resolve_file_id as _resolve_file_id

# Backward-compat alias — previously a workspace-specific class.
WorkspaceFileEntry = FileEntry


def resolve_file_id(user_id: int, file_id: str) -> Path | None:
    return _resolve_file_id(workspace_dir(user_id), file_id)


def list_workspace_files(user_id: int) -> list[FileEntry]:
    return list_files(workspace_dir(user_id))


__all__ = [
    "WorkspaceFileEntry",
    "encode_file_id",
    "guess_mime",
    "list_workspace_files",
    "resolve_file_id",
]
