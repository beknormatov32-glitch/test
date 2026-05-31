FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV POSTER_HEADLESS=true
ENV BROWSER_PROFILE_DIR=/data/chrome_profile
ENV BROWSER_DEBUG_DIR=/data/debug
ENV INSTAGRAM_LOG_FILE=/data/instagram_poster.log
ENV INSTAGRAM_JSON_LOG=/data/posts_log.json
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

CMD ["python", "telegram_bot.py"]
