#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Browser-assisted Instagram Reels poster.

You log in manually in Chrome. The script then uses that same browser profile
to schedule uploads through Instagram Web.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, List, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright is not installed. Run: pip install playwright", file=sys.stderr)
    sys.exit(1)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]
logger = logging.getLogger("instagram_browser_poster")


@dataclass
class BrowserConfig:
    username: str
    video_path: Path
    image_posts_enabled: bool
    image_dir: Path
    image_template: str
    image_text_template: str
    image_bg: str
    image_fg: str
    hashtags: str
    caption_template: str
    posts_per_day: int
    start_time: str
    end_time: str
    timezone: str
    log_file: Path
    json_log: Path
    profile_dir: Path
    debug_dir: Path
    storage_state_path: Optional[Path]
    action_delay: float
    verbose: bool


def resolve_path(value: str, base_dir: Path = BASE_DIR) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def setup_logging(log_file: Path, verbose: bool) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("File logging disabled: %s", exc)


def read_config(config_path: Path) -> BrowserConfig:
    raw = load_json(config_path)
    instagram = raw.get("instagram", {})
    posting = raw.get("posting", {})
    video = raw.get("video", {})
    image_posts = raw.get("image_posts", {})
    schedule = raw.get("schedule", {})
    logging_cfg = raw.get("logging", {})
    browser_cfg = raw.get("browser", {})

    return BrowserConfig(
        username=instagram.get("username", "").strip(),
        video_path=resolve_path(video.get("path", "./video_reel1.mp4"), config_path.parent),
        image_posts_enabled=bool(image_posts.get("enabled", False)),
        image_dir=resolve_path(image_posts.get("dir", "generated_posts"), config_path.parent),
        image_template=image_posts.get("template", "post_{number:03d}.png"),
        image_text_template=image_posts.get("text_template", "{number} post"),
        image_bg=image_posts.get("background", "#000000"),
        image_fg=image_posts.get("foreground", "#ffffff"),
        hashtags=posting.get("hashtags", "#yumor").strip(),
        caption_template=posting.get("caption_template", "{number}-reels {hashtags}"),
        posts_per_day=int(posting.get("posts_per_day", 50)),
        start_time=posting.get("start_time", "00:00"),
        end_time=posting.get("end_time", "23:59"),
        timezone=schedule.get("timezone", "Asia/Tashkent"),
        log_file=resolve_path(os.getenv("INSTAGRAM_LOG_FILE") or logging_cfg.get("log_file", "instagram_poster.log"), config_path.parent),
        json_log=resolve_path(os.getenv("INSTAGRAM_JSON_LOG") or logging_cfg.get("json_log", "posts_log.json"), config_path.parent),
        profile_dir=resolve_path(os.getenv("BROWSER_PROFILE_DIR") or browser_cfg.get("profile_dir", "chrome_profile"), config_path.parent),
        debug_dir=resolve_path(os.getenv("BROWSER_DEBUG_DIR") or browser_cfg.get("debug_dir", "debug"), config_path.parent),
        storage_state_path=resolve_path(os.getenv("STORAGE_STATE_PATH"), config_path.parent) if os.getenv("STORAGE_STATE_PATH") else None,
        action_delay=float(os.getenv("BROWSER_ACTION_DELAY") or browser_cfg.get("action_delay", 0.7)),
        verbose=bool(logging_cfg.get("verbose", True)),
    )


def parse_clock(value: str) -> dt_time:
    return datetime.strptime(value, "%H:%M").time()


class InstagramBrowserPoster:
    def __init__(self, config: BrowserConfig, headless: bool = False):
        self.config = config
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.scheduler = BackgroundScheduler(timezone=config.timezone)
        self.posts_today = 0

    def pause(self, multiplier: float = 1.0) -> None:
        delay = max(0.0, self.config.action_delay * multiplier)
        if delay:
            time.sleep(delay)

    def validate(self) -> None:
        if not self.config.username:
            raise ValueError("Instagram username is missing in config.json")
        if not self.config.image_posts_enabled and not self.config.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.config.video_path}")
        if self.config.posts_per_day < 1:
            raise ValueError("posts_per_day must be at least 1")
        parse_clock(self.config.start_time)
        parse_clock(self.config.end_time)

    def start_browser(self) -> None:
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self.playwright = sync_playwright().start()
        launch_options = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        chrome_path = self.find_chrome_path()
        if chrome_path:
            launch_options["executable_path"] = chrome_path
            logger.info("Using browser executable: %s", chrome_path)
        else:
            logger.info("Using Playwright bundled Chromium.")

        if self.config.storage_state_path and self.config.storage_state_path.exists():
            logger.info("Using storage state: %s", self.config.storage_state_path)
            self.browser = self.playwright.chromium.launch(**launch_options)
            self.context = self.browser.new_context(
                storage_state=str(self.config.storage_state_path),
                viewport={"width": 1280, "height": 900},
            )
        else:
            launch_options["user_data_dir"] = str(self.config.profile_dir)
            launch_options["viewport"] = {"width": 1280, "height": 900}
            self.context = self.playwright.chromium.launch_persistent_context(**launch_options)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def find_chrome_path(self) -> Optional[str]:
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

    def close_browser(self) -> None:
        self.save_storage_state()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def save_storage_state(self) -> None:
        if not self.context or not self.config.storage_state_path:
            return
        try:
            self.config.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(self.config.storage_state_path))
            logger.info("Storage state saved: %s", self.config.storage_state_path)
        except Exception as exc:
            logger.warning("Could not save storage state: %s", exc)

    def ensure_login(self) -> None:
        self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
        logger.info("Chrome opened. Checking login state...")
        if not self.is_logged_in():
            if self.headless or not sys.stdin.isatty():
                raise RuntimeError(
                    "Instagram session is not logged in. Import storage_state.json first, "
                    "or run this script locally with a visible browser and complete login."
                )
            logger.info("Login page detected. Log in manually if needed.")
            input("Login/SMS/challenge tugagach Enter bosing: ")
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
        logger.info("Browser session ready.")
        self.save_storage_state()

    def is_logged_in(self) -> bool:
        selectors = [
            "svg[aria-label='New post']",
            "svg[aria-label='Создать']",
            "svg[aria-label='Новая публикация']",
            "a[href='/create/select/']",
            "a[href*='/direct/inbox']",
            "svg[aria-label='Home']",
            "svg[aria-label='Главная']",
        ]
        for selector in selectors:
            try:
                self.page.locator(selector).first.wait_for(state="attached", timeout=1500)
                return True
            except Exception:
                continue
        return False

    def create_caption(self, post_number: Union[int, str]) -> str:
        return self.config.caption_template.format(
            number=post_number,
            hashtags=self.config.hashtags,
            date=datetime.now().strftime("%Y-%m-%d"),
            time=datetime.now().strftime("%H:%M"),
        ).strip()

    def media_path_for(self, post_number: Union[int, str]) -> Path:
        if not self.config.image_posts_enabled:
            return self.config.video_path
        number = int(post_number) if str(post_number).isdigit() else post_number
        filename = self.config.image_template.format(number=number)
        path = self.config.image_dir / filename
        if not path.exists():
            self.generate_text_post_image(path, post_number)
        return path

    def generate_text_post_image(self, path: Path, post_number: Union[int, str]) -> None:
        if Image is None or ImageDraw is None or ImageFont is None:
            raise RuntimeError("Pillow is required for image post generation. Install pillow.")

        path.parent.mkdir(parents=True, exist_ok=True)
        width, height = 1080, 1080
        text = self.config.image_text_template.format(number=post_number)
        image = Image.new("RGB", (width, height), self.config.image_bg)
        draw = ImageDraw.Draw(image)

        font = self.load_font(190)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) / 2
        y = (height - text_height) / 2 - 20
        draw.text((x, y), text, font=font, fill=self.config.image_fg)
        image.save(path, "PNG")
        logger.info("Generated image post: %s", path)

    def load_font(self, size: int):
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()

    def click_first(self, selectors: List[str], timeout: int = 5000) -> bool:
        for selector in selectors:
            try:
                logger.debug("Trying selector: %s", selector)
                locator = self.page.locator(selector).first
                locator.wait_for(state="visible", timeout=timeout)
                locator.click(timeout=timeout)
                logger.info("Clicked selector: %s", selector)
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
        return False

    def save_debug_artifacts(self, label: str) -> None:
        try:
            self.config.debug_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot = self.config.debug_dir / f"{stamp}_{label}.png"
            html = self.config.debug_dir / f"{stamp}_{label}.html"
            self.page.screenshot(path=str(screenshot), full_page=True)
            html.write_text(self.page.content(), encoding="utf-8")
            logger.info("Debug saved: %s and %s", screenshot, html)
        except Exception as exc:
            logger.warning("Could not save debug artifacts: %s", exc)

    def upload_reel(self, post_number: Union[int, str], auto_share: bool = True) -> bool:
        caption = self.create_caption(post_number)
        media_path = self.media_path_for(post_number)
        logger.info("Starting browser upload for post %s: %s", post_number, caption)
        try:
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
            logger.info("Looking for Create button...")
            clicked = self.click_first(
                [
                    "svg[aria-label='New post']",
                    "svg[aria-label='Создать']",
                    "svg[aria-label='Новая публикация']",
                    "a[aria-label='New post']",
                    "a[aria-label='Create']",
                    "a[href='/create/select/']",
                    "div[role='button']:has-text('Create')",
                    "div[role='button']:has-text('Создать')",
                    "span:has-text('Create')",
                    "span:has-text('Создать')",
                ],
                timeout=3000,
            )
            if not clicked:
                logger.info("Create button not found; opening create URL.")
                self.page.goto("https://www.instagram.com/create/select/", wait_until="domcontentloaded", timeout=60000)

            self.set_media_file(media_path)
            logger.info("Media selected: %s", media_path)

            logger.info("Clicking first Next...")
            self.click_next()
            logger.info("Clicking second Next...")
            self.click_next()
            logger.info("Filling caption...")
            self.fill_caption(caption)

            if auto_share:
                logger.info("Looking for Share button...")
                if not self.click_share():
                    logger.info("Share button selector not found; trying keyboard fallback.")
                    self.page.keyboard.press("Tab")
                    self.page.keyboard.press("Enter")
                logger.info("Share clicked for post %s", post_number)
                self.finish_share_dialog()
            else:
                input("Caption tayyor. Post qilish uchun Instagram oynasida Share bosing, keyin Enter: ")

            self.posts_today += 1
            self.log_post(post_number, caption, "submitted")
            return True
        except Exception as exc:
            logger.exception("Browser upload failed for post %s: %s", post_number, exc)
            self.save_debug_artifacts(f"upload_failed_{post_number}")
            self.log_post(post_number, caption, "failed")
            return False

    def upload_next_reel(self, auto_share: bool = True) -> bool:
        if self.posts_today >= self.config.posts_per_day:
            logger.info("Daily limit reached: %s/%s", self.posts_today, self.config.posts_per_day)
            return True
        return self.upload_reel(self.posts_today + 1, auto_share=auto_share)

    def click_next(self) -> None:
        if not self.click_first(
            [
                "div[role='button']:has-text('Next')",
                "button:has-text('Next')",
                "div[role='button']:has-text('Далее')",
                "button:has-text('Далее')",
                "div[role='button']:has-text('Дальше')",
                "button:has-text('Дальше')",
            ],
            timeout=60000,
        ):
            raise RuntimeError("Next button not found")
        self.pause(1.0)

    def set_media_file(self, media_path: Path) -> None:
        logger.info("Looking for upload input or Create menu...")
        if self.try_set_existing_file_input(media_path, timeout=2500):
            return

        if self.select_create_post_if_menu_open():
            if self.try_set_existing_file_input(media_path, timeout=30000):
                return
            if self.click_select_from_computer(media_path):
                return

        logger.info("Opening direct create URL as fallback...")
        self.page.goto("https://www.instagram.com/create/select/", wait_until="domcontentloaded", timeout=60000)
        if self.try_set_existing_file_input(media_path, timeout=30000):
            return
        if self.click_select_from_computer(media_path):
            return
        raise RuntimeError("File input/file chooser not found")

    def try_set_existing_file_input(self, media_path: Path, timeout: int) -> bool:
        try:
            file_input = self.page.locator("input[type='file']").first
            file_input.wait_for(state="attached", timeout=timeout)
            file_input.set_input_files(str(media_path))
            return True
        except Exception:
            return False

    def select_create_post_if_menu_open(self) -> bool:
        logger.info("Checking Create menu...")
        labels = ["Post", "Reel", "Публикация", "Рилс"]
        for label in labels:
            if self.click_menu_text(label):
                logger.info("Clicked Create menu item by text: %s", label)
                self.pause(0.5)
                return True
        logger.info("Create menu item not visible; continuing.")
        return False

    def click_menu_text(self, label: str) -> bool:
        selectors = [
            f"a:has(svg[aria-label='{label}'])",
            f"a:has(svg title:text-is('{label}'))",
            f"xpath=//a[.//*[name()='svg' and @aria-label='{label}']]",
            f"xpath=//a[.//*[name()='title' and normalize-space()='{label}']]",
            f"div[role='button']:has-text('{label}')",
            f"a[role='link']:has-text('{label}')",
            f"a:has-text('{label}')",
            f"span:has-text('{label}')",
            f"text='{label}'",
        ]
        for selector in selectors:
            try:
                item = self.page.locator(selector).first
                item.wait_for(state="visible", timeout=1500)
                item.click(timeout=3000, force=True)
                return True
            except Exception:
                continue
        try:
            return bool(
                self.page.evaluate(
                    """(label) => {
                        const svg = document.querySelector(`svg[aria-label="${label}"]`);
                        if (svg) {
                            const link = svg.closest('a, [role="button"]');
                            if (link) {
                                link.click();
                                return true;
                            }
                        }
                        const titles = [...document.querySelectorAll('svg title')];
                        const title = titles.find((el) => el.textContent && el.textContent.trim() === label);
                        if (title) {
                            const link = title.closest('a, [role="button"]');
                            if (link) {
                                link.click();
                                return true;
                            }
                        }
                        const nodes = [...document.querySelectorAll('span, div, a')];
                        const node = nodes.find((el) => el.textContent && el.textContent.trim() === label);
                        if (!node) return false;
                        const clickable = node.closest('a, [role="button"]') || node.closest('div') || node;
                        clickable.click();
                        return true;
                    }""",
                    label,
                )
            )
        except Exception:
            return False

    def click_select_from_computer(self, media_path: Path) -> bool:
        logger.info("Looking for Select from computer button...")
        labels = ["Select from computer", "Выбрать с компьютера", "Выбрать на компьютере"]
        for label in labels:
            selectors = [
                f"div[role='button']:has-text('{label}')",
                f"button:has-text('{label}')",
                f"text='{label}'",
            ]
            for selector in selectors:
                try:
                    button = self.page.locator(selector).first
                    button.wait_for(state="visible", timeout=3000)
                    try:
                        with self.page.expect_file_chooser(timeout=5000) as chooser_info:
                            button.click(timeout=3000, force=True)
                        chooser_info.value.set_files(str(media_path))
                        logger.info("Selected video through file chooser button: %s", label)
                        return True
                    except Exception:
                        button.click(timeout=3000, force=True)
                        if self.try_set_existing_file_input(media_path, timeout=10000):
                            return True
                except Exception:
                    continue
        return False

    def fill_caption(self, caption: str) -> None:
        selectors = [
            "div[aria-label='Write a caption...'][contenteditable='true']",
            "div[aria-label='Напишите подпись...'][contenteditable='true']",
            "div[aria-label='Добавьте подпись...'][contenteditable='true']",
            "[role='textbox'][contenteditable='true']",
            "textarea",
            "div[contenteditable='true']",
        ]
        for selector in selectors:
            try:
                field = self.page.locator(selector).last
                field.wait_for(state="visible", timeout=10000)
                if self.type_caption(field, caption):
                    logger.info("Caption filled: %s", caption)
                    return
            except Exception:
                continue
        raise RuntimeError("Caption field not found")

    def type_caption(self, field, caption: str) -> bool:
        try:
            field.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass

        field.click(timeout=5000, force=True)
        self.pause(0.25)

        # Instagram's caption box is a React contenteditable. Keyboard input is
        # more reliable than Locator.fill() for preserving the final caption.
        try:
            field.fill("")
        except Exception:
            pass

        for shortcut in ("Meta+A", "Control+A"):
            try:
                self.page.keyboard.press(shortcut)
            except Exception:
                pass
        self.page.keyboard.press("Backspace")
        self.page.keyboard.insert_text(caption)
        self.pause(0.5)

        if self.caption_field_has_text(field, caption):
            return True

        try:
            field.evaluate(
                """(el, value) => {
                    el.focus();
                    if ('value' in el) {
                        el.value = value;
                    } else {
                        el.textContent = value;
                    }
                    el.dispatchEvent(new InputEvent('input', {
                        bubbles: true,
                        inputType: 'insertText',
                        data: value
                    }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                caption,
            )
            self.pause(0.5)
        except Exception:
            return False

        return self.caption_field_has_text(field, caption)

    def caption_field_has_text(self, field, caption: str) -> bool:
        try:
            value = field.input_value(timeout=1000)
        except Exception:
            try:
                value = field.inner_text(timeout=1000)
            except Exception:
                value = ""
        return caption in value

    def click_share(self) -> bool:
        share_texts = ["Share", "Поделиться", "Опубликовать"]
        for text in share_texts:
            xpath = f"xpath=//div[@role='button' and normalize-space()='{text}'] | //button[normalize-space()='{text}']"
            try:
                button = self.page.locator(xpath).last
                button.wait_for(state="visible", timeout=5000)
                button.click(timeout=5000, force=True)
                logger.info("Clicked %s by forced role/text selector", text)
                return True
            except Exception:
                continue
        for text in share_texts:
            try:
                clicked = self.page.evaluate(
                    """(label) => {
                        const nodes = [...document.querySelectorAll('div[role="button"], button')];
                        const node = nodes.reverse().find((el) => el.textContent && el.textContent.trim() === label);
                        if (!node) return false;
                        node.click();
                        return true;
                    }""",
                    text,
                )
                if clicked:
                    logger.info("Clicked %s by JS fallback", text)
                    return True
            except Exception:
                continue
        try:
            self.page.get_by_text("Share", exact=True).click(timeout=5000)
            logger.info("Clicked Share by exact text")
            return True
        except Exception:
            pass
        try:
            self.page.get_by_text("Поделиться", exact=True).click(timeout=5000)
            logger.info("Clicked Поделиться by exact text")
            return True
        except Exception:
            pass
        try:
            self.page.get_by_text("Опубликовать", exact=True).click(timeout=5000)
            logger.info("Clicked Опубликовать by exact text")
            return True
        except Exception:
            pass
        return self.click_first(
            [
                "div[role='button']:has-text('Share')",
                "button:has-text('Share')",
                "div[role='button']:has-text('Поделиться')",
                "button:has-text('Поделиться')",
                "div[role='button']:has-text('Опубликовать')",
                "button:has-text('Опубликовать')",
            ],
            timeout=30000,
        )

    def finish_share_dialog(self) -> None:
        logger.info("Waiting for share confirmation...")
        success_selectors = [
            "text='Your reel has been shared.'",
            "text='Reel shared'",
            "text='Ваша публикация опубликована.'",
            "text='Публикация опубликована'",
        ]
        for selector in success_selectors:
            try:
                self.page.locator(selector).first.wait_for(state="visible", timeout=180000)
                break
            except Exception:
                continue

        logger.info("Looking for Done button...")
        if self.click_done():
            logger.info("Done clicked.")
            self.pause(1.0)
            return
        logger.warning("Done button not found; trying Escape.")
        self.page.keyboard.press("Escape")
        self.pause(1.0)

    def click_done(self) -> bool:
        done_texts = ["Done", "Готово"]
        for text in done_texts:
            xpath = f"xpath=//div[@role='button' and normalize-space()='{text}'] | //button[normalize-space()='{text}']"
            try:
                button = self.page.locator(xpath).last
                button.wait_for(state="visible", timeout=10000)
                button.click(timeout=5000, force=True)
                logger.info("Clicked %s by forced role/text selector", text)
                return True
            except Exception:
                continue
        for text in done_texts:
            try:
                clicked = self.page.evaluate(
                    """(label) => {
                        const nodes = [...document.querySelectorAll('div[role="button"], button')];
                        const node = nodes.reverse().find((el) => el.textContent && el.textContent.trim() === label);
                        if (!node) return false;
                        node.click();
                        return true;
                    }""",
                    text,
                )
                if clicked:
                    logger.info("Clicked %s by JS fallback", text)
                    return True
            except Exception:
                continue
        return self.click_first(
            [
                "div[role='button']:has-text('Done')",
                "button:has-text('Done')",
                "div[role='button']:has-text('Готово')",
                "button:has-text('Готово')",
            ],
            timeout=10000,
        )

    def log_post(self, post_number: Union[int, str], caption: str, status: str) -> None:
        entry = {
            "post_number": post_number,
            "status": status,
            "caption": caption,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": "browser",
        }
        try:
            if self.config.json_log.exists():
                with self.config.json_log.open("r", encoding="utf-8") as file:
                    logs = json.load(file)
                if not isinstance(logs, list):
                    logs = []
            else:
                logs = []
            logs.append(entry)
            with self.config.json_log.open("w", encoding="utf-8") as file:
                json.dump(logs, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("JSON post log disabled: %s", exc)

    def preview_schedule(self) -> List[str]:
        start = parse_clock(self.config.start_time)
        end = parse_clock(self.config.end_time)
        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60

        interval = (end_minutes - start_minutes) / self.config.posts_per_day
        times = []
        for index in range(self.config.posts_per_day):
            total_minutes = int(start_minutes + index * interval) % (24 * 60)
            times.append(f"{total_minutes // 60:02d}:{total_minutes % 60:02d}")
        return times

    def schedule_posts(self, auto_share: bool = True) -> None:
        for index, time_str in enumerate(self.preview_schedule(), start=1):
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                self.upload_reel,
                args=(index, auto_share),
                trigger="cron",
                hour=hour,
                minute=minute,
                id=f"browser_post_{index}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("Post %s scheduled at %s", index, time_str)
        self.scheduler.add_job(self.reset_daily_counter, trigger="cron", hour=23, minute=59, id="browser_reset", replace_existing=True)

    def schedule_interval_posts(self, interval_minutes: int, auto_share: bool = True) -> None:
        logger.info("Scheduling interval mode: every %s minutes, max %s posts/day", interval_minutes, self.config.posts_per_day)
        self.scheduler.add_job(
            self.upload_next_reel,
            args=(auto_share,),
            trigger="interval",
            minutes=interval_minutes,
            id="browser_interval_post",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(self.reset_daily_counter, trigger="cron", hour=23, minute=59, id="browser_reset", replace_existing=True)

    def reset_daily_counter(self) -> None:
        logger.info("Daily counter reset. Posts today: %s", self.posts_today)
        self.posts_today = 0

    def run(self, auto_share: bool = True) -> bool:
        self.validate()
        self.start_browser()
        try:
            self.ensure_login()
            self.schedule_posts(auto_share=auto_share)
            self.scheduler.start()
            logger.info("Browser scheduler started. Keep Chrome and terminal open. Ctrl+C stops it.")
            while True:
                self.pause(1.0)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            self.scheduler.shutdown(wait=False)
            return True
        finally:
            self.close_browser()

    def run_interval(self, interval_minutes: int = 29, start_now: bool = True, auto_share: bool = True) -> bool:
        self.validate()
        self.start_browser()
        try:
            self.ensure_login()
            if start_now:
                self.upload_next_reel(auto_share=auto_share)
            self.schedule_interval_posts(interval_minutes=interval_minutes, auto_share=auto_share)
            self.scheduler.start()
            logger.info("Auto interval scheduler started. Keep Chrome and terminal open. Ctrl+C stops it.")
            while True:
                self.pause(1.0)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            self.scheduler.shutdown(wait=False)
            return True
        finally:
            self.close_browser()

    def run_batch(self, start_number: int = 1, count: Optional[int] = None, delay_seconds: int = 5, auto_share: bool = True) -> bool:
        self.validate()
        total = count or (self.config.posts_per_day - start_number + 1)
        end_number = start_number + total - 1
        self.start_browser()
        try:
            self.ensure_login()
            logger.info("Batch mode started: %s -> %s", start_number, end_number)
            for number in range(start_number, end_number + 1):
                ok = self.upload_reel(number, auto_share=auto_share)
                if not ok:
                    logger.error("Batch stopped at reel %s", number)
                    return False
                if number < end_number and delay_seconds > 0:
                    logger.info("Waiting %s seconds before next reel...", delay_seconds)
                    time.sleep(delay_seconds)
            logger.info("Batch completed.")
            return True
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            return True
        finally:
            self.close_browser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browser-assisted Instagram Reels poster")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.json")
    parser.add_argument("--preview", action="store_true", help="Print schedule and exit")
    parser.add_argument("--once", type=int, metavar="N", help="Open Chrome, wait for login, upload one reel and exit")
    parser.add_argument("--start-now", action="store_true", help="Upload now, then continue every --interval-minutes")
    parser.add_argument("--interval-minutes", type=int, default=29, help="Interval for --start-now mode")
    parser.add_argument("--batch-now", action="store_true", help="Upload multiple reels one after another without the 29 minute interval")
    parser.add_argument("--start-number", type=int, default=1, help="First reel number for --batch-now")
    parser.add_argument("--count", type=int, help="How many reels to upload in --batch-now mode")
    parser.add_argument("--delay-seconds", type=int, default=5, help="Delay between reels in --batch-now mode")
    parser.add_argument("--manual-share", action="store_true", help="Prepare upload and caption, but let you click Share manually")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless after session exists")
    parser.add_argument("--action-delay", type=float, help="Small delay between browser actions. Lower is faster, higher is safer.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = resolve_path(args.config, Path.cwd())
    config = read_config(config_path)
    if args.action_delay is not None:
        config.action_delay = args.action_delay
    setup_logging(config.log_file, config.verbose)
    poster = InstagramBrowserPoster(config, headless=args.headless)

    try:
        if args.preview:
            poster.validate()
            for index, time_str in enumerate(poster.preview_schedule(), start=1):
                print(f"{index:02d}. {time_str} -> {poster.create_caption(index)!r}")
            return 0
        if args.once is not None:
            poster.validate()
            poster.start_browser()
            try:
                poster.ensure_login()
                return 0 if poster.upload_reel(args.once, auto_share=not args.manual_share) else 1
            finally:
                poster.close_browser()
        if args.start_now:
            return 0 if poster.run_interval(interval_minutes=args.interval_minutes, start_now=True, auto_share=not args.manual_share) else 1
        if args.batch_now:
            return 0 if poster.run_batch(start_number=args.start_number, count=args.count, delay_seconds=args.delay_seconds, auto_share=not args.manual_share) else 1
        return 0 if poster.run(auto_share=not args.manual_share) else 1
    except Exception as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
