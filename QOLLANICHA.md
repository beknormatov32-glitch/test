# Instagram Reels Poster qo'llanma

Bu loyiha bitta videoni Instagram Reels sifatida reja bo'yicha joylash uchun CLI script.

## O'rnatish
```bash
cd "/Users/ogabeknormatov/Desktop/Instagram automation"
source venv/bin/activate
pip install -r requirements.txt
```

## Config
Asosiy sozlamalar `config.json` faylida:

- `instagram.username` - Instagram username
- `instagram.password_env` - parol olinadigan env nomi, default `IG_PASSWORD`
- `video.path` - mp4 video yo'li
- `posting.posts_per_day` - kunlik post soni
- `posting.caption_template` - caption shabloni
- `posting.start_time` / `posting.end_time` - vaqt oralig'i

Parolni faylga yozish tavsiya qilinmaydi. Terminalda shunday bering:

```bash
export IG_PASSWORD='instagram_parolingiz'
```

## Tekshirish
Haqiqiy upload qilmasdan:

```bash
python3 instagram_reels_poster.py --preview
python3 instagram_reels_poster.py --dry-run --once 1
```

## Ishlatish
Bitta test reel:

```bash
python3 instagram_reels_poster.py --test
```

Bitta raqamli reel:

```bash
python3 instagram_reels_poster.py --once 7
```

Kunlik scheduler:

```bash
python3 instagram_reels_poster.py
```

## Loglar
- `instagram_poster.log` - asosiy log
- `posts_log.json` - upload natijalari
- `session.json` - instagrapi session sozlamalari

## Eslatma
Instagram ko'p avtomatik post joylashni cheklashi mumkin. Avval kichik limit bilan tekshiring va `--dry-run`dan foydalaning.
