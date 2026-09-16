from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from models.db import session_scope
from services.user_service import is_whitelisted

# Команды, доступные всем (даже не из whitelist), чтобы объяснить, что делать дальше
_OPEN_COMMANDS = {"/start"}


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
