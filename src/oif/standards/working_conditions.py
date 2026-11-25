"""Коэффициенты γc1 и γc2 из таблицы 5.4 СП 22.13330.2016.

Описание конструктивной схемы и влажности песка задаётся пользователем.
"""

from dataclasses import dataclass
from decimal import Decimal

SOURCE = "СП 22.13330.2016, табл. 5.4, печ. с. 36"

# Строки таблицы 5.4 в форме, удобной для справочного экрана интерфейса:
# грунт/состояние, γc1, γc2 при L/H≥4, γc2 при L/H≤1,5.
WORKING_CONDITIONS_TABLE = (
    ("Крупнообломочные с песчаным заполнителем и пески, кроме мелких и пылеватых", "1.4", "1.2", "1.4"),
    ("Пески мелкие", "1.3", "1.1", "1.3"),
    ("Пески пылеватые: маловлажные и влажные", "1.25", "1.0", "1.2"),
    ("Пески пылеватые: насыщенные водой", "1.1", "1.0", "1.2"),
    ("Глинистые грунты при IL≤0,25", "1.25", "1.0", "1.1"),
    ("Глинистые грунты при 0,25<IL≤0,5", "1.2", "1.0", "1.1"),
    ("Глинистые грунты при IL>0,5", "1.1", "1.0", "1.0"),
)


class WorkingConditionsError(ValueError):
    pass


@dataclass(frozen=True)
class WorkingConditions:
    gamma_c1: Decimal
    gamma_c2: Decimal
    category: str
    source: str = SOURCE


def select_working_conditions(*, soil_name: str, liquidity_index: Decimal | None,
                              sand_moisture: str | None, rigid_scheme: bool,
                              length_height_ratio: Decimal | None = None,
                              loose_sand: bool = False) -> WorkingConditions:
    if loose_sand:
        if "песок" not in soil_name.lower():
            raise WorkingConditionsError("Признак рыхлого песка несовместим с типом грунта")
        return WorkingConditions(Decimal(1), Decimal(1), "Рыхлый песок, примечание 4")
    name = soil_name.lower()
    if "песок" in name or "пески" in name:
        if "пылеват" in name:
            if sand_moisture not in ("low", "wet", "saturated"):
                raise WorkingConditionsError("Для пылеватого песка укажите степень влажности")
            gamma_c1 = Decimal("1.25") if sand_moisture in ("low", "wet") else Decimal("1.1")
            category = "Песок пылеватый"
            low, high = Decimal("1.0"), Decimal("1.2")
        elif "мелк" in name:
            gamma_c1 = Decimal("1.3")
            category = "Песок мелкий"
            low, high = Decimal("1.1"), Decimal("1.3")
        else:
            gamma_c1 = Decimal("1.4")
            category = "Песок, кроме мелкого и пылеватого"
            low, high = Decimal("1.2"), Decimal("1.4")
    elif any(word in name for word in ("глин", "суглин", "супес")):
        if liquidity_index is None:
            raise WorkingConditionsError("Для глинистого грунта нужен показатель текучести IL")
        if liquidity_index <= Decimal("0.25"):
            gamma_c1, low, high, category = Decimal("1.25"), Decimal("1.0"), Decimal("1.1"), "Глинистый IL≤0,25"
        elif liquidity_index <= Decimal("0.5"):
            gamma_c1, low, high, category = Decimal("1.2"), Decimal("1.0"), Decimal("1.1"), "Глинистый 0,25<IL≤0,5"
        else:
            gamma_c1, low, high, category = Decimal("1.1"), Decimal("1.0"), Decimal("1.0"), "Глинистый IL>0,5"
    else:
        raise WorkingConditionsError("Тип грунта отсутствует в оцифрованной таблице 5.4")
    if not rigid_scheme:
        gamma_c2 = Decimal(1)
    else:
        if length_height_ratio is None or length_height_ratio <= 0:
            raise WorkingConditionsError("Для жёсткой схемы укажите отношение L/H")
        if length_height_ratio <= Decimal("1.5"):
            gamma_c2 = high
        elif length_height_ratio >= 4:
            gamma_c2 = low
        else:
            gamma_c2 = high + (low - high) * (length_height_ratio - Decimal("1.5")) / Decimal("2.5")
    return WorkingConditions(gamma_c1, gamma_c2, category)
