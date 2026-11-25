"""Проверенное ядро формулы (5.7) и давления из СП 22.13330.2016."""

from dataclasses import dataclass
from decimal import Decimal

from ..domain import FoundationKind
from ..units import Quantity

SOURCE_M = "СП 22.13330.2016, табл. 5.5, печ. с. 36–37"
SOURCE_R = "СП 22.13330.2016, п. 5.6.7, формула (5.7), печ. с. 34–35"
SOURCE_PRESSURE = "СП 22.13330.2016, п. 5.6.26–5.6.29, формулы (5.11)–(5.15), печ. с. 40–43"

# φII, Mγ, Mq, Mc; построчно сверено по таблице 5.5 приложенной редакции.
_M_ROWS = """
0 0 1.00 3.14
1 0.01 1.06 3.23
2 0.03 1.12 3.32
3 0.04 1.18 3.41
4 0.06 1.25 3.51
5 0.08 1.32 3.61
6 0.10 1.39 3.71
7 0.12 1.47 3.82
8 0.14 1.55 3.93
9 0.16 1.64 4.05
10 0.18 1.73 4.17
11 0.21 1.83 4.29
12 0.23 1.94 4.42
13 0.26 2.05 4.55
14 0.29 2.17 4.69
15 0.32 2.30 4.84
16 0.36 2.43 4.99
17 0.39 2.57 5.15
18 0.43 2.73 5.31
19 0.47 2.89 5.48
20 0.51 3.06 5.66
21 0.56 3.24 5.84
22 0.61 3.44 6.04
23 0.66 3.65 6.24
24 0.72 3.87 6.45
25 0.78 4.11 6.67
26 0.84 4.37 6.90
27 0.91 4.64 7.14
28 0.98 4.93 7.40
29 1.06 5.25 7.67
30 1.15 5.59 7.95
31 1.24 5.95 8.24
32 1.34 6.34 8.55
33 1.44 6.76 8.88
34 1.55 7.22 9.22
35 1.68 7.71 9.58
36 1.81 8.24 9.97
37 1.95 8.81 10.37
38 2.11 9.44 10.80
39 2.28 10.11 11.25
40 2.46 10.85 11.73
41 2.66 11.64 12.24
42 2.88 12.51 12.79
43 3.12 13.46 13.37
44 3.38 14.50 13.98
45 3.66 15.64 14.64
"""
M_TABLE = {int(fields[0]): tuple(Decimal(x) for x in fields[1:]) for line in _M_ROWS.strip().splitlines() if (fields := line.split())}


class ResistanceInputError(ValueError):
    pass


def basement_reduced_depth(*, base_depth: Quantity, floor_depth: Quantity,
                           soil_height: Quantity, floor_thickness: Quantity,
                           floor_unit_weight: Quantity, gamma_above: Quantity) -> tuple[Quantity, Quantity]:
    """d1 по (5.8) и db по п. 5.6.7; вводимые длины проверяются геометрически."""
    d = base_depth.to("m").value
    floor = floor_depth.to("m").value
    hs = soil_height.to("m").value
    hcf = floor_thickness.to("m").value
    gamma_floor = floor_unit_weight.to("kN/m3").value
    gamma_soil = gamma_above.to("kN/m3").value
    if floor <= 0 or floor >= d or hs < 0 or hcf < 0 or gamma_floor <= 0 or gamma_soil <= 0:
        raise ResistanceInputError("Некорректная геометрия или удельный вес подвала")
    if abs(hs + hcf + floor - d) > Decimal("0.001"):
        raise ResistanceInputError("Для подвала должно выполняться d = db,факт + hs + hcf")
    return Quantity(hs + hcf * gamma_floor / gamma_soil, "m"), Quantity(min(floor, Decimal(2)), "m")


def m_coefficients(phi_ii: Quantity) -> tuple[Decimal, Decimal, Decimal]:
    phi = phi_ii.to("deg").value
    if phi != phi.to_integral_value() or int(phi) not in M_TABLE:
        raise ResistanceInputError("φII должен совпадать с узлом таблицы 5.5 (0…45°); интерполяция не утверждена")
    return M_TABLE[int(phi)]


@dataclass(frozen=True)
class ResistanceInputs:
    phi_ii: Quantity
    cohesion_ii: Quantity
    width: Quantity
    gamma_below: Quantity
    gamma_above: Quantity
    d1: Quantity
    basement_depth: Quantity
    gamma_c1: Decimal
    gamma_c2: Decimal
    k: Decimal
    kz: Decimal = Decimal(1)


def resistance(inputs: ResistanceInputs) -> Quantity:
    m_gamma, m_q, m_c = m_coefficients(inputs.phi_ii)
    if min(inputs.gamma_c1, inputs.gamma_c2, inputs.k, inputs.kz) <= 0:
        raise ResistanceInputError("Коэффициенты должны быть положительными")
    b = inputs.width.to("m").value
    d1 = inputs.d1.to("m").value
    db = inputs.basement_depth.to("m").value
    if b <= 0 or d1 < 0 or db < 0:
        raise ResistanceInputError("Некорректная геометрия")
    gamma_below = inputs.gamma_below.to("kN/m3").value
    gamma_above = inputs.gamma_above.to("kN/m3").value
    cohesion = inputs.cohesion_ii.to("kPa").value
    if gamma_below <= 0 or gamma_above <= 0 or cohesion < 0:
        raise ResistanceInputError("Удельный вес должен быть положительным, сцепление неотрицательным")
    kz = Decimal(1) if b < 10 else Decimal(8) / b + Decimal("0.2")
    if inputs.kz != Decimal(1) and inputs.kz != kz:
        raise ResistanceInputError("kz определяется шириной по п. 5.6.7; переданное значение не совпадает")
    result = (inputs.gamma_c1 * inputs.gamma_c2 / inputs.k) * (
        m_gamma * kz * b * gamma_below
        + m_q * d1 * gamma_above
        + (m_q - 1) * db * gamma_above
        + m_c * cohesion
    )
    return Quantity(result, "kPa")


@dataclass(frozen=True)
class PressureResult:
    mean: Quantity
    eccentricity: Quantity
    edge_min: Quantity | None
    edge_max: Quantity | None
    uplift: bool
    edge_limit_ok: bool | None
    kern_dimension: Quantity
    kern_limit: Quantity


def base_pressure(vertical: Quantity, moment_at_base: Quantity, width: Quantity, length_along_moment: Quantity,
                  depth: Quantity, mean_unit_weight: Quantity, r: Quantity | None = None,
                  *, kind: FoundationKind = FoundationKind.PAD) -> PressureResult:
    n = vertical.to("kN").value
    m = abs(moment_at_base.to("kN*m").value)
    b = width.to("m").value
    l = length_along_moment.to("m").value
    d = depth.to("m").value
    gamma = mean_unit_weight.to("kN/m3").value
    if n <= 0 or b <= 0 or l <= 0 or d < 0 or gamma <= 0:
        raise ResistanceInputError("Некорректные нагрузка или геометрия")
    if kind == FoundationKind.STRIP and l != Decimal(1):
        raise ResistanceInputError("Для ленточного фундамента расчётная длина должна быть 1 м")
    total = n + gamma * d * b * l
    area = b * l
    mean = total / area
    eccentricity = m / total
    # Для отдельного фундамента момент действует вдоль l: W=b·l²/6.
    # Лента рассматривается на участке 1 м, момент — поперёк ленты: W=l·b²/6.
    axis = b if kind == FoundationKind.STRIP else l
    transverse = l if kind == FoundationKind.STRIP else b
    kern = axis / Decimal(6)
    if eccentricity > kern:
        return PressureResult(Quantity(mean, "kPa"), Quantity(eccentricity, "m"), None, None, True, None,
            Quantity(axis, "m"), Quantity(kern, "m"))
    modulus = transverse * axis * axis / 6
    edge_min = Quantity(mean - m / modulus, "kPa")
    edge_max = Quantity(mean + m / modulus, "kPa")
    edge_ok = None if r is None else edge_max.value <= Decimal("1.2") * r.to("kPa").value
    return PressureResult(Quantity(mean, "kPa"), Quantity(eccentricity, "m"), edge_min, edge_max, False, edge_ok,
        Quantity(axis, "m"), Quantity(kern, "m"))
