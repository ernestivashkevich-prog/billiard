from __future__ import annotations

import datetime
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Match, MatchStatus, User

SCORE_PAIR_RE = re.compile(r"^(\d+):(\d+)$")

_GAME_TYPES = {
    "moscow": "moscow",
    "москва": "moscow",
    "america": "america",
    "америка": "america",
}

_GAME_TYPE_LABELS = {
    "moscow": "Москва",
    "america": "Америка",
}


class ScoreParseError(Exception):
    pass


@dataclass
class ParsedScore:
    score1: int
    score2: int


def _parse_score_token(token: str) -> tuple[int, int]:
    m = SCORE_PAIR_RE.match(token)
    if not m:
        raise ScoreParseError(f"Не могу разобрать счёт «{token}». Формат: X:Y, например 2:0")
    return int(m.group(1)), int(m.group(2))


def parse_score_pairs(tokens: list[str]) -> list[ParsedScore]:
    if not tokens:
        raise ScoreParseError("Нужно указать хотя бы один счёт партии, например: 8:7")

    pairs = []
    for token in tokens:
        score1, score2 = _parse_score_token(token)
        if score1 == score2:
            raise ScoreParseError(f"Ничьих не бывает: «{token}» — счёт партии не может быть равным")
        pairs.append(ParsedScore(score1=score1, score2=score2))
    return pairs


def parse_aggregate_score(token: str) -> tuple[int, int]:
    """Сводный счёт партий (X:Y) — может быть равным, это не отдельная партия."""
    return _parse_score_token(token)


def parse_game_type(token: str) -> str:
    key = token.strip().lower()
    if key not in _GAME_TYPES:
        raise ScoreParseError(
            f"Не знаю тип игры «{token}». Укажите moscow/москва или america/америка."
        )
    return _GAME_TYPES[key]


def game_type_label(game_type: str | None) -> str:
    return _GAME_TYPE_LABELS.get(game_type or "", "Неизвестный тип")


async def create_score_session(
    session: AsyncSession,
    reporter_id: int,
    player1: User,
    player2: User,
    game_type: str,
    pairs: list[ParsedScore],
) -> list[Match]:
    session_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc)
    matches = []
    for idx, pair in enumerate(pairs):
        match = Match(
            player1_id=player1.telegram_id,
            player2_id=player2.telegram_id,
            score1=pair.score1,
            score2=pair.score2,
            game_type=game_type,
            status=MatchStatus.CONFIRMED.value,
            session_id=session_id,
            sequence=idx,
            reported_by=reporter_id,
            confirmed_at=now,
        )
        session.add(match)
        matches.append(match)
    await session.commit()
    for match in matches:
        await session.refresh(match)
    return matches


async def get_session_matches(session: AsyncSession, session_id: str) -> list[Match]:
    stmt = select(Match).where(Match.session_id == session_id).order_by(Match.sequence.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_match(session: AsyncSession, match_id: int) -> Match | None:
    return await session.get(Match, match_id)


async def cancel_session(session: AsyncSession, session_id: str, requester_id: int) -> bool:
    matches = await get_session_matches(session, session_id)
    if not matches:
        return False
    if any(m.status != MatchStatus.CONFIRMED.value for m in matches):
        return False
    if any(m.reported_by != requester_id for m in matches):
        return False
    for match in matches:
        match.status = MatchStatus.CANCELLED.value
    await session.commit()
    return True


async def find_latest_session_by_reporter(session: AsyncSession, reporter_id: int) -> str | None:
    stmt = (
        select(Match)
        .where(Match.reported_by == reporter_id, Match.status == MatchStatus.CONFIRMED.value)
        .order_by(Match.created_at.desc())
    )
    result = await session.execute(stmt)
    match = result.scalars().first()
    return match.session_id if match else None


async def get_head_to_head(session: AsyncSession, user_a: int, user_b: int) -> list[Match]:
    stmt = (
        select(Match)
        .where(
            Match.status == MatchStatus.CONFIRMED.value,
            or_(
                and_(Match.player1_id == user_a, Match.player2_id == user_b),
                and_(Match.player1_id == user_b, Match.player2_id == user_a),
            ),
        )
        .order_by(Match.confirmed_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_matches(session: AsyncSession, user_id: int, limit: int = 5) -> list[Match]:
    stmt = (
        select(Match)
        .where(
            Match.status == MatchStatus.CONFIRMED.value,
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
        )
        .order_by(Match.confirmed_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
