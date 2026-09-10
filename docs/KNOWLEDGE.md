# ضمیمهٔ ۷ — لایهٔ دانش (Knowledge Layer): قوانین، دانش، حافظه، یادگیری از چت

| | |
|---|---|
| **محصول** | EcoCode Studio (PRD: `docs/PRD-V2.md` · TECH: `docs/TECH-V2.md` · سرویس‌ها: `docs/SERVICES-V2.md`) |
| **نسخهٔ ضمیمه** | 1.0 — as-built |
| **تاریخ** | 2026-09-10 |
| **مالک محصول** | Amin |
| **مهاجرت** | `0010_knowledge` — جدول `knowledge_entries`، ستون `users.learning_enabled`، ستون `conversations.learned_through_message_id` |

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
| **`user_service`** | خودِ کاربر («دانش من» یا «یادت باشه … برای سرویس X») یا ادمین | همان کاربر، فقط هنگام استفاده از همان سرویس | همان‌جا، زیر بخش «قوانین/دانش شخصی این کاربر» |
| **`user`** | خودِ کاربر، ادمین (دربارهٔ او)، یا **یادگیری خودکار** | همان کاربر در همهٔ گفتگوها (چت وب + `/v1` API) | `--append-system-prompt` هر نوبت: قوانین همیشه inline؛ دانش inline تا سقف بودجه، بیش از آن → فایل `.ecocode/knowledge/user.md` + فهرست عناوین در پرامپت |
| **`team`** | هر عضو تیم یا ادمین | همهٔ اعضای تیم | مثل `user`؛ فایل `.ecocode/knowledge/team-<slug>.md` |

**اصل توکن‌اقتصادی:** قوانین کوتاه‌اند و باید در همهٔ پاسخ‌ها باشند → همیشه در system prompt. دانش می‌تواند بزرگ شود → تا `KNOWLEDGE_INLINE_MAX_CHARS` (پیش‌فرض ۶۰۰۰) inline است، بعد از آن فقط فهرست عناوین در پرامپت می‌ماند و دستیار وقتی موضوع مربوط شد فایل را با `Read` می‌خواند. سرویس‌ها اصلاً هزینهٔ ثابت ندارند چون در skill‌اند.

**اصل امنیتی (بدون تغییر):** دانش فقط *کیفیت پاسخ* را شکل می‌دهد؛ مرز دسترسی همان گرنت/عضویت/اکانت فقط‌خواندنی است (SERVICES-V2 DS4). یک قانون هرگز دسترسی نمی‌دهد یا نمی‌گیرد.

## ۲. حافظهٔ شخصی («یادت باشه») — نسخهٔ ۲

اسکیل `eco-memory` (v2، برای همهٔ کاربران) دیگر `CLAUDE.md` را دست نمی‌زند؛ به سرور MCP رزروشدهٔ **`_me`** وصل است (`mcp___me__remember / update_memory / forget / list_memory`) که فقط روی سطرهای همان کاربر (scope `user` و `user_service`) کار می‌کند. نتیجه: چیزی که کاربر در چت می‌گوید «یادت باشه»، در صفحهٔ «دانش من» دیده، ویرایش و حذف می‌شود و برعکس. `CLAUDE.md` قدیمی همچنان توسط CLI بار می‌شود (سازگاری)؛ اسکیل به دستیار می‌گوید مورد جدید آنجا ننویسد و در صورت درخواست کاربر مهاجرت دهد.

## ۳. یادگیری از چت هر فرد

`app/services/learning.py` + job زمان‌بندی‌شده (`chat_learning`, هر `LEARNING_INTERVAL_MINUTES`=۱۵ دقیقه):

1. کاندیدا: گفتگوهای حذف‌نشده که ≥ `LEARNING_IDLE_MINUTES` (۱۰) ساکت‌اند، ≥ `LEARNING_MIN_NEW_USER_MESSAGES` (۲) پیام کاربرِ جدید بعد از cursor دارند، و کاربرشان `learning_enabled` است. حداکثر `LEARNING_MAX_CONVERSATIONS_PER_RUN` (۶) در هر اجرا.
2. برای هر گفتگو **یک** نوبت one-shot با thinking خاموش و مدل استخراج (پیش‌فرض ارزان‌ترین مدل فعال؛ ادمین می‌تواند پین کند): متن پیام‌های جدید + دانش موجود کاربر → آرایهٔ JSON از `{action: add|update, id, kind, title, content}`.
3. ثبت به‌عنوان `source=learned` در scope `user`؛ `update` فقط روی سطرهای learned مجاز است (نوشتهٔ دست انسان هرگز خودکار بازنویسی نمی‌شود). سقف `LEARNING_MAX_ENTRIES_PER_USER` (۸۰).
4. cursor (`learned_through_message_id`) بعد از parse موفق جلو می‌رود (حتی وقتی چیزی یاد نگرفته) — هر پیام فقط یک‌بار خوانده می‌شود؛ خطای CLI cursor را جلو نمی‌برد (تلاش مجدد در اجرای بعد).
5. مصرف در `usage_ledger` با `surface=learning` به نام کاربر ثبت می‌شود (شفاف؛ quota-gated نیست).
6. کنترل: کاربر در «دانش من» سوئیچ خاموش/روشن دارد؛ ادمین در «دانش و یادگیری» سوئیچ کلی، انتخاب مدل، «اجرای دستی الان» و آخرین اجرا را دارد.

پرامپت استخراج صراحت دارد که متن گفتگو *داده* است نه دستور (RS1)، و موارد موقتی/حساس (رمز، شماره کارت، سلامت، افراد ثالث) را استخراج نکند.

## ۴. دیتاست برای «سیستم سازمانی»

`GET /api/admin/knowledge/export/conversations.jsonl?since=&until=&user_id=&min_messages=` — هر خط یک گفتگو:
`{"conversation_id","user_id","username","model","created_at","messages":[{"role":"user|assistant","content"}]}` (فقط پیام‌های complete و غیرخالی).
`GET /api/admin/knowledge/export/entries.jsonl` — کل پایگاه دانش با username/service_slug/team_slug.
هر export در `audit_log` ثبت می‌شود (`knowledge.export_*`؛ چه کسی، چه فیلتری، چند سطر) — این‌ها گفتگوهای افراد است. گام بعدیِ پیشنهادی (ساخته نشده): برچسب کیفیت روی پاسخ‌ها (👍/👎) برای فیلتر دیتاست پیش از آموزش.

## ۵. سطح API

| مسیر | نقش | توضیح |
|---|---|---|
| `GET/POST /api/knowledge/me` | کاربر | scope `user` خودش |
| `GET /api/knowledge/me/services` | کاربر | سرویس‌های گرنت‌شده + شمار یادداشت‌ها |
| `GET/POST /api/knowledge/me/services/{slug}` | کاربر | scope `user_service` (۴۰۴ اگر گرنت ندارد) |
| `GET/POST /api/knowledge/teams/{team_id}` | عضو | scope `team` (۴۰۴ برای غیرعضو) |
| `PATCH/DELETE /api/knowledge/entries/{id}` | کاربر | مالکیت: سطرهای خودش به‌جز سطرهایی که ادمین دربارهٔ او نوشته (`admin_locked` → ۴۰۳)؛ سطر تیم برای اعضا |
| `GET/PUT /api/knowledge/me/learning` | کاربر | opt-out یادگیری |
| `GET/POST /api/admin/knowledge/services/{id}` `…/services/{id}/users/{uid}` `…/users/{uid}` `…/teams/{tid}` | ادمین | چهار دامنه |
| `PATCH/DELETE /api/admin/knowledge/entries/{id}` | ادمین | همه |
| `GET /api/admin/knowledge/stats` · `GET/PUT …/learning` · `POST …/learning/run` | ادمین | |
| `GET /api/admin/knowledge/export/{conversations,entries}.jsonl` | ادمین | §۴ |
| MCP `_me` (همهٔ کاربران) | دستیار | `remember / update_memory / forget / list_memory` |
| MCP `_admin` (افزوده) | دستیار سرویس‌ساز | `list_knowledge / add_knowledge / update_knowledge / delete_knowledge` |

`GET /api/auth/me` فیلد `learning_enabled` گرفت.

## ۶. UI

- **کاربر:** `/knowledge` «دانش من» — سوئیچ یادگیری؛ تب‌های «حافظه و قوانین من» (شامل برچسب «یادگرفته‌شده»)، «سرویس‌های من» (یادداشت per-service)، «تیم‌ها».
- **ادمین:** `/admin/knowledge` «دانش و یادگیری» — آمار پایگاه دانش؛ تنظیمات یادگیری + اجرای دستی؛ خروجی دیتاست؛ تب‌های کاربران/تیم‌ها/سرویس‌ها. در `/admin/services` هر سرویس آیکن «دانش و قوانین سرویس» دارد (scope `service` + انتخاب کاربر برای `user_service`).
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
| `app/routers/knowledge.py`, `app/routers/admin_knowledge.py` | API |
| `app/assets/skills/eco-memory/SKILL.md` | v2 (DB-backed) |
| `frontend/src/components/knowledge/KnowledgeEntriesEditor.tsx`, `pages/KnowledgePage.tsx`, `pages/admin/AdminKnowledgePage.tsx`, `pages/admin/AdminServicesPage.tsx` | UI |

## ۸. تنظیمات (env)

`KNOWLEDGE_INLINE_MAX_CHARS=6000` · `LEARNING_ENABLED=1` (قابل override از پنل ادمین) · `LEARNING_INTERVAL_MINUTES=15` · `LEARNING_IDLE_MINUTES=10` · `LEARNING_MIN_NEW_USER_MESSAGES=2` · `LEARNING_MAX_CONVERSATIONS_PER_RUN=6` · `LEARNING_MAX_ENTRIES_PER_USER=80` · `LEARNING_MODEL_KEY=` (خالی = ارزان‌ترین)

## ۹. معیار پذیرش (AC-KN)

- قانونی در scope `user` → در نوبت بعدیِ *گفتگوی جدید* همان کاربر رعایت می‌شود؛ برای کاربر دیگر اثری ندارد.
- قانون `team` → برای عضو اعمال، برای غیرعضو نه؛ حذف عضویت = از نوبت بعد اثر ندارد.
- قانون `service` → در `<ws>/.claude/skills/eco-svc-<slug>/SKILL.md` کاربرِ دارای گرنت ظاهر می‌شود (بعد از مارکر `<!-- ecocode:knowledge -->`)؛ کاربر بدون گرنت هیچ ردی ندارد.
- «یادت باشه X» در چت → سطر `manual` در «دانش من»؛ حذف از UI → در چت بعدی فراموش شده.
- بعد از یک گفتگوی ≥۲ پیامیِ ۱۰ دقیقه ساکت، اجرای دستی یادگیری → سطرهای `learned` (یا هیچ، اگر چیزی پایدار نبود) و cursor جلو رفته؛ اجرای دوم همان پیام‌ها را دوباره نمی‌خواند.
- کاربر با `learning_enabled=false` هرگز کاندیدا نمی‌شود.
- export بدون سطر `audit_log` انجام نمی‌شود.
