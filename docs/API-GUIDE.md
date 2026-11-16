# راهنمای استفاده از وب‌سرویس Coolade

این راهنما برای کاربرانی است که می‌خواهند با **کلید API شخصی** خود از گیت‌وی Coolade در ابزارهای برنامه‌نویسی (Cline، Continue، aider و…) یا اسکریپت‌های خودشان استفاده کنند.

آدرس پایه (داخل شبکه سازمان): `http://<آدرس-سرور>:8085`

---

## ۱. ساخت کلید API

1. وارد وب Coolade شوید (نام کاربری/رمز سازمانی خودتان).
2. از منو، **«کلیدهای API»** → **«ساخت کلید جدید»** و یک نام بدهید (مثلاً «Cline لپ‌تاپ»).
3. کلید (`coolade_live_…`) **فقط همین یک‌بار** نمایش داده می‌شود — همان لحظه کپی و در جای امن ذخیره کنید.

نکته‌ها:
- می‌توانید چند کلید با نام‌های مختلف داشته باشید و هر کدام را جداگانه باطل کنید.
- مصرف همه کلیدهای شما از **سهمیه خود شما** کم می‌شود و در صفحه «مصرف من» با تفکیک هر کلید دیده می‌شود.
- کلید فقط به مدل‌هایی دسترسی دارد که ادمین برای شما مجاز کرده است.

## ۲. Endpoint ها

| Endpoint | سبک | توضیح |
|---|---|---|
| `POST /v1/messages` | Anthropic Messages API | برای ابزارهایی که provider نوع Anthropic دارند |
| `POST /v1/chat/completions` | OpenAI Chat Completions | برای ابزارها/کتابخانه‌های OpenAI-سازگار |
| `GET /v1/models` | OpenAI-style | لیست مدل‌های مجاز شما (auto-discovery) |

احراز هویت با هر دو شکل پذیرفته می‌شود:
- هدر `x-api-key: coolade_live_…` (سبک Anthropic)
- هدر `Authorization: Bearer coolade_live_…` (سبک OpenAI)

استریم (SSE) در هر دو endpoint با `"stream": true` پشتیبانی می‌شود.

## ۳. نمونه‌ها

### curl — سبک Anthropic

```bash
curl -X POST http://SERVER:8085/v1/messages \
  -H "x-api-key: coolade_live_XXXX" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "سلام!"}]
  }'
```

### curl — سبک OpenAI (با استریم)

```bash
curl -N -X POST http://SERVER:8085/v1/chat/completions \
  -H "Authorization: Bearer coolade_live_XXXX" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-haiku",
    "stream": true,
    "messages": [{"role": "user", "content": "سلام!"}]
  }'
```

### Python — کتابخانه رسمی anthropic

```python
from anthropic import Anthropic

client = Anthropic(base_url="http://SERVER:8085", api_key="coolade_live_XXXX")
msg = client.messages.create(
    model="claude-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "سلام!"}],
)
print(msg.content[0].text)
```

### Python — کتابخانه openai

```python
from openai import OpenAI

client = OpenAI(base_url="http://SERVER:8085/v1", api_key="coolade_live_XXXX")
resp = client.chat.completions.create(
    model="claude-haiku",
    messages=[{"role": "user", "content": "سلام!"}],
)
print(resp.choices[0].message.content)
```

## ۴. تنظیم ابزارها

### Cline (VS Code)

روش پیشنهادی — provider نوع Anthropic:
- **API Provider:** Anthropic
- **Anthropic Base URL:** `http://SERVER:8085`
- **API Key:** `coolade_live_XXXX`
- **Model:** `claude-sonnet` (یا هر مدل مجاز شما)

روش جایگزین — OpenAI Compatible:
- **API Provider:** OpenAI Compatible
- **Base URL:** `http://SERVER:8085/v1`
- **API Key / Model:** مثل بالا

### Continue

در `config.json`:
```json
{
  "models": [{
    "title": "Coolade Sonnet",
    "provider": "anthropic",
    "apiBase": "http://SERVER:8085",
    "apiKey": "coolade_live_XXXX",
    "model": "claude-sonnet"
  }]
}
```

### aider

```bash
export ANTHROPIC_API_KEY=coolade_live_XXXX
export ANTHROPIC_BASE_URL=http://SERVER:8085
aider --model claude-sonnet
```

## ۵. نام مدل‌ها

از **کلید داخلی** مدل‌ها استفاده کنید، نه نام‌های رسمی Anthropic:

| کلید مدل | توضیح |
|---|---|
| `claude-opus` | قوی‌ترین — مصرف امتیاز بالا |
| `claude-sonnet` | تعادل کیفیت/مصرف |
| `claude-haiku` | سریع و کم‌مصرف |

لیست دقیق مدل‌های مجاز *شما* را از `GET /v1/models` بگیرید. (ادمین ممکن است دسترسی شما را محدود کرده باشد.)

## ۶. خطاها

| کد | معنی | چه کنیم |
|---|---|---|
| `401` | کلید نامعتبر یا باطل‌شده | کلید جدید بسازید |
| `403 model_not_allowed` | مدل برای شما مجاز نیست | از مدل مجاز استفاده کنید یا از ادمین بخواهید |
| `429 quota_exceeded` | سهمیه دوره شما تمام شده | تا شروع دوره بعد صبر کنید یا از ادمین سهمیه موقت بگیرید |
| `429 upstream_rate_limited` | سرویس بالادستی موقتاً شلوغ است | کمی بعد دوباره تلاش کنید |

بدنه خطاها به شکل `{"error": {"code": "...", "message": "پیام فارسی"}}` است.

## ۷. سقف مصرف

- مصرف بر اساس «امتیاز» محاسبه می‌شود: توکن ورودی/خروجی × ضریب مدل (Opus گران‌تر از Sonnet، Sonnet گران‌تر از Haiku).
- وضعیت لحظه‌ای را در صفحه **«مصرف من»** ببینید؛ در ۸۰٪ سهمیه هشدار نمایش داده می‌شود.
- بعد از اتمام سهمیه، درخواست‌ها تا شروع دوره بعدی (پیش‌فرض: هفتگی) با `429` رد می‌شوند.
