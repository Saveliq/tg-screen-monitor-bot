from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class FrameMeta:
    received_at: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    jpeg_quality: int | None = None
    client_name: str | None = None
    client_time: str | None = None

    @property
    def received_datetime(self) -> datetime:
        return datetime.fromisoformat(self.received_at)


class LatestFrameStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.image_path = self.data_dir / "latest.jpg"
        self.meta_path = self.data_dir / "latest.json"

    def exists(self) -> bool:
        return self.image_path.exists()

    def read_image(self) -> bytes:
        return self.image_path.read_bytes()

    def read_meta(self) -> FrameMeta | None:
        if not self.meta_path.exists():
            return None
        try:
            raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return FrameMeta(**raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def save(self, data: bytes, *, width: int | None, height: int | None, jpeg_quality: int | None, client_name: str | None, client_time: str | None) -> FrameMeta:
        meta = FrameMeta(
            received_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=len(data),
            width=width,
            height=height,
            jpeg_quality=jpeg_quality,
            client_name=client_name,
            client_time=client_time,
        )
        image_tmp = self.image_path.with_suffix(".jpg.tmp")
        meta_tmp = self.meta_path.with_suffix(".json.tmp")
        image_tmp.write_bytes(data)
        meta_tmp.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(image_tmp, self.image_path)
        os.replace(meta_tmp, self.meta_path)
        return meta
