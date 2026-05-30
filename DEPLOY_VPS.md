# VPS deploy

Bu deploy varianti botni VPSda 24/7 ishlatadi. Instagram Web login uchun bir marta browser oynasiga kirish kerak bo'ladi, shuning uchun VPSda `xvfb` + `x11vnc` ishlatiladi.

## 1. VPS talablar

- Ubuntu 22.04/24.04
- 2 GB RAM yoki ko'proq
- Python 3.10+
- Root yoki sudo access

## 2. Loyihani VPSga yuborish

MacBookdan:

```bash
scp -r "/Users/ogabeknormatov/Desktop/Instagram automation" root@VPS_IP:/opt/instagram-automation
```

VPSda:

```bash
cd /opt/instagram-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 3. Linux dependencylar

```bash
apt update
apt install -y xvfb x11vnc fluxbox novnc websockify
python -m playwright install-deps chromium
```

## 4. VNC display ochish

VPSda:

```bash
Xvfb :99 -screen 0 1280x900x24 &
export DISPLAY=:99
fluxbox &
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &
```

Brauzerni login uchun ochish:

```bash
cd /opt/instagram-automation
source venv/bin/activate
DISPLAY=:99 python instagram_browser_poster.py --once 1 --manual-share
```

Keyin browserda login qilish uchun:

```text
http://VPS_IP:6080/vnc.html
```

Instagram login/SMS tugagach terminalda `Enter` bosing. Test postni oxirida qo'lda yoki avtomatik yakunlang.

## 5. Telegram bot service

`/etc/systemd/system/instagram-telegram-bot.service`:

```ini
[Unit]
Description=Instagram Telegram Automation Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/instagram-automation
Environment=DISPLAY=:99
Environment=TELEGRAM_BOT_TOKEN=BOT_TOKEN_HERE
ExecStart=/opt/instagram-automation/venv/bin/python /opt/instagram-automation/telegram_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Service yoqish:

```bash
systemctl daemon-reload
systemctl enable instagram-telegram-bot
systemctl start instagram-telegram-bot
systemctl status instagram-telegram-bot
```

Log ko'rish:

```bash
journalctl -u instagram-telegram-bot -f
```

## 6. Telegram commandlar

```text
/status
/logs
/once 6
/batch 6 45
/auto
/stop
```

## Muhim

- VPS IP almashsa yoki yangi serverga ko'chirilsa Instagram yana verification so'rashi mumkin.
- `chrome_profile` papkasi login sessionni saqlaydi. Uni o'chirmang.
- VPSda browser oynasi uchun `DISPLAY=:99` kerak.
