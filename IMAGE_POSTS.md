# Image post mode

Video o'rniga qora fon + oq matnli rasm postlar yaratish mumkin.

`config.json`:

```json
{
  "image_posts": {
    "enabled": true,
    "dir": "generated_posts",
    "template": "post_{number:03d}.png",
    "text_template": "{number} post",
    "background": "#000000",
    "foreground": "#ffffff"
  },
  "posting": {
    "caption_template": "{number} post {hashtags}"
  }
}
```

Ishlatish:

```bash
python instagram_browser_poster.py --batch-now --start-number 1 --count 20 --delay-seconds 10 --action-delay 0.5
```

Bot har raqam uchun `generated_posts/post_001.png`, `post_002.png` kabi rasm yaratadi va upload qiladi.
