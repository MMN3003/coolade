"""Admin — User Plans / Tiers (CRUD + re-apply to members).

A plan bundles: monthly (or other-period) credit limit, rolling 5h credit limit,
allowed models, and a max thinking level. Users inherit a plan on create/edit
(admin_users.py) and it can be re-applied to every member here.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_db, require_admin
from app.errors import bad_request, not_found
from app.models import Model, Plan, PlanModel, QuotaPeriod, ThinkingLevel, User
from app.schemas import PlanCreate, PlanOut, PlanUpdate
from app.services.audit import record_audit
from app.services.plans import apply_plan_to_user, plan_model_ids

router = APIRouter(prefix="/api/admin/plans", tags=["admin-plans"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return base[:80] or "plan"


async def _unique_slug(db: AsyncSession, base: str, exclude_id: int | None = None) -> str:
    candidate = base
    n = 2
    while True:
        q = select(Plan.id).where(Plan.slug == candidate)
        if exclude_id is not None:
            q = q.where(Plan.id != exclude_id)
        if (await db.execute(q)).scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"[:80]
        n += 1


async def _validate_model_ids(db: AsyncSession, model_ids: list[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(model_ids))  # dedupe, preserve order
    if not unique_ids:
        return []
    rows = await db.execute(select(Model.id).where(Model.id.in_(unique_ids)))
    found = {r[0] for r in rows.all()}
    missing = [str(m) for m in unique_ids if m not in found]
    if missing:
        raise bad_request(f"مدل‌های نامعتبر: {', '.join(missing)}")
    return unique_ids


async def _model_ids_map(db: AsyncSession, plan_ids: list[int]) -> dict[int, list[int]]:
    if not plan_ids:
        return {}
    rows = await db.execute(
        select(PlanModel.plan_id, PlanModel.model_id).where(PlanModel.plan_id.in_(plan_ids))
    )
    out: dict[int, list[int]] = {}
    for plan_id, model_id in rows.all():
        out.setdefault(plan_id, []).append(model_id)
    return out


async def _member_counts(db: AsyncSession, plan_ids: list[int]) -> dict[int, int]:
    if not plan_ids:
        return {}
    rows = await db.execute(
        select(User.plan_id, func.count(User.id))
        .where(User.plan_id.in_(plan_ids))
        .group_by(User.plan_id)
    )
    return dict(rows.all())


def _plan_out(plan: Plan, model_ids: list[int], member_count: int) -> PlanOut:
    return PlanOut(
        id=plan.id,
        name=plan.name,
        slug=plan.slug,
        description=plan.description,
        period=getattr(plan.period, "value", plan.period),
        limit_credits=plan.limit_credits,
        limit_credits_5h=plan.limit_credits_5h,
        max_thinking_level=getattr(plan.max_thinking_level, "value", plan.max_thinking_level),
        is_active=plan.is_active,
        sort_order=plan.sort_order,
        model_ids=list(model_ids),
        member_count=member_count,
        created_at=plan.created_at,
    )


@router.get("", response_model=list[PlanOut])
async def list_plans(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[PlanOut]:
    plans = list(
        (await db.execute(select(Plan).order_by(Plan.sort_order, Plan.id))).scalars().all()
    )
    ids = [p.id for p in plans]
    model_map = await _model_ids_map(db, ids)
    counts = await _member_counts(db, ids)
    return [_plan_out(p, model_map.get(p.id, []), counts.get(p.id, 0)) for p in plans]


@router.post("", response_model=PlanOut)
async def create_plan(
    body: PlanCreate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    if (await db.execute(select(Plan.id).where(Plan.name == body.name))).scalar_one_or_none():
        raise bad_request("پلنی با این نام قبلاً وجود دارد.")
    slug = await _unique_slug(db, _slugify(body.slug or body.name))
    model_ids = await _validate_model_ids(db, body.model_ids)

    plan = Plan(
        name=body.name,
        slug=slug,
        description=body.description,
        period=QuotaPeriod(body.period),
        limit_credits=body.limit_credits,
        limit_credits_5h=body.limit_credits_5h,
        max_thinking_level=ThinkingLevel(body.max_thinking_level),
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(plan)
    await db.flush()
    for model_id in model_ids:
        db.add(PlanModel(plan_id=plan.id, model_id=model_id))

    await record_audit(
        db, actor_id=admin.id, action="plan.create", target_id=None,
        detail={"plan_id": plan.id, "slug": slug, "name": plan.name}, ip_address=ip,
    )
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan, model_ids, 0)


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> PlanOut:
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise not_found("پلن یافت نشد.")
    model_ids = await plan_model_ids(db, plan_id)
    counts = await _member_counts(db, [plan_id])
    return _plan_out(plan, model_ids, counts.get(plan_id, 0))


@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: int,
    body: PlanUpdate,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> PlanOut:
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise not_found("پلن یافت نشد.")

    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] and data["name"] != plan.name:
        dup = await db.execute(select(Plan.id).where(Plan.name == data["name"], Plan.id != plan_id))
        if dup.scalar_one_or_none():
            raise bad_request("پلنی با این نام قبلاً وجود دارد.")
        plan.name = data["name"]
    if "slug" in data and data["slug"]:
        plan.slug = await _unique_slug(db, _slugify(data["slug"]), exclude_id=plan_id)
    if "description" in data:
        plan.description = data["description"]
    if "period" in data and data["period"] is not None:
        plan.period = QuotaPeriod(data["period"])
    if "limit_credits" in data and data["limit_credits"] is not None:
        plan.limit_credits = data["limit_credits"]
    if "limit_credits_5h" in data:  # present-and-null clears the 5h cap
        plan.limit_credits_5h = data["limit_credits_5h"]
    if "max_thinking_level" in data and data["max_thinking_level"] is not None:
        plan.max_thinking_level = ThinkingLevel(data["max_thinking_level"])
    if "is_active" in data and data["is_active"] is not None:
        plan.is_active = data["is_active"]
    if "sort_order" in data and data["sort_order"] is not None:
        plan.sort_order = data["sort_order"]

    if "model_ids" in data and data["model_ids"] is not None:
        model_ids = await _validate_model_ids(db, data["model_ids"])
        await db.execute(delete(PlanModel).where(PlanModel.plan_id == plan_id))
        for model_id in model_ids:
            db.add(PlanModel(plan_id=plan_id, model_id=model_id))

    await record_audit(
        db, actor_id=admin.id, action="plan.update", target_id=None,
        detail={"plan_id": plan_id, "fields": sorted(data.keys())}, ip_address=ip,
    )
    await db.commit()
    await db.refresh(plan)
    final_ids = await plan_model_ids(db, plan_id)
    counts = await _member_counts(db, [plan_id])
    return _plan_out(plan, final_ids, counts.get(plan_id, 0))


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise not_found("پلن یافت نشد.")
    # plan_models rows cascade; users.plan_id is SET NULL (members keep their quota/policy).
    await record_audit(
        db, actor_id=admin.id, action="plan.delete", target_id=None,
        detail={"plan_id": plan_id, "slug": plan.slug, "name": plan.name}, ip_address=ip,
    )
    await db.delete(plan)
    await db.commit()
    return {"ok": True}


@router.post("/{plan_id}/apply")
async def apply_plan(
    plan_id: int,
    admin: User = Depends(require_admin),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-apply this plan to EVERY user whose plan_id == plan_id: rewrite each
    member's Quota + ModelPolicy rows + max thinking level from the plan."""
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise not_found("پلن یافت نشد.")
    members = list((await db.execute(select(User).where(User.plan_id == plan_id))).scalars().all())
    for member in members:
        await apply_plan_to_user(db, member, plan)
    await record_audit(
        db, actor_id=admin.id, action="plan.apply", target_id=None,
        detail={"plan_id": plan_id, "applied_to": len(members)}, ip_address=ip,
    )
    await db.commit()
    return {"ok": True, "applied_to": len(members)}
