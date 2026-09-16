from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings
from handlers import register_handlers
from models.db import init_db, session_scope
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


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    register_handlers(dp)

    await init_db()
    await _seed_admins()

    logger.info("Бот запущен, начинаю polling")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
