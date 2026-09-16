from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from models.models import MatchStatus
from services.audit_log import log_action
from services.match_service import ScoreParseError, get_match, parse_score_pairs
from services.rating_service import rebuild_all_ratings
from services.user_service import add_to_whitelist, is_admin, remove_from_whitelist

router = Router(name="admin")


async def _require_admin(message: Message) -> bool:
    if message.from_user is None:
        return False
    async with session_scope() as session:
        return await is_admin(session, message.from_user.id)


@router.message(Command("adduser"))
async def cmd_adduser(message: Message) -> None:
    if not await _require_admin(message):
        await message.answer("Команда доступна только администратору.")
        return

    args = message.text.split()[1:] if message.text else []
    if not args or not args[0].lstrip("-").isdigit():
        await message.answer("Формат: /adduser «telegram_id» [имя]")
        return

    telegram_id = int(args[0])
    display_name = " ".join(args[1:]) if len(args) > 1 else None

    async with session_scope() as session:
        user = await add_to_whitelist(session, telegram_id, display_name)

    log_action(message.from_user.id, "adduser", f"target={telegram_id}")
    await message.answer(f"Игрок {user.display()} ({telegram_id}) добавлен в список участников.")


@router.message(Command("removeuser"))
async def cmd_removeuser(message: Message) -> None:
    if not await _require_admin(message):
        await message.answer("Команда доступна только администратору.")
        return

    args = message.text.split()[1:] if message.text else []
    if not args or not args[0].lstrip("-").isdigit():
        await message.answer("Формат: /removeuser «telegram_id»")
        return

    telegram_id = int(args[0])
    async with session_scope() as session:
        ok = await remove_from_whitelist(session, telegram_id)

    log_action(message.from_user.id, "removeuser", f"target={telegram_id}")
    if ok:
        await message.answer(f"Игрок {telegram_id} удалён из списка участников. История матчей сохранена.")
    else:
        await message.answer("Такой игрок не найден.")


@router.message(Command("editmatch"))
async def cmd_editmatch(message: Message) -> None:
    if not await _require_admin(message):
        await message.answer("Команда доступна только администратору.")
        return

    args = message.text.split()[1:] if message.text else []
    if len(args) < 2 or not args[0].isdigit():
        await message.answer(
            "Формат: /editmatch «match_id» X:Y — исправить счёт\n"
            "/editmatch «match_id» delete — удалить матч"
        )
        return

    match_id = int(args[0])
    action = args[1]

    async with session_scope() as session:
        match = await get_match(session, match_id)
        if match is None:
            await message.answer("Матч не найден.")
            return

        if action.lower() == "delete":
            match.status = MatchStatus.CANCELLED.value
        else:
            try:
                pairs = parse_score_pairs([action])
            except ScoreParseError as e:
                await message.answer(str(e))
                return
            match.score1, match.score2 = pairs[0].score1, pairs[0].score2

        await session.commit()
        await rebuild_all_ratings(session)

    log_action(message.from_user.id, "editmatch", f"match_id={match_id} action={action}")
    await message.answer(f"Матч {match_id} изменён, рейтинги всех игроков пересчитаны.")
