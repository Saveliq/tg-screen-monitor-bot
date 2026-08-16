from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc

    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"{name} must be <= {maximum}")
    return value


def _user_ids(raw: str) -> frozenset[int]:
    result: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.add(int(chunk))
        except ValueError as exc:
            raise RuntimeError(f"Invalid Telegram user id: {chunk!r}") from exc
    if not result:
        raise RuntimeError("ALLOWED_USER_IDS must contain at least one Telegram user id")
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    allowed_user_ids: frozenset[int]
    screen_interval: int
    screen_monitor: int
    jpeg_quality: int
    max_width: int
    state_file: Path


def load_settings() -> Settings:
    return Settings(
        bot_token=_required("BOT_TOKEN"),
        allowed_user_ids=_user_ids(_required("ALLOWED_USER_IDS")),
        screen_interval=_int("SCREEN_INTERVAL", 10, minimum=3),
        screen_monitor=_int("SCREEN_MONITOR", 0, minimum=0),
        jpeg_quality=_int("SCREEN_JPEG_QUALITY", 92, minimum=30, maximum=95),
        max_width=_int("SCREEN_MAX_WIDTH", 0, minimum=0),
        state_file=Path(os.getenv("STATE_FILE", "state.json")).expanduser(),
    )
