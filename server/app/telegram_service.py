from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, InputMediaPhoto, Message

from .config import Settings
from .state import StateStore
from .storage import FrameMeta, LatestFrameStore

logger = logging.getLogger("screenbot.telegram")


class TelegramService:
    def __init__(self, bot: Bot, settings: Settings, state: StateStore, frames: LatestFrameStore) -> None:
        self.bot = bot
        self.settings = settings
        self.state = state
        self.frames = frames
        self.router = self._build_router()

    def _is_allowed(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.settings.allowed_user_ids)

    async def _deny(self, message: Message) -> None:
        if message.from_user:
            logger.warning("Denied user id=%s username=%s", message.from_user.id, message.from_user.username)
        await message.answer("Доступ запрещён.")

    @staticmethod
    def _caption(meta: FrameMeta) -> str:
        received = meta.received_datetime.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")
        dimensions = f"\n📐 {meta.width}×{meta.height}" if meta.width and meta.height else ""
        source = f"\n💻 {meta.client_name}" if meta.client_name else ""
        return f"🖥 Live screen\n🕒 {received}{dimensions}{source}"

    async def _send_new(self, chat_id: int, data: bytes, meta: FrameMeta) -> int:
        sent = await self.bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(data, filename="screen.jpg"),
            caption=self._caption(meta),
            disable_notification=True,
        )
        self.state.set_message_id(chat_id, sent.message_id)
        return sent.message_id

    async def update_viewer(self, chat_id: int, data: bytes, meta: FrameMeta) -> None:
        viewer = self.state.get(chat_id)
        message_id = viewer.message_id if viewer else None
        if message_id is None:
            await self._send_new(chat_id, data, meta)
            return
        media = InputMediaPhoto(media=BufferedInputFile(data, filename="screen.jpg"), caption=self._caption(meta))
        try:
            await self.bot.edit_message_media(chat_id=chat_id, message_id=message_id, media=media)
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.warning("Cannot edit live message %s in chat %s: %s", message_id, chat_id, exc)
            await self._send_new(chat_id, data, meta)

    async def broadcast(self, data: bytes, meta: FrameMeta) -> None:
        for viewer in self.state.enabled_viewers:
            try:
                await self.update_viewer(viewer.chat_id, data, meta)
            except TelegramForbiddenError:
                logger.warning("Bot blocked in chat %s; disabling viewer", viewer.chat_id)
                self.state.disable(viewer.chat_id)
            except (TelegramNetworkError, TelegramBadRequest):
                logger.exception("Telegram update failed for chat %s", viewer.chat_id)
            except Exception:
                logger.exception("Unexpected Telegram update failure for chat %s", viewer.chat_id)

    def _status_text(self) -> str:
        meta = self.frames.read_meta()
        if meta is None or not self.frames.exists():
            return "🔴 Скриншоты ещё не поступали с Windows-клиента."
        age = max(0, int((datetime.now(timezone.utc) - meta.received_datetime).total_seconds()))
        online = age <= self.settings.offline_after_seconds
        status = "🟢 Windows client online" if online else "🔴 Windows client offline"
        dimensions = f"\nРазрешение: {meta.width}×{meta.height}" if meta.width and meta.height else ""
        source = f"\nКлиент: {meta.client_name}" if meta.client_name else ""
        return f"{status}\nПоследний кадр: {age} сек. назад\nРазмер JPEG: {meta.size_bytes / 1024:.0f} KB{dimensions}{source}"

    def _build_router(self) -> Router:
        router = Router()

        @router.message(CommandStart())
        async def start(message: Message) -> None:
            if not self._is_allowed(message):
                await self._deny(message)
                return
            self.state.enable(message.chat.id)
            if self.frames.exists():
                meta = self.frames.read_meta()
                if meta is not None:
                    await self.update_viewer(message.chat.id, self.frames.read_image(), meta)
                    await message.answer("✅ Просмотр включён. Live screen будет обновляться при каждом новом кадре.")
                    return
            await message.answer("✅ Просмотр включён. Ожидаю первый скриншот от Windows-клиента.")

        @router.message(Command("screen"))
        async def screen(message: Message) -> None:
            if not self._is_allowed(message):
                await self._deny(message)
                return
            if not self.frames.exists():
                await message.answer("Скриншотов ещё нет.")
                return
            meta = self.frames.read_meta()
            if meta is None:
                await message.answer("Последний кадр повреждён или ещё не готов.")
                return
            self.state.enable(message.chat.id)
            await self.update_viewer(message.chat.id, self.frames.read_image(), meta)

        @router.message(Command("status"))
        async def status(message: Message) -> None:
            if not self._is_allowed(message):
                await self._deny(message)
                return
            await message.answer(self._status_text())

        @router.message(Command("stop"))
        async def stop(message: Message) -> None:
            if not self._is_allowed(message):
                await self._deny(message)
                return
            self.state.disable(message.chat.id)
            await message.answer("⏸ Автообновление выключено. /start — включить снова.")

        @router.message(F.text)
        async def other(message: Message) -> None:
            if not self._is_allowed(message):
                await self._deny(message)
                return
            await message.answer("Команды: /start, /screen, /status, /stop")

        return router
