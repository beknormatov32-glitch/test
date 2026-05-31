#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export a logged-in Instagram Playwright storage state from local Chrome profile."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent


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
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=args.headless,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
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
