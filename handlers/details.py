from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from rating.glicko2 import PlayerRating, conservative_rating, expected_win_probability
from services.match_service import game_type_label, get_user_matches
from services.rating_service import get_history_for_match
from services.user_service import get_user

router = Router(name="details")


@router.message(Command("details"))
async def cmd_details(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    async with session_scope() as session:
        matches = await get_user_matches(session, user.id, limit=1)
        if not matches:
            await message.answer("У вас пока нет сыгранных матчей.")
            return
        match = matches[0]

        is_p1 = match.player1_id == user.id
        opponent_id = match.player2_id if is_p1 else match.player1_id
        my_score = match.score1 if is_p1 else match.score2
        opp_score = match.score2 if is_p1 else match.score1

        opponent = await get_user(session, opponent_id)
        opp_name = opponent.display() if opponent else str(opponent_id)

        h_me = await get_history_for_match(session, match.id, user.id)
        h_opp = await get_history_for_match(session, match.id, opponent_id)

        if h_me is None or h_opp is None:
            await message.answer("Не нашёл историю рейтинга по этому матчу.")
            return

        win_prob = expected_win_probability(
            PlayerRating(rating=h_me.rating_before, rd=h_me.rd_before),
            PlayerRating(rating=h_opp.rating_before, rd=h_opp.rd_before),
        )

        elo_before = conservative_rating(PlayerRating(rating=h_me.rating_before, rd=h_me.rd_before))
        elo_after = conservative_rating(PlayerRating(rating=h_me.rating_after, rd=h_me.rd_after))
        elo_delta = elo_after - elo_before
        won = my_score > opp_score

    if won and win_prob >= 0.5:
        verdict = "Ожидаемая победа — вы и так были фаворитом, поэтому прибавка небольшая."
    elif won:
        verdict = "Неожиданная победа (апсет) — вы были аутсайдером, поэтому прибавка больше обычной."
    elif win_prob >= 0.5:
        verdict = "Неожиданное поражение — вы были фаворитом, поэтому рейтинг падает сильнее обычного."
    else:
        verdict = "Ожидаемое поражение — соперник и так был сильнее по рейтингу, поэтому потеря небольшая."

    text = (
        f"📋 Подробности последнего матча\n\n"
        f"{game_type_label(match.game_type)}: вы vs {opp_name}, счёт {my_score}:{opp_score}\n\n"
        f"Перед матчем:\n"
        f"Вы — рейтинг {h_me.rating_before:.0f}, RD {h_me.rd_before:.0f}\n"
        f"{opp_name} — рейтинг {h_opp.rating_before:.0f}, RD {h_opp.rd_before:.0f}\n\n"
        f"Ваш ожидаемый шанс на победу (по рейтингу до матча): {win_prob:.0%}\n"
        f"{verdict}\n\n"
        f"Elo: {elo_before:.0f} → {elo_after:.0f} ({elo_delta:+.0f})\n"
        f"Чем выше был ваш RD ({h_me.rd_before:.0f}) и чем неожиданнее результат — тем сильнее "
        f"меняется рейтинг за один матч."
    )

    await message.answer(text)
