"""DS6 (docs/SERVICES-V2.md ب-۵) — sync granted services into a chat turn.

The general-chat CLI runs in-process with cwd = the user's workspace dir, so
everything is PROJECT-scope there:
  * skills   → <ws>/.claude/skills/coolade-svc-<slug>/   (from /data/services/<slug>/<ver>/)
  * builder  → <ws>/.claude/skills/coolade-service-builder/  (admins only, shipped asset)
  * mcp      → <ws>/.coolade/mcp.json with a fresh short-lived turn key
                (org_services.mint_turn_key), passed to the CLI via --mcp-config.

amendment-7 (knowledge layer, docs/KNOWLEDGE.md):
  * every synced service skill gets the service's knowledge/rules (admin, scope
    `service`) and THIS user's own notes for it (scope `user_service`) appended
    to SKILL.md — so they load exactly when the service is used. A service with
    tools but no published skill gets a minimal generated SKILL.md when it has
    knowledge, so the knowledge is still discoverable.
  * every user gets the `_me` MCP server (personal memory tools: remember /
    forget / list) — the coolade-memory skill talks to it instead of hand-editing
    CLAUDE.md, so «یادت باشه» lands in the DB and shows up in «دانش من».

A version marker (<ws>/.coolade/services-state.json) makes the copy step a
no-op when nothing changed (skill version AND knowledge fingerprint). Revocation
never depends on this file — the gateway re-checks the grant on every call (ب-۳);
stale synced skills are removed on the next turn anyway.
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
from app.services import knowledge as knowledge_service
from app.services import org_services

settings = get_settings()

SKILL_PREFIX = "coolade-svc-"
BUILDER_SLUG = "_admin"
BUILDER_SKILL_DIRNAME = "coolade-service-builder"
_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "skills"
BUILDER_ASSET = _ASSETS / BUILDER_SKILL_DIRNAME
BUILDER_VERSION = 1  # bump when the shipped asset changes
# Token-economy: the personal-memory skill ships to EVERY user (CLAUDE.md in the
# workspace root is natively auto-loaded by the CLI each turn — cross-chat memory
# that makes starting a cheap new conversation painless).
MEMORY_SLUG = "_memory"
MEMORY_SKILL_DIRNAME = "coolade-memory"
MEMORY_ASSET = _ASSETS / MEMORY_SKILL_DIRNAME
MEMORY_VERSION = 2  # v2: DB-backed via the `_me` MCP tools (amendment-7)
# amendment-7: reserved per-user MCP server (personal memory tools), all users.
ME_SLUG = "_me"


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
        # slug -> (version, knowledge-fingerprint, addendum markdown, minimal SKILL.md)
        granted: dict[str, tuple[int, str, str, str]] = {}
        for s in rows:
            fp = await knowledge_service.service_fingerprint(db, user_id, s.id)
            addendum = ""
            if fp:  # cheap: only load rows when there could be any
                s_rows = await knowledge_service.service_entries(db, s.id)
                u_rows = await knowledge_service.user_service_entries(db, user_id, s.id)
                addendum = knowledge_service.render_service_addendum(
                    s.name, s.description, s_rows, u_rows
                )
            granted[s.slug] = (
                s.skill_version,
                fp,
                addendum,
                knowledge_service.minimal_skill_md(s.slug, s.name, s.description),
            )
    is_admin = user is not None and user.role == UserRole.admin

    def _sync_files() -> tuple[str | None, list[str]]:
        app_dir = ws / ".coolade"
        skills_root = ws / ".claude" / "skills"
        state_path = app_dir / "services-state.json"
        # Skills to have on disk (slug -> state marker). _memory is skill-only for
        # everyone; _admin is skill+server for admins; services may be
        # server-only (version 0 = no published skill and no knowledge yet).
        desired_skills: dict[str, str] = {
            slug: f"{ver}:{fp}" for slug, (ver, fp, _add, _min) in granted.items()
        }
        desired_skills[MEMORY_SLUG] = str(MEMORY_VERSION)
        mcp_slugs = list(granted) + [ME_SLUG]
        if is_admin:
            desired_skills[BUILDER_SLUG] = str(BUILDER_VERSION)
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
        for slug, marker in desired_skills.items():
            if str(prev.get(slug)) == marker:
                continue
            if slug == BUILDER_SLUG:
                src, dest = BUILDER_ASSET, skills_root / BUILDER_SKILL_DIRNAME
                addendum, minimal = "", ""
            elif slug == MEMORY_SLUG:
                src, dest = MEMORY_ASSET, skills_root / MEMORY_SKILL_DIRNAME
                addendum, minimal = "", ""
            else:
                ver, _fp, addendum, minimal = granted[slug]
                dest = skills_root / f"{SKILL_PREFIX}{slug}"
                src = Path(settings.services_root) / slug / str(ver) if ver > 0 else None
                if (src is None or not src.is_dir()) and not addendum:
                    # tools but neither a published skill nor any knowledge yet
                    shutil.rmtree(dest, ignore_errors=True)
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            if src is not None and src.is_dir():
                shutil.copytree(src, dest)
            else:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text(minimal, encoding="utf-8")
            if slug not in (BUILDER_SLUG, MEMORY_SLUG):
                skill_md = dest / "SKILL.md"
                base = skill_md.read_text(encoding="utf-8") if skill_md.exists() else minimal
                skill_md.write_text(
                    knowledge_service.apply_addendum(base, addendum), encoding="utf-8"
                )

        app_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(desired_skills, ensure_ascii=False), encoding="utf-8")

        allowed = [f"mcp__{s}" for s in sorted(mcp_slugs)]
        if desired_skills:
            allowed.append("Skill")

        key = org_services.mint_turn_key(user_id)
        servers = {
            slug: {
                "type": "http",
                "url": f"{settings.service_gateway_base}/{slug}",
                "headers": {"Authorization": f"Bearer {key}"},
            }
            for slug in sorted(mcp_slugs)
        }
        cfg_path = app_dir / "mcp.json"
        cfg_path.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False), encoding="utf-8")
        return str(cfg_path), allowed

    return await asyncio.to_thread(_sync_files)
