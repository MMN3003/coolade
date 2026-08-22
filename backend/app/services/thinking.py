"""Issue D — thinking-level ladder, global cap, MAX_THINKING_TOKENS mapping (TECH.md 5.7).

effective = min(requested_or_conversation_default, cap); cap = min(THINKING_MAX_LEVEL env,
optional per-policy cap). The per-policy cap is a documented extension point (nice-to-have,
not built — TECH.md explicitly says "over-build نکنید"): pass `policy_cap` when/if a
per-user/quota column for it is added later; today no caller supplies one.
"""
from __future__ import annotations

import os

from app.models import ThinkingLevel

_ORDER: dict[ThinkingLevel, int] = {
    ThinkingLevel.off: 0,
    ThinkingLevel.standard: 1,
    ThinkingLevel.deep: 2,
}

MAX_THINKING_TOKENS: dict[ThinkingLevel, int | None] = {
    ThinkingLevel.off: None,
    ThinkingLevel.standard: 8000,
    ThinkingLevel.deep: 24000,
}


def _parse_level(value: str | None, default: ThinkingLevel) -> ThinkingLevel:
    if not value:
        return default
    try:
        return ThinkingLevel(value)
    except ValueError:
        return default


def global_cap() -> ThinkingLevel:
    return _parse_level(os.environ.get("THINKING_MAX_LEVEL"), ThinkingLevel.deep)


def effective_level(
    requested: ThinkingLevel | None,
    conversation_default: ThinkingLevel,
    *,
    policy_cap: ThinkingLevel | None = None,
) -> ThinkingLevel:
    """Effective level used for a turn — also what gets persisted/reported (badge source)."""
    wanted = requested if requested is not None else conversation_default
    cap = global_cap()
    if policy_cap is not None and _ORDER[policy_cap] < _ORDER[cap]:
        cap = policy_cap
    return wanted if _ORDER[wanted] <= _ORDER[cap] else cap


def max_thinking_tokens(level: ThinkingLevel) -> int | None:
    return MAX_THINKING_TOKENS[level]
