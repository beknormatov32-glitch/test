#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instagram Reels poster with config, dry-run, test and schedule modes."""

import argparse
import getpass
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, List, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, ChallengeUnknownStep, TwoFactorRequired

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
logger = logging.getLogger("instagram_reels_poster")


@dataclass
class PosterConfig:
    username: str
    password: str
    video_path: Path
    hashtags: str
    caption_template: str
    posts_per_day: int
    start_time: str
    end_time: str
    timezone: str
    log_file: Path
    json_log: Path
    session_file: Path
    verbose: bool
    dry_run: bool = False


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_path(value: str, base_dir: Path = BASE_DIR) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


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


def read_config(config_path: Path, dry_run: bool = False) -> PosterConfig:
    raw = load_json(config_path)
    instagram = raw.get("instagram", {})
    posting = raw.get("posting", {})
    video = raw.get("video", {})
    schedule = raw.get("schedule", {})
    logging_cfg = raw.get("logging", {})

    password_env = instagram.get("password_env", "IG_PASSWORD")
    password = os.getenv(password_env) or instagram.get("password", "")

    return PosterConfig(
        username=instagram.get("username", "").strip(),
        password=password,
        video_path=resolve_path(video.get("path", "./video_reel.mp4"), config_path.parent),
        hashtags=posting.get("hashtags", "").strip(),
        caption_template=posting.get("caption_template", "{number}-reels\n{hashtags}"),
        posts_per_day=int(posting.get("posts_per_day", 1)),
        start_time=posting.get("start_time", "00:00"),
        end_time=posting.get("end_time", "23:59"),
        timezone=schedule.get("timezone", "Asia/Tashkent"),
        log_file=resolve_path(logging_cfg.get("log_file", "instagram_poster.log"), config_path.parent),
        json_log=resolve_path(logging_cfg.get("json_log", "posts_log.json"), config_path.parent),
        session_file=resolve_path(instagram.get("session_file", "session.json"), config_path.parent),
        verbose=bool(logging_cfg.get("verbose", True)),
        dry_run=dry_run,
    )


def parse_clock(value: str) -> dt_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"Time must be HH:MM, got {value!r}") from exc


class InstagramReelsPoster:
    def __init__(self, config: PosterConfig):
        self.config = config
        self.client = None
        self.posts_today = 0
        self.scheduler = BackgroundScheduler(timezone=config.timezone)

    def validate(self, require_password: bool = True) -> None:
        if not self.config.username:
            raise ValueError("Instagram username is missing in config.json")
        if require_password and not self.config.password:
            self.config.password = getpass.getpass("Instagram password: ")
        if require_password and not self.config.password:
            raise ValueError("Instagram password is missing. Set IG_PASSWORD or config instagram.password.")
        if self.config.posts_per_day < 1:
            raise ValueError("posting.posts_per_day must be at least 1")
        if self.config.posts_per_day > 50:
            logger.warning("posts_per_day is above 50. High automation volume can trigger platform limits.")
        if not self.config.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.config.video_path}")
        if self.config.video_path.suffix.lower() != ".mp4":
            logger.warning("Video file is not .mp4; Instagram upload may fail: %s", self.config.video_path)
        parse_clock(self.config.start_time)
        parse_clock(self.config.end_time)

    def login(self) -> bool:
        if self.config.dry_run:
            logger.info("DRY RUN: login skipped for @%s", self.config.username)
            return True

        try:
            logger.info("Logging in as @%s...", self.config.username)
            self.client = Client()
            if self.config.session_file.exists():
                self.client.load_settings(str(self.config.session_file))
            self.client.login(self.config.username, self.config.password)
            self.client.dump_settings(str(self.config.session_file))
            logger.info("Login successful.")
            return True
        except TwoFactorRequired:
            logger.error("Instagram requested 2FA. Log in once in the official app/browser, approve the login, then run this bot again.")
            return False
        except (ChallengeRequired, ChallengeUnknownStep) as exc:
            logger.error("Instagram requested a security challenge for @%s.", self.config.username)
            logger.error("Open Instagram app or instagram.com, log in manually, approve the challenge/It was me prompt, then run: python instagram_reels_poster.py --login-only")
            return False
        except Exception:
            logger.exception("Login failed")
            return False

    def create_caption(self, post_number: Union[int, str]) -> str:
        return self.config.caption_template.format(
            number=post_number,
            hashtags=self.config.hashtags,
            date=datetime.now().strftime("%Y-%m-%d"),
            time=datetime.now().strftime("%H:%M"),
        ).strip()

    def post_reel(self, post_number: Union[int, str]) -> bool:
        caption = self.create_caption(post_number)
        logger.info("Posting reel %s (%s/%s)", post_number, self.posts_today + 1, self.config.posts_per_day)

        if self.config.dry_run:
            logger.info("DRY RUN: would upload %s with caption: %r", self.config.video_path, caption)
            self.posts_today += 1
            self.log_post(post_number, "dry-run", caption, "dry_run")
            return True

        if not self.client:
            logger.error("Instagram client is not logged in")
            return False

        try:
            media = self.client.clip_upload(
                video_path=str(self.config.video_path),
                caption=caption,
                thumbnail=None,
            )
            self.posts_today += 1
            self.log_post(post_number, media.id, caption, "success")
            logger.info("Reel %s uploaded successfully. media_id=%s", post_number, media.id)
            return True
        except Exception:
            logger.exception("Post failed for %s", post_number)
            self.log_post(post_number, None, caption, "failed")
            return False

    def log_post(self, post_number: Union[int, str], media_id: Optional[str], caption: str, status: str) -> None:
        entry = {
            "post_number": post_number,
            "media_id": media_id,
            "status": status,
            "caption": caption,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
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
            self.config.json_log.parent.mkdir(parents=True, exist_ok=True)
            with self.config.json_log.open("w", encoding="utf-8") as file:
                json.dump(logs, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("JSON post log disabled: %s", exc)
        except Exception:
            logger.exception("Could not write JSON post log")

    def preview_schedule(self) -> List[str]:
        start = parse_clock(self.config.start_time)
        end = parse_clock(self.config.end_time)
        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60

        window_minutes = end_minutes - start_minutes
        interval = window_minutes / max(self.config.posts_per_day, 1)
        times = []
        for index in range(self.config.posts_per_day):
            total_minutes = int(start_minutes + index * interval) % (24 * 60)
            times.append(f"{total_minutes // 60:02d}:{total_minutes % 60:02d}")
        return times

    def schedule_posts(self) -> None:
        logger.info("Scheduling %s posts between %s and %s (%s)", self.config.posts_per_day, self.config.start_time, self.config.end_time, self.config.timezone)
        for index, time_str in enumerate(self.preview_schedule(), start=1):
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                func=self.post_reel,
                args=(index,),
                trigger="cron",
                hour=hour,
                minute=minute,
                id=f"post_{index}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("Post %s scheduled at %s", index, time_str)

        self.scheduler.add_job(
            func=self.reset_daily_counter,
            trigger="cron",
            hour=23,
            minute=59,
            id="reset_counter",
            replace_existing=True,
        )

    def reset_daily_counter(self) -> None:
        logger.info("Daily counter reset. Posts today: %s", self.posts_today)
        self.posts_today = 0

    def start(self) -> bool:
        self.validate(require_password=not self.config.dry_run)
        self.log_startup()
        if not self.login():
            return False
        self.schedule_posts()
        self.scheduler.start()
        logger.info("Scheduler started. Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            self.scheduler.shutdown(wait=False)
            return True

    def test_post(self) -> bool:
        self.validate(require_password=not self.config.dry_run)
        self.log_startup()
        if not self.login():
            return False
        return self.post_reel("TEST")

    def login_only(self) -> bool:
        self.validate(require_password=not self.config.dry_run)
        self.log_startup()
        return self.login()

    def log_startup(self) -> None:
        logger.info("=" * 50)
        logger.info("Instagram Reels Poster")
        logger.info("Account: @%s", self.config.username)
        logger.info("Daily posts: %s", self.config.posts_per_day)
        logger.info("Hashtags: %s", self.config.hashtags)
        logger.info("Video: %s", self.config.video_path)
        logger.info("Dry run: %s", self.config.dry_run)
        logger.info("=" * 50)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Instagram Reels poster")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Validate and log actions without logging in or uploading")
    parser.add_argument("--preview", action="store_true", help="Print today's schedule and exit")
    parser.add_argument("--login-only", action="store_true", help="Log in, save session and exit")
    parser.add_argument("--test", action="store_true", help="Upload one TEST reel and exit")
    parser.add_argument("--once", type=int, metavar="N", help="Upload one reel with number N and exit")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = resolve_path(args.config, Path.cwd())
    config = read_config(config_path, dry_run=args.dry_run)
    setup_logging(config.log_file, config.verbose)
    poster = InstagramReelsPoster(config)

    try:
        if args.preview:
            poster.validate(require_password=False)
            for index, time_str in enumerate(poster.preview_schedule(), start=1):
                print(f"{index:02d}. {time_str} -> {poster.create_caption(index)!r}")
            return 0
        if args.login_only:
            return 0 if poster.login_only() else 1
        if args.test:
            return 0 if poster.test_post() else 1
        if args.once is not None:
            poster.validate(require_password=not config.dry_run)
            if poster.login():
                return 0 if poster.post_reel(args.once) else 1
            return 1
        return 0 if poster.start() else 1
    except Exception as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
