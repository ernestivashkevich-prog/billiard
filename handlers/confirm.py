from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.config import get_settings
from models.models import MatchStatus
from models.db import session_scope
from services.audit_log import log_action
from services.match_service import get_session_matches
from services.rating_service import confirm_session, get_rating_deltas_for_session
from services.user_service import get_user, list_active_users

router = Router(name="confirm")


@router.callback_query(lambda c: c.data and c.data.startswith("confirm:"))
async def on_confirm(callback: CallbackQuery) -> None:
    session_id = callback.data.split(":", 1)[1]
    responder = callback.from_user

    async with session_scope() as session:
        matches = await get_session_matches(session, session_id)
        if not matches:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        if matches[0].player2_id != responder.id:
            await callback.answer("Это не ваша заявка на подтверждение.", show_alert=True)
            return

        if matches[0].status != MatchStatus.PENDING.value:
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            return

        reporter = await get_user(session, matches[0].player1_id)
        opponent = await get_user(session, matches[0].player2_id)

        await confirm_session(session, session_id)
        deltas = await get_rating_deltas_for_session(session, session_id)

    log_action(responder.id, "match_confirmed", f"session_id={session_id}")

    lines = []
    for match, h1, h2 in deltas:
        d1 = h1.rating_after - h1.rating_before
        d2 = h2.rating_after - h2.rating_before
        lines.append(
            f"{reporter.display()} {match.score1}:{match.score2} {opponent.display()} | "
            f"рейтинг: {h1.rating_before:.0f} → {h1.rating_after:.0f} ({d1:+.0f}) / "
            f"{h2.rating_before:.0f} → {h2.rating_after:.0f} ({d2:+.0f})"
        )
    text = "\n".join(lines)

    await callback.message.edit_text(f"Результат подтверждён ✅\n\n{text}")
    await callback.answer("Подтверждено!")

    settings = get_settings()
    if settings.group_chat_id:
        try:
            await callback.bot.send_message(settings.group_chat_id, text)
        except Exception:
            pass


@router.callback_query(lambda c: c.data and c.data.startswith("dispute:"))
async def on_dispute(callback: CallbackQuery) -> None:
    session_id = callback.data.split(":", 1)[1]
    responder = callback.from_user

    async with session_scope() as session:
        matches = await get_session_matches(session, session_id)
        if not matches:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        if matches[0].player2_id != responder.id:
            await callback.answer("Это не ваша заявка на подтверждение.", show_alert=True)
            return

        if matches[0].status != MatchStatus.PENDING.value:
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            return

        for match in matches:
            match.status = MatchStatus.DISPUTED.value
        await session.commit()

        reporter = await get_user(session, matches[0].player1_id)
        opponent = await get_user(session, matches[0].player2_id)
        active_users = await list_active_users(session)
        admins = [u for u in active_users if u.is_admin]

    log_action(responder.id, "match_disputed", f"session_id={session_id}")

    summary = "\n".join(f"{m.score1}:{m.score2}" for m in matches)
    await callback.message.edit_text(f"Результат оспорен ❌\n{summary}\n\nАдминистратор разрешит спор.")
    await callback.answer("Оспорено")

    for admin in admins:
        try:
            await callback.bot.send_message(
                admin.telegram_id,
                f"⚠️ Спор по матчу: {reporter.display()} vs {opponent.display()}\n{summary}\n"
                f"session_id: {session_id}\n"
                f"Разрешить: /resolve {session_id} confirm — подтвердить как есть\n"
                f"/resolve {session_id} cancel — отменить матч",
            )
        except Exception:
            pass
