"""Amendment-1 (docs/SERVICES-V2.md) — organizational services: connector
execution + enforcement primitives used by the MCP gateway router.

Enforcement model (DS4 — two layers, prompts are never one of them):
  * layer 1 (here): tool list filtered by grant level, read-SQL guards
    (single SELECT/WITH statement, wrapped row limit, statement timeout,
    session forced read-only), per-user rate limit.
  * layer 2 (the target system): the read DSN must belong to a SELECT-only
    DB account created by the admin. A bug here cannot write — the database
    itself refuses.

Credentials: `services.conn_read_enc`/`conn_write_enc` are Fernet-encrypted
at rest and decrypted ONLY inside this module at call time (mirror of the
D2.4 upstream-token rule). They never appear in tool results or errors.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import deque
from typing import Any

import asyncpg

from app.config import get_settings
from app.models import GrantLevel, Service, ServiceKind

settings = get_settings()


# ---------------------------------------------------------------- rate limit
class _SlidingWindow:
    """Per-user calls/minute cap (SV9). In-process is fine at this scale."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[int, deque[float]] = {}

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        dq = self._hits.setdefault(user_id, deque())
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= self.per_minute:
            return False
        dq.append(now)
        return True


rate_limiter = _SlidingWindow(settings.service_rate_per_min)


# ---------------------------------------------------------------- turn keys
# The general-chat CLI runs IN-PROCESS in the backend container (not in an
# ecows_* container), so it has no workspace gateway key. Before each turn,
# cli_runner mints a short-lived key here and puts it in the generated
# --mcp-config; the gateway resolves it from this in-memory map. Process
# restart voids all keys — fine, the turn dies with the process anyway.
_TURN_KEY_TTL_S = 6 * 3600
_turn_keys: dict[str, tuple[int, float]] = {}  # key -> (user_id, expires_at)


def mint_turn_key(user_id: int) -> str:
    import secrets

    now = time.monotonic()
    for k in [k for k, (_, exp) in _turn_keys.items() if exp < now]:
        _turn_keys.pop(k, None)
    key = f"eco-turn-{secrets.token_urlsafe(24)}"
    _turn_keys[key] = (user_id, now + _TURN_KEY_TTL_S)
    return key


def resolve_turn_key(key: str) -> int | None:
    row = _turn_keys.get(key)
    if not row:
        return None
    user_id, exp = row
    if exp < time.monotonic():
        _turn_keys.pop(key, None)
        return None
    return user_id


# ---------------------------------------------------------------- tool defs
def tools_for(service: Service, level: GrantLevel) -> list[dict[str, Any]]:
    """The MCP tools/list for this service filtered by the caller's grant.
    P5a exposes read tools only; write tools arrive with the P5b mutation
    queue (DS8) — so even a `write` grant sees the read set for now."""
    if service.kind == ServiceKind.sql:
        return [
            {
                "name": "list_tables",
                "description": f"فهرست جدول‌های سرویس «{service.name}» را برمی‌گرداند.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "describe_table",
                "description": "ستون‌ها و نوع دادهٔ یک جدول را برمی‌گرداند.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"table": {"type": "string", "description": "نام جدول"}},
                    "required": ["table"],
                },
            },
            {
                "name": "run_query",
                "description": (
                    f"یک کوئری SELECT روی سرویس «{service.name}» اجرا می‌کند و ردیف‌ها را "
                    f"برمی‌گرداند (حداکثر {settings.service_sql_row_limit} ردیف). فقط SELECT مجاز است."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "کوئری SELECT (یک statement)"}},
                    "required": ["sql"],
                },
            },
        ]
    if service.kind == ServiceKind.files:
        return [
            {
                "name": "list_dir",
                "description": f"فهرست فایل‌ها/پوشه‌های سرویس «{service.name}» را برمی‌گرداند.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "مسیر نسبی؛ خالی = ریشه"}},
                },
            },
            {
                "name": "read_file",
                "description": (
                    f"محتوای یک فایل متنی سرویس «{service.name}» را برمی‌گرداند "
                    f"(حداکثر {settings.service_file_max_mb}MB)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "مسیر نسبی فایل"}},
                    "required": ["path"],
                },
            },
        ]
    if service.kind == ServiceKind.http:
        return [
            {
                "name": "http_get",
                "description": (
                    f"یک درخواست GET به API سرویس «{service.name}» می‌زند (فقط مسیرهای زیر base_url مجاز)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "مسیر نسبی، مثل /reports/summary"},
                        "query": {"type": "object", "description": "پارامترهای query اختیاری"},
                    },
                    "required": ["path"],
                },
            },
        ]
    return []


def params_digest(arguments: dict[str, Any]) -> str:
    """SV7 privacy: audit stores a digest of tool params, never the text."""
    return hashlib.sha256(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


# ---------------------------------------------------------------- sql guards
class SqlGuardError(ValueError):
    """Layer-1 rejection with a user-facing Persian message."""


_FORBIDDEN_WORDS = re.compile(
    r"\b(insert|update|delete|truncate|drop|alter|grant|revoke|create|copy|vacuum|call|do)\b",
    re.IGNORECASE,
)


def clean_read_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise SqlGuardError("کوئری خالی است.")
    if ";" in cleaned:
        raise SqlGuardError("فقط یک statement مجاز است.")
    head = cleaned.lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise SqlGuardError("فقط SELECT مجاز است (سطح دسترسی: read).")
    if _FORBIDDEN_WORDS.search(cleaned):
        raise SqlGuardError("کوئری شامل عبارت نوشتنی است؛ این سرویس فقط‌خواندنی است.")
    return cleaned


def _jsonable(value: Any) -> Any:
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


async def _pg_connect(dsn: str) -> asyncpg.Connection:
    """Read connection with server-side belt-and-braces: statement timeout AND
    a read-only session, regardless of what the account itself allows."""
    return await asyncpg.connect(
        dsn=dsn,
        timeout=5,
        command_timeout=settings.service_sql_timeout_s,
        server_settings={
            "statement_timeout": str(settings.service_sql_timeout_s * 1000),
            "default_transaction_read_only": "on",
            "application_name": "ecocode-svc-gateway",
        },
    )


async def sql_list_tables(dsn: str) -> dict[str, Any]:
    conn = await _pg_connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema') "
            "ORDER BY table_schema, table_name"
        )
        tables = [
            r["table_name"] if r["table_schema"] == "public" else f"{r['table_schema']}.{r['table_name']}"
            for r in rows
        ]
        return {"tables": tables, "row_count": len(tables)}
    finally:
        await conn.close()


async def sql_describe_table(dsn: str, table: str) -> dict[str, Any]:
    schema, _, name = table.rpartition(".")
    schema = schema or "public"
    conn = await _pg_connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema=$1 AND table_name=$2 ORDER BY ordinal_position",
            schema,
            name,
        )
        if not rows:
            return {"error": f"جدول {table} یافت نشد یا این اکانت به آن دسترسی ندارد.", "row_count": 0}
        return {
            "columns": [
                {"name": r["column_name"], "type": r["data_type"], "nullable": r["is_nullable"] == "YES"}
                for r in rows
            ],
            "row_count": len(rows),
        }
    finally:
        await conn.close()


async def sql_run_query(dsn: str, sql: str) -> dict[str, Any]:
    cleaned = clean_read_sql(sql)
    limit = settings.service_sql_row_limit
    # Wrapping (legal for SELECT and WITH subqueries in PG) bounds the result
    # server-side; +1 row detects truncation honestly.
    wrapped = f"SELECT * FROM ({cleaned}) AS _ecocode_sub LIMIT {limit + 1}"
    conn = await _pg_connect(dsn)
    try:
        records = await conn.fetch(wrapped)
    finally:
        await conn.close()
    truncated = len(records) > limit
    records = records[:limit]
    rows = [{k: _jsonable(v) for k, v in dict(r).items()} for r in records]
    out: dict[str, Any] = {"rows": rows, "row_count": len(rows), "sql_executed": cleaned}
    if truncated:
        out["truncated"] = True
        out["note"] = f"نتیجه بیش از {limit} ردیف بود و بریده شد؛ کوئری را محدودتر کن."
    return out


# ---------------------------------------------------------------- files connector
def _resolve_under_root(root: str, rel: str) -> "os.PathLike[str]":
    import os
    from pathlib import Path

    base = Path(root).resolve()
    target = (base / rel.lstrip("/")).resolve()
    if base != target and base not in target.parents:
        raise SqlGuardError("مسیر خارج از محدودهٔ این سرویس است.")
    if not os.path.exists(target):
        raise SqlGuardError(f"مسیر یافت نشد: {rel or '/'}")
    return target


async def files_list_dir(root: str, rel: str) -> dict[str, Any]:
    import asyncio
    import os

    def _ls() -> dict[str, Any]:
        target = _resolve_under_root(root, rel)
        if not os.path.isdir(target):
            raise SqlGuardError("این مسیر پوشه نیست.")
        entries = []
        for name in sorted(os.listdir(target)):
            p = os.path.join(target, name)
            entries.append(
                {
                    "name": name,
                    "type": "dir" if os.path.isdir(p) else "file",
                    "size": None if os.path.isdir(p) else os.path.getsize(p),
                }
            )
        return {"entries": entries, "row_count": len(entries)}

    return await asyncio.to_thread(_ls)


async def files_read(root: str, rel: str) -> dict[str, Any]:
    import asyncio
    import os

    def _read() -> dict[str, Any]:
        target = _resolve_under_root(root, rel)
        if os.path.isdir(target):
            raise SqlGuardError("این مسیر پوشه است، نه فایل.")
        size = os.path.getsize(target)
        cap = settings.service_file_max_mb * 1024 * 1024
        if size > cap:
            raise SqlGuardError(f"فایل بزرگ‌تر از سقف {settings.service_file_max_mb}MB است.")
        with open(target, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise SqlGuardError("فایل باینری است و به‌صورت متن قابل خواندن نیست.")
        return {"content": text, "size": size, "row_count": size}

    return await asyncio.to_thread(_read)


# ---------------------------------------------------------------- http connector
async def http_get(conn_json: str, path: str, query: dict[str, Any] | None) -> dict[str, Any]:
    import httpx

    try:
        conf = json.loads(conn_json)
        base = str(conf["base_url"]).rstrip("/")
    except Exception:
        raise SqlGuardError("پیکربندی اتصال HTTP نامعتبر است؛ به ادمین اطلاع دهید.")
    rel = "/" + str(path).lstrip("/")
    if "://" in str(path) or ".." in rel:
        raise SqlGuardError("فقط مسیر نسبی زیر base_url مجاز است.")
    headers = {str(k): str(v) for k, v in (conf.get("headers") or {}).items()}
    async with httpx.AsyncClient(timeout=settings.service_http_timeout_s) as client:
        resp = await client.get(base + rel, params=query or None, headers=headers)
    body = resp.text
    cap = 1024 * 1024
    truncated = len(body) > cap
    return {
        "status": resp.status_code,
        "body": body[:cap],
        "truncated": truncated,
        "row_count": len(body[:cap]),
    }


async def call_tool(service: Service, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a READ tool against the service's read connector. Raises
    SqlGuardError for layer-1 rejections; other exceptions = upstream errors."""
    from app.security import decrypt_secret

    conn = decrypt_secret(service.conn_read_enc)
    if not conn:
        raise SqlGuardError("اعتبارنامهٔ سرویس قابل بازیابی نیست؛ به ادمین اطلاع دهید.")
    if service.kind == ServiceKind.sql:
        if tool == "list_tables":
            return await sql_list_tables(conn)
        if tool == "describe_table":
            return await sql_describe_table(conn, str(arguments.get("table", "")))
        if tool == "run_query":
            return await sql_run_query(conn, str(arguments.get("sql", "")))
    elif service.kind == ServiceKind.files:
        if tool == "list_dir":
            return await files_list_dir(conn, str(arguments.get("path", "")))
        if tool == "read_file":
            return await files_read(conn, str(arguments.get("path", "")))
    elif service.kind == ServiceKind.http:
        if tool == "http_get":
            q = arguments.get("query")
            return await http_get(conn, str(arguments.get("path", "")), q if isinstance(q, dict) else None)
    raise SqlGuardError(f"ابزار ناشناخته: {tool}")


async def test_connection(service_kind: ServiceKind, conn: str) -> tuple[bool, str]:
    """Admin «تست اتصال» with the (already decrypted) read connection.
    Error text goes to the admin only, never to end users."""
    try:
        if service_kind == ServiceKind.sql:
            c = await _pg_connect(conn)
            try:
                await c.fetchval("SELECT 1")
            finally:
                await c.close()
            return True, "اتصال برقرار شد (SELECT 1 موفق)."
        if service_kind == ServiceKind.files:
            res = await files_list_dir(conn, "")
            return True, f"ریشه در دسترس است ({res['row_count']} مورد)."
        if service_kind == ServiceKind.http:
            res = await http_get(conn, "/", None)
            return True, f"پاسخ base_url: HTTP {res['status']}."
        return False, "نوع connector ناشناخته است."
    except Exception as exc:  # admin-facing diagnostic; connectors never echo secrets
        return False, f"اتصال ناموفق: {type(exc).__name__}: {exc}"
