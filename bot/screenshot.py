from __future__ import annotations

import io
from dataclasses import dataclass

import mss
from PIL import Image


TELEGRAM_PHOTO_MAX_BYTES = 9_500_000
TELEGRAM_DIMENSION_SUM_MAX = 10_000


@dataclass(frozen=True, slots=True)
class Screenshot:
    data: bytes
    width: int
    height: int
    quality: int


class ScreenCapture:
    def __init__(self, monitor_index: int, jpeg_quality: int, max_width: int):
        self.monitor_index = monitor_index
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width

    @property
    def monitor_count(self) -> int:
        with mss.mss() as sct:
            return max(0, len(sct.monitors) - 1)

    def close(self) -> None:
        return None

    def capture(self) -> Screenshot:
        with mss.mss() as sct:
            monitors = sct.monitors
            if self.monitor_index >= len(monitors):
                raise RuntimeError(
                    f"SCREEN_MONITOR={self.monitor_index} is unavailable; "
                    f"detected monitors: {max(0, len(monitors) - 1)}. Use 0 for all monitors."
                )
            raw = sct.grab(monitors[self.monitor_index])
            image = Image.frombytes("RGB", raw.size, raw.rgb)

        image = self._fit_dimensions(image)
        return self._encode_for_telegram(image)

    def _fit_dimensions(self, image: Image.Image) -> Image.Image:
        scale = 1.0

        if self.max_width > 0 and image.width > self.max_width:
            scale = min(scale, self.max_width / image.width)

        if image.width + image.height > TELEGRAM_DIMENSION_SUM_MAX:
            scale = min(scale, TELEGRAM_DIMENSION_SUM_MAX / (image.width + image.height))

        if scale < 1.0:
            image = image.resize(
                (
                    max(1, int(image.width * scale)),
                    max(1, int(image.height * scale)),
                ),
                Image.Resampling.LANCZOS,
            )

        return image

    def _encode_for_telegram(self, image: Image.Image) -> Screenshot:
        quality = self.jpeg_quality
        working = image

        while True:
            output = io.BytesIO()
            working.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                subsampling=0,
            )
            data = output.getvalue()

            if len(data) <= TELEGRAM_PHOTO_MAX_BYTES:
                return Screenshot(
                    data=data,
                    width=working.width,
                    height=working.height,
                    quality=quality,
                )

            if quality > 60:
                quality = max(60, quality - 5)
                continue

            working = working.resize(
                (
                    max(1, int(working.width * 0.9)),
                    max(1, int(working.height * 0.9)),
                ),
                Image.Resampling.LANCZOS,
            )
            quality = min(self.jpeg_quality, 90)
