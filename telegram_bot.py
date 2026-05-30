#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram controller for the browser-assisted Instagram poster."""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import requests


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "telegram_bot_state.json"
POSTER = BASE_DIR / "instagram_browser_poster.py"
LOG_FILE = BASE_DIR / "instagram_poster.log"


class TelegramPosterBot:
    def __init__(self, token: str):
        self.token = token
        self.api = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.state = self.load_state()
        self.process: Optional[subprocess.Popen] = None
        self.process_output: list[str] = []

    def load_state(self) -> dict[str, Any]:
        if STATE_FILE.exists():
            with STATE_FILE.open("r", encoding="utf-8") as file:
                return json.load(file)
        return {"admin_chat_id": os.getenv("TELEGRAM_ADMIN_CHAT_ID")}

    def save_state(self) -> None:
        with STATE_FILE.open("w", encoding="utf-8") as file:
            json.dump(self.state, file, ensure_ascii=False, indent=2)

    def request(self, method: str, **params: Any) -> dict[str, Any]:
        response = requests.post(f"{self.api}/{method}", json=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data)
        return data

    def send(self, chat_id: int, text: str) -> None:
        self.request("sendMessage", chat_id=chat_id, text=text[-3900:])

    def is_admin(self, chat_id: int) -> bool:
        admin = self.state.get("admin_chat_id")
        if not admin:
            self.state["admin_chat_id"] = str(chat_id)
            self.save_state()
            self.send(chat_id, "Admin sifatida ulandingiz. Endi bot faqat sizning commandlaringizni bajaradi.")
            return True
        return str(chat_id) == str(admin)

    def poll(self) -> None:
        print("Telegram bot started. Press Ctrl+C to stop.")
        while True:
            try:
                updates = self.request("getUpdates", offset=self.offset, timeout=30).get("result", [])
                for update in updates:
                    self.offset = max(self.offset, update["update_id"] + 1)
                    message = update.get("message") or update.get("edited_message")
                    if message:
                        self.handle_message(message)
            except KeyboardInterrupt:
                self.stop_process()
                print("Stopped.")
                return
            except Exception as exc:
                print(f"Polling error: {exc}")
                time.sleep(5)

    def handle_message(self, message: dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        if not text:
            return
        if not self.is_admin(chat_id):
            self.send(chat_id, "Ruxsat yo'q.")
            return

        parts = text.split()
        command = parts[0].split("@", 1)[0].lower()

        try:
            if command in {"/start", "/help"}:
                self.send(chat_id, self.help_text())
            elif command == "/whoami":
                self.send(chat_id, f"chat_id: {chat_id}")
            elif command == "/status":
                self.send(chat_id, self.status_text())
            elif command == "/logs":
                self.send(chat_id, self.tail_logs())
            elif command == "/stop":
                self.stop_process()
                self.send(chat_id, "Jarayon to'xtatildi.")
            elif command == "/once":
                number = int(parts[1]) if len(parts) > 1 else 1
                self.start_process(chat_id, ["--once", str(number)])
            elif command == "/batch":
                start = int(parts[1]) if len(parts) > 1 else 1
                count = int(parts[2]) if len(parts) > 2 else 50
                delay = int(parts[3]) if len(parts) > 3 else 5
                self.start_process(chat_id, ["--batch-now", "--start-number", str(start), "--count", str(count), "--delay-seconds", str(delay)])
            elif command == "/auto":
                interval = int(parts[1]) if len(parts) > 1 else 29
                self.start_process(chat_id, ["--start-now", "--interval-minutes", str(interval)])
            else:
                self.send(chat_id, "Noma'lum command. /help ni bosing.")
        except (IndexError, ValueError):
            self.send(chat_id, "Command formati noto'g'ri. /help ni bosing.")
        except Exception as exc:
            self.send(chat_id, f"Xato: {exc}")

    def help_text(self) -> str:
        return (
            "Instagram automation controller\n\n"
            "/status - jarayon holati\n"
            "/once 4 - bitta reel chiqarish\n"
            "/batch 4 47 - 4 dan boshlab 47 ta reel chiqarish\n"
            "/batch 4 47 10 - 10 sekund delay bilan batch\n"
            "/auto - hozir boshlash, keyin har 29 minut\n"
            "/auto 15 - hozir boshlash, keyin har 15 minut\n"
            "/stop - jarayonni to'xtatish\n"
            "/logs - oxirgi loglar\n"
            "/whoami - chat id"
        )

    def status_text(self) -> str:
        if self.process and self.process.poll() is None:
            return f"Ishlayapti. PID: {self.process.pid}\n\n{self.last_output()}"
        if self.process:
            return f"To'xtagan. Exit code: {self.process.poll()}\n\n{self.last_output()}"
        return "Hozir aktiv jarayon yo'q."

    def tail_logs(self, limit: int = 40) -> str:
        if not LOG_FILE.exists():
            return "Log file hali yo'q."
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:]) or "Log bo'sh."

    def last_output(self) -> str:
        return "\n".join(self.process_output[-20:]) or "Hali output yo'q."

    def start_process(self, chat_id: int, args: list[str]) -> None:
        if self.process and self.process.poll() is None:
            self.send(chat_id, "Oldingi jarayon hali ishlayapti. Avval /stop bosing.")
            return

        command = [sys.executable, str(POSTER), *args]
        if os.getenv("POSTER_HEADLESS", "").lower() in {"1", "true", "yes"} and "--headless" not in command:
            command.append("--headless")
        self.process_output = []
        self.process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        threading.Thread(target=self.read_process_output, args=(chat_id,), daemon=True).start()
        self.send(chat_id, "Jarayon boshlandi:\n" + " ".join(args))

    def read_process_output(self, chat_id: int) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            clean = line.rstrip()
            self.process_output.append(clean)
            if any(marker in clean for marker in ["Share clicked", "Done clicked", "Batch completed", "Batch stopped", "ERROR", "failed"]):
                self.send(chat_id, clean)
        code = self.process.wait()
        self.send(chat_id, f"Jarayon tugadi. Exit code: {code}")

    def stop_process(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
            self.process.wait(timeout=10)
        except Exception:
            self.process.terminate()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram controller for Instagram browser poster")
    parser.add_argument("--token", help="Telegram bot token. Prefer TELEGRAM_BOT_TOKEN env.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN env kerak.", file=sys.stderr)
        return 1
    TelegramPosterBot(token).poll()
    return 0


if __name__ == "__main__":
    sys.exit(main())
