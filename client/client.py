from __future__ import annotations

import io
import logging
import math
import socket
import time
from datetime import datetime, timezone

import mss
import requests
from PIL import Image, ImageOps


# ============================================================
# НАСТРОЙКИ КЛИЕНТА
# Меняй только этот блок.
# ============================================================

# Адрес Linux-сервера БЕЗ /upload в конце.
# Пример: "http://192.168.1.50:8088"
SERVER_URL = "http://192.168.1.50:8088"

# Должен полностью совпадать с UPLOAD_TOKEN в Portainer.
# Не коммить реальный токен в публичный GitHub.
UPLOAD_TOKEN = "PASTE_YOUR_UPLOAD_TOKEN_HERE"

# Интервал отправки скриншотов, секунд.
SCREEN_INTERVAL = 10

# 0 = все мониторы одним изображением
# 1 = первый монитор
# 2 = второй монитор
SCREEN_MONITOR = 0

# Качество JPEG: 30-95.
SCREEN_JPEG_QUALITY = 95

# 0 = не уменьшать изображение заранее.
# Например 1920 = уменьшать до ширины 1920 px, если изображение шире.
SCREEN_MAX_WIDTH = 0

# Таймаут HTTP-запроса к серверу, секунд.
REQUEST_TIMEOUT = 30


# ============================================================
# ВНУТРЕННИЕ ОГРАНИЧЕНИЯ TELEGRAM
# Обычно менять не нужно.
# ============================================================

TELEGRAM_SAFE_MAX_BYTES = 9_000_000
TELEGRAM_SAFE_DIMENSION_SUM = 9_500
TELEGRAM_SAFE_ASPECT_RATIO = 19.5


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("screen-client")


def validate_settings() -> None:
    if not SERVER_URL.startswith(("http://", "https://")):
        raise ValueError("SERVER_URL must start with http:// or https://")

    if SERVER_URL.endswith("/upload"):
        raise ValueError("SERVER_URL must not end with /upload")

    if len(UPLOAD_TOKEN) < 16 or UPLOAD_TOKEN == "PASTE_YOUR_UPLOAD_TOKEN_HERE":
        raise ValueError("Set UPLOAD_TOKEN at the top of client.py")

    if SCREEN_INTERVAL < 3:
        raise ValueError("SCREEN_INTERVAL must be >= 3 seconds")

    if SCREEN_MONITOR < 0:
        raise ValueError("SCREEN_MONITOR must be >= 0")

    if not 30 <= SCREEN_JPEG_QUALITY <= 95:
        raise ValueError("SCREEN_JPEG_QUALITY must be between 30 and 95")

    if SCREEN_MAX_WIDTH < 0:
        raise ValueError("SCREEN_MAX_WIDTH must be >= 0")

    if REQUEST_TIMEOUT <= 0:
        raise ValueError("REQUEST_TIMEOUT must be > 0")


def resize_to_width(image: Image.Image, width: int) -> Image.Image:
    if width <= 0 or image.width <= width:
        return image

    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def fit_telegram_dimensions(image: Image.Image) -> Image.Image:
    ratio = max(image.width / image.height, image.height / image.width)

    if ratio > TELEGRAM_SAFE_ASPECT_RATIO:
        if image.width >= image.height:
            target_height = math.ceil(image.width / TELEGRAM_SAFE_ASPECT_RATIO)
            padding = target_height - image.height
            image = ImageOps.expand(
                image,
                border=(0, padding // 2, 0, padding - padding // 2),
                fill="black",
            )
        else:
            target_width = math.ceil(image.height / TELEGRAM_SAFE_ASPECT_RATIO)
            padding = target_width - image.width
            image = ImageOps.expand(
                image,
                border=(padding // 2, 0, padding - padding // 2, 0),
                fill="black",
            )

    dimension_sum = image.width + image.height

    if dimension_sum > TELEGRAM_SAFE_DIMENSION_SUM:
        scale = TELEGRAM_SAFE_DIMENSION_SUM / dimension_sum
        image = image.resize(
            (
                max(1, int(image.width * scale)),
                max(1, int(image.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )

    return image


def encode_jpeg(
    image: Image.Image,
    requested_quality: int,
) -> tuple[bytes, int, Image.Image]:
    current = image
    quality = requested_quality

    for _ in range(12):
        for candidate_quality in range(quality, 49, -5):
            buffer = io.BytesIO()
            current.save(
                buffer,
                format="JPEG",
                quality=candidate_quality,
                optimize=True,
                subsampling=0,
            )
            data = buffer.getvalue()

            if len(data) <= TELEGRAM_SAFE_MAX_BYTES:
                return data, candidate_quality, current

        new_width = max(640, int(current.width * 0.85))

        if new_width >= current.width:
            break

        current = resize_to_width(current, new_width)
        quality = requested_quality

    raise RuntimeError(
        "Could not compress screenshot below Telegram photo size limit"
    )


def capture_jpeg(
    sct: mss.mss,
) -> tuple[bytes, int, int, int]:
    if SCREEN_MONITOR >= len(sct.monitors):
        raise RuntimeError(
            f"SCREEN_MONITOR={SCREEN_MONITOR} does not exist; "
            f"detected monitors: {len(sct.monitors) - 1}"
        )

    raw = sct.grab(sct.monitors[SCREEN_MONITOR])

    image = Image.frombytes(
        "RGB",
        raw.size,
        raw.rgb,
    )

    image = resize_to_width(image, SCREEN_MAX_WIDTH)
    image = fit_telegram_dimensions(image)

    data, actual_quality, final_image = encode_jpeg(
        image,
        SCREEN_JPEG_QUALITY,
    )

    return (
        data,
        final_image.width,
        final_image.height,
        actual_quality,
    )


def upload(
    session: requests.Session,
    data: bytes,
    width: int,
    height: int,
    quality: int,
) -> None:
    response = session.post(
        f"{SERVER_URL.rstrip('/')}/upload",
        data=data,
        headers={
            "Authorization": f"Bearer {UPLOAD_TOKEN}",
            "Content-Type": "image/jpeg",
            "X-Screen-Width": str(width),
            "X-Screen-Height": str(height),
            "X-Jpeg-Quality": str(quality),
            "X-Client-Name": socket.gethostname(),
            "X-Client-Time": datetime.now(timezone.utc).isoformat(),
        },
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()


def main() -> None:
    validate_settings()

    session = requests.Session()

    logger.info("Screen client starting")
    logger.info("Server: %s", SERVER_URL)
    logger.info("Upload endpoint: %s/upload", SERVER_URL.rstrip("/"))
    logger.info("Interval: %ss", SCREEN_INTERVAL)
    logger.info("Monitor: %s", SCREEN_MONITOR)
    logger.info("Requested JPEG quality: %s", SCREEN_JPEG_QUALITY)
    logger.info("Maximum width: %s", SCREEN_MAX_WIDTH or "disabled")

    with mss.mss() as sct:
        logger.info(
            "Detected physical monitors: %s",
            len(sct.monitors) - 1,
        )

        while True:
            started = time.monotonic()

            try:
                data, width, height, quality = capture_jpeg(sct)

                upload(
                    session,
                    data,
                    width,
                    height,
                    quality,
                )

                logger.info(
                    "Uploaded %sx%s, JPEG %s, %.0f KB",
                    width,
                    height,
                    quality,
                    len(data) / 1024,
                )

            except KeyboardInterrupt:
                logger.info("Stopped")
                return

            except requests.HTTPError as exc:
                code = (
                    exc.response.status_code
                    if exc.response is not None
                    else "?"
                )
                body = (
                    exc.response.text[:200]
                    if exc.response is not None
                    else ""
                )
                logger.error(
                    "Server HTTP error %s: %s",
                    code,
                    body,
                )

            except requests.RequestException as exc:
                logger.error("Network error: %s", exc)

            except Exception as exc:
                logger.exception("Client iteration failed: %s", exc)

            elapsed = time.monotonic() - started

            try:
                time.sleep(
                    max(0.2, SCREEN_INTERVAL - elapsed)
                )
            except KeyboardInterrupt:
                logger.info("Stopped")
                return


if __name__ == "__main__":
    main()
