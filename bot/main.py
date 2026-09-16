from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import get_settings
from handlers import register_handlers
from models.db import init_db, session_scope
from services.match_service import get_pending_matches_older_than
from services.user_service import add_to_whitelist, get_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("billiard.main")


async def _seed_admins() -> None:
    settings = get_settings()
    async with session_scope() as session:
        for admin_id in settings.admin_ids:
            existing = await get_user(session, admin_id)
            if existing is None:
                await add_to_whitelist(session, admin_id, is_admin_flag=True)
            elif not existing.is_admin:
                existing.is_admin = True
                await session.commit()


async def _check_pending_reminders(bot: Bot) -> None:
    settings = get_settings()

    async with session_scope() as session:
        overdue_24h = await get_pending_matches_older_than(session, settings.reminder_hours)
        for match in overdue_24h:
            if match.reminder_sent:
                continue
            try:
                await bot.send_message(
                    match.player2_id,
                    f"⏰ Напоминание: вас ждёт неподтверждённый результат матча "
                    f"({match.score1}:{match.score2}). Пожалуйста, подтвердите или оспорьте его.",
                )
            except TelegramForbiddenError:
                pass
            match.reminder_sent = True
        await session.commit()

        overdue_48h = await get_pending_matches_older_than(session, settings.escalation_hours)
        from services.user_service import list_active_users

        admins = [u for u in await list_active_users(session) if u.is_admin]
        for match in overdue_48h:
            if match.escalated:
                continue
            for admin in admins:
                try:
                    await bot.send_message(
                        admin.telegram_id,
                        f"⚠️ Матч #{match.id} (session {match.session_id}) не подтверждён "
                        f"уже {settings.escalation_hours}+ часов. Требуется ручной разбор: "
                        f"/resolve {match.session_id} confirm|cancel",
                    )
                except Exception:
                    pass
            match.escalated = True
        await session.commit()


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    register_handlers(dp)

    await init_db()
    await _seed_admins()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_pending_reminders, "interval", hours=1, args=[bot])
    scheduler.start()

    logger.info("Бот запущен, начинаю polling")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
