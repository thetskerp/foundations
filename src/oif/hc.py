"""Определение Hc по выбранному профилю и явному правилу дискретизации."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .domain import FoundationKind, Profile
from .standards.alpha import alpha
from .units import Quantity


class HcError(ValueError):
    pass


class HcSearchMode(StrEnum):
    FIRST_GRID_POINT = "first_grid_point"
    LINEAR_CROSSING = "linear_crossing"


@dataclass(frozen=True)
class StressLayer:
    soil_number: int
    top_m: Decimal
    bottom_m: Decimal
    gamma_above_water: Quantity
    gamma_below_water: Quantity | None = None
    modulus: Quantity | None = None


@dataclass(frozen=True)
class HcPoint:
    z_below_base_m: Decimal
    sigma_zp_kpa: Decimal
    sigma_zg_kpa: Decimal
    ratio: Decimal


@dataclass(frozen=True)
class HcResult:
    depth: Quantity
    threshold: Decimal
    mode: HcSearchMode
    points: tuple[HcPoint, ...]
    source: str


def _stress_at(absolute_depth: Decimal, layers: list[StressLayer], groundwater_m: Decimal | None) -> Decimal:
    if absolute_depth < 0:
        raise HcError("Отрицательная глубина")
    ordered = sorted(layers, key=lambda item: item.top_m)
    current = Decimal(0)
    total = Decimal(0)
    while current < absolute_depth:
        matches = [layer for layer in ordered if layer.top_m <= current < layer.bottom_m]
        if len(matches) != 1:
            raise HcError(f"Нет единственного слоя для σzg на глубине {current} м")
        layer = matches[0]
        next_depth = min(absolute_depth, layer.bottom_m)
        if groundwater_m is not None and current < groundwater_m < next_depth:
            next_depth = groundwater_m
        below_water = groundwater_m is not None and current >= groundwater_m
        gamma = layer.gamma_below_water if below_water else layer.gamma_above_water
        if gamma is None:
            raise HcError(f"Не задан удельный вес ниже УГВ для грунта №{layer.soil_number}")
        total += gamma.to("kN/m3").value * (next_depth - current)
        current = next_depth
    return total


def geostatic_stress(absolute_depth: Quantity, layers: list[StressLayer], groundwater_m: Decimal | None) -> Quantity:
    """Эффективное вертикальное напряжение от веса слоёв, кПа."""
    return Quantity(_stress_at(absolute_depth.to("m").value, layers, groundwater_m), "kPa")


def _minimum_sp_hc(b: Decimal) -> Decimal:
    if b <= 10:
        return b / 2
    if b <= 60:
        return Decimal(4) + Decimal("0.1") * b
    return Decimal(10)


def find_hc(*, profile: Profile, mode: HcSearchMode, kind: FoundationKind, width: Quantity, length: Quantity | None, pressure: Quantity, base_depth: Quantity, layers: list[StressLayer], groundwater_m: Decimal | None, grid_step: Quantity, weak_layer_selected: bool = False) -> HcResult:
    b = width.to("m").value
    base = base_depth.to("m").value
    p = pressure.to("kPa").value
    step = grid_step.to("m").value
    if b <= 0 or base < 0 or p <= 0 or step <= 0 or step > Decimal("0.4") * b:
        raise HcError("Некорректные входы или шаг больше 0,4b")
    if weak_layer_selected and profile == Profile.LECTURE_HC_02:
        raise HcError("Особое правило слабого слоя применяется только к варианту Hc по СП; учебный вариант уже использует 0,2σzg")
    if kind == FoundationKind.PAD:
        if length is None:
            raise HcError("Не задана длина подошвы")
        eta = length.to("m").value / b
        if eta < 1:
            raise HcError("Для таблицы α требуется l≥b")
    else:
        eta = None
    threshold = Decimal("0.2") if profile == Profile.LECTURE_HC_02 else Decimal("0.5")
    source = "Лекция № 5, PDF с. 4" if profile == Profile.LECTURE_HC_02 else "СП 22.13330.2016, п. 5.6.41"
    minimum = _minimum_sp_hc(b) if profile == Profile.SP_HC_05_LECTURE_SETTLEMENT else Decimal(0)
    max_depth = Decimal(6) * b  # ξ=2z/b не выходит за предел 12 таблицы 5.8.
    candidates = {Decimal(0), max_depth}
    z = Decimal(0)
    while z < max_depth:
        z = min(max_depth, z + step)
        candidates.add(z)
    if 0 < minimum < max_depth:
        candidates.add(minimum)
    points: list[HcPoint] = []
    for z in sorted(candidates):
        xi = 2 * z / b
        a = alpha(xi, kind, eta=eta)
        sigma_zp = a * p
        sigma_zg = _stress_at(base + z, layers, groundwater_m)
        ratio = sigma_zp / sigma_zg if sigma_zg > 0 else Decimal("Infinity")
        point = HcPoint(z, sigma_zp, sigma_zg, ratio)
        points.append(point)
        if z >= minimum and sigma_zp <= threshold * sigma_zg:
            if weak_layer_selected and profile != Profile.LECTURE_HC_02 and threshold == Decimal("0.5"):
                absolute_boundary = base + z
                weak = [layer for layer in layers if layer.top_m <= absolute_boundary <= layer.bottom_m
                        and layer.modulus is not None and layer.modulus.to("MPa").value <= 7]
                if not weak:
                    raise HcError("Выбран слабый слой, но у границы Hc нет слоя с E≤7 МПа")
                minimum = max(minimum, max(layer.bottom_m - base for layer in weak))
                threshold = Decimal("0.2")
                source += "; слабый слой E≤7 МПа, продолжение до 0,2σzg"
                continue
            if mode == HcSearchMode.FIRST_GRID_POINT or len(points) == 1:
                depth = z
            else:
                previous = points[-2]
                if previous.z_below_base_m < minimum:
                    depth = minimum
                else:
                    f0 = previous.sigma_zp_kpa - threshold * previous.sigma_zg_kpa
                    f1 = sigma_zp - threshold * sigma_zg
                    depth = previous.z_below_base_m + (z - previous.z_below_base_m) * f0 / (f0 - f1) if f0 != f1 else z
            return HcResult(Quantity(depth, "m"), threshold, mode, tuple(points), source)
    raise HcError("Условие Hc не достигнуто в пределах таблицы α; экстраполяция запрещена")
