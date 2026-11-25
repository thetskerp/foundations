"""Одночленная формула осадки из лекции № 5 для заданной Hc.

Автоматический поиск Hc находится в отдельном модуле hc.py.
"""

from dataclasses import dataclass
from decimal import Decimal
from collections.abc import Callable

from .domain import FoundationKind
from .standards.alpha import alpha
from .units import Quantity

SOURCE = "Лекция 005 «Расчёт осадок фундаментов энергообъектов», PDF с. 4–6"


class SettlementInputError(ValueError):
    pass


@dataclass(frozen=True)
class SettlementSoilLayer:
    soil_number: int
    top_m: Decimal
    bottom_m: Decimal
    modulus: Quantity


@dataclass(frozen=True)
class ElementaryLayer:
    soil_number: int
    top_m: Decimal
    bottom_m: Decimal
    midpoint_m: Decimal
    xi: Decimal
    alpha_value: Decimal
    sigma_zp: Quantity
    modulus: Quantity
    settlement: Quantity
    z_top_m: Decimal
    z_bottom_m: Decimal
    xi_top: Decimal
    xi_bottom: Decimal
    alpha_top: Decimal
    alpha_bottom: Decimal
    sigma_zp_top: Quantity
    sigma_zp_bottom: Quantity
    sigma_zg_top: Quantity | None
    sigma_zg_bottom: Quantity | None
    sigma_zy_top: Quantity | None
    sigma_zy_bottom: Quantity | None
    sigma_zy_average: Quantity | None
    stress_difference: Quantity | None


@dataclass(frozen=True)
class SettlementResult:
    total: Quantity
    layers: tuple[ElementaryLayer, ...]
    source: str = SOURCE


def calculate_settlement(*, kind: FoundationKind, width: Quantity, length: Quantity | None, pressure: Quantity, base_depth: Quantity, h_c: Quantity, soils: list[SettlementSoilLayer], groundwater_m: Decimal | None = None, step_fraction: Decimal = Decimal("0.4"), geostatic_stress_at: Callable[[Quantity], Quantity] | None = None) -> SettlementResult:
    b = width.to("m").value
    base = base_depth.to("m").value
    hc = h_c.to("m").value
    p = pressure.to("kPa").value
    if b <= 0 or base < 0 or hc <= 0 or p <= 0 or step_fraction <= 0 or step_fraction > Decimal("0.4"):
        raise SettlementInputError("Некорректные размеры, давление или шаг слоёв")
    if kind == FoundationKind.PAD:
        if length is None:
            raise SettlementInputError("Для столбчатого фундамента требуется длина")
        l = length.to("m").value
        if l < b:
            raise SettlementInputError("Для таблицы α требуется l≥b")
        eta = l / b
    else:
        eta = None
    if 2 * hc / b > 12:
        raise SettlementInputError("Нижняя граница вне таблицы α: ξ>12")
    ordered = sorted(soils, key=lambda item: item.top_m)
    current = base
    end = base + hc
    generated = []
    max_step = step_fraction * b
    while current < end:
        matches = [layer for layer in ordered if layer.top_m <= current < layer.bottom_m]
        if len(matches) != 1:
            raise SettlementInputError(f"Нет единственного ИГЭ на глубине {current} м")
        layer = matches[0]
        modulus = layer.modulus.to("kPa").value
        if modulus <= 0:
            raise SettlementInputError("Модуль деформации должен быть положительным")
        next_boundary = min(end, layer.bottom_m, current + max_step)
        if groundwater_m is not None and current < groundwater_m < next_boundary:
            next_boundary = groundwater_m
        if next_boundary <= current:
            raise SettlementInputError("Нулевой элементарный слой")
        midpoint = (current + next_boundary) / 2
        z = midpoint - base
        xi = 2 * z / b
        xi_top = 2 * (current - base) / b
        xi_bottom = 2 * (next_boundary - base) / b
        alpha_top = alpha(xi_top, kind, eta=eta)
        alpha_bottom = alpha(xi_bottom, kind, eta=eta)
        # Лекция № 5 задаёт среднее дополнительное напряжение
        # по значениям на кровле и подошве элементарного слоя.
        a = (alpha_top + alpha_bottom) / 2
        sigma_top = alpha_top * p
        sigma_bottom = alpha_bottom * p
        sigma = (sigma_top + sigma_bottom) / 2
        sigma_zg_top = sigma_zg_bottom = None
        sigma_zy_top = sigma_zy_bottom = sigma_zy_average = difference = None
        if geostatic_stress_at is not None:
            sigma_zg_top = geostatic_stress_at(Quantity(current, "m")).to("kPa")
            sigma_zg_bottom = geostatic_stress_at(Quantity(next_boundary, "m")).to("kPa")
            sigma_zy_top = Quantity(alpha_top * sigma_zg_top.value, "kPa")
            sigma_zy_bottom = Quantity(alpha_bottom * sigma_zg_bottom.value, "kPa")
            sigma_zy_average = Quantity((sigma_zy_top.value + sigma_zy_bottom.value) / 2, "kPa")
            difference = Quantity(sigma - sigma_zy_average.value, "kPa")
        delta_s = Decimal("0.8") * sigma * (next_boundary - current) / modulus
        generated.append(ElementaryLayer(
            layer.soil_number, current, next_boundary, midpoint, xi, a,
            Quantity(sigma, "kPa"), Quantity(modulus, "kPa"), Quantity(delta_s, "m"),
            current - base, next_boundary - base, xi_top, xi_bottom, alpha_top, alpha_bottom,
            Quantity(sigma_top, "kPa"), Quantity(sigma_bottom, "kPa"),
            sigma_zg_top, sigma_zg_bottom, sigma_zy_top, sigma_zy_bottom,
            sigma_zy_average, difference,
        ))
        current = next_boundary
    return SettlementResult(Quantity(sum((entry.settlement.value for entry in generated), Decimal(0)), "m"), tuple(generated))
