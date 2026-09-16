from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from services.match_service import get_user_matches
from services.user_service import get_user, get_user_by_username

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    args = message.text.split()[1:] if message.text else []
    requester = message.from_user
    if requester is None:
        return

    async with session_scope() as session:
        if args and args[0].startswith("@"):
            target = await get_user_by_username(session, args[0])
            if target is None:
                await message.answer(f"Не могу найти игрока {args[0]}.")
                return
        else:
            target = await get_user(session, requester.id)
            if target is None:
                await message.answer("Вы не зарегистрированы. Отправьте /start.")
                return

        matches = await get_user_matches(session, target.telegram_id, limit=5)

        wins = 0
        losses = 0
        recent_lines = []
        for m in matches:
            is_p1 = m.player1_id == target.telegram_id
            my_score = m.score1 if is_p1 else m.score2
            opp_score = m.score2 if is_p1 else m.score1
            opponent_id = m.player2_id if is_p1 else m.player1_id
            opponent = await get_user(session, opponent_id)
            opp_name = opponent.display() if opponent else str(opponent_id)

            if my_score > opp_score:
                wins += 1
                result = "🟢"
            else:
                losses += 1
                result = "🔴"
            recent_lines.append(f"{result} {my_score}:{opp_score} vs {opp_name}")

        # W/L считаем по всей истории, а не только по последним 5
        all_matches = await get_user_matches(session, target.telegram_id, limit=10_000)
        total_wins = sum(
            1
            for m in all_matches
            if (m.player1_id == target.telegram_id and m.score1 > m.score2)
            or (m.player2_id == target.telegram_id and m.score2 > m.score1)
        )
        total_losses = len(all_matches) - total_wins

    text = (
        f"📊 Статистика: {target.display()}\n"
        f"Рейтинг: {target.rating:.0f} (RD {target.rd:.0f})\n"
        f"W/L: {total_wins}/{total_losses}\n"
    )
    if recent_lines:
        text += "\nПоследние матчи:\n" + "\n".join(recent_lines)

    await message.answer(text)
