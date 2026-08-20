from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import client_ip, get_current_user, get_db
from app.errors import forbidden, not_found
from app.models import ApiKey, Model, ModelPolicy, User
from app.schemas import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.security import generate_api_key
from app.services.audit import record_audit
from app.services.litellm_client import litellm_client
from app.services.quota import get_or_create_quota

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=ApiKeyCreatedOut)
async def create_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedOut:
    full_key, key_prefix, key_hash = generate_api_key()
    api_key = ApiKey(user_id=user.id, name=body.name, key_prefix=key_prefix, key_hash=key_hash)
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    result = await db.execute(
        select(Model.model_key)
        .join(ModelPolicy, ModelPolicy.model_id == Model.id)
        .where(ModelPolicy.user_id == user.id, Model.is_enabled.is_(True))
    )
    allowed_models = [r[0] for r in result.all()]

    quota = await get_or_create_quota(db, user.id)
    max_budget = float(quota.limit_credits) * 2 if quota.limit_credits else 1_000_000.0

    try:
        litellm_resp = await litellm_client.key_generate(
            models=allowed_models,
            metadata={"ecocode_user_id": user.id, "ecocode_key_id": api_key.id},
            max_budget=max_budget,
        )
        api_key.litellm_key_id = litellm_resp.get("key")
        await db.commit()
    except Exception:
        # LiteLLM unreachable/failed — the ecocode key still works for auth/ACL/quota
        # (enforced by our own backend); the virtual key is only a secondary safety net.
        pass

    await record_audit(
        db,
        actor_id=user.id,
        action="key.create",
        target_id=user.id,
        detail={"key_prefix": key_prefix, "name": body.name},
        ip_address=ip,
    )
    await db.commit()

    return ApiKeyCreatedOut(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        key=full_key,
    )


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> dict:
    api_key = await db.get(ApiKey, key_id)
    if not api_key:
        raise not_found("کلید یافت نشد.")
    if api_key.user_id != user.id and user.role != "admin":
        raise forbidden()

    api_key.is_active = False
    api_key.revoked_at = datetime.datetime.now(datetime.timezone.utc)
    if api_key.litellm_key_id:
        try:
            await litellm_client.key_delete(api_key.litellm_key_id)
        except Exception:
            pass

    await record_audit(
        db,
        actor_id=user.id,
        action="key.revoke",
        target_id=api_key.user_id,
        detail={"key_prefix": api_key.key_prefix},
        ip_address=ip,
    )
    await db.commit()
    return {"ok": True}
