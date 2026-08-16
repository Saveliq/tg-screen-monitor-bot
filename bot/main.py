from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, InputMediaPhoto, Message

from bot.config import Settings, load_settings
from bot.screenshot import ScreenCapture
from bot.state import StateStore


logger = logging.getLogger("screenbot")
router = Router()
settings: Settings
store: StateStore
capture: ScreenCapture


def is_allowed(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.allowed_user_ids)


async def deny(message: Message) -> None:
    if message.from_user:
        logger.warning("Denied Telegram user id=%s username=%s", message.from_user.id, message.from_user.username)
    await message.answer("Доступ запрещён.")


def caption(shot_width: int, shot_height: int, quality: int) -> str:
    now = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")
    return f"🖥 Live screen\n🕒 {now}\n📐 {shot_width}×{shot_height} · JPEG {quality}"


async def send_new_live_message(bot: Bot, chat_id: int, shot_data: bytes, width: int, height: int, quality: int) -> int:
    photo = BufferedInputFile(shot_data, filename="screen.jpg")
    sent = await bot.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=caption(width, height, quality),
        disable_notification=True,
    )
    store.set_message_id(chat_id, sent.message_id)
    return sent.message_id


async def update_viewer(bot: Bot, chat_id: int, message_id: int | None, shot_data: bytes, width: int, height: int, quality: int) -> None:
    if message_id is None:
        await send_new_live_message(bot, chat_id, shot_data, width, height, quality)
        return

    media = InputMediaPhoto(
        media=BufferedInputFile(shot_data, filename="screen.jpg"),
        caption=caption(width, height, quality),
    )

    try:
        await bot.edit_message_media(chat_id=chat_id, message_id=message_id, media=media)
    except TelegramBadRequest as exc:
        text = str(exc).lower()
        if "message is not modified" in text:
            return
        logger.warning("Cannot edit message %s in chat %s: %s; creating a new live message", message_id, chat_id, exc)
        await send_new_live_message(bot, chat_id, shot_data, width, height, quality)


@router.message(CommandStart())
async def command_start(message: Message, bot: Bot) -> None:
    if not is_allowed(message):
        await deny(message)
        return

    store.upsert(message.chat.id)
    shot = await asyncio.to_thread(capture.capture)
    viewer = store.get(message.chat.id)
    await update_viewer(bot, message.chat.id, viewer.message_id if viewer else None, shot.data, shot.width, shot.height, shot.quality)
    await message.answer(
        "✅ Просмотр включён. Картинка в сообщении Live screen будет обновляться автоматически.\n"
        "/screen — создать/обновить кадр сейчас\n"
        "/status — состояние клиента\n"
        "/stop — перестать обновлять экран в этом чате",
        disable_notification=True,
    )


@router.message(Command("screen"))
async def command_screen(message: Message, bot: Bot) -> None:
    if not is_allowed(message):
        await deny(message)
        return

    store.upsert(message.chat.id)
    shot = await asyncio.to_thread(capture.capture)
    viewer = store.get(message.chat.id)
    await update_viewer(bot, message.chat.id, viewer.message_id if viewer else None, shot.data, shot.width, shot.height, shot.quality)


@router.message(Command("status"))
async def command_status(message: Message) -> None:
    if not is_allowed(message):
        await deny(message)
        return

    viewer = store.get(message.chat.id)
    await message.answer(
        "✅ Клиент работает\n"
        f"Мониторов обнаружено: {capture.monitor_count}\n"
        f"SCREEN_MONITOR: {settings.screen_monitor}\n"
        f"Интервал: {settings.screen_interval} сек.\n"
        f"Автообновление этого чата: {'включено' if viewer and viewer.enabled else 'выключено'}"
    )


@router.message(Command("stop"))
async def command_stop(message: Message) -> None:
    if not is_allowed(message):
        await deny(message)
        return
    store.disable(message.chat.id)
    await message.answer("⏸ Автообновление экрана в этом чате выключено. /start — включить снова.")


@router.message(F.text)
async def other_text(message: Message) -> None:
    if not is_allowed(message):
        await deny(message)
        return
    await message.answer("Команды: /start, /screen, /status, /stop")


async def screenshot_loop(bot: Bot) -> None:
    while True:
        started = asyncio.get_running_loop().time()
        viewers = store.viewers

        if viewers:
            try:
                shot = await asyncio.to_thread(capture.capture)
                for viewer in viewers:
                    try:
                        await update_viewer(
                            bot,
                            viewer.chat_id,
                            viewer.message_id,
                            shot.data,
                            shot.width,
                            shot.height,
                            shot.quality,
                        )
                    except TelegramForbiddenError:
                        logger.warning("Bot was blocked in chat %s; disabling viewer", viewer.chat_id)
                        store.disable(viewer.chat_id)
                    except (TelegramNetworkError, TelegramBadRequest):
                        logger.exception("Telegram update failed for chat %s", viewer.chat_id)
            except Exception:
                logger.exception("Screenshot capture/update iteration failed")

        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(1.0, settings.screen_interval - elapsed))


async def async_main() -> None:
    global settings, store, capture

    settings = load_settings()
    store = StateStore(settings.state_file)
    capture = ScreenCapture(
        monitor_index=settings.screen_monitor,
        jpeg_quality=settings.jpeg_quality,
        max_width=settings.max_width,
    )

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    logger.info("Started @%s; monitors=%s; interval=%ss", me.username, capture.monitor_count, settings.screen_interval)

    updater = asyncio.create_task(screenshot_loop(bot), name="screenshot-loop")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        updater.cancel()
        with suppress(asyncio.CancelledError):
            await updater
        capture.close()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
