from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web

from .config import load_settings
from .http_api import create_app
from .state import StateStore
from .storage import LatestFrameStore
from .telegram_service import TelegramService

logger = logging.getLogger("screenbot")


async def async_main() -> None:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    state = StateStore(settings.data_dir / "state.json")
    frames = LatestFrameStore(settings.data_dir)

    session = AiohttpSession(proxy=settings.proxy_url or None)
    bot = Bot(token=settings.bot_token, session=session)
    telegram = TelegramService(bot, settings, state, frames)
    dispatcher = Dispatcher()
    dispatcher.include_router(telegram.router)

    app = create_app(settings, frames, state, telegram.broadcast)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, settings.http_host, settings.http_port)
    await site.start()

    me = await bot.get_me()
    logger.info("Telegram bot @%s started", me.username)
    logger.info("Telegram proxy: %s", settings.proxy_url or "disabled")
    logger.info("Upload API listening on http://%s:%s/upload", settings.http_host, settings.http_port)

    polling = asyncio.create_task(
        dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types()),
        name="telegram-polling",
    )
    try:
        await polling
    finally:
        polling.cancel()
        with suppress(asyncio.CancelledError):
            await polling
        await runner.cleanup()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
