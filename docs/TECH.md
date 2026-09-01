# سند فنی (TECH) — گیت‌وی سازمانی EcoCode

| | |
|---|---|
| **نام محصول** | EcoCode Gateway |
| **نسخه سند** | 1.6 — اصلاحیهٔ ۶ پیاده‌سازی‌شده (حذف LiteLLM؛ یکسان‌سازی روی Claude Code CLI) |
| **تاریخ** | 2026-08-24 |
| **مدیر فنی** | Opus (Tech Lead) |
| **مبنا** | `docs/PRD.md` v0.2 (§1 توضیح آپ‌استریم، F1.0، F4.6، R1 منتفی) |
| **مخاطب** | دو توسعه‌دهندهٔ Sonnet (Dev1: infra+backend، Dev2: frontend) |

> **اصلاحیهٔ ۶ (2026-08-24، درخواست کاربر — پیاده‌سازی‌شده):**
> ۱) **حذف LiteLLM؛ یکسان‌سازی هر دو مسیر روی Claude Code CLI:** مسیر passthrough (`/v1/messages` و `/v1/chat/completions`) دیگر از LiteLLM عبور نمی‌کند؛ هر درخواست یک نوبت **تک‌شاتِ بدون‌حالتِ** Claude Code CLI است (`cli_runner.run_oneshot_turn` — بدون conversation/`--resume`/busy-lock؛ همزمانی با همان `_semaphore` سراسری). چون CLI هویت Claude Code را می‌فرستد، گیت توکن اشتراک OAuth ارضا و **۴۲۹ روی opus/sonnet در مسیر API رفع می‌شود** (علت ریشه‌ای تأییدشده: توکن اشتراک بدون بلوکِ هویت Claude Code فقط haiku را می‌پذیرد و opus/sonnet را با `rate_limit_error` رد می‌کند). قرارداد wire بیرونی تغییر نکرد (Anthropic/OpenAI، stream و non-stream). تاریخچهٔ چندنوبتیِ client به یک prompt تخت می‌شود؛ tool definitionهای client به CLI **پل نمی‌شوند** (محدودیت مستند §۵.۲). usage از رویداد `done` مستقیم در ledger با `surface=api` ثبت می‌شود (side-channel `/internal/usage-report` دیگر لازم نیست). fail-fast: خطای پیش از اولین delta به‌صورت status واقعی HTTP برمی‌گردد (parity با peekِ قبلی). مدل مستقیماً از `models.upstream_model` به `claude --model` می‌رود (نیاز به `model_map` منتفی).
> ۲) **کلیدهای API:** دیگر virtual key در LiteLLM ساخته/حذف/به‌روزرسانی نمی‌شود؛ کلید EcoCode به‌تنهایی معتبر است (auth/ACL/quota کاملاً در بک‌اند). ستون `api_keys.litellm_key_id` به‌عنوان legacy بدون migration باقی می‌ماند.
> ۳) **compose و پاک‌سازی:** سرویس `litellm`، volume `litellm_data`، پوشهٔ `litellm/*`، و ماژول `app/services/litellm_client.py` حذف شدند. `health` دیگر litellm را probe نمی‌کند (فیلد legacy همیشه true). `LITELLM_MASTER_KEY` فقط به‌عنوان bearer داخلیِ `/internal/*` نگه داشته شد.
> ۴) **لایهٔ کاهش توکن (اختیاری، پیش‌فرض خاموش):** سرویس opt-in `compression` (profile `compression`) در `./compression` — پروکسی معکوسِ استریمی بین CLI و آپ‌استریم؛ پیش‌فرض pass-throughِ امن (`COMPRESS=0`). نقطهٔ اتصال LLMLingua/tamp در `compression/proxy.py::_maybe_compress`. ⚠️ تغییر بدنهٔ درخواست پیشوندِ prompt-caching را می‌شکند؛ پیش از فعال‌سازی باید با ترافیک واقعی سنجیده شود. (نکته: **Graphify** درخواستیِ کاربر مخصوص ناوبری کدبیس بزرگ است و برای این کاربردِ دستیار سازمانی مناسب نبود؛ tamp/LLMLingua جایگزین شد.)
> ۵) **استقرار:** فعال‌شدن نیازمند `docker compose up -d --build --remove-orphans backend` است (کانتینر `litellm` به‌عنوان orphan حذف می‌شود). تأیید انجام‌شده: اعتبارسنجی compose، کامپایل کل بک‌اند، بارگذاری کامل import graph، تست منطق passthrough (flatten/error-map/fail-fast peek)، و اجرای واقعیِ زیرفرایند CLI (mock) با ترجمهٔ رویداد و گزارش usage.
> ۶) **ادیتور وب (VS Code-style) — مرحلهٔ ۱ (پیاده‌شده):** صفحهٔ `/workspace` با ادیتور **Monaco** (bundle محلی، بدون CDN) روی **همان workspace سندباکسِ موجود** کاربر: مرور درخت فایل، باز کردن، ویرایش، ذخیره. endpointهای جدید backend: `GET /api/workspace/files/{id}/content` (خواندن متن UTF-8؛ رد باینری؛ cap ۱MB) و `PUT /api/workspace/file` (ذخیره با همان realpath-containmentِ CLI — مسیر خارج از workspace رد می‌شود). **بدون شل**؛ اجرای دستور به مرحلهٔ ۲ موکول است. تأیید: `resolve_writable_path` (تست escape/containment) + build موفق فرانت (tsc + vite، Monaco به‌صورت chunk جدا lazy-load).
> ۸) **VS Code واقعی (code-server) — جایگزین ادیتور Monaco (پیاده و verify‌شده):** به‌جای ادیتور تک‌فایلی، **code-server** (نسخهٔ متن‌باز VS Code) مستقر شد: explorer/ادیتور/ترمینال/git/extensions کامل. چون ترمینالش شل کامل است، **داخل همان envelope مرحلهٔ ۲** اجرا می‌شود: روی `ecocode_sandbox_net` (internal، بدون اینترنت مستقیم؛ فقط egress allowlist)، بدون mount کردن creds/DB، سقف mem/pids. nginx (وصل به هر دو شبکه) روی پورت اختصاصی `${CODE_SERVER_PORT:-8091}` به‌صورت root-path پروکسی می‌کند (websocket)، auth با `CODE_SERVER_PASSWORD`. mount: `users_data:/data/users`. profile `ide`. **تأیید:** لاگین‌پیج + assets از nginx، لود کامل workbench در مرورگر، و ایزوله‌سازی egress (example.com مسدود، open-vsx مجاز). **باقی‌مانده (مرحلهٔ بعد):** instanceهای per-user + gating با نشست EcoCode (الان تک‌instanceِ مشترک با یک پسورد است و همهٔ workspaceها زیر /data/users دیده می‌شوند)، embed در صفحهٔ اپ، و volume کانفیگ ماندگار.
> ۷) **اجرای دستور/گیت — مرحلهٔ ۲ (طراحی؛ بخشی بلاک روی آدرس ریپو):** «کد پیچیده + git push» نیازمند **سندباکس اجرایی ایزوله per-session** است (نه روشن‌کردن Bash داخل کانتینر backend که secret/DB/دادهٔ همهٔ کاربران را دارد — ریسک prompt-injection). تصمیم‌ها: کانتینر جدا per-session با **egress allowlist**، بدون mount اعتبارنامه/DB، سقف منابع/زمان؛ اعتبارنامهٔ git **scoped** فقط به ریپوهای مجاز. مقصد push: گیت‌لب سازمان روی `git.ecobin.ir` (آدرس دقیق ریپو بعداً). قدم پیاده‌سازی جداست چون تا آدرس/توکن نباشد، push قابل اتصال نیست.

> **اصلاحیهٔ ۵ (2026-08-22، درخواست کاربر J — فقط طراحی):**
> ⚠️ **هنوز پیاده نمی‌شود.** Dev1 در حال اتمام اصلاحیهٔ ۴ است که `cli_runner.py` را ویرایش می‌کند؛ اصلاحیهٔ ۵ هم runner را لمس می‌کند پس **متوالی** بعد از merge اصلاحیهٔ ۴ اجرا می‌شود. اگر schema لازم شد → revision متوالی Alembic `0005`. تصمیم این سند: **بدون schema؛ فقط فایل‌سیستم** (mirror رویکرد حافظه). بخش‌ها با تگ «اصلاحیهٔ ۵» مشخص‌اند.
> **Issue J — اجرای دستورهای slash کاربر در چت:** وقتی پیام چت با `/` شروع شود، runner آن را (به‌جای متن ساده) به‌عنوان prompt به CLI می‌دهد. **denylist** دستورهای built-in ناامن/بی‌معنا در گیت‌وی (auth/config/permission/model/mcp/session/host-touching) پیش از spawn با پیام فارسی رد می‌شود؛ custom commands و دستورهای شناخته‌شده پاس می‌شوند — چون سندباکس ابزار (Bash/web خاموش، deny بر allowed-tools فرمن‌ماتر غالب است) و cwd-confinement همچنان برقرارند. custom commands در سه لایه: admin-global (`/data/commands/`) + team (`/data/teams/<tid>/commands/`) + personal (`/data/users/<uid>/commands/`)، که runner هر نوبت در `<cwd>/.claude/commands/` سرهم می‌کند (precedence: personal > team > global). endpoint `GET /api/chat/slash-commands` لیست دستورهای در‌دسترس کاربر را می‌دهد؛ composer منوی فیلترپذیر نشان می‌دهد. streaming/usage/security بدون تغییر؛ دستور ردشده هیچ هزینهٔ upstream ندارد. جزئیات denylist/precedence/assembly در **§۵.۱۰** (ground truth headless در آنجا تثبیت شده).
> تقسیم کار اصلاحیهٔ ۵ در انتهای §۱۰.

> **اصلاحیهٔ ۴ (2026-08-22، دو درخواست کاربر — فقط طراحی):**
> ⚠️ **اصلاحیه‌های ۱–۳ پیاده و merge شده‌اند (HEAD 45d9e14).** اصلاحیهٔ ۴ روی اسکیمای v1.3 سوار می‌شود: **revision متوالی Alembic `0004`، down_revision=`0003`**؛ همهٔ تغییرات جدول‌های جدید یا `ADD COLUMN` nullable هستند. بخش‌های این اصلاحیه با تگ «اصلاحیهٔ ۴» مشخص شده‌اند.
> ۱) **Issue H — تیم‌ها/عضویت گروهی:** تیم به‌عنوان شیء درجه‌یک؛ عضویت **چند‌به‌چند** (`teams` + `team_members` با unique `(team_id,user_id)`). CRUD ادمین زیر `/api/admin/teams`؛ تیم‌های کاربر در `/api/auth/me` و نمای فقط‌خواندنی «تیم‌های من». per-user quota/policy دست‌نخورده می‌ماند؛ سیاست/سهمیهٔ تیمی فقط نقطهٔ توسعهٔ آینده است (ساخته نمی‌شود).
> ۲) **Issue I — حافظهٔ مشترک تیم (HR: «کاربران تیم منابع انسانی به حافظه‌های مشترک دسترسی داشته باشند»):** هر تیم یک دایرکتوری مشترک `/data/teams/<team_id>/memory` دارد که در چت هر عضو به‌صورت زیرپوشهٔ `./teams/<slug>/` داخل cwd سشن **در دسترس** می‌شود (رویکرد file-visibility؛ خواندن/نوشتن با همان ابزارهای Read/Write سندباکس). realpath-containment گسترش می‌یابد به **اجتماع** workspace خود کاربر ∪ دایرکتوری تیم‌هایی که عضوشان است. پنل «حافظهٔ مشترک تیم» مثل «فایل‌های من» ولی scoped به تیم انتخابی؛ endpointها زیر `/api/teams/{id}/memory/files` با enforcement عضویت. last-writer-wins (سشن‌ها کوتاه‌عمر per-message).
> ۳) تقسیم کار اصلاحیهٔ ۴ در انتهای §۱۰.

> **اصلاحیهٔ ۳ (2026-08-22، سه درخواست کاربر — فقط طراحی):**
> ⚠️ **این اصلاحیه هنوز پیاده نمی‌شود.** Dev1/Dev2 وسط پیاده‌سازی اصلاحیهٔ ۲ (A/B/C/D) هستند. migration و کدِ اصلاحیهٔ ۳ باید **روی** اسکیمای اصلاحیهٔ ۲ سوار شود (revision متوالی Alembic، بعد از merge و integration اصلاحیهٔ ۲). بخش‌های این اصلاحیه با تگ «اصلاحیهٔ ۳» مشخص شده‌اند.
> ۱) **Issue E — سقف غلتان ۵ ساعته به ازای هر کاربر (علاوه بر سهمیهٔ هفتگی؛ هر دو هم‌زمان enforce):** پنجرهٔ rolling `[now-5h, now]` روی `usage_ledger` (بدون reset period)، سقف per-user در ستون جدید `quotas.limit_credits_5h` (NULL/0 = نامحدود)، طول پنجره از env (`ROLLING_WINDOW_HOURS`, پیش‌فرض ۵). `check_quota` هر دو سطح (چت وب + passthrough) را با کد مجزا `quota_exceeded_5h` رد می‌کند + زمان آزاد شدن پنجره.
> ۲) **Issue F — نمایش لیمیت خود اکانت اصلی در ادمین:** capture هدرهای `anthropic-ratelimit-*` از پاسخ آپ‌استریم در مسیر passthrough (خام + parseشده) → side-channel `/internal/upstream-limits` → state store؛ داشبورد ادمین «مصرف/باقی‌مانده/reset» هر پنجرهٔ اکانت را نشان می‌دهد. مسیر CLI هدر نمی‌دهد → طراحی صادقانه: state از ترافیک passthrough (+ probe اختیاری) تازه می‌شود، `last_updated` نمایش داده می‌شود، عدد جعلی ساخته نمی‌شود؛ در نبود هدر → فقط `rateLimitTier/subscriptionType` از credentials.
> ۳) **Issue G — گزارش مصرف per-user در ادمین:** endpoint جدید `GET /api/admin/users/{id}/usage` (روند روزانه + by_model + by_key + ۵ساعته و هفتگی جاری) + CSV تک‌کاربر (nice)، و صفحهٔ drill-down ادمین (همان «مصرف من» کاربر، فقط متادیتا).
> ۴) تقسیم کار اصلاحیهٔ ۳ در انتهای §۱۰ (اجرا پس از integration اصلاحیهٔ ۲).

> **اصلاحیهٔ ۲ (2026-08-22، دو مسئلهٔ production):**
> ۱) **Issue A — بقای نوبت چت مستقل از مرورگر (§۵.۱، §۵.۳، §۸، §۹، §۳):** اجرای CLI دیگر به درخواست SSE کوپل نیست. `POST messages` نوبت را می‌پذیرد (**202**) و یک task پس‌زمینهٔ asyncio آن را تا انتها اجرا و **همیشه** persist می‌کند؛ استریم همیشه از endpoint جدید `GET /api/conversations/{id}/stream` مصرف می‌شود که رویدادهای بافرشدهٔ نوبتِ در جریان را **از ابتدا replay** و سپس live دنبال می‌کند (ring buffer در حافظه + registry تک‌پروسه‌ای؛ بدون redis/celery). ردیف پیام دستیار از ابتدا با `status='streaming'` ساخته می‌شود (`complete`/`failed` در پایان)؛ در استارتاپ backend ردیف‌های `streaming` مانده → `failed` (هشدار restart). لیست گفتگوها فلگ `generating` می‌دهد (اسپینر سایدبار).
> ۲) **Issue B — مالکیت چرخهٔ عمر توکن آپ‌استریم (§۴.۱):** پس از seed اولیه از فایل هاست، **backend خودش refresh می‌کند** (`POST $UPSTREAM_OAUTH_TOKEN_URL` با `grant_type=refresh_token` و `client_id` همان Claude Code؛ env جدید). توکن‌های چرخیده هم در volume `claude_state` (برای CLI) و هم رمزشده در `settings` (بقا بعد از از‌دست‌رفتن volume) ذخیره می‌شوند. sync هاست فقط وقتی import می‌کند که فایل هاست از آخرین seed **تغییر کرده** باشد (hash) — یعنی `claude login` دستی دوباره seed می‌کند ولی هرگز توکن‌های backend-managed را clobber نمی‌کند. اگر endpoint رفرش سرویس ثالث متفاوت بود → degrade شفاف به دستور «claude login روی سرور». وضعیت کامل در پنل ادمین.
> ۳) **Issue C — تلاش مجدد نوبت شکست‌خورده (§۳، §۵.۱، §۸، §۹):** پیام دستیار شکست‌خورده با `status='failed'` + `error_code`/`error_reason` (دلیل کوتاه فارسی) persist می‌شود — شامل حالت `aborted_restart` استارتاپ. endpoint جدید `POST .../messages/{message_id}/retry` همان پیام کاربر قبلی را به‌صورت یک نوبت تازه دوباره اجرا می‌کند با **بازمصرف همان ردیف شکست‌خورده** (reset به `streaming`؛ نه حذف/ساخت مجدد)؛ فقط روی آخرین نوبت و فقط وقتی `failed`؛ از همان قفل busy و مسیر پس‌زمینه/reattach مسئلهٔ A عبور می‌کند؛ شارژ فقط به‌اندازهٔ اجرای واقعیِ retry. UI: دکمهٔ «تلاش مجدد» روی حباب خطا.
> ۴) **مستندسازی موارد از قبل پیاده‌شده:** volume `claude_state` برای پایداری سشن‌های CLI + fallback خاموشِ resume در runner (§۵.۴)؛ `model_map` در `/internal/upstream-config` که handler قبل از relay اعمال می‌کند (§۶.۱)؛ نگاشت خطاهای 4xx/429/529 آپ‌استریم به کد/پیام فارسی در passthrough + side-channel گزارش usage واقعی (§۵.۲، §۶.۱).
> ۵) **Issue D — کنترل و نمایش «سطح تفکر» (§۳، §۵.۱، §۵.۲، §۸، §۹):** picker سه‌سطحی سطح تفکر (خاموش/متوسط/عمیق) در چت وب؛ default به ازای گفتگو، override به ازای پیام. مکانیزم چت وب = env `MAX_THINKING_TOKENS` per-turn در subprocess CLI (نه تزریق keyword در متن). مسیر passthrough نامتقارن: فیلد `thinking` خود client دست‌نخورده رد می‌شود (ما تزریق نمی‌کنیم، strip هم نمی‌کنیم). توکن‌های تفکر در `usage.output_tokens` می‌آیند پس ledger وزن‌دار خودکار آن‌ها را با وزن output می‌شمارد (بدون multiplier جدا). رویداد `done` سطح واقعی‌استفاده‌شده را گزارش می‌دهد (badge روی پاسخ). cap سراسری با env؛ cap per-policy nice-to-have.
> ۶) تقسیم کار این اصلاحیه (A+B+C+D) در انتهای §۱۰.

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

**ماژول ایزولهٔ آپ‌استریم** دو نقطهٔ تماس دارد: (الف) `backend/app/upstream/credentials.py` — مالک کامل چرخهٔ عمر اعتبارنامه (seed از هاست، refresh خودکار، persist سه‌جایه — §۴.۱)، (ب) `litellm/ecocode_upstream_handler.py` — custom handler داخل کانتینر litellm که عمداً یک **relay گنگ** است: نه DB دارد، نه crypto، نه دسترسی به فایل اعتبارنامه؛ پیکربندی مؤثر (mode، base_url، توکن plaintext، `model_map`) را از endpoint داخلی backend یعنی `GET /internal/upstream-config` می‌گیرد (bearer = `LITELLM_MASTER_KEY`، فقط شبکهٔ داخلی، cache ۱۵ثانیه‌ای) و usage واقعی را به `POST /internal/usage-report` برمی‌گرداند (§۶.۱). تغییر مکانیزم سرویس آپ‌استریم فقط این دو فایل را لمس می‌کند.

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
    - teams_data:/data/teams                          # اصلاحیهٔ ۴: حافظهٔ مشترک تیم‌ها
    - commands_data:/data/commands                    # اصلاحیهٔ ۵: دستورهای slash سازمانی (admin-global)
    - attachments_data:/data/attachments
    - claude_state:/home/app/.claude                  # state سشن‌های CLI + اعتبارنامهٔ backend-managed
    - ${CLAUDE_CREDS_DIR:-./data/claude-creds}:/host_claude:ro  # اعتبارنامهٔ Claude Code هاست (seed، فقط‌خواندنی)
```
**volume `claude_state` (پیاده‌شده):** دایرکتوری `~/.claude` کانتینر را ماندگار می‌کند؛ دو کارکرد: (۱) state سشن‌های Claude Code (تا `--resume` بعد از recreate کانتینر کار کند — fallback نرم در §۵.۴)، (۲) فایل اعتبارنامهٔ backend-managed (§۴.۱).
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
# --- OAuth refresh (Issue B، §4.1) ---
UPSTREAM_OAUTH_TOKEN_URL=             # خالی → پیش‌فرض: ${UPSTREAM_BASE_URL}/v1/oauth/token
UPSTREAM_OAUTH_CLIENT_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e   # client_id خود Claude Code (پیش‌فرض)

# --- CLI Runner ---
CLAUDE_CREDS_DIR=/home/amin/.claude   # مسیر اعتبارنامهٔ Claude Code روی هاست (mount :ro)
CLI_MAX_CONCURRENCY=4                 # سقف پروسه‌های هم‌زمان CLI (کل سیستم)
CLI_TIMEOUT_SECONDS=300               # حداکثر عمر یک اجرای CLI به ازای هر پیام
MOCK_CLI=0                            # 1 → runner به‌جای claude، /app/bin/mock-claude را اجرا می‌کند
THINKING_MAX_LEVEL=deep               # سقف سراسری سطح تفکر (Issue D): off | standard | deep
# --- اصلاحیهٔ ۳ ---
ROLLING_WINDOW_HOURS=5                 # طول پنجرهٔ غلتان سقف ۵ساعته (Issue E)
UPSTREAM_LIMIT_PROBE_ENABLED=false    # probe دوره‌ای سبک برای تازه‌کردن لیمیت اکانت (Issue F)
UPSTREAM_LIMIT_PROBE_INTERVAL=900     # ثانیه؛ فقط اگر probe فعال باشد

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
CREATE TYPE thinking_level AS ENUM ('off', 'standard', 'deep');   -- اصلاحیهٔ ۲ / Issue D

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
--
-- اصلاحیهٔ ۴: چیدمان دیسک تیم‌ها (بدون جدول برای خودِ دایرکتوری):
--   /data/teams/<team_id>/memory/         حافظهٔ مشترک تیم (0770، مالکیت app user)
--   داخل cwd سشن هر عضو، به‌صورت symlink دیده می‌شود: <cwd>/teams/<slug> -> /data/teams/<team_id>/memory
--   منبع حقیقت عضویت = جدول team_members؛ دیسک فقط storage است.

-- ============ teams (اصلاحیهٔ ۴ / Issue H) ============
CREATE TABLE teams (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    slug        VARCHAR(80)  NOT NULL UNIQUE,   -- [a-z0-9-]؛ نام پوشهٔ ./teams/<slug>/ در cwd
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- عضویت چند‌به‌چند. role_in_team فعلاً فقط برای نمایش/توسعهٔ آینده؛ enforcement
-- دسترسی صرفاً بر «عضو بودن» است، نه نقش داخل تیم (ساده و کافی برای فاز فعلی).
CREATE TYPE team_role AS ENUM ('member', 'lead');
CREATE TABLE team_members (
    team_id     BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_in_team team_role NOT NULL DEFAULT 'member',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id)             -- unique (team_id,user_id)
);
CREATE INDEX idx_team_members_user ON team_members(user_id);   -- «تیم‌های کاربر X» (hot path runner)

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
    -- اصلاحیهٔ ۳ / Issue E: سقف پنجرهٔ غلتان ۵ساعته. NULL = نامحدود (بدون enforce).
    -- migration اصلاحیهٔ ۳ این ستون را ADD می‌کند (روی اسکیمای اصلاحیهٔ ۲).
    limit_credits_5h NUMERIC(14,2),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_quota_user UNIQUE (user_id)
);
-- توجه: سقف ۵ساعته «پنجرهٔ غلتان» است، نه دوره‌ای — period_start/bonus بی‌ربط‌اند؛
-- مصرف لحظه‌ای = SUM(usage_ledger.credits) روی [now - ROLLING_WINDOW_HOURS, now] (Issue E، §۵.۱).

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
    -- Issue D: سطح تفکر پیش‌فرض این گفتگو؛ هر پیام می‌تواند override کند.
    thinking_level  thinking_level NOT NULL DEFAULT 'standard',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ                         -- soft delete
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC) WHERE deleted_at IS NULL;

-- ============ messages ============
CREATE TYPE message_status AS ENUM ('complete', 'streaming', 'failed');   -- اصلاحیهٔ ۲

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,               -- 'user' | 'assistant'
    content         TEXT NOT NULL DEFAULT '',           -- متن (markdown)؛ برای ردیف streaming تا پایان خالی
    -- رویدادهای ساختاری سشن CLI (tool_use ها، فایل‌های ساخته‌شده و…) به‌صورت JSONB:
    content_blocks  JSONB,
    -- Issue A: ردیف دستیار از لحظهٔ پذیرش نوبت با status='streaming' ساخته می‌شود؛
    -- پایان موفق → 'complete'، خطا/timeout/از‌دست‌رفتن در restart → 'failed'.
    status          message_status NOT NULL DEFAULT 'complete',
    -- Issue C: فقط برای status='failed' پر می‌شوند؛ در retry پاک می‌شوند.
    error_code      VARCHAR(40),   -- 'quota_exceeded' | 'upstream_rate_limited' | 'cli_error'
                                   -- | 'timeout' | 'aborted_restart'
    error_reason    TEXT,          -- دلیل کوتاه فارسی قابل‌نمایش در حباب خطا
    -- Issue D: سطح تفکرِ عملاً‌استفاده‌شده برای این نوبت (روی ردیف assistant پر می‌شود؛
    -- منبع badge در UI). پس از cap سراسری/policy محاسبه می‌شود، نه صرفاً درخواست کاربر.
    thinking_level  thinking_level,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_msg_conv      ON messages(conversation_id, created_at);
CREATE INDEX idx_msg_streaming ON messages(status) WHERE status = 'streaming';
-- استارتاپ backend (بازیابی از crash/restart):
--   UPDATE messages SET status='failed', error_code='aborted_restart',
--          error_reason='سرویس هنگام تولید پاسخ راه‌اندازی مجدد شد.' WHERE status='streaming';
-- تا UI هرگز روی نوبتِ گم‌شده برای همیشه منتظر نماند (کاوئت restart در §۵.۱) و retry ممکن باشد.

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
--   upstream.mode                    = 'cli_creds'|'apikey'|'mock'  (override runtime؛ env اولویت دارد)
--   upstream.apikey            (enc) = توکن دستی سرویس آپ‌استریم (mode apikey)
--   -- Issue B: نسخهٔ پشتیبان رمزشدهٔ اعتبارنامهٔ backend-managed (بقا بعد از از‌دست‌رفتن volume):
--   upstream.cli.access_token  (enc)
--   upstream.cli.refresh_token (enc)
--   upstream.cli.expires_at          = ISO timestamp
--   upstream.cli.host_seed_hash      = sha256 آخرین فایل هاستِ importشده (سیاست seed در §۴.۱)
--   upstream.cli.last_refresh        = JSON: {at, ok, error?}
--   quota.warn_threshold             = '0.8'  (هشدار ۸۰٪)

-- ============ upstream_account_limits (اصلاحیهٔ ۳ / Issue F) ============
-- state لیمیتِ خودِ اکانت آپ‌استریم، استخراج‌شده از هدرهای پاسخ آپ‌استریم.
-- یک ردیف به ازای هر «پنجره‌ای» که آپ‌استریم افشا می‌کند (مثلا '5h', 'weekly',
-- 'unified'). فقط state است (نه سری‌زمانی)؛ upsert روی window_key.
CREATE TABLE upstream_account_limits (
    window_key      VARCHAR(40) PRIMARY KEY,  -- '5h' | 'weekly' | 'unified' | 'tier' ...
    limit_value     NUMERIC(18,2),            -- سقف (اگر افشا شود؛ واحد = واحد آپ‌استریم)
    remaining_value NUMERIC(18,2),            -- باقی‌مانده
    reset_at        TIMESTAMPTZ,              -- زمان reset پنجره (از هدر reset)
    unit            VARCHAR(30),              -- 'tokens' | 'requests' | 'credits' ... اگر معلوم
    raw_headers     JSONB,                    -- همهٔ هدرهای anthropic-ratelimit-* خام (دفاعی)
    source          VARCHAR(20) NOT NULL,     -- 'passthrough' | 'probe'
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    upstream_request_id VARCHAR(100)          -- برای trace
);
-- اگر آپ‌استریم هیچ هدری ندهد، این جدول خالی می‌ماند و ادمین فقط
-- rateLimitTier/subscriptionType از credentials را می‌بیند (طراحی صادقانهٔ §۴.۵).
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

### ۴.۱ mode `cli_creds` — seed از هاست، مالکیت چرخهٔ عمر با backend (بازطراحی اصلاحیهٔ ۲)

**درس production:** طراحی v1.1 (sync یک‌طرفهٔ ۶۰ثانیه‌ای، هاست منبع حقیقت) دو بار سرویس را زمین زد: access token ~۸ساعته منقضی می‌شود و refresh token فایل هاست توسط بازیگرهای دیگر rotate/باطل می‌شود؛ گیت‌وی می‌مُرد تا یک انسان `claude login` بزند. از این نسخه **پس از seed اولیه، backend خودش مالک توکن است**.

**پیش‌فرض:** ادمین یک‌بار روی همین سرور `claude login` را علیه سرویس Claude-سازگار انجام داده (`~/.claude/.credentials.json`، قابل تنظیم با `CLAUDE_CREDS_DIR`).

```
                       ┌───── seed (فقط وقتی فایل هاست «تغییر کرده») ─────┐
هاست: ~/.claude/.credentials.json ──(mount :ro /host_claude)──▶ TokenManager (backend)
                                                                    │  مالک چرخهٔ عمر:
        ┌───────────────────────────────────────────────────────────┤  refresh خودکار
        ▼ persist                          ▼ persist                │  قبل از انقضا
 claude_state volume                 settings (enc)                 │
 /home/app/.claude/.credentials.json  upstream.cli.*                │
   └──▶ Claude Code CLI خودش می‌خواند   └──▶ بازسازی فایل بعد از     │
        (چت وب)                             از‌دست‌رفتن volume        │
                                                                    ▼ serve
                                              /internal/upstream-config → litellm handler (passthrough)
```

**اجزای TokenManager (همه داخل ماژول ایزولهٔ `app/upstream/credentials.py`):**

1. **Seed از هاست — فقط بر تغییر:** hash محتوای `/host_claude/.credentials.json` با `settings.upstream.cli.host_seed_hash` مقایسه می‌شود (چک در استارتاپ + هر ۶۰ ثانیه). **فقط اگر متفاوت بود** import می‌شود (access+refresh+expiresAt) و hash جدید ثبت می‌گردد. یعنی: `claude login` دستی روی هاست = re-seed فوری گیت‌وی؛ ولی فایل هاستِ کهنه **هرگز** توکن‌های backend-managed را clobber نمی‌کند.
2. **Refresh خودکار:** task دوره‌ای (هر ۶۰ ثانیه چکِ) `expires_at`؛ وقتی `< now + 10min` → با قفل single-flight:
   - ابتدا فایل volume دوباره خوانده می‌شود (خود CLI ممکن است حین اجرا refresh کرده باشد — اگر تازه‌تر بود، همان adopt و persist می‌شود و تمام).
   - وگرنه: `POST $UPSTREAM_OAUTH_TOKEN_URL` (پیش‌فرض `${UPSTREAM_BASE_URL}/v1/oauth/token`) با body:
     ```json
     { "grant_type": "refresh_token", "refresh_token": "<current>",
       "client_id": "$UPSTREAM_OAUTH_CLIENT_ID" }
     ```
     (`client_id` پیش‌فرض = همانی که Claude Code استفاده می‌کند؛ سرویس Claude-سازگار همین flow را برای توکن‌های Claude Code پیاده کرده است.)
   - پاسخ (`access_token`, `refresh_token` چرخیده, `expires_in`) **در هر دو جا** persist می‌شود: فایل `claude_state` (همان شکل on-disk خود Claude Code — `claudeAiOauth.accessToken/refreshToken/expiresAt` — تا CLI بی‌تغییر بخواند) + رمزشده در `settings.upstream.cli.*` (بقا بعد از از‌دست‌رفتن volume). نتیجهٔ هر refresh در `upstream.cli.last_refresh` ثبت می‌شود.
3. **بازیابی در استارتاپ:** اگر فایل volume نبود ولی `settings.upstream.cli.*` بود → فایل از settings بازسازی می‌شود (و بالعکس، تازه‌ترین برنده است بر اساس `expires_at`).
4. **Serve:** توکن معتبر لحظه‌ای به CLI runner (از طریق همان فایل HOME) و به litellm handler (از طریق `/internal/upstream-config`) داده می‌شود.
5. **صداقت در شکست (graceful degradation):** اگر endpoint رفرشِ این سرویس ثالث فرق داشت (404/شکل ناشناخته) → auto-refresh غیرفعال، یک بار log، و رفتار به سیاست قبلی برمی‌گردد: sync هاست + دستور فارسی «روی سرور `claude login` را اجرا کنید». اگر refresh با `invalid_grant`/401 رد شد (refresh token باطل/منقضی) → وضعیت «قطع» + همان CTA. همه‌چیز داخل ماژول credentials می‌ماند؛ هیچ لایهٔ دیگری تغییر نمی‌کند.

**نمایش وضعیت (F1.2):** `GET /api/admin/upstream/status` (فیلدهای جدید):
```json
{ "mode": "cli_creds", "connected": true,
  "expires_at": "2026-08-22T18:00:00Z",            
  "refresh_token_valid_until": null,                 
  "expiring_soon": false,
  "last_refresh": { "at": "2026-08-22T09:40:00Z", "ok": true, "error": null },
  "auto_refresh": "active",                          
  "creds_source": "backend-managed (seeded from /host_claude)",
  "base_url": "https://claude-compat.example.com" }
```
- `refresh_token_valid_until`: اکثر سرویس‌ها انقضای refresh token را گزارش نمی‌کنند → `null` و در UI «نامشخص». اگر گزارش شد، نمایش داده می‌شود.
- `auto_refresh`: `active` | `degraded` (endpoint ناسازگار) | `failed` (refresh token باطل).
- **CTA فارسی فقط وقتی refresh واقعاً ناممکن است** (`degraded` منقضی‌شده یا `failed`): «توکن قابل تمدید خودکار نیست؛ روی سرور دستور `claude login` را اجرا کنید.» در حالت عادی هیچ اقدامی از ادمین خواسته نمی‌شود.

**اتصال مجدد (F1.3):** پس از `claude login` مجدد روی هاست، سیاست seed-بر-تغییر ظرف ≤۶۰ ثانیه گیت‌وی را سبز می‌کند — بدون restart و بدون از‌دست‌رفتن داده. **هیچ credential به مرورگر نمی‌رود؛ در DB فقط رمزشده.**

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

### ۴.۵ capture لیمیت خودِ اکانت آپ‌استریم (اصلاحیهٔ ۳ / Issue F — طراحی)

هدف کاربر: «لیمیت خود اکانت اصلی رو ببینم چقدر مصرف شده و چقدر مونده». اکانت Max آپ‌استریم پنجره‌های نرخ خودش (۵ساعته/هفتگی) را دارد؛ ما فقط چیزی را نشان می‌دهیم که آپ‌استریم **واقعاً افشا** می‌کند — هیچ عددی ساخته نمی‌شود.

**منبع داده — هدرهای پاسخ (مسیر passthrough):** litellm handler به هر پاسخ آپ‌استریم دسترسی به response headers دارد. خانوادهٔ مورد انتظار `anthropic-ratelimit-*` (دفاعی نسبت به نام دقیق — سرویس ثالث ممکن است متفاوت باشد):
- `anthropic-ratelimit-unified-*` / `anthropic-ratelimit-*-limit` / `-remaining` / `-reset` و هر واریانت `-5h-` / `-weekly-`.
- **راهبرد capture:** handler **همهٔ** هدرهایی که با `anthropic-ratelimit` شروع می‌شوند را خام برمی‌دارد (بدون فرض نام) و به side-channel می‌فرستد؛ parse به window/limit/remaining/reset در backend انجام می‌شود تا منطق در یک جا (نه در relay گنگ) بماند.

**side-channel (توسعهٔ `/internal`):** endpoint داخلی جدید `POST /internal/upstream-limits` (bearer = master key، فقط شبکهٔ داخلی):
```json
{ "raw_headers": { "anthropic-ratelimit-unified-limit": "...", ... },
  "upstream_request_id": "msg_...", "source": "passthrough" }
```
backend parse می‌کند و در `upstream_account_limits` (به ازای هر window_key) **upsert** می‌کند + `last_updated=now`. handler این را در همان مسیر گزارش usage (بعد از خواندن پاسخ) صدا می‌زند؛ شکست آن هرگز درخواست کاربر را نمی‌شکند (fire-and-forget).

**مسیر CLI (چت وب) — طراحی صادقانه:** رویداد `result` خروجی stream-json و سایر خروجی‌های `claude -p` لیمیت سطح‌اکانت را **نمی‌دهند** (فقط usageِ همان نوبت). بنابراین:
- state لیمیت اکانت **فقط از ترافیک passthrough** تازه می‌شود (و در صورت `UPSTREAM_LIMIT_PROBE_ENABLED=true`، از یک probe سبک دوره‌ای: یک درخواست کوچک `max_tokens=1` به `/v1/messages` صرفاً برای خواندن هدرها — با هزینهٔ توکن ناچیز که در ledger «اکانت» ثبت نمی‌شود چون کاربر نیست؛ پیش‌فرض خاموش).
- اگر مدتی هیچ ترافیک passthrough نبوده، ارقام کهنه‌اند → UI حتماً `last_updated` را نشان می‌دهد و اگر از آستانه‌ای (مثلاً > ۱۵ دقیقه) گذشت، برچسب «ممکن است به‌روز نباشد».
- **degrade کامل:** اگر سرویس ثالث اصلاً چنین هدری ندهد، `upstream_account_limits` خالی می‌ماند؛ ادمین فقط `rateLimitTier`/`subscriptionType` استخراج‌شده از فایل credentials را می‌بیند و پیام صریح «سرویس بالادستی جزئیات مصرف اکانت را ارائه نمی‌دهد».

**نمایش:** `GET /api/admin/upstream/account-limits` (§۸) خروجی می‌دهد: لیست پنجره‌ها `[{window, limit, remaining, reset_at, unit, last_updated, stale}]` + `tier`/`subscription` (اگر معلوم) + `available: bool`.

---

## ۵. جریان درخواست هر دو سطح (auth · ACL · quota · ثبت مصرف · streaming)

**تصمیم قطعی مسیرها:** چت وب **همیشه** از CLI runner می‌گذرد (مسیر «چت سادهٔ» HTTP مستقیم نداریم). دلیل: یک مسیر واحد یعنی یک پروتکل رندر، یک منطق usage، و قابلیت agentic/فایل همیشه در دسترس (F4.6)؛ دو مسیر یعنی دو باگ‌سطح. سطح کلید API (Cline/OpenAI-سازگار) **همیشه** HTTP مستقیم از طریق LiteLLM است — ابزارها خودشان agentic هستند و فقط completion می‌خواهند.

هر دو سطح از یک **pipeline مشترک** auth/ACL/quota/ledger در backend عبور می‌کنند.

### ۵.۱ سطح (الف) — چت وب از طریق CLI Runner (بازطراحی اصلاحیهٔ ۲: نوبتِ جدا از مرورگر)

**اصل:** از لحظه‌ای که POST پذیرفته شد، نوبت **مستقل از client** تا انتها اجرا و persist می‌شود. قطع/تعویض تب هیچ اثری روی اجرا ندارد؛ client هر لحظه می‌تواند دوباره وصل شود و استریم را **از ابتدای نوبت** ببیند.

```
Browser ──(session cookie)──▶ POST /api/conversations/{id}/messages   {content}
   ▼ backend (همه پیش از پذیرش، سنکرون)
 [۱ AUTH]   session cookie → user. نامعتبر/غیرفعال → 401.
 [۲ BUSY]   نوبت فعال برای همین گفتگو در registry؟ → 409 chat_busy.
 [۳ ACL ]   مدل گفتگو در model_policies[user]؟ نه → 403 «مدل مجاز نیست».
 [۴ QUOTA pre-check]  دو سقف، هر دو enforce (اصلاحیهٔ ۳ / Issue E):
            (الف) هفتگی: used_period >= budget → 429 quota_exceeded + audit request.denied_quota.
            (ب) غلتان ۵ساعته: اگر limit_credits_5h ست است و
                used_5h = SUM(credits over [now-Wh, now]) >= limit_credits_5h
                → 429 quota_exceeded_5h + audit request.denied_quota_5h.
            هر کدام زودتر پر شد همان رد می‌شود (کد و پیام مجزا — §۵.۸).
 [۵ ذخیرهٔ ردیف‌ها]  message(role=user, status=complete) +
            message(role=assistant, content='', status='streaming')   ← ردیف از ابتدا
 [۶ SPAWN]  asyncio.create_task(run_turn) + ثبت در TurnRegistry (در حافظه):
            registry[conversation_id] = TurnState{ assistant_message_id,
                                                   events: ring buffer, cond, done }
   ◀── پاسخ فوری: 202 {assistant_message_id, generating: true}

── task پس‌زمینه (بدون هیچ وابستگی به اتصال client) ──
 [۷ RUN CLI]  spawn پروسهٔ Claude Code headless (مشخصات ۵.۴):
            claude -p "<متن>" --output-format stream-json --verbose
                   --model <upstream_model> [--resume <cli_session_id>]
            env شامل MAX_THINKING_TOKENS بر اساس سطح تفکر مؤثر (Issue D، §۵.۷).
            cwd = workspace کاربر (ساخت 0700 در اولین بار؛ attachmentها قبلاً کپی شده‌اند).
            (اصلاحیهٔ ۴) پیش از spawn، symlinkهای تیم عضو در <cwd>/teams/<slug> هم‌گام می‌شوند (§۵.۴).
 [۸ BUFFER] هر رویداد ترجمه‌شده (نگاشت ۵.۳) به ring buffer نوبت append و
            cond.notify_all() → همهٔ streamهای متصل، live دنبال می‌کنند.
 [۹ FINALIZE] رویداد result → usage → credits → INSERT usage_ledger
            (surface='web_chat', request_id=cli_session_id).
            UPDATE ردیف assistant: content=متن نهایی، content_blocks، status='complete'،
            thinking_level=<سطح مؤثر> (خطا/timeout → status='failed' + error_code/error_reason فارسی + رویداد error در buffer).
            conversations.cli_session_id (بار اول) + updated_at.
            registry حذف پس از terminal event (buffer تا بسته‌شدن آخرین مشترک زنده می‌ماند).

── مصرف استریم (attach/reattach، هر تعداد بار) ──
Browser ──▶ GET /api/conversations/{id}/stream        (SSE)
            نوبت فعال هست → replay کل buffer از رویداد ۰، سپس follow زنده تا terminal.
            نوبت فعال نیست → یک رویداد `idle` و بستن (client از GET conversation
            پیام‌های نهایی را دارد).
```

**انتخاب مکانیزم reattach (قطعی): ring buffer در حافظه، نه persist تدریجی.** توجیه: (الف) backend تک‌پروسه است (uvicorn یک worker) پس registry در حافظه کافی و «boring» است — بدون redis/celery؛ (ب) persist تدریجی هر delta یعنی write amplification روی Postgres به ازای هر توکن، بی‌فایده چون تنها مصرف‌کنندهٔ رویدادهای میانی همین replay است؛ (ج) تضمین ماندگاری فقط برای نوبت تمام‌شده لازم است (متن نهایی + usage) که در FINALIZE اتمیک انجام می‌شود. سقف buffer: ۴۰۹۶ رویداد / ~۴MB به ازای نوبت (بیش از آن: deltaهای قدیمی متن‌شان merge می‌شود تا replay همچنان کامل بماند).

**کاوئت restart (پذیرفته‌شده):** اگر backend وسط نوبت restart شود، task و buffer از بین می‌روند. در استارتاپ همهٔ ردیف‌های `streaming` → `failed` با `error_code='aborted_restart'` (شکل کامل در §۳) → UI به‌جای انتظار ابدی، حباب خطا با دکمهٔ «تلاش مجدد» (Issue C) نشان می‌دهد. (مصرفی ثبت نمی‌شود چون رویداد result نیامده.)

**فلگ `generating`:** در `GET /api/conversations` و `GET /api/conversations/{id}` به ازای هر گفتگو: `generating = (id in TurnRegistry)`. سایدبار اسپینر نشان می‌دهد؛ ورود به گفتگوی در حال تولید → اتصال خودکار به `/stream`.

**تلاش مجدد نوبت شکست‌خورده (Issue C):** `POST /api/conversations/{id}/messages/{message_id}/retry` —

- **گاردها (سنکرون، پیش از پذیرش):** پیام باید (الف) متعلق به همین گفتگو و همین کاربر، (ب) `role='assistant'`، (ج) `status='failed'`، (د) **آخرین پیام گفتگو** باشد (نوبت‌های قدیمی‌تر retry ندارند — 409 `not_retryable`)؛ (ه) گفتگو busy نباشد (409 `chat_busy`)؛ سپس همان pre-checkهای POST عادی (ACL مدل، quota → 403/429).
- **معناشناسی (قطعی): بازمصرف همان ردیف، نه حذف/ساخت مجدد.** ردیف شکست‌خورده reset می‌شود: `status='streaming'`, `content=''`, `content_blocks=NULL`, `error_code=NULL`, `error_reason=NULL` — و نوبت تازه‌ای با **متن همان پیام user ماقبلش** از همان مسیر پس‌زمینهٔ Issue A (registry، buffer، `GET /stream`) اجرا می‌شود. پاسخ: **202** `{assistant_message_id: <همان id>, generating:true}`. توجیه انتخاب supersede-in-place: id پیام برای client پایدار می‌ماند (همان حبابی که خطا نشان می‌داد به حالت استریم برمی‌گردد)، ترتیب/شمارهٔ پیام‌ها دست نمی‌خورد و ردیف orphan تولید نمی‌شود؛ نگه‌داشتن تاریخچهٔ شکست‌ها ارزش محصولی ندارد (در audit_log نیست و لازم نیست باشد).
- **resume:** مثل هر نوبت، از `conversations.cli_session_id` موجود استفاده می‌شود (+ fallback خاموش §۵.۴). در شکستِ نوع timeout ممکن است نوبت قبلی اثر جزئی روی workspace گذاشته باشد؛ retry همان prompt را در نوبت جدید می‌فرستد — پذیرفته و مستند.
- **بدون شارژ مضاعف:** credit فقط از رویداد `result` موفق ثبت می‌شود؛ نوبت شکست‌خورده چیزی در ledger ننوشته (رویداد result نداشته یا `is_error` بوده)، پس retry فقط مصرف واقعی اجرای خودش را می‌نویسد.
- **idempotency:** چون retry اولین کارش reset ردیف به `streaming` و ثبت در registry است، retry دوم هم‌زمان به گارد (ج)/(ه) می‌خورد (409).

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
 [۳ QUOTA pre-check]  همان منطق ۵.۱[۴] — **هر دو سقف** هفتگی و ۵ساعته (اصلاحیهٔ ۳ / Issue E)؛
            رد → 429 quota_exceeded یا quota_exceeded_5h.
 [۴ CALL] backend ──▶ litellm ──▶ custom upstream handler ──▶ POST $UPSTREAM_BASE_URL/v1/messages.
            اگر endpoint = /v1/chat/completions، LiteLLM خودش شکل OpenAI را ترجمه می‌کند.
            metadata: {user_id, api_key_id, model_key, surface:api}.
 [۵ STREAM] SSE از آپ‌استریم تا Cline پیوسته proxy می‌شود (هر دو فرمت stream پشتیبانی می‌شوند).
 [۶ ثبت مصرف]  usage واقعی از side-channel داخلی (§۶.۱) با کلید x-ecocode-request-id؛
            fallback: بلوک usage خود litellm. همان فرمول؛ api_key_id پر.
            (چت وب و API از یک سهمیهٔ کاربر کم می‌شوند — F5.3.)
 [۷ لیمیت اکانت]  (اصلاحیهٔ ۳ / Issue F) handler هدرهای anthropic-ratelimit-* پاسخ آپ‌استریم را
            به /internal/upstream-limits می‌فرستد → upsert در upstream_account_limits (§۴.۵).
```

**نگاشت خطای آپ‌استریم (پیاده‌شده — `routers/passthrough.py` + handler):** handler هر پاسخ non-2xx آپ‌استریم را به exception تایپ‌دار litellm با **همان status واقعی** تبدیل می‌کند (وگرنه litellm همه را 500 می‌کرد)؛ backend به client برمی‌گرداند:

| status آپ‌استریم | code | پیام فارسی |
|---|---|---|
| 401 | `upstream_auth_error` | احراز هویت نزد سرویس بالادستی ناموفق بود؛ تنظیمات اعتبارنامه را بررسی کنید. |
| 403 | `upstream_forbidden` | سرویس بالادستی این درخواست را مجاز نمی‌داند. |
| 404 | `upstream_not_found` | مدل یا مسیر درخواستی در سرویس بالادستی یافت نشد. |
| 429 | `upstream_rate_limited` | سرویس بالادستی فعلاً شلوغ است؛ کمی بعد دوباره تلاش کنید. |
| 529 | `upstream_overloaded` | سرویس بالادستی زیر بار سنگین است؛ کمی بعد دوباره تلاش کنید. |
| سایر | 502 `upstream_error` | خطا در ارتباط با سرویس بالادستی رخ داد. |

نکتهٔ streaming: litellm خطای بعد از شروعِ استریم را به‌صورت HTTP 200 + یک رویداد `data:{"error":...,"code":"429"}` گزارش می‌کند؛ backend **قبل از تعهد به 200 خودش، اولین رویداد SSE را peek می‌کند** (fail-fast) تا 429/401 واقعی به client برسد نه یک استریم خالی.

**سطح تفکر در passthrough (Issue D — نامتقارن با چت وب):** در این مسیر client صاحب تفکر است. اگر body شامل `thinking: {type:"enabled", budget_tokens:N}` (Anthropic) بود، **دست‌نخورده** رد می‌شود؛ ما نه تزریق می‌کنیم و نه strip. تبدیل `_to_anthropic_body` در handler باید فیلد `thinking` را در صورت وجود منتقل کند (امروز فقط system/messages/max_tokens/temperature را منتقل می‌کند — یک خط پاس‌دادن `thinking` اضافه شود). ابزارهایی مثل Cline خودشان تنظیم می‌کنند. برخلاف چت وب، اینجا `MAX_THINKING_TOKENS` معنا ندارد (پروسهٔ CLI نیست).

**نکتهٔ کلیدی:** auth/ACL/quota/ledger **در backend ما** اتفاق می‌افتد، نه در LiteLLM و نه در CLI. Cline هرگز مستقیم به LiteLLM یا آپ‌استریم نمی‌رسد (PRD بند ۴).

### ۵.۳ نگاشت stream-json → SSE ما (چت وب)

خروجی `--output-format stream-json` خطی-JSON است. backend هر خط را parse و به رویداد SSE سادهٔ خودمان ترجمه می‌کند تا فرانت با یک پروتکل ثابت کار کند:

| رویداد CLI (stream-json) | SSE ما به مرورگر |
|---|---|
| `{"type":"system","subtype":"init","session_id":...}` | `event: start` `{conversation_id}` (+ ذخیرهٔ cli_session_id) |
| `{"type":"assistant","message":{content:[{type:"text",...}]}}` | `event: delta` `{text}` (متن تدریجی) |
| بلوک `tool_use` در پیام assistant (مثلاً Write/Edit) | `event: tool` `{name, summary}` — UI به‌صورت «در حال ساخت فایل …» نشان می‌دهد |
| `{"type":"result","usage":{...},"is_error":false}` | `event: done` `{credits_used, files_changed[], thinking_level}` (Issue D: سطح مؤثر برای badge) |
| `{"type":"result","is_error":true}` یا خطای پروسه | `event: error` `{message فارسی}` |
| — (فقط `GET /stream` وقتی نوبت فعالی نیست) | `event: idle` `{}` و بستن اتصال |

**قرارداد replay (اصلاحیهٔ ۲):** `GET /api/conversations/{id}/stream` اگر نوبت فعال باشد، همهٔ رویدادهای بافرشده را از رویداد صفر (شامل `start`) بازپخش و سپس زنده دنبال می‌کند تا `done`/`error`. client لازم نیست بداند وسط نوبت وصل شده — رندر replay و live یکسان است. `POST messages` دیگر SSE برنمی‌گرداند (202 JSON — §۵.۱).

مسیر passthrough (۵.۲) دست‌نخورده SSE خام آپ‌استریم را forward می‌کند (سازگاری ابزارها)؛ این نگاشت فقط مال چت وب است.

### ۵.۴ مشخصات CLI Runner (قطعی)

| مورد | تصمیم |
|---|---|
| **مدل اجرا** | یک subprocess به ازای هر پیام کاربر (`asyncio.create_subprocess_exec`). بدون پروسهٔ مقیم. |
| **فرمان** | `claude -p <prompt> --output-format stream-json --verbose --model <upstream_model> [--resume <sid>]` |
| **cwd** | `/data/users/<user_id>/workspace` — قبل از spawn ساخته/بررسی می‌شود؛ realpath باید زیر `/data/users/<user_id>/` باشد. |
| **دایرکتوری تیم‌ها** (اصلاحیهٔ ۴) | پیش از spawn، `sync_team_links(user_id)`: زیرپوشهٔ `<cwd>/teams/` ساخته می‌شود و به ازای **هر تیم عضو**، symlink `<cwd>/teams/<slug> -> /data/teams/<team_id>/memory`؛ symlinkهای تیم‌هایی که کاربر دیگر عضوشان نیست حذف می‌شوند (عضویت که تغییر کند، دسترسی نوبتِ بعد اصلاح می‌شود). دایرکتوری تیم با 0770 در اولین نیاز ساخته می‌شود. اگر کاربر عضو هیچ تیمی نبود، `teams/` خالی/غایب است. |
| **هم‌زمانی** | semaphore سراسری = `CLI_MAX_CONCURRENCY` (پیش‌فرض ۴) + قفل به ازای هر گفتگو = ۱ (پیام دوم در همان گفتگو تا پایان قبلی 409 «پاسخ قبلی در جریان است»). |
| **timeout** | `CLI_TIMEOUT_SECONDS` (پیش‌فرض ۳۰۰s): ابتدا SIGTERM، بعد از ۱۰s SIGKILL؛ SSE با `event: error` بسته می‌شود؛ اگر تا آن لحظه رویداد usage نیامده، مصرفی ثبت نمی‌شود. |
| **env پاس‌شده** | فقط لیست سفید: `HOME=/home/app` (که `.claude/.credentials.json` sync‌شده آنجاست)، `ANTHROPIC_BASE_URL=$UPSTREAM_BASE_URL`، در mode apikey: `ANTHROPIC_AUTH_TOKEN=<توکن>`، `HTTP(S)_PROXY/NO_PROXY`، `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. هیچ env دیگر backend (secrets, DB URL) به CLI نمی‌رسد. |
| **انتخاب مدل** | `models.upstream_model` گفتگو → `--model`. ACL قبل از spawn چک شده. |
| **پرمیشن ابزارها** | **بدون `--dangerously-skip-permissions`.** به‌جای آن allowlist صریح: `--allowedTools "Read(./**),Write(./**),Edit(./**),Glob,Grep"` و `--disallowedTools "Bash,WebFetch,WebSearch"`. **توجیه:** (الف) headless هرگز روی prompt پرمیشن بلاک نمی‌شود چون هر چیزِ مجاز auto-approve است و باقی رد می‌شود؛ (ب) `Bash` عملاً فرار از confinement پوشه است (می‌تواند workspace کاربر دیگر را بخواند) پس در فاز ۱ ممنوع؛ (ج) `WebFetch/WebSearch` بسته تا داده از سازمان بیرون نرود و مصرف قابل پیش‌بینی بماند. الگوهای `./**` دسترسی فایل را به cwd محدود می‌کنند — و چون دایرکتوری تیم به‌صورت symlink **زیر** cwd (در `./teams/<slug>/`) قرار دارد، همین الگو خواندن/نوشتن حافظهٔ تیم را طبیعتاً پوشش می‌دهد بدون افزودن مسیر مطلق (اصلاحیهٔ ۴). فاز ۲ در صورت نیازِ سناریوهای کدنویسی، `Bash` را با sandbox سطح‌OS (bubblewrap) اضافه می‌کند — نه زودتر. |
| **مجموعهٔ containment** (اصلاحیهٔ ۴) | مسیرهای مجاز = **اجتماع** `realpath(/data/users/<user_id>/workspace)` ∪ `{ realpath(/data/teams/<tid>/memory) : tid ∈ تیم‌های عضو کاربر }`. هر resolve فایل (workspace و team-memory) با این مجموعه چک می‌شود؛ خارج از آن → رد. عضویت از `team_members` خوانده می‌شود (منبع حقیقت)، نه از وجود symlink روی دیسک. |
| **usage** | از رویداد `result` (فیلد `usage`) → فرمول ضمیمهٔ الف. `total_cost_usd` نادیده گرفته می‌شود (واحد ما credit است). |
| **قطع مرورگر** | هیچ اثری ندارد — نوبت در task پس‌زمینه است (§۵.۱)؛ client با `GET /stream` هر لحظه reattach می‌کند. |
| **پایداری سشن + fallback resume** (پیاده‌شده) | state سشن‌های CLI روی volume `claude_state` ماندگار است. اگر با وجود آن، CLI شناسهٔ ذخیره‌شده را نشناسد (خطای «No conversation found with session ID» — مثلا state پیش از volume-backed شدن گم شده)، runner **یک‌بار** بدون `--resume` دوباره اجرا می‌کند: رویداد `start` تلاش اول بی‌صدا دور ریخته می‌شود، کاربر یک استریم عادی روی سشن تازه می‌بیند (از دست رفتن context پذیرفته و log می‌شود) و session id جدید persist می‌گردد. |

### ۵.۵ reset دوره‌ای و به‌روزرسانی مصرف

- مصرف نمایش‌داده‌شده = query زندهٔ روی `usage_ledger` (نه cache). تأخیر ~۰ (PRD حداکثر ۱ دقیقه می‌خواهد).
- **job سبک** (APScheduler داخل backend، هر ۵ دقیقه): برای هر quota که `now >= period_start + interval`، `period_start` را به مرز دورهٔ بعد ببر و `bonus_credits` را صفر کن.

### ۵.۶ mock کردن مسیر CLI (`MOCK_CLI=1`)

اسکریپت `/app/bin/mock-claude` (پایتونی، داخل image بک‌اند) دقیقاً همان قرارداد را شبیه‌سازی می‌کند:
1. آرگومان‌ها را می‌پذیرد (`-p`, `--output-format stream-json`, `--model`, `--resume`, `--allowedTools`, …).
2. روی stdout به ترتیب emit می‌کند: `system:init` (با session_id ثابتِ برگرفته از `--resume` یا تصادفی) → چند رویداد `assistant` متنی با تأخیر مصنوعی (تست رندر تدریجی) → یک بلوک `tool_use` از نوع Write و **واقعاً یک فایل نمونه در cwd می‌سازد** (تست پنل فایل‌ها) → `result` با usage جعلی معقول (مثلاً in=1200, out=350, cache_read=400).
3. exit code 0.

نتیجه: کل مسیر چت وب + پنل فایل‌ها + ledger بدون هیچ credential واقعی E2E-تست می‌شود. (Issue D: mock-claude مقدار `MAX_THINKING_TOKENS` را از env می‌خواند و در usageِ `result` خود منعکس می‌کند — output_tokens جعلی متناسب با سطح بزرگ‌تر — تا badge و تفاوت credit در تست دیده شود.)

### ۵.۷ کنترل «سطح تفکر» چت وب (Issue D — قطعی)

**نردبان سطوح (۳ سطح، قطعی):**

| سطح (enum) | برچسب فارسی | `MAX_THINKING_TOKENS` |
|---|---|---|
| `off` | خاموش | env تنظیم **نمی‌شود** (پیش‌فرض مدل؛ عملاً بدون تفکر گسترده) |
| `standard` | متوسط | `8000` |
| `deep` | عمیق | `24000` |

- **مکانیزم (env، نه keyword):** runner در `_build_env` (پیاده‌شده در `backend/app/cli_runner.py`) بر اساس سطح مؤثر، `MAX_THINKING_TOKENS` را به env whitelist‌شدهٔ subprocess اضافه می‌کند. برای `off` کلید اصلاً ست نمی‌شود. **هیچ تزریق keyword** («ultrathink» و…) در متن کاربر انجام نمی‌شود — تا صریح و بدون آلودگی پیام باشد و در usage قابل حسابرسی بماند.
- **تعیین سطح مؤثر:** `effective = min(requested_or_conversation_default, cap)` که `cap = min(THINKING_MAX_LEVEL env, policy_cap کاربر در صورت وجود)`. ترتیب سطوح: `off < standard < deep`. سطح مؤثر همان چیزی است که در `messages.thinking_level` و رویداد `done` گزارش می‌شود (نه صرفاً خواستهٔ کاربر) تا badge دقیق باشد.
- **default و override:** اگر پیام `thinking_level` نداشت، `conversations.thinking_level` استفاده می‌شود؛ اگر کاربر در پیام سطحی انتخاب کرد و متفاوت از default گفتگو بود، هم آن نوبت با آن اجرا می‌شود و هم **default گفتگو به همان به‌روز می‌شود** (رفتار «چسبنده» مورد انتظار کاربر؛ ساده و قابل‌پیش‌بینی).
- **cap ادمین:** فاز فعلی فقط cap سراسری با `THINKING_MAX_LEVEL` (env). cap per-user/policy به‌عنوان nice-to-have: یک ستون اختیاری `max_thinking_level` روی `quotas` یا policy در فاز بعد؛ همین حالا فقط در تابع محاسبهٔ `cap` یک نقطهٔ توسعه گذاشته می‌شود. **over-build نکنید.**

**عدالت credit (تأییدشده):** توکن‌های تفکر توسط سرویس آپ‌استریم در `usage.output_tokens` شمرده می‌شوند (extended thinking = output). رویداد `result` خروجی CLI هم همان `output_tokens` تجمیعی را می‌دهد؛ runner آن را مستقیم در ledger با **وزن output مدل** ثبت می‌کند (§ضمیمهٔ الف). پس سطح بالاتر تفکر خودکار گران‌تر است و **هیچ multiplier جداگانه‌ای لازم نیست**. تنها در صورتی که سرویس آپ‌استریم فیلد usage جداگانه‌ای برای thinking tokens برگرداند (مثلاً `thinking_tokens` مجزا)، آن‌را به bucket خروجی اضافه کرده و با همان `output_weight` وزن می‌دهیم — هرگز رایگان حساب نمی‌شود.

### ۵.۸ دو سقف هم‌زمان: هفتگی + غلتان ۵ساعته (اصلاحیهٔ ۳ / Issue E — طراحی)

هدف کاربر: mirror کردن پنجرهٔ ۵ساعتهٔ خودِ آپ‌استریم، **علاوه بر** سهمیهٔ دوره‌ای موجود. هر دو هم‌زمان enforce می‌شوند؛ هرکدام زودتر پر شد درخواست را رد می‌کند.

**مدل داده (تصمیم قطعی): یک ستون روی `quotas`، نه جدول جدا.** توجیه: سقف ۵ساعته یک عدد per-user است، دقیقاً مثل `limit_credits`؛ جدول `quotas` از قبل یک-ردیف-per-user است و `check_quota` همان را می‌خواند. ستون `limit_credits_5h` (nullable) کمترین سطح تغییر است — نه FK جدید، نه join. جدول جدا فقط وقتی توجیه داشت که چند پنجرهٔ دلخواه per-user می‌خواستیم؛ اینجا فقط یک پنجرهٔ ثابت (طولش env، سقفش per-user) داریم.

**محاسبه (rolling، بدون reset):** برخلاف سهمیهٔ دوره‌ای که با `period_start` کار می‌کند، اینجا هیچ reset نیست:
```
window = timedelta(hours=ROLLING_WINDOW_HOURS)   # پیش‌فرض ۵
used_5h = SUM(usage_ledger.credits) WHERE user_id=? AND created_at >= now - window
```
ایندکس موجود `idx_ledger_user_time (user_id, created_at)` این query را پوشش می‌دهد — بدون ایندکس جدید.

**enforcement در `services/quota.py`:** `check_quota` بازنویسی می‌شود تا **هر دو** را چک کند (هر دو سطح از این تابع مشترک عبور می‌کنند — §۵.۱/۵.۲):
1. مثل امروز: `used_period >= budget` → `raise quota_exceeded(...)` (کد `quota_exceeded`).
2. جدید: اگر `limit_credits_5h` ست و `> 0` بود و `used_5h >= limit_credits_5h` → `raise quota_exceeded_5h(...)` با پیام **«سقف مصرف ۵ ساعتهٔ شما پر شده؛ تا آزاد شدن پنجره صبر کنید.»** و audit `request.denied_quota_5h`.
- تابع خروجی‌اش گسترش می‌یابد تا `used_5h`, `limit_credits_5h`, `reset_5h_at` را هم برگرداند (برای نمایش و برای Issue-C UX).

**زمان آزاد شدن پنجره (`reset_5h_at`):** چون rolling است، پنجره وقتی آزاد می‌شود که **قدیمی‌ترین credit داخل پنجره** از آن خارج شود:
```
oldest = MIN(created_at) روی ردیف‌های داخل [now-window, now]
reset_5h_at = oldest + window     # زمانی که با aging out آن ردیف، used_5h کاهش می‌یابد
```
این «آزادی جزئی» است (اولین کاهش)، نه آزادی کامل — که برای پیام «تا حدود این ساعت صبر کنید» کافی و صادقانه است. در پاسخ 429 و در بدنهٔ خطا برمی‌گردد تا UI (و retry اصلاحیهٔ ۲/Issue C) دلیل و زمان درست را نشان دهد.

**تمایز کدها:** `error_code` روی پیام شکست‌خورده (Issue C) و در بدنهٔ 429: `quota_exceeded` (هفتگی) در برابر `quota_exceeded_5h` (۵ساعته). retry فقط زمانی منطقی است که پنجره آزاد شده باشد؛ UI دکمهٔ «تلاش مجدد» را تا `reset_5h_at` غیرفعال/با تولتیپ نشان می‌دهد.

### ۵.۹ حافظهٔ مشترک تیم در سشن چت (اصلاحیهٔ ۴ / Issue I — طراحی)

درخواست عینی: اعضای تیم HR به مجموعه‌ای از حافظه‌های مشترک دسترسی داشته باشند. چون چت وب یک subprocess کوتاه‌عمرِ Claude Code با `cwd = workspace کاربر` است، سؤال اصلی «چطور دایرکتوری تیم را به آن سشن برسانیم».

**دو رویکرد ارزیابی‌شده:**

| رویکرد | چطور | مزیت | عیب |
|---|---|---|---|
| **file-visibility** | دایرکتوری تیم به‌صورت زیرپوشه در cwd دیده شود؛ دستیار با همان ابزارهای Read/Write/Edit/Glob/Grep داخل سندباکس آن را می‌خواند/می‌نویسد | طبیعی با معماری فعلی؛ هیچ ابزار/مسیر جدیدی به CLI اضافه نمی‌شود؛ خواندن **و** نوشتن هر دو کار می‌کنند؛ حجم زیاد بدون هزینهٔ توکن ثابت | دستیار باید «بداند» به `./teams/<slug>/` سر بزند (با یک اشارهٔ کوتاه در context حل می‌شود) |
| **context-injection** | محتوای حافظهٔ تیم هر نوبت به‌صورت system/context جلوی پیام تزریق شود | دستیار همیشه حافظه را «می‌بیند» بدون کاوش | هر نوبت هزینهٔ توکن؛ نوشتن ممکن نیست (فقط خواندن)؛ حجم بزرگ context را می‌ترکاند؛ نیاز به منطق تزریق جدید در runner |

**تصمیم (هیبرید، متمایل به file-visibility):**
1. **پایه = file-visibility:** دایرکتوری تیم به‌صورت **symlink** در `<cwd>/teams/<slug>/` (سیاست §۵.۴)، **خواندن‌ونوشتن برای اعضا**. این مکانیزم اصلی است — چون هم read و هم write را با سندباکس موجود پوشش می‌دهد و با اصل «یک مسیر، بدون ابزار جدید» سازگار است.
2. **اشارهٔ سبک (بخش هیبرید):** runner یک فایل کوچک `<cwd>/teams/README.md` تولیدشده می‌گذارد (فهرست تیم‌های عضو + یک خط راهنما: «حافظه‌های مشترک هر تیم در پوشهٔ هم‌نامش اینجاست؛ پیش از پاسخ به سؤالات مرتبط با تیم، این پوشه را بخوان»). این جای تزریقِ کل محتوا را می‌گیرد: چند ده توکن ثابت به‌جای کل حافظه، و دستیار خودش با Read سراغ فایل‌های مرتبط می‌رود. **کل محتوای حافظه تزریق نمی‌شود.**

این هیبرید عملاً هزینهٔ context-injection را ندارد ولی کشف‌پذیری‌اش را دارد.

**هم‌زمانی/consistency:** دایرکتوری تیم یک پوشهٔ فایل‌سیستمیِ مشترک است و سشن‌ها **کوتاه‌عمر و per-message**اند. معناشناسی صراحتاً **last-writer-wins** در سطح فایل است (بدون قفل توزیع‌شده). چون نوشتن‌ها معمولاً افزودن/به‌روزکردن فایل‌های جدا هستند و نه ویرایش هم‌زمان یک فایل، برخورد نادر است؛ هیچ تضمین تراکنشی روی دایرکتوری تیم داده نمی‌شود و این در UI («حافظهٔ مشترک؛ آخرین نوشته برنده است») مستند می‌شود. write ابزار CLI اتمیک-per-file است (فایل کامل نوشته می‌شود) پس فایل نیمه‌نوشته دیده نمی‌شود.

**مرزهای امنیت (تکرار §۱۱):** symlink فقط برای تیم‌هایی ساخته می‌شود که کاربر در `team_members` عضوشان است؛ resolve هر دسترسی به مجموعهٔ containment (workspace ∪ تیم‌های عضو) چک می‌شود؛ کاربر هرگز به تیمی که عضوش نیست نمی‌رسد. تغییر عضویت در نوبت بعد اعمال می‌شود (symlink کهنه حذف می‌شود).

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
  # custom handler = relay گنگ (بخش ۲.۱)؛ پیکربندی مؤثر را از backend می‌گیرد.
  custom_provider_map:
    - provider: "ecocode-upstream"
      custom_handler: ecocode_upstream_handler.adapter   # فایل mount‌شده (ro) در کانتینر
  drop_params: true

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  database_url: "os.environ/LITELLM_DATABASE_URL"
  # budget به‌عنوان کمربند ایمنی دوم فعال است ولی authoritative نیست (بخش ۶.۳).
```

**رفتار پیاده‌شدهٔ handler (relay گنگ):** کانتینر litellm نه DB دارد، نه crypto، نه فایل اعتبارنامه. handler به ازای هر درخواست (با cache ۱۵ثانیه‌ای):
1. `GET backend:/internal/upstream-config` (bearer = `LITELLM_MASTER_KEY`؛ فقط شبکهٔ داخلی، هرگز پشت nginx expose نمی‌شود) → `{mode, base_url, api_key, auth_header, oauth_beta, model_map}`. backend اینجا env/settings/TokenManager را resolve می‌کند؛ در دسترس‌نبودن لحظه‌ای backend → fallback امن به mock بدون credential.
2. **اعمال `model_map` (پیاده‌شده):** نگاشت `model_key` داخلی → `upstream_model` (مثلاً `claude-sonnet` → `claude-sonnet-5`) قبل از relay اعمال می‌شود؛ بدون آن کلید داخلی به سرویس واقعی نشت می‌کرد و 404 می‌گرفت.
3. relay به `POST {base_url}/v1/messages` با شکل اصیل Messages API (هدرها طبق §۴.۴).
4. **گزارش usage واقعی (پیاده‌شده):** usage کامل پاسخ آپ‌استریم (شامل cache_read/cache_write که schema چانک‌های streaming litellm حملش نمی‌کند) به `POST backend:/internal/usage-report` با کلید `x-ecocode-request-id` برمی‌گردد؛ backend همین را در ledger می‌نویسد (fallback: usage خود litellm). → usage_ledger مستقل از حسابداری litellm، authoritative می‌ماند.
5. **خطاها:** non-2xx آپ‌استریم به exception تایپ‌دار litellm با status واقعی re-raise می‌شود (جدول §۵.۲).
6. **(اصلاحیهٔ ۳ / Issue F):** همهٔ response headerهای با پیشوند `anthropic-ratelimit` را خام برمی‌دارد و به `POST /internal/upstream-limits` می‌فرستد (fire-and-forget، شکستش درخواست را نمی‌شکند)؛ parse و upsert در backend (§۴.۵). handler همچنان relay گنگ می‌ماند — نام هدرها را فرض نمی‌کند.

**handler (+ `credentials.py` در backend) تنها فایل‌هایی هستند که با تغییر مکانیزم سرویس آپ‌استریم عوض می‌شوند.**

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
| GET | `/api/auth/me` | user | اطلاعات کاربر جاری + role + مدل‌های مجاز + خلاصهٔ سهمیه + **`max_thinking_level` مؤثر** (Issue D) + **(اصلاحیهٔ ۴)** `teams: [{id, name, slug, role_in_team}]` |

### چت و تاریخچه (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/conversations` | لیست گفتگوهای کاربر (paginate, search با `?q=`) — هر آیتم شامل **`generating: bool`** |
| POST | `/api/conversations` | ساخت گفتگوی جدید (`{title?, model_key}`) |
| GET | `/api/conversations/{id}` | جزئیات + پیام‌ها (فقط مالک) + `generating` + `status` هر پیام (`complete`/`streaming`/`failed`) |
| PATCH | `/api/conversations/{id}` | تغییر عنوان / مدل / **`thinking_level` پیش‌فرض** (Issue D) |
| DELETE | `/api/conversations/{id}` | حذف (soft) — سشن CLI مرتبط دیگر resume نمی‌شود |
| POST | `/api/conversations/{id}/messages` | **پذیرش نوبت** (pipeline ۵.۱): body `{content, thinking_level?}` (Issue D: اختیاری؛ نبود → default گفتگو)؛ اعتبارسنجی سنکرون (401/403/409/429) سپس **202** `{assistant_message_id, generating:true, thinking_level:<مؤثر>}` — پاسخ SSE نمی‌دهد؛ اجرای CLI در پس‌زمینه ادامه می‌یابد حتی اگر client برود |
| GET | `/api/conversations/{id}/stream` | **استریم/reattach (SSE، پروتکل ۵.۳):** نوبت فعال → replay بافر از ابتدا + دنبالهٔ زنده تا `done`/`error`؛ نوبت فعال نیست → `event: idle` و بستن. idempotent — هر تعداد بار و از هر تب |
| POST | `/api/conversations/{id}/messages/{message_id}/retry` | **تلاش مجدد نوبت شکست‌خورده** (Issue C، معناشناسی §۵.۱): فقط آخرین پیامِ `failed`؛ reset همان ردیف به `streaming` و اجرای نوبت تازه با متن پیام user قبلی → **202** `{assistant_message_id, generating:true}`؛ خطاها: 409 `not_retryable`/`chat_busy`، 403، 429 |
| POST | `/api/conversations/{id}/attachments` | آپلود فایل (multipart) → کپی داخل workspace + attachment id |
| GET | `/api/attachments/{id}` | دانلود فایل پیوست (فقط مالک گفتگو) |

### workspace — فایل‌های کاربر (جدید، F4.6)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/workspace/files` | لیست بازگشتی فایل‌های workspace خود کاربر: `[{file_id, name, relpath, size_bytes, modified_at}]` |
| GET | `/api/workspace/files/{file_id}` | دانلود فایل |
| DELETE | `/api/workspace/files/{file_id}` | حذف فایل (اختیاری در UI؛ endpoint موجود) + audit `workspace.file_delete` |

**قرارداد `file_id`:** شناسهٔ opaque = base64url(مسیر نسبی داخل workspace). سرور هنگام resolve: decode → join با root workspace کاربرِ session → `realpath` → **الزام** به قرارگیری زیر همان root (رد traversal و symlink-escape با 404). نام فایل یا user id هرگز در URL نیست؛ هویت همیشه از session.

### تیم‌ها و حافظهٔ مشترک (کاربر) — اصلاحیهٔ ۴ / Issue H+I
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/teams/mine` | تیم‌های کاربر جاری `[{id, name, slug, role_in_team, member_count}]` (نمای «تیم‌های من») |
| GET | `/api/teams/{id}/members` | اعضای تیم (فقط اگر خود کاربر عضو باشد؛ متادیتا: username/display_name/role_in_team) |
| GET | `/api/teams/{id}/memory/files` | لیست فایل‌های حافظهٔ مشترک تیم — **فقط اگر عضو**؛ همان شکل workspace files |
| POST | `/api/teams/{id}/memory/files` | آپلود فایل به حافظهٔ تیم (multipart) — فقط عضو |
| GET | `/api/teams/{id}/memory/files/{file_id}` | دانلود — فقط عضو |
| DELETE | `/api/teams/{id}/memory/files/{file_id}` | حذف — فقط عضو + audit `team.memory.file_delete` |

**enforcement عضویت (قطعی):** هر endpoint تیمی ابتدا چک می‌کند `(team_id, current_user.id) ∈ team_members` (یا `role=admin`)؛ در غیر این صورت **404** (نه 403 — تا وجود/عدم‌وجود تیم برای غیرعضو فاش نشود). `file_id` همان قرارداد opaque base64url؛ resolve با root = `realpath(/data/teams/<team_id>/memory)` و الزام containment زیر همان root. ادمین می‌تواند حافظهٔ هر تیم را مدیریت کند (بدون نیاز به عضویت).

### کلید API شخصی (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/keys` | لیست کلیدهای کاربر (prefix, name, last_used, active) |
| POST | `/api/keys` | ساخت کلید (`{name}`) → **کلید کامل فقط در این پاسخ** |
| DELETE | `/api/keys/{id}` | ابطال کلید |

### مصرف (کاربر)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/usage/me` | مصرف دورهٔ جاری / سقف، تفکیک مدل و کلید، روند روزانه (F6.1) + **(اصلاحیهٔ ۳)** بلوک ۵ساعته: `{used_5h, limit_credits_5h, reset_5h_at}` |

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

### ادمین — تیم‌ها (اصلاحیهٔ ۴ / Issue H)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/teams` | لیست تیم‌ها + شمار اعضا |
| POST | `/api/admin/teams` | ساخت تیم (`{name, slug?, description?}`؛ slug اگر نبود از name تولید و یکتاسازی می‌شود) |
| GET | `/api/admin/teams/{id}` | جزئیات + اعضا |
| PATCH | `/api/admin/teams/{id}` | تغییر نام/description (slug پس از ساخت ثابت است — چون نام پوشهٔ symlink؛ تغییرش migration دیسک می‌خواهد) |
| DELETE | `/api/admin/teams/{id}` | حذف تیم (رکوردها CASCADE؛ دایرکتوری `/data/teams/<id>` روی دیسک می‌ماند تا پاک‌سازی دستی — مثل workspace) |
| POST | `/api/admin/teams/{id}/members` | افزودن عضو (`{user_id, role_in_team?}`) |
| DELETE | `/api/admin/teams/{id}/members/{user_id}` | حذف عضو |
| GET/POST/DELETE | `/api/admin/teams/{id}/memory/files[...]` | مدیریت حافظهٔ هر تیم توسط ادمین (همان قرارداد endpointهای کاربر، بدون نیاز به عضویت) |

### ادمین — سیاست و سهمیه
| متد | مسیر | هدف |
|---|---|---|
| PUT | `/api/admin/users/{id}/policy` | تنظیم مدل‌های مجاز (`{model_keys: [...]}`) → sync به LiteLLM |
| PUT | `/api/admin/users/{id}/quota` | تنظیم `{period, limit_credits, limit_credits_5h?}` — **(اصلاحیهٔ ۳)** سقف ۵ساعته (NULL/۰ = نامحدود) |
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
| GET | `/api/admin/users/{id}/usage` | **(اصلاحیهٔ ۳ / Issue G)** گزارش مصرف یک کاربر: روند روزانه + by_model + by_key + بلوک ۵ساعته `{used_5h, limit_credits_5h, reset_5h_at}` + بلوک هفتگی `{used, limit, bonus, period_start, reset_at}` — همان دادهٔ «مصرف من» او، فقط متادیتا (هرگز محتوای چت). پارامتر `?since=` |
| GET | `/api/admin/users/{id}/usage/export.csv` | **(اصلاحیهٔ ۳، nice)** CSV تک‌کاربر (همان ستون‌های usage/export.csv، فیلترشده به این کاربر) |
| GET | `/api/admin/audit` | لاگ رخدادها (filter بر action/user/بازهٔ زمانی) |

### ادمین — اتصال آپ‌استریم (بخش ۴)
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/admin/upstream/status` | وضعیت اتصال (mode, connected, expires_at, **refresh_token_valid_until, last_refresh, auto_refresh**, base_url, creds_source — شکل کامل در §۴.۱) |
| PUT | `/api/admin/upstream/apikey` | ست توکن دستی (mode apikey؛ رمزشده ذخیره می‌شود) |
| PUT | `/api/admin/upstream/mode` | سوییچ mode (`cli_creds`/`apikey`/`mock`) + audit `upstream.mode_change` |
| GET | `/api/admin/upstream/account-limits` | **(اصلاحیهٔ ۳ / Issue F)** لیمیت خودِ اکانت آپ‌استریم: `{available, windows:[{window, limit, remaining, reset_at, unit, last_updated, stale}], tier, subscription}` (§۴.۵)؛ اگر آپ‌استریم هدری نداده → `available:false` + tier/subscription از credentials |

### سلامت
| متد | مسیر | هدف |
|---|---|---|
| GET | `/api/health` | liveness: `{status, db, litellm, upstream_mode, upstream_connected, cli_available}` |

**قرارداد خطا (یکنواخت):** بدنهٔ `{ "error": { "code": "quota_exceeded", "message": "پیام فارسی قابل‌نمایش" } }` با status مناسب (401/403/409/429/400/502/503/500). Dev2 روی `error.message` رندر می‌کند و روی `error.code` منطق. کدهای ویژه: `chat_busy` (409، پیام هم‌زمان در یک گفتگو)، `not_retryable` (409، retry روی پیام غیرمجاز)، خانوادهٔ `upstream_*` مسیر passthrough (جدول §۵.۲)، و **(اصلاحیهٔ ۳)** `quota_exceeded` / `quota_exceeded_5h` (هر دو 429، با فیلد `reset_at`/`reset_5h_at` در بدنه برای نمایش زمان آزادی).

---

## ۹. نقشهٔ صفحات فرانت (React + Vite، فارسی RTL)

کل UI فارسی RTL با فونت Vazirmatn؛ سوییچ به انگلیسی (فاز P3) با i18next آماده می‌شود ولی رشته‌ها فارسی-اول.

| مسیر | صفحه | دسترسی | محتوا |
|---|---|---|---|
| `/login` | ورود | عمومی | فرم username/password، پیام خطای فارسی، rate-limit-aware |
| `/chat` | چت (پیش‌فرض کاربر) | user | سایدبار تاریخچه + پنجرهٔ گفتگو + **پنل «فایل‌های من»** |
| `/chat/:id` | گفتگوی خاص | user | همان، گفتگوی انتخابی |
| `/usage` | مصرف من | user | نوار پیشرفت سهمیهٔ هفتگی، تفکیک مدل/کلید، نمودار روند روزانه، هشدار ۸۰٪ + **(اصلاحیهٔ ۳)** نوار جداگانهٔ «۵ ساعتهٔ اخیر» (used_5h/limit + «آزاد می‌شود حدود …») در کنار نوار هفتگی |
| `/keys` | کلیدهای API من | user | لیست + ساخت (نمایش یک‌بارهٔ کلید در modal با دکمهٔ کپی) + ابطال |
| `/teams` | تیم‌های من | user | **(اصلاحیهٔ ۴ / Issue H)** لیست فقط‌خواندنی تیم‌های عضو (نام، اعضا) + ورود به «حافظهٔ مشترک تیم» هر کدام |
| `/teams/:id/memory` | حافظهٔ مشترک تیم | user (عضو) | **(اصلاحیهٔ ۴ / Issue I)** پنل مثل «فایل‌های من» ولی scoped به تیم: لیست/آپلود/دانلود/حذف فایل‌های `/api/teams/{id}/memory/files`؛ برچسب «حافظهٔ مشترک — آخرین نوشته برنده است» |
| `/admin/users` | مدیریت کاربران | admin | جدول، ساخت/ویرایش/غیرفعال، لینک به policy/quota |
| `/admin/teams` | مدیریت تیم‌ها | admin | **(اصلاحیهٔ ۴ / Issue H)** CRUD تیم، افزودن/حذف عضو (chip/autocomplete کاربر)، ورود به حافظهٔ هر تیم |
| `/admin/policies` | سیاست‌ها | admin | تنظیم مدل‌های مجاز و سهمیهٔ هر کاربر + **(اصلاحیهٔ ۳)** فیلد «سقف ۵ ساعته» |
| `/admin/usage` | مصرف کل | admin | رتبه‌بندی کاربران (هر ردیف لینک به گزارش کاربر)، تفکیک مدل، روند، دکمهٔ CSV + **(اصلاحیهٔ ۳)** کارت «لیمیت اکانت اصلی» (مصرف/باقی‌مانده/reset هر پنجره + `last_updated`؛ در نبود داده: فقط tier/subscription و پیام صریح) |
| `/admin/users/:id/usage` | گزارش کاربر | admin | **(اصلاحیهٔ ۳ / Issue G)** drill-down: همان نمای «مصرف من» کاربر (روند، by_model، by_key، نوار هفتگی و ۵ساعته) + دکمهٔ CSV تک‌کاربر — فقط متادیتا، هرگز محتوای چت |
| `/admin/models` | مدل‌ها و وزن‌ها | admin | ویرایش input/output/cache وزن هر مدل |
| `/admin/settings` | اتصال آپ‌استریم | admin | **کارت وضعیت توکن (اصلاحیهٔ ۲):** «توکن معتبر تا …»، «refresh token معتبر تا … / نامشخص»، آخرین refresh (زمان/نتیجه/خطا)، وضعیت auto_refresh؛ CTA فارسی «claude login روی سرور» **فقط** وقتی `degraded`/`failed` (§۴.۱)؛ + ورود توکن apikey، سوییچ mode |
| `/admin/audit` | لاگ رخدادها | admin | جدول فیلترپذیر audit_log |

**اجزای کلیدی چت:**
- **model picker** فیلترشده به مدل‌های مجاز کاربر (از `/api/auth/me`).
- **thinking-level picker (Issue D):** کنترل کوچک کنار model picker با ۳ گزینه (خاموش/متوسط/عمیق)، محدود به `max_thinking_level` از `/api/auth/me`. مقدار اولیه = `conversations.thinking_level`؛ تغییر آن هم روی نوبت بعد اعمال می‌شود هم default گفتگو را به‌روز می‌کند (رفتار چسبنده §۵.۷). در body پیام به‌صورت `thinking_level` می‌رود.
- **badge سطح تفکر روی پاسخ:** هر حباب assistant که `thinking_level` دارد (از رویداد `done` یا `GET conversation`) یک badge کوچک نشان می‌دهد (مثلاً «تفکر: عمیق»)؛ `off` badge ندارد.
- **چرخهٔ ارسال/استریم (اصلاحیهٔ ۲):** ارسال = `POST messages` → 202 → بلافاصله باز کردن `GET /stream` و رندر رویدادها. **باز کردن هر گفتگو:** ابتدا `GET /api/conversations/{id}`؛ اگر `generating:true` (یا آخرین پیام `status='streaming'`) → اتصال خودکار به `/stream` و رندر replay از ابتدای نوبت — از دید کاربر انگار هیچ‌وقت قطع نشده. رویداد `idle` → اتصال بسته، حالت عادی. `done` → refresh فایل‌ها/مصرف (مثل قبل) + invalidate لیست گفتگوها (خاموش‌شدن اسپینر).
- **اسپینر سایدبار:** آیتم‌هایی که `generating:true` دارند اسپینر کوچک می‌گیرند؛ لیست با polling سبک TanStack Query (هر ۱۰s وقتی حداقل یک generating هست) یا invalidate بعد از `done`.
- **حباب شکست‌خورده + تلاش مجدد (Issue C):** پیام assistant با `status='failed'` به‌صورت حباب خطا رندر می‌شود: `error_reason` فارسی + دکمهٔ **«تلاش مجدد»** (فقط وقتی آخرین پیام گفتگوست). کلیک → `POST .../retry` → 202 → همان حباب به حالت استریم برمی‌گردد و `/stream` باز می‌شود. حالت `aborted_restart` («سرویس هنگام تولید پاسخ راه‌اندازی مجدد شد») همین مسیر را دارد.
- **رندر استریم:** خواندن SSE (پروتکل ۵.۳: `start`/`delta`/`tool`/`done`/`error`/`idle`) با `fetch` + `ReadableStream`؛ نمایش تدریجی؛ رویداد `tool` به‌صورت chip «در حال ساخت/ویرایش فایل…»؛ markdown با `react-markdown`؛ code block با highlight و دکمهٔ کپی.
- **پنل «فایل‌های من» (جدید، مینیمال):** drawer/tab کنار چت؛ `GET /api/workspace/files` → لیست (نام، حجم، تاریخ) + دکمهٔ دانلود؛ refresh خودکار بعد از رویداد `done` که `files_changed` دارد. حذف: فاز بعد (endpoint هست، UI اختیاری).
- **دسترسی حافظهٔ تیم در چت (اصلاحیهٔ ۴):** در حین چت، دستیار حافظهٔ تیم‌های عضو را به‌صورت `./teams/<slug>/` می‌بیند و می‌تواند بخواند/بنویسد (§۵.۹)؛ مدیریت مستقیم فایل‌ها از صفحهٔ `/teams/:id/memory` انجام می‌شود. نیازی به کنترل جدید در خود صفحهٔ چت نیست.
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
- [ ] **(اصلاحیهٔ ۲)** بستن تب وسط تولید → پیام کامل persist شد؛ باز کردن دوباره → replay از ابتدای نوبت + ادامهٔ زنده؛ اسپینر سایدبار روشن/خاموش درست.
- [ ] **(اصلاحیهٔ ۲)** restart backend وسط نوبت → پیام `failed/aborted_restart` با دلیل فارسی؛ دکمهٔ «تلاش مجدد» ظاهر و کار می‌کند (202 → استریم تازه، بدون ردیف اضافه، بدون شارژ نوبت شکست‌خورده).
- [ ] **(اصلاحیهٔ ۲)** retry روی پیام غیرآخر/غیرfailed → 409 `not_retryable`؛ retry هم‌زمان دوم → 409.
- [ ] **(اصلاحیهٔ ۲)** انقضای مصنوعی access token (دستکاری expiresAt در mock) → auto-refresh اجرا، توکن چرخیده در volume + settings؛ کارت ادمین «آخرین refresh: موفق». خراب کردن refresh token → auto_refresh=failed + CTA فارسی.
- [ ] **(اصلاحیهٔ ۲)** `claude login` جدید روی هاست (تغییر فایل seed) → ظرف ≤۶۰s adopt؛ فایل هاست دست‌نخورده → هرگز توکن backend-managed را clobber نمی‌کند.
- [ ] **(اصلاحیهٔ ۲ / D)** انتخاب سطح «عمیق» → `MAX_THINKING_TOKENS=24000` در env پروسه؛ badge «تفکر: عمیق» روی پاسخ؛ output_tokens و در نتیجه credit نسبت به «متوسط» بیشتر است (با mock هم دیده می‌شود). سطح بالاتر از `THINKING_MAX_LEVEL` در UI اصلاً قابل انتخاب نیست و در backend هم cap می‌شود.
- [ ] **(اصلاحیهٔ ۲ / D)** passthrough: ارسال `thinking:{type:"enabled",budget_tokens:N}` از Cline دست‌نخورده به آپ‌استریم می‌رسد (strip نمی‌شود، تزریق هم نمی‌شود).
- [ ] `openapi.json` نسخهٔ فرانت با backend یکی است (CI diff).

### تقسیم کار اصلاحیهٔ ۲ (Issues A+B+C+D)

**Dev1 — backend (به این ترتیب):**
1. **A:** ستون‌های `messages.status/error_code/error_reason` + migration + مارک `failed/aborted_restart` در استارتاپ؛ `TurnRegistry` + ring buffer + جداسازی نوبت به `asyncio.create_task`؛ تبدیل `POST messages` به 202؛ endpoint جدید `GET /stream` (replay+live+idle)؛ فلگ `generating` در دو endpoint گفتگو.
2. **C:** endpoint `POST .../messages/{id}/retry` با گاردها و reset-in-place (§۵.۱)؛ پرکردن error_code/error_reason در همهٔ مسیرهای شکست (cli_error/timeout/quota/upstream_rate_limited).
3. **B:** ارتقای `app/upstream/credentials.py` به TokenManager: seed-بر-تغییر (hash)، refresh خودکار single-flight علیه `UPSTREAM_OAUTH_TOKEN_URL`، persist دوگانه (volume + settings رمزشده)، بازیابی استارتاپ، حالت‌های `active/degraded/failed`، فیلدهای جدید status؛ env جدید در `.env.example`.
4. **D:** enum `thinking_level` + ستون‌های `conversations.thinking_level`/`messages.thinking_level` (migration)؛ نگاشت سطح→`MAX_THINKING_TOKENS` و افزودن به `_build_env` (فقط چت وب)؛ محاسبهٔ سطح مؤثر با cap (`THINKING_MAX_LEVEL` + نقطهٔ توسعهٔ policy)؛ افزودن `thinking_level` به body پذیرش پیام، رویداد `done`، و `PATCH conversation`؛ **پاس‌دادن `thinking` client در `_to_anthropic_body` handler** (passthrough)؛ تأیید ثبت output_tokens شامل thinking در ledger؛ `max_thinking_level` در `/api/auth/me`؛ به‌روزرسانی mock-claude برای انعکاس env در usage.
5. regenerate `docs/openapi.json` و اطلاع به Dev2.

**Dev2 — frontend:**
1. **A:** بازنویسی چرخهٔ ارسال (202 + همیشه `GET /stream`)، reattach خودکار هنگام باز کردن گفتگوی `generating`، رندر رویداد `idle`، اسپینر سایدبار + invalidate بعد از `done`.
2. **C:** حباب `failed` با `error_reason` فارسی + دکمهٔ «تلاش مجدد» (فقط آخرین نوبت) + برگشت حباب به حالت استریم پس از 202.
3. **B:** کارت وضعیت توکن در `/admin/settings` (چهار فیلد + CTA شرطی).
4. **D:** thinking-level picker کنار model picker (محدود به `max_thinking_level`)، ارسال `thinking_level` در body، همگام‌سازی با default گفتگو، و badge سطح تفکر روی حباب‌های assistant.

### تقسیم کار اصلاحیهٔ ۳ (Issues E+F+G) — پس از integration اصلاحیهٔ ۲

> **پیش‌نیاز:** روی branch بعد از merge اصلاحیهٔ ۲؛ **revision متوالی Alembic** (down_revision = آخرین revision اصلاحیهٔ ۲). ستون‌ها با ADD COLUMN اضافه می‌شوند (nullable، بدون بازنویسی جداول موجود). E مستقل از F است و می‌تواند موازی برود؛ G به هر دو (به‌ویژه E برای بلوک ۵ساعته) وابسته است پس آخر.

**Dev1 — backend (به این ترتیب):**
1. **E:** migration `quotas.limit_credits_5h` (nullable)؛ بازنویسی `services/quota.py`: `check_quota` هر دو سقف را چک کند، تابع `get_used_5h(window)` و محاسبهٔ `reset_5h_at` (min(created_at) داخل پنجره + window)؛ خطای جدید `quota_exceeded_5h` در `errors.py` با `reset_5h_at` در بدنه؛ audit `request.denied_quota_5h`؛ env `ROLLING_WINDOW_HOURS`؛ گسترش `/api/usage/me` و `PUT quota` با فیلدهای ۵ساعته. **بدون** تغییر `run_periodic_reset` (پنجرهٔ غلتان reset ندارد).
2. **F:** جدول `upstream_account_limits` (migration)؛ endpoint داخلی `POST /internal/upstream-limits` (parse خانوادهٔ `anthropic-ratelimit-*` → window/limit/remaining/reset، upsert)؛ افزودن capture هدر در `ecocode_upstream_handler.py` (fire-and-forget)؛ endpoint `GET /api/admin/upstream/account-limits` (+ محاسبهٔ `stale` از `last_updated`، fallback به tier/subscription از credentials)؛ probe اختیاری پشت env (پیش‌فرض خاموش).
3. **G:** endpoint `GET /api/admin/users/{id}/usage` (بازاستفاده از منطق `admin_usage.py` با فیلتر `user_id` + بلوک‌های ۵ساعته/هفتگی از quota service) + CSV تک‌کاربر (فیلتر همان query موجود).
4. regenerate `docs/openapi.json` و اطلاع به Dev2.

**Dev2 — frontend:**
1. **E:** نوار «۵ ساعتهٔ اخیر» در `/usage`؛ فیلد «سقف ۵ ساعته» در ویرایشگر سهمیهٔ `/admin/policies`؛ در چت، پیام/حباب خطای `quota_exceeded_5h` با متن مخصوص و زمان آزادی (هماهنگ با دکمهٔ retry اصلاحیهٔ ۲/C که تا `reset_5h_at` غیرفعال می‌ماند).
2. **F:** کارت «لیمیت اکانت اصلی» در `/admin/usage` (پنجره‌ها + `last_updated` + برچسب stale؛ حالت `available:false`).
3. **G:** صفحهٔ `/admin/users/:id/usage` (drill-down از لیست کاربران و از ردیف‌های رتبه‌بندی مصرف) + دکمهٔ CSV تک‌کاربر.

### تقسیم کار اصلاحیهٔ ۴ (Issues H+I) — پس از HEAD 45d9e14

> **پیش‌نیاز:** revision متوالی Alembic `0004` (down_revision=`0003`). جدول‌های جدید + volume `teams_data`. H مستقل است و اول می‌رود؛ I روی H سوار می‌شود (نیاز به عضویت). per-user quota/policy دست‌نخورده.

**Dev1 — backend:**
1. **H:** migration `teams` + `team_members` (+ enum `team_role`) + volume `teams_data:/data/teams`؛ CRUD ادمین `/api/admin/teams` (+ members)؛ تولید/یکتاسازی slug؛ افزودن `teams[]` به `/api/auth/me` و endpoint `/api/teams/mine` + `/api/teams/{id}/members`.
2. **I — runner:** تابع `member_team_dirs(user_id)` (خواندن `team_members`) و `sync_team_links(user_id, cwd)` که symlinkهای `<cwd>/teams/<slug>` را با عضویت هم‌گام می‌کند + تولید `<cwd>/teams/README.md` (اشارهٔ سبک §۵.۹)؛ فراخوانی پیش از spawn در `cli_runner.py`؛ ساخت `/data/teams/<id>/memory` با 0770.
3. **I — containment و endpointها:** گسترش منطق `workspace_files.resolve_file_id` به یک resolver عمومی با root پارامتری؛ ماژول جدید team-memory (root = `/data/teams/<id>/memory`) با همان قرارداد opaque؛ endpointهای `/api/teams/{id}/memory/files` (+ نسخهٔ ادمین) با گارد عضویت (404 برای غیرعضو)؛ audit `team.memory.file_delete`.
4. regenerate `docs/openapi.json` و اطلاع به Dev2.

**Dev2 — frontend:**
1. **H:** صفحهٔ `/admin/teams` (CRUD + مدیریت اعضا با autocomplete کاربر)؛ صفحهٔ فقط‌خواندنی `/teams` («تیم‌های من») از `/api/teams/mine`؛ نمایش تیم‌ها در نمای پروفایل/هدر از `/me`.
2. **I:** صفحهٔ `/teams/:id/memory` («حافظهٔ مشترک تیم») — کامپوننت فایل‌منیجرِ همان «فایل‌های من» با baseِ endpoint تیمی + برچسب last-writer-wins؛ ادمین از `/admin/teams` هم به همان کامپوننت (root تیم) دسترسی دارد.

---

## ۱۱. امنیت + برنامهٔ تست/تأیید

### ۱۱.۱ نکات امنیتی (الزامی)
- **اعتبارنامهٔ آپ‌استریم:** mode cli_creds: mount فقط‌خواندنی + کپی فقط داخل HOME کانتینر؛ هرگز در DB/لاگ/مرورگر. mode apikey: **Fernet** (کلید از `ECOCODE_SECRET_KEY` در env) در `settings`. کلید env در secrets سرور، نه در repo.
- **کلید API کاربر:** فقط `sha256` ذخیره؛ متن کامل یک‌بار نمایش. `.env` و `certs/` در `.gitignore`.
- **confinement مسیر CLI:** بدون `--dangerously-skip-permissions`؛ allowlist ابزار فقط-فایل با الگوی `./**`؛ `Bash/WebFetch/WebSearch` ممنوع (توجیه در ۵.۴)؛ env پروسه لیست سفید (هیچ secret backend به CLI نمی‌رسد). **(اصلاحیهٔ ۴)** مجموعهٔ مجاز = workspace کاربر ∪ دایرکتوری تیم‌های عضو؛ symlink تیم فقط برای عضو ساخته می‌شود و هر resolve فایل realpath-چک‌شده در همین اجتماع است.
- **مرز دسترسی تیم (اصلاحیهٔ ۴ / Issue I):** عضویت در `team_members` **تنها** مرز دسترسی به حافظهٔ تیم است — هم در سشن CLI (symlink فقط برای عضو) و هم در endpointهای `/api/teams/{id}/memory/*` (گارد عضویت، 404 برای غیرعضو تا وجود تیم فاش نشود). کاربر هرگز به دایرکتوری تیمی که عضوش نیست نمی‌رسد؛ تغییر عضویت در نوبت بعد اعمال می‌شود. `file_id` تیمی opaque و containment زیر `/data/teams/<id>/memory`. ادمین استثناست (مدیریت هر تیم).
- **workspace isolation:** `file_id` opaque + realpath containment check؛ user id هرگز از URL؛ پرمیشن پوشه‌ها 0700 متعلق به app user.
- **rate limiting لاگین:** حداکثر ~۵ تلاش ناموفق در ۱۵ دقیقه به ازای username+IP؛ سپس backoff. همهٔ تلاش‌ها در audit.
- **کنترل منابع CLI:** semaphore هم‌زمانی + timeout + kill group (پروسهٔ فرزند هم بمیرد)؛ سقف حجم workspace هر کاربر (softquota ~1GB، هشدار در UI) در فاز ۱ فقط گزارشی.
- **CORS:** پیش‌فرض بسته. فرانت و API هم‌دامنه (پشت یک nginx)؛ اگر باز شد فقط origin سازمان.
- **بدون محتوای چت در لاگ:** logger backend نباید body پیام‌ها، خروجی CLI یا پاسخ‌ها را لاگ کند. فقط متادیتا (user_id, model, tokens, exit code, request_id). code review این را چک می‌کند.
- **حریم خصوصی ادمین:** endpointهای ادمین هیچ join به `messages.content` و هیچ دسترسی به workspace کاربران ندارند. **(اصلاحیهٔ ۳ / Issue G)** گزارش per-user فقط از `usage_ledger`/`quotas` می‌خواند (توکن، credit، مدل، کلید، زمان) — هرگز از `messages`/`conversations.title`/`attachments`؛ همان قاعدهٔ «ادمین فقط متادیتا».
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
8. **(اصلاحیهٔ ۴)** ادمین تیم HR می‌سازد و کاربر اول را عضو می‌کند؛ در چت کاربر اول «در پوشهٔ تیم HR یادداشتی بنویس» → فایل در `./teams/hr/` ساخته و در `/teams/:id/memory` دیده می‌شود؛ عضو دوم همان تیم آن را می‌بیند؛ کاربرِ **غیرعضو** با درخواست `/api/teams/{hr}/memory/files` → **404** و در چتش `./teams/hr` وجود ندارد.

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

*پایان سند فنی v1.4 — اصلاحیه‌های ۱–۳ پیاده و merge شده (HEAD 45d9e14)؛ اصلاحیهٔ ۴ (H/I) طراحی‌شده، اجرا روی revision متوالی 0004.*
