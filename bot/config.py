from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            result.append(int(part))
    return result


@dataclass(frozen=True)
class Settings:
    bot_token: str
    group_chat_id: int
    admin_ids: list[int] = field(default_factory=list)
    database_url: str = "sqlite+aiosqlite:///./data/billiard.db"


@lru_cache
def get_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN не задан в окружении (.env)")

    group_chat_id_raw = os.getenv("GROUP_CHAT_ID")
    if not group_chat_id_raw:
        raise RuntimeError(
            "GROUP_CHAT_ID не задан в окружении (.env) — бот работает только "
            "внутри одного группового чата, id обязателен."
        )
    group_chat_id = int(group_chat_id_raw)

    return Settings(
        bot_token=bot_token,
        group_chat_id=group_chat_id,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/billiard.db"),
    )
