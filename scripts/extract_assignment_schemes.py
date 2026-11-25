"""Однократная оцифровка табл. 2 задания из извлечённого текста PDF."""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path


VALUE = re.compile(r"[+-]?\d+(?:[,.]\d+)?|-|±\d+(?:[,.]\d+)?")


def _quantity(token: str, unit: str) -> dict | None:
    if token == "-":
        return None
    return {"value": token.replace(",", "."), "unit": unit}


def extract(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    start = source.index("Таблица 2")
    end = source.index("Окончание таблицы 2", start)
    table = source[start:end + 10000]
    marks = list(re.finditer(r"(?<![А-Яа-я])(Четный|Нечетный)", table))
    if len(marks) != 50:
        raise ValueError(f"Ожидалось 50 групп вариантов, найдено {len(marks)}")
    schemes = {}
    loads = {}
    for group_index, marker in enumerate(marks):
        number = group_index // 2 + 1
        variant = "even" if group_index % 2 == 0 else "odd"
        if (marker.group(1) == "Четный") != (variant == "even"):
            raise ValueError(f"Нарушено чередование вариантов у схемы {number}")
        until = marks[group_index + 1].start() if group_index + 1 < len(marks) else len(table)
        lines = table[marker.start():until].splitlines()
        rows = []
        for line in lines:
            tokens = line.split()
            if len(tokens) < 7 or not tokens[-7].isdigit() or not 1 <= int(tokens[-7]) <= 6:
                continue
            if not all(VALUE.fullmatch(token) for token in tokens[-6:]):
                continue
            foundation = int(tokens[-7])
            values = tokens[-6:]
            if values[0] == "-" or values[3] == "-":
                raise ValueError(f"Нет N у схемы {number}, варианта {variant}, фундамента {foundation}")
            rows.append((foundation, values))
        foundations = [item[0] for item in rows]
        if foundations != list(range(1, len(rows) + 1)):
            raise ValueError(f"Неполная последовательность фундаментов у схемы {number}, {variant}: {foundations}")
        if variant == "even":
            schemes[str(number)] = {"number": number, "name": f"Схема {number} задания на КР", "variants": {"even": {}, "odd": {}}, "foundation_numbers": foundations, "figure": str(number + 25), "verification": "извлечено из цифрового текста табл. 2; не сверено визуально"}
        elif schemes[str(number)]["foundation_numbers"] != foundations:
            raise ValueError(f"Чётный и нечётный варианты схемы {number} имеют разные номера фундаментов")
        for foundation, values in rows:
            for combination, (n, m, t) in enumerate((values[:3], values[3:]), 1):
                key = f"{number}:{variant}:{foundation}:{combination}"
                ratio = Decimal(values[3].replace(",", ".")) / Decimal(values[0].replace(",", "."))
                warnings = []
                if ratio > 5 or ratio < Decimal("0.2"):
                    warnings.append("Сильное различие N между сочетаниями; значение сохранено как в задании")
                if "±" in m or "±" in t:
                    warnings.append("В задании M или T указан со знаком ±; направление выбирается при расчёте")
                loads[key] = {"scheme": number, "variant": variant, "foundation": foundation, "combination": combination,
                    "N": _quantity(n, "tf"), "M": _quantity(m, "tf*m"), "T": _quantity(t, "tf"),
                    "verification": "извлечено из цифрового текста табл. 2; не сверено визуально",
                    "warnings": warnings}
    if len(schemes) != 25 or len(loads) != 516:
        raise ValueError(f"Неожиданный объём: {len(schemes)} схем, {len(loads)} сочетаний")
    return {"schemes": schemes, "loads": loads}


def main():
    data = extract(Path(sys.argv[1]))
    target = Path("src/oif/data/assignment_schemes.json")
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Схем: {len(data['schemes'])}; сочетаний: {len(data['loads'])}; сохранено: {target}")


if __name__ == "__main__":
    main()
