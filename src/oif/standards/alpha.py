"""Коэффициент α, СП 22 табл. 5.8, с допустимой интерполяцией."""

import json
from decimal import Decimal
from importlib.resources import files

from ..domain import FoundationKind

SOURCE = "СП 22.13330.2016, таблица 5.8, примечание 3, печ. с. 45–46"


class AlphaSelectionError(ValueError):
    pass


_raw = json.loads(files("oif.standards").joinpath("data/alpha_5_8.json").read_text(encoding="utf-8"))
ROWS = [tuple(Decimal(v) for v in row) for row in _raw["rows"]]
ETA_NODES = (Decimal(1), Decimal("1.4"), Decimal("1.8"), Decimal("2.4"), Decimal("3.2"), Decimal(5), Decimal(10))


def _lerp(x, x0, y0, x1, y1):
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def _alpha_at_row(row: tuple[Decimal, ...], kind: FoundationKind, eta: Decimal | None) -> Decimal:
    if kind == FoundationKind.STRIP:
        return row[8]
    if eta is None or eta < 1:
        raise AlphaSelectionError("Для столбчатого фундамента требуется η=l/b ≥1")
    if eta >= 10:
        return row[8]
    values = row[2:9]
    for index, node in enumerate(ETA_NODES):
        if eta == node:
            return values[index]
    for index, (left, right) in enumerate(zip(ETA_NODES, ETA_NODES[1:])):
        if left < eta < right:
            return _lerp(eta, left, values[index], right, values[index + 1])
    raise AssertionError("Интервал η не найден")


def alpha(xi: Decimal, kind: FoundationKind, *, eta: Decimal | None = None) -> Decimal:
    if xi < ROWS[0][0] or xi > ROWS[-1][0]:
        raise AlphaSelectionError("ξ вне таблицы 5.8 (0…12); экстраполяция запрещена")
    for row in ROWS:
        if xi == row[0]:
            return _alpha_at_row(row, kind, eta)
    for low, high in zip(ROWS, ROWS[1:]):
        if low[0] < xi < high[0]:
            a0 = _alpha_at_row(low, kind, eta)
            a1 = _alpha_at_row(high, kind, eta)
            return _lerp(xi, low[0], a0, high[0], a1)
    raise AssertionError("Интервал ξ не найден")
