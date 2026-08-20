# سند فنی (TECH) — گیت‌وی سازمانی EcoCode

| | |
|---|---|
| **نام محصول** | EcoCode Gateway |
| **نسخه سند** | 1.1 — طراحی فنی برای پیاده‌سازی (اصلاحیهٔ ۱) |
| **تاریخ** | 2026-08-20 |
| **مدیر فنی** | Opus (Tech Lead) |
| **مبنا** | `docs/PRD.md` v0.2 (§1 توضیح آپ‌استریم، F1.0، F4.6، R1 منتفی) |
| **مخاطب** | دو توسعه‌دهندهٔ Sonnet (Dev1: infra+backend، Dev2: frontend) |

> **اصلاحیهٔ ۱ (2026-08-20، دستور تغییر مالک محصول):**
> ۱) آپ‌استریم دیگر Claude خودِ Anthropic نیست؛ یک سرویس ثالث **Claude-سازگار** است (همان API؛ خود Claude Code CLI با آن کار می‌کند و اشتراک‌گذاری بین کاربران مجاز است → ریسک ToS منتفی). آدرس آپ‌استریم همه‌جا از `UPSTREAM_BASE_URL` می‌آید و هرگز hardcode نمی‌شود.
> ۲) mode جدید و **اصلی** آپ‌استریم: `cli-creds` — استفادهٔ مجدد از اعتبارنامه‌ای که Claude Code روی همین سرور ذخیره کرده (`~/.claude/.credentials.json`، mount فقط‌خواندنی). حالت‌های `apikey` و `mock` حفظ شدند؛ flow OAuth ادمین (mode قدیم A) حذف شد.
> ۳) الزام جدید F4.6: پوشهٔ اختصاصی هر کاربر + اجرای چت وب به‌صورت سشن headless خودِ **Claude Code CLI** در همان پوشه (`claude -p --output-format stream-json`) با ذخیرهٔ `cli_session_id` برای ادامهٔ گفتگو؛ endpointهای فایل workspace اضافه شد (§۸)؛ اسکیمای DB و compose و جریان درخواست به‌روز شد (§۲، §۳، §۵).
> ۴) تقسیم کار §۱۰ به‌روز شد (Dev1: CLI runner + workspace؛ Dev2: پنل «فایل‌های من»).

> این سند تصمیم‌های فنی **قطعی** است. هر جا گزینه‌ای انتخاب شده، انتخاب نهایی است و نباید در پیاده‌سازی دوباره باز شود. تصمیم‌های محصولی در PRD تأیید شده‌اند و اینجا فقط پیاده‌سازی می‌شوند.

---

## فهرست

۱. انتخاب استک · ۲. توپولوژی کانتینرها و پورت‌ها · ۳. اسکیمای دیتابیس · ۴. اتصال به آپ‌استریم (cli-creds اصلی) · ۵. جریان درخواست (وب = CLI runner، API = HTTP مستقیم) · ۶. پیکربندی LiteLLM · ۷. طراحی احراز هویت · ۸. قرارداد API بک‌اند · ۹. نقشهٔ صفحات فرانت · ۱۰. تقسیم کار دو توسعه‌دهنده · ۱۱. امنیت و برنامهٔ تست

---

## ۱. انتخاب استک (Stack)

انتخاب: **boring, reliable, mainstream**. هیچ چیز عجیبی که یک تیم دو‌نفره را زمین بزند.

| لایه | انتخاب | دلیل |
|---|---|---|
| **Backend** | Python 3.12 + **FastAPI** + Uvicorn | async native (برای streaming SSE و مدیریت subprocess ضروری)، تولید خودکار OpenAPI (قرارداد Dev1↔Dev2)، هم‌زبان با LiteLLM، اکوسیستم بالغ `httpx`/`asyncpg`/`sqlalchemy` |
| **CLI runner** | **Claude Code CLI** (headless، نصب‌شده در image بک‌اند با Node 20) | موتور اجرای چت وب agentic (F4.6): سشن در پوشهٔ کاربر، ساخت/ویرایش فایل، resume با session id. نصب داخل image (نه mount باینری هاست) تا وابستگی glibc/نسخه نداشته باشیم |
| **ORM / Migration** | **SQLAlchemy 2.0 (async)** + **Alembic** | migration نسخه‌دار، تایپ‌سیف |
| **DB** | **PostgreSQL 16** | تراکنشی، JSONB برای متادیتا و پیام‌ها، کافی تا صدها کاربر بدون sharding |
| **Gateway engine** | **LiteLLM Proxy** (کانتینر رسمی `ghcr.io/berriai/litellm`) | کلید مجازی، budget، محدودیت مدل per-key، شمارش توکن — برای سطح passthrough (Cline/OpenAI-سازگار) |
| **Frontend** | **React 18 + Vite + TypeScript** | استاندارد صنعت، build سریع، بیلد داخل Docker (Node 18 host بی‌اهمیت) |
| **UI kit / RTL** | **MUI (Material UI)** با `direction: rtl` + `stylis-plugin-rtl` + فونت **Vazirmatn** | پشتیبانی رسمی RTL، کامپوننت آماده برای پنل ادمین |
| **State / data fetch** | **TanStack Query** + **Zustand** (state سبک) | cache و invalidation آماده؛ برای SSE از `fetch` + `ReadableStream` استفاده می‌شود |
| **Markdown/Code render** | `react-markdown` + `rehype-highlight` + `remark-gfm` | رندر پاسخ چت با syntax highlighting و دکمهٔ کپی |
| **Reverse proxy / static** | **Nginx** (کانتینر) | سرو SPA، ترمینیشن TLS، پروکسی `/api` به بک‌اند، پروکسی `/v1` passthrough |
| **Password hashing** | **argon2id** (`argon2-cffi`) | استاندارد امروزی |
| **Encryption at rest** | `cryptography` Fernet (AES-128-CBC + HMAC) با کلید از env | رمز کردن کلید API آپ‌استریم (mode apikey) |
| **LDAP** | `ldap3` (pure-python) | bind ساده، بدون وابستگی C |
| **Container/Orchestration** | **docker-compose v5** روی یک سرور لینوکسی | مطابق PRD؛ همان سروری که Claude Code روی آن لاگین شده |

**آپ‌استریم:** در سراسر این سند «آپ‌استریم» یعنی **سرویس ثالث Claude-سازگار** (نه Anthropic). سطح API آن همان Messages API است و Claude Code CLI مستقیماً با آن کار می‌کند. آدرس پایه همیشه از `UPSTREAM_BASE_URL` خوانده می‌شود.

---

## ۲. توپولوژی کانتینرها + docker-compose + پورت‌ها

### ۲.۱ نمودار توپولوژی

```
              Host (Linux, single server — همان سرور لاگین‌شدهٔ Claude Code)
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  ~/.claude/.credentials.json  (اعتبارنامهٔ Claude Code روی هاست)              │
  │        │ mount :ro                                                            │
  │  Internet / اینترنت سازمان                                                     │
  │      │ 443 (TLS) / 80 (redirect→443)                                           │
  │      ▼                                                                         │
  │  ┌─────────────┐   docker network: ecocode_net (bridge, internal)             │
  │  │   nginx     │  سرو SPA + reverse proxy                                      │
  │  └──────┬──────┘                                                               │
  │         │  /api/*  → backend:8000      /v1/* → backend:8000 (Cline/OpenAI)     │
  │         ▼                                                                      │
  │  ┌────────────────────────────────────┐      ┌──────────────┐                 │
  │  │  backend (FastAPI) :8000            │      │   litellm    │                 │
  │  │  ├─ pipeline auth/ACL/quota/ledger  │─────▶│   :4000      │                 │
  │  │  ├─ CLI Runner (چت وب):             │admin │  custom      │                 │
  │  │  │   claude -p --output-format      │ API  │  upstream    │                 │
  │  │  │   stream-json  (subprocess)      │      │  handler     │                 │
  │  │  │   cwd=/data/users/<id>/workspace │      └──────┬───────┘                 │
  │  │  ├─ /host_claude (:ro creds sync)   │             │                         │
  │  │  └─ volume /data/users              │             │ HTTPS (+HTTPS_PROXY)    │
  │  └──────┬──────────────┬───────────────┘             ▼                         │
  │         │ asyncpg      │ CLI ──▶ UPSTREAM_BASE_URL   $UPSTREAM_BASE_URL        │
  │         ▼              ▼        (مستقیم از CLI)      (سرویس Claude-سازگار)     │
  │  ┌──────────────────────────────────┐                                          │
  │  │        postgres :5432             │   ┌──────────────────────────┐          │
  │  │  DBs: ecocode  +  litellm         │   │ mock-upstream :8080       │◀─ dev   │
  │  └──────────────────────────────────┘   │ (SSE canned) + mock-claude│  profile │
  │                                          └──────────────────────────┘          │
  └──────────────────────────────────────────────────────────────────────────────┘
```

**دو مسیر به آپ‌استریم (تصمیم قطعی):**
- **چت وب** → **CLI Runner** داخل backend: هر پیام یک اجرای headless از Claude Code CLI در پوشهٔ کاربر. CLI خودش مستقیم با `UPSTREAM_BASE_URL` حرف می‌زند (با اعتبارنامهٔ sync‌شده). LiteLLM در این مسیر نیست.
- **کلید API (Cline/…)** → backend → **LiteLLM** → custom upstream handler → HTTP مستقیم `POST $UPSTREAM_BASE_URL/v1/messages`.

**ماژول ایزولهٔ آپ‌استریم** دو نقطهٔ تماس دارد که هر دو در یک پکیج (`backend/app/upstream/`) نگه‌داری می‌شوند: (الف) `credentials.py` — خواندن/sync/تشخیص انقضای اعتبارنامه (سه mode)، (ب) `litellm_handler.py` — custom handler که در کانتینر litellm mount می‌شود و از همان منطق credential استفاده می‌کند. تغییر مکانیزم سرویس آپ‌استریم فقط این پکیج را لمس می‌کند.

### ۲.۲ سرویس‌های docker-compose

| service | image | نقش | پورت host | پورت internal | profile |
|---|---|---|---|---|---|
| `nginx` | `nginx:1.27-alpine` (build stage برای SPA) | TLS، static، reverse proxy | `443`, `80` | 80 | default |
| `backend` | build از `./backend` (python:3.12-slim + **Node 20 + `@anthropic-ai/claude-code`**) | FastAPI، auth، ledger، quota، **CLI runner**، workspace | — | `8000` | default |
| `litellm` | `ghcr.io/berriai/litellm:main-stable` | gateway engine مسیر passthrough + custom upstream handler | — | `4000` | default |
| `postgres` | `postgres:16-alpine` | دو دیتابیس: `ecocode`، `litellm` | — | `5432` | default |
| `mock-upstream` | build از `./mock-upstream` (python:3.12-slim, FastAPI) | استاب SSE بدون credential (مسیر passthrough) | — | `8080` | `dev` |

**volumeها و mountهای backend:**
```yaml
backend:
  volumes:
    - users_data:/data/users                          # workspace کاربران (named volume)
    - ${CLAUDE_CREDS_DIR:-~/.claude}:/host_claude:ro  # اعتبارنامهٔ Claude Code هاست (فقط‌خواندنی)
    - attachments_data:/data/attachments
```
اسکریپت `mock-claude` (استاب CLI برای mode mock — بخش ۵.۶) داخل image بک‌اند در `/app/bin/mock-claude` قرار دارد؛ کانتینر جداگانه لازم ندارد.

**قواعد شبکه:**
- فقط `nginx` روی host expose می‌شود. بقیه در شبکهٔ داخلی `ecocode_net` و **بدون** `ports:` (فقط `expose:`).
- TLS: در فاز اول self-signed یا cert سازمانی داخل `nginx` (mount از `./certs`). چون همه‌چیز پشت nginx است، TLS در لبه کافی است.

### ۲.۳ پلن پورت (قطعی)

| منبع | مقصد | پورت | یادداشت |
|---|---|---|---|
| کاربر/Cline | nginx | 443 | تنها نقطهٔ ورود |
| nginx | backend | 8000 | `/api`, `/v1` |
| backend | litellm | 4000 | مسیر passthrough + admin API (`/key/generate` و…) |
| backend | postgres | 5432 | DB `ecocode` |
| litellm | postgres | 5432 | DB `litellm` (جدا) |
| litellm | mock-upstream | 8080 | فقط mode mock |
| litellm→handler / CLI | `$UPSTREAM_BASE_URL` | 443 | از طریق `HTTPS_PROXY` env اگر ست شده |

### ۲.۴ متغیرهای محیطی مهم (`.env`)

```dotenv
# --- عمومی ---
ECOCODE_ENV=prod                      # prod | dev
UPSTREAM_MODE=mock                    # mock | cli_creds | apikey   (پیش‌فرض dev/تأیید = mock؛ prod = cli_creds)
UPSTREAM_BASE_URL=https://claude-compat.example.com   # آدرس سرویس Claude-سازگار — هرگز hardcode نمی‌شود

# --- CLI Runner ---
CLAUDE_CREDS_DIR=/home/amin/.claude   # مسیر اعتبارنامهٔ Claude Code روی هاست (mount :ro)
CLI_MAX_CONCURRENCY=4                 # سقف پروسه‌های هم‌زمان CLI (کل سیستم)
CLI_TIMEOUT_SECONDS=300               # حداکثر عمر یک اجرای CLI به ازای هر پیام
MOCK_CLI=0                            # 1 → runner به‌جای claude، /app/bin/mock-claude را اجرا می‌کند

# --- رمزنگاری ---
ECOCODE_SECRET_KEY=<32-byte base64>   # کلید Fernet برای رمز کردن کلید apikey آپ‌استریم
SESSION_SECRET=<random 64 hex>        # امضای کوکی session

# --- دیتابیس ---
POSTGRES_PASSWORD=<...>
ECOCODE_DATABASE_URL=postgresql+asyncpg://ecocode:***@postgres:5432/ecocode
LITELLM_DATABASE_URL=postgresql://litellm:***@postgres:5432/litellm

# --- LiteLLM ---
LITELLM_MASTER_KEY=sk-master-<random>     # فقط backend می‌داند
LITELLM_BASE_URL=http://litellm:4000

# --- Outbound proxy (اختیاری، برای تانل به آپ‌استریم) ---
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=litellm,backend,postgres,mock-upstream,localhost,127.0.0.1

# --- LDAP (فاز P3، می‌تواند خالی بماند) ---
LDAP_ENABLED=false
LDAP_URI=ldaps://ldap.corp.local:636
LDAP_BASE_DN=ou=people,dc=corp,dc=local
LDAP_BIND_TEMPLATE=uid={username},ou=people,dc=corp,dc=local
```

کلید apikey آپ‌استریم (mode apikey) در env نیست — از پنل ادمین وارد و رمزشده در `settings` ذخیره می‌شود. mode `cli_creds` هیچ secret در env/DB ندارد؛ فقط mount فایل هاست.

---

## ۳. اسکیمای دیتابیس (SQL DDL)

دیتابیس `ecocode` (منبع authoritative ما). دیتابیس `litellm` جداست و کاملاً مدیریت‌شده توسط خود LiteLLM (به آن دست نمی‌زنیم).

```sql
-- ============ ENUMs ============
CREATE TYPE user_role   AS ENUM ('admin', 'user');
CREATE TYPE auth_source AS ENUM ('local', 'ldap');
CREATE TYPE quota_period AS ENUM ('daily', 'weekly', 'monthly');
CREATE TYPE upstream_mode AS ENUM ('mock', 'cli_creds', 'apikey');

-- ============ users ============
-- کاربر محلی و کاربر لینک‌شده به LDAP در یک جدول.
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(150) NOT NULL UNIQUE,      -- برای LDAP = uid سازمانی
    display_name    VARCHAR(255),
    email           VARCHAR(255),
    role            user_role   NOT NULL DEFAULT 'user',
    auth_source     auth_source NOT NULL DEFAULT 'local',
    password_hash   TEXT,                              -- argon2id؛ NULL برای کاربر ldap
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE, -- غیرفعال = بلاک لاگین + ابطال کلیدها
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_local_has_pw
        CHECK (auth_source <> 'local' OR password_hash IS NOT NULL)
);
CREATE INDEX idx_users_active ON users(is_active);
-- workspace کاربر جدول ندارد: قرارداد فایل‌سیستمی /data/users/<user_id>/workspace
-- (ساخت در اولین استفاده، مالکیت app user، پرمیشن 0700).

-- ============ api_keys ============
-- کلید شخصی کاربر. متن خام هرگز ذخیره نمی‌شود؛ فقط hash + prefix نمایشی.
-- هر کلید به یک virtual key در LiteLLM نگاشت می‌شود.
CREATE TABLE api_keys (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,          -- مثلا «Cline لپ‌تاپ»
    key_prefix          VARCHAR(16)  NOT NULL,          -- مثلا "eco_live_a1b2" برای نمایش
    key_hash            TEXT NOT NULL,                  -- sha256(full_key) hex
    litellm_key_id      TEXT,                           -- شناسه/توکن virtual key در LiteLLM
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ,
    CONSTRAINT uq_key_hash UNIQUE (key_hash)
);
CREATE INDEX idx_api_keys_user   ON api_keys(user_id);
CREATE INDEX idx_api_keys_active ON api_keys(is_active);

-- ============ models ============
-- کاتالوگ مدل‌های در دسترس گیت‌وی + وزن‌های سهمیه (ضمیمهٔ الف).
-- وزن‌ها = «امتیاز مصرف» به ازای هر ۱۰۰۰ توکن؛ admin-configurable.
CREATE TABLE models (
    id                  BIGSERIAL PRIMARY KEY,
    model_key           VARCHAR(100) NOT NULL UNIQUE,  -- نامی که گیت‌وی می‌شناسد، مثلا "claude-opus"
    display_name        VARCHAR(150) NOT NULL,         -- «Claude Opus»
    upstream_model      VARCHAR(150) NOT NULL,         -- id مدل نزد سرویس آپ‌استریم؛ به CLI با --model پاس می‌شود
    input_weight        NUMERIC(10,4) NOT NULL,        -- credit / 1000 input tokens
    output_weight       NUMERIC(10,4) NOT NULL,        -- credit / 1000 output tokens
    cache_read_weight   NUMERIC(10,4) NOT NULL,        -- credit / 1000 cache-read tokens
    is_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ model_policies ============
-- مدل‌های مجاز به ازای هر کاربر (whitelist). خالی = هیچ مدلی مجاز نیست.
CREATE TABLE model_policies (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id    BIGINT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, model_id)
);

-- ============ quotas ============
-- سقف مصرف دوره‌ای به ازای هر کاربر. یک ردیف فعال به ازای هر کاربر.
CREATE TABLE quotas (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period          quota_period NOT NULL DEFAULT 'weekly',
    limit_credits   NUMERIC(14,2) NOT NULL,            -- سقف امتیاز مصرف در دوره
    period_start    TIMESTAMPTZ NOT NULL DEFAULT now(),-- شروع دورهٔ جاری؛ هفتگی = شنبه ۰۰:۰۰ محلی
    bonus_credits   NUMERIC(14,2) NOT NULL DEFAULT 0,  -- افزایش موقت ادمین (F3.4) تا پایان دوره
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_quota_user UNIQUE (user_id)
);

-- ============ usage_ledger ============
-- منبع authoritative مصرف. یک ردیف به ازای هر درخواست موفق (post-response).
-- مبنای شمارش = فیلد usage خودِ پاسخ آپ‌استریم (مسیر HTTP) یا رویداد result خروجی
-- stream-json خودِ CLI (مسیر چت وب) — نه تخمین محلی (R4 در PRD).
CREATE TABLE usage_ledger (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    api_key_id          BIGINT REFERENCES api_keys(id) ON DELETE SET NULL, -- NULL = چت وب
    model_id            BIGINT NOT NULL REFERENCES models(id),
    surface             VARCHAR(20) NOT NULL,           -- 'web_chat' | 'api'
    input_tokens        INT NOT NULL DEFAULT 0,
    output_tokens       INT NOT NULL DEFAULT 0,
    cache_read_tokens   INT NOT NULL DEFAULT 0,
    cache_write_tokens  INT NOT NULL DEFAULT 0,         -- ثبت می‌شود ولی فعلا وزن = input
    credits             NUMERIC(14,4) NOT NULL,         -- محاسبه‌شده بر اساس وزن‌های لحظهٔ ثبت
    request_id          VARCHAR(100),                   -- request-id پاسخ HTTP یا cli session id
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ledger_user_time  ON usage_ledger(user_id, created_at);
CREATE INDEX idx_ledger_key        ON usage_ledger(api_key_id);
CREATE INDEX idx_ledger_model_time ON usage_ledger(model_id, created_at);

-- ============ conversations ============
CREATE TABLE conversations (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(300) NOT NULL DEFAULT 'گفتگوی جدید',
    model_id        BIGINT REFERENCES models(id),      -- مدل انتخابی این گفتگو
    -- شناسهٔ سشن Claude Code CLI برای resume (--resume). NULL تا اولین پیام.
    cli_session_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ                         -- soft delete
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC) WHERE deleted_at IS NULL;

-- ============ messages ============
CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,               -- 'user' | 'assistant'
    content         TEXT NOT NULL,                      -- متن (markdown)
    -- رویدادهای ساختاری سشن CLI (tool_use ها، فایل‌های ساخته‌شده و…) به‌صورت JSONB:
    content_blocks  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);

-- ============ attachments ============
-- فایل‌های آپلودشده در گفتگو (F4.4). فایل داخل workspace کاربر کپی می‌شود
-- (تا CLI ببیندش)، متادیتا در DB.
CREATE TABLE attachments (
    id              BIGSERIAL PRIMARY KEY,
    message_id      BIGINT REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(150) NOT NULL,
    size_bytes      BIGINT NOT NULL,
    storage_path    TEXT NOT NULL,                      -- مسیر داخل workspace کاربر، نه قابل traversal
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attach_conv ON attachments(conversation_id);

-- ============ audit_log ============
-- F7.2: لاگین‌ها، ساخت/ابطال کلید، تغییر سهمیه، رد شدن به‌دلیل سقف.
-- هرگز محتوای چت اینجا نمی‌آید.
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT REFERENCES users(id) ON DELETE SET NULL, -- کیست که این کار را کرد
    target_id   BIGINT REFERENCES users(id) ON DELETE SET NULL, -- روی چه کاربری
    action      VARCHAR(80) NOT NULL,   -- login.success | login.fail | key.create | key.revoke
                                        -- | quota.change | request.denied_quota | user.disable
                                        -- | upstream.mode_change | workspace.file_delete
    detail      JSONB,                  -- متادیتا: ip, key_prefix, old/new limit ... (بدون محتوای چت)
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_time   ON audit_log(created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

-- ============ settings ============
-- key-value برای تنظیمات سراسری + کلید رمزشدهٔ آپ‌استریم (mode apikey).
-- مقادیر حساس با Fernet (ECOCODE_SECRET_KEY) رمز می‌شوند؛ ستون is_encrypted نشانه‌گذاری می‌کند.
CREATE TABLE settings (
    key             VARCHAR(120) PRIMARY KEY,
    value           TEXT,               -- اگر is_encrypted: ciphertext base64
    is_encrypted    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      BIGINT REFERENCES users(id) ON DELETE SET NULL
);
-- کلیدهای شناخته‌شده:
--   upstream.mode                = 'cli_creds'|'apikey'|'mock'  (override runtime؛ env اولویت دارد)
--   upstream.apikey        (enc) = توکن دستی سرویس آپ‌استریم (mode apikey)
--   quota.warn_threshold         = '0.8'  (هشدار ۸۰٪)
-- توجه: در mode cli_creds هیچ secret در DB نیست؛ منبع = فایل mount‌شدهٔ هاست.
```

**نکات طراحی:**
- **usage_ledger منبع حقیقت سهمیه است.** LiteLLM budget صرفاً کمربند ایمنی دومِ مسیر passthrough است (بخش ۶).
- **workspace جدول ندارد.** مسیر با قرارداد `user_id` ساخته می‌شود؛ endpointهای فایل (بخش ۸) با شناسهٔ opaque کار می‌کنند نه نام فایل در URL.
- **reset دورهٔ هفتگی** با مقایسهٔ `period_start` انجام می‌شود، نه با پاک‌کردن ledger. یک job سبک (بخش ۵.۵) وقتی دوره تمام شد `period_start` را جلو می‌برد؛ مصرف دوره = جمع `credits` روی ledger از `period_start` تا now.
- **جداسازی حریم خصوصی:** `audit_log` و همهٔ endpointهای ادمین **هرگز** به `messages.content` و فایل‌های workspace کاربران دسترسی ندارند. این در سطح کد (نبود join/مسیر) و در سطح review تضمین می‌شود.

---

## ۴. اتصال به آپ‌استریم — mode اصلی `cli_creds`

سه mode؛ سوییچ با `UPSTREAM_MODE` (env، اولویت‌دار) یا `settings.upstream.mode` (runtime از پنل ادمین).

| mode | منبع credential | مصرف‌کننده | کاربرد |
|---|---|---|---|
| **`cli_creds`** (اصلی/prod) | فایل اعتبارنامهٔ Claude Code روی هاست | CLI runner (ذاتی) + LiteLLM handler (خواندن توکن) | استقرار واقعی |
| `apikey` | توکن دستی، رمزشده در `settings` | CLI runner (از طریق env توکن) + LiteLLM handler | وقتی سرویس آپ‌استریم کلید مستقیم بدهد |
| `mock` | — | mock-claude (چت وب) + mock-upstream (passthrough) | dev / تأیید E2E بدون credential |

### ۴.۱ mode `cli_creds` — استفادهٔ مجدد از اعتبارنامهٔ Claude Code هاست

**پیش‌فرض:** ادمین قبلاً روی همین سرور یک‌بار `claude login` (یا `claude setup-token`) را علیه سرویس Claude-سازگار انجام داده و اعتبارنامه در `~/.claude/.credentials.json` (یا مسیر معادل، قابل تنظیم با `CLAUDE_CREDS_DIR`) ذخیره شده است.

```
هاست: ~/.claude/.credentials.json ──(mount :ro)──▶ کانتینر backend: /host_claude/.credentials.json
                                                          │ sync یک‌طرفه (entrypoint + هر 60s)
                                                          ▼
                                        /home/app/.claude/.credentials.json  (HOME کانتینر)
                                          ├──▶ Claude Code CLI (چت وب): خودش می‌خواند
                                          └──▶ upstream package: access_token را استخراج و
                                               به LiteLLM handler می‌دهد (مسیر passthrough)
```

- **sync یک‌طرفه هاست→کانتینر:** mount مستقیم ro به `$HOME/.claude` کافی نیست چون CLI به دایرکتوری config خودش نیاز به نوشتن دارد؛ پس فایل ro در `/host_claude` mount و توسط یک task پس‌زمینهٔ backend (هر ۶۰ ثانیه + هنگام استارت) به HOME کپی می‌شود. **هاست منبع حقیقت است**: اگر CLI روی هاست توکن را refresh کند، حداکثر ۶۰ ثانیه بعد کانتینر هم دارد.
- **refresh/انقضا:** فایل اعتبارنامه شامل `expiresAt` (و refresh token) است. خود CLI در حین اجرا در صورت نیاز refresh می‌کند (در کپی داخل کانتینر). upstream package قبل از هر استفادهٔ passthrough، `expiresAt` را چک می‌کند؛ اگر منقضی و نسخهٔ هاست جدیدتر بود → sync فوری؛ اگر هر دو منقضی → وضعیت «قطع» و خطای 503 با پیام فارسی.
- **نمایش وضعیت (F1.2):** `GET /api/admin/upstream/status`:
```json
{ "mode": "cli_creds", "connected": true, "expires_at": "2026-09-01T10:00:00Z",
  "expiring_soon": false, "creds_source": "/host_claude/.credentials.json",
  "base_url": "https://claude-compat.example.com", "last_synced": "2026-08-20T09:00:00Z" }
```
- **اتصال مجدد (F1.3):** اگر منقضی شد، پنل ادمین بنر می‌دهد: «روی سرور دستور `claude login` را دوباره اجرا کنید». پس از لاگین مجدد هاست، sync خودکار وضعیت را سبز می‌کند — هیچ داده‌ای از دست نمی‌رود و restart لازم نیست.
- **هیچ credential به مرورگر یا DB نمی‌رود.**

### ۴.۲ mode `apikey`

ادمین در پنل توکن سرویس آپ‌استریم را وارد می‌کند → Fernet-رمز در `settings.upstream.apikey`. مصرف:
- **LiteLLM handler:** هدر مناسب (Bearer یا `x-api-key`، مطابق آنچه سرویس آپ‌استریم می‌پذیرد؛ پیش‌فرض هر دو شکل تست و در handler ثابت می‌شود) علیه `UPSTREAM_BASE_URL`.
- **CLI runner:** توکن از طریق متغیر محیطی به پروسهٔ CLI پاس می‌شود (`ANTHROPIC_AUTH_TOKEN`) به‌همراه `ANTHROPIC_BASE_URL=$UPSTREAM_BASE_URL` — Claude Code همین envها را می‌شناسد.

### ۴.۳ mode `mock`

- **مسیر passthrough:** LiteLLM به `mock-upstream:8080` وصل می‌شود (SSE قوطی‌شده + usage جعلی).
- **مسیر چت وب:** با `MOCK_CLI=1`، runner به‌جای `claude` اسکریپت `/app/bin/mock-claude` را اجرا می‌کند (بخش ۵.۶).
- هیچ credential و هیچ دسترسی اینترنتی لازم نیست؛ کل استک قابل bring-up و E2E است.

### ۴.۴ فراخوانی HTTP مستقیم (مسیر passthrough، همهٔ modeها)

LiteLLM handler درخواست را به شکل Messages API به `POST $UPSTREAM_BASE_URL/v1/messages` می‌فرستد:
- `Authorization: Bearer <token>` (cli_creds/apikey) + `anthropic-beta: oauth-2025-04-20` (برای توکن‌های سبک oauth که Claude Code تولید می‌کند) + `anthropic-version: 2023-06-01`.
- body: شکل Messages API (system, messages, max_tokens, stream, …). سرویس آپ‌استریم Claude-سازگار است، پس همین کافی است.
- `HTTPS_PROXY` از env رعایت می‌شود.

---

## ۵. جریان درخواست هر دو سطح (auth · ACL · quota · ثبت مصرف · streaming)

**تصمیم قطعی مسیرها:** چت وب **همیشه** از CLI runner می‌گذرد (مسیر «چت سادهٔ» HTTP مستقیم نداریم). دلیل: یک مسیر واحد یعنی یک پروتکل رندر، یک منطق usage، و قابلیت agentic/فایل همیشه در دسترس (F4.6)؛ دو مسیر یعنی دو باگ‌سطح. سطح کلید API (Cline/OpenAI-سازگار) **همیشه** HTTP مستقیم از طریق LiteLLM است — ابزارها خودشان agentic هستند و فقط completion می‌خواهند.

هر دو سطح از یک **pipeline مشترک** auth/ACL/quota/ledger در backend عبور می‌کنند.

### ۵.۱ سطح (الف) — چت وب از طریق CLI Runner

```
Browser ──(session cookie)──▶ nginx /api/conversations/{id}/messages (POST, stream)
   ▼ backend
 [۱ AUTH]   session cookie → user. نامعتبر/غیرفعال → 401.
 [۲ ACL ]   مدل گفتگو در model_policies[user]؟ نه → 403 «مدل مجاز نیست».
 [۳ QUOTA pre-check]
            used = SUM(usage_ledger.credits WHERE user AND created_at >= quota.period_start)
            budget = quota.limit_credits + quota.bonus_credits
            used >= budget → 429 + پیام فارسی + audit: request.denied_quota.
 [۴ WORKSPACE]  اطمینان از وجود /data/users/<user_id>/workspace (ساخت 0700 در اولین بار).
            attachmentهای پیام (در صورت وجود) داخل workspace کپی شده‌اند (بخش attachments).
 [۵ ذخیرهٔ پیام کاربر]  message(role=user) در DB.
 [۶ RUN CLI]  spawn پروسهٔ Claude Code headless (مشخصات کامل ۵.۴):
            claude -p "<متن پیام>" --output-format stream-json --verbose
                   --model <models.upstream_model>
                   [--resume <conversations.cli_session_id>]      # اگر ادامهٔ گفتگوست
            cwd = workspace کاربر
 [۷ STREAM] رویدادهای stream-json خط‌به‌خط از stdout پروسه خوانده و به پروتکل SSE ما
            ترجمه می‌شوند (نگاشت ۵.۳) → مرورگر به‌صورت تدریجی رندر می‌کند.
            رویداد system:init → session_id استخراج و در conversations.cli_session_id ذخیره
            (فقط بار اول؛ در resume همان می‌ماند).
 [۸ ثبت مصرف post-response]
            رویداد پایانی result شامل usage است (input_tokens, output_tokens,
            cache_read_input_tokens, ...) →
            credits = input/1000*w_in + output/1000*w_out + cache_read/1000*w_cache
            INSERT usage_ledger (surface='web_chat', request_id=cli_session_id).
            message(role=assistant) با متن نهایی + content_blocks (خلاصهٔ tool_useها) ذخیره.
            conversation.updated_at لمس.
```

**ادامهٔ گفتگو (F4.5):** با `--resume <cli_session_id>` خود CLI کل context قبلی سشن را دارد؛ ما تاریخچه را دوباره نمی‌فرستیم. تاریخچهٔ DB ما برای نمایش UI و ماندگاری است، نه برای context.

### ۵.۲ سطح (ب) — کلید API شخصی از Cline/ابزار OpenAI-سازگار (HTTP مستقیم)

Cline/aider/… مستقیم به `/v1/messages` (Anthropic-شکل) یا `/v1/chat/completions` (OpenAI-شکل) روی همان دامنه می‌زنند، با هدر `x-api-key: eco_live_…` یا `Authorization: Bearer eco_live_…`.

```
Cline ──(Bearer eco_live_...)──▶ nginx /v1/messages  یا  /v1/chat/completions  (POST)
   ▼ backend (passthrough endpoint)
 [۱ AUTH]   کلید از هدر → sha256 → lookup در api_keys (key_hash). نبود/غیرفعال/کاربر غیرفعال
            → 401. last_used_at به‌روز.
 [۲ ACL ]   مدل درخواستی (body.model) → نگاشت به models.model_key → در model_policies[user]؟
            نه → 403.
 [۳ QUOTA pre-check]  همان منطق ۵.۱[۳].
 [۴ CALL] backend ──▶ litellm ──▶ custom upstream handler ──▶ POST $UPSTREAM_BASE_URL/v1/messages.
            اگر endpoint = /v1/chat/completions، LiteLLM خودش شکل OpenAI را ترجمه می‌کند.
            metadata: {user_id, api_key_id, model_key, surface:api}.
 [۵ STREAM] SSE از آپ‌استریم تا Cline پیوسته proxy می‌شود (هر دو فرمت stream پشتیبانی می‌شوند).
 [۶ ثبت مصرف]  از فیلد usage پاسخ آپ‌استریم؛ همان فرمول؛ api_key_id پر.
            (چت وب و API از یک سهمیهٔ کاربر کم می‌شوند — F5.3.)
```

**نکتهٔ کلیدی:** auth/ACL/quota/ledger **در backend ما** اتفاق می‌افتد، نه در LiteLLM و نه در CLI. Cline هرگز مستقیم به LiteLLM یا آپ‌استریم نمی‌رسد (PRD بند ۴).

### ۵.۳ نگاشت stream-json → SSE ما (چت وب)

خروجی `--output-format stream-json` خطی-JSON است. backend هر خط را parse و به رویداد SSE سادهٔ خودمان ترجمه می‌کند تا فرانت با یک پروتکل ثابت کار کند:

| رویداد CLI (stream-json) | SSE ما به مرورگر |
|---|---|
| `{"type":"system","subtype":"init","session_id":...}` | `event: start` `{conversation_id}` (+ ذخیرهٔ cli_session_id) |
| `{"type":"assistant","message":{content:[{type:"text",...}]}}` | `event: delta` `{text}` (متن تدریجی) |
| بلوک `tool_use` در پیام assistant (مثلاً Write/Edit) | `event: tool` `{name, summary}` — UI به‌صورت «در حال ساخت فایل …» نشان می‌دهد |
| `{"type":"result","usage":{...},"is_error":false}` | `event: done` `{credits_used, files_changed[]}` |
| `{"type":"result","is_error":true}` یا خطای پروسه | `event: error` `{message فارسی}` |

مسیر passthrough (۵.۲) دست‌نخورده SSE خام آپ‌استریم را forward می‌کند (سازگاری ابزارها)؛ این نگاشت فقط مال چت وب است.

### ۵.۴ مشخصات CLI Runner (قطعی)

| مورد | تصمیم |
|---|---|
| **مدل اجرا** | یک subprocess به ازای هر پیام کاربر (`asyncio.create_subprocess_exec`). بدون پروسهٔ مقیم. |
| **فرمان** | `claude -p <prompt> --output-format stream-json --verbose --model <upstream_model> [--resume <sid>]` |
| **cwd** | `/data/users/<user_id>/workspace` — قبل از spawn ساخته/بررسی می‌شود؛ realpath باید زیر `/data/users/<user_id>/` باشد. |
| **هم‌زمانی** | semaphore سراسری = `CLI_MAX_CONCURRENCY` (پیش‌فرض ۴) + قفل به ازای هر گفتگو = ۱ (پیام دوم در همان گفتگو تا پایان قبلی 409 «پاسخ قبلی در جریان است»). |
| **timeout** | `CLI_TIMEOUT_SECONDS` (پیش‌فرض ۳۰۰s): ابتدا SIGTERM، بعد از ۱۰s SIGKILL؛ SSE با `event: error` بسته می‌شود؛ اگر تا آن لحظه رویداد usage نیامده، مصرفی ثبت نمی‌شود. |
| **env پاس‌شده** | فقط لیست سفید: `HOME=/home/app` (که `.claude/.credentials.json` sync‌شده آنجاست)، `ANTHROPIC_BASE_URL=$UPSTREAM_BASE_URL`، در mode apikey: `ANTHROPIC_AUTH_TOKEN=<توکن>`، `HTTP(S)_PROXY/NO_PROXY`، `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. هیچ env دیگر backend (secrets, DB URL) به CLI نمی‌رسد. |
| **انتخاب مدل** | `models.upstream_model` گفتگو → `--model`. ACL قبل از spawn چک شده. |
| **پرمیشن ابزارها** | **بدون `--dangerously-skip-permissions`.** به‌جای آن allowlist صریح: `--allowedTools "Read(./**),Write(./**),Edit(./**),Glob,Grep"` و `--disallowedTools "Bash,WebFetch,WebSearch"`. **توجیه:** (الف) headless هرگز روی prompt پرمیشن بلاک نمی‌شود چون هر چیزِ مجاز auto-approve است و باقی رد می‌شود؛ (ب) `Bash` عملاً فرار از confinement پوشه است (می‌تواند workspace کاربر دیگر را بخواند) پس در فاز ۱ ممنوع؛ (ج) `WebFetch/WebSearch` بسته تا داده از سازمان بیرون نرود و مصرف قابل پیش‌بینی بماند. الگوهای `./**` دسترسی فایل را به workspace محدود می‌کنند. فاز ۲ در صورت نیازِ سناریوهای کدنویسی، `Bash` را با sandbox سطح‌OS (bubblewrap) اضافه می‌کند — نه زودتر. |
| **usage** | از رویداد `result` (فیلد `usage`) → فرمول ضمیمهٔ الف. `total_cost_usd` نادیده گرفته می‌شود (واحد ما credit است). |
| **پاک‌سازی** | on-disconnect مرورگر: پروسه kill نمی‌شود (پاسخ تمام و ذخیره می‌شود) — کاربر با reload ادامه را در تاریخچه می‌بیند. |

### ۵.۵ reset دوره‌ای و به‌روزرسانی مصرف

- مصرف نمایش‌داده‌شده = query زندهٔ روی `usage_ledger` (نه cache). تأخیر ~۰ (PRD حداکثر ۱ دقیقه می‌خواهد).
- **job سبک** (APScheduler داخل backend، هر ۵ دقیقه): برای هر quota که `now >= period_start + interval`، `period_start` را به مرز دورهٔ بعد ببر و `bonus_credits` را صفر کن.

### ۵.۶ mock کردن مسیر CLI (`MOCK_CLI=1`)

اسکریپت `/app/bin/mock-claude` (پایتونی، داخل image بک‌اند) دقیقاً همان قرارداد را شبیه‌سازی می‌کند:
1. آرگومان‌ها را می‌پذیرد (`-p`, `--output-format stream-json`, `--model`, `--resume`, `--allowedTools`, …).
2. روی stdout به ترتیب emit می‌کند: `system:init` (با session_id ثابتِ برگرفته از `--resume` یا تصادفی) → چند رویداد `assistant` متنی با تأخیر مصنوعی (تست رندر تدریجی) → یک بلوک `tool_use` از نوع Write و **واقعاً یک فایل نمونه در cwd می‌سازد** (تست پنل فایل‌ها) → `result` با usage جعلی معقول (مثلاً in=1200, out=350, cache_read=400).
3. exit code 0.

نتیجه: کل مسیر چت وب + پنل فایل‌ها + ledger بدون هیچ credential واقعی E2E-تست می‌شود.

---

## ۶. پیکربندی LiteLLM + آنچه عمداً به آن نمی‌سپاریم

LiteLLM فقط در مسیر passthrough (سطح کلید API) است؛ چت وب از آن عبور نمی‌کند.

### ۶.۱ نمونهٔ `litellm_config.yaml`

```yaml
model_list:
  # هر مدل گیت‌وی به custom provider = upstream handler وصل می‌شود.
  - model_name: claude-opus          # نامی که backend/Cline صدا می‌زند
    litellm_params:
      model: ecocode-upstream/claude-opus        # نگاشت به models.upstream_model در handler
  - model_name: claude-sonnet
    litellm_params:
      model: ecocode-upstream/claude-sonnet
  - model_name: claude-haiku
    litellm_params:
      model: ecocode-upstream/claude-haiku

litellm_settings:
  # custom handler = بخشی از پکیج ایزولهٔ upstream (بخش ۲.۱).
  # سه mode (cli_creds/apikey/mock) را با env سوییچ می‌کند؛
  # base_url = os.environ/UPSTREAM_BASE_URL  (mode mock → http://mock-upstream:8080)
  custom_provider_map:
    - provider: "ecocode-upstream"
      custom_handler: ecocode_upstream_handler.adapter   # فایل mount‌شده در کانتینر
  drop_params: true

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  database_url: "os.environ/LITELLM_DATABASE_URL"
  # budget به‌عنوان کمربند ایمنی دوم فعال است ولی authoritative نیست (بخش ۶.۳).
```

کانتینر litellm این mountها را دارد: فایل handler + volume اعتبارنامهٔ sync‌شده (فقط‌خواندنی، برای خواندن access token در mode cli_creds). **handler تنها فایلی است که با تغییر مکانیزم سرویس آپ‌استریم عوض می‌شود** (به‌همراه `credentials.py` هم‌پکیجش).

### ۶.۲ چرخهٔ عمر virtual key (admin API)

backend با `LITELLM_MASTER_KEY` مدیریت می‌کند:

| رخداد در EcoCode | فراخوانی LiteLLM |
|---|---|
| ساخت کلید API کاربر (F5.1) | `POST /key/generate` با `{ models: [مدل‌های مجاز کاربر], metadata: {ecocode_user_id, ecocode_key_id}, max_budget: <بزرگ، کمربند ایمنی> }` → `key` برمی‌گردد؛ در `api_keys.litellm_key_id` ذخیره. |
| ابطال کلید (F5.2) | `POST /key/delete` با آن key. |
| غیرفعال‌سازی کاربر (F2.2) | حلقه روی همهٔ کلیدهای کاربر → `POST /key/delete`. |
| تغییر مدل‌های مجاز (F3.1) | `POST /key/update` روی همهٔ کلیدهای کاربر با `models` جدید. |

> نکته: چون auth/ACL/quota را ما در backend انجام می‌دهیم، virtual key در LiteLLM عمدتاً برای **جداسازی و شمارش** است. حتی اگر کسی کلید LiteLLM را بدزدد، به backend ما دسترسی ندارد چون Cline از طریق کلید ما (`eco_live_…`) می‌آید نه کلید LiteLLM.

### ۶.۳ آنچه عمداً به LiteLLM نمی‌سپاریم — و چرا

| مسئولیت | متولی | دلیل |
|---|---|---|
| **سهمیهٔ authoritative** | **backend + usage_ledger** | مدل ما «توکن وزن‌دار» است: `input×w_in + output×w_out + cache_read×w_cache` با وزن‌های **admin-configurable** و **کاهش cache-read**. LiteLLM budget فقط برحسب دلار/توکن خام است و منطق وزن‌دهی ما را نمی‌فهمد. مهم‌تر: **مسیر چت وب اصلاً از LiteLLM عبور نمی‌کند** (CLI مستقیم به آپ‌استریم می‌زند)، پس فقط ledger ما هر دو سطح را یک‌جا می‌بیند. |
| **reset هفتگی** | **backend (quota.period_start)** | دورهٔ هفتگی با مرز مشخص محلی، منطق ماست. |
| **auth کاربر / کلید** | **backend** | session، LDAP، argon2، لینک کلید↔کاربر — هیچ‌کدام در LiteLLM نیست. |
| **ACL مدل per-user واقعی** | **backend** | اعمال قبل از ارسال/spawn + پیام فارسی؛ محدودیت per-key در LiteLLM کمربند دوم است. |
| **تاریخچهٔ چت، workspace، حریم خصوصی** | **backend** | محتوا هرگز به LiteLLM/ادمین نمی‌رسد. |

LiteLLM budget را با یک سقف **بزرگ** (مثلاً ۲× سهمیهٔ کاربر) ست می‌کنیم؛ فقط اگر منطق ما به‌دلیل باگ نشتی کرد، جلوی فاجعه را بگیرد. **منبع حقیقت همیشه usage_ledger ماست.**

---

## ۷. طراحی احراز هویت (Auth)

### ۷.۱ وب — session cookie

- لاگین موفق → session ایجاد. **cookie امضاشدهٔ سرور** (`itsdangerous`/JWT کوتاه‌عمر داخل کوکی) با فلگ‌های:
  `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, عمر مثلاً ۸ ساعت با sliding renewal.
- payload کوکی: `{ user_id, role, issued_at }` امضاشده با `SESSION_SECRET`. server-side session store لازم نیست (stateless) ولی برای «logout همه‌جا» یک ستون `session_epoch` روی users قابل افزودن است (فاز بعد).
- CSRF: چون `SameSite=Lax` + همه‌ی mutationها JSON با `Content-Type: application/json` هستند (نه form)، سطح حمله پایین است؛ علاوه بر آن هدر `X-Requested-With` را الزامی می‌کنیم.

### ۷.۲ LDAP bind + کاربر محلی

```
لاگین(username, password):
  user = users[username]
  if not user or not user.is_active: → 401 (پیام عمومی، بدون افشای وجود کاربر)
  if user.auth_source == 'ldap' and LDAP_ENABLED:
      bind_dn = LDAP_BIND_TEMPLATE.format(username=username)
      try: ldap3.Connection(LDAP_URI, bind_dn, password, auto_bind=True)   # bind واقعی
      except: → 401
  else:  # local
      if not argon2.verify(user.password_hash, password): → 401
  session ساخته می‌شود. audit: login.success (یا login.fail).
```

- **کاربر محلی:** رمز با **argon2id** (`argon2-cffi`، پارامترهای پیش‌فرض امن). هیچ رمزی plain لاگ نمی‌شود.
- **کاربر LDAP:** رکورد `users` با `auth_source=ldap` و `password_hash=NULL`. فاز اول: ادمین دستی می‌سازد، LDAP فقط رمز را verify می‌کند.
- **fallback خرابی LDAP:** کاربران محلی همیشه کار می‌کنند (F2.1).

### ۷.۳ فرمت کلید API

```
فرمت نمایش‌شده به کاربر (فقط یک‌بار، هنگام ساخت):
    eco_live_<32 char base62 تصادفی>
      └ prefix ثابت    └ راز

ذخیره:
    key_prefix = "eco_live_" + اولین ۴ کاراکتر راز   → برای نمایش در لیست
    key_hash   = sha256(کل کلید).hex()               → تنها چیز ذخیره‌شده از راز
```
- متن کامل هرگز ذخیره نمی‌شود (F5.2). lookup در auth: `sha256(هدر ورودی)` → `WHERE key_hash=`.
- sha256 کافی است چون کلید ۳۲ کاراکتر تصادفی high-entropy است (نه رمز کم‌آنتروپی؛ نیاز به argon2 ندارد).
- ابطال: `is_active=false` + `revoked_at` + حذف virtual key در LiteLLM.

### ۷.۴ مدل نقش

- دو نقش: `admin`, `user` (F2.3). enforcement با dependency در FastAPI: `require_admin` روی همهٔ endpointهای `/api/admin/*`.
- کاربر فقط به داده، کلید، مصرف و **workspace خودش** دسترسی دارد (isolation در سطح query و مسیر فایل: همیشه از `current_user.id`، هرگز از ورودی URL).

---

## ۸. قرارداد API بک‌اند EcoCode (REST)

پایه: `/api`. همه JSON مگر endpointهای stream (SSE)، آپلود (multipart) و دانلود فایل. این جدول **قرارداد بین Dev1 و Dev2** است؛ Dev2 فقط علیه این می‌سازد. Dev1 موظف است `openapi.json` را از FastAPI export و در repo نگه دارد.

### احراز هویت و session
| متد | مسیر | نقش | هدف |
|---|---|---|---|
| POST | `/api/auth/login` | عمومی | لاگین (username, password) → set cookie |
| POST | `/api/auth/logout` | user | حذف session |
| GET | `/api/auth/me` | user | اطلاعات کاربر جاری + role + مدل‌های مجاز + خلاصهٔ سهمیه |

### چت و تاریخچه (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/conversations` | لیست گفتگوهای کاربر (paginate, search با `?q=`) |
| POST | `/api/conversations` | ساخت گفتگوی جدید (`{title?, model_key}`) |
| GET | `/api/conversations/{id}` | جزئیات + پیام‌ها (فقط مالک) |
| PATCH | `/api/conversations/{id}` | تغییر عنوان / مدل |
| DELETE | `/api/conversations/{id}` | حذف (soft) — سشن CLI مرتبط دیگر resume نمی‌شود |
| POST | `/api/conversations/{id}/messages` | **ارسال پیام → اجرای CLI runner → پاسخ SSE استریم** (pipeline ۵.۱، پروتکل ۵.۳) |
| POST | `/api/conversations/{id}/attachments` | آپلود فایل (multipart) → کپی داخل workspace + attachment id |
| GET | `/api/attachments/{id}` | دانلود فایل پیوست (فقط مالک گفتگو) |

### workspace — فایل‌های کاربر (جدید، F4.6)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/workspace/files` | لیست بازگشتی فایل‌های workspace خود کاربر: `[{file_id, name, relpath, size_bytes, modified_at}]` |
| GET | `/api/workspace/files/{file_id}` | دانلود فایل |
| DELETE | `/api/workspace/files/{file_id}` | حذف فایل (اختیاری در UI؛ endpoint موجود) + audit `workspace.file_delete` |

**قرارداد `file_id`:** شناسهٔ opaque = base64url(مسیر نسبی داخل workspace). سرور هنگام resolve: decode → join با root workspace کاربرِ session → `realpath` → **الزام** به قرارگیری زیر همان root (رد traversal و symlink-escape با 404). نام فایل یا user id هرگز در URL نیست؛ هویت همیشه از session.

### کلید API شخصی (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/keys` | لیست کلیدهای کاربر (prefix, name, last_used, active) |
| POST | `/api/keys` | ساخت کلید (`{name}`) → **کلید کامل فقط در این پاسخ** |
| DELETE | `/api/keys/{id}` | ابطال کلید |

### مصرف (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/usage/me` | مصرف دورهٔ جاری / سقف، تفکیک مدل و کلید، روند روزانه (F6.1) |

### passthrough سازگار با ابزار (کلید API، نه session)
| متد | مسیر | هدف |
|---|---|---|
| POST | `/v1/messages` | Anthropic Messages API passthrough (pipeline ۵.۲)، SSE |
| POST | `/v1/chat/completions` | OpenAI Chat Completions passthrough، SSE |
| GET | `/v1/models` | لیست مدل‌های مجاز همان کلید (برای auto-discovery ابزارها) |

### ادمین — کاربران
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/users` | لیست کاربران |
| POST | `/api/admin/users` | ساخت کاربر (local یا ldap-linked) |
| GET | `/api/admin/users/{id}` | جزئیات + policy + quota |
| PATCH | `/api/admin/users/{id}` | ویرایش (نقش، فعال/غیرفعال، رمز محلی) |
| DELETE | `/api/admin/users/{id}` | حذف کاربر (+ابطال کلیدها؛ workspace روی دیسک می‌ماند تا پاک‌سازی دستی) |

### ادمین — سیاست و سهمیه
| متد | مسیر | هدف |
|---|---|---|
| PUT | `/api/admin/users/{id}/policy` | تنظیم مدل‌های مجاز (`{model_keys: [...]}`) → sync به LiteLLM |
| PUT | `/api/admin/users/{id}/quota` | تنظیم `{period, limit_credits}` |
| POST | `/api/admin/users/{id}/quota/bonus` | افزایش موقت سهمیه (`{bonus_credits}`) (F3.4) |

### ادمین — مدل‌ها و وزن‌ها
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/models` | لیست مدل‌ها + وزن‌ها |
| POST | `/api/admin/models` | افزودن مدل |
| PATCH | `/api/admin/models/{id}` | ویرایش وزن‌ها / فعال‌سازی |

### ادمین — مصرف کل و audit
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/usage` | مصرف کل سازمان، رتبه‌بندی کاربران، تفکیک مدل، روند (F6.2) |
| GET | `/api/admin/usage/export.csv` | خروجی CSV |
| GET | `/api/admin/audit` | لاگ رخدادها (filter بر action/user/بازهٔ زمانی) |

### ادمین — اتصال آپ‌استریم (بخش ۴)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/upstream/status` | وضعیت اتصال (mode, connected, expires_at, base_url, creds_source) |
| PUT | `/api/admin/upstream/apikey` | ست توکن دستی (mode apikey؛ رمزشده ذخیره می‌شود) |
| PUT | `/api/admin/upstream/mode` | سوییچ mode (`cli_creds`/`apikey`/`mock`) + audit `upstream.mode_change` |

### سلامت
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/health` | liveness: `{status, db, litellm, upstream_mode, upstream_connected, cli_available}` |

**قرارداد خطا (یکنواخت):** بدنهٔ `{ "error": { "code": "quota_exceeded", "message": "پیام فارسی قابل‌نمایش" } }` با status مناسب (401/403/409/429/400/503/500). Dev2 روی `error.message` رندر می‌کند و روی `error.code` منطق. کد `chat_busy` (409) برای پیام هم‌زمان در یک گفتگو.

---

## ۹. نقشهٔ صفحات فرانت (React + Vite، فارسی RTL)

کل UI فارسی RTL با فونت Vazirmatn؛ سوییچ به انگلیسی (فاز P3) با i18next آماده می‌شود ولی رشته‌ها فارسی-اول.

| مسیر | صفحه | دسترسی | محتوا |
|---|---|---|---|
| `/login` | ورود | عمومی | فرم username/password، پیام خطای فارسی، rate-limit-aware |
| `/chat` | چت (پیش‌فرض کاربر) | user | سایدبار تاریخچه + پنجرهٔ گفتگو + **پنل «فایل‌های من»** |
| `/chat/:id` | گفتگوی خاص | user | همان، گفتگوی انتخابی |
| `/usage` | مصرف من | user | نوار پیشرفت سهمیه، تفکیک مدل/کلید، نمودار روند روزانه، هشدار ۸۰٪ |
| `/keys` | کلیدهای API من | user | لیست + ساخت (نمایش یک‌بارهٔ کلید در modal با دکمهٔ کپی) + ابطال |
| `/admin/users` | مدیریت کاربران | admin | جدول، ساخت/ویرایش/غیرفعال، لینک به policy/quota |
| `/admin/policies` | سیاست‌ها | admin | تنظیم مدل‌های مجاز و سهمیهٔ هر کاربر |
| `/admin/usage` | مصرف کل | admin | رتبه‌بندی کاربران، تفکیک مدل، روند، دکمهٔ CSV |
| `/admin/models` | مدل‌ها و وزن‌ها | admin | ویرایش input/output/cache وزن هر مدل |
| `/admin/settings` | اتصال آپ‌استریم | admin | وضعیت اتصال (mode/انقضا/base_url)، ورود توکن apikey، سوییچ mode، راهنمای «claude login روی سرور» |
| `/admin/audit` | لاگ رخدادها | admin | جدول فیلترپذیر audit_log |

**اجزای کلیدی چت:**
- **model picker** فیلترشده به مدل‌های مجاز کاربر (از `/api/auth/me`).
- **رندر استریم:** خواندن SSE (پروتکل ۵.۳: `start`/`delta`/`tool`/`done`/`error`) با `fetch` + `ReadableStream`؛ نمایش تدریجی؛ رویداد `tool` به‌صورت chip «در حال ساخت/ویرایش فایل…»؛ markdown با `react-markdown`؛ code block با highlight و دکمهٔ کپی.
- **پنل «فایل‌های من» (جدید، مینیمال):** drawer/tab کنار چت؛ `GET /api/workspace/files` → لیست (نام، حجم، تاریخ) + دکمهٔ دانلود؛ refresh خودکار بعد از رویداد `done` که `files_changed` دارد. حذف: فاز بعد (endpoint هست، UI اختیاری).
- **آپلود فایل:** drag/drop یا دکمه → `POST attachments` → نمایش chip؛ انواع متن/کد/PDF/تصویر.
- **سایدبار:** لیست گفتگوها، جستجو، تغییر عنوان (inline)، حذف؛ isolation کامل.
- **بنر سهمیه:** وقتی `used/budget >= 0.8` هشدار زرد؛ وقتی رد شد پیام قرمز فارسی. حالت `chat_busy` (409): دکمهٔ ارسال قفل با پیام «پاسخ قبلی در جریان است».

**RTL:** `ThemeProvider` با `direction:'rtl'` + `CacheProvider` (emotion) + `stylis-plugin-rtl`. `dir="rtl"` روی `<html>`.

---

## ۱۰. تقسیم کار دو توسعه‌دهندهٔ Sonnet (مرز سخت ماژول)

**مرز:** `openapi.json` (بخش ۸). Dev1 آن را می‌سازد و freeze می‌کند؛ Dev2 فقط علیه آن می‌سازد. هیچ‌کدام فایل‌های دیگری را لمس نمی‌کنند.

```
repo/
  backend/          ← Dev1 (انحصاری) — شامل upstream package، CLI runner، bin/mock-claude
  mock-upstream/    ← Dev1 (انحصاری)
  litellm/          ← Dev1 (config + upstream handler)
  docker-compose.yml, .env.example, nginx/  ← Dev1
  frontend/         ← Dev2 (انحصاری)
  docs/openapi.json ← Dev1 تولید، Dev2 مصرف (read-only برای Dev2)
```

### Dev1 — Infra + Backend (ترتیب کار)
1. **skeleton compose:** postgres + backend سلامت‌ده + nginx. `docker compose up` سبز شود.
2. **DB + migrations:** Alembic، همهٔ جداول بخش ۳ (با `cli_session_id`)، seed مدل‌ها با وزن‌های پیش‌فرض + ادمین اولیه.
3. **auth:** login/logout/me، session cookie، argon2، (LDAP پشت فلگ، ماک‌شدنی).
4. **mock دوقلو:** (الف) سرویس `mock-upstream` (SSE قوطی‌شده + usage جعلی برای مسیر passthrough)؛ (ب) اسکریپت `bin/mock-claude` (stream-json قوطی‌شده + ساخت فایل واقعی در cwd — بخش ۵.۶). → کل استک با `UPSTREAM_MODE=mock` و `MOCK_CLI=1` بالا می‌آید بدون credential.
5. **CLI Runner + چت وب** (۵.۱، ۵.۳، ۵.۴): workspace provisioning، spawn/timeout/semaphore، parse stream-json → SSE ما، ذخیرهٔ `cli_session_id`، ثبت ledger از رویداد `result`. اول علیه `mock-claude`، بعد CLI واقعی.
6. **workspace endpoints:** list/download/delete با قرارداد `file_id` opaque + تست‌های traversal.
7. **upstream package + litellm handler:** `credentials.py` (sync هاست→کانتینر، تشخیص انقضا) + custom handler سه-mode برای مسیر passthrough؛ اول mock، سپس cli_creds، سپس apikey.
8. **passthrough** `/v1/messages` و `/v1/chat/completions` + auth کلید (۵.۲).
9. **quota** pre-check + reset job + models/policy/quota endpoints + sync به LiteLLM.
10. **admin:** users, usage aggregation, CSV, audit, upstream status/apikey/mode.
11. **export `openapi.json`** و به‌روزنگه‌داشتنش (بعد از هر تغییر قرارداد به Dev2 اطلاع).

### Dev2 — Frontend (ترتیب کار)
1. **scaffold Vite + MUI RTL + Vazirmatn + router + i18next + TanStack Query.** Dockerfile چندمرحله‌ای (build با Node 18 در image، سرو با nginx).
2. **API client** تولیدشده از `openapi.json` (openapi-typescript) + wrapper خطای یکنواخت + هندلر session/401.
3. **login** + گارد نقش‌ها + layout RTL.
4. **chat** (سنگین‌ترین): سایدبار، model picker، ارسال، **رندر SSE (پروتکل start/delta/tool/done/error)**، markdown/code/copy، آپلود فایل، حالت `chat_busy`.
5. **پنل «فایل‌های من»** (مینیمال): لیست + دانلود، refresh بعد از `done`.
6. **usage** کاربر (نوار + نمودار + هشدار).
7. **keys** کاربر (ساخت با نمایش یک‌بارهٔ کلید).
8. **admin:** users → policies → models → usage(+CSV) → settings(upstream) → audit.
9. صیقل RTL، حالت‌های خطا/خالی، پیام‌های فارسی.

**تا آماده‌شدن backend، Dev2 چگونه کار کند؟** دو مسیر مستند:
- **الف)** `frontend` را با `VITE_API_BASE=http://localhost/api` به backend واقعی (که Dev1 با mock دوقلو بالا آورده) وصل کن — روش ترجیحی، چون از مرحلهٔ ۴ Dev1 کل استک بدون credential کار می‌کند.
- **ب)** اگر backend هنوز نیست: **MSW (Mock Service Worker)** با fixtureهای مطابق `openapi.json` — Dev2 مستقل جلو می‌رود.

### چک‌لیست یکپارچه‌سازی (Integration checklist)
- [ ] `docker compose --profile dev up` کل استک را با `UPSTREAM_MODE=mock` + `MOCK_CLI=1` بالا می‌آورد.
- [ ] `GET /api/health` سبز (db, litellm, upstream=mock, cli_available=true).
- [ ] لاگین ادمین اولیه؛ ساخت کاربر + policy + quota.
- [ ] چت وب: ارسال پیام → استریم تدریجی mock-claude رندر می‌شود → رویداد `tool` نمایش داده شد → یک ردیف `usage_ledger` با surface=web_chat ثبت شد → `cli_session_id` روی گفتگو پر شد.
- [ ] پیام دوم در همان گفتگو با `--resume` اجرا می‌شود (mock همان session id را echo می‌کند).
- [ ] پنل «فایل‌های من»: فایل ساخته‌شدهٔ mock-claude در لیست است و دانلود می‌شود؛ کاربر دوم آن را **نمی‌بیند**.
- [ ] تست traversal: `file_id` جعلی با `../` → 404.
- [ ] ساخت کلید API → `curl /v1/messages` با `eco_live_…` استریم می‌دهد → از همان سهمیه کم شد.
- [ ] `curl /v1/chat/completions` (شکل OpenAI) هم کار می‌کند.
- [ ] رسیدن به سقف سهمیه → 429 با پیام فارسی + ردیف `request.denied_quota` در audit (هر دو سطح).
- [ ] مدل غیرمجاز → 403؛ پیام هم‌زمان در یک گفتگو → 409 `chat_busy`.
- [ ] سوییچ `UPSTREAM_MODE=cli_creds` (با اعتبارنامهٔ واقعی هاست) → چت وب و passthrough علیه سرویس واقعی.
- [ ] `openapi.json` نسخهٔ فرانت با backend یکی است (CI diff).

---

## ۱۱. امنیت + برنامهٔ تست/تأیید

### ۱۱.۱ نکات امنیتی (الزامی)
- **اعتبارنامهٔ آپ‌استریم:** mode cli_creds: mount فقط‌خواندنی + کپی فقط داخل HOME کانتینر؛ هرگز در DB/لاگ/مرورگر. mode apikey: **Fernet** (کلید از `ECOCODE_SECRET_KEY` در env) در `settings`. کلید env در secrets سرور، نه در repo.
- **کلید API کاربر:** فقط `sha256` ذخیره؛ متن کامل یک‌بار نمایش. `.env` و `certs/` در `.gitignore`.
- **confinement مسیر CLI:** بدون `--dangerously-skip-permissions`؛ allowlist ابزار فقط-فایل با الگوی `./**`؛ `Bash/WebFetch/WebSearch` ممنوع (توجیه در ۵.۴)؛ cwd همیشه realpath-چک‌شده زیر `/data/users/<user_id>/`؛ env پروسه لیست سفید (هیچ secret backend به CLI نمی‌رسد).
- **workspace isolation:** `file_id` opaque + realpath containment check؛ user id هرگز از URL؛ پرمیشن پوشه‌ها 0700 متعلق به app user.
- **rate limiting لاگین:** حداکثر ~۵ تلاش ناموفق در ۱۵ دقیقه به ازای username+IP؛ سپس backoff. همهٔ تلاش‌ها در audit.
- **کنترل منابع CLI:** semaphore هم‌زمانی + timeout + kill group (پروسهٔ فرزند هم بمیرد)؛ سقف حجم workspace هر کاربر (softquota ~1GB، هشدار در UI) در فاز ۱ فقط گزارشی.
- **CORS:** پیش‌فرض بسته. فرانت و API هم‌دامنه (پشت یک nginx)؛ اگر باز شد فقط origin سازمان.
- **بدون محتوای چت در لاگ:** logger backend نباید body پیام‌ها، خروجی CLI یا پاسخ‌ها را لاگ کند. فقط متادیتا (user_id, model, tokens, exit code, request_id). code review این را چک می‌کند.
- **حریم خصوصی ادمین:** endpointهای ادمین هیچ join به `messages.content` و هیچ دسترسی به workspace کاربران ندارند.
- **کوکی:** `HttpOnly + Secure + SameSite=Lax`. TLS در nginx (cert سازمانی).
- **پایداری/بکاپ:** volumeهای `postgres_data`، `users_data`، `attachments_data`؛ اسکریپت `pg_dump` روزانه + tar از `users_data` (مستند در README). ری‌استارت نباید داده را ببرد.
- **آپلود فایل:** ذخیره با نام sanitize‌شده داخل workspace؛ سقف حجم؛ mime whitelist.
- **outbound proxy:** `HTTPS_PROXY`/`NO_PROXY` از env؛ هم CLI و هم LiteLLM handler رعایت می‌کنند.

### ۱۱.۲ برنامهٔ تست/تأیید (verification)

**سطح ۱ — bring-up با mock (بدون credential):**
```
cp .env.example .env      # UPSTREAM_MODE=mock , MOCK_CLI=1
docker compose --profile dev up --build
curl -k https://localhost/api/health           # همه سبز، cli_available=true
```

**سطح ۲ — curl کردن سطح API:**
```
# لاگین ادمین → کوکی
curl -k -c cj https://localhost/api/auth/login -d '{"username":"admin","password":"..."}'
# ساخت کاربر، policy، quota (با کوکی ادمین)
# چت وب از طریق CLI (mock-claude):
curl -k -N -b cj https://localhost/api/conversations/1/messages \
     -d '{"content":"یک فایل نمونه بساز"}'          # SSE: start/delta/tool/done
# فایل ساخته‌شده:
curl -k -b cj https://localhost/api/workspace/files   # لیست شامل فایل mock
# لاگین کاربر، ساخت کلید:
curl -k -b cj https://localhost/api/keys -d '{"name":"test"}'   # → eco_live_...
# تست passthrough Anthropic-شکل:
curl -k https://localhost/v1/messages -H "x-api-key: eco_live_..." \
     -d '{"model":"claude-sonnet","max_tokens":64,"stream":true,
          "messages":[{"role":"user","content":"سلام"}]}'   # SSE قوطی‌شده از mock-upstream
# تست OpenAI-سازگار:
curl -k https://localhost/v1/chat/completions -H "Authorization: Bearer eco_live_..." \
     -d '{"model":"claude-sonnet","stream":true,"messages":[{"role":"user","content":"hi"}]}'
# بررسی ثبت مصرف (هر دو سطح):
curl -k -b cj https://localhost/api/usage/me      # credits افزایش یافت
```
موارد منفی: کلید باطل→۴۰۱، مدل غیرمجاز→۴۰۳، عبور از سقف→۴۲۹ فارسی، `file_id` traversal→۴۰۴، پیام هم‌زمان→۴۰۹.

**سطح ۳ — یک E2E چت کامل از UI:**
1. مرورگر → `/login` → ورود کاربر.
2. `/chat` → انتخاب مدل مجاز → ارسال «یک فایل متنی دربارهٔ X بساز».
3. مشاهدهٔ رندر تدریجی استریم + chip «در حال ساخت فایل» + markdown/code.
4. پنل «فایل‌های من»: فایل جدید ظاهر و دانلود می‌شود.
5. ارسال پیام دوم در همان گفتگو → context حفظ شده (resume).
6. `/usage` → افزایش مصرف و نوار پیشرفت.
7. isolation: با کاربر دوم لاگین → نه گفتگو و نه فایل کاربر اول دیده می‌شود.

**سطح ۴ — تعویض به آپ‌استریم واقعی:** روی سرورِ لاگین‌شده، `UPSTREAM_MODE=cli_creds` و `MOCK_CLI=0` → تکرار سناریوهای سطح ۲/۳ علیه سرویس Claude-سازگار واقعی؛ بررسی `/admin/settings` (وضعیت اتصال و انقضا)؛ در صورت وجود توکن مستقیم، mode `apikey` هم یک‌بار دود-تست شود.

---

## ضمیمهٔ الف — مدل سهمیه (فرمول قطعی + وزن‌های پیش‌فرض)

```
credits(request) =
      input_tokens      / 1000 * model.input_weight
    + output_tokens     / 1000 * model.output_weight
    + cache_read_tokens / 1000 * model.cache_read_weight
```

منبع اعداد توکن: مسیر passthrough = فیلد `usage` پاسخ HTTP آپ‌استریم؛ مسیر چت وب = فیلد `usage` رویداد `result` خروجی stream-json خودِ CLI. در هر دو حالت «گزارش خود سرویس»، نه تخمین محلی (رفع R4).

وزن‌های پیش‌فرض (credit به ازای ۱۰۰۰ توکن)، نسبت‌ها مطابق PRD (Opus=5×Sonnet، Haiku=0.2×Sonnet، cache-read=0.1×input). همه admin-configurable در `/admin/models`:

| مدل | input_weight | output_weight | cache_read_weight |
|---|---|---|---|
| Sonnet (baseline) | 3.0 | 15.0 | 0.3 |
| Opus | 15.0 | 75.0 | 1.5 |
| Haiku | 0.6 | 3.0 | 0.06 |

«امتیاز مصرف» (credit) واحد نمایش به کاربر است — عدد ساده، نه توکن خام (F6/PRD بند ۶).

---

*پایان سند فنی v1.1 (اصلاحیهٔ ۱) — آماده برای شروع پیاده‌سازی توسط دو توسعه‌دهنده.*
