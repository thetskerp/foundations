"""Встроенные строки таблиц 1–2 задания на КР с происхождением и статусом сверки."""

import json
from importlib.resources import files

from .catalog import Catalog

SOIL_SOURCE = "ЗАДАНИЕ на КР.pdf, табл. 1, печ. с. 17–21"
SERVICE_SAND_SOURCE = (
    "служебный грунт для замены верхнего техногенного слоя; характеристики строки №62 "
    "табл. 1 задания на КР; E=40 МПа также использовано на листе «Фундамент 3» "
    "книги ee499aaedd0818d869fc2aca5121f294.xlsx"
)

SOILS = {int(number): data for number, data in json.loads(files("oif").joinpath("data/assignment_soils.json").read_text(encoding="utf-8")).items()}
SOILS[0] = {
    **SOILS[62],
    "name": "Песок",
    "reference_soil_number": 62,
    "service_role": "replacement_for_technogenic_top_layer",
    "usage_note": (
        "Служебный грунт №0. Используется вместо верхнего техногенного слоя; "
        "характеристики приняты по грунту №62 и должны быть заменены пользовательскими, "
        "если в проекте задан другой песок."
    ),
    "verification": "служебная запись; характеристики полностью совпадают со строкой 62 табл. 1",
}
SOIL_SOURCES = {0: SERVICE_SAND_SOURCE}
for _checked in (29, 40, 81):
    SOILS[_checked]["verification"] = "проверено визуально по PDF задания"

_assignment = json.loads(files("oif").joinpath("data/assignment_schemes.json").read_text(encoding="utf-8"))
SCHEMES = {int(number): data for number, data in _assignment["schemes"].items()}
LOADS = _assignment["loads"]
SCHEME_NAMES = {
    1: "Сортировочный цех", 2: "Котельная", 3: "Жилой дом", 4: "Фабричный цех",
    5: "Общежитие", 6: "Жилой дом", 7: "Химический корпус", 8: "Мартеновский цех",
    9: "Механический цех", 10: "База механизации", 11: "8-этажный жилой дом",
    12: "8-этажный жилой дом", 13: "Силосный корпус", 14: "Фабричный цех",
    15: "Механический цех", 16: "Сварочный цех", 17: "Ремонтный цех",
    18: "Монтажный цех", 19: "Экспериментальный цех", 20: "Химический корпус",
    21: "Корпус по изготовлению оборудования", 22: "Промышленный цех",
    23: "Сборочный цех", 24: "Бизнес-центр", 25: "Торговый центр",
}
for _number, _name in SCHEME_NAMES.items():
    SCHEMES[_number]["name"] = _name
    SCHEMES[_number]["figure_asset"] = f"data/schemes/{_number}.png"
    SCHEMES[_number]["figure_verification"] = "заголовок и номер рисунка сверены визуально"
SCHEMES[18].update({"name": "Монтажный цех", "variants": {"even": {"span_l_m": "16", "height_h_m": "1.5"}, "odd": {"span_l_m": "10", "height_h_m": "2.1"}}, "verification": "проверено визуально по PDF задания"})

# N (тс), M (тс·м), T (тс) для схемы 18; отсутствие усилия остаётся None.
LOADS_18 = {
    "even": {
        1: (("185", "-52", "-3"), ("242", "67", "5.3")),
        2: (("107", None, None), ("120", None, None)),
        3: (("235", "63", "2.5"), ("337", "-56", "-3.8")),
        4: (("51", None, None), ("58", None, None)),
        5: (("10", "2", None), ("12", "2.4", None)),
        6: (("30", "58", "2"), ("90", "-40", "-1.2")),
    },
    "odd": {
        1: (("166", "-40", "-2"), ("213", "48", "4.2")),
        2: (("91", None, None), ("110", None, None)),
        3: (("257", "44", "1.5"), ("304", None, None)),
        4: (("40", None, None), ("44", None, None)),
        5: (("8", None, None), ("11", None, None)),
        6: (("80", "46", None), ("80", "-30", None)),
    },
}

for _variant, _foundations in LOADS_18.items():
    for _foundation, _combinations in _foundations.items():
        for _combination, _values in enumerate(_combinations, 1):
            _key = f"18:{_variant}:{_foundation}:{_combination}"
            _extracted = LOADS[_key]
            if tuple(_extracted[field]["value"] if _extracted[field] else None for field in ("N", "M", "T")) != _values:
                raise ValueError(f"Извлечение нагрузок схемы 18 не совпало с ручной сверкой: {_key}")
            _extracted["verification"] = "проверено визуально по PDF задания"


def install_pilot_catalog(catalog: Catalog) -> None:
    def install(kind: str, key: str, data: dict, source: str) -> None:
        existing = catalog.get(kind, key)
        if existing is None:
            catalog.put(kind, key, 1, data, source, builtin=True)
        elif existing["builtin"] and (existing["data"] != data or existing["source"] != source):
            catalog.refresh_builtin(kind, key, existing["version"], data, source)

    for number, data in SOILS.items():
        install("soil", str(number), data, SOIL_SOURCES.get(number, SOIL_SOURCE))
    for number, scheme in SCHEMES.items():
        source = f"ЗАДАНИЕ на КР.pdf, табл. 2, схема {number}, рис. {number+25}"
        install("scheme", str(number), scheme, source)
    for key, load in LOADS.items():
        number = load["scheme"]
        install("load", key, load, f"ЗАДАНИЕ на КР.pdf, табл. 2, схема {number}, рис. {number+25}")
