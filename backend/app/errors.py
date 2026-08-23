"""Uniform error envelope: {"error": {"code": "...", "message": "پیام فارسی"}}"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, extra: dict | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        # اصلاحیهٔ ۳ / Issue E: extra fields merged into the "error" body object —
        # e.g. reset_at / reset_5h_at so the retry UX (Issue C) can show the right
        # reason and time (TECH.md 5.8, section 8 error contract).
        self.extra = extra or {}
        super().__init__(message)


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, **exc.extra}},
    )


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "validation_error",
                "message": "داده‌های ارسالی نامعتبر است.",
            }
        },
    )


def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "خطای داخلی سرور رخ داد."}},
    )


# Common, reusable errors
def unauthorized(message: str = "نام کاربری یا رمز عبور نامعتبر است.") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, "unauthorized", message)


def forbidden(message: str = "دسترسی مجاز نیست.") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, "forbidden", message)


def not_found(message: str = "مورد درخواستی یافت نشد.") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, "not_found", message)


def bad_request(message: str = "درخواست نامعتبر است.") -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, "bad_request", message)


def quota_exceeded(
    message: str = "سقف مصرف دوره تمام شده است.", *, reset_at: str | None = None
) -> AppError:
    return AppError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "quota_exceeded",
        message,
        extra={"reset_at": reset_at},
    )


def upstream_rate_limited_message(
    *, model: str | None = None, reset_at: str | None = None
) -> str:
    """Product-owner follow-up (folded into اصلاحیهٔ ۴ work, 2026-08-22): an upstream
    429 keeps the requested model — explicitly NO auto-substitution/fallback loop —
    but the message must be actionable: name the model, suggest a lighter one, and
    (when the account's 5h window reset time is known, Issue F state) say roughly
    when it frees up. Shared by both surfaces that can see an upstream 429:
    routers/passthrough.py (API-key surface) and cli_runner.py's
    _classify_result_error (web-chat surface, same code+message on the failed
    message row so the Issue C retry bubble shows the right reason)."""
    if not model:
        return "سرویس بالادستی فعلاً شلوغ است؛ کمی بعد دوباره تلاش کنید."
    message = (
        f"مدل {model} موقتاً از سمت اکانت محدود شده است (سقف مصرف اشتراک پر شده). "
        "از یک مدل سبک‌تر مثل claude-haiku استفاده کنید یا کمی بعد دوباره تلاش کنید."
    )
    if reset_at:
        message += f" آزاد شدن حدود {reset_at}."
    return message


def upstream_rate_limited(*, model: str | None = None, reset_at: str | None = None) -> AppError:
    """429 from the upstream service itself (distinct from our own quota_exceeded*
    codes above) — code stays `upstream_rate_limited` (TECH.md 5.2's error table),
    only the message/extra got more actionable."""
    message = upstream_rate_limited_message(model=model, reset_at=reset_at)
    return AppError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "upstream_rate_limited",
        message,
        extra={
            "reset_at": reset_at,
            "retry_hint": "می‌توانید کمی بعد دوباره تلاش کنید یا از یک مدل سبک‌تر استفاده کنید.",
        },
    )


def quota_exceeded_5h(
    message: str = "سقف مصرف ۵ ساعتهٔ شما پر شده؛ تا آزاد شدن پنجره صبر کنید.",
    *,
    reset_5h_at: str | None = None,
) -> AppError:
    """اصلاحیهٔ ۳ / Issue E (TECH.md 5.8): rolling 5h window cap, distinct code from
    the periodic weekly `quota_exceeded` so the client (and Issue C retry UX) can
    show the right reason and enable the retry button only once `reset_5h_at` has
    passed."""
    return AppError(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "quota_exceeded_5h",
        message,
        extra={"reset_5h_at": reset_5h_at},
    )


def model_not_allowed(message: str = "این مدل برای شما مجاز نیست.") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, "model_not_allowed", message)


def rate_limited(message: str = "تعداد تلاش‌ها زیاد است. کمی بعد دوباره تلاش کنید.") -> AppError:
    return AppError(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", message)
