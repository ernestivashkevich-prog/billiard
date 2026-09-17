from __future__ import annotations

import random

from models.models import User, UserRating

_PLACE_PHRASES: dict[int, list[str]] = {
    1: [
        "👑 Свершилось! {winner} скидывает {loser} с трона и становится новым королём {type}!",
        "🔥 Революция в {type}! {winner} только что отобрал корону у {loser}!",
        "💥 Землетрясение в топе {type}: {winner} обошёл {loser} и теперь безоговорочный №1!",
        "🚨 Внеочередной выпуск новостей: {winner} — новый чемпион {type}, {loser} низложен!",
        "🏆 {winner} принимает корону {type}, а {loser} тихонько плачет в углу бильярдной.",
    ],
    2: [
        "🥈 {winner} подвинул {loser} и заехал на 2-е место в {type}!",
        "😤 {loser}, подвиньтесь — {winner} теперь серебряный призёр {type}!",
        "📈 {winner} обошёл {loser} по пути на пьедестал {type}. Красиво зашёл.",
        "🥈 Серебро сменило хозяина: {winner} обошёл {loser} в {type}.",
    ],
    3: [
        "🥉 {winner} втиснулся в топ-3 {type}, выпихнув оттуда {loser}!",
        "👀 {winner} прокрался на 3-е место в {type} — {loser}, можно собирать вещи.",
        "🎉 Добро пожаловать в топ-3 {type}, {winner}! {loser}, увидимся на 4-м месте.",
        "🐍 {winner} тихо подкрался и занял бронзу {type}, оттеснив {loser}.",
    ],
}


def detect_top3_changes(
    before: list[tuple[User, UserRating | None]],
    after: list[tuple[User, UserRating | None]],
    type_label: str,
) -> list[str]:
    """Сравнивает топ-3 до и после матча, возвращает готовые забавные уведомления
    о том, кто кого обошёл на 1/2/3-м месте (пусто, если топ-3 не поменялся)."""
    before_ids = [u.telegram_id for u, _ in before[:3]]
    after_top3 = after[:3]

    users_by_id = {u.telegram_id: u for u, _ in before}
    users_by_id.update({u.telegram_id: u for u, _ in after})

    messages = []
    for idx, (new_user, _) in enumerate(after_top3):
        place = idx + 1
        old_id = before_ids[idx] if idx < len(before_ids) else None
        if old_id == new_user.telegram_id:
            continue

        winner = new_user.mention()
        loser = users_by_id[old_id].mention() if old_id is not None else "пустого места"

        template = random.choice(_PLACE_PHRASES[place])
        messages.append(template.format(winner=winner, loser=loser, type=type_label))

    return messages
