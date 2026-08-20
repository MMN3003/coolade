from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import client_ip, get_current_user, get_db
from app.errors import unauthorized, rate_limited
from app.models import Model, ModelPolicy, User
from app.schemas import LoginRequest, MeQuotaSummary, MeResponse, OkResponse
from app.security import create_session_cookie, login_attempts, verify_password
from app.services.audit import record_audit
from app.services.quota import get_or_create_quota, get_used_credits

try:
    import ldap3
except ImportError:  # pragma: no cover
    ldap3 = None  # type: ignore

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _verify_ldap(username: str, password: str) -> bool:
    if not settings.ldap_enabled or ldap3 is None:
        return False
    bind_dn = settings.ldap_bind_template.format(username=username)
    try:
        conn = ldap3.Connection(settings.ldap_uri, bind_dn, password, auto_bind=True)
        conn.unbind()
        return True
    except Exception:
        return False


@router.post("/login", response_model=OkResponse)
async def login(
    body: LoginRequest,
    response: Response,
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    if login_attempts.is_blocked(body.username, ip):
        raise rate_limited("تعداد تلاش‌های ورود ناموفق زیاد بوده است. لطفاً ۱۵ دقیقه دیگر تلاش کنید.")

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    ok = False
    if user and user.is_active:
        auth_source = getattr(user.auth_source, "value", user.auth_source)
        if auth_source == "ldap" and settings.ldap_enabled:
            ok = _verify_ldap(body.username, body.password)
        else:
            ok = verify_password(user.password_hash, body.password)

    if not ok:
        login_attempts.record_failure(body.username, ip)
        await record_audit(
            db,
            actor_id=user.id if user else None,
            action="login.fail",
            detail={"username": body.username},
            ip_address=ip,
        )
        await db.commit()
        raise unauthorized("نام کاربری یا رمز عبور نادرست است.")

    login_attempts.record_success(body.username, ip)
    cookie_value = create_session_cookie(user.id, getattr(user.role, "value", user.role))
    response.set_cookie(
        settings.session_cookie_name,
        cookie_value,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.ecocode_env == "prod",
        samesite="lax",
        path="/",
    )
    await record_audit(db, actor_id=user.id, action="login.success", ip_address=ip)
    await db.commit()
    return OkResponse()


@router.post("/logout", response_model=OkResponse)
async def logout(response: Response, user: User = Depends(get_current_user)) -> OkResponse:
    response.delete_cookie(settings.session_cookie_name, path="/")
    return OkResponse()


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeResponse:
    result = await db.execute(
        select(Model.model_key)
        .join(ModelPolicy, ModelPolicy.model_id == Model.id)
        .where(ModelPolicy.user_id == user.id, Model.is_enabled.is_(True))
    )
    allowed_models = [r[0] for r in result.all()]

    quota = await get_or_create_quota(db, user.id)
    used = await get_used_credits(db, user.id, quota.period_start)
    await db.commit()

    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=getattr(user.role, "value", user.role),
        auth_source=getattr(user.auth_source, "value", user.auth_source),
        allowed_models=allowed_models,
        quota=MeQuotaSummary(
            period=getattr(quota.period, "value", quota.period),
            limit_credits=quota.limit_credits,
            bonus_credits=quota.bonus_credits,
            used_credits=used,
            period_start=quota.period_start,
        ),
    )
