"""Password hashing, Fernet encryption, session cookie signing, API key helpers."""
from __future__ import annotations

import hashlib
import secrets
import string
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

settings = get_settings()

_ph = PasswordHasher()

_BASE62 = string.ascii_letters + string.digits


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(hashed: str | None, plain: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def _fernet() -> Fernet:
    key = settings.ecocode_secret_key
    # Accept either a raw urlsafe-base64 Fernet key or derive one from an
    # arbitrary secret so operators can drop in any 32+ char string.
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        import base64

        digest = hashlib.sha256(key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None


def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="ecocode-session")


def create_session_cookie(user_id: int, role: str) -> str:
    payload = {"user_id": user_id, "role": role, "issued_at": int(time.time())}
    return _session_serializer().dumps(payload)


def read_session_cookie(cookie_value: str) -> dict | None:
    try:
        return _session_serializer().loads(
            cookie_value, max_age=settings.session_max_age_seconds
        )
    except (BadSignature, SignatureExpired):
        return None


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, key_prefix, key_hash)."""
    secret = "".join(secrets.choice(_BASE62) for _ in range(32))
    full_key = f"eco_live_{secret}"
    key_prefix = f"eco_live_{secret[:4]}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


@dataclass
class LoginAttemptTracker:
    """In-memory sliding-window login rate limiter (single-server deployment)."""

    max_attempts: int = 5
    window_seconds: int = 15 * 60

    def __post_init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    def _key(self, username: str, ip: str) -> str:
        return f"{username}:{ip}"

    def is_blocked(self, username: str, ip: str) -> bool:
        now = time.time()
        k = self._key(username, ip)
        attempts = [t for t in self._attempts.get(k, []) if now - t < self.window_seconds]
        self._attempts[k] = attempts
        return len(attempts) >= self.max_attempts

    def record_failure(self, username: str, ip: str) -> None:
        k = self._key(username, ip)
        self._attempts.setdefault(k, []).append(time.time())

    def record_success(self, username: str, ip: str) -> None:
        self._attempts.pop(self._key(username, ip), None)


login_attempts = LoginAttemptTracker()
