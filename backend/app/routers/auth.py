from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import client_ip, get_current_user, get_db
from app.errors import unauthorized, rate_limited
from app.models import Model, ModelPolicy, Team, TeamMember, User
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeQuotaSummary,
    MeResponse,
    MeTeamOut,
    OkResponse,
)
from app.security import create_session_cookie, login_attempts, verify_password
from app.services import thinking as thinking_service
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


@router.post("/change-password", response_model=OkResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    ip: str = Depends(client_ip),
    db: AsyncSession = Depends(get_db),
) -> OkResponse:
    """Self-service password change (local accounts only — LDAP passwords are
    the organization directory's business). Requires the current password;
    audited without ever storing either value."""
    from app.errors import bad_request
    from app.models import AuthSource
    from app.security import hash_password

    if user.auth_source != AuthSource.local:
        raise bad_request("رمز عبور شما از طریق LDAP سازمان مدیریت می‌شود و از این‌جا قابل تغییر نیست.")
    # Same throttle store as login (distinct bucket) so a stolen session can't
    # brute-force the current password through this endpoint.
    bucket = f"pw:{user.username}"
    if login_attempts.is_blocked(bucket, ip):
        raise rate_limited("تلاش بیش از حد؛ کمی بعد دوباره امتحان کنید.")
    if not verify_password(user.password_hash, body.current_password):
        login_attempts.record_failure(bucket, ip)
        raise unauthorized("رمز عبور فعلی نادرست است.")
    login_attempts.record_success(bucket, ip)
    user.password_hash = hash_password(body.new_password)
    await record_audit(
        db, actor_id=user.id, action="auth.change_password", target_id=user.id, ip_address=ip
    )
    await db.commit()
    return OkResponse()


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeResponse:
    # Token economy: cheapest model first — the chat page defaults a NEW chat to
    # allowed_models[0], so ordering by weight makes the cheap model the default
    # without taking choice away.
    result = await db.execute(
        select(Model.model_key)
        .join(ModelPolicy, ModelPolicy.model_id == Model.id)
        .where(ModelPolicy.user_id == user.id, Model.is_enabled.is_(True))
        .order_by(Model.input_weight.asc(), Model.model_key)
    )
    allowed_models = [r[0] for r in result.all()]

    quota = await get_or_create_quota(db, user.id)
    used = await get_used_credits(db, user.id, quota.period_start)

    # اصلاحیهٔ ۴ / Issue H (TECH.md 8): teams[] on /api/auth/me.
    teams_result = await db.execute(
        select(Team.id, Team.name, Team.slug, TeamMember.role_in_team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.name)
    )
    teams = [
        MeTeamOut(id=r[0], name=r[1], slug=r[2], role_in_team=getattr(r[3], "value", r[3]))
        for r in teams_result.all()
    ]

    await db.commit()

    # Effective thinking cap = min(global THINKING_MAX_LEVEL env, per-user cap).
    # The per-user cap comes from the user's plan (User Plans / Tiers); NULL falls
    # back to the global cap. effective_level(user_cap, user_cap) yields that min.
    user_cap = user.max_thinking_level
    max_thinking = (
        thinking_service.effective_level(user_cap, user_cap).value
        if user_cap is not None
        else thinking_service.global_cap().value
    )

    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=getattr(user.role, "value", user.role),
        auth_source=getattr(user.auth_source, "value", user.auth_source),
        allowed_models=allowed_models,
        max_thinking_level=max_thinking,
        quota=MeQuotaSummary(
            period=getattr(quota.period, "value", quota.period),
            limit_credits=quota.limit_credits,
            bonus_credits=quota.bonus_credits,
            used_credits=used,
            period_start=quota.period_start,
        ),
        teams=teams,
        learning_enabled=bool(getattr(user, "learning_enabled", True)),
    )
