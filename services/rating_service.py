from __future__ import annotations

import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Match, MatchStatus, RatingHistory, User, UserRating
from rating.glicko2 import PlayerRating, conservative_rating, update_match

GAME_TYPES = ("moscow", "america")


async def rebuild_all_ratings(session: AsyncSession) -> None:
    """Полный пересчёт рейтингов всех игроков с нуля по истории confirmed-матчей.

    Рейтинг ведётся отдельно и независимо по каждому типу игры (Москва/Америка) —
    у игрока может быть разная сила в разных типах. Используется после /score,
    /cancel и /editmatch — самый надёжный способ корректно пересчитать "всю
    последующую историю" для затронутых игроков, не гадая, какие именно матчи
    и в каком порядке нужно частично пересчитать. Матчи внутри одной сессии
    /score применяются в порядке ``sequence``.
    """
    users_result = await session.execute(select(User))
    user_ids = [u.telegram_id for u in users_result.scalars().all()]

    await session.execute(delete(UserRating))
    await session.execute(delete(RatingHistory))

    for game_type in GAME_TYPES:
        pools = {uid: PlayerRating() for uid in user_ids}
        last_match_at: dict[int, datetime.datetime | None] = {uid: None for uid in user_ids}

        stmt = (
            select(Match)
            .where(Match.status == MatchStatus.CONFIRMED.value, Match.game_type == game_type)
            .order_by(Match.confirmed_at.asc(), Match.session_id.asc(), Match.sequence.asc(), Match.id.asc())
        )
        matches = (await session.execute(stmt)).scalars().all()

        for match in matches:
            if match.player1_id not in pools or match.player2_id not in pools:
                continue

            before1, before2 = pools[match.player1_id], pools[match.player2_id]
            days1 = _days_between(last_match_at[match.player1_id], match.confirmed_at)
            days2 = _days_between(last_match_at[match.player2_id], match.confirmed_at)

            after1, after2 = update_match(
                before1, before2, match.score1, match.score2,
                days_since_p1_last_match=days1,
                days_since_p2_last_match=days2,
            )

            pools[match.player1_id], pools[match.player2_id] = after1, after2
            last_match_at[match.player1_id] = match.confirmed_at
            last_match_at[match.player2_id] = match.confirmed_at

            session.add(
                RatingHistory(
                    match_id=match.id,
                    user_id=match.player1_id,
                    rating_before=before1.rating, rd_before=before1.rd, sigma_before=before1.sigma,
                    rating_after=after1.rating, rd_after=after1.rd, sigma_after=after1.sigma,
                )
            )
            session.add(
                RatingHistory(
                    match_id=match.id,
                    user_id=match.player2_id,
                    rating_before=before2.rating, rd_before=before2.rd, sigma_before=before2.sigma,
                    rating_after=after2.rating, rd_after=after2.rd, sigma_after=after2.sigma,
                )
            )

        for uid, pr in pools.items():
            session.add(
                UserRating(
                    user_id=uid,
                    game_type=game_type,
                    rating=pr.rating, rd=pr.rd, sigma=pr.sigma,
                    last_match_at=last_match_at[uid],
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


async def get_ranked_users(session: AsyncSession, game_type: str) -> list[tuple[User, UserRating | None]]:
    """Активные игроки с рейтингом по конкретному типу игры, по убыванию Elo.

    LEFT JOIN, а не INNER: игрок, только что добавленный админом, ещё не имеет
    строки UserRating (она появляется при первом /score где-либо в системе) —
    такой игрок всё равно должен быть виден в /top со стартовым рейтингом.
    """
    stmt = (
        select(User, UserRating)
        .outerjoin(
            UserRating,
            (UserRating.user_id == User.telegram_id) & (UserRating.game_type == game_type),
        )
        .where(User.is_active.is_(True))
    )
    rows = (await session.execute(stmt)).all()

    def _cr(row: tuple[User, UserRating | None]) -> float:
        ur = row[1]
        return conservative_rating(PlayerRating(rating=ur.rating, rd=ur.rd) if ur else PlayerRating())

    return sorted(rows, key=_cr, reverse=True)


async def get_history_for_match(session: AsyncSession, match_id: int, user_id: int) -> RatingHistory | None:
    stmt = select(RatingHistory).where(RatingHistory.match_id == match_id, RatingHistory.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_ratings(session: AsyncSession, user_id: int) -> dict[str, UserRating]:
    """Оба рейтинга игрока (Москва/Америка) по telegram_id."""
    stmt = select(UserRating).where(UserRating.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {r.game_type: r for r in rows}
