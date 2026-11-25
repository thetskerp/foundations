"""Учебная обработка физико-механических характеристик грунта.

Формулы и коэффициенты β взяты из «ЗАДАНИЕ на КР», печ. с. 54.
Расчёт возвращает пропуск, а не ноль, если показатель к данному грунту
неприменим или не может быть определён.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .units import UnitConversions


SOURCE = "ЗАДАНИЕ на КР.pdf, печ. с. 54"
BETA_BY_SOIL = {
    "Глина": Decimal("0.43"),
    "Суглинок": Decimal("0.57"),
    "Супесь": Decimal("0.72"),
}


class SoilPropertiesError(ValueError):
    pass


def _number(value) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise SoilPropertiesError(f"Некорректное число: {value}") from exc


@dataclass(frozen=True)
class DerivedSoilProperties:
    dry_density_g_cm3: Decimal
    void_ratio: Decimal
    saturation: Decimal
    plasticity_index: Decimal | None
    liquidity_index: Decimal | None
    beta: Decimal
    relative_compressibility_1_kpa: Decimal
    unit_weight_kn_m3: Decimal
    particle_unit_weight_kn_m3: Decimal
    dry_unit_weight_kn_m3: Decimal
    submerged_unit_weight_kn_m3: Decimal
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        def text(value: Decimal | None):
            return None if value is None else str(value)

        return {
            "rho_d_g_cm3": text(self.dry_density_g_cm3),
            "e": text(self.void_ratio),
            "sr": text(self.saturation),
            "ip": text(self.plasticity_index),
            "il": text(self.liquidity_index),
            "beta": text(self.beta),
            "mv_1_kpa": text(self.relative_compressibility_1_kpa),
            "gamma_kn_m3": text(self.unit_weight_kn_m3),
            "gamma_s_kn_m3": text(self.particle_unit_weight_kn_m3),
            "gamma_d_kn_m3": text(self.dry_unit_weight_kn_m3),
            "gamma_sb_kn_m3": text(self.submerged_unit_weight_kn_m3),
            "warnings": list(self.warnings),
            "source": SOURCE,
        }


def beta_for_soil(name: str) -> Decimal:
    if name.startswith("Песок"):
        return Decimal("0.76")
    try:
        return BETA_BY_SOIL[name]
    except KeyError as exc:
        raise SoilPropertiesError(f"Для грунта «{name}» в задании не задан коэффициент β") from exc


def calculate_soil_properties(soil: dict, conversions: UnitConversions | None = None) -> DerivedSoilProperties:
    """Вычислить все производные колонки листа «Грунты» для одной записи."""
    conversions = conversions or UnitConversions()
    rho = _number(soil.get("rho_ii_g_cm3"))
    rho_s = _number(soil.get("rho_s_g_cm3"))
    water = _number(soil.get("w"))
    modulus = _number(soil.get("e_mpa"))
    if rho is None or rho_s is None or water is None or modulus is None:
        raise SoilPropertiesError("Нужны ρII, ρs, W и E")
    if rho <= 0 or rho_s <= 0 or water < 0 or modulus <= 0:
        raise SoilPropertiesError("ρII, ρs и E должны быть положительны, W — неотрицательной")

    rho_d = rho / (Decimal(1) + water)
    void_ratio = (rho_s - rho_d) / rho_d
    if void_ratio <= 0:
        raise SoilPropertiesError("Коэффициент пористости должен быть положительным")
    saturation = water * rho_s / void_ratio

    wl = _number(soil.get("wl"))
    wp = _number(soil.get("wp"))
    ip = il = None
    if wl is not None or wp is not None:
        if wl is None or wp is None or wl <= wp:
            raise SoilPropertiesError("Для пластичного грунта нужны WL>WP")
        ip = wl - wp
        il = (water - wp) / ip

    beta = beta_for_soil(soil["name"])
    warnings: list[str] = []
    if saturation > 1:
        warnings.append("Sr>1; проверьте исходные ρII, ρs и W")
    if soil["name"] in BETA_BY_SOIL and il is None:
        warnings.append("Для глинистого грунта не определён IL")

    density_gravity_factor = conversions.g_cm3_to_kg_m3 * conversions.gravity_m_s2 / Decimal(1000)
    return DerivedSoilProperties(
        dry_density_g_cm3=rho_d,
        void_ratio=void_ratio,
        saturation=saturation,
        plasticity_index=ip,
        liquidity_index=il,
        beta=beta,
        relative_compressibility_1_kpa=beta / (modulus * Decimal(1000)),
        unit_weight_kn_m3=rho * density_gravity_factor,
        particle_unit_weight_kn_m3=rho_s * density_gravity_factor,
        dry_unit_weight_kn_m3=rho_d * density_gravity_factor,
        submerged_unit_weight_kn_m3=(rho_s - Decimal(1)) * density_gravity_factor / (Decimal(1) + void_ratio),
        warnings=tuple(warnings),
    )
