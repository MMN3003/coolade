"""FastAPI dependencies: DB session, current user (cookie), API key auth, admin guard."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import async_session_factory
from app.errors import unauthorized, forbidden
from app.models import ApiKey, User
from app.security import hash_api_key, read_session_cookie

settings = get_settings()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    cookie_value = request.cookies.get(settings.session_cookie_name)
    if not cookie_value:
        raise unauthorized("لطفاً ابتدا وارد شوید.")
    payload = read_session_cookie(cookie_value)
    if not payload:
        raise unauthorized("نشست شما نامعتبر یا منقضی شده است.")
    user = await db.get(User, payload["user_id"])
    if not user or not user.is_active:
        raise unauthorized("حساب کاربری غیرفعال یا یافت نشد.")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin" and getattr(user.role, "value", user.role) != "admin":
        raise forbidden("این عملیات فقط برای ادمین مجاز است.")
    return user


def require_feature(*keys: str):
    """Router-level gate: the user's plan must expose at least one of `keys`
    (app/services/features.py). Mirrors the sidebar/route hiding so a hidden
    area cannot be reached by URL or direct API call."""

    async def _dep(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        from app.services.features import user_features  # local: avoids an import cycle

        granted = await user_features(db, user)
        if not any(k in granted for k in keys):
            raise forbidden("این بخش در پلن شما فعال نیست.")
        return user

    return _dep


class ApiKeyPrincipal:
    def __init__(self, user: User, api_key: ApiKey) -> None:
        self.user = user
        self.api_key = api_key


def _extract_key(request: Request) -> str | None:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def get_api_key_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyPrincipal:
    raw_key = _extract_key(request)
    if not raw_key or not raw_key.startswith("eco_live_"):
        raise unauthorized("کلید API نامعتبر است.")
    key_hash = hash_api_key(raw_key)
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if not api_key or not api_key.is_active:
        raise unauthorized("کلید API نامعتبر یا باطل‌شده است.")
    user = await db.get(User, api_key.user_id)
    if not user or not user.is_active:
        raise unauthorized("حساب کاربری غیرفعال است.")
    return ApiKeyPrincipal(user=user, api_key=api_key)
