"""
Реализация рейтинговой системы Glicko-2 по официальной спецификации
Марка Гликмана: "Example of the Glicko-2 system" (2013).

http://www.glicko.net/glicko/glicko2.pdf

Дополнительно (сверх базовой спецификации, по требованию ТЗ) добавлен
учёт роста RD со временем простоя игрока: если с последнего матча
игрока прошло много дней, перед применением результата нового матча
его RD "подрастает" по формуле шага 1 алгоритма (тот же расчёт, что
используется для нескольких периодов бездействия в батчевом Glicko-2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Стартовые значения нового игрока.
# DEFAULT_RATING подобран так, чтобы стартовый Elo (rating - 2*RD, см.
# conservative_rating) был ровно 1000: 1400 - 2*200 = 1000.
DEFAULT_RATING = 1400.0
DEFAULT_RD = 200.0
DEFAULT_SIGMA = 0.06

# Системная константа, ограничивающая волатильность
TAU = 0.5

# Максимально допустимый RD (не даём ему расти бесконечно у "уснувших" игроков).
# Понижен с 350: чем меньше диапазон RD, тем меньше на итоговый рейтинг влияет
# сама степень неопределённости — по запросу снизить "зависимость от RD".
MAX_RD = 200.0

# Верхний предел RD СОПЕРНИКА, который учитывается при расчёте "неожиданности"
# результата (см. update_pair). Без этого потолка победа над непроверенным
# новичком (у которого RD высокий просто потому, что он новичок) выглядит для
# алгоритма куда более "неожиданной", чем победа над таким же по силе, но уже
# проверенным игроком — и опытный игрок получает завышенный прирост Elo просто
# за счёт того, что оппонент новый, а не потому что реально сильнее. Кэп не
# трогает СОБСТВЕННЫЙ RD новичка — его личная калибровка идёт как обычно.
OPPONENT_RD_CAP = 80.0

# Один "рейтинговый период" Glicko-2 = 1 день (см. п.7 ТЗ)
RATING_PERIOD_DAYS = 1.0

# Множитель перевода рейтинга Glicko-1 <-> Glicko-2 шкалы
_Q = 173.7178

_EPSILON = 1e-6


@dataclass(frozen=True)
class PlayerRating:
    """Рейтинг игрока на шкале Glicko-1 (та, что хранится в БД)."""

    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    sigma: float = DEFAULT_SIGMA


def _to_glicko2_scale(rating: float, rd: float) -> tuple[float, float]:
    mu = (rating - DEFAULT_RATING) / _Q
    phi = rd / _Q
    return mu, phi


def _from_glicko2_scale(mu: float, phi: float) -> tuple[float, float]:
    rating = mu * _Q + DEFAULT_RATING
    rd = phi * _Q
    return rating, rd


def apply_rd_time_decay(player: PlayerRating, days_since_last_match: float | None) -> PlayerRating:
    """Шаг 1: увеличение RD за время простоя, ДО применения результата нового матча.

    Если игрок ни разу не играл (days_since_last_match is None) — рост не нужен,
    RD уже равен стартовому значению.
    """
    if not days_since_last_match or days_since_last_match <= 0:
        return player

    mu, phi = _to_glicko2_scale(player.rating, player.rd)
    t_periods = days_since_last_match / RATING_PERIOD_DAYS
    phi_star = math.sqrt(phi * phi + player.sigma * player.sigma * t_periods)

    # не даём RD расти выше максимума (стандартная практика Glicko)
    max_phi = MAX_RD / _Q
    phi_star = min(phi_star, max_phi)

    new_rating, new_rd = _from_glicko2_scale(mu, phi_star)
    return PlayerRating(rating=new_rating, rd=new_rd, sigma=player.sigma)


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi ** 2))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _capped_opponent_phi(phi_j: float) -> float:
    return min(phi_j, OPPONENT_RD_CAP / _Q)


def expected_win_probability(player: PlayerRating, opponent: PlayerRating) -> float:
    """Вероятность победы ``player`` над ``opponent`` по рейтингам до матча (0..1).

    Использует тот же кэп RD соперника, что и реальный пересчёт в update_pair —
    иначе /details объяснял бы матч по формуле, которая не совпадает с тем, что
    на самом деле было применено.
    """
    mu, _ = _to_glicko2_scale(player.rating, player.rd)
    mu_j, phi_j = _to_glicko2_scale(opponent.rating, opponent.rd)
    return _e(mu, mu_j, _capped_opponent_phi(phi_j))


def _new_sigma(phi: float, sigma: float, delta: float, v: float, tau: float = TAU) -> float:
    """Шаг 5: итеративный поиск новой волатильности (алгоритм Иллинойс)."""
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (tau * tau)

    A = a
    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B = a - k * tau

    fA = f(A)
    fB = f(B)

    while abs(B - A) > _EPSILON:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB < 0:
            A, fA = B, fB
        else:
            fA = fA / 2.0
        B, fB = C, fC

    return math.exp(A / 2.0)


def update_pair(
    player: PlayerRating,
    opponent: PlayerRating,
    score: float,
    days_since_player_last_match: float | None = None,
) -> PlayerRating:
    """Пересчитывает рейтинг ``player`` по результату ОДНОЙ партии против ``opponent``.

    ``score`` — 1.0, если ``player`` победил, 0.0 если проиграл (ничьих в бильярде нет).
    Рейтинг ``opponent`` используется "как есть" (без роста RD — это отдельный вызов
    для оппонента с его собственным days_since_last_match).
    """
    player = apply_rd_time_decay(player, days_since_player_last_match)

    mu, phi = _to_glicko2_scale(player.rating, player.rd)
    mu_j, phi_j_raw = _to_glicko2_scale(opponent.rating, opponent.rd)
    phi_j = _capped_opponent_phi(phi_j_raw)

    g_j = _g(phi_j)
    e_val = _e(mu, mu_j, phi_j)

    v = 1.0 / (g_j * g_j * e_val * (1.0 - e_val))
    delta = v * g_j * (score - e_val)

    sigma_prime = _new_sigma(phi, player.sigma, delta, v)

    phi_star = math.sqrt(phi * phi + sigma_prime * sigma_prime)
    phi_prime = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_prime = mu + phi_prime * phi_prime * g_j * (score - e_val)

    new_rating, new_rd = _from_glicko2_scale(mu_prime, phi_prime)
    return PlayerRating(rating=new_rating, rd=new_rd, sigma=sigma_prime)


def update_match(
    player1: PlayerRating,
    player2: PlayerRating,
    score1: int,
    score2: int,
    days_since_p1_last_match: float | None = None,
    days_since_p2_last_match: float | None = None,
) -> tuple[PlayerRating, PlayerRating]:
    """Пересчитывает рейтинги ОБОИХ игроков по результату одной партии.

    ``score1``/``score2`` — счёт партии (например 2:0). Победитель определяется
    по тому, чей счёт больше; ничьих не бывает.
    """
    if score1 == score2:
        raise ValueError("Ничья невозможна в бильярде: score1 не может равняться score2")

    s1 = 1.0 if score1 > score2 else 0.0
    s2 = 1.0 - s1

    new_p1 = update_pair(player1, player2, s1, days_since_p1_last_match)
    new_p2 = update_pair(player2, player1, s2, days_since_p2_last_match)
    return new_p1, new_p2


def conservative_rating(player: PlayerRating) -> float:
    """rating - 2*RD — консервативная оценка силы игрока для сортировки /top."""
    return player.rating - 2.0 * player.rd


def format_signed(value: float) -> str:
    """Изменение рейтинга/Elo со знаком, например "+7" или "-3".

    round(-0.3) даёт -0.0, а f"{-0.0:+.0f}" печатает "-0" — что выглядит как
    баг ("проиграл, а Elo не изменился, но почему-то со знаком минус").
    Явно нормализуем такие случаи в "0" без знака.
    """
    rounded = round(value)
    if rounded == 0:
        return "0"
    return f"{rounded:+d}"
