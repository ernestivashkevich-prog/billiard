"""
Юнит-тесты модуля расчёта рейтинга (Glicko-2).

Покрывают приёмочные сценарии из раздела 11 ТЗ, которые относятся
к чистой логике рейтинга (не требуют БД/телеграма):
1. Два новых игрока 1500/1500 -> симметричное расхождение, RD уменьшается.
2. Фаворит побеждает аутсайдера -> изменение рейтинга минимально у обоих.
3. Аутсайдер побеждает фаворита (апсет) -> изменение рейтинга заметно больше.
6. Игрок, долго не игравший, получает больший скачок рейтинга/RD.
7. Консервативная оценка rating - 2*RD используется для сортировки /top.
"""
from __future__ import annotations

import pytest

from rating.glicko2 import (
    DEFAULT_RATING,
    DEFAULT_RD,
    PlayerRating,
    apply_rd_time_decay,
    conservative_rating,
    update_match,
)


def test_two_new_players_symmetric_update():
    p1 = PlayerRating()
    p2 = PlayerRating()

    new_p1, new_p2 = update_match(p1, p2, 2, 0)

    # Победитель прибавляет, проигравший теряет, симметрично относительно 1500
    assert new_p1.rating > DEFAULT_RATING
    assert new_p2.rating < DEFAULT_RATING
    assert new_p1.rating - DEFAULT_RATING == pytest.approx(DEFAULT_RATING - new_p2.rating, abs=1e-6)

    # RD у обоих должен уменьшиться после сыгранной партии
    assert new_p1.rd < DEFAULT_RD
    assert new_p2.rd < DEFAULT_RD


def test_favorite_beats_underdog_small_change():
    favorite = PlayerRating(rating=1900, rd=60, sigma=0.06)
    underdog = PlayerRating(rating=1300, rd=60, sigma=0.06)

    new_favorite, new_underdog = update_match(favorite, underdog, 2, 0)

    favorite_delta = new_favorite.rating - favorite.rating
    underdog_delta = underdog.rating - new_underdog.rating

    # Ожидаемый исход -> небольшое изменение рейтинга у обоих
    assert 0 < favorite_delta < 10
    assert 0 < underdog_delta < 10


def test_underdog_beats_favorite_big_change():
    favorite = PlayerRating(rating=1900, rd=60, sigma=0.06)
    underdog = PlayerRating(rating=1300, rd=60, sigma=0.06)

    # Апсет: аутсайдер (player1) побеждает фаворита (player2)
    new_underdog, new_favorite = update_match(underdog, favorite, 2, 0)

    underdog_gain = new_underdog.rating - underdog.rating
    favorite_loss = favorite.rating - new_favorite.rating

    assert underdog_gain > 15
    assert favorite_loss > 15


def test_upset_change_bigger_than_expected_outcome():
    favorite = PlayerRating(rating=1900, rd=60, sigma=0.06)
    underdog = PlayerRating(rating=1300, rd=60, sigma=0.06)

    _, expected_underdog_after = update_match(favorite, underdog, 2, 0)
    upset_underdog_after, _ = update_match(underdog, favorite, 2, 0)

    expected_underdog_change = abs(expected_underdog_after.rating - underdog.rating)
    upset_underdog_change = abs(upset_underdog_after.rating - underdog.rating)

    assert upset_underdog_change > expected_underdog_change


def test_rd_grows_with_inactivity():
    player = PlayerRating(rating=1600, rd=60, sigma=0.06)

    decayed_short = apply_rd_time_decay(player, days_since_last_match=1)
    decayed_long = apply_rd_time_decay(player, days_since_last_match=45)

    assert decayed_long.rd > decayed_short.rd > player.rd


def test_inactive_player_gets_bigger_rating_jump():
    opponent = PlayerRating(rating=1500, rd=60, sigma=0.06)

    regular_player = PlayerRating(rating=1500, rd=60, sigma=0.06)
    inactive_player = PlayerRating(rating=1500, rd=60, sigma=0.06)

    new_regular, _ = update_match(
        regular_player, opponent, 2, 0, days_since_p1_last_match=1
    )
    new_inactive, _ = update_match(
        inactive_player, opponent, 2, 0, days_since_p1_last_match=45
    )

    regular_change = abs(new_regular.rating - regular_player.rating)
    inactive_change = abs(new_inactive.rating - inactive_player.rating)

    assert inactive_change > regular_change
    assert new_inactive.rd > new_regular.rd


def test_rd_does_not_grow_beyond_max_for_brand_new_player():
    # У нового игрока (без истории матчей) рост RD не применяется
    player = PlayerRating()
    result = apply_rd_time_decay(player, days_since_last_match=None)
    assert result.rd == player.rd


def test_draw_is_impossible():
    p1 = PlayerRating()
    p2 = PlayerRating()
    with pytest.raises(ValueError):
        update_match(p1, p2, 2, 2)


def test_conservative_rating_formula():
    player = PlayerRating(rating=1550, rd=100)
    assert conservative_rating(player) == pytest.approx(1550 - 200)


def test_conservative_rating_penalizes_high_rd_newcomer():
    # Новичок с одной победой не должен обгонять стабильного игрока
    # с чуть более низким чистым рейтингом, но низким RD.
    newcomer = PlayerRating(rating=1560, rd=300)
    veteran = PlayerRating(rating=1520, rd=50)

    assert conservative_rating(newcomer) < conservative_rating(veteran)
