# سند فنی (TECH) — EcoCode Studio v2

| | |
|---|---|
| **محصول** | EcoCode Studio (PRD: `docs/PRD-V2.md` v2.0) |
| **نسخه سند** | 2.1 — ارجاع به ضمیمهٔ ۱ (سرویس‌های سازمانی) افزوده شد؛ پیشین 2.0: کامل (§۰ تا §۱۰ + ضمیمه)؛ سه spike بنیادی اجرا و بسته شد |
| **تاریخ** | 2026-08-29 |
| **مدیر فنی** | — |
| **مبنا** | PRD-V2 §۵ (الزامات W/I/C/G/V/A)، درس‌های L1–L5 |
| **نسبت با v1** | ریپوی جدید؛ اجزای اثبات‌شدهٔ v1 طبق PRD-V2 §۱۱ منتقل می‌شوند. این سند فقط دلتای معماری v2 را قطعی می‌کند؛ چیزهایی که از v1 عیناً می‌آیند در سند v1 (`docs/TECH.md`) مستندند و اینجا فقط ارجاع داده می‌شوند. |

> **ضمیمهٔ ۱ (2026-09-01):** طراحی فنی «سرویس‌های سازمانی» — MCP Gateway در بک‌اند، ایزولاسیون اعتبارنامه به قرینهٔ D2.4، enforcement دولایه، auth با همان `workspace_keys` §۴.۴ — در `docs/SERVICES-V2.md` بخش ب. پیاده‌سازی در فاز P5 (پس از P3)؛ دو spike پیش‌نیاز آن‌جا تعریف شده (SPK-SV1/SV2).

> **وضعیت:** پیش‌نویس کاملِ آمادهٔ بازبینی. تصمیم‌های بنیادی با سه spike واقعی اثبات شده‌اند: relay خام (§۰)، code-server زیر sub-path (§۳.۱۰)، و افزونهٔ Claude Code با auth از env (§۳.۱۱). §۴–§۷ روی همین بنا اسکیمای DB، relay تولیدی، compose/image و V6 را قطعی می‌کنند؛ §۸–§۱۰ تقسیم کار، امنیت و برنامهٔ تأیید. جزئیات ریزِ پیاده‌سازی (کد) هنگام ساخت نهایی می‌شود.

---

## ۰. نتیجهٔ Spike P0 — رفع بلاکر R5 (اجرا و تأیید شد، 2026-08-29)

### ۰.۱ سؤالی که باید جواب می‌گرفت

بزرگ‌ترین ریسک PRD-V2 (R5) و ریشهٔ درس L1 این بود: v1 هر درخواست passthrough را در یک نوبت تک‌شات CLI می‌پیچید، چون فرض شده بود توکن اشتراک بدون «بلوک هویت Claude Code» فقط haiku را می‌پذیرد و opus/sonnet را با ۴۲۹ رد می‌کند. اگر این فرض درست بود، مسیر CLI کاربر (PRD-V2 §A) غیرممکن می‌شد.

**فرضیهٔ v2:** اگر خودِ کلاینت Claude Code باشد، هویت لازم را **خودش** می‌فرستد؛ پس گیت‌وی فقط باید توکن آپ‌استریم را تزریق و بایت‌ها را **بدون دستکاری** relay کند — نه اینکه درخواست را بازسازی کند.

### ۰.۲ چطور تست شد

یک relay مینیمال stdlib-only (`spike/relay_spike.py`) که:
- روی `127.0.0.1:8899` گوش می‌دهد و `POST /v1/messages` را به `https://api.anthropic.com` می‌فرستد؛
- هدر `Authorization` کلاینت را دور می‌ریزد و توکن OAuth واقعی را می‌گذارد؛
- اگر `anthropic-beta` کلاینت شامل `oauth-2025-04-20` نبود، آن را اضافه می‌کند (بقیهٔ betaها دست‌نخورده)؛
- پاسخ را chunked و بدون تغییر برمی‌گرداند و ضمن عبور، usage و هدرهای ratelimit را از استریم برمی‌دارد.

relay داخل یک کانتینر با mount فقط‌خواندنیِ volume اعتبارنامهٔ بک‌اند (`ecocode_claude_state`) اجرا شد تا توکن معتبر از مرز کنترل‌شده خارج نشود. کلاینت = `claude` واقعی (نسخهٔ 2.1.246) با `ANTHROPIC_BASE_URL=http://127.0.0.1:8899` و یک کلید dummy (`eco-...`)، روی یک workspace واقعی با فایل nonce.

### ۰.۳ نتایج (ground truth)

| سناریو | مدل | نتیجه |
|---|---|---|
| Read تک‌ابزاره | sonnet | ✅ ۲۰۰، محتوای فایل دقیق برگشت |
| Read→Write چندمرحله‌ای | opus | ✅ ۲۰۰، فایل واقعاً نوشته شد |
| نوبت ساده بدون ابزار | haiku | ✅ ۲۰۰ |

**۶ درخواست آپ‌استریم، هر ۶ تا ۲۰۰ — صفر ۴۲۹ — روی هر سه مدل haiku/sonnet/opus.** فرض شکنندهٔ v1 **باطل شد**: مشکل «هویت» بود، نه «مدل»، و کلاینت Claude Code آن هویت را خودش حمل می‌کند.

سه یافتهٔ کلیدی که مستقیم وارد طراحی v2 می‌شوند:

1. **حلقهٔ ایجنتیک کامل round-trip می‌شود.** در یک تسک، تعداد پیام‌ها ۲→۵→۸ رشد کرد و بلوک‌های `tool_result` دست‌نخورده به آپ‌استریم برگشتند؛ `stop_reason` مسیر `tool_use → tool_use → end_turn` را طی کرد. این دقیقاً همان چیزی است که CLI-wrapping در v1 نمی‌توانست پل بزند. **درس L1 با داده اثبات شد.**

2. **کلاینت هویت خودش را می‌فرستد؛ گیت‌وی فقط یک تبدیل دارد.** هدرهای واقعی کلاینت:
   - `user-agent: claude-cli/2.1.246 (external, claude-desktop, agent-sdk/0.3.209)`
   - `anthropic-beta: claude-code-20250219,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,effort-2025-11-24`
   - `anthropic-version: 2023-06-01`، `x-app: cli`، ۲۰ ابزار native، system prompt کامل.

   نکته: چون کلاینت با کلید gateway (`eco-...`) فکر نمی‌کرد OAuth است، `oauth-2025-04-20` را **نفرستاد**؛ گیت‌وی باید این یک beta را (کنار توکن) اضافه کند. این تنها تبدیل لازم گیت‌وی است.

3. **usage و لیمیت اکانت هر دو از همین استریم قابل استخراج‌اند** (بدون side-channel جداگانهٔ v1):
   - usage کامل از رویدادهای SSE: `input_tokens`, `cache_creation_input_tokens` (در تست: ۳۳۹۵۹ — همان system prompt کش‌شدهٔ Claude Code)، `output_tokens`, `stop_reason`. برای ledger وزن‌دار کافی است. (نکته پیاده‌سازی: usage تو در تو است — parse با brace-matching، نه regex تخت.)
   - **نام واقعی هدرهای ratelimit** (که §۴.۵ سند v1 فقط حدس می‌زد): `anthropic-ratelimit-unified-5h-status/-reset/-utilization`، معادل‌های `-7d-`، و `-unified-overage-status`, `-fallback`, `-representative-claim`. این‌ها مستقیم طراحی V6 (نمایش لیمیت اکانت) را قطعی می‌کنند — دیگر حدس نمی‌زنیم.

### ۰.۴ تصمیم‌های قطعی‌شده از spike

- **D0.1** مسیر کلید API (PRD-V2 §A) = **relay خام HTTP**، نه CLI-wrapping. گیت‌وی درخواست را بازنمی‌سازد؛ فقط auth را جایگزین و `oauth-2025-04-20` را تضمین می‌کند و بایت‌ها را pass می‌کند.
- **D0.2** فعال‌سازی relay per-key صریح است (تصمیم ۲ PRD): کلید با فلگ «Claude Code» → relay خام. حدس‌زدن از شکل درخواست نداریم.
- **D0.3** منبع usage در این مسیر = رویدادهای SSE همان پاسخ (نه side-channel). ledger موجود v1 با ورودی usageِ استخراج‌شده تغذیه می‌شود.
- **D0.4** capture هدرهای `anthropic-ratelimit-unified-*` روی همین مسیر relay، منبعِ V6 است. مسیر چت وب (headless CLI) این هدرها را نمی‌دهد؛ همان degrade صادقانهٔ v1.
- **D0.5** relay تولیدی باید: streaming واقعی (fail-fast روی خطای پیش از اولین byte)، رعایت `HTTPS_PROXY` برای تانل خروجی، و timeout بلند (نوبت ایجنتیک طولانی) داشته باشد. اسکلت در `spike/relay_spike.py` است؛ نسخهٔ تولیدی داخل بک‌اند FastAPI با enforcement سهمیه/ACL **قبل** از relay و ثبت usage **بعد** از استریم.

### ۰.۵ مصنوعات

- `spike/relay_spike.py` — relay مرجع (stdlib، ~۱۸۰ خط، مستند).
- `spike/relay.log` — لاگ JSON خط‌به‌خط هر درخواست آپ‌استریم (متادیتا، status، usage، هدرهای ratelimit؛ بدون توکن).

---

## ۱. استک و معماری کلان v2

### ۱.۱ استک (بازاستفاده از v1 — درس L5)

استک v1 پایدار بود و بدون تغییر می‌ماند: **backend** FastAPI (async SQLAlchemy)، **DB** PostgreSQL + Alembic، **frontend** React + Vite (فارسی RTL)، **ingress** nginx، **اجرا** Docker Compose روی یک سرور لینوکسی. آپ‌استریم = سرویس ثالث Claude-سازگار از راه `UPSTREAM_BASE_URL`. زبان و ابزار عوض نمی‌شوند؛ فقط واحد محصول (Workspace) و دو قطعهٔ جدید (کانتینر ماندگار + relay خام) اضافه می‌شوند.

### ۱.۲ واحد اصلی = Workspace

برخلاف v1 که واحدش «سشن چت» بود و کانتینر throwaway per-message داشت (§۲.۰)، v2 حول **Workspace** ساخته می‌شود: کانتینر **ماندگار per (کاربر × ریپو)** (§۲) که هم code-server و هم `claude` را میزبانی می‌کند. دو گونه: **ریپویی** (dev، با IDE + افزونهٔ Claude Code) و **شخصی** (کاربر عمومی، چت ساده).

### ۱.۳ توپولوژی (به‌روزشده با تصمیم‌های §۲/§۳/D3.6)

```
                         ┌─────────────────── سرور EcoCode ───────────────────┐
[مرورگر dev] ──────► nginx ──/ide/<id>/──(auth_request→backend)──► کانتینر ورک‌اسپیس ecows_<id>
   IDE + افزونهٔ                │                                    ├─ code-server (webview چت = Claude Code)
   Claude Code                  │                                    └─ claude (bundled) ─┐
                                │                                                          │ ANTHROPIC_BASE_URL
[مرورگر عمومی] ──► nginx ──/api/──► backend ──► docker exec claude -p (چت ساده) ──────────┤ = relay بک‌اند
                                │                    │  (روی همان کانتینر ورک‌اسپیس)         │ + کلید gateway
[Claude Code روی ماشین dev] ──► nginx ──/v1/──► backend RAW RELAY ◄────────────────────────┘
                                │                    │  (auth/ACL/quota → تزریق توکن → عبور خام)
                                │                    ▼
                                │              آپ‌استریم Claude-سازگار (UPSTREAM_BASE_URL)
                                └── Postgres · نشست/کوکی · ledger · audit
   منبع حقیقت کد: GitLab سازمان (git.ecobin.ir) — clone/push با PAT خود کاربر (§۴/§۶)
```

نکتهٔ کلیدی توپولوژی: **همهٔ مسیرهای مدل به یک relay خام در بک‌اند ختم می‌شوند** (dev-CLI، افزونهٔ داخل IDE، و چت headless عمومی). توکن آپ‌استریم فقط در همین یک نقطه تزریق می‌شود و هرگز وارد کانتینر ورک‌اسپیس نمی‌شود (D2.4). این «یک primitive» همان درس L1/L2 است.

### ۱.۴ نقشهٔ سند

§۰ spike relay (قطعی) · §۲ چرخهٔ عمر کانتینر (قطعی) · §۳ گِیت code-server + افزونه (قطعی، با spikeهای §۳.۱۰/§۳.۱۱) · §۴ اسکیمای DB · §۵ relay تولیدی · §۶ compose + image واحد · §۷ V6 لیمیت اکانت · §۸ تقسیم کار و فازها · §۹ جمع‌بندی امنیت · §۱۰ برنامهٔ تأیید · ضمیمه.

## ۲. چرخهٔ عمر کانتینر ورک‌اسپیس ماندگار

### ۲.۰ تغییر بنیادی نسبت به v1

v1 (`sandbox_runner.py`) برای **هر نوبت** یک کانتینر throwaway می‌سازد: `docker run --rm -i`، workspace کاربر را روی `/work` بایند می‌کند، استریم می‌گیرد، و کانتینر با پایان نوبت نابود می‌شود. این برای «سشن کوتاه‌عمر per-message» عالی بود ولی برای مدل v2 (ورک‌اسپیس ماندگار per کاربر×ریپو با IDE زنده) کافی نیست.

سه چیز از v1 عیناً درست است و می‌ماند: **envelope ایزولاسیون** (شبکهٔ internal، egress allowlist، بدون mount اعتبارنامه/DB، `--read-only`، `--cap-drop ALL`، `--security-opt no-new-privileges`، سقف mem/cpu/pids)، **قرارداد stream-json→رویداد نرمال** (`_translate_event`)، و **انتقال ورودی‌های نامعتمد فقط از راه env** (بدون interpolation در شل). آنچه عوض می‌شود: از «کانتینر per-turn» به «کانتینر ماندگار per-workspace با ماشین حالت start/stop».

### ۲.۱ مدل: یک volume ماندگار + یک کانتینر workspace + یک image واحد

**تصمیم D2.1 — واحد فیزیکی ورک‌اسپیس = یک Docker volume ماندگار + یک کانتینرِ قابل stop/start، هر دو per (کاربر × ریپو).**

- **volume** (`ecows_<workspace_id>`) نگهدارندهٔ حقیقتِ روی دیسک است: clone ریپو، `node_modules`، کش build، برنچ کاری. **بقای ماندگاری از volume می‌آید، نه از زندهٔ‌بودن کانتینر** — پس idle-stop هیچ کار کاربر را از بین نمی‌برد.
- **کانتینر workspace** (`ecows_<workspace_id>`) از یک **image واحد** ساخته می‌شود که هم `code-server` و هم `claude-code` CLI (+ node + git + bash) را دارد. یعنی image فعلی `runner/` با پایهٔ code-server ادغام می‌شود (§۶).

**تصمیم D2.2 — IDE و ایجنت در «یک» کانتینر، نه دو تا.** پروسهٔ code-server به‌عنوان سرویس بلندعمر داخل کانتینر بالاست؛ هر نوبت ایجنت با `docker exec <container> claude -p …` **داخل همان کانتینر** اجرا می‌شود. دلیل: PRD §۳.۲ می‌خواهد IDE و ایجنت یک حقیقت را ببینند — نه فقط یک فایل‌سیستم، بلکه یک **محیط** (اگر کاربر در ترمینال IDE، `npm run dev` را بالا آورد یا ابزاری global نصب کرد، ایجنت هم همان را ببیند). volume مشترک فقط فایل‌ها را یکی می‌کند؛ پروسه‌های در حال اجرا و `$PATH` و ابزارهای نصب‌شده فقط وقتی یکی می‌شوند که کانتینر یکی باشد.

> **گزینهٔ رد شده (دو-کانتینری):** code-server بلندعمر + کانتینر ایجنت throwaway per-turn، هر دو mount کنندهٔ همان volume. مزیتش بهداشت توکن بهتر بود (توکن فقط لحظهٔ نوبت در env کانتینر throwaway)، ولی «دو محیط» می‌سازد و وعدهٔ محصول را می‌شکند. مشکل بهداشت توکن را در D2.4 با relay §۰ حل می‌کنیم، پس دلیلِ گزینهٔ دو-کانتینری از بین می‌رود. → **تک-کانتینری انتخاب شد.**

چون envelope هنگام `docker run` روی کانتینر workspace اعمال می‌شود، `docker exec` همان namespace شبکه/محدودیت‌ها/کاربر را به ارث می‌برد؛ پس exec کردن ایجنت به داخل، دقیقاً همان‌قدر امن است که نوبت throwaway v1 بود.

### ۲.۲ ماشین حالت چرخهٔ عمر

منبع حقیقتِ حالت = ردیف ورک‌اسپیس در DB بک‌اند؛ Docker فقط مکانیزم است. Docker هرگز مستقیم صدا زده نمی‌شود مگر از راه یک مدیر چرخهٔ عمر که ردیف DB را هم‌زمان به‌روز می‌کند.

```
                 create(repo, branch)
   [∅] ────────────────────────────────► [provisioning]
                                              │  volume create + docker run +
                                              │  git clone + (opsiyonel) نصب اولیه
                                              ▼
      resume/agent-turn/IDE-open        ┌─► [running] ──────┐
   [stopped] ◄───────────────────────────┤                  │ idle-timeout (reaper)
        │  ▲     docker start (ثانیه‌ها) └──────────────────►┤
        │  └──────────────────────────────────────────────  ▼
        │                                              [stopping] ─► docker stop ─► [stopped]
        │  retention TTL (پیش‌فرض ۳۰ روز) + دو اخطار + بدون برنچ push-نشده
        ▼
   [archived] ──── delete volume ────► [deleted]
        ▲                                   ▲
        └──── حذف دستی کاربر ───────────────┘  (با تأیید؛ برنچ push-نشده هشدار می‌دهد)
```

حالت‌ها: `provisioning` (اولین ساخت؛ کند)، `running` (کانتینر بالا؛ RAM مصرف می‌کند)، `stopped` (کانتینر خاموش؛ فقط دیسک)، `archived` (کاندید حذف؛ اخطار داده‌شده)، `deleted`. حالت گذرای `stopping` برای idempotency reaper.

### ۲.۳ عملیات‌ها و تجربهٔ cold-start در برابر warm-resume

| عملیات | مکانیزم | زمان تقریبی | تجربهٔ کاربر |
|---|---|---|---|
| **create** (اولین بار) | `docker volume create` → `docker run` (envelope) → `git clone` (shallow، با PAT کاربر) | ده‌ها ثانیه تا ~۱ دقیقه | صفحهٔ «در حال آماده‌سازی ورک‌اسپیس…» با گام‌ها (clone/نصب) |
| **resume** (از stopped) | `docker start` | ثانیه‌ها | اسپینر کوتاه؛ clone و نصب دوباره **انجام نمی‌شود** (روی volume است) |
| **stop** (idle یا دستی) | به‌روزرسانی last_activity → `docker stop` | ثانیه‌ها | شفاف؛ دفعهٔ بعد resume |
| **delete** | `docker rm` + `docker volume rm` | ثانیه‌ها | تأیید صریح؛ اگر برنچ push-نشده باشد اخطار قرمز |

نوبت ایجنت وقتی کانتینر `stopped` است: مدیر چرخهٔ عمر **auto-resume** می‌کند (start → exec → استریم)، سپس reaper بعداً دوباره stop می‌کند. این «بقای نوبت مستقل از مرورگر» v1 (Issue A) را حفظ می‌کند: نوبت پس‌زمینه می‌رسد → ensure-running → exec → persist.

### ۲.۴ ایزولاسیون توکن آپ‌استریم — اتحاد با relay §۰

**تصمیم D2.4 — توکن OAuth آپ‌استریم هرگز وارد کانتینر ورک‌اسپیس نمی‌شود.** این مهم‌ترین تفاوت امنیتی با v1 است. در v1 توکن واقعی در env کانتینر throwaway بود (قابل‌قبول چون عمرش یک نوبت بود). در کانتینر ماندگار، توکن در env برای کل عمر می‌ماند و یک prompt-injection در هر نوبتی می‌تواند `$ANTHROPIC_AUTH_TOKEN` را بخواند.

راه‌حل: ایجنت داخل ورک‌اسپیس دقیقاً همان کاری را می‌کند که Claude Code روی ماشین dev در مسیر §A می‌کند — به یک relay وصل می‌شود:
- `ANTHROPIC_BASE_URL` = endpoint relay بک‌اند (همان D0.1).
- `ANTHROPIC_AUTH_TOKEN` = یک **کلید gateway مخصوص همان ورک‌اسپیس** (نه توکن آپ‌استریم)، کوتاه‌عمر و قابل ابطال، که با هر resume می‌تواند چرخانده شود.
- بک‌اند در relay توکن واقعی OAuth را تزریق می‌کند؛ توکن هرگز از مرز بک‌اند خارج نمی‌شود.

پیامد امنیتی: بدترین حالتِ نشتِ کلید ورک‌اسپیس = سوزاندن سهمیهٔ خودِ همان کاربر (محدود، قابل‌ابطال) — نه لو رفتن اعتبارنامهٔ master سازمان. **این اکیداً از v1 بهتر است.** و یک primitive واحد (relay §۰) هر دو مسیر (CLI روی dev و ایجنت وب) را تغذیه می‌کند (درس L1/L2).

**egress allowlist ورک‌اسپیس‌ها بازتعریف می‌شود:** مقصدهای مجاز = host relay بک‌اند + `git.ecobin.ir` + منبع extension (open-vsx). دیگر `api.anthropic.com` **مستقیماً** از ورک‌اسپیس در دسترس نیست؛ فقط بک‌اند به آن می‌رسد. یعنی حتی سطح حملهٔ کمتر از v1.

> نکتهٔ توپولوژی برای §۶: relay بک‌اند باید از شبکهٔ internal ورک‌اسپیس‌ها قابل‌دسترس باشد. بک‌اند به آن شبکه هم وصل می‌شود، ولی چون ورک‌اسپیس فقط یک کلید gateway دارد نه نشست، همهٔ مسیرهای دیگر بک‌اند (admin/DB) پشت auth می‌مانند. ترجیح طراحی: relay روی یک listener/مسیر مجزا که فقط کلید gateway را می‌پذیرد.

### ۲.۵ تشخیص idle و reaper

**سیگنال فعالیت (`last_activity_at` در ردیف ورک‌اسپیس):**
1. شروع/پایان هر نوبت ایجنت.
2. heartbeat سبک از مرورگر **فقط وقتی تب IDE قابل‌مشاهده است** (`visibilitychange`)، هر چند دقیقه — تا تبِ بازِ بلااستفاده مانع idle-stop نشود و پینگ‌های خالص websocket به‌اشتباه «فعالیت» شمرده نشوند.

**reaper:** یک تسک پس‌زمینهٔ دوره‌ای (هر ~۱ دقیقه) ورک‌اسپیس‌های `running` با `now - last_activity_at > idle_timeout` را `docker stop` می‌کند و به `stopped` می‌برد. `idle_timeout` پیش‌فرض **۳۰ دقیقه**، قابل‌تنظیم ادمین (سراسری) و بعداً per-user (nice-to-have). نوبت ایجنتِ در حال اجرا هرگز نصفه kill نمی‌شود: reaper فقط وقتی هیچ نوبت فعالی نیست stop می‌کند.

### ۲.۶ سهمیهٔ دیسک per-user، پاک‌سازی self-service، و GC

مطابق PRD W4 و تصمیم ۳: سقف فضا **per-user** است (مجموع volumeهای ورک‌اسپیس + فایل‌های چت)، نه per-workspace.

- **اندازه‌گیری:** استفادهٔ دیسک هر volume به‌صورت دوره‌ای محاسبه و در ردیف ورک‌اسپیس کش می‌شود؛ مجموع per-user در برابر `user.disk_quota_bytes` سنجیده می‌شود.
- **enforcement:** عبور از سقف → مسدودکردن ساختِ ورک‌اسپیس/فایل جدید (نه قطع کار جاری) با پیام فارسی صریح: «فضای شما پر است — یک ورک‌اسپیس/گفتگوی قدیمی حذف کنید یا retention را کوتاه‌تر کنید.» مدل کاملاً **self-service** است؛ سیستم خودش چیزی حذف نمی‌کند مگر GC زیر.
- **GC ورک‌اسپیس‌های متروک:** ورک‌اسپیس `stopped` که بیش از `retention_days` (پیش‌فرض ۳۰، قابل‌تنظیم per-user) بی‌فعالیت مانده → دو اخطار (مثلاً ۷ روز و ۱ روز مانده) → `archived` → حذف volume.
- **محافظ سخت:** پیش از هر حذف (GC یا دستی)، وضعیت git داخل volume بررسی می‌شود؛ اگر **برنچ/کامیت push-نشده** وجود دارد، حذف خودکار **انجام نمی‌شود** و فقط به کاربر هشدار می‌رود. حذف دستی در این حالت تأیید دوم می‌خواهد. (PRD W4: «برنچ‌های push نشده هرگز بی‌اخطار حذف نمی‌شوند».)

### ۲.۷ هم‌زمانی و ظرفیت

سقف روی کانتینرهای **`running` هم‌زمان** است (کرانِ RAM)، نه روی تعداد کل ورک‌اسپیس‌ها (ورک‌اسپیس `stopped` تقریباً فقط دیسک می‌گیرد). `max_running_workspaces` سراسری و قابل‌تنظیم؛ پیش‌فرض متناسب با «زیر ۱۰ dev» (مثلاً ۴). درخواست resume/create بالاتر از ظرفیت → یا صف کوتاه یا پیام «ظرفیت پر است، بعداً تلاش کنید». این مکملِ سقف‌های سهمیهٔ توکن (V3) است، نه جایگزین آن‌ها. semaphore هم‌زمانیِ نوبتِ ایجنت (`sandbox_max_concurrency` v1) جداگانه باقی می‌ماند.

### ۲.۸ reconciliation پس از restart بک‌اند

هم‌ارز «ردیف‌های streaming → failed» v1. در استارتاپ، مدیر چرخهٔ عمر برای هر ردیف `running`/`provisioning`/`stopping` وضعیت واقعی Docker را می‌پرسد و همگام می‌کند: کانتینر بالا → `running`؛ کانتینر نیست/خاموش → `stopped`؛ نوبت ایجنتِ نیمه‌کاره → `failed` (با مسیر retry v1). هیچ حالت DB نباید با واقعیت Docker واگرا بماند.

### ۲.۹ ورک‌اسپیس شخصی (بدون ریپو)

کاربر عمومی (PRD W5) از **همین ماشین حالت** استفاده می‌کند، فقط بدون مرحلهٔ clone و بدون PAT گیت‌لب: create = volume + `docker run` روی همان image؛ egress حداقلی (فقط relay بک‌اند)؛ رابطش چت ساده به‌جای IDE. یک مکانیزم، دو پوسته (درس L2/L3) — نه کد جدا برای «چت» و «کد».

### ۲.۱۰ ردپای اسکیمای DB (جزئیات کامل در §۴)

جدول جدید `workspaces` (خلاصه): `id`, `user_id`, `kind` (`repo`|`personal`), `repo_url`, `base_branch`, `work_branch`, `container_name`, `volume_name`, `status`, `created_at`, `last_activity_at`, `disk_bytes`, `retention_days`. ستون جدید `users.disk_quota_bytes`. جزئیات و revision Alembic پایه در §۴.

### ۲.۱۱ جمع‌بندی تصمیم‌های §۲

- **D2.1** واحد = volume ماندگار + کانتینر قابل stop/start، per (کاربر×ریپو)؛ ماندگاری از volume می‌آید.
- **D2.2** IDE و ایجنت در یک کانتینر؛ ایجنت با `docker exec`. (دو-کانتینری رد شد.)
- **D2.3** image واحد = code-server ⊕ claude-code ⊕ node/git/bash.
- **D2.4** توکن آپ‌استریم هرگز وارد ورک‌اسپیس نمی‌شود؛ ایجنت از relay §۰ با کلید gateway کوتاه‌عمر عبور می‌کند؛ egress ورک‌اسپیس = relay بک‌اند + `git.ecobin.ir` + open-vsx.
- **D2.5** idle-stop با reaper (پیش‌فرض ۳۰ دقیقه)؛ سیگنال = نوبت ایجنت + heartbeat تبِ مرئی.
- **D2.6** سهمیهٔ دیسک per-user + پاک‌سازی self-service + GC ۳۰روزه با محافظِ برنچ push-نشده.
- **D2.7** سقف روی کانتینرهای running هم‌زمان (پیش‌فرض ~۴).
- **D2.8** reconciliation حالت DB↔Docker در استارتاپ.
- **D2.9** ورک‌اسپیس شخصی = همان ماشین حالت بدون clone/PAT.

---

## ۳. گِیت کردن code-server با نشست EcoCode (حل R4)

### ۳.۰ وضعیت v1 و شکاف امنیتی

v1 یک **instance مشترکِ تک** code-server روی پورت اختصاصی ۸۰۹۰ دارد؛ auth = یک `PASSWORD` واحد؛ و mount کردن `users_data:/data/users` یعنی هر کسی که پسورد را دارد **workspace همهٔ کاربران** را می‌بیند. برای v2 (که هر کاربر باید فقط ورک‌اسپیس خودش را ببیند، بدون پسورد جدا) این کافی نیست. خوشبختانه D2.2 مسئله را ساده کرد: **هر ورک‌اسپیس کانتینر خودش را دارد و code-server داخل همان کانتینر است** (`ecows_<id>:8080` روی شبکهٔ internal). پس §۳ فقط باید لایهٔ auth/پروکسی جلوی این instanceهای پویا را قطعی کند — نه ساختن per-user instance از صفر.

### ۳.۱ الزام و مدل تهدید

- **الزام (PRD I1):** فقط **مالکِ** ورک‌اسپیس به code-server آن دسترسی دارد؛ auth از **همان نشست EcoCode** می‌آید (کوکی session موجود v1)، **بدون پسورد جداگانه**.
- **تهدید:** کاربر A نباید بتواند code-server کاربر B را (حتی با دانستن `workspace_id`) باز کند؛ code-server نباید بدون احراز هویت مستقیم در دسترس باشد؛ کانتینرها پویا می‌آیند/می‌روند (start/stop از §۲).

### ۳.۲ تصمیم: `auth_request` nginx + upstream پویا + code-server بدون auth داخلی

**تصمیم D3.1 — الگوی احراز = nginx `auth_request` به یک endpoint داخلی بک‌اند که مالکیت را چک می‌کند؛ سپس پروکسی پویا به کانتینر همان ورک‌اسپیس.** code-server داخل کانتینر با `--auth none` اجرا می‌شود.

`--auth none` امن است چون سه شرط هم‌زمان برقرارند: (۱) code-server روی شبکهٔ internal است و هیچ پورتی publish نمی‌کند (فقط از داخل قابل‌دسترس)؛ (۲) nginx تنها ingress است و پیش از هر پروکسی، `auth_request` را اجرا می‌کند؛ (۳) هر ورک‌اسپیس یک code-server **جدا** دارد، پس مرز کانتینر خودش ایزولاسیون بین‌کاربری را تضمین می‌کند — کاربر A حتی نمی‌تواند به کانتینر B «آدرس بدهد» چون authz مالکیت `<id>` را رد می‌کند.

```
مرورگر ── GET /ide/<id>/... (کوکی session EcoCode، same-origin) ──► nginx
                                                                      │
                          auth_request ─► backend GET /internal/authz/workspace/<id>
                                            (کوکی forward می‌شود)
                                            چک: session معتبر؟ user == workspace.owner؟ status==running؟
                                            ◄─ 200 + هدر X-Ecocode-Upstream: ecows_<id>:8080
                                            ◄─ 401 (بدون session) | 403 (نه مالک) | 409 (stopped) | 404
                                                                      │ (روی 200)
                          proxy_pass http://$upstream (از هدر، با docker DNS resolve) ─► ecows_<id>:8080
```

### ۳.۳ مسیردهی: same-origin با پیشوند مسیر (چرا نه subdomain/port)

**تصمیم D3.2 — همان host و همان پورت (same-origin)، با پیشوند `/ide/<workspace_id>/`.**

دلیل تعیین‌کننده: **کوکی نشست.** کوکی session روی host اصلی EcoCode ست می‌شود. اگر IDE هم روی همان origin سرو شود، کوکی طبیعتاً همراه هر درخواست (از جمله handshake وب‌سوکت) می‌رود و `auth_request` کار می‌کند. جایگزین‌ها هر کدام هزینه دارند:
- **subdomain per-workspace** (`<id>.ide.ecocode`): نیازمند wildcard DNS + wildcard TLS (روی on-prem دردسر) و ست‌کردن دامنهٔ کوکی روی دامنهٔ والد؛ کنار گذاشته شد.
- **پورت per-workspace از یک pool:** مدیریت پورت و publish کردن پورت‌ها، سطح حمله و پیچیدگی compose را زیاد می‌کند؛ کنار گذاشته شد.

**آیتمِ تأیید — spike اجرا و بسته شد ✅ (2026-08-29، §۳.۱۰).** تنها ریسک باز §۳ (رفتار code-server زیر sub-path) با یک stack واقعی nginx+code-server تست شد و **کار می‌کند**؛ fallback subdomain+تیکت لازم نشد. جزئیات و شرط لازم پیاده‌سازی در §۳.۱۰.

### ۳.۴ قرارداد endpoint احراز بک‌اند

`GET /internal/authz/workspace/{id}` — فقط برای مصرف داخلی nginx (نه مسیر public؛ روی شبکهٔ داخلی و/یا با هدر اعتماد nginx):
- ورودی: کوکی‌های forwardشدهٔ مرورگر (شامل session).
- منطق: session را resolve کن → user؛ اگر session نامعتبر → **401**؛ اگر ورک‌اسپیس متعلق به این user نیست → **403**؛ اگر `status != running` → **409** (فرانت باید اول resume کند، §۳.۶)؛ اگر ورک‌اسپیس نیست → **404**.
- خروجی موفق: **200** + هدر `X-Ecocode-Upstream: ecows_<id>:8080`. nginx با `auth_request_set $upstream $upstream_http_x_ecocode_upstream;` آن را می‌گیرد و `proxy_pass http://$upstream;` (نامِ کانتینر با docker DNS در زمان درخواست resolve می‌شود — همان ترفند `resolver 127.0.0.11` v1، تا نبود کانتینر nginx را نشکند).

این endpoint سبک است (lookup نشست + یک چک مالکیتِ ایندکس‌دار)، ولی `auth_request` برای **هر** درخواست asset اجرا می‌شود؛ در مقیاس «زیر ۱۰ dev» ناچیز است. **بهینه‌سازی اختیاری (D3.5):** پس از اولین authz موفق، بک‌اند یک کوکی امضاشدهٔ کوتاه‌عمرِ scope‌شده به همان `<id>` (مثلاً ۵ دقیقه) ست کند؛ endpoint authz اگر آن کوکی معتبر بود بدون hit به DB سریع 200 برگرداند.

### ۳.۵ وب‌سوکت و ابطال نشست

`auth_request` روی **handshake** وب‌سوکت (درخواست HTTP اولیهٔ Upgrade) اجرا می‌شود، نه روی تک‌تک frameها. یعنی authz یک‌بار هنگام اتصال چک می‌شود و سپس سوکت باز می‌ماند. پیامد: اگر نشست کاربر **حین** یک سوکت باز ابطال شود، آن سوکت تا قطع‌شدن طبیعی زنده می‌ماند. در این مقیاس قابل‌قبول است؛ کاهش کامل (اختیاری): reaper نشست‌های ابطال‌شده، کانتینر مربوط را هم می‌تواند به‌زور قطع کند. map وب‌سوکت (`$connection_upgrade`) از v1 عیناً استفاده می‌شود.

### ۳.۶ resume در جریانِ باز کردن IDE

چون `auth_request` نمی‌تواند یک resume کندِ چندثانیه‌ای را trigger کند، جریان این‌طور است: فرانت پیش از بارگذاری IDE، وضعیت ورک‌اسپیس را می‌پرسد؛ اگر `stopped` بود، دکمهٔ «راه‌اندازی ورک‌اسپیس» → `POST /api/workspaces/{id}/resume` (که `docker start` می‌کند و منتظر آماده‌شدن code-server می‌ماند)، و پس از `running` شدن، iframe/صفحهٔ IDE بار می‌شود. authz روی مسیر `/ide/<id>/` آن‌گاه 200 می‌دهد. (اگر authz حین بارگذاری 409 دید، فرانت همین flow را نشان می‌دهد.)

### ۳.۷ چت dev = افزونهٔ رسمی Claude Code داخل code-server (بازطراحیِ درخواست کاربر)

**تصمیم D3.6 — برای ورک‌اسپیس ریپویی، «چت کنار IDE» یک UI جدا که ما بسازیم نیست؛ خودِ افزونهٔ رسمی `Anthropic.claude-code` داخل code-server است.** درخواست مالک محصول (2026-08-29): چتی که dev باهاش کد می‌زند باید همان تجربهٔ native خودِ Claude Code باشد، نه یک پنل جدا.

چرا این درست است (درس L3 — چیزِ موجود را دوباره نساز):
- تجربهٔ native: چت + دیدن فایل‌های باز + اعمال inline با diff review + ترمینال integrated، همه در ادیتور. این همان «یک محیط» است که D2.2 برایش تصمیم گرفتیم — حالا ایجنت واقعاً *داخل* ادیتور است، نه کنارش.
- ما هیچ چت‌ِ dev اختصاصی نمی‌سازیم/نگه نمی‌داریم. split-view قبلی (iframe + چت React) حذف می‌شود؛ صفحهٔ ورک‌اسپیس ریپویی فقط IDE را جاسازی می‌کند (same-origin `<iframe src="/ide/<id>/">`، بدون مشکل X-Frame/CSP).

شواهد feasibility (بررسی‌شده 2026-08-29):
- افزونهٔ رسمی `Anthropic.claude-code` (نسخهٔ 2.1.251، دستهٔ AI/Chat، engine `vscode ^1.94.0`) **روی open-vsx موجود است** — همان رجیستری‌ای که code-server از آن افزونه نصب می‌کند و از قبل در egress allowlist ماست (`open-vsx.org`). نصب = مسیر عادی افزونهٔ code-server (یا bake در image واحد D2.3).
- افزونه یک UI روی همان `claude` CLI است؛ و §۰ اثبات کرد این CLI از راه relay ما (با `ANTHROPIC_BASE_URL` + کلید gateway) کامل کار می‌کند. پس auth/quota/usage همان مسیر D2.4 را می‌روند و توکن آپ‌استریم هرگز وارد ورک‌اسپیس نمی‌شود.

**تفکیک persona (مهم):** این چتِ-داخل-IDE فقط برای **ورک‌اسپیس ریپویی (dev)** است. کاربر عمومی (ورک‌اسپیس شخصی W5) کل VS Code را نمی‌بیند؛ برای او همان **چت سادهٔ v1** (با picker سطح تفکر، تاریخچه، retry) می‌ماند که پشتش `claude -p` headless (C1/D2.2) اجرا می‌شود. پس دو پوسته روی یک CLI و یک relay (سازگار با §۲.۹): dev → افزونهٔ Claude Code؛ عمومی → چت سادهٔ ما.

**پیامد برای مدل اجرای ایجنت:** `claude` داخل کانتینر ورک‌اسپیس به دو شکل اجرا می‌شود، هر دو با auth از راه relay: (الف) تعاملی از افزونه (dev در IDE)؛ (ب) headless `claude -p` از بک‌اند برای چت وب/نوبت پس‌زمینه (عمومی، و هر اتوماسیون سمت سرور). قرارداد رویداد و ledger یکسان است.

**آیتم تأیید — spike اجرا و بسته شد ✅ (2026-08-29، §۳.۱۱).** افزونه با **env** احراز هویت می‌شود؛ login تعاملی لازم نیست؛ درخواستش از relay ما با ۲۰۰ عبور کرد. جزئیات و نکات build در §۳.۱۱.

### ۳.۸ چرا این اکیداً از v1 بهتر است

| جنبه | v1 | v2 (§۳) |
|---|---|---|
| احراز هویت | یک پسورد مشترک code-server | نشست EcoCode، بدون پسورد جدا |
| ایزولاسیون بین‌کاربری | هیچ — همه `/data/users` را می‌بینند | مرز کانتینر per-workspace + چک مالکیت authz |
| قابلیت ابطال | تعویض پسورد مشترک (همه را می‌اندازد) | ابطال نشست خود کاربر |
| مدل | نقض حریم خصوصی | فقط مالک، پویا، هم‌راستا با auth بقیهٔ محصول |

### ۳.۹ جمع‌بندی تصمیم‌های §۳

- **D3.1** الگو = nginx `auth_request` → `/internal/authz/workspace/{id}` + پروکسی پویا؛ code-server با `--auth none` پشت آن (امن به‌خاطر شبکهٔ internal + تک‌ingress بودن nginx + مرز کانتینر per-workspace).
- **D3.2** مسیردهی same-origin با پیشوند `/ide/<id>/` (به‌خاطر جریان طبیعی کوکی نشست)؛ subdomain/port رد شدند.
- **D3.3** قرارداد authz: 200+`X-Ecocode-Upstream` / 401 / 403 / 409(stopped) / 404؛ upstream پویا با docker DNS.
- **D3.4** resume در جریانِ باز کردن IDE از راه `POST /resume` پیش از بار کردن iframe.
- **D3.5** (اختیاری) کوکی authz کوتاه‌عمر برای کاهش hit هر-asset.
- **D3.6** چت dev = افزونهٔ رسمی `Anthropic.claude-code` داخل code-server (نه چت جدا)؛ عمومی = چت سادهٔ v1؛ هر دو روی یک CLI/relay. (§۳.۷)
- **آیتم تأیید base-path:** ✅ بسته شد (§۳.۱۰) — sub-path کار می‌کند؛ شرط لازم = `Host $http_host`.
- **آیتم تأیید افزونه:** ✅ بسته شد (§۳.۱۱) — افزونه با env بدون login از راه relay ما ۲۰۰ گرفت؛ build باید VSIX `linux-x64` را bake کند.

### ۳.۱۰ نتیجهٔ spike base-path (اجرا و تأیید شد، 2026-08-29)

**سؤال:** آیا VS Code workbench زیر پیشوند `/ide/<id>/` کامل و بدون خطای asset بار می‌شود، یا باید به fallback (subdomain+تیکت) برویم؟

**روش:** stack واقعی `codercom/code-server` + `nginx:alpine` (پروکسی روی `/ide/spike/`، strip پیشوند با trailing-slash)، بار شدن در مرورگر واقعی و بازرسی console + network. مصنوعات در `spike/ide-basepath/`.

**نتیجه: ✅ کار می‌کند.** workbench کامل رندر شد (Explorer با درخت فایل، تب Welcome، activity bar)؛ **صفر خطای console**؛ همهٔ asset‌ها زیر پیشوند ۲۰۰ دادند — استاتیک، فونت‌ها (`codicon.ttf`)، `webWorkerExtensionHostIframe.html`، و `vscode-remote-resource?path=...` (themeها از کانال remote extension host؛ یعنی وب‌سوکت هم زیر پیشوند سالم است).

**یافتهٔ کلیدی — تنها شرط لازم:** باید `Host` و `X-Forwarded-Host` را **با پورت** فوروارد کرد (`proxy_set_header Host $http_host;` نه `$host`). با `$host` بدونِ پورت، code-server ریدایرکت‌های مطلق را با پورت‌افتاده می‌سازد و در loop می‌افتد. با `$http_host`، code-server خودش `serverBasePath: "."` (نسبی) تولید می‌کند و همهٔ asset‌ها با `new URL('stable-<commit>/static', window.location)` نسبت به `/ide/<id>/` درست resolve می‌شوند — نیازی به هیچ فلگ base-path در code-server نیست.

**نکات برای پیاده‌سازی تولیدی:**
- گوتچای docker: bind-mount **تک‌فایلیِ** `nginx.conf` با تغییر inode (ادیتور) به‌روز نمی‌شود؛ در compose یا کل سرویس recreate شود یا دایرکتوری mount شود.
- دو ۴۰۴ بی‌ضرر: `vsda.js`/`vsda_bg.wasm` (ماژول امضای اختصاصی مایکروسافت، در build متن‌باز code-server نیست) — ربطی به sub-path ندارد و در هر استقرار هست.
- `remoteAuthority: "remote:80"` در کانفیگ workbench دیده شد؛ روی عملکرد اثری نداشت، ولی هنگام ادغام با auth_request و TLS باید دوباره سنجیده شود.

### ۳.۱۱ نتیجهٔ spike افزونهٔ Claude Code (اجرا و تأیید شد، 2026-08-29)

**سؤال:** آیا افزونهٔ رسمی داخل code-server با env (بدون login تعاملی) از راه relay ما احراز هویت می‌کند؟

**روش:** image واحد (code-server + claude، آینهٔ D2.3) ساخته شد؛ کانتینر با `ANTHROPIC_BASE_URL=http://relay:8899` و کلید gateway ساختگی و بدون توکن آپ‌استریم بالا آمد؛ relay §۰ روی همان شبکه (خواندن توکن معتبر از volume بک‌اند)؛ افزونه از VSIX نصب شد؛ سپس **باینری native خودِ افزونه** headless با env کانتینر اجرا شد. مصنوعات در `spike/ide-basepath/`.

**نتیجه: ✅ کار می‌کند.** relay درخواست افزونه را دید: `model=claude-sonnet-5`, **`status=200`**, `n_tools=21`, `usage={input, cache_creation, output}`, `beta_injected=true` — **بدون هیچ login تعاملی**، فقط از env. یعنی D2.4 (relay به‌جای توکن در ورک‌اسپیس) و D3.6 (افزونه به‌عنوان چت dev) با هم سازگار و اثبات‌شده‌اند: توکن آپ‌استریم هرگز وارد ورک‌اسپیس نشد و افزونه از راه relay به مدل رسید.

**یافته‌های مهم برای build تولیدی (§۶):**
- **افزونه platform-specific است** و یک باینری native خودش را bundle می‌کند (`resources/native-binary/claude`، ~۱۰۰MB per-platform). `code-server --install-extension Anthropic.claude-code` معماری را اشتباه resolve کرد (۴۰۳ / پیش‌فرض `alpine-arm64`). راه درست: نصب VSIX هدف **`linux-x64`** صریح (URL: `open-vsx.org/api/Anthropic/claude-code/linux-x64/<ver>/file/...`). image واحد باید این نسخه را bake کند.
- افزونه UI خود را به‌صورت webview در کانتینر `claude-sidebar` (activity bar، یا هنگام پشتیبانی از secondary sidebar در پنل راست) می‌گذارد — **نه** chat participant و **نه** چت داخلی build (این code-server یک چت Copilot-مانند جدا هم دارد که ربطی به ما ندارد و باید در image غیرفعال/حذف شود تا کاربر گیج نشود).
- env احراز هویت (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`) باید هنگام **create** کانتینر تزریق شود (کلید gateway کوتاه‌عمر D2.4)، چون extension host آن را از محیط پروسهٔ کانتینر می‌خواند.
- دو runtime `claude` در ورک‌اسپیس، هر دو با auth از env/relay: باینری bundleشدهٔ افزونه (IDE) و `claude` نصب‌شده برای `-p` headless بک‌اند (چت عمومی). سازگار با «دو پوسته، یک relay».

**صداقت spike:** احراز هویت env در **لایهٔ runtime** (باینری‌ای که واقعاً با مدل حرف می‌زند و webview آن را می‌راند) قطعی اثبات شد. click-through بصریِ خودِ webview به‌صورت اسکرین‌شات ثبت نشد چون پنل مرورگرِ داخلی زیر DOM سنگین VS Code به screenshot پاسخ نمی‌داد؛ این محدودیتِ ابزار مشاهده است، نه محصول — رندر workbench و درخت a11y سالم بودند و منطق auth در لایهٔ زیرین verify شد.

---

## ۴. اسکیمای دیتابیس (دلتای v2)

### ۴.۰ مبنای Alembic — شروع تازه

چون v2 **ریپوی جدید و DB تمیز** است (تصمیم ۴ PRD)، زنجیرهٔ مهاجرت‌های v1 (`0001`..`0006`) حمل نمی‌شود. یک **baseline واحد `0001_v2_initial`** ساخته می‌شود که همهٔ جدول‌های v1 که در PRD-V2 §۱۱ «پورت» شده‌اند را به‌علاوهٔ افزوده‌های v2 دارد. جدول‌های حذف‌شدهٔ v1 در baseline نمی‌آیند: چیزی مربوط به LiteLLM نیست (ستون `api_keys.litellm_key_id` **حذف** می‌شود، نه legacy)، و `teams`/`team_members`/حافظهٔ مشترک فعلاً ساخته نمی‌شوند (PRD-V2 §۱۱ — بعداً روی مدل workspace بازطراحی).

جدول‌های پورت‌شده از v1 (بدون تغییر ساختاری، مرجع `docs/TECH.md §۳`): `users`, `api_keys`, `models`, `model_policies`, `quotas`, `usage_ledger`, `conversations`, `messages`, `attachments`, `audit_log`, `upstream_account_limits`, `settings`. زیر فقط **افزوده‌ها/تغییرها**ی v2 را می‌دهیم.

### ۴.۱ تغییر جدول‌های موجود

```sql
-- سهمیهٔ فضای ذخیره‌سازی per-user (PRD W4 / تصمیم ۳ / §۲.۶). NULL = نامحدود.
ALTER TABLE users ADD COLUMN disk_quota_bytes BIGINT;
ALTER TABLE users ADD COLUMN retention_days   INTEGER;   -- NULL = پیش‌فرض سراسری (۳۰)

-- کلید API: انتخاب صریح مسیر (D0.2). 'flatten' = رفتار قدیمِ سازگار با ابزارهای عمومی
-- (فقط اگر روزی لازم شد)؛ 'claude_code' = relay خام برای کلاینت Claude Code (پیش‌فرض عملی).
ALTER TABLE api_keys ADD COLUMN mode VARCHAR(20) NOT NULL DEFAULT 'claude_code';
-- ستون litellm_key_id حذف شد (v2 اصلاً LiteLLM ندارد).
ALTER TABLE api_keys DROP COLUMN litellm_key_id;

-- surface جدید در ledger: 'ide' برای نوبت‌های افزونهٔ داخل کد-سرور، در کنار
-- 'web' (چت ساده) و 'api' (کلید شخصی روی ماشین dev). فقط مقدار جدید در ستون موجود
-- usage_ledger.surface؛ نیازی به DDL نیست (VARCHAR است).
```

### ۴.۲ جدول جدید `workspaces` (§۲)

```sql
CREATE TYPE workspace_kind   AS ENUM ('repo', 'personal');
CREATE TYPE workspace_status AS ENUM ('provisioning','running','stopping','stopped','archived','deleted');

CREATE TABLE workspaces (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            workspace_kind   NOT NULL,
    status          workspace_status NOT NULL DEFAULT 'provisioning',
    name            VARCHAR(200) NOT NULL,                 -- نام نمایشی
    repo_url        TEXT,                                  -- NULL برای personal
    base_branch     VARCHAR(200),
    work_branch     VARCHAR(200),                          -- ecocode/<...>
    container_name  VARCHAR(120),                          -- ecows_<id>
    volume_name     VARCHAR(120),                          -- ecows_<id>
    disk_bytes      BIGINT NOT NULL DEFAULT 0,             -- کش‌شده، توسط اندازه‌گیر دوره‌ای
    retention_days  INTEGER,                               -- override per-workspace؛ NULL = از user/سراسری
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),   -- سیگنال idle-stop (§۲.۵)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- یک ورک‌اسپیس ریپویی فعال به ازای هر (کاربر، ریپو) (§۲.۳). personalها repo_url ندارند.
    CONSTRAINT uq_ws_user_repo UNIQUE (user_id, repo_url)
);
CREATE INDEX idx_ws_user        ON workspaces(user_id);
CREATE INDEX idx_ws_status      ON workspaces(status);
CREATE INDEX idx_ws_reaper      ON workspaces(status, last_activity_at);  -- reaper/GC
```

`conversations` برای بستنِ چت‌های چت‌ساده به ورک‌اسپیس، یک ستون nullable می‌گیرد:
```sql
ALTER TABLE conversations ADD COLUMN workspace_id BIGINT REFERENCES workspaces(id) ON DELETE CASCADE;
```
(چت‌های افزونهٔ داخل IDE توسط خود Claude Code مدیریت می‌شوند و در DB ما ردیف `conversations` نمی‌سازند؛ فقط usage‌شان از relay در `usage_ledger` با `surface='ide'` ثبت می‌شود.)

### ۴.۳ جدول جدید `gitlab_tokens` (§۴ PRD G1/F10)

```sql
CREATE TABLE gitlab_tokens (
    user_id       BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_enc     TEXT NOT NULL,                 -- PAT کاربر، رمزشده با Fernet (همان کلید v1)
    gitlab_host   VARCHAR(200) NOT NULL DEFAULT 'git.ecobin.ir',
    scopes        VARCHAR(200),                  -- برای نمایش؛ enforcement سمت گیت‌لب است
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
توکن هرگز plaintext برنمی‌گردد؛ فقط برای تزریق داخل sandbox همان کاربر رمزگشایی می‌شود (§۶). یک ردیف per-user کافی است (یک گیت‌لب سازمانی).

### ۴.۴ جدول جدید `workspace_keys` — کلید gateway کوتاه‌عمر (D2.4)

```sql
CREATE TABLE workspace_keys (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_prefix    VARCHAR(16) NOT NULL,
    key_hash      TEXT NOT NULL,                 -- هش؛ خودِ کلید فقط لحظهٔ تزریق شناخته می‌شود
    expires_at    TIMESTAMPTZ,                   -- چرخش با هر resume (§۲.۳)
    revoked_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wskey_hash UNIQUE (key_hash)
);
CREATE INDEX idx_wskey_ws ON workspace_keys(workspace_id);
```
این کلید همان کلیدی است که به‌عنوان `ANTHROPIC_AUTH_TOKEN` داخل کانتینر ورک‌اسپیس می‌رود. در relay، authentication یا از `api_keys` (mode=`claude_code`، مسیر dev-CLI) است یا از `workspace_keys` (مسیر ورک‌اسپیس)، و هر دو به همان user resolve و همان سهمیه/ACL را می‌گیرند. مزیت جداسازی: ابطال کلید یک ورک‌اسپیس بدون لمس کلیدهای شخصی dev.

## ۵. relay خام تولیدی (§A + مسیر ورک‌اسپیس)

### ۵.۰ از spike تا تولید

اسکلت در `spike/relay_spike.py` رفتار wire را اثبات کرد (§۰). نسخهٔ تولیدی داخل بک‌اند FastAPI است تا **enforcement پیش از relay** و **ثبت usage پس از استریم** در همان جا و با همان ledger/quota موجود انجام شود. `app/routers/passthrough.py` v1 (که هر درخواست را به `run_oneshot_turn` تبدیل می‌کرد) با این جایگزین می‌شود.

### ۵.۱ ترتیب قطعی یک درخواست `POST /v1/messages`

```
۱. auth: کلید را resolve کن (api_keys.mode='claude_code'  یا  workspace_keys) → user.
        نامعتبر/ابطال‌شده → 401.  کاربر غیرفعال → 403.
۲. مدل: body.model → Model؛ اگر enable نیست → 404 ؛ ModelPolicy(user,model) نبود → 403 (model_not_allowed).
۳. سهمیه: check_quota(user)  — هر دو سقف هفتگی + غلتان ۵ساعته (§V3، پورت v1).
        رد → 429 با کد quota_exceeded / quota_exceeded_5h + زمان آزادشدن.
۴. relay: درخواست را بدون بازسازی به UPSTREAM_BASE_URL بفرست:
        - Authorization: Bearer <توکن OAuth آپ‌استریم> (از credentials؛ همان refreshِ خودکار v1)
        - anthropic-beta: اگر oauth-2025-04-20 نبود اضافه کن (تنها تبدیل — §۰)
        - بقیهٔ هدرها/بدنه دست‌نخورده؛ HTTPS_PROXY رعایت شود.
۵. fail-fast: اگر پیش از اولین byteِ بدنه، status آپ‌استریم خطا بود → همان status واقعی HTTP
        (نه 200 خالی؛ parity با peek v1). خطاهای 4xx/429/529 → کد/پیام فارسی نگاشت‌شده.
۶. stream: بایت‌ها را chunked به کلاینت pass کن (proxy_buffering off مثل v1).
۷. usage: ضمن عبور، رویدادهای SSE را برای usage بخوان (parse با brace-matching نه regex —
        input_tokens, cache_creation_input_tokens→cache_write, cache_read_input_tokens→cache_read,
        output_tokens). پس از پایان استریم، ledger.record_usage(surface = 'api'|'ide') + commit.
        شکست ثبت usage هرگز پاسخ کاربر را نمی‌شکند (پس از ارسال است).
۸. V6: هدرهای anthropic-ratelimit-* پاسخ را برای upstream_account_limits بردار (§۷).
```

نکته‌ها: تاریخچهٔ چندنوبتی و tool_use/tool_result کلاینت **دست‌نخورده** عبور می‌کنند (این کل تفاوت با v1 است — §۰ اثبات کرد کار می‌کند). ستون `surface`: مسیر dev-CLI → `api`؛ مسیر افزونهٔ داخل IDE (که با `workspace_keys` می‌آید) → `ide`.

### ۵.۲ مسیر ورک‌اسپیس همان endpoint است

افزونهٔ Claude Code و `claude -p` headless هر دو داخل کانتینر ورک‌اسپیس به `ANTHROPIC_BASE_URL` = همین relay می‌زنند، با `workspace_keys` به‌عنوان bearer. یعنی یک پیاده‌سازی relay، سه مصرف‌کننده (dev-CLI، افزونه، headless). §۰ و §۳.۱۱ هر دو این را با ۲۰۰ واقعی تأیید کردند.

### ۵.۳ چه چیزی از v1 حذف می‌شود

`run_oneshot_turn` و کل مسیر «CLI-wrapping برای passthrough»، flatten تاریخچه، و side-channel `/internal/usage-report`. مسیر `/v1/chat/completions` (OpenAI-سازگار) در MVP **حذف** است (تصمیم ۲ PRD)؛ اگر بعداً لازم شد، فقط با راه غیر-wrapping.

## ۶. Compose v2 + image واحد ورک‌اسپیس

### ۶.۱ سرویس‌ها

| سرویس | نقش | تغییر نسبت به v1 |
|---|---|---|
| `postgres` | DB | بدون تغییر |
| `backend` | FastAPI: auth/ACL/quota/ledger/audit + **relay خام** + مدیر چرخهٔ عمر ورک‌اسپیس | relay جایگزین passthrough؛ مدیر ورک‌اسپیس جدید |
| `nginx` | ingress: `/api`,`/v1`, و `/ide/<id>/` با auth_request (§۳) | مسیر `/ide/` پویا اضافه شد |
| `egress` | پروکسی allowlist خروجی ورک‌اسپیس‌ها | پورت مستقیم؛ allowlist = relay بک‌اند + `git.ecobin.ir` + `open-vsx.org` (§۲.۴) |
| **image واحد ورک‌اسپیس** | build‌شده، runtime کانتینرهای `ecows_<id>` | جایگزین `runner/` + `code-server` تک‌instance |
| ~~litellm~~, ~~compression~~, ~~code-server مشترک~~ | — | **حذف** (PRD-V2 §۱۱) |

مدیر چرخهٔ عمر برای اجرای `docker` نیاز به دسترسی به Docker socket دارد (مثل v1 که برای sandbox داشت) — با احتیاط: فقط backend، و همهٔ ورودی‌ها به‌صورت argv نه شل (پورت الگوی امن `sandbox_runner`).

### ۶.۲ شبکه — دسترسی relay از شبکهٔ internal

دو شبکه مثل v1: `ecocode_net` (پل، اینترنت‌دار) و `ecocode_sandbox_net` (**internal: true**، بدون اینترنت). کانتینرهای ورک‌اسپیس **فقط** روی `ecocode_sandbox_net`اند. تنها خروجی‌شان `egress` است. برای این‌که relay بک‌اند از داخل ورک‌اسپیس قابل‌دسترس باشد، دو راه (تصمیم §۶):
- **الف (ساده):** `egress` را طوری allowlist کن که به host بک‌اند هم اجازه دهد؛ ورک‌اسپیس از راه HTTPS_PROXY به relay بک‌اند می‌رسد. مزیت: بک‌اند به شبکهٔ internal وصل نمی‌شود (سطح حملهٔ کمتر).
- **ب:** backend را هم به `ecocode_sandbox_net` وصل کن و relay را روی یک **listener/پورت مجزا** بگذار که فقط `workspace_keys` را می‌پذیرد؛ مسیرهای admin/DB روی پورت اصلی و شبکهٔ دیگر می‌مانند.

**انتخاب: الف** — چون توکن آپ‌استریم اصلاً وارد ورک‌اسپیس نمی‌شود، و بردنِ همهٔ ترافیک مدل از `egress` (که allowlist و لاگ دارد) یکدست‌تر و کم‌سطح‌حمله‌تر است. `SANDBOX_ALLOW_HOSTS` = host بک‌اند + `git.ecobin.ir` + `open-vsx.org`.

### ۶.۳ Dockerfile image واحد ورک‌اسپیس

اثبات‌شده در spike §۳.۱۱؛ نسخهٔ تولیدی:
```dockerfile
FROM codercom/code-server:<pinned>          # نسخهٔ pin‌شده، نه latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gnupg git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \        # برای مسیر headless `claude -p`
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
# افزونهٔ Claude Code — نسخهٔ هدفِ صریحِ معماری (یافتهٔ §۳.۱۱: نصب معمولی arch را اشتباه resolve می‌کند)
RUN curl -fsSL -o /tmp/cc.vsix \
     "https://open-vsx.org/api/Anthropic/claude-code/linux-x64/<ver>/file/Anthropic.claude-code-<ver>@linux-x64.vsix" \
 && code-server --install-extension /tmp/cc.vsix && rm /tmp/cc.vsix
# چت Copilot-مانند داخلی این build غیرفعال شود تا کاربر گیج نشود (§۳.۱۱)
USER coder
```
env احراز هویت (`ANTHROPIC_BASE_URL` = relay، `ANTHROPIC_AUTH_TOKEN` = کلید workspace، `HTTPS_PROXY` = egress) و شناسهٔ git کاربر، هنگام **`docker run`** (create ورک‌اسپیس) تزریق می‌شوند — نه در image. توکن گیت‌لب (رمزگشایی‌شده از `gitlab_tokens`) هم فقط لحظهٔ clone/push به‌صورت env/credential-helper داخل همین کانتینر تزریق می‌شود و در image یا volume نمی‌نشیند.

### ۶.۴ فلگ‌های `docker run` کانتینر ماندگار (پورت از `sandbox_runner`)

از v1 عیناً: `--network ecocode_sandbox_net`, `--user 1000:1000`, `--memory/--cpus/--pids-limit`, `--security-opt no-new-privileges`, `--cap-drop ALL`, `-v ecows_<id>:/home/coder/project`. تفاوت با v1: `--read-only` سراسری برداشته می‌شود (code-server به مسیرهای config نیاز دارد)؛ در عوض فقط volume ورک‌اسپیس rw است و بقیهٔ حساسیت‌ها با نبودِ mountِ creds/DB و شبکهٔ internal پوشش داده می‌شود. **بدون `--rm`** (کانتینر ماندگار؛ stop/start به‌جای نابودی) و **بدون timeout سراسری** (نوبت‌ها با idle-stop مدیریت می‌شوند، §۲.۵).

## ۷. capture لیمیت اکانت آپ‌استریم (V6) — با نام‌های واقعی هدر

spike §۰ نام‌های واقعی را داد؛ §۴.۵ سند v1 دیگر «حدس» نیست. در گام ۸ relay (§۵.۱)، همهٔ هدرهای پاسخ که با `anthropic-ratelimit` شروع می‌شوند خام برداشته و در جدول موجود `upstream_account_limits` (پورت از v1) upsert می‌شوند — **inline در بک‌اند، بدون side-channel** (چون relay خودش در بک‌اند است، برخلاف v1 که handler جدا بود).

خانواده‌های واقعیِ دیده‌شده (باید دفاعی parse شوند، نه با فرض نام دقیق):
```
anthropic-ratelimit-unified-5h-status | -5h-reset | -5h-utilization
anthropic-ratelimit-unified-7d-status | -7d-reset | -7d-utilization
anthropic-ratelimit-unified-status | -reset | -overage-status | -fallback
anthropic-ratelimit-unified-representative-claim | -fallback-percentage
```
نگاشت: هر پنجره (`5h`,`7d`,`unified`) → یک ردیف با `window_key`؛ `utilization`→ محاسبهٔ `remaining`؛ `reset`→ `reset_at`؛ کل مجموعه در `raw_headers` (JSONB) نگه‌داری می‌شود تا هیچ داده‌ای گم نشود. مسیرهای headless (`claude -p`) این هدرها را نمی‌دهند؛ پس مثل v1 state فقط از ترافیک relayدار تازه می‌شود و `last_updated`/`stale` در UI صادقانه نشان داده می‌شود. endpoint ادمین: `GET /api/admin/upstream/account-limits` (پورت از v1). probe اختیاری (`UPSTREAM_LIMIT_PROBE_ENABLED`) حفظ می‌شود.

## ۸. تقسیم کار و نگاشت به فازهای PRD

| فاز PRD | بخش‌های فنی | خروجی قابل‌تأیید |
|---|---|---|
| **P0 بنیان** | §۰ (✅)، §۳.۱۰/§۳.۱۱ (✅)، اسکلت compose §۶، baseline Alembic §۴.۰ | ریپو بالا می‌آید؛ هر سه spike بسته (relay/base-path/افزونه) |
| **P1 هستهٔ dev** | §۲ (create/running/stopped/resume, reconciliation)، §۴ (workspaces, gitlab_tokens, workspace_keys)، §۵ relay، §۶ image واحد + docker run، §۷ | یک dev واقعی: create ورک‌اسپیس از ریپو → کار → push → لینک MR |
| **P2 IDE** | §۳ کامل (auth_request، `/ide/<id>/`، resume-flow، افزونه)، §۲.۶ دیسک/idle/GC | تجربهٔ «VS Code + افزونهٔ Claude Code» برای همهٔ devها |
| **P3 عمومی** | §۲.۹ ورک‌اسپیس شخصی، چت سادهٔ پورت‌شده از v1 (surface `web`)، §۴ `conversations.workspace_id` | کاربر عمومی؛ خاموشی v1 پس از دورهٔ فقط‌خواندنی |
| **P4 حاکمیت + CLI** | داشبورد/گزارش (پورت v1)، §۵ کلید dev-CLI + onboarding، §۷ داشبورد لیمیت | نسخهٔ ۱.۰ |
| **P5 سرویس‌ها** | `docs/SERVICES-V2.md` بخش ب: MCP Gateway، connectorهای sql/files، اسکیمای services/grants/audit، سینک skill (DS6)، spikeهای SPK-SV1/SV2 | کاربر گرنت‌دار گزارش read-only از سیستم واقعی می‌گیرد؛ `grep` کانتینر ورک‌اسپیس هیچ اعتبارنامه‌ای پیدا نمی‌کند |

مرز ماژول (اگر دو توسعه‌دهنده): Dev1 = backend (چرخهٔ عمر ورک‌اسپیس، relay، DB، compose)؛ Dev2 = frontend (صفحهٔ ورک‌اسپیس، embed IDE، ثبت PAT، داشبوردها) + nginx auth_request. نقطهٔ integration = قرارداد `/api/workspaces/*` و `/internal/authz/workspace/{id}`.

## ۹. جمع‌بندی مدل امنیت v2

- **ایزولاسیون اجرا:** هر چیزِ دارای Bash/git فقط داخل کانتینر ورک‌اسپیس روی `ecocode_sandbox_net` (internal، بدون اینترنت مستقیم)؛ بدون mount اعتبارنامه/DB بک‌اند؛ سقف mem/cpu/pids؛ `no-new-privileges`؛ `cap-drop ALL`.
- **توکن آپ‌استریم:** هرگز وارد ورک‌اسپیس نمی‌شود؛ فقط در relay بک‌اند تزریق می‌شود (D2.4، اثبات §۳.۱۱). بدترین حالتِ نشتِ کلید workspace = سوزاندن سهمیهٔ خود کاربر (قابل‌ابطال).
- **egress allowlist:** خروجی ورک‌اسپیس فقط به relay بک‌اند + `git.ecobin.ir` + `open-vsx.org`. حتی `api.anthropic.com` مستقیم در دسترس نیست.
- **توکن گیت‌لب:** PAT خود کاربر، رمزشده (`gitlab_tokens`)، فقط لحظهٔ clone/push داخل sandbox همان کاربر؛ egress مقصدش را به `git.ecobin.ir` قفل می‌کند.
- **گِیت IDE:** نشست EcoCode از راه nginx `auth_request` + چک مالکیت + مرز کانتینر per-workspace (§۳). code-server `--auth none` فقط پشت این لایه.
- **حریم خصوصی:** ادمین متادیتا/مصرف می‌بیند، نه محتوای گفتگو/ورک‌اسپیس (پورت v1).

## ۱۰. برنامهٔ تأیید

**بسته‌شده با spike (این سند):**
- relay خام: opus/sonnet/haiku همه ۲۰۰، حلقهٔ tool round-trip، usage از SSE (§۰).
- code-server زیر sub-path: workbench کامل، شرط `Host $http_host` (§۳.۱۰).
- افزونهٔ Claude Code: auth با env از راه relay، بدون login؛ نیاز به VSIX `linux-x64` (§۳.۱۱).

**برای E2E پیش از هر فاز:**
- P1: create→push→MR روی یک ریپوی واقعی `git.ecobin.ir` با PAT واقعی؛ صحت ثبت usage `surface='api'/'ide'` در ledger؛ reconciliation بعد از restart بک‌اند.
- P2: gating — کاربر A نتواند `/ide/<id>ِ-کاربر-B/` را باز کند (403)؛ idle-stop و resume؛ سهمیهٔ دیسک و پیام self-service.
- P3: چت سادهٔ عمومی روی ورک‌اسپیس شخصی؛ ایزولهٔ کامل بین کاربران.

## ضمیمه

- **مدل سهمیه:** بدون تغییر از v1 (`docs/TECH.md` ضمیمهٔ الف) — `credits = input×w_in + output×w_out + cache_read×w_cache`؛ توکن‌های تفکر در `output_tokens`اند پس خودکار وزن می‌گیرند.
- **متغیرهای محیطی جدید v2 (پیشنهاد):** `WORKSPACE_IMAGE`, `WORKSPACE_IDLE_MINUTES=30`, `WORKSPACE_RETENTION_DAYS=30`, `MAX_RUNNING_WORKSPACES=4`, `SANDBOX_ALLOW_HOSTS=<backend>,git.ecobin.ir,open-vsx.org`, `GITLAB_HOST=git.ecobin.ir`. متغیرهای پورت‌شده از v1 (upstream/oauth/quota/thinking/…) بدون تغییر.
- **مصنوعات spike:** `spike/relay_spike.py`, `spike/relay.log`, `spike/ide-basepath/` (compose + Dockerfile + nginx.conf).
