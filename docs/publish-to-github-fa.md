# راهنمای انتشار امن CareerPilot AI در GitHub

## تفاوت دو بسته

- **GitHub Source (Curated):** کد و مستندات انتخاب‌شده بدون اطلاعات شخصی و راهنماهای تاریخی؛ برای مخزن جدید GitHub از **همین** بسته استفاده کنید.
- **Docs Overlay:** جایگزین README و مستندات پروژه موجود، بدون تغییر برنامه و دیتابیس. از پوشه توسعه قدیمی با `git add .` مستقیم منتشر نکنید.

## ۱. مخزن جدید

در GitHub یک مخزن ترجیحاً **Private** با نام `careerpilot-ai` بسازید. README خودکار و فایل `.gitignore` یا License خودکار را هنگام ساخت مخزن انتخاب نکنید تا با بسته تداخل نداشته باشند. پس از بررسی و پاک‌سازی می‌توانید مخزن را Public کنید.

**Description پیشنهادی:**

`Local-first AI job intelligence platform with consent-gated resume analysis, explainable matching, multi-source discovery, SQLite tracking, and human-reviewed application drafts.`

**Topics پیشنهادی:** `python`, `fastapi`, `artificial-intelligence`, `job-search`, `resume-parser`, `sqlite`, `llm`, `explainable-ai`, `docker`, `human-in-the-loop`

## ۲. کار با GitHub Source ZIP

ZIP تمیز را در پوشه **مستقل از پروژه زنده ویندوز** استخراج کنید؛ مثلاً `Documents\careerpilot-ai-public`. فایل `.env` واقعی، فایل‌های دیتابیس و Backup را به آن کپی نکنید.

```powershell
cd "$env:USERPROFILE\Documents\careerpilot-ai-public"
git init -b main
git status --short
# Confirm that only intended source/docs are present:
Get-ChildItem -Force
# .env and .sqlite3 should be absent.
git add .
git status --short
# Inspect files staged for commit:
git diff --cached --name-only
```

**اگر `.env`، رزومه، بکاپ یا فایل شخصی دیدید، همین‌جا متوقف شوید.** هرگز کلید محرمانه را در commit ثبت نکنید.

بعد از بررسی:

```powershell
git commit -m "release: CareerPilot AI v1.0.0-local"
git remote add origin https://github.com/YOUR_ACCOUNT/careerpilot-ai.git
git push -u origin main
```

`YOUR_ACCOUNT` را با نام کاربری GitHub خودتان جایگزین کنید. در صورت فعال‌بودن 2FA، از مرورگر/credential manager یا SSH استفاده کنید؛ پسورد اکانت را در متن فرمان قرار ندهید.

## ۳. تست مخزن عمومی

یک clone تازه از مخزن بگیرید و دقیقاً دستورهای `docs/setup-windows.md` را دنبال کنید. راهنمای اصلی نباید برای نصب اولیه به فایل‌های مخفی از نسخه‌های قبلی وابسته باشد. تست خودکار ۱۷۸گانه را اجرا کنید.

## ۴. Release

در GitHub بخش **Releases → Draft a new release**، tag با نام `v1.0.0-local` بسازید. عنوان و متن را از `docs/github-release-notes.md` کپی کنید. برای Release نه دیتابیس، نه Backup، نه رزومه و نه فایل `.env` آپلود نکنید.

## ۵. تصاویر، امنیت، مجوز

تصاویر بسته از اسکرین‌شات‌های کاربری برش خورده‌اند تا Chrome و بخش‌های دارای مشخصات شخصی نمایش داده نشوند؛ بااین‌حال قبل از انتشار عمومی **خودتان تک‌تک تصاویر را تأیید کنید**. اگر نمی‌خواهید سابقه مشاهده آگهی خاصی عمومی باشد، تصویر آن را حذف یا جایگزین کنید.

در بسته عمداً فایل `LICENSE` قرار نگرفته است. اگر قصد متن‌باز کردن دارید، ابتدا مجوز مناسب را خودتان انتخاب کنید؛ تا آن زمان انتشار عمومی کد الزاماً اجازه استفاده مجدد دیگران را نمی‌دهد.

## ۶. معرفی در پورتفولیو

عنوان، توضیح کوتاه/بلند، Technology Stack و رزومه بولت‌های آماده در `docs/portfolio-copy.md` وجود دارد. فقط ادعاهایی را منتشر کنید که واقعاً با کد و تست پروژه تطابق دارند.

**هشدار:** این پروژه را به‌عنوان سرویس عمومی، ارسال‌کننده خودکار درخواست استخدام یا سیستم دارای احراز هویت معرفی نکنید؛ نسخه 1.0.0 صرفاً محلی است.
