# EcoCode Gateway

گیت‌وی سازمانی برای مدیریت دسترسی، سهمیه و مصرف یک اشتراک/سرویس Claude-سازگار بین
چند کاربر داخلی — چت وب فارسی (RTL) + کلید API شخصی سازگار با Cline/ابزارهای
OpenAI-سازگار. مطابق `docs/PRD.md` و `docs/TECH.md` (نسخهٔ ۱.۱، اصلاحیهٔ ۱).

## شروع سریع (بدون هیچ credential واقعی)

```bash
cp .env.example .env
docker compose --profile dev up --build -d
curl http://localhost:8085/api/health
```

با تنظیمات پیش‌فرض `.env.example` (`UPSTREAM_MODE=mock`, `MOCK_CLI=1`) کل استک —
شامل چت وب agentic و passthrough سازگار با Cline — بدون هیچ اکانت/کلید واقعی
کار می‌کند. ادمین اولیه از `ADMIN_USERNAME`/`ADMIN_PASSWORD` در `.env` ساخته
می‌شود (پیش‌فرض: `admin` / `ChangeMe123!` — **در prod تغییر دهید**).

نکته: nginx به‌صورت پیش‌فرض روی پورت میزبان `8085` (HTTP ساده) در دسترس است، نه
`443`/TLS. برای فعال‌سازی TLS به بخش «TLS» پایین همین فایل مراجعه کنید.

## معماری

```
مرورگر/Cline → nginx(:8085) → backend(FastAPI:8000) ─┬─ چت وب: CLI Runner (subprocess claude/mock-claude)
                                                       │            → مستقیم به UPSTREAM_BASE_URL
                                                       └─ کلید API: litellm(:4000) → custom handler
                                                                    → UPSTREAM_BASE_URL یا mock-upstream
backend/litellm → postgres (دو DB: ecocode, litellm)
```

جزئیات کامل در `docs/TECH.md`.

## سرویس‌ها

| سرویس | نقش |
|---|---|
| `nginx` | تنها سرویس expose‌شده روی هاست؛ سرو SPA (placeholder تا وقتی فرانت build شود) + پروکسی `/api`، `/v1` |
| `backend` | FastAPI: auth، ledger، quota، CLI runner (چت وب)، workspace، admin API |
| `litellm` | فقط برای مسیر passthrough (کلید API شخصی) — چت وب از آن عبور نمی‌کند |
| `postgres` | دو دیتابیس مجزا: `ecocode` (ماژول ما) و `litellm` (مدیریت‌شده توسط خودش) |
| `mock-upstream` | (`profile: dev`) استاب SSE برای مسیر passthrough در mode `mock` |

## متغیرهای محیطی مهم

فایل `.env.example` را ببینید. مهم‌ترین‌ها:

- `UPSTREAM_MODE`: `mock` (پیش‌فرض/بدون credential) | `cli_creds` (استفادهٔ مجدد از
  اعتبارنامهٔ `claude login` روی هاست) | `apikey` (توکن دستی از پنل ادمین)
- `UPSTREAM_BASE_URL`: آدرس سرویس Claude-سازگار (فقط در mode غیر از mock استفاده می‌شود)
- `CLAUDE_CREDS_DIR`: مسیر مطلق `~/.claude` روی هاست، برای mode `cli_creds`
  (توجه: docker compose علامت `~` را expand نمی‌کند — مسیر مطلق واقعی بدهید)
- `MOCK_CLI=1`: چت وب به‌جای `claude` واقعی از `bin/mock-claude` استفاده می‌کند

## اجرای مقابل سرویس واقعی (production)

```dotenv
ECOCODE_ENV=prod
UPSTREAM_MODE=cli_creds
UPSTREAM_BASE_URL=https://<آدرس سرویس Claude-سازگار شما>
CLAUDE_CREDS_DIR=/home/<user>/.claude   # مسیر مطلق واقعی روی هاست، بعد از یک‌بار `claude login`
MOCK_CLI=0
```

سرویس backend هر ۶۰ ثانیه اعتبارنامه را از `CLAUDE_CREDS_DIR` (mount فقط‌خواندنی)
به داخل کانتینر sync می‌کند. وضعیت اتصال از `GET /api/admin/upstream/status` یا
پنل `/admin/settings` قابل مشاهده است.

## TLS

پیش‌فرض فقط HTTP روی `8085` است. برای فعال‌سازی HTTPS:

1. گواهی/کلید را در `./certs/fullchain.pem` و `./certs/privkey.pem` بگذارید.
2. در `docker-compose.yml` سرویس `nginx`: پورت `443` و mount `./certs` را از کامنت خارج کنید.
3. در `nginx/nginx.conf`: بلوک `server { listen 443 ssl; ... }` را از کامنت خارج کنید.
4. `docker compose up -d --force-recreate nginx`

## بکاپ

- `postgres_data` (دیتابیس): `docker compose exec postgres pg_dump -U ecocode ecocode > backup.sql` — روزانه با cron پیشنهاد می‌شود.
- `users_data` (فایل‌های workspace کاربران): `docker run --rm -v ecocode_users_data:/data -v $(pwd):/backup alpine tar czf /backup/users_data.tar.gz -C /data .`
- `attachments_data`: مشابه بالا.

ری‌استارت سرویس‌ها داده را از بین نمی‌برد (همه در named volume).

## تأیید (verification)

توالی کامل curl در `docs/TECH.md` بخش ۱۱.۲ آمده (با این تفاوت که این استقرار از
`http://localhost:8085` به‌جای `https://localhost` استفاده می‌کند، و mutation های
`/api/*` به هدر `X-Requested-With: XMLHttpRequest` نیاز دارند — بخش ۷.۱).

## توسعه

- بک‌اند: `backend/` (FastAPI + SQLAlchemy async + Alembic). Migration:
  `docker compose exec backend alembic upgrade head` (به‌صورت خودکار در استارت کانتینر هم اجرا می‌شود).
- قرارداد API: `docs/openapi.json` (تولیدشده از FastAPI؛ Dev2 فقط علیه این می‌سازد).
- فرانت‌اند (`frontend/`) مسئولیت جداگانه‌ای دارد و در این README پوشش داده نمی‌شود.

## توقف

```bash
docker compose --profile dev down          # نگه‌داشتن داده‌ها (volumeها باقی می‌مانند)
docker compose --profile dev down -v       # حذف کامل، شامل داده‌ها (فقط dev/test)
```
