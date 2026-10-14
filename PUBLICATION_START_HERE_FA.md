# CareerPilot AI v1.0.0-local | بسته انتشار GitHub و پورتفولیو

## هدف بسته

این پوشه نسخه **انتخاب‌شده و تمیزِ کد پروژه** برای یک مخزن جدید GitHub است. تنظیمات API شخصی و دیتابیس ویندوز عمداً در آن وجود ندارند.

- `README.md`: صفحه اصلی حرفه‌ای پروژه.
- `docs/architecture.md` و `docs/assets/architecture.svg`: معماری سیستم و مرزهای اعتماد.
- `docs/setup-windows.md`: نصب از روی مخزن تازه.
- `SECURITY.md`: شرایط استفاده محلی، داده‌های خصوصی، تهدیدها و محدودیت‌ها.
- `docs/github-release-notes.md`: متن آماده Release نسخه `v1.0.0-local`.
- `docs/portfolio-copy.md`: متن آماده پورتفولیو، رزومه و پست لینکدین.
- `docs/publish-to-github-fa.md`: راهنمای دقیق انتشار امن GitHub به فارسی.
- `docs/release-checklist.md`: چک‌لیست امنیت و انتشار.
- `.github/workflows/ci.yml`: تست CI در GitHub Actions؛ بعد از انتشار باید اجرای واقعی‌اش بررسی شود.

## نکات امنیتی

۱. از پوشه توسعه قدیمی با تمام فایل‌های فازها و مسیرهای شخصی مستقیماً `git add .` نکنید. این بسته تمیز را در پوشه‌ای **جدید** استخراج کنید.

۲. فایل `.env`، دیتابیس محلی، بکاپ و رزومه خصوصی را هرگز به مخزن جدید منتقل نکنید.

۳. تصاویر پیوست از داشبورد واقعی برش خورده‌اند؛ قبل از عمومی‌کردن مخزن آن‌ها را یک‌به‌یک بررسی کنید.

۴. License هنوز انتخاب نشده؛ اگر قصد اجازه استفاده مجدد می‌دهید، ابتدا نوع مجوز را تعیین کنید.

۵. این برنامه فقط روی localhost و برای یک کاربر طراحی شده؛ انتشار سرویس عمومی از نظر امنیتی تأیید نشده است.

## نصب کد تمیز برای یک مخزن جدید

```powershell
$dest = "$env:USERPROFILE\Documents\careerpilot-ai-public"
New-Item -ItemType Directory -Force -Path $dest
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\CareerPilot_AI_v1_0_GitHub_Source_Clean.zip" -DestinationPath $dest -Force
Set-Location $dest
```

سپس `docs/publish-to-github-fa.md` را بخوانید. قدم بعدی ایجاد مخزن Private و بررسی کامل `git diff --cached --name-only` پیش از نخستین commit است.

## مستندات روی نصب اصلی

اگر فقط می‌خواهید README و دیاگرام و راهنماها داخل نسخه زنده ویندوز هم به‌روزرسانی شوند، بسته **Docs Overlay** جداگانه را روی پروژه اصلی استخراج کنید. اجرای Backend یا دیتابیس با آن تغییر نمی‌کند.
