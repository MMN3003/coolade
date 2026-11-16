# ضمیمهٔ ۷ — لایهٔ دانش (Knowledge Layer): قوانین، دانش، حافظه، یادگیری از چت

| | |
|---|---|
| **محصول** | Coolade Studio (PRD: `docs/PRD-V2.md` · TECH: `docs/TECH-V2.md` · سرویس‌ها: `docs/SERVICES-V2.md`) |
| **نسخهٔ ضمیمه** | 1.0 — as-built |
| **تاریخ** | 2026-09-10 |
| **مالک محصول** | Amin |
| **مهاجرت** | `0010_knowledge`, `0011_team_learning` — جدول `knowledge_entries`، ستون `users.learning_enabled`، ستون `conversations.learned_through_message_id` |

> **خلاصهٔ اجرایی:** تا امروز «دانش» دستیار سه جای پراکنده داشت: اسکیلِ سرویس (فقط ادمین، فقط با انتشار نسخه)، `CLAUDE.md` شخصی (فقط با «یادت باشه»، فقط فایل) و پوشهٔ حافظهٔ تیم (فایل). این ضمیمه یک **پایگاه دانش واحد و چهارسطحی** می‌سازد که (۱) ادمین، (۲) خودِ کاربر، (۳) تیم و (۴) خودِ سیستم (با یادگیری از چت‌ها) در آن می‌نویسند، و هر مورد **خودکار** در نوبت‌های بعدیِ همان دامنه در اختیار دستیار قرار می‌گیرد. خروجی JSONL گفتگوها و دانش هم فراهم شده تا بعداً بتوان یک مدل/سیستم سازمانی روی آن آموزش داد.

---

## ۱. مدل مفهومی

هر **مورد دانش** (`knowledge_entries`) یک سطر است با:

| فیلد | معنی |
|---|---|
| `scope` | دامنهٔ اعمال — دقیقاً یکی از چهار مورد جدول زیر |
| `kind` | `rule` = دستور الزامی که همیشه رعایت می‌شود · `knowledge` = واقعیت/تعریف/داده که وقتی مربوط است استفاده می‌شود |
| `source` | `manual` (ادمین/کاربر/دستیار سرویس‌ساز) · `learned` (استخراج خودکار از چت همان کاربر) |
| `title`, `content` | عنوان کوتاه + متن مستقل (سقف ۲۰k کاراکتر؛ عملاً چند خط) |
| `enabled`, `sort_order` | خاموش/روشن بدون حذف؛ ترتیب |

### چهار دامنه و مسیر رسیدن به دستیار

| scope | چه کسی می‌نویسد | برای چه کسی اعمال می‌شود | چگونه به دستیار می‌رسد |
|---|---|---|---|
| **`service`** | ادمین (پنل یا دستیار سرویس‌ساز) | همهٔ کاربرانِ دارای گرنت آن سرویس | به `SKILL.md` سینک‌شدهٔ سرویس الحاق می‌شود → فقط وقتی سرویس استفاده می‌شود بار می‌شود (skill lazy است) |
| **`user_service`** | ادمین (پنل سرویس‌ها / دستیار سرویس‌ساز)؛ کاربر فقط از راه چت («یادت باشه … برای سرویس X») | همان کاربر، فقط هنگام استفاده از همان سرویس | همان‌جا، زیر بخش «قوانین/دانش شخصی این کاربر» |
| **`user`** | خودِ کاربر (صفحهٔ «حافظه و قوانین من» یا «یادت باشه» در چت)، ادمین (دربارهٔ او؛ برای کاربر فقط‌خواندنی)، **یادگیری خودکار** | همان کاربر در همهٔ گفتگوها (چت وب + `/v1` API) | `--append-system-prompt` هر نوبت: قوانین همیشه inline؛ دانش inline تا سقف بودجه، بیش از آن → فایل `.coolade/knowledge/user.md` + فهرست عناوین در پرامپت |
| **`team`** | ادمین، یا **یادگیری تیمی** خودکار | همهٔ اعضای تیم | مثل `user`؛ فایل `.coolade/knowledge/team-<slug>.md` |

**اصل توکن‌اقتصادی:** قوانین کوتاه‌اند و باید در همهٔ پاسخ‌ها باشند → همیشه در system prompt. دانش می‌تواند بزرگ شود → تا `KNOWLEDGE_INLINE_MAX_CHARS` (پیش‌فرض ۶۰۰۰) inline است، بعد از آن فقط فهرست عناوین در پرامپت می‌ماند و دستیار وقتی موضوع مربوط شد فایل را با `Read` می‌خواند. سرویس‌ها اصلاً هزینهٔ ثابت ندارند چون در skill‌اند.

**تصمیم مالک محصول (2026-09-10):** کاربر فقط **حافظه و قوانین خودش** (scope `user`) را می‌بیند و ویرایش می‌کند — صفحهٔ «حافظه و قوانین من» + «یادت باشه» در چت. همهٔ دامنه‌های دیگر (سرویس، کاربر×سرویس، تیم) و سوئیچ‌های یادگیری **فقط سمت ادمین** مدیریت می‌شوند. ادمین همهٔ قوانین/دانشِ هر کاربر را می‌بیند و در صورت نیاز می‌تواند گفتگوهای کاربر را بخواند (هر خواندن در `audit_log` ثبت می‌شود: `knowledge.read_conversation(s)`).

**اصل امنیتی (بدون تغییر):** دانش فقط *کیفیت پاسخ* را شکل می‌دهد؛ مرز دسترسی همان گرنت/عضویت/اکانت فقط‌خواندنی است (SERVICES-V2 DS4). یک قانون هرگز دسترسی نمی‌دهد یا نمی‌گیرد.

## ۲. حافظهٔ شخصی («یادت باشه») — نسخهٔ ۲

اسکیل `coolade-memory` (v2، برای همهٔ کاربران) دیگر `CLAUDE.md` را دست نمی‌زند؛ به سرور MCP رزروشدهٔ **`_me`** وصل است (`mcp___me__remember / update_memory / forget / list_memory`) که فقط روی سطرهای همان کاربر (scope `user` و `user_service`) کار می‌کند. نتیجه: چیزی که کاربر در چت می‌گوید «یادت باشه»، در صفحهٔ «حافظه و قوانین من» (و پنل ادمین) دیده، ویرایش و حذف می‌شود و برعکس. `CLAUDE.md` قدیمی همچنان توسط CLI بار می‌شود (سازگاری)؛ اسکیل به دستیار می‌گوید مورد جدید آنجا ننویسد و در صورت درخواست کاربر مهاجرت دهد.

## ۳. یادگیری از چت هر فرد

`app/services/learning.py` + job زمان‌بندی‌شده (`chat_learning`, هر `LEARNING_INTERVAL_MINUTES`=۱۵ دقیقه):

1. کاندیدا: گفتگوهای حذف‌نشده که ≥ `LEARNING_IDLE_MINUTES` (۱۰) ساکت‌اند، ≥ `LEARNING_MIN_NEW_USER_MESSAGES` (۲) پیام کاربرِ جدید بعد از cursor دارند، و کاربرشان `learning_enabled` است. حداکثر `LEARNING_MAX_CONVERSATIONS_PER_RUN` (۶) در هر اجرا.
2. برای هر گفتگو **یک** نوبت one-shot با thinking خاموش و مدل استخراج (پیش‌فرض ارزان‌ترین مدل فعال؛ ادمین می‌تواند پین کند): متن پیام‌های جدید + دانش موجود کاربر → آرایهٔ JSON از `{action: add|update, id, kind, title, content}`.
3. ثبت به‌عنوان `source=learned` در scope `user`؛ `update` فقط روی سطرهای learned مجاز است (نوشتهٔ دست انسان هرگز خودکار بازنویسی نمی‌شود). سقف `LEARNING_MAX_ENTRIES_PER_USER` (۸۰).
4. cursor (`learned_through_message_id`) بعد از parse موفق جلو می‌رود (حتی وقتی چیزی یاد نگرفته) — هر پیام فقط یک‌بار خوانده می‌شود؛ خطای CLI cursor را جلو نمی‌برد (تلاش مجدد در اجرای بعد).
5. مصرف در `usage_ledger` با `surface=learning` به نام کاربر ثبت می‌شود (شفاف؛ quota-gated نیست).
6. کنترل (فقط ادمین): سوئیچ کلی، سوئیچ per-user (تب کاربران)، انتخاب مدل، «اجرای دستی الان» و آخرین اجرا در «دانش و یادگیری».

پرامپت استخراج صراحت دارد که متن گفتگو *داده* است نه دستور (RS1)، و موارد موقتی/حساس (رمز، شماره کارت، سلامت، افراد ثالث) را استخراج نکند.

### ۳ب. یادگیری تیمی

`learning.run_team_once` + job `team_learning` (هر `TEAM_LEARNING_INTERVAL_HOURS`=۶ ساعت): برای هر تیم، پیام‌های جدید همهٔ اعضا (در همهٔ گفتگوهایشان، `id > teams.learned_through_message_id`، تا ۶۰ پیام در هر اجرا) در **یک** نوبت استخراج خلاصه می‌شود؛ فقط دانش **مشترک تیم** (اصطلاحات، فرایندها، سیستم‌ها، قواعد گزارش‌دهی) در scope `team` با `source=learned` ذخیره می‌شود و از نوبت بعد در system prompt همهٔ اعضا می‌آید. ترجیح‌های فردی و دادهٔ حساس استخراج نمی‌شود. حداقل `TEAM_LEARNING_MIN_NEW_MESSAGES`=۸ پیام کاربرِ جدید؛ سقف `TEAM_LEARNING_MAX_ENTRIES`=۸۰ مورد در هر تیم. اجرا به نام اولین ادمین فعال (workspace و لجر او، `surface=learning`). مهاجرت `0011_team_learning`.

## ۴. دیتاست برای «سیستم سازمانی»

`GET /api/admin/knowledge/export/conversations.jsonl?since=&until=&user_id=&min_messages=` — هر خط یک گفتگو:
`{"conversation_id","user_id","username","model","created_at","messages":[{"role":"user|assistant","content"}]}` (فقط پیام‌های complete و غیرخالی).
`GET /api/admin/knowledge/export/entries.jsonl` — کل پایگاه دانش با username/service_slug/team_slug.
هر export در `audit_log` ثبت می‌شود (`knowledge.export_*`؛ چه کسی، چه فیلتری، چند سطر) — این‌ها گفتگوهای افراد است. گام بعدیِ پیشنهادی (ساخته نشده): برچسب کیفیت روی پاسخ‌ها (👍/👎) برای فیلتر دیتاست پیش از آموزش.

## ۵. سطح API

| مسیر | نقش | توضیح |
|---|---|---|
| `GET/POST /api/knowledge/me` · `PATCH/DELETE /api/knowledge/entries/{id}` | کاربر | فقط scope `user` خودش؛ سطرهای ادمین‌نوشته `admin_locked` → ۴۰۳ |
| `GET /api/admin/knowledge/users/{uid}/conversations` · `GET …/conversations/{cid}` | ادمین | خواندن گفتگوهای کاربر — audited |
| `GET/POST /api/admin/knowledge/services/{id}` `…/services/{id}/users/{uid}` `…/users/{uid}` `…/teams/{tid}` | ادمین | چهار دامنه |
| `PATCH/DELETE /api/admin/knowledge/entries/{id}` | ادمین | همه |
| `GET /api/admin/knowledge/stats` · `GET/PUT …/learning` (شامل `team_enabled`) · `POST …/learning/run` (کاربران + تیم‌ها) | ادمین | |
| `PUT /api/admin/knowledge/users/{uid}/learning` | ادمین | خاموش/روشن‌کردن یادگیری از چت یک کاربر |
| `GET /api/admin/knowledge/export/{conversations,entries}.jsonl` | ادمین | §۴ |
| MCP `_me` (همهٔ کاربران) | دستیار | `remember / update_memory / forget / list_memory` |
| MCP `_admin` (افزوده) | دستیار سرویس‌ساز | `list_knowledge / add_knowledge / update_knowledge / delete_knowledge` |


## ۶. UI

- **کاربر:** `/knowledge` «حافظه و قوانین من» — فقط scope `user` خودش (شامل موارد یادگرفته‌شده؛ موارد ادمین فقط‌خواندنی).
- **ادمین:** `/admin/knowledge` «دانش و یادگیری» — آمار پایگاه دانش؛ تنظیمات یادگیری فردی و تیمی + اجرای دستی؛ خروجی دیتاست؛ تب‌های کاربران (سوئیچ یادگیری هر کاربر + فهرست/خواندن گفتگوهای او)/تیم‌ها/سرویس‌ها. در `/admin/services` هر سرویس آیکن «دانش و قوانین سرویس» دارد (scope `service` + انتخاب کاربر برای `user_service`).
- کامپوننت واحد `KnowledgeEntriesEditor` برای همهٔ دامنه‌ها؛ فقط `api` عوض می‌شود.

## ۷. پیاده‌سازی (فایل‌ها)

| فایل | چه می‌کند |
|---|---|
| `backend/alembic/versions/0010_knowledge.py`, `app/models.py` | اسکیما + enumها |
| `app/services/knowledge.py` | کوئری‌ها، رندر، `compile_turn_context` (پک هر نوبت + spill به فایل)، `render_service_addendum`/`apply_addendum` (الحاق به SKILL.md)، `service_fingerprint` |
| `app/cli_runner.py` | `_knowledge_pack` → `--append-system-prompt` (چت وب و one-shot) |
| `app/services/service_sync.py` | marker = `ver:fingerprint`؛ الحاق دانش به اسکیل؛ SKILL.md حداقلی برای سرویس بدون اسکیل؛ سرور `_me` برای همه |
| `app/services/me_tools.py`, `app/routers/mcp_gateway.py` | سرور `_me`؛ حلقهٔ مشترک `_handle_reserved` برای `_admin`/`_me` |
| `app/services/service_admin_tools.py` | ابزارهای دانش برای دستیار سرویس‌ساز |
| `app/services/learning.py`, `app/scheduler.py` | job یادگیری |
| `app/routers/knowledge.py`, `app/routers/admin_knowledge.py` | API کاربر (فقط حافظهٔ خودش) / ادمین |
| `app/assets/skills/coolade-memory/SKILL.md` | v2 (DB-backed) |
| `frontend/src/components/knowledge/KnowledgeEntriesEditor.tsx`, `pages/KnowledgePage.tsx`, `pages/admin/AdminKnowledgePage.tsx`, `pages/admin/AdminServicesPage.tsx` | UI |

## ۸. تنظیمات (env)

`KNOWLEDGE_INLINE_MAX_CHARS=6000` · `LEARNING_ENABLED=1` (قابل override از پنل ادمین) · `LEARNING_INTERVAL_MINUTES=15` · `LEARNING_IDLE_MINUTES=10` · `LEARNING_MIN_NEW_USER_MESSAGES=2` · `LEARNING_MAX_CONVERSATIONS_PER_RUN=6` · `LEARNING_MAX_ENTRIES_PER_USER=80` · `LEARNING_MODEL_KEY=` (خالی = ارزان‌ترین) · `TEAM_LEARNING_ENABLED=1` · `TEAM_LEARNING_INTERVAL_HOURS=6` · `TEAM_LEARNING_MIN_NEW_MESSAGES=8` · `TEAM_LEARNING_MAX_ENTRIES=80`

## ۹. معیار پذیرش (AC-KN)

- قانونی در scope `user` → در نوبت بعدیِ *گفتگوی جدید* همان کاربر رعایت می‌شود؛ برای کاربر دیگر اثری ندارد.
- قانون `team` → برای عضو اعمال، برای غیرعضو نه؛ حذف عضویت = از نوبت بعد اثر ندارد.
- قانون `service` → در `<ws>/.claude/skills/coolade-svc-<slug>/SKILL.md` کاربرِ دارای گرنت ظاهر می‌شود (بعد از مارکر `<!-- coolade:knowledge -->`)؛ کاربر بدون گرنت هیچ ردی ندارد.
- «یادت باشه X» در چت → سطر `manual` در «حافظه و قوانین من» و پنل ادمین؛ حذف → در چت بعدی فراموش شده.
- خواندن گفتگوی کاربر توسط ادمین بدون سطر `audit_log` انجام نمی‌شود.
- یادگیری تیمی: بعد از ≥۸ پیام جدید اعضای یک تیم، اجرای دستی → سطرهای `learned` در scope `team` و cursor تیم جلو رفته؛ از نوبت بعد در پک همهٔ اعضا.
- بعد از یک گفتگوی ≥۲ پیامیِ ۱۰ دقیقه ساکت، اجرای دستی یادگیری → سطرهای `learned` (یا هیچ، اگر چیزی پایدار نبود) و cursor جلو رفته؛ اجرای دوم همان پیام‌ها را دوباره نمی‌خواند.
- کاربر با `learning_enabled=false` هرگز کاندیدا نمی‌شود.
- export بدون سطر `audit_log` انجام نمی‌شود.
