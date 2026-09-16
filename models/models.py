from __future__ import annotations

import datetime
import enum
import html

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from rating.glicko2 import DEFAULT_RATING, DEFAULT_RD, DEFAULT_SIGMA


class Base(DeclarativeBase):
    pass


class MatchStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class User(Base):
    """Игрок. Таблица одновременно служит whitelist'ом: строка появляется,
    когда админ добавляет telegram_id через /adduser (is_active=True), а
    заполняется данными профиля при /start."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def display(self) -> str:
        if self.display_name:
            return self.display_name
        if self.username:
            return f"@{self.username}"
        return str(self.telegram_id)

    def mention(self) -> str:
        """HTML-ссылка на профиль пользователя (кликабельное упоминание в группе)."""
        return f'<a href="tg://user?id={self.telegram_id}">{html.escape(self.display())}</a>'


class UserRating(Base):
    """Рейтинг игрока по одному типу игры (moscow/america) — независимые пулы Glicko-2."""

    __tablename__ = "user_ratings"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), primary_key=True)
    game_type: Mapped[str] = mapped_column(String(16), primary_key=True)

    rating: Mapped[float] = mapped_column(Float, default=DEFAULT_RATING, nullable=False)
    rd: Mapped[float] = mapped_column(Float, default=DEFAULT_RD, nullable=False)
    sigma: Mapped[float] = mapped_column(Float, default=DEFAULT_SIGMA, nullable=False)

    last_match_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    player1_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    player2_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

    score1: Mapped[int] = mapped_column(Integer, nullable=False)
    score2: Mapped[int] = mapped_column(Integer, nullable=False)
    game_type: Mapped[str | None] = mapped_column(String(16), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=MatchStatus.CONFIRMED.value, nullable=False)

    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # порядок партии внутри сессии

    reported_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    player1: Mapped[User] = relationship(foreign_keys=[player1_id])
    player2: Mapped[User] = relationship(foreign_keys=[player2_id])


class RatingHistory(Base):
    """Снапшот рейтинга после каждого подтверждённого матча."""

    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)

    rating_before: Mapped[float] = mapped_column(Float, nullable=False)
    rd_before: Mapped[float] = mapped_column(Float, nullable=False)
    sigma_before: Mapped[float] = mapped_column(Float, nullable=False)

    rating_after: Mapped[float] = mapped_column(Float, nullable=False)
    rd_after: Mapped[float] = mapped_column(Float, nullable=False)
    sigma_after: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
