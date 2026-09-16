from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from services.audit_log import log_action
from services.match_service import cancel_session, find_latest_session_by_reporter
from services.rating_service import rebuild_all_ratings

router = Router(name="cancel")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    args = message.text.split()[1:] if message.text else []

    async with session_scope() as session:
        session_id = args[0] if args else await find_latest_session_by_reporter(session, user.id)
        if not session_id:
            await message.answer("У вас нет заявленных матчей, которые можно отменить.")
            return

        ok = await cancel_session(session, session_id, user.id)
        if ok:
            await rebuild_all_ratings(session)

    if ok:
        log_action(user.id, "match_cancelled", f"session_id={session_id}")
        await message.answer("Заявка отменена, рейтинг пересчитан.")
    else:
        await message.answer(
            "Не удалось отменить: заявка не найдена, уже отменена или принадлежит не вам."
        )
