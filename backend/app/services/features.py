"""Per-plan feature visibility.

A plan may restrict which product areas its members see: the sidebar entry,
the route and the backing API all key off the same list. Chat and help are
always on. Admins and users without a plan (or with a plan whose list is NULL)
see everything, so existing installs behave exactly as before.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Plan, User

# Order = sidebar order. Keep in sync with frontend/src/api/types.ts FeatureKey.
FEATURE_KEYS: tuple[str, ...] = ("workspaces", "cli", "usage", "keys", "teams", "knowledge")


def normalize(features: list[str] | None) -> list[str] | None:
    """Validate an admin-supplied list; returns None (= all) when None is given."""
    if features is None:
        return None
    unknown = sorted(set(features) - set(FEATURE_KEYS))
    if unknown:
        raise ValueError(", ".join(unknown))
    return [k for k in FEATURE_KEYS if k in features]


async def user_features(db: AsyncSession, user: User) -> list[str]:
    if getattr(user.role, "value", user.role) == "admin" or not user.plan_id:
        return list(FEATURE_KEYS)
    plan = await db.get(Plan, user.plan_id)
    if plan is None or plan.features is None:
        return list(FEATURE_KEYS)
    return [k for k in FEATURE_KEYS if k in plan.features]
