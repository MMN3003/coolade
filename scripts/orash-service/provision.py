"""One-off provisioning for the «حسابداری توسعه ایمن (اوراش)» SQL service.

Run INSIDE the backend container (it needs app.* + the DB + the /data/services
volume). The read DSN is taken from the ORASH_DSN env var so no secret is ever
committed to the repo or typed on a shared command line:

    # 1) copy this script + SKILL.md into the container
    docker cp scripts/orash-service/provision.py coolade-backend-1:/app/provision_orash.py
    docker cp scripts/orash-service/SKILL.md      coolade-backend-1:/tmp/orash_SKILL.md

    # 2) run it, passing the DSN via env (replace the password)
    docker exec -e ORASH_DSN='mssql://sa:PASSWORD@192.168.5.2:53012/Orash1' \
        -e ORASH_SKILL=/tmp/orash_SKILL.md \
        coolade-backend-1 python /app/provision_orash.py

Re-running is safe: it updates the existing service and republishes the skill.
Prefer a dedicated SELECT-only SQL login over `sa` for the DSN (see the report).
"""
import asyncio
import os
import pathlib

from sqlalchemy import select

from app.config import get_settings
from app.db import async_session_factory
from app.models import GrantLevel, Service, ServiceGrant, ServiceKind
from app.security import encrypt_secret

SLUG = "tosee-hesabdari"
NAME = "حسابداری توسعه ایمن (اوراش)"
DESC = "گزارش‌گیری فقط‌خواندنی از دیتابیس حسابداری اوراش/آرمون شرکت توسعه ایمن (SQL Server، Orash1)."
CONFIG = {"row_limit": 500, "display_host": "192.168.5.2\\ORASH · Orash1"}
GRANT_USER_IDS = [6]  # amin (admin). بقیهٔ افراد را از پنل ادمین → سرویس‌ها grant کن.


async def main() -> None:
    settings = get_settings()
    dsn = (os.environ.get("ORASH_DSN") or "").strip()
    if not dsn:
        # fallback: read from a file inside the container so the credential never
        # appears on a command line
        dsn_file = os.environ.get("ORASH_DSN_FILE", "/tmp/dsn.txt")
        if os.path.exists(dsn_file):
            dsn = pathlib.Path(dsn_file).read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("ORASH_DSN یا فایل DSN لازم است (mssql://user:pass@host:port/DATABASE).")
    skill_path = os.environ.get("ORASH_SKILL", "/tmp/orash_SKILL.md")
    skill = pathlib.Path(skill_path).read_text(encoding="utf-8")

    async with async_session_factory() as db:
        svc = (
            await db.execute(select(Service).where(Service.slug == SLUG))
        ).scalar_one_or_none()
        if svc is None:
            svc = Service(
                slug=SLUG, name=NAME, description=DESC, kind=ServiceKind.sql,
                enabled=True, config=CONFIG, conn_read_enc=encrypt_secret(dsn),
                created_by=GRANT_USER_IDS[0], skill_version=0,
            )
            db.add(svc)
            await db.flush()
            print(f"created service id={svc.id}")
        else:
            svc.conn_read_enc = encrypt_secret(dsn)
            svc.name, svc.description, svc.enabled, svc.config = NAME, DESC, True, CONFIG
            print(f"updated service id={svc.id}")

        ver = (svc.skill_version or 0) + 1
        dest = pathlib.Path(settings.services_root) / svc.slug / str(ver)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(skill, encoding="utf-8")
        svc.skill_version = ver
        print(f"published skill v{ver} -> {dest}")

        for uid in GRANT_USER_IDS:
            g = (
                await db.execute(
                    select(ServiceGrant).where(
                        ServiceGrant.service_id == svc.id, ServiceGrant.user_id == uid
                    )
                )
            ).scalar_one_or_none()
            if g is None:
                db.add(
                    ServiceGrant(
                        service_id=svc.id, user_id=uid,
                        level=GrantLevel.read, granted_by=GRANT_USER_IDS[0],
                    )
                )
                print(f"granted read to user {uid}")
            else:
                g.level = GrantLevel.read
                print(f"grant already present for user {uid}")

        await db.commit()
        print(f"DONE  service_id={svc.id}  slug={svc.slug}")


if __name__ == "__main__":
    asyncio.run(main())
