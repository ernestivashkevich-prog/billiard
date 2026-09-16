from aiogram import Dispatcher

from handlers import admin, cancel, faq, history, score, start, stats, top
from handlers.middleware import GroupOnlyMiddleware, WhitelistMiddleware


def register_handlers(dp: Dispatcher) -> None:
    dp.message.middleware(GroupOnlyMiddleware())
    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(GroupOnlyMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    dp.include_router(start.router)
    dp.include_router(score.router)
    dp.include_router(cancel.router)
    dp.include_router(top.router)
    dp.include_router(stats.router)
    dp.include_router(history.router)
    dp.include_router(faq.router)
    dp.include_router(admin.router)
