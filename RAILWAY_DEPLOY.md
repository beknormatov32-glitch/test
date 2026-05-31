# Railway deploy sinov

Railway bu loyiha uchun VPSdan qiyinroq, chunki Instagram login/SMS uchun browser session kerak. Shunga qaramay Telegram bot + headless Playwright container sifatida sinab ko'rish mumkin.

## Muhim cheklov

Railway containerda GUI yo'q. Shuning uchun birinchi loginni Railway ichida ko'rib kiritish qiyin. Ishlashi uchun `chrome_profile` session tayyor bo'lishi yoki Instagram login challenge bermasligi kerak. Eng stabil variant VPS + noVNC.

## 1. Railway project

1. Railway dashboard oching
2. New Project
3. Deploy from GitHub repo yoki Railway CLI orqali deploy
4. Dockerfile sifatida `Dockerfile.railway` ishlatiladi

Railway Playwright Docker deployni qo'llaydi: https://docs.railway.com/guides/playwright

## 2. Volume

Railway servicega volume qo'shing va mount path:

```text
/data
```

Bu yerda saqlanadi:

```text
/data/chrome_profile
/data/instagram_poster.log
/data/posts_log.json
/data/debug
```

Railway volume docs: https://docs.railway.com/volumes

## 3. Variables

Railway Variables:

```text
TELEGRAM_BOT_TOKEN=your_bot_token
POSTER_HEADLESS=true
BROWSER_PROFILE_DIR=/data/chrome_profile
BROWSER_DEBUG_DIR=/data/debug
INSTAGRAM_LOG_FILE=/data/instagram_poster.log
INSTAGRAM_JSON_LOG=/data/posts_log.json
STORAGE_STATE_PATH=/data/storage_state.json
```

## 4. Deploy

Railway CLI bilan:

```bash
railway login
railway init
railway up
```

Yoki GitHubga push qilib Railway dashboarddan deploy qiling.

## 5. Telegram commandlar

```text
/start
/status
/logs
/once 6
/batch 6 45
/auto
/stop
```

## Login/session import qilish

Railwayda browser ko'rinmaydi. Shuning uchun local Mac'dan session export qiling:

```bash
cd "/Users/ogabeknormatov/Desktop/Instagram automation"
source venv/bin/activate
python export_instagram_state.py
```

Bu `storage_state.json` yaratadi. Shu faylni Telegram botga document qilib yuboring. Bot uni `/data/storage_state.json`ga saqlaydi. Keyin:

```text
/once 1
```

## Agar login/session ishlamasa

Railwayda GUI yo'qligi sabab Instagram login challenge chiqsa, VPS kerak bo'ladi. Railway sinovi asosan session saqlangan va headless upload ishlaydigan holatlar uchun.
