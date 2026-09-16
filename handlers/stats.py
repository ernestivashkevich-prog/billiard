from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from rating.glicko2 import PlayerRating, conservative_rating
from services.match_service import game_type_label, get_user_matches, get_win_loss_counts_by_type
from services.rating_service import GAME_TYPES, get_user_ratings
from services.user_service import get_user, get_user_by_username

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    args = message.text.split()[1:] if message.text else []
    requester = message.from_user
    if requester is None:
        return

    async with session_scope() as session:
        if args:
            target = await get_user_by_username(session, args[0])
            if target is None:
                await message.answer(f"Не могу найти игрока {args[0]}.")
                return
        else:
            target = await get_user(session, requester.id)
            if target is None:
                await message.answer("Вы не зарегистрированы. Отправьте /start.")
                return

        ratings = await get_user_ratings(session, target.telegram_id)

        rating_lines = []
        for game_type in GAME_TYPES:
            ur = ratings.get(game_type)
            player = PlayerRating(rating=ur.rating, rd=ur.rd) if ur else PlayerRating()
            cr = conservative_rating(player)
            wl = await get_win_loss_counts_by_type(session, game_type)
            wins, losses = wl.get(target.telegram_id, (0, 0))
            rating_lines.append(
                f"{game_type_label(game_type)}: Elo {cr:.0f} (рейтинг {player.rating:.0f}, "
                f"RD {player.rd:.0f}), W/L {wins}/{losses}"
            )

        matches = await get_user_matches(session, target.telegram_id, limit=5)

        recent_lines = []
        for m in matches:
            is_p1 = m.player1_id == target.telegram_id
            my_score = m.score1 if is_p1 else m.score2
            opp_score = m.score2 if is_p1 else m.score1
            opponent_id = m.player2_id if is_p1 else m.player1_id
            opponent = await get_user(session, opponent_id)
            opp_name = opponent.display() if opponent else str(opponent_id)

            result = "🟢" if my_score > opp_score else "🔴"
            recent_lines.append(
                f"{result} {game_type_label(m.game_type)} {my_score}:{opp_score} vs {opp_name}"
            )

    text = f"📊 Статистика: {target.display()}\n\n" + "\n".join(rating_lines)
    if recent_lines:
        text += "\n\nПоследние матчи:\n" + "\n".join(recent_lines)

    await message.answer(text)
