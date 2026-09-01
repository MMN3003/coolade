# لایهٔ فشرده‌سازی توکن (اختیاری)

پروکسی معکوسِ استریمی که بین Claude Code CLI و سرویس بالادستی می‌نشیند تا مصرف توکن
را کم کند، بدون خروج از اشتراک.

**پیش‌فرض: خاموش.** با `COMPRESS=0` این پروکسی درخواست‌ها را **دست‌نخورده** عبور می‌دهد
(pass-through امن). فعال‌کردن profile به‌تنهایی رفتار مدل را عوض نمی‌کند.

## فعال‌سازی
```bash
docker compose --profile compression up -d compression
```
سپس در `.env`:
```
UPSTREAM_BASE_URL=http://compression:8788
```
تا CLI ترافیک را از این پروکسی رد کند (CLI مقدار `ANTHROPIC_BASE_URL` را از
`UPSTREAM_BASE_URL` می‌گیرد).

## پیاده‌سازی فشرده‌سازی واقعی
تابع `_maybe_compress` در [proxy.py](proxy.py) نقطهٔ اتصال است. یک compressor واقعی
(مثل LLMLingua به‌صورت sidecar یا قواعد سبک شبیه tamp) را اینجا وصل کنید و `COMPRESS=1`
بگذارید.

> ⚠️ **هشدار prompt caching:** هر تغییر در بدنهٔ درخواست، پیشوندِ بایتیِ کش Anthropic را
> عوض می‌کند؛ یک compressor نادقیق می‌تواند با busting کش، هزینه را **بالا** ببرد.
> قبل از فعال‌کردن در production حتماً روی ترافیک واقعی اندازه‌گیری کنید. به همین دلیل
> این ماژول به‌صورت scaffoldِ خاموش‌به‌پیش‌فرض ارائه شده است.
