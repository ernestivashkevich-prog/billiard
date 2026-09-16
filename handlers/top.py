from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import session_scope
from rating.glicko2 import PlayerRating, conservative_rating
from services.match_service import ScoreParseError, game_type_label, get_win_loss_counts_by_type, parse_game_type
from services.rating_service import GAME_TYPES, get_ranked_users

router = Router(name="top")


async def _format_section(session: AsyncSession, game_type: str) -> str:
    ranked = await get_ranked_users(session, game_type)
    counts = await get_win_loss_counts_by_type(session, game_type)

    lines = [f"🏆 {game_type_label(game_type)}:", ""]
    if not ranked:
        lines.append("Пока нет ни одного игрока в рейтинге.")
        return "\n".join(lines)

    for i, (u, ur) in enumerate(ranked, start=1):
        player = PlayerRating(rating=ur.rating, rd=ur.rd) if ur else PlayerRating()
        cr = conservative_rating(player)
        wins, losses = counts.get(u.telegram_id, (0, 0))
        lines.append(f"{i}. {u.display()} — Elo {cr:.0f} | W/L {wins}/{losses}")

    return "\n".join(lines)


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    args = message.text.split()[1:] if message.text else []

    types_to_show = list(GAME_TYPES)
    if args:
        try:
            types_to_show = [parse_game_type(args[0])]
        except ScoreParseError as e:
            await message.answer(str(e))
            return

    async with session_scope() as session:
        sections = [await _format_section(session, gt) for gt in types_to_show]

    await message.answer("\n\n".join(sections))
