# Streamlit deploy sinov

Streamlit bu loyiha uchun control panel sifatida ishlaydi. Instagram browser automation uzoq vaqt ishlashi va login/session talab qilishi sabab 24/7 ishonchlilik VPSdan pastroq bo'lishi mumkin.

## Local run

```bash
cd "/Users/ogabeknormatov/Desktop/Instagram automation"
source venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Community Cloud

1. GitHub repo deploy qiling.
2. Main file sifatida:

```text
streamlit_app.py
```

3. Secrets/Environment variables:

```text
POSTER_HEADLESS=true
BROWSER_PROFILE_DIR=/mount-or-default/chrome_profile
BROWSER_DEBUG_DIR=/mount-or-default/debug
INSTAGRAM_LOG_FILE=/mount-or-default/instagram_poster.log
INSTAGRAM_JSON_LOG=/mount-or-default/posts_log.json
```

## Cheklov

Streamlit Cloud browser GUI bermaydi va app hibernate bo'lishi mumkin. Instagram login challenge chiqsa, bu platformada uni yechish qiyin. Local yoki VPS muhitida yaxshiroq ishlaydi.
