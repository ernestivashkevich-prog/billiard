from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import User


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.get(User, telegram_id)


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    username = username.lstrip("@").lower()
    stmt = select(User).where(User.username.isnot(None))
    result = await session.execute(stmt)
    for user in result.scalars():
        if user.username and user.username.lower() == username:
            return user
    return None


async def is_whitelisted(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(session, telegram_id)
    return bool(user and user.is_active)


async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(session, telegram_id)
    return bool(user and user.is_admin and user.is_active)


async def register_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    display_name: str | None,
) -> tuple[User | None, bool]:
    """Регистрация по /start. Возвращает (пользователь, был_ли_уже_в_whitelist).

    Пользователь должен быть предварительно добавлен админом через /adduser.
    """
    user = await get_user(session, telegram_id)
    if user is None or not user.is_active:
        return None, False

    user.username = username
    user.display_name = display_name or user.display_name
    user.registered = True
    await session.commit()
    return user, True


async def add_to_whitelist(
    session: AsyncSession,
    telegram_id: int,
    display_name: str | None = None,
    is_admin_flag: bool = False,
) -> User:
    user = await get_user(session, telegram_id)
    if user is not None:
        user.is_active = True
        if display_name:
            user.display_name = display_name
        if is_admin_flag:
            user.is_admin = True
        await session.commit()
        return user

    user = User(
        telegram_id=telegram_id,
        display_name=display_name,
        is_active=True,
        is_admin=is_admin_flag,
    )
    session.add(user)
    await session.commit()
    return user


async def remove_from_whitelist(session: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(session, telegram_id)
    if user is None:
        return False
    user.is_active = False
    await session.commit()
    return True
