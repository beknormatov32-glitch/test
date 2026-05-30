# Tez ishlatish

## 1. Muhitni tayyorlash
```bash
pip install -r requirements.txt
```

## 2. Parolni xavfsiz berish
Parolni `config.json` ichiga yozmasdan terminalda env orqali bering:

```bash
export IG_PASSWORD='instagram_parolingiz'
```

## 3. Tekshirish
Haqiqiy post joylamasdan schedule va captionlarni ko'rish:

```bash
python3 instagram_reels_poster.py --preview
python3 instagram_reels_poster.py --dry-run --once 1
```

## 4. Bitta test post
```bash
python3 instagram_reels_poster.py --test
```

## 5. Kunlik schedule bilan ishga tushirish
```bash
python3 instagram_reels_poster.py
```

To'xtatish: terminalda `Ctrl+C`.

## Browser orqali ishlatish
Agar `instagrapi` login challenge bersa, Chrome orqali manual login qiling:

```bash
python instagram_browser_poster.py --once 1 --manual-share
```

Chrome ochiladi. Instagram login, SMS yoki challenge bo'lsa o'zingiz kiritasiz.
Login tugagach terminalda `Enter` bosing. Script video va captionni tayyorlaydi.

To'liq schedule bilan:

```bash
python instagram_browser_poster.py
```

Hozirdan boshlab har 29 minutda avtomatik yuklash:

```bash
python instagram_browser_poster.py --start-now
```

Bu Chrome profilini `chrome_profile` papkasida saqlaydi, keyingi safar login qolishi mumkin.

## Telegram bot orqali boshqarish
Bot tokenni terminal env orqali bering:

```bash
export TELEGRAM_BOT_TOKEN='BOT_TOKEN'
python telegram_bot.py
```

Telegram commandlar:

```text
/status
/once 4
/batch 4 47
/batch 4 47 10
/auto
/auto 29
/stop
/logs
```

Birinchi yozgan Telegram chat admin sifatida saqlanadi.

## Foydali buyruqlar
```bash
python3 instagram_reels_poster.py --help
python3 instagram_reels_poster.py --once 7
python3 instagram_reels_poster.py --dry-run --test
python instagram_browser_poster.py --preview
python instagram_browser_poster.py --once 1 --manual-share
python instagram_browser_poster.py --once 2
python instagram_browser_poster.py --start-now
```

## Muhim eslatma
Ko'p post joylash Instagram limitlari va akkaunt cheklovlariga olib kelishi mumkin. Avval `--preview` va `--dry-run` bilan tekshiring, keyin kichik limitdan boshlang.
