from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.errors import bad_request, not_found
from app.models import Model, User
from app.schemas import ModelCreate, ModelOut, ModelUpdate

router = APIRouter(prefix="/api/admin/models", tags=["admin-models"])


@router.get("", response_model=list[ModelOut])
async def list_models(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[ModelOut]:
    result = await db.execute(select(Model).order_by(Model.sort_order, Model.id))
    return list(result.scalars().all())


@router.post("", response_model=ModelOut)
async def create_model(
    body: ModelCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> ModelOut:
    existing = await db.execute(select(Model).where(Model.model_key == body.model_key))
    if existing.scalar_one_or_none():
        raise bad_request("این model_key قبلاً وجود دارد.")
    model = Model(**body.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.patch("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int,
    body: ModelUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ModelOut:
    model = await db.get(Model, model_id)
    if not model:
        raise not_found("مدل یافت نشد.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await db.commit()
    await db.refresh(model)
    return model
