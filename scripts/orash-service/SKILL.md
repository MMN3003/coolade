---
name: eco-svc-tosee-hesabdari
description: گزارش‌گیری از دیتابیس حسابداری توسعه ایمن (نرم‌افزار اوراش/آرمون روی SQL Server). تراز آزمایشی، مانده حساب اشخاص، گردش حساب، دفتر معین، فاکتور و دریافت/پرداخت. Use whenever the user asks for a حسابداری/مالی report of توسعه ایمن: تراز آزمایشی, مانده حساب, گردش, دفتر, سود و زیان, بدهکار/بستانکار, مانده شخص یا پرسنل.
---

# حسابداری توسعه ایمن (اوراش)

این سرویس فقط‌خواندنی به دیتابیس نرم‌افزار حسابداری **اوراش/آرمون** شرکت «توسعه ایمن» وصل است (SQL Server، دیتابیس اصلی `Orash1`). سه ابزار داری: `list_tables`، `describe_table`، و `run_query` (فقط یک `SELECT`). همهٔ مبالغ به **ریال** است. تاریخ‌ها **شمسی و از نوع متن** (varchar) با قالب `YYYY/MM/DD` هستند.

## قواعد کوئری‌نویسی (مهم)
- فقط `SELECT` تک‌statement. برای محدودسازی از `TOP` استفاده کن (نه LIMIT).
- مبالغ بزرگ‌اند؛ برای خوانایی در گزارش، تقسیم بر ۱۰٬۰۰۰٬۰۰۰ = میلیون تومان.
- گزارش دوره‌ای را همیشه با `FYearIdRef` فیلتر کن.

## دوره‌های مالی (جدول `dbo.FinanceYear`)
| FYearIdRef | دوره | بازه |
|---|---|---|
| 10 | ۱۴۰۲ | 1402/01/01 تا 1402/12/29 |
| 11 | ۱۴۰۳ | 1403 |
| 12 | ۱۴۰۴ | 1404 |
| 13 | ۱۴۰۵ | جاری |

## ساختار سند حسابداری
- `dbo.AccTransactionHdr` — سرسند: `HdrID`، `Date` (شمسی، متن)، `AccNo` (شمارهٔ سند)، `Description`، `FYearIdRef`.
- `dbo.AccTransactionITM` — ردیف‌های سند: `HdrIdRef` (به سرسند)، `Debit`، `Credit`، و کدینگ حساب:
  - `KlCodeRef` = کد **کل** (متن) → جدول `dbo.Kl(Code, Name)`
  - `MnCodeRef` = کد **معین** (متن) → جدول `dbo.MN`
  - `TfCodeRef` = کد **تفصیلی** (عدد) → معمولاً برابر `dbo.Person.Code`
- کدینگ استاندارد ایران: 1xx دارایی جاری، 2xx دارایی غیرجاری، 3xx بدهی جاری، 4xx بدهی بلندمدت، 5xx حقوق صاحبان سهام، 6xx درآمد، 7xx هزینه، 8xx سایر، 9xx بهای تمام‌شده/انتظامی/افتتاحیه.

## دستور کارهای آماده

### تراز آزمایشی یک دوره (سطح کل)
```sql
SELECT i.KlCodeRef AS code, k.Name AS name,
  SUM(i.Debit) AS debit_turnover, SUM(i.Credit) AS credit_turnover
FROM dbo.AccTransactionITM i
JOIN dbo.AccTransactionHdr h ON h.HdrID = i.HdrIdRef
LEFT JOIN dbo.Kl k ON CAST(k.Code AS VARCHAR(50)) = i.KlCodeRef
WHERE h.FYearIdRef = 12            -- ۱۴۰۴
GROUP BY i.KlCodeRef, k.Name
ORDER BY i.KlCodeRef
```
مانده هر ردیف = گردش بدهکار منهای بستانکار (مثبت=بدهکار، منفی=بستانکار). جمع گردش بدهکار باید با بستانکار برابر شود.

### مانده حساب یک شخص/پرسنل
اول کد تفصیلی را پیدا کن:
```sql
SELECT Code, Name, KlCodeRef, MnCodeRef FROM dbo.Person
WHERE Name LIKE N'%<نام>%' OR LName LIKE N'%<نام>%'
```
سپس مانده (کل دوره‌ها = مانده جاری دفتر):
```sql
SELECT SUM(Debit) AS debit, SUM(Credit) AS credit, SUM(Debit)-SUM(Credit) AS balance
FROM dbo.AccTransactionITM WHERE TfCodeRef = <کد تفصیلی>
```
مثبت=بدهکار (به شرکت بدهکار است)، منفی=بستانکار (شرکت به او بدهکار است). برای یک دورهٔ خاص، با join به Hdr روی `FYearIdRef` فیلتر کن.

### گردش/دفتر یک حساب در یک دوره (ریز اسناد)
```sql
SELECT h.[Date] AS dt, h.AccNo, i.Description, i.Debit, i.Credit
FROM dbo.AccTransactionITM i
JOIN dbo.AccTransactionHdr h ON h.HdrID = i.HdrIdRef
WHERE i.TfCodeRef = <کد> AND h.FYearIdRef = 13
ORDER BY h.[Date], h.AccNo
```

## جدول‌های پرکاربرد دیگر
- `dbo.Factor_HDR` / `Factor_ITM` — فاکتور فروش/خرید.
- `dbo.RecievePayment_HDR` / `_ITM` — دریافت و پرداخت و چک.
- `dbo.Turnoveraccount` — خزانه‌داری (دریافت/پرداخت).
- اسکیمای `Sala` — حقوق و دستمزد، `AST` — اموال و دارایی ثابت، `SLM` — فروش، `ORD` — سفارش.

اگر ساختار جدولی را نمی‌دانی، اول `describe_table` را صدا بزن. برای کشف نام جدول‌ها `list_tables`.
