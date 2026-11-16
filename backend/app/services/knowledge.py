"""Knowledge layer (amendment-7, docs/KNOWLEDGE.md) — rules & knowledge at four
scopes and how each reaches the agent.

Scopes (knowledge_entries.scope) and delivery:

  service        admin-written, for EVERYONE using that service
  user_service   one user's own notes/rules for one service
                 → both are appended to the synced service skill (SKILL.md) by
                   service_sync.py, so they load exactly when the service is used
                   (skills are lazy: only the description costs tokens until triggered).

  user           the person's own rules/knowledge — written by them («یادت باشه»
                 via the `_me` MCP tools or the «دانش من» page), by an admin about
                 them, or LEARNED from their chats (services/learning.py)
  team           a team's shared rules/knowledge (members write, all members get it)
                 → compiled per turn into --append-system-prompt (compile_turn_context):
                   RULES are always inline (they must bind every answer); KNOWLEDGE is
                   inline while the pack is small, otherwise spilled to
                   <ws>/.coolade/knowledge/*.md with an index in the prompt, so a big
                   knowledge base doesn't ride along every turn (token economy).

Nothing here is a security layer: knowledge shapes answers; access is still
grants / membership / read-only connectors (SERVICES-V2 DS4).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import KnowledgeEntry, KnowledgeKind, KnowledgeScope, KnowledgeSource, Team

settings = get_settings()

MAX_TITLE = 200
MAX_CONTENT = 20_000  # per entry, chars


# ---------------------------------------------------------------- validation
def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    if not t:
        raise ValueError("عنوان خالی است.")
    return t[:MAX_TITLE]


def clean_content(content: str) -> str:
    c = (content or "").strip()
    if not c:
        raise ValueError("متن خالی است.")
    if len(c) > MAX_CONTENT:
        raise ValueError(f"متن بلندتر از سقف {MAX_CONTENT} کاراکتر است.")
    return c


# ---------------------------------------------------------------- queries
def _active(stmt):
    return stmt.where(KnowledgeEntry.enabled.is_(True)).order_by(
        KnowledgeEntry.sort_order, KnowledgeEntry.id
    )


async def service_entries(db: AsyncSession, service_id: int) -> list[KnowledgeEntry]:
    return list(
        (
            await db.execute(
                _active(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.scope == KnowledgeScope.service,
                        KnowledgeEntry.service_id == service_id,
                    )
                )
            )
        ).scalars()
    )


async def user_service_entries(
    db: AsyncSession, user_id: int, service_id: int
) -> list[KnowledgeEntry]:
    return list(
        (
            await db.execute(
                _active(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.scope == KnowledgeScope.user_service,
                        KnowledgeEntry.service_id == service_id,
                        KnowledgeEntry.user_id == user_id,
                    )
                )
            )
        ).scalars()
    )


async def user_entries(db: AsyncSession, user_id: int) -> list[KnowledgeEntry]:
    return list(
        (
            await db.execute(
                _active(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.scope == KnowledgeScope.user,
                        KnowledgeEntry.user_id == user_id,
                    )
                )
            )
        ).scalars()
    )


async def team_entries(db: AsyncSession, team_id: int) -> list[KnowledgeEntry]:
    return list(
        (
            await db.execute(
                _active(
                    select(KnowledgeEntry).where(
                        KnowledgeEntry.scope == KnowledgeScope.team,
                        KnowledgeEntry.team_id == team_id,
                    )
                )
            )
        ).scalars()
    )


async def service_fingerprint(db: AsyncSession, user_id: int, service_id: int) -> str:
    """Cheap change-detector for service_sync's version marker: max(updated_at)
    + count over the entries that would be appended to this user's copy of the
    service skill. Any add/edit/delete/toggle changes it → re-sync."""
    row = (
        await db.execute(
            select(func.count(KnowledgeEntry.id), func.max(KnowledgeEntry.updated_at)).where(
                KnowledgeEntry.service_id == service_id,
                (
                    (KnowledgeEntry.scope == KnowledgeScope.service)
                    | (
                        (KnowledgeEntry.scope == KnowledgeScope.user_service)
                        & (KnowledgeEntry.user_id == user_id)
                    )
                ),
            )
        )
    ).one()
    if not row[0]:
        return ""  # no entries at all → callers skip loading/rendering
    raw = f"{row[0]}|{row[1].isoformat() if row[1] else ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- rendering
def _render_entries(entries: list[KnowledgeEntry], *, numbered: bool = True) -> str:
    lines: list[str] = []
    for i, e in enumerate(entries, 1):
        head = f"{i}. **{e.title}**" if numbered else f"### {e.title}"
        body = e.content.strip()
        if "\n" in body or len(body) > 160:
            lines.append(f"{head}\n{body}\n")
        else:
            lines.append(f"{head} — {body}")
    return "\n".join(lines).strip()


def render_service_addendum(
    service_name: str,
    service_desc: str | None,
    service_rows: list[KnowledgeEntry],
    user_rows: list[KnowledgeEntry],
) -> str:
    """Markdown appended to (or forming) the synced service SKILL.md."""
    parts: list[str] = []
    s_rules = [e for e in service_rows if e.kind == KnowledgeKind.rule]
    s_know = [e for e in service_rows if e.kind == KnowledgeKind.knowledge]
    u_rules = [e for e in user_rows if e.kind == KnowledgeKind.rule]
    u_know = [e for e in user_rows if e.kind == KnowledgeKind.knowledge]
    if s_rules:
        parts.append(
            f"## قوانین سرویس «{service_name}» (تعیین‌شده توسط ادمین — الزامی)\n\n"
            + _render_entries(s_rules)
        )
    if s_know:
        parts.append(f"## دانش سرویس «{service_name}»\n\n" + _render_entries(s_know))
    if u_rules:
        parts.append(
            "## قوانین شخصی این کاربر برای این سرویس (الزامی)\n\n" + _render_entries(u_rules)
        )
    if u_know:
        parts.append("## دانش/یادداشت‌های شخصی این کاربر برای این سرویس\n\n" + _render_entries(u_know))
    return "\n\n".join(parts).strip()


def minimal_skill_md(slug: str, service_name: str, service_desc: str | None) -> str:
    """For services with tools but no published skill: a small SKILL.md so the
    knowledge below it is still discoverable when the service is used."""
    desc = (service_desc or "").strip() or f"گزارش‌گیری از سرویس سازمانی «{service_name}»"
    desc_line = re.sub(r"\s+", " ", desc)[:400]
    return (
        f"---\nname: coolade-svc-{slug}\n"
        f"description: {desc_line} — وقتی کاربر دربارهٔ «{service_name}» یا داده‌های آن می‌پرسد.\n---\n\n"
        f"# سرویس «{service_name}»\n\n"
        f"ابزارهای این سرویس در سرور MCP `{slug}` هستند (`mcp__{slug}__*`). هر عدد فقط از "
        f"همین ابزارها؛ هرگز عدد نساز. کوئری/فراخوانی انجام‌شده را در پایان پاسخ ذکر کن.\n"
    )


KNOWLEDGE_MARKER = "\n\n<!-- coolade:knowledge -->\n"
_LEGACY_KNOWLEDGE_MARKER = "\n\n<!-- ecocode:knowledge -->\n"  # skills published before the rename


def apply_addendum(skill_md: str, addendum: str) -> str:
    """Idempotently append (replacing any earlier generated block)."""
    base = skill_md.split(KNOWLEDGE_MARKER, 1)[0].split(_LEGACY_KNOWLEDGE_MARKER, 1)[0].rstrip()
    if not addendum:
        return base + "\n"
    return base + KNOWLEDGE_MARKER + addendum + "\n"


# ---------------------------------------------------------------- per-turn pack
@dataclass
class TurnContext:
    system_text: str = ""              # goes into --append-system-prompt
    files: dict[str, str] = field(default_factory=dict)  # relpath under <ws> -> content


def _slug_file(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40] or "x"


async def compile_turn_context(
    db: AsyncSession,
    user_id: int,
    member_teams: list[tuple[int, str, str]],
    *,
    inline_budget: int | None = None,
) -> TurnContext:
    """Build the per-turn pack for user + team scopes.

    Rules: always inline (user's own → admin-about-user are the same scope; team
    rules per team). Knowledge: inline as long as the whole pack fits
    `inline_budget` chars, else written to <ws>/.coolade/knowledge/<file>.md
    with a one-line-per-entry index in the prompt telling the agent to read the
    file when the topic comes up."""
    budget = inline_budget if inline_budget is not None else settings.knowledge_inline_max_chars
    ctx = TurnContext()

    u_rows = await user_entries(db, user_id)
    team_rows: list[tuple[str, str, list[KnowledgeEntry]]] = []
    for team_id, slug, name in member_teams:
        rows = await team_entries(db, team_id)
        if rows:
            team_rows.append((slug, name, rows))

    if not u_rows and not team_rows:
        return ctx

    sections: list[str] = []
    u_rules = [e for e in u_rows if e.kind == KnowledgeKind.rule]
    u_know = [e for e in u_rows if e.kind == KnowledgeKind.knowledge]
    if u_rules:
        sections.append("## قوانین این کاربر (الزامی — در همهٔ پاسخ‌ها رعایت کن)\n\n" + _render_entries(u_rules))
    for slug, name, rows in team_rows:
        t_rules = [e for e in rows if e.kind == KnowledgeKind.rule]
        if t_rules:
            sections.append(f"## قوانین تیم «{name}» (الزامی)\n\n" + _render_entries(t_rules))

    # knowledge: try inline first
    know_blocks: list[tuple[str, str, list[KnowledgeEntry]]] = []
    if u_know:
        know_blocks.append(("user", "دانش این کاربر (چیزهایی که دربارهٔ او و کارش می‌دانی)", u_know))
    for slug, name, rows in team_rows:
        t_know = [e for e in rows if e.kind == KnowledgeKind.knowledge]
        if t_know:
            know_blocks.append((f"team-{_slug_file(slug)}", f"دانش تیم «{name}»", t_know))

    inline_know = [f"## {label}\n\n{_render_entries(rows)}" for _f, label, rows in know_blocks]
    head = (
        f"# دانش و قوانین سازمانی ({settings.app_name})\n"
        "این بخش از پایگاه دانش سازمان ساخته شده و مقدم بر حدس توست. "
        "قوانین الزامی‌اند؛ دانش را وقتی به موضوع مربوط است به‌کار بگیر و "
        "اگر با گفتهٔ کاربر تضاد دارد، تضاد را بگو.\n\n"
    )
    candidate = head + "\n\n".join(sections + inline_know)
    if len(candidate) <= budget or not know_blocks:
        ctx.system_text = candidate.strip()
        return ctx

    # spill knowledge to files, keep an index inline
    index_lines: list[str] = []
    for fname, label, rows in know_blocks:
        rel = f".coolade/knowledge/{fname}.md"
        ctx.files[rel] = f"# {label}\n\n{_render_entries(rows, numbered=False)}\n"
        titles = "؛ ".join(e.title for e in rows[:40])
        more = "" if len(rows) <= 40 else f" و {len(rows) - 40} مورد دیگر"
        index_lines.append(f"- **{label}** → فایل `{rel}` (عناوین: {titles}{more})")
    sections.append(
        "## فهرست دانش (متن کامل در فایل‌ها — وقتی موضوع مربوط شد، فایل را با Read بخوان)\n\n"
        + "\n".join(index_lines)
    )
    ctx.system_text = (head + "\n\n".join(sections)).strip()
    return ctx


def write_context_files(ws: Path, files: dict[str, str]) -> None:
    """Materialise spilled knowledge files; remove stale ones we wrote earlier."""
    kdir = ws / ".coolade" / "knowledge"
    if kdir.is_dir():
        for child in kdir.iterdir():
            if child.is_file() and child.suffix == ".md":
                rel = f".coolade/knowledge/{child.name}"
                if rel not in files:
                    try:
                        child.unlink()
                    except OSError:
                        pass
    if not files:
        return
    kdir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        (ws / rel).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- helpers for routers/tools
def to_dict(e: KnowledgeEntry) -> dict:
    return {
        "id": e.id,
        "scope": e.scope.value if hasattr(e.scope, "value") else str(e.scope),
        "kind": e.kind.value if hasattr(e.kind, "value") else str(e.kind),
        "source": e.source.value if hasattr(e.source, "value") else str(e.source),
        "service_id": e.service_id,
        "user_id": e.user_id,
        "team_id": e.team_id,
        "title": e.title,
        "content": e.content,
        "enabled": e.enabled,
        "sort_order": e.sort_order,
        "learned_from_conversation_id": e.learned_from_conversation_id,
        "created_by": e.created_by,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


async def team_name(db: AsyncSession, team_id: int) -> str | None:
    t = await db.get(Team, team_id)
    return t.name if t else None


__all__ = [
    "KnowledgeKind",
    "KnowledgeScope",
    "KnowledgeSource",
    "TurnContext",
    "apply_addendum",
    "clean_content",
    "clean_title",
    "compile_turn_context",
    "minimal_skill_md",
    "render_service_addendum",
    "service_entries",
    "service_fingerprint",
    "team_entries",
    "to_dict",
    "user_entries",
    "user_service_entries",
    "write_context_files",
]
