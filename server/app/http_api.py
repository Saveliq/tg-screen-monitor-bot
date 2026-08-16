from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import Awaitable, Callable

from aiohttp import web

from .config import Settings
from .state import StateStore
from .storage import FrameMeta, LatestFrameStore

logger = logging.getLogger("screenbot.http")
BroadcastCallback = Callable[[bytes, FrameMeta], Awaitable[None]]


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def _clean_header(value: str | None, max_length: int = 200) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:max_length] if value else None


def create_app(settings: Settings, frames: LatestFrameStore, state: StateStore, broadcast: BroadcastCallback) -> web.Application:
    app = web.Application(client_max_size=settings.max_upload_bytes)
    upload_lock = asyncio.Lock()

    async def healthz(_: web.Request) -> web.Response:
        meta = frames.read_meta()
        return web.json_response({
            "ok": True,
            "has_frame": frames.exists(),
            "last_frame_at": meta.received_at if meta else None,
            "viewers": len(state.enabled_viewers),
        })

    async def upload(request: web.Request) -> web.Response:
        expected = f"Bearer {settings.upload_token}"
        received = request.headers.get("Authorization", "")
        if not hmac.compare_digest(received, expected):
            raise web.HTTPUnauthorized(text="invalid upload token")
        content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"image/jpeg", "image/jpg"}:
            raise web.HTTPUnsupportedMediaType(text="Content-Type must be image/jpeg")

        async with upload_lock:
            data = await request.read()
            if not data:
                raise web.HTTPBadRequest(text="empty upload")
            if len(data) > settings.max_upload_bytes:
                raise web.HTTPRequestEntityTooLarge(max_size=settings.max_upload_bytes, actual_size=len(data))
            if not data.startswith(b"\xff\xd8"):
                raise web.HTTPBadRequest(text="payload is not a JPEG image")
            meta = frames.save(
                data,
                width=_optional_int(request.headers.get("X-Screen-Width")),
                height=_optional_int(request.headers.get("X-Screen-Height")),
                jpeg_quality=_optional_int(request.headers.get("X-Jpeg-Quality")),
                client_name=_clean_header(request.headers.get("X-Client-Name")),
                client_time=_clean_header(request.headers.get("X-Client-Time")),
            )
            logger.info("Received screenshot: %.0f KB, %sx%s, client=%s", len(data) / 1024, meta.width or "?", meta.height or "?", meta.client_name or "?")
            await broadcast(data, meta)
        return web.json_response({"ok": True, "received_at": meta.received_at, "viewers": len(state.enabled_viewers)})

    app.router.add_get("/healthz", healthz)
    app.router.add_post("/upload", upload)
    return app
