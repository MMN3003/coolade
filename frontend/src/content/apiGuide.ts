// راهنمای کاربری استفاده از وب‌سرویس EcoCode.
// همگام با docs/API-GUIDE.md نگه داشته شود.
// آدرس پایه با placeholder «SERVER» نوشته شده تا کاربر با آدرس واقعی سرور خودش جایگزین کند.

export const API_GUIDE_FA = `
## استفاده از وب‌سرویس با کلید API

با کلید API شخصی خود می‌توانید از EcoCode در ابزارهای برنامه‌نویسی (Cline، Continue، aider و…) یا اسکریپت‌های خودتان استفاده کنید. آدرس پایه، همین آدرسی است که این صفحه را با آن باز کرده‌اید (در نمونه‌ها به‌جای \`SERVER:8085\` از آن استفاده کنید).

### ۱. ساخت کلید API
۱. از منو وارد **«کلیدهای API»** شوید و **«ساخت کلید جدید»** را بزنید و یک نام بدهید (مثلاً «Cline لپ‌تاپ»).
۲. کلید (\`eco_live_…\`) **فقط همان یک‌بار** نمایش داده می‌شود — همان لحظه کپی و در جای امن ذخیره کنید.

نکته‌ها:
- می‌توانید چند کلید با نام‌های مختلف بسازید و هرکدام را جداگانه باطل کنید.
- مصرف همهٔ کلیدهای شما از **سهمیهٔ خودتان** کم می‌شود و در «مصرف من» با تفکیک هر کلید دیده می‌شود.
- کلید فقط به مدل‌هایی دسترسی دارد که ادمین برای شما مجاز کرده است.

### ۲. Endpoint ها

| Endpoint | سبک | توضیح |
|---|---|---|
| \`POST /v1/messages\` | Anthropic Messages API | برای ابزارهای provider نوع Anthropic |
| \`POST /v1/chat/completions\` | OpenAI Chat Completions | برای ابزارهای OpenAI-سازگار |
| \`GET /v1/models\` | OpenAI-style | لیست مدل‌های مجاز شما |

احراز هویت با هر دو شکل پذیرفته می‌شود:
- هدر \`x-api-key: eco_live_…\` (سبک Anthropic)
- هدر \`Authorization: Bearer eco_live_…\` (سبک OpenAI)

استریم (SSE) با \`"stream": true\` در هر دو endpoint پشتیبانی می‌شود.

### ۳. نمونه‌ها

**curl — سبک Anthropic**
\`\`\`bash
curl -X POST http://SERVER:8085/v1/messages \\
  -H "x-api-key: eco_live_XXXX" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-sonnet",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "سلام!"}]
  }'
\`\`\`

**curl — سبک OpenAI (با استریم)**
\`\`\`bash
curl -N -X POST http://SERVER:8085/v1/chat/completions \\
  -H "Authorization: Bearer eco_live_XXXX" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-haiku",
    "stream": true,
    "messages": [{"role": "user", "content": "سلام!"}]
  }'
\`\`\`

**Python — کتابخانهٔ anthropic**
\`\`\`python
from anthropic import Anthropic

client = Anthropic(base_url="http://SERVER:8085", api_key="eco_live_XXXX")
msg = client.messages.create(
    model="claude-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "سلام!"}],
)
print(msg.content[0].text)
\`\`\`

**Python — کتابخانهٔ openai**
\`\`\`python
from openai import OpenAI

client = OpenAI(base_url="http://SERVER:8085/v1", api_key="eco_live_XXXX")
resp = client.chat.completions.create(
    model="claude-haiku",
    messages=[{"role": "user", "content": "سلام!"}],
)
print(resp.choices[0].message.content)
\`\`\`

### ۴. تنظیم ابزارها

**Cline (VS Code)** — روش پیشنهادی:
- API Provider: **Anthropic**
- Anthropic Base URL: \`http://SERVER:8085\`
- API Key: \`eco_live_XXXX\`
- Model: \`claude-sonnet\` (یا هر مدل مجاز شما)

روش جایگزین — **OpenAI Compatible**:
- Base URL: \`http://SERVER:8085/v1\`
- API Key / Model: مثل بالا

**Continue** (در \`config.json\`):
\`\`\`json
{
  "models": [{
    "title": "EcoCode Sonnet",
    "provider": "anthropic",
    "apiBase": "http://SERVER:8085",
    "apiKey": "eco_live_XXXX",
    "model": "claude-sonnet"
  }]
}
\`\`\`

**aider**:
\`\`\`bash
export ANTHROPIC_API_KEY=eco_live_XXXX
export ANTHROPIC_BASE_URL=http://SERVER:8085
aider --model claude-sonnet
\`\`\`

### ۵. نام مدل‌ها
از **کلید داخلی** مدل استفاده کنید، نه نام رسمی: \`claude-opus\` (قوی، پرمصرف)، \`claude-sonnet\` (متعادل)، \`claude-haiku\` (سریع، کم‌مصرف). لیست دقیق مدل‌های مجاز *شما* را از \`GET /v1/models\` بگیرید.

### ۶. خطاها

| کد | معنی | چه کنیم |
|---|---|---|
| \`401\` | کلید نامعتبر یا باطل‌شده | کلید جدید بسازید |
| \`403 model_not_allowed\` | مدل برای شما مجاز نیست | از مدل مجاز استفاده کنید یا از ادمین بخواهید |
| \`429 quota_exceeded\` | سهمیهٔ دورهٔ شما تمام شده | تا شروع دورهٔ بعد صبر کنید یا سهمیهٔ موقت بگیرید |
| \`429 upstream_rate_limited\` | سرویس بالادستی موقتاً شلوغ است | کمی بعد دوباره تلاش کنید |

بدنهٔ خطا: \`{"error": {"code": "...", "message": "پیام فارسی"}}\`

### ۷. سقف مصرف
مصرف بر اساس «امتیاز» است: توکن ورودی/خروجی × ضریب مدل. وضعیت لحظه‌ای را در **«مصرف من»** ببینید؛ در ۸۰٪ سهمیه هشدار می‌گیرید و پس از اتمام، درخواست‌ها تا دورهٔ بعد با \`429\` رد می‌شوند.
`;
