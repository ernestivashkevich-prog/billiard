from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from models.db import session_scope
from rating.glicko2 import PlayerRating, conservative_rating
from services.user_service import list_active_users

router = Router(name="top")


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    async with session_scope() as session:
        users = await list_active_users(session)

    if not users:
        await message.answer("Пока нет ни одного игрока в рейтинге.")
        return

    ranked = sorted(
        users,
        key=lambda u: conservative_rating(PlayerRating(rating=u.rating, rd=u.rd, sigma=u.sigma)),
        reverse=True,
    )

    lines = ["🏆 Таблица лидеров (Elo = рейтинг − 2×RD):", ""]
    for i, u in enumerate(ranked, start=1):
        cr = conservative_rating(PlayerRating(rating=u.rating, rd=u.rd, sigma=u.sigma))
        lines.append(f"{i}. {u.display()} — Elo {cr:.0f} (рейтинг {u.rating:.0f}, RD {u.rd:.0f})")

    await message.answer("\n".join(lines))
