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
import zipfile
from pathlib import Path
from typing import Any, Optional

import requests


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "telegram_bot_state.json"
POSTER = BASE_DIR / "instagram_browser_poster.py"
LOG_FILE = BASE_DIR / "instagram_poster.log"
PROFILE_DIR = Path(os.getenv("BROWSER_PROFILE_DIR", BASE_DIR / "chrome_profile"))
STORAGE_STATE_PATH = Path(os.getenv("STORAGE_STATE_PATH", BASE_DIR / "storage_state.json"))


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
        if not self.is_admin(chat_id):
            self.send(chat_id, "Ruxsat yo'q.")
            return

        if message.get("document"):
            self.handle_document(chat_id, message["document"])
            return

        text = (message.get("text") or "").strip()
        if not text:
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
            elif command == "/profile":
                self.send(chat_id, self.profile_status())
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
            "/profile - Chrome profile/session holati\n"
            "Chrome profile import: Mac'dagi chrome_profile papkasini zip qilib botga document sifatida yuboring.\n"
            "/whoami - chat id"
        )

    def status_text(self) -> str:
        if self.process and self.process.poll() is None:
            return f"Ishlayapti. PID: {self.process.pid}\n\n{self.last_output()}"
        if self.process:
            return f"To'xtagan. Exit code: {self.process.poll()}\n\n{self.last_output()}"
        return "Hozir aktiv jarayon yo'q."

    def profile_status(self) -> str:
        if not PROFILE_DIR.exists():
            return f"Profile topilmadi: {PROFILE_DIR}"
        files = sum(1 for item in PROFILE_DIR.rglob("*") if item.is_file())
        size = sum(item.stat().st_size for item in PROFILE_DIR.rglob("*") if item.is_file())
        return f"Profile bor: {PROFILE_DIR}\nFiles: {files}\nSize: {size // 1024 // 1024} MB"

    def tail_logs(self, limit: int = 40) -> str:
        if not LOG_FILE.exists():
            return "Log file hali yo'q."
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:]) or "Log bo'sh."

    def last_output(self) -> str:
        return "\n".join(self.process_output[-20:]) or "Hali output yo'q."

    def handle_document(self, chat_id: int, document: dict[str, Any]) -> None:
        file_name = document.get("file_name", "")
        if file_name.endswith(".json"):
            self.handle_storage_state(chat_id, document)
            return
        if not file_name.endswith(".zip"):
            self.send(chat_id, "Faqat storage_state.json yoki .zip profile fayl qabul qilinadi.")
            return

        self.stop_process()
        self.send(chat_id, "Profile zip yuklanmoqda...")
        file_id = document["file_id"]
        file_info = self.request("getFile", file_id=file_id)["result"]
        file_path = file_info["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        response = requests.get(url, timeout=300)
        response.raise_for_status()

        tmp_zip = BASE_DIR / "profile_upload.zip"
        tmp_zip.write_bytes(response.content)
        self.import_profile_zip(tmp_zip)
        tmp_zip.unlink(missing_ok=True)
        self.send(chat_id, "Profile import qilindi.\n" + self.profile_status() + "\nEndi /once 1 bilan test qiling.")

    def handle_storage_state(self, chat_id: int, document: dict[str, Any]) -> None:
        self.stop_process()
        self.send(chat_id, "storage_state.json yuklanmoqda...")
        file_id = document["file_id"]
        file_info = self.request("getFile", file_id=file_id)["result"]
        file_path = file_info["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        response = requests.get(url, timeout=120)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict) or "cookies" not in data:
            raise RuntimeError("Bu Playwright storage_state.json fayliga o'xshamayapti")

        STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STORAGE_STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.send(chat_id, f"storage_state import qilindi: {STORAGE_STATE_PATH}\nEndi /once 1 bilan test qiling.")

    def import_profile_zip(self, zip_path: Path) -> None:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        for child in PROFILE_DIR.iterdir():
            if child.is_dir():
                self.remove_tree(child)
            else:
                child.unlink(missing_ok=True)

        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            common_prefix = self.detect_common_prefix([member.filename for member in members])
            for member in members:
                if member.is_dir():
                    continue
                name = member.filename
                if common_prefix and name.startswith(common_prefix):
                    name = name[len(common_prefix):]
                target = PROFILE_DIR / name
                target = target.resolve()
                if not str(target).startswith(str(PROFILE_DIR.resolve())):
                    raise RuntimeError("Unsafe zip path detected")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source:
                    target.write_bytes(source.read())

    def detect_common_prefix(self, names: list[str]) -> str:
        clean = [name for name in names if name and "/" in name]
        if not clean:
            return ""
        first_parts = clean[0].split("/")
        if first_parts[0] in {"chrome_profile", "Default"}:
            return first_parts[0] + "/"
        return ""

    def remove_tree(self, path: Path) -> None:
        for child in path.iterdir():
            if child.is_dir():
                self.remove_tree(child)
            else:
                child.unlink(missing_ok=True)
        path.rmdir()

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
