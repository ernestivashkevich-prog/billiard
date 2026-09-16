from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import get_settings
from models.db import session_scope
from services.user_service import is_whitelisted, register_user

# Команды, доступные всем (даже не из whitelist), чтобы объяснить, что делать дальше
_OPEN_COMMANDS = {"/start"}


def _chat_id_of(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat.id
    return None


class GroupOnlyMiddleware(BaseMiddleware):
    """Бот работает только внутри рабочего группового чата (GROUP_CHAT_ID)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat_id = _chat_id_of(event)
        if chat_id is None:
            return await handler(event, data)

        settings = get_settings()
        if chat_id != settings.group_chat_id:
            if isinstance(event, Message):
                await event.answer("Этот бот работает только в общем групповом чате.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Этот бот работает только в общем групповом чате.", show_alert=True)
            return None

        return await handler(event, data)


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        text = None

        if isinstance(event, Message):
            user = event.from_user
            text = event.text or ""
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        command = text.split()[0].split("@")[0] if text else ""
        if command in _OPEN_COMMANDS:
            return await handler(event, data)

        async with session_scope() as session:
            allowed = await is_whitelisted(session, user.id)
            if allowed and isinstance(event, Message):
                # Синхронизируем username/имя при каждом сообщении в группе,
                # чтобы не требовать отдельного /start в личке для регистрации.
                await register_user(session, user.id, user.username, user.full_name)

        if not allowed:
            if isinstance(event, Message):
                await event.answer(
                    "Вы не в списке участников. Обратитесь к администратору, "
                    "чтобы вас добавили, а затем отправьте /start."
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("Вы не в списке участников.", show_alert=True)
            return None

        return await handler(event, data)
