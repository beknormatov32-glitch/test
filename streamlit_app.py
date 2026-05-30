#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Streamlit control panel for Instagram browser automation."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
POSTER = BASE_DIR / "instagram_browser_poster.py"
LOG_FILE = Path(os.getenv("INSTAGRAM_LOG_FILE", BASE_DIR / "instagram_poster.log"))
JSON_LOG = Path(os.getenv("INSTAGRAM_JSON_LOG", BASE_DIR / "posts_log.json"))


def init_state() -> None:
    st.session_state.setdefault("process", None)
    st.session_state.setdefault("last_command", "")
    st.session_state.setdefault("started_at", None)


def process_running() -> bool:
    process: Optional[subprocess.Popen] = st.session_state.get("process")
    return bool(process and process.poll() is None)


def start_process(args: list[str]) -> None:
    if process_running():
        st.warning("Oldingi jarayon hali ishlayapti. Avval Stop bosing.")
        return

    command = [sys.executable, str(POSTER), *args]
    if os.getenv("POSTER_HEADLESS", "").lower() in {"1", "true", "yes"} and "--headless" not in command:
        command.append("--headless")

    log_path = BASE_DIR / "streamlit_process.log"
    log_file = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    st.session_state["process"] = process
    st.session_state["last_command"] = " ".join(args)
    st.session_state["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    st.success("Jarayon boshlandi: " + " ".join(args))


def stop_process() -> None:
    process: Optional[subprocess.Popen] = st.session_state.get("process")
    if not process or process.poll() is not None:
        st.info("Aktiv jarayon yo'q.")
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        process.wait(timeout=10)
    except Exception:
        process.terminate()
    st.success("Jarayon to'xtatildi.")


def tail_file(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return "Fayl hali yo'q."
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:]) or "Fayl bo'sh."


def main() -> None:
    st.set_page_config(page_title="Instagram Automation", page_icon="IG", layout="wide")
    init_state()

    st.title("Instagram Automation Control Panel")
    st.caption("Streamlit sinov paneli. 24/7 ishonchlilik uchun VPS yaxshiroq.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", "Running" if process_running() else "Stopped")
    with col2:
        st.metric("Last command", st.session_state.get("last_command") or "-")
    with col3:
        st.metric("Started at", st.session_state.get("started_at") or "-")

    st.divider()

    tab_once, tab_batch, tab_auto, tab_logs = st.tabs(["Once", "Batch", "Auto", "Logs"])

    with tab_once:
        number = st.number_input("Reel number", min_value=1, max_value=999, value=1, step=1)
        manual = st.checkbox("Manual Share", value=False, key="once_manual")
        if st.button("Upload once", type="primary"):
            args = ["--once", str(number)]
            if manual:
                args.append("--manual-share")
            start_process(args)

    with tab_batch:
        start_number = st.number_input("Start number", min_value=1, max_value=999, value=1, step=1)
        count = st.number_input("Count", min_value=1, max_value=999, value=10, step=1)
        delay = st.number_input("Delay seconds", min_value=0, max_value=3600, value=5, step=1)
        manual_batch = st.checkbox("Manual Share", value=False, key="batch_manual")
        if st.button("Start batch", type="primary"):
            args = [
                "--batch-now",
                "--start-number",
                str(start_number),
                "--count",
                str(count),
                "--delay-seconds",
                str(delay),
            ]
            if manual_batch:
                args.append("--manual-share")
            start_process(args)

    with tab_auto:
        interval = st.number_input("Interval minutes", min_value=1, max_value=1440, value=29, step=1)
        if st.button("Start auto interval", type="primary"):
            start_process(["--start-now", "--interval-minutes", str(interval)])
        if st.button("Stop", type="secondary"):
            stop_process()

    with tab_logs:
        c1, c2, c3 = st.columns([1, 1, 1])
        if c1.button("Refresh logs"):
            st.rerun()
        if c2.button("Stop process"):
            stop_process()
        if c3.button("Clear Streamlit process state"):
            st.session_state["process"] = None
            st.rerun()

        st.subheader("instagram_poster.log")
        st.code(tail_file(LOG_FILE, 100), language="text")

        st.subheader("posts_log.json")
        st.code(tail_file(JSON_LOG, 60), language="json")

        process_log = BASE_DIR / "streamlit_process.log"
        st.subheader("streamlit_process.log")
        st.code(tail_file(process_log, 100), language="text")


if __name__ == "__main__":
    main()
