#!/usr/bin/env bash
# جاب موقت تازه‌سازی توکن اکانت Claude-سازگار روی هاست.
#
# چرا لازم است: توکن دسترسی حدود ۸ ساعت اعتبار دارد. اگر مدتی هیچ‌کس CLI را
# اجرا نکند، access token منقضی می‌شود و در بدترین حالت refresh token هم باطل
# می‌شود و گیت‌وی می‌میرد تا وقتی یک انسان `claude /login` بزند.
#
# این اسکریپت با یک درخواست ناچیز، CLI را وادار می‌کند توکن را (در صورت نزدیک
# بودن به انقضا) refresh کند و فایل ~/.claude/.credentials.json را به‌روز بنویسد.
# گیت‌وی هر ۶۰ ثانیه از همین فایل sync می‌کند، پس اتصالش همیشه سبز می‌ماند.
#
# نکته: این راه‌حل موقت است. راه‌حل دائمی = بک‌اند خودش چرخهٔ refresh را در دست
# بگیرد (TECH.md اصلاحیهٔ ۲، در حال پیاده‌سازی). بعد از آن این جاب قابل حذف است.
set -u

export HOME=/home/amin
LOG=/home/amin/ai/Coolade/scripts/refresh-claude-token.log
TS="$(date -Is)"

# ارزان‌ترین مدل، کوتاه‌ترین خروجی — فقط برای فعال‌کردن مسیر refresh.
OUT="$(cd "$HOME" && timeout 120 claude -p --model claude-haiku-4-5-20251001 "ok" 2>&1)"
RC=$?

# انقضای فعلی توکن را برای پایش لاگ کن.
EXP="$(python3 - <<'PY' 2>/dev/null
import json, datetime
try:
    d = json.load(open("/home/amin/.claude/.credentials.json"))["claudeAiOauth"]
    print(datetime.datetime.fromtimestamp(d["expiresAt"]/1000).isoformat())
except Exception as e:
    print(f"parse-error:{e}")
PY
)"

if [ $RC -eq 0 ]; then
  echo "$TS  OK   rc=$RC  expiresAt=$EXP" >> "$LOG"
else
  echo "$TS  FAIL rc=$RC  expiresAt=$EXP  out=${OUT:0:200}" >> "$LOG"
fi

# لاگ را کوتاه نگه دار (آخرین ۵۰۰ خط).
tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
exit $RC
