"""Однократная оцифровка строк табл. 1 задания из извлечённого текста PDF.

Запуск: python scripts/extract_assignment_soils.py путь/к/тексту.pdf.txt
Результат включает только строки с полным набором 12 полей и известной группой.
"""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path


def _number(value: str) -> str | None:
    if value == "-":
        return None
    normalized = value.replace(",", ".")
    if normalized.startswith("<"):
        return normalized
    Decimal(normalized)
    return normalized


def _name(number: int) -> str | None:
    if 1 <= number <= 20:
        return "Глина"
    if 21 <= number <= 50:
        return "Суглинок"
    if 51 <= number <= 56:
        return "Супесь"
    if 61 <= number <= 66:
        return "Песок"
    if 67 <= number <= 78:
        return "Песок мелкий"
    if 79 <= number <= 85:
        return "Песок пылеватый"
    return None


def extract(path: Path) -> dict[str, dict]:
    source = path.read_text(encoding="utf-8")
    start = source.index("Таблица 1\n")
    end = source.index("Примечания:", start)
    rows = {}
    keys = ("rho_ii_g_cm3", "phi_ii_deg", "c_ii_kpa", "rho_i_g_cm3", "phi_i_deg", "c_i_kpa", "e_mpa", "rho_s_g_cm3", "w", "wl", "wp", "filtration_m_day")
    for line in source[start:end].splitlines():
        match = re.match(r"^\s*(\d{1,3})\s+", line)
        if not match:
            continue
        number = int(match.group(1))
        name = _name(number)
        if name is None:
            continue
        tokens = line.split()
        if len(tokens) < 14:
            continue
        index = tokens[-13]
        try:
            values = [_number(token) for token in tokens[-12:]]
            if values[0] is None or not Decimal(values[0]) > 0:
                continue
        except Exception:
            continue
        data = {"name": name, "geological_index": index, **dict(zip(keys, values)), "verification": "извлечено из цифрового текста табл. 1; контрольные строки 29, 40, 81 сверены визуально"}
        if number in rows:
            raise ValueError(f"Повтор строки {number}")
        rows[number] = data
    expected = {*range(1, 57), *range(61, 86)}
    missing = sorted(expected - set(rows))
    if missing:
        raise ValueError(f"Строки не извлечены: {missing}")
    return {str(number): rows[number] for number in sorted(rows)}


def main():
    source = Path(sys.argv[1])
    rows = extract(source)
    target = Path("src/oif/data/assignment_soils.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Строк: {len(rows)}; сохранено: {target}")


if __name__ == "__main__":
    main()
