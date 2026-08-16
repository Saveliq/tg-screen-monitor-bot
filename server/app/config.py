from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bot_token: str
    upload_token: str
    allowed_user_ids: frozenset[int]
    data_dir: Path
    http_host: str
    http_port: int
    max_upload_bytes: int
    offline_after_seconds: int


def parse_user_ids(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"Invalid Telegram user id: {part!r}") from exc
        if value <= 0:
            raise ValueError("Telegram user ids must be positive integers")
        values.add(value)
    return frozenset(values)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    upload_token = os.getenv("UPLOAD_TOKEN", "").strip()
    allowed_user_ids = parse_user_ids(os.getenv("ALLOWED_USER_IDS", ""))

    if not bot_token:
        raise ValueError("BOT_TOKEN is required")
    if len(upload_token) < 16:
        raise ValueError("UPLOAD_TOKEN is required and must be at least 16 characters")
    if not allowed_user_ids:
        raise ValueError("ALLOWED_USER_IDS must contain at least one Telegram user id")

    return Settings(
        bot_token=bot_token,
        upload_token=upload_token,
        allowed_user_ids=allowed_user_ids,
        data_dir=Path(os.getenv("DATA_DIR", "/data")),
        http_host=os.getenv("HTTP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        http_port=_positive_int("HTTP_PORT", 8080),
        max_upload_bytes=_positive_int("MAX_UPLOAD_BYTES", 9_500_000),
        offline_after_seconds=_positive_int("OFFLINE_AFTER_SECONDS", 30),
    )
