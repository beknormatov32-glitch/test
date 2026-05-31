#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export a logged-in Instagram Playwright storage state from local Chrome profile."""

import argparse
import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chrome_path() -> str | None:
    env_path = os.getenv("CHROME_PATH")
    candidates = [env_path] if env_path else []
    candidates.extend(DEFAULT_CHROME_PATHS)
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Instagram storage_state.json")
    parser.add_argument("--profile-dir", default=str(BASE_DIR / "chrome_profile"))
    parser.add_argument("--output", default=str(BASE_DIR / "storage_state.json"))
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        launch_options = {
            "user_data_dir": str(profile_dir),
            "headless": args.headless,
            "viewport": {"width": 1280, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        chrome_path = find_chrome_path()
        if chrome_path:
            launch_options["executable_path"] = chrome_path
            print(f"Using browser executable: {chrome_path}")
        else:
            print("Using Playwright bundled Chromium. If it fails, run: python -m playwright install chromium")
        context = playwright.chromium.launch_persistent_context(**launch_options)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
        print("Instagram ochildi. Agar login so'rasa, login qiling.")
        input("Profil/home ochilganidan keyin Enter bosing: ")
        context.storage_state(path=str(output))
        context.close()

    print(f"Storage state saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
