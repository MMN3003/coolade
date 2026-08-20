"""Uniform error envelope: {"error": {"code": "...", "message": "پیام فارسی"}}"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
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


def quota_exceeded(message: str = "سقف مصرف دوره تمام شده است.") -> AppError:
    return AppError(status.HTTP_429_TOO_MANY_REQUESTS, "quota_exceeded", message)


def model_not_allowed(message: str = "این مدل برای شما مجاز نیست.") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, "model_not_allowed", message)


def rate_limited(message: str = "تعداد تلاش‌ها زیاد است. کمی بعد دوباره تلاش کنید.") -> AppError:
    return AppError(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", message)
