"""Team shared-memory disk layout + file resolver (اصلاحیهٔ ۴ / Issue I, TECH.md
section 3, 5.9, 8, 10).

Disk layout: /data/teams/<team_id>/memory/ (0770, created on first use).
`team_members` is the sole source of truth for who may reach a team's memory —
this module never makes an access decision itself; callers (routers/teams.py,
routers/admin_teams.py, app/cli_runner.py) must do the membership check (or be
admin) before calling in here. Reuses app.file_store's parametric-root resolver
(the same one workspace_files.py uses) so both surfaces share one containment
implementation.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from app.config import get_settings
from app.errors import bad_request
from app.file_store import FileEntry, encode_file_id, guess_mime, list_files, sanitize_filename
from app.file_store import resolve_file_id as _resolve_file_id

settings = get_settings()


def team_root_dir(team_id: int) -> Path:
    return Path(settings.teams_root) / str(team_id)


def team_memory_dir(team_id: int) -> Path:
    """Create-on-first-use, 0770 (TECH.md 5.4/5.9)."""
    root = team_root_dir(team_id)
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o770)
        mem.chmod(0o770)
    except OSError:
        pass
    return mem


def resolve_team_file_id(team_id: int, file_id: str) -> Path | None:
    return _resolve_file_id(team_memory_dir(team_id), file_id)


def list_team_files(team_id: int) -> list[FileEntry]:
    return list_files(team_memory_dir(team_id))


def save_uploaded_file(team_id: int, filename: str, data: bytes) -> FileEntry:
    """Write (or overwrite) a file directly under the team's memory dir.

    Concurrency (TECH.md 5.9): last-writer-wins per file, no lock — sessions are
    short-lived/per-message so real same-file collisions are rare, and the write
    below is atomic-per-file (full bytes written, then the fd is closed), so no
    reader ever observes a half-written file. Intentionally NOT uuid-prefixed
    (unlike conversation attachments) so re-uploading the same filename overwrites
    the previous version, matching the documented last-writer-wins semantics.
    """
    safe_name = sanitize_filename(filename)
    dest = team_memory_dir(team_id) / safe_name
    dest.write_bytes(data)
    stat = dest.stat()
    return FileEntry(
        file_id=encode_file_id(safe_name),
        name=safe_name,
        relpath=safe_name,
        size_bytes=stat.st_size,
        modified_at=datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc),
    )


async def receive_upload(team_id: int, file) -> FileEntry:
    """Shared read + size-check + save for both the member (routers/teams.py) and
    admin (routers/admin_teams.py) upload endpoints."""
    max_bytes = settings.max_upload_bytes
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise bad_request("حجم فایل بیش از سقف مجاز است.")
    return save_uploaded_file(team_id, file.filename or "file", content)


__all__ = [
    "guess_mime",
    "list_team_files",
    "receive_upload",
    "resolve_team_file_id",
    "save_uploaded_file",
    "team_memory_dir",
    "team_root_dir",
]
