from __future__ import annotations

import io
import logging
import math
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import mss
import requests
from dotenv import load_dotenv
from PIL import Image, ImageOps


load_dotenv(Path(__file__).with_name(".env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("screen-client")

TELEGRAM_SAFE_MAX_BYTES = 9_000_000
TELEGRAM_SAFE_DIMENSION_SUM = 9_500
TELEGRAM_SAFE_ASPECT_RATIO = 19.5


@dataclass(frozen=True)
class Settings:
    server_url: str
    upload_token: str
    interval: float
    monitor: int
    jpeg_quality: int
    max_width: int
    request_timeout: float


def _number(name: str, default: str, cast):
    raw = os.getenv(name, default).strip()
    try:
        return cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} has invalid value: {raw!r}") from exc


def load_settings() -> Settings:
    server_url = os.getenv("SERVER_URL", "").strip().rstrip("/")
    upload_token = os.getenv("UPLOAD_TOKEN", "").strip()
    interval = _number("SCREEN_INTERVAL", "10", float)
    monitor = _number("SCREEN_MONITOR", "0", int)
    quality = _number("SCREEN_JPEG_QUALITY", "95", int)
    max_width = _number("SCREEN_MAX_WIDTH", "0", int)
    timeout = _number("REQUEST_TIMEOUT", "30", float)

    if not server_url.startswith(("http://", "https://")):
        raise ValueError("SERVER_URL must start with http:// or https://")
    if len(upload_token) < 16:
        raise ValueError("UPLOAD_TOKEN must be at least 16 characters")
    if interval < 3:
        raise ValueError("SCREEN_INTERVAL must be >= 3 seconds")
    if monitor < 0:
        raise ValueError("SCREEN_MONITOR must be >= 0")
    if not 30 <= quality <= 95:
        raise ValueError("SCREEN_JPEG_QUALITY must be between 30 and 95")
    if max_width < 0:
        raise ValueError("SCREEN_MAX_WIDTH must be >= 0")
    if timeout <= 0:
        raise ValueError("REQUEST_TIMEOUT must be > 0")

    return Settings(server_url, upload_token, interval, monitor, quality, max_width, timeout)


def _resize_to_width(image: Image.Image, width: int) -> Image.Image:
    if width <= 0 or image.width <= width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _fit_telegram_dimensions(image: Image.Image) -> Image.Image:
    ratio = max(image.width / image.height, image.height / image.width)
    if ratio > TELEGRAM_SAFE_ASPECT_RATIO:
        if image.width >= image.height:
            target_height = math.ceil(image.width / TELEGRAM_SAFE_ASPECT_RATIO)
            padding = target_height - image.height
            image = ImageOps.expand(image, border=(0, padding // 2, 0, padding - padding // 2), fill="black")
        else:
            target_width = math.ceil(image.height / TELEGRAM_SAFE_ASPECT_RATIO)
            padding = target_width - image.width
            image = ImageOps.expand(image, border=(padding // 2, 0, padding - padding // 2, 0), fill="black")

    dimension_sum = image.width + image.height
    if dimension_sum > TELEGRAM_SAFE_DIMENSION_SUM:
        scale = TELEGRAM_SAFE_DIMENSION_SUM / dimension_sum
        image = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return image


def _encode_jpeg(image: Image.Image, requested_quality: int) -> tuple[bytes, int, Image.Image]:
    current = image
    quality = requested_quality

    for _ in range(12):
        for candidate_quality in range(quality, 49, -5):
            buffer = io.BytesIO()
            current.save(buffer, format="JPEG", quality=candidate_quality, optimize=True, subsampling=0)
            data = buffer.getvalue()
            if len(data) <= TELEGRAM_SAFE_MAX_BYTES:
                return data, candidate_quality, current

        new_width = max(640, int(current.width * 0.85))
        if new_width >= current.width:
            break
        current = _resize_to_width(current, new_width)
        quality = requested_quality

    raise RuntimeError("Could not compress screenshot below Telegram photo size limit")


def capture_jpeg(sct: mss.mss, settings: Settings) -> tuple[bytes, int, int, int]:
    if settings.monitor >= len(sct.monitors):
        raise RuntimeError(
            f"SCREEN_MONITOR={settings.monitor} does not exist; detected monitors: {len(sct.monitors) - 1}"
        )

    raw = sct.grab(sct.monitors[settings.monitor])
    image = Image.frombytes("RGB", raw.size, raw.rgb)
    image = _resize_to_width(image, settings.max_width)
    image = _fit_telegram_dimensions(image)
    data, actual_quality, final_image = _encode_jpeg(image, settings.jpeg_quality)
    return data, final_image.width, final_image.height, actual_quality


def upload(session: requests.Session, settings: Settings, data: bytes, width: int, height: int, quality: int) -> None:
    response = session.post(
        f"{settings.server_url}/upload",
        data=data,
        headers={
            "Authorization": f"Bearer {settings.upload_token}",
            "Content-Type": "image/jpeg",
            "X-Screen-Width": str(width),
            "X-Screen-Height": str(height),
            "X-Jpeg-Quality": str(quality),
            "X-Client-Name": socket.gethostname(),
            "X-Client-Time": datetime.now(timezone.utc).isoformat(),
        },
        timeout=settings.request_timeout,
    )
    response.raise_for_status()


def main() -> None:
    settings = load_settings()
    session = requests.Session()
    logger.info("Server: %s", settings.server_url)
    logger.info("Interval: %ss; monitor: %s; requested JPEG quality: %s", settings.interval, settings.monitor, settings.jpeg_quality)

    with mss.mss() as sct:
        logger.info("Detected physical monitors: %s", len(sct.monitors) - 1)
        while True:
            started = time.monotonic()
            try:
                data, width, height, quality = capture_jpeg(sct, settings)
                upload(session, settings, data, width, height, quality)
                logger.info("Uploaded %sx%s, JPEG %s, %.0f KB", width, height, quality, len(data) / 1024)
            except KeyboardInterrupt:
                logger.info("Stopped")
                return
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else "?"
                body = exc.response.text[:200] if exc.response is not None else ""
                logger.error("Server HTTP error %s: %s", code, body)
            except requests.RequestException as exc:
                logger.error("Network error: %s", exc)
            except Exception as exc:
                logger.exception("Client iteration failed: %s", exc)

            elapsed = time.monotonic() - started
            try:
                time.sleep(max(0.2, settings.interval - elapsed))
            except KeyboardInterrupt:
                logger.info("Stopped")
                return


if __name__ == "__main__":
    main()
