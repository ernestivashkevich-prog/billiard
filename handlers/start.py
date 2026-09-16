from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from models.db import session_scope
from services.audit_log import log_action
from services.user_service import register_user

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    async with session_scope() as session:
        db_user, in_whitelist = await register_user(
            session, user.id, user.username, user.full_name
        )

    if not in_whitelist:
        await message.answer(
            "Привет! Пока вас нет в списке участников лиги.\n"
            "Попросите администратора добавить ваш Telegram ID командой /adduser, "
            "а затем снова отправьте /start."
        )
        return

    log_action(user.id, "start", f"username={user.username}")
    await message.answer(
        f"Добро пожаловать, {db_user.display()}! Вы зарегистрированы в системе рейтинга.\n\n"
        "Основные команды:\n"
        "/score @оппонент X:Y — заявить результат матча\n"
        "/top — таблица лидеров\n"
        "/stats — ваша статистика\n"
        "/faq — как считается рейтинг"
    )
