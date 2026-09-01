"""User Plans / Tiers — apply a plan's quota + model access + thinking cap to a user.

The single source of inheritance logic, reused by:
  - POST /api/admin/plans/{id}/apply  (re-apply to ALL members of a plan)
  - admin_users.create_user / update_user (apply to one user on create/edit)

Mirrors the manual admin_users flows: set_quota (get_or_create_quota + period/limits),
set_policy (replace ModelPolicy rows), and the per-user thinking cap. Manual per-user
edits afterwards still override until the plan is re-applied.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelPolicy, Plan, PlanModel, User
from app.services.quota import get_or_create_quota


async def plan_model_ids(db: AsyncSession, plan_id: int) -> list[int]:
    rows = await db.execute(select(PlanModel.model_id).where(PlanModel.plan_id == plan_id))
    return [r[0] for r in rows.all()]


async def apply_plan_to_user(db: AsyncSession, user: User, plan: Plan) -> None:
    """Inherit `plan` onto `user`. Rewrites the Quota row (period + both limits),
    replaces the user's ModelPolicy rows with the plan's models, sets the per-user
    thinking cap, and stamps user.plan_id. Does NOT commit — the caller owns the
    transaction (so create/update can batch it with their own audit + commit)."""
    quota = await get_or_create_quota(db, user.id)
    quota.period = plan.period
    quota.limit_credits = plan.limit_credits
    quota.limit_credits_5h = plan.limit_credits_5h

    model_ids = await plan_model_ids(db, plan.id)
    await db.execute(delete(ModelPolicy).where(ModelPolicy.user_id == user.id))
    for model_id in model_ids:
        db.add(ModelPolicy(user_id=user.id, model_id=model_id))

    user.max_thinking_level = plan.max_thinking_level
    user.plan_id = plan.id
