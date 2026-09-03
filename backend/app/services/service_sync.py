"""DS6 (docs/SERVICES-V2.md ب-۵) — sync granted services into a chat turn.

The general-chat CLI runs in-process with cwd = the user's workspace dir, so
everything is PROJECT-scope there:
  * skills   → <ws>/.claude/skills/eco-svc-<slug>/   (from /data/services/<slug>/<ver>/)
  * builder  → <ws>/.claude/skills/eco-service-builder/  (admins only, shipped asset)
  * mcp      → <ws>/.ecocode/mcp.json with a fresh short-lived turn key
                (org_services.mint_turn_key), passed to the CLI via --mcp-config.

A version marker (<ws>/.ecocode/services-state.json) makes the copy step a
no-op when nothing changed. Revocation never depends on this file — the
gateway re-checks the grant on every call (ب-۳); stale synced skills are
removed on the next turn anyway.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import async_session_factory
from app.models import Service, ServiceGrant, User, UserRole
from app.services import org_services

settings = get_settings()

SKILL_PREFIX = "eco-svc-"
BUILDER_SLUG = "_admin"
BUILDER_SKILL_DIRNAME = "eco-service-builder"
_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "skills"
BUILDER_ASSET = _ASSETS / BUILDER_SKILL_DIRNAME
BUILDER_VERSION = 1  # bump when the shipped asset changes
# Token-economy: the personal-memory skill ships to EVERY user (CLAUDE.md in the
# workspace root is natively auto-loaded by the CLI each turn — cross-chat memory
# that makes starting a cheap new conversation painless).
MEMORY_SLUG = "_memory"
MEMORY_SKILL_DIRNAME = "eco-memory"
MEMORY_ASSET = _ASSETS / MEMORY_SKILL_DIRNAME
MEMORY_VERSION = 1


async def sync_service_access(user_id: int, ws: Path) -> tuple[str | None, list[str]]:
    """Sync skills into <ws>/.claude/skills and write the per-turn MCP config.
    Returns (mcp-config path for --mcp-config or None, permission rules for
    --allowedTools: one mcp__<slug> per reachable server + "Skill" whenever any
    skill was synced). Leftovers from revoked grants are cleaned up."""
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        rows = (
            await db.execute(
                select(Service)
                .join(ServiceGrant, ServiceGrant.service_id == Service.id)
                .where(ServiceGrant.user_id == user_id, Service.enabled.is_(True))
                .order_by(Service.slug)
            )
        ).scalars().all()
        granted = [(s.slug, s.skill_version) for s in rows]
    is_admin = user is not None and user.role == UserRole.admin

    def _sync_files() -> tuple[str | None, list[str]]:
        eco_dir = ws / ".ecocode"
        skills_root = ws / ".claude" / "skills"
        state_path = eco_dir / "services-state.json"
        # Skills to have on disk (slug -> version). _memory is skill-only for
        # everyone; _admin is skill+server for admins; services may be
        # server-only (version 0 = no published skill yet).
        desired_skills: dict[str, int] = {slug: ver for slug, ver in granted}
        desired_skills[MEMORY_SLUG] = MEMORY_VERSION
        mcp_slugs = [slug for slug, _ in granted]
        if is_admin:
            desired_skills[BUILDER_SLUG] = BUILDER_VERSION
            mcp_slugs.append(BUILDER_SLUG)

        try:
            prev = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

        # Remove skills for revoked/disabled services (only OUR managed dirs).
        if skills_root.is_dir():
            for child in skills_root.iterdir():
                if child.name.startswith(SKILL_PREFIX):
                    slug = child.name.removeprefix(SKILL_PREFIX)
                    if slug not in desired_skills:
                        shutil.rmtree(child, ignore_errors=True)
                if child.name == BUILDER_SKILL_DIRNAME and not is_admin:
                    shutil.rmtree(child, ignore_errors=True)

        # Copy changed/new skill packages.
        for slug, ver in desired_skills.items():
            if prev.get(slug) == ver:
                continue
            if slug == BUILDER_SLUG:
                src, dest = BUILDER_ASSET, skills_root / BUILDER_SKILL_DIRNAME
            elif slug == MEMORY_SLUG:
                src, dest = MEMORY_ASSET, skills_root / MEMORY_SKILL_DIRNAME
            else:
                if ver <= 0:
                    continue  # service has tools but no published skill yet
                src = Path(settings.services_root) / slug / str(ver)
                dest = skills_root / f"{SKILL_PREFIX}{slug}"
            if not src.is_dir():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src, dest)

        eco_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(desired_skills, ensure_ascii=False), encoding="utf-8")

        allowed = [f"mcp__{s}" for s in sorted(mcp_slugs)]
        if desired_skills:
            allowed.append("Skill")

        if not mcp_slugs:
            (eco_dir / "mcp.json").unlink(missing_ok=True)
            return None, allowed

        key = org_services.mint_turn_key(user_id)
        servers = {
            slug: {
                "type": "http",
                "url": f"{settings.service_gateway_base}/{slug}",
                "headers": {"Authorization": f"Bearer {key}"},
            }
            for slug in sorted(mcp_slugs)
        }
        cfg_path = eco_dir / "mcp.json"
        cfg_path.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False), encoding="utf-8")
        return str(cfg_path), allowed

    return await asyncio.to_thread(_sync_files)
