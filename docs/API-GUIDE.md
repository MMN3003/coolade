# راهنمای اتصال ابزارها به Coolade

این راهنما برای کاربرانی است که می‌خواهند با **کلید شخصی** خود، Claude Code (ترمینال یا VS Code)، Cline، Continue، aider یا اسکریپت‌های خودشان را به گیت‌وی Coolade وصل کنند. کد و فایل‌ها روی سیستم خودتان می‌مانند؛ فقط درخواست‌های مدل از گیت‌وی رد می‌شوند.

**آدرس relay:** همان آدرسی که وب را با آن باز می‌کنید + `/relay`، مثلاً `http://SERVER:8085/relay`. در همهٔ نمونه‌ها `SERVER:8085` را با آدرس واقعی جایگزین کنید.

> ⚠️ آدرس‌های قدیمی `http://SERVER:8085/v1/...` و `/v1/chat/completions` (سبک OpenAI) **حذف شده‌اند**. فقط `/relay/v1/...` (سبک Anthropic) کار می‌کند.

---

## ۱. ساخت کلید

1. وارد وب Coolade شوید → **«اتصال CLI»** یا **«کلیدهای API»** → **«ساخت کلید»**.
2. کلید (`coolade_live_…`) **فقط همان یک‌بار** نمایش داده می‌شود؛ همان لحظه کپی کنید.

- می‌توانید چند کلید بسازید و هرکدام را جداگانه باطل کنید.
- مصرف همهٔ کلیدها از **سهمیهٔ خودتان** کم می‌شود و در «مصرف من» دیده می‌شود.

## ۲. سه قانون مهم (علت بیشتر خطاهای اتصال)

| درست ✅ | غلط ❌ | نتیجهٔ غلط |
|---|---|---|
| `ANTHROPIC_AUTH_TOKEN` | `ANTHROPIC_API_KEY` | Claude Code منوی «Select login method» را نشان می‌دهد یا دربارهٔ کلید سؤال می‌پرسد |
| `ANTHROPIC_BASE_URL=http://SERVER:8085/relay` | بدون `/relay` یا با `/relay/v1` | خطای 404 یا 405 |
| متغیرها در فایل شل **با `export`** (یا `setx` در ویندوز) | فقط تایپ در یک ترمینال، یا بدون `export` | در ترمینال جدید کار نمی‌کند |

همچنین اگر در `~/.claude/settings.json` بخش `"env"` با کلیدهای `ANTHROPIC_*` دارید، **حذفش کنید**؛ مقدار آن بر متغیرهای شل غلبه می‌کند.

## ۳. Claude Code — بر اساس سیستم‌عامل

### macOS (zsh)

```zsh
# ۱) نصب (یک‌بار)
curl -fsSL https://claude.ai/install.sh | bash

# ۲) بررسی تنظیمات قبلی (اگر خطی پیدا شد، از همان فایل پاکش کنید)
grep -n ANTHROPIC ~/.zshrc ~/.zprofile ~/.zshenv ~/.claude/settings.json 2>/dev/null

# ۳) ذخیرهٔ دائمی
cat >> ~/.zshrc <<'EOF'
export ANTHROPIC_BASE_URL="http://SERVER:8085/relay"
export ANTHROPIC_AUTH_TOKEN="coolade_live_XXXX"
EOF
unset ANTHROPIC_API_KEY
source ~/.zshrc

# ۴) تست
env | grep ANTHROPIC
claude -p "سلام"
```

اگر قبلاً `ANTHROPIC_API_KEY` گذاشته بودید، با این دستور به `AUTH_TOKEN` تبدیلش کنید:

```zsh
sed -i '' 's/ANTHROPIC_API_KEY=/ANTHROPIC_AUTH_TOKEN=/' ~/.zshrc && unset ANTHROPIC_API_KEY && source ~/.zshrc
```

### Linux (Ubuntu، bash)

```bash
# ۱) نصب (یک‌بار)
curl -fsSL https://claude.ai/install.sh | bash
# یا: npm install -g @anthropic-ai/claude-code   (Node 18 یا جدیدتر)

# ۲) بررسی تنظیمات قبلی
grep -n ANTHROPIC ~/.bashrc ~/.profile ~/.bash_profile ~/.claude/settings.json 2>/dev/null

# ۳) ذخیرهٔ دائمی
cat >> ~/.bashrc <<'EOF'
export ANTHROPIC_BASE_URL="http://SERVER:8085/relay"
export ANTHROPIC_AUTH_TOKEN="coolade_live_XXXX"
EOF
unset ANTHROPIC_API_KEY
source ~/.bashrc

# ۴) تست
env | grep ANTHROPIC
claude -p "سلام"
```

تبدیل `API_KEY` قدیمی:

```bash
sed -i 's/ANTHROPIC_API_KEY=/ANTHROPIC_AUTH_TOKEN=/' ~/.bashrc && unset ANTHROPIC_API_KEY && source ~/.bashrc
```

### Windows (PowerShell، بدون WSL)

پیش‌نیاز: [Git for Windows](https://git-scm.com/download/win) (Claude Code در ویندوز از Git Bash استفاده می‌کند).

```powershell
# ۱) نصب (یک‌بار)
irm https://claude.ai/install.ps1 | iex

# ۲) بررسی تنظیمات قبلی
Get-ChildItem Env:ANTHROPIC*
Select-String -Path "$HOME\.claude\settings.json" -Pattern ANTHROPIC -ErrorAction SilentlyContinue

# ۳) ذخیرهٔ دائمی (برای کاربر جاری) + حذف API_KEY قدیمی
setx ANTHROPIC_BASE_URL "http://SERVER:8085/relay"
setx ANTHROPIC_AUTH_TOKEN "coolade_live_XXXX"
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $null, "User")
```

**مهم:** `setx` فقط روی پنجره‌های **جدید** اثر دارد. همهٔ ترمینال‌ها و VS Code را ببندید و یک PowerShell تازه باز کنید:

```powershell
# ۴) تست
Get-ChildItem Env:ANTHROPIC*
claude -p "سلام"
```

(در CMD هم همان دستورهای `setx` کار می‌کنند؛ برای دیدن مقدار: `echo %ANTHROPIC_BASE_URL%`.)

### Windows + WSL (Ubuntu داخل ویندوز)

داخل WSL، **همه‌چیز مثل Linux است**؛ متغیرهای ویندوز (`setx`) به WSL منتقل **نمی‌شوند** و برعکس.

```bash
# داخل ترمینال WSL:
# ۱) نصب نسخهٔ Linux (نه نسخهٔ ویندوز)
curl -fsSL https://claude.ai/install.sh | bash
which claude        # باید مسیر لینوکسی باشد (مثل ~/.local/bin/claude)، نه /mnt/c/...

# ۲) و ۳) دقیقاً مثل بخش Linux: export در ~/.bashrc (یا ~/.zshrc اگر zsh دارید)
cat >> ~/.bashrc <<'EOF'
export ANTHROPIC_BASE_URL="http://SERVER:8085/relay"
export ANTHROPIC_AUTH_TOKEN="coolade_live_XXXX"
EOF
source ~/.bashrc

# ۴) تست اتصال شبکه از داخل WSL، بعد خود Claude
curl -s http://SERVER:8085/relay/v1/models -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" | head -c 300
claude -p "سلام"
```

- اگر `which claude` به `/mnt/c/...` اشاره می‌کند، نسخهٔ ویندوزی جلوتر در PATH است؛ نسخهٔ لینوکسی را نصب کنید یا PATH را اصلاح کنید.
- اگر `curl` بالا از WSL به سرور نمی‌رسد ولی از ویندوز می‌رسد، مشکل شبکهٔ WSL است (VPN یا فایروال). در `%UserProfile%\.wslconfig` بنویسید `[wsl2]` و `networkingMode=mirrored`، سپس `wsl --shutdown` بزنید.

## ۴. اگر هنوز منوی «Select login method» می‌آید

این منو یعنی Claude Code توکن را نمی‌بیند یا تنظیمات اولیه‌اش (onboarding) هنوز ثبت نشده است. به‌ترتیب بررسی کنید:

1. `env | grep ANTHROPIC` (در ویندوز: `Get-ChildItem Env:ANTHROPIC*`) باید **فقط** `ANTHROPIC_AUTH_TOKEN` و `ANTHROPIC_BASE_URL` را نشان دهد. اگر `ANTHROPIC_API_KEY` هم هست، حذفش کنید.
2. `claude -p "سلام"` را بزنید. اگر جواب داد، اتصال درست است و فقط صفحهٔ اول اجرا باقی مانده. با این دستور ثبتش کنید:

   macOS / Linux / WSL:
   ```bash
   python3 - <<'EOF'
   import json, os
   p = os.path.expanduser('~/.claude.json')
   d = json.load(open(p)) if os.path.exists(p) else {}
   d['hasCompletedOnboarding'] = True
   json.dump(d, open(p, 'w'), indent=2)
   EOF
   ```

   Windows (PowerShell):
   ```powershell
   $p = "$HOME\.claude.json"
   $j = if (Test-Path $p) { Get-Content $p -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
   $j | Add-Member -Force -NotePropertyName hasCompletedOnboarding -NotePropertyValue $true
   $j | ConvertTo-Json -Depth 100 | Set-Content -Encoding utf8 $p
   ```
3. اگر قبلاً با حساب claude.ai وارد شده بودید، یک‌بار `claude` را باز کنید، `/logout` بزنید و دوباره اجرا کنید.
4. بخش `"env"` در `~/.claude/settings.json` (ویندوز: `%USERPROFILE%\.claude\settings.json`) را بررسی کنید.

## ۵. ابزارهای دیگر

همهٔ ابزارهای سازگار با **Anthropic Messages API** با این دو مقدار کار می‌کنند:

- **Base URL:** `http://SERVER:8085/relay`
- **API Key:** `coolade_live_XXXX` (با هدر `x-api-key` یا `Authorization: Bearer`)

**Cline:** API Provider = Anthropic، کلید را وارد کنید، «Use custom base URL» را تیک بزنید و Base URL بالا را بگذارید.

**Continue** (`config.json`):
```json
{
  "models": [{
    "title": "Coolade Sonnet",
    "provider": "anthropic",
    "apiBase": "http://SERVER:8085/relay/v1/",
    "apiKey": "coolade_live_XXXX",
    "model": "claude-sonnet"
  }]
}
```

**aider:**
```bash
export ANTHROPIC_API_KEY=coolade_live_XXXX      # aider (برخلاف Claude Code) همین نام را می‌خواهد
export ANTHROPIC_BASE_URL=http://SERVER:8085/relay
aider --model anthropic/claude-sonnet
```

**curl:**
```bash
curl http://SERVER:8085/relay/v1/messages \
  -H "x-api-key: coolade_live_XXXX" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet", "max_tokens": 512, "messages": [{"role": "user", "content": "سلام!"}]}'
```

مسیرهای فقط-OpenAI (`/chat/completions`) پشتیبانی **نمی‌شوند**.

## ۶. نام مدل‌ها

لیست مدل‌های مجاز **شما**: `GET http://SERVER:8085/relay/v1/models` (با همان کلید). هم کلید داخلی (مثل `claude-sonnet`) و هم شناسهٔ رسمی مدل پذیرفته می‌شود. ادمین ممکن است دسترسی شما را محدود کرده باشد.

## ۷. خطاها

| نشانه | علت | راه‌حل |
|---|---|---|
| منوی «Select login method» | `API_KEY` به‌جای `AUTH_TOKEN`، یا توکن در این ترمینال دیده نمی‌شود | بخش ۲ و ۴ |
| `404` / `405` | Base URL بدون `/relay` یا آدرس قدیمی `/v1` | `ANTHROPIC_BASE_URL=http://SERVER:8085/relay` |
| `401` | کلید نامعتبر یا باطل‌شده | کلید جدید بسازید |
| `403 model_not_allowed` | مدل برای شما مجاز نیست | مدل مجاز انتخاب کنید یا از ادمین بخواهید |
| `429 quota_exceeded` | سهمیهٔ دوره تمام شده | تا دورهٔ بعد صبر کنید یا از ادمین سهمیه بگیرید |
| Claude Code معطل می‌ماند | بخش `env` در `~/.claude/settings.json` آدرس را عوض می‌کند، یا شبکه به سرور نمی‌رسد | آن بخش را حذف کنید؛ با `curl` بخش WSL اتصال را تست کنید |

## ۸. سقف مصرف

مصرف بر اساس «امتیاز» است: توکن ورودی/خروجی × ضریب مدل. وضعیت را در **«مصرف من»** ببینید؛ در ۸۰٪ سهمیه هشدار می‌گیرید و پس از اتمام، درخواست‌ها تا دورهٔ بعد با `429` رد می‌شوند.
