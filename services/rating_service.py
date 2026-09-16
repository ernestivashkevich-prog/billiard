from __future__ import annotations

import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Match, MatchStatus, RatingHistory, User
from rating.glicko2 import DEFAULT_RATING, DEFAULT_RD, DEFAULT_SIGMA, PlayerRating, update_match


async def rebuild_all_ratings(session: AsyncSession) -> None:
    """Полный пересчёт рейтингов всех игроков с нуля по истории confirmed-матчей.

    Используется после /score, /cancel и /editmatch — самый надёжный способ
    корректно пересчитать "всю последующую историю" для затронутых игроков,
    не гадая, какие именно матчи и в каком порядке нужно частично пересчитать.
    Матчи внутри одной сессии /score применяются в порядке ``sequence``.
    """
    users_result = await session.execute(select(User))
    users = {u.telegram_id: u for u in users_result.scalars().all()}

    for user in users.values():
        user.rating = DEFAULT_RATING
        user.rd = DEFAULT_RD
        user.sigma = DEFAULT_SIGMA
        user.last_match_at = None

    await session.execute(delete(RatingHistory))

    stmt = (
        select(Match)
        .where(Match.status == MatchStatus.CONFIRMED.value)
        .order_by(Match.confirmed_at.asc(), Match.session_id.asc(), Match.sequence.asc(), Match.id.asc())
    )
    result = await session.execute(stmt)
    matches = list(result.scalars().all())

    for match in matches:
        p1 = users.get(match.player1_id)
        p2 = users.get(match.player2_id)
        if p1 is None or p2 is None:
            continue

        before1 = PlayerRating(rating=p1.rating, rd=p1.rd, sigma=p1.sigma)
        before2 = PlayerRating(rating=p2.rating, rd=p2.rd, sigma=p2.sigma)

        days1 = _days_between(p1.last_match_at, match.confirmed_at)
        days2 = _days_between(p2.last_match_at, match.confirmed_at)

        after1, after2 = update_match(
            before1, before2, match.score1, match.score2,
            days_since_p1_last_match=days1,
            days_since_p2_last_match=days2,
        )

        p1.rating, p1.rd, p1.sigma = after1.rating, after1.rd, after1.sigma
        p2.rating, p2.rd, p2.sigma = after2.rating, after2.rd, after2.sigma
        p1.last_match_at = match.confirmed_at
        p2.last_match_at = match.confirmed_at

        session.add(
            RatingHistory(
                match_id=match.id,
                user_id=p1.telegram_id,
                rating_before=before1.rating, rd_before=before1.rd, sigma_before=before1.sigma,
                rating_after=after1.rating, rd_after=after1.rd, sigma_after=after1.sigma,
            )
        )
        session.add(
            RatingHistory(
                match_id=match.id,
                user_id=p2.telegram_id,
                rating_before=before2.rating, rd_before=before2.rd, sigma_before=before2.sigma,
                rating_after=after2.rating, rd_after=after2.rd, sigma_after=after2.sigma,
            )
        )

    await session.commit()


def _days_between(last: datetime.datetime | None, now: datetime.datetime | None) -> float | None:
    if last is None or now is None:
        return None
    delta = now - last
    return max(delta.total_seconds() / 86400.0, 0.0)


async def get_rating_deltas_for_session(session: AsyncSession, session_id: str) -> list[tuple[Match, RatingHistory, RatingHistory]]:
    """Для сообщения в группу: возвращает (матч, история p1, история p2) по каждому матчу сессии."""
    stmt = select(Match).where(Match.session_id == session_id).order_by(Match.sequence.asc())
    result = await session.execute(stmt)
    matches = list(result.scalars().all())

    output = []
    for match in matches:
        h1_stmt = select(RatingHistory).where(
            RatingHistory.match_id == match.id, RatingHistory.user_id == match.player1_id
        )
        h2_stmt = select(RatingHistory).where(
            RatingHistory.match_id == match.id, RatingHistory.user_id == match.player2_id
        )
        h1 = (await session.execute(h1_stmt)).scalar_one_or_none()
        h2 = (await session.execute(h2_stmt)).scalar_one_or_none()
        output.append((match, h1, h2))
    return output
