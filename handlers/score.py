from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from models.db import session_scope
from services.audit_log import log_action
from services.match_service import ScoreParseError, create_score_session, parse_score_pairs
from services.user_service import get_user, get_user_by_username

router = Router(name="score")


def _extract_username(args: list[str]) -> tuple[str | None, list[str]]:
    if not args:
        return None, []
    first = args[0]
    if first.startswith("@"):
        return first[1:], args[1:]
    return None, args


def _confirm_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{session_id}"),
                InlineKeyboardButton(text="❌ Оспорить", callback_data=f"dispute:{session_id}"),
            ]
        ]
    )


@router.message(Command("score"))
async def cmd_score(message: Message) -> None:
    reporter_tg = message.from_user
    if reporter_tg is None:
        return

    raw_args = message.text.split()[1:] if message.text else []
    username, score_tokens = _extract_username(raw_args)

    if username is None:
        await message.answer(
            "Формат: /score @оппонент X:Y [X:Y ...]\nНапример: /score @Alex 2:0"
        )
        return

    try:
        pairs = parse_score_pairs(score_tokens)
    except ScoreParseError as e:
        await message.answer(str(e))
        return

    async with session_scope() as session:
        reporter = await get_user(session, reporter_tg.id)
        opponent = await get_user_by_username(session, username)

        if reporter is None or not reporter.is_active:
            await message.answer("Вы не зарегистрированы. Отправьте /start в личные сообщения боту.")
            return

        if opponent is None or not opponent.is_active:
            await message.answer(
                f"Не могу найти игрока @{username}. Он должен быть в списке участников "
                "и хотя бы раз отправить /start боту."
            )
            return

        if opponent.telegram_id == reporter.telegram_id:
            await message.answer("Нельзя заявить матч самому с собой 🙂")
            return

        matches = await create_score_session(session, reporter, opponent, pairs)
        session_id = matches[0].session_id

    log_action(reporter_tg.id, "score_submitted", f"opponent={opponent.telegram_id} pairs={pairs}")

    summary = "\n".join(f"{i+1}) {m.score1}:{m.score2}" for i, m in enumerate(matches))
    try:
        await message.bot.send_message(
            opponent.telegram_id,
            f"{reporter.display()} заявил результат матча с вами:\n{summary}\n\n"
            "Подтвердите или оспорьте результат:",
            reply_markup=_confirm_keyboard(session_id),
        )
    except TelegramForbiddenError:
        await message.answer(
            f"{opponent.display()} ещё не запускал(а) бота в личных сообщениях — "
            "попросите его/её отправить /start боту, чтобы получить запрос на подтверждение."
        )
        return

    await message.answer(
        f"Результат отправлен {opponent.display()} на подтверждение в личные сообщения.\n{summary}"
    )
