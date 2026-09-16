from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from services.audit_log import log_action
from services.match_service import (
    ScoreParseError,
    create_score_session,
    game_type_label,
    parse_aggregate_score,
    parse_game_type,
    parse_score_pairs,
)
from services.rating_service import get_rating_deltas_for_session, rebuild_all_ratings
from services.user_service import get_user_by_username

router = Router(name="score")

_USAGE = (
    "Формат: /score @игрок1 @игрок2 <тип> <счёт партий> <счёт1> [<счёт2> ...]\n"
    "тип — moscow/москва или america/америка\n"
    "Например: /score @alex @petya moscow 2:0 8:7 8:6"
)


@router.message(Command("score"))
async def cmd_score(message: Message) -> None:
    reporter_tg = message.from_user
    if reporter_tg is None:
        return

    args = message.text.split()[1:] if message.text else []
    if len(args) < 4 or not args[0].startswith("@") or not args[1].startswith("@"):
        await message.answer(_USAGE)
        return

    username1, username2, type_token, agg_token, *ball_tokens = args

    try:
        game_type = parse_game_type(type_token)
        agg1, agg2 = parse_aggregate_score(agg_token)
        pairs = parse_score_pairs(ball_tokens)
    except ScoreParseError as e:
        await message.answer(str(e))
        return

    total_games = agg1 + agg2
    if len(pairs) != total_games:
        await message.answer(
            f"Счёт партий {agg1}:{agg2} — это {total_games} партий(и), "
            f"а счётов по шарам указано {len(pairs)}."
        )
        return

    wins1 = sum(1 for p in pairs if p.score1 > p.score2)
    wins2 = len(pairs) - wins1
    if wins1 != agg1 or wins2 != agg2:
        await message.answer(
            f"Счёт по шарам не совпадает с заявленным счётом партий {agg1}:{agg2} "
            f"(по шарам получилось {wins1}:{wins2})."
        )
        return

    async with session_scope() as session:
        player1 = await get_user_by_username(session, username1)
        player2 = await get_user_by_username(session, username2)

        if player1 is None or not player1.is_active:
            await message.answer(
                f"Не могу найти игрока {username1}. Он должен быть в списке участников "
                "и хотя бы раз написать что-нибудь в этом чате."
            )
            return
        if player2 is None or not player2.is_active:
            await message.answer(
                f"Не могу найти игрока {username2}. Он должен быть в списке участников "
                "и хотя бы раз написать что-нибудь в этом чате."
            )
            return
        if player1.telegram_id == player2.telegram_id:
            await message.answer("Нельзя заявить матч игрока самому с собой 🙂")
            return

        matches = await create_score_session(
            session, reporter_tg.id, player1, player2, game_type, pairs
        )
        session_id = matches[0].session_id

        await rebuild_all_ratings(session)
        deltas = await get_rating_deltas_for_session(session, session_id)

        p1_mention, p2_mention = player1.mention(), player2.mention()

    log_action(
        reporter_tg.id,
        "score_submitted",
        f"player1={player1.telegram_id} player2={player2.telegram_id} "
        f"type={game_type} pairs={pairs}",
    )

    lines = [
        f"🎱 {game_type_label(game_type)}: {p1_mention} {agg1}:{agg2} {p2_mention}",
        "",
    ]
    for match, h1, h2 in deltas:
        d1 = h1.rating_after - h1.rating_before
        d2 = h2.rating_after - h2.rating_before
        lines.append(
            f"{match.score1}:{match.score2} | рейтинг: "
            f"{h1.rating_before:.0f} → {h1.rating_after:.0f} ({d1:+.0f}) / "
            f"{h2.rating_before:.0f} → {h2.rating_after:.0f} ({d2:+.0f})"
        )

    await message.answer("\n".join(lines))
