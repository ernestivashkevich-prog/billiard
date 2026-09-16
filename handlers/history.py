from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from services.match_service import game_type_label, get_head_to_head
from services.user_service import get_user, get_user_by_username

router = Router(name="history")


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    args = message.text.split()[1:] if message.text else []
    requester = message.from_user
    if requester is None:
        return

    if not args:
        await message.answer("Формат: /history @игрок")
        return

    async with session_scope() as session:
        me = await get_user(session, requester.id)
        opponent = await get_user_by_username(session, args[0])

        if me is None:
            await message.answer("Вы не зарегистрированы. Отправьте /start.")
            return
        if opponent is None:
            await message.answer(f"Не могу найти игрока {args[0]}.")
            return

        matches = await get_head_to_head(session, me.telegram_id, opponent.telegram_id)

    if not matches:
        await message.answer(f"У вас пока нет сыгранных матчей с {opponent.display()}.")
        return

    lines = [f"История встреч с {opponent.display()}:", ""]
    wins = 0
    for m in matches:
        is_me_p1 = m.player1_id == me.telegram_id
        my_score = m.score1 if is_me_p1 else m.score2
        opp_score = m.score2 if is_me_p1 else m.score1
        if my_score > opp_score:
            wins += 1
        date_str = m.confirmed_at.strftime("%d.%m.%Y") if m.confirmed_at else "?"
        lines.append(f"{date_str}: {game_type_label(m.game_type)} {my_score}:{opp_score}")

    lines.append("")
    lines.append(f"Итого: {wins}-{len(matches) - wins}")

    await message.answer("\n".join(lines))
