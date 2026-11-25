"""Явное преобразование входных единиц в рабочие единицы кН, м, кПа."""

from dataclasses import dataclass
from decimal import Decimal


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class UnitConversions:
    """Коэффициенты хранятся в проекте, чтобы расчёт был воспроизводимым."""

    tf_to_kn: Decimal = Decimal("9.80665")
    gravity_m_s2: Decimal = Decimal("9.80665")
    mm_to_m: Decimal = Decimal("0.001")
    mpa_to_kpa: Decimal = Decimal("1000")
    g_cm3_to_kg_m3: Decimal = Decimal("1000")

    def __post_init__(self) -> None:
        if any(value <= 0 or not value.is_finite() for value in (
            self.tf_to_kn, self.gravity_m_s2, self.mm_to_m,
            self.mpa_to_kpa, self.g_cm3_to_kg_m3,
        )):
            raise UnitError("Коэффициенты перевода должны быть положительными")

    def as_dict(self) -> dict[str, str]:
        return {
            "tf_to_kn": str(self.tf_to_kn),
            "gravity_m_s2": str(self.gravity_m_s2),
            "mm_to_m": str(self.mm_to_m),
            "mpa_to_kpa": str(self.mpa_to_kpa),
            "g_cm3_to_kg_m3": str(self.g_cm3_to_kg_m3),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "UnitConversions":
        defaults = cls()
        data = data or {}
        return cls(**{
            name: Decimal(str(data.get(name, getattr(defaults, name))))
            for name in defaults.as_dict()
        })


_UNITS: dict[str, tuple[str, Decimal]] = {
    "m": ("length", Decimal(1)),
    "mm": ("length", Decimal("0.001")),
    "m2": ("area", Decimal(1)),
    "kN": ("force", Decimal(1)),
    "tf": ("force", Decimal("9.80665")),
    "kN*m": ("moment", Decimal(1)),
    "tf*m": ("moment", Decimal("9.80665")),
    "kPa": ("pressure", Decimal(1)),
    "MPa": ("pressure", Decimal(1000)),
    "tf/m2": ("pressure", Decimal("9.80665")),
    "kN/m3": ("unit_weight", Decimal(1)),
    "tf/m3": ("unit_weight", Decimal("9.80665")),
    "g/cm3": ("density", Decimal(1000)),
    "kg/m3": ("density", Decimal(1)),
    "1": ("dimensionless", Decimal(1)),
    "deg": ("angle", Decimal(1)),
}


def _factor(unit: str, conversions: UnitConversions | None) -> Decimal:
    if conversions is None:
        return _UNITS[unit][1]
    return {
        "mm": conversions.mm_to_m,
        "tf": conversions.tf_to_kn,
        "tf*m": conversions.tf_to_kn,
        "tf/m2": conversions.tf_to_kn,
        "tf/m3": conversions.tf_to_kn,
        "MPa": conversions.mpa_to_kpa,
        "g/cm3": conversions.g_cm3_to_kg_m3,
    }.get(unit, _UNITS[unit][1])


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in _UNITS:
            raise UnitError(f"Неизвестная единица: {self.unit}")
        if not self.value.is_finite():
            raise UnitError("Значение должно быть конечным")

    @classmethod
    def of(cls, value: str | int | float | Decimal, unit: str) -> "Quantity":
        return cls(Decimal(str(value)), unit)

    @property
    def dimension(self) -> str:
        return _UNITS[self.unit][0]

    def to(self, unit: str, conversions: UnitConversions | None = None) -> "Quantity":
        if unit not in _UNITS or _UNITS[unit][0] != self.dimension:
            raise UnitError(f"Несовместимые единицы: {self.unit} → {unit}")
        return Quantity(self.value * _factor(self.unit, conversions) / _factor(unit, conversions), unit)

    def as_dict(self) -> dict[str, str]:
        return {"value": str(self.value), "unit": self.unit}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Quantity":
        return cls.of(data["value"], data["unit"])


def unit_weight_from_density(density: Quantity, gravity: Decimal | None = None,
                             conversions: UnitConversions | None = None) -> Quantity:
    if density.dimension != "density":
        raise UnitError("Для удельного веса нужна плотность")
    gravity = gravity if gravity is not None else (
        conversions.gravity_m_s2 if conversions is not None else Decimal("9.80665")
    )
    # кг/м³ × м/с² / 1000 = кН/м³
    return Quantity(density.to("kg/m3", conversions).value * gravity / 1000, "kN/m3")
