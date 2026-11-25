"""Подбор площади подошвы с явным шагом 0,1 м² и фиксированной шириной."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from .domain import FoundationKind
from .standards.resistance import PressureResult, base_pressure
from .units import Quantity


class SizingError(ValueError):
    pass


@dataclass(frozen=True)
class SizingResult:
    width: Quantity
    length: Quantity
    area: Quantity
    pressure: PressureResult
    iterations: int
    rule: str


@dataclass(frozen=True)
class PreliminaryGeometry:
    width: Quantity
    length: Quantity
    area: Quantity
    rule: str


def preliminary_geometry(area: Quantity, kind: FoundationKind, *, width: Quantity | None = None,
                         length: Quantity | None = None) -> PreliminaryGeometry:
    """Предложить размеры с округлением вверх до 0,1 м без проверки по R."""
    required = area.to("m2").value
    tenth = Decimal("0.1")

    def ceil_tenth(value: Decimal) -> Decimal:
        return (value / tenth).to_integral_value(rounding=ROUND_CEILING) * tenth

    if required <= 0:
        raise SizingError("Предварительная площадь должна быть положительной")
    b = width.to("m").value if width is not None else None
    l = length.to("m").value if length is not None else None
    if b is not None and b <= 0 or l is not None and l <= 0:
        raise SizingError("Размеры подошвы должны быть положительными")
    if kind == FoundationKind.PAD:
        if b is None and l is not None:
            raise SizingError("Для столбчатого фундамента укажите ширину либо оставьте оба размера пустыми")
        if b is None:
            b = ceil_tenth(required.sqrt())
            l = b
            rule = "Квадратная подошва; стороны округлены вверх до 0,1 м"
        else:
            l = ceil_tenth(max(b, l or Decimal(0), required / b))
            rule = "Ширина сохранена; длина округлена вверх до 0,1 м"
    elif kind == FoundationKind.STRIP:
        l = Decimal(1)
        b = ceil_tenth(max(b or Decimal(0), required))
        rule = "Лента рассчитана на участке l=1 м; ширина b округлена вверх до 0,1 м"
    else:
        raise SizingError("Неизвестный тип фундамента")
    return PreliminaryGeometry(Quantity(b, "m"), Quantity(l, "m"), Quantity(b * l, "m2"), rule)


def auto_size_area(*, vertical: Quantity, moment_at_base: Quantity, width: Quantity,
                   initial_length: Quantity, depth: Quantity, foundation_unit_weight: Quantity,
                   resistance: Quantity, area_step: Quantity = Quantity.of("0.1", "m2"),
                   max_iterations: int = 100_000, kind: FoundationKind = FoundationKind.PAD) -> SizingResult:
    b = width.to("m").value
    initial_l = initial_length.to("m").value
    if kind == FoundationKind.STRIP and initial_l != Decimal(1):
        raise SizingError("Для ленточного фундамента l должна быть равна 1 м")
    start_area = b * initial_l
    step = area_step.to("m2").value
    if b <= 0 or start_area <= 0 or step <= 0:
        raise SizingError("Ширина, начальная площадь и шаг должны быть положительными")
    if max_iterations < 1:
        raise SizingError("Некорректный предел итераций")
    floor_pressure = foundation_unit_weight.to("kN/m3").value * depth.to("m").value
    if resistance.to("kPa").value <= floor_pressure:
        raise SizingError("При фиксированных γ и d увеличение площади не позволит выполнить p≤R")
    area = (start_area / step).to_integral_value(rounding=ROUND_CEILING) * step
    for iteration in range(max_iterations):
        if kind == FoundationKind.STRIP:
            current_width = Quantity(area, "m")
            length = Quantity.of(1, "m")
        else:
            current_width = width
            length = Quantity(area / b, "m")
        pressure = base_pressure(vertical, moment_at_base, current_width, length, depth,
            foundation_unit_weight, resistance, kind=kind)
        if not pressure.uplift and pressure.mean.value <= resistance.to("kPa").value:
            rule = ("Лента: l=1 м; b увеличена с шагом площади 0,1 м²; проверены e≤b/6 и p≤R"
                    if kind == FoundationKind.STRIP else
                    "Ширина постоянна; площадь увеличена с шагом 0,1 м²; проверены e≤l/6 и p≤R")
            return SizingResult(current_width, length, Quantity(area, "m2"), pressure, iteration + 1, rule)
        area += step
    raise SizingError("Подбор не сошёлся в установленном диапазоне площадей")
