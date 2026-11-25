"""Предварительное R0 по таблицам Б.2–Б.3 СП 22.13330.2016.

Неизвестная классификация, в том числе общий тип «Песок», блокирует выбор.
"""

from dataclasses import dataclass
from decimal import Decimal

from ..soil_properties import calculate_soil_properties
from ..units import Quantity

SOURCE = "СП 22.13330.2016, приложение Б, Б.1–Б.3, печ. с. 193–195"


class R0SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class R0Selection:
    value: Quantity
    table: str
    parameters: dict[str, str]
    explanation: str


# (e, R0 при IL=0, R0 при IL=1), кПа. Таблица Б.3.
CLAY_B3 = {
    "Супесь": (("0.5", "300", "200"), ("0.7", "250", "150")),
    "Суглинок": (("0.5", "350", "250"), ("0.7", "250", "180"), ("1.0", "200", "100")),
    "Глина": (("0.5", "600", "400"), ("0.6", "500", "300"), ("0.8", "300", "200"), ("1.1", "250", "100")),
}

# Б.2: {тип: {плотность: {влажность: R0}}}. Только строки, проверенные по скану.
SAND_B2 = {
    "Песок крупный": {"dense": Decimal(600), "medium": Decimal(500)},
    "Песок средней крупности": {"dense": Decimal(500), "medium": Decimal(400)},
    "Песок пылеватый": {
        "dense": {"low": Decimal(300), "wet": Decimal(200), "saturated": Decimal(150)},
        "medium": {"low": Decimal(250), "wet": Decimal(150), "saturated": Decimal(100)},
    },
    "Песок мелкий": {
        "dense": {"low": Decimal(400), "wet": Decimal(300), "saturated": Decimal(300)},
        "medium": {"low": Decimal(300), "wet": Decimal(200), "saturated": Decimal(200)},
    },
}


def _linear(x: Decimal, x0: Decimal, y0: Decimal, x1: Decimal, y1: Decimal) -> Decimal:
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def r0_for_clay(name: str, e: Decimal, liquidity_index: Decimal) -> Quantity:
    if name not in CLAY_B3:
        raise R0SelectionError("Для этого грунта нет проверенной строки таблицы Б.3")
    if not Decimal(0) <= liquidity_index <= Decimal(1):
        raise R0SelectionError("IL вне табличного диапазона 0…1")
    rows = [(Decimal(a), Decimal(b), Decimal(c)) for a, b, c in CLAY_B3[name]]
    if not rows[0][0] <= e <= rows[-1][0]:
        raise R0SelectionError(f"e вне табличного диапазона {rows[0][0]}…{rows[-1][0]}")
    for e0, r00, r01 in rows:
        if e == e0:
            return Quantity(_linear(liquidity_index, Decimal(0), r00, Decimal(1), r01), "kPa")
    for (e0, r00, r01), (e1, r10, r11) in zip(rows, rows[1:]):
        if e0 < e < e1:
            low = _linear(liquidity_index, Decimal(0), r00, Decimal(1), r01)
            high = _linear(liquidity_index, Decimal(0), r10, Decimal(1), r11)
            return Quantity(_linear(e, e0, low, e1, high), "kPa")
    raise AssertionError("Не найден интервал интерполяции")


def r0_from_soil_record(soil: dict, *, sand_density: str | None = None, sand_moisture: str | None = None) -> Quantity:
    return select_r0(soil, sand_density=sand_density, sand_moisture=sand_moisture).value


def select_r0(soil: dict, *, sand_density: str | None = None, sand_moisture: str | None = None) -> R0Selection:
    name = soil["name"]
    if name in CLAY_B3:
        try:
            derived = calculate_soil_properties(soil)
        except ValueError as exc:
            raise R0SelectionError(str(exc)) from exc
        if derived.plasticity_index is None or derived.liquidity_index is None:
            raise R0SelectionError("Для выбора R0 глинистого грунта нужны Ip и IL")
        value = r0_for_clay(name, derived.void_ratio, derived.liquidity_index)
        return R0Selection(
            value=value,
            table="СП 22.13330.2016, таблица Б.3 — глинистые непросадочные грунты",
            parameters={"e": str(derived.void_ratio), "Ip": str(derived.plasticity_index), "IL": str(derived.liquidity_index)},
            explanation="R0 получено двумерной линейной интерполяцией по e и IL",
        )
    if name in SAND_B2:
        if not sand_density:
            raise R0SelectionError("Для песка укажите плотность сложения")
        try:
            selected = SAND_B2[name][sand_density]
            if isinstance(selected, dict):
                if not sand_moisture:
                    raise R0SelectionError("Для мелкого или пылеватого песка укажите состояние по влажности")
                selected = selected[sand_moisture]
            return R0Selection(
                value=Quantity(selected, "kPa"),
                table="СП 22.13330.2016, таблица Б.2 — пески",
                parameters={"density": sand_density, **({"moisture": sand_moisture} if isinstance(SAND_B2[name][sand_density], dict) else {})},
                explanation="R0 выбрано по виду песка, плотности сложения и состоянию по влажности",
            )
        except KeyError as exc:
            raise R0SelectionError("Состояние песка отсутствует в проверенной части таблицы Б.2") from exc
    raise R0SelectionError("Для данного типа грунта R0 ещё не оцифровано")


def preliminary_area(vertical: Quantity, r0: Quantity, depth: Quantity, mean_unit_weight: Quantity) -> Quantity:
    n = vertical.to("kN").value
    gamma = mean_unit_weight.to("kN/m3").value
    d = depth.to("m").value
    if gamma <= 0 or d < 0 or r0.to("kPa").value <= 0:
        raise R0SelectionError("Некорректные исходные данные для предварительного подбора")
    denominator = r0.to("kPa").value - gamma * d
    if n <= 0 or denominator <= 0:
        raise R0SelectionError("Предварительная площадь не определена при этой нагрузке и глубине")
    return Quantity(n / denominator, "m2")
