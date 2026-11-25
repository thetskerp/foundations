"""Инженерно оформленная Excel-книга из снимка расчётного ядра.

Модуль отвечает только за представление данных. Расчётные величины берутся из
сохранённого снимка и здесь не пересчитываются.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break

from ..domain import Project
from .common import ReportError, included_sections, require_snapshot


NAVY = "1F4E78"
BLUE = "5B9BD5"
SECTION = "D9EAF7"
PALE = "F4F8FB"
LINE = "A9B8C6"
TEXT = "1F2937"
MUTED = "5B6573"
GOOD = "E2F0D9"
WARN = "FFF2CC"
WHITE = "FFFFFF"

THIN = Side(style="thin", color=LINE)
TABLE_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _number(value):
    """Вернуть число Excel либо длинное/нечисловое значение без изменений."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return str(value)


def _quantity(value: dict | None):
    return "—" if value is None else _number(value.get("value"))


def _modulus_mpa(value: dict | None):
    """Вывести модуль деформации в МПа, как в расчётной таблице пользователя."""
    if not value:
        return "—"
    number = Decimal(str(value.get("value")))
    unit = value.get("unit")
    if unit == "kPa":
        number /= Decimal(1000)
    elif unit != "MPa":
        return f"{number} {unit or ''}".strip()
    return float(number)


def _unit(value: dict | None) -> str:
    return "—" if not value else value.get("unit", "—")


def _quantity_text(value: dict | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{float(value['value']):.{places}f} {value['unit']}"


def _text(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, dict):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    return str(value)


def _new_sheet(book: Workbook, name: str, title: str, subtitle: str, last_column: int):
    sheet = book.create_sheet(name)
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "B5"
    sheet.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_column)
    cell = sheet.cell(2, 2, title)
    cell.font = Font(name="Arial", size=16, bold=True, color=TEXT)
    cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[2].height = 25
    sheet.merge_cells(start_row=3, start_column=2, end_row=3, end_column=last_column)
    cell = sheet.cell(3, 2, subtitle)
    cell.font = Font(name="Arial", size=9, italic=True, color=MUTED)
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.row_dimensions[3].height = 28
    for column in range(2, last_column + 1):
        sheet.cell(4, column).fill = PatternFill("solid", fgColor=NAVY)
    sheet.row_dimensions[4].height = 4
    return sheet


def _section(sheet, row: int, title: str, start_column: int, end_column: int) -> int:
    sheet.merge_cells(start_row=row, start_column=start_column, end_row=row, end_column=end_column)
    cell = sheet.cell(row, start_column, title)
    cell.font = Font(name="Arial", size=10, bold=True, color=NAVY)
    cell.alignment = Alignment(vertical="center")
    for column in range(start_column, end_column + 1):
        current = sheet.cell(row, column)
        current.fill = PatternFill("solid", fgColor=SECTION)
        current.border = Border(bottom=Side(style="medium", color=BLUE))
    sheet.row_dimensions[row].height = 22
    return row + 1


def _header(sheet, row: int, headings: tuple[str, ...], start_column: int = 2) -> int:
    for offset, heading in enumerate(headings):
        cell = sheet.cell(row, start_column + offset, heading)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Arial", size=9, bold=True, color=WHITE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = TABLE_BORDER
    sheet.row_dimensions[row].height = 26
    return row + 1


def _row(sheet, row: int, values: tuple, start_column: int = 2, *, fill: str | None = None,
         bold: bool = False, height: float | None = None) -> int:
    for offset, value in enumerate(values):
        cell = sheet.cell(row, start_column + offset, value)
        cell.font = Font(name="Arial", size=9, bold=bold, color=TEXT)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        cell.border = TABLE_BORDER
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        if isinstance(value, float):
            cell.number_format = "0.######"
    if height:
        sheet.row_dimensions[row].height = height
    return row + 1


def _label_value(sheet, row: int, label: str, value, label_column: int = 2,
                 value_column: int = 3, *, fill: str | None = None) -> int:
    label_cell = sheet.cell(row, label_column, label)
    value_cell = sheet.cell(row, value_column, value)
    for cell in (label_cell, value_cell):
        cell.font = Font(name="Arial", size=9, color=TEXT)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        cell.border = TABLE_BORDER
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
    label_cell.font = Font(name="Arial", size=9, bold=True, color=TEXT)
    if isinstance(value, float):
        value_cell.number_format = "0.######"
    return row + 1


def _finish(sheet, last_column: int, *, orientation: str = "portrait") -> None:
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.orientation = orientation
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins = PageMargins(left=0.35, right=0.35, top=0.55, bottom=0.55,
                                     header=0.2, footer=0.2)
    sheet.print_title_rows = "1:4"
    sheet.print_area = f"B2:{sheet.cell(sheet.max_row, last_column).coordinate}"
    sheet.oddFooter.center.text = "Страница &P из &N"
    sheet.oddFooter.center.size = 8
    sheet.oddFooter.center.color = MUTED


def _foundation(project: Project, result: dict):
    return next((item for item in project.foundations if item.number == result["foundation_number"]), None)


def _load(project: Project, result: dict) -> dict | None:
    return project.catalog_snapshot.get("loads", {}).get(result["load_key"])


def _result_sheet(book: Workbook, project: Project, result: dict, sections: tuple[str, ...]) -> None:
    sheet = _new_sheet(
        book, "01 Результат", "Результат расчёта",
        f"{project.name} · фундамент №{result['foundation_number']} · сочетание {result['combination']}", 6,
    )
    for column, width in {"B": 24, "C": 18, "D": 18, "E": 18, "F": 18}.items():
        sheet.column_dimensions[column].width = width
    row = _section(sheet, 6, "Ключевые показатели", 2, 6)
    cards = (
        ("Расчётное сопротивление R, кПа", _quantity(result.get("R"))),
        ("Среднее давление p, кПа", _quantity(result.get("pressure", {}).get("mean"))),
        ("Проверка p ≤ R", "ВЫПОЛНЕНО" if result.get("mean_pressure_ok") else "НЕ ВЫПОЛНЕНО"),
        ("Глубина сжимаемой толщи Hc, м", _quantity(result.get("hc", {}).get("depth") if result.get("hc") else None)),
        ("Осадка s, мм", float(result["settlement"]["total"]["value"]) * 1000 if result.get("settlement") else "—"),
    )
    for column, (label, value) in enumerate(cards, 2):
        label_cell = sheet.cell(row, column, label)
        label_cell.fill = PatternFill("solid", fgColor=PALE)
        label_cell.font = Font(name="Arial", size=9, bold=True, color=NAVY)
        label_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        label_cell.border = TABLE_BORDER
        value_cell = sheet.cell(row + 1, column, value if "results" in sections else "—")
        ok = column != 4 or result.get("mean_pressure_ok")
        value_cell.fill = PatternFill("solid", fgColor=GOOD if ok else WARN)
        value_cell.font = Font(name="Arial", size=14, bold=True, color=NAVY)
        value_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        value_cell.border = TABLE_BORDER
        if isinstance(value_cell.value, float):
            value_cell.number_format = "0.###"
    sheet.row_dimensions[row].height = 40
    sheet.row_dimensions[row + 1].height = 32
    row += 4
    row = _section(sheet, row, "Объект и расчётный случай", 2, 6)
    profile = "учебный: Hc по 0,2σzg" if project.profile.value == "lecture_hc_02" else "СП: Hc по 0,5σzg"
    for index, (label, value) in enumerate((
        ("Объект", project.name), ("Профиль", project.profile_name),
        ("Схема и вариант", f"{project.scheme_number}, {project.scheme_variant}"),
        ("Фундамент / сочетание", f"№{result['foundation_number']} / {result['combination']}"),
        ("Метод определения Hc", profile),
    )):
        sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=6)
        _label_value(sheet, row, label, value, 2, 3, fill=PALE if index % 2 else None)
        for column in range(4, 7):
            sheet.cell(row, column).border = TABLE_BORDER
            if index % 2:
                sheet.cell(row, column).fill = PatternFill("solid", fgColor=PALE)
        row += 1
    row += 1
    row = _section(sheet, row, "Контрольные условия", 2, 6)
    pressure = result.get("pressure", {})
    checks = (
        ("Среднее давление не превышает R", result.get("mean_pressure_ok")),
        ("Отрыв подошвы отсутствует", not pressure.get("uplift", False)),
        ("Краевое давление удовлетворяет pкрай ≤ 1,2R", pressure.get("edge_limit_ok")),
    )
    for label, condition in checks:
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
        for column in range(2, 6):
            sheet.cell(row, column).border = TABLE_BORDER
            sheet.cell(row, column).fill = PatternFill("solid", fgColor=PALE)
        sheet.cell(row, 2, label).font = Font(name="Arial", size=9, color=TEXT)
        sheet.cell(row, 2).alignment = Alignment(vertical="center", wrap_text=True)
        verdict = "НЕ ПРОВЕРЯЛОСЬ" if condition is None else "ВЫПОЛНЕНО" if condition else "НЕ ВЫПОЛНЕНО"
        cell = sheet.cell(row, 6, verdict)
        cell.fill = PatternFill("solid", fgColor=GOOD if condition else WARN)
        cell.font = Font(name="Arial", size=9, bold=True, color=TEXT)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = TABLE_BORDER
        row += 1
    _finish(sheet, 6)


def _input_sheet(book: Workbook, project: Project, result: dict) -> None:
    sheet = _new_sheet(book, "02 Исходные данные", "Исходные данные",
                       "Геометрия, нагрузки и инженерно-геологические условия", 7)
    for column, width in {"B": 24, "C": 17, "D": 13, "E": 24, "F": 17, "G": 16}.items():
        sheet.column_dimensions[column].width = width
    foundation = _foundation(project, result)
    load_record = _load(project, result)
    load_data = load_record.get("data", {}) if load_record else {}
    inputs = result.get("inputs", {})
    row = _section(sheet, 6, "Геометрия фундамента", 2, 4)
    _section(sheet, 6, "Нагрузки", 5, 7)
    geometry = (
        ("Номер", result["foundation_number"], "—"),
        ("Тип", "столбчатый" if foundation and foundation.kind.value == "pad" else "ленточный", "—"),
        ("Ширина b", _quantity(foundation.width.as_dict()) if foundation and foundation.width else "—", "м"),
        ("Длина l", _quantity(foundation.length.as_dict()) if foundation and foundation.length else "—", "м"),
        ("Глубина d", _quantity(foundation.depth.as_dict()) if foundation and foundation.depth else "—", "м"),
    )
    loads = (
        ("N по заданию", _quantity(load_data.get("N")), _unit(load_data.get("N"))),
        ("M по заданию", _quantity(load_data.get("M")), _unit(load_data.get("M"))),
        ("T по заданию", _quantity(load_data.get("T")), _unit(load_data.get("T"))),
        ("M у подошвы", _quantity(inputs.get("moment_at_base")), _unit(inputs.get("moment_at_base"))),
        ("Происхождение M", inputs.get("moment_basis", "—"), "—"),
    )
    _header(sheet, row, ("Параметр", "Значение", "Ед."), 2)
    _header(sheet, row, ("Параметр", "Значение", "Ед."), 5)
    row += 1
    for index in range(max(len(geometry), len(loads))):
        if index < len(geometry):
            _row(sheet, row, geometry[index], 2, fill=PALE if index % 2 else None)
        if index < len(loads):
            _row(sheet, row, loads[index], 5, fill=PALE if index % 2 else None)
        row += 1
    row += 1
    row = _section(sheet, row, "Подвал, удельные веса и настройки единиц", 2, 7)
    settings = (
        ("Подвал", "есть" if project.basement_enabled else "нет", "Высота подвала, м", _number(project.basement_height_m)),
        ("Средний γ фундамента и засыпки", _quantity(inputs.get("foundation_unit_weight")), "Ед.", _unit(inputs.get("foundation_unit_weight"))),
        ("γII ниже подошвы", _quantity(inputs.get("gamma_below_base")), "Режим", inputs.get("gamma_below_base_mode", "—")),
        ("1 тс", _number(inputs.get("unit_conversions", {}).get("tf_to_kn", project.unit_conversions.tf_to_kn)), "кН", "настройка проекта"),
    )
    for index, values in enumerate(settings):
        _row(sheet, row, values, 2, fill=PALE if index % 2 else None)
        sheet.merge_cells(start_row=row, start_column=5, end_row=row, end_column=7)
        for column in range(6, 8):
            sheet.cell(row, column).border = TABLE_BORDER
            if index % 2:
                sheet.cell(row, column).fill = PatternFill("solid", fgColor=PALE)
        row += 1
    row += 1
    row = _section(sheet, row, "Геологический разрез и уровень грунтовых вод", 2, 7)
    row = _header(sheet, row, ("№ слоя", "Грунт №", "Верхняя граница, м", "Нижняя граница, м", "Система координат", "Примечание"), 2)
    elevation = project.geology_coordinate_mode == "elevation" and project.surface_elevation_m is not None
    for index, layer in enumerate(project.layers, 1):
        top = project.surface_elevation_m - layer.top_m if elevation else layer.top_m
        bottom = project.surface_elevation_m - layer.bottom_m if elevation else layer.bottom_m
        note = "верхняя отметка больше нижней" if elevation else "глубина от поверхности"
        row = _row(sheet, row, (index, layer.soil_number, _number(top), _number(bottom),
                                "абсолютные отметки" if elevation else "глубины", note), 2,
                   fill=PALE if index % 2 == 0 else None)
    groundwater = "подтверждено отсутствие" if inputs.get("groundwater_absent") else (
        f"{project.groundwater_m} м" if project.groundwater_m is not None else "не задан")
    row += 1
    sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=7)
    _label_value(sheet, row, "Уровень грунтовых вод", groundwater, 2, 3, fill=SECTION)
    for column in range(4, 8):
        sheet.cell(row, column).fill = PatternFill("solid", fgColor=SECTION)
        sheet.cell(row, column).border = TABLE_BORDER
    _finish(sheet, 7, orientation="landscape")


RAW_FIELDS = (
    ("rho_ii_g_cm3", "ρII", "г/см³"), ("phi_ii_deg", "φII", "°"),
    ("c_ii_kpa", "cII", "кПа"), ("rho_i_g_cm3", "ρI", "г/см³"),
    ("phi_i_deg", "φI", "°"), ("c_i_kpa", "cI", "кПа"),
    ("e_mpa", "E", "МПа"), ("rho_s_g_cm3", "ρs", "г/см³"),
    ("w", "W", "д.е."), ("wl", "WL", "д.е."), ("wp", "WP", "д.е."),
    ("filtration_m_day", "Kф", "м/сут"), ("rc_mpa", "Rc", "МПа"),
)
DERIVED_FIELDS = (
    ("rho_d_g_cm3", "ρd", "г/см³", "ρ/(1+W)"),
    ("e", "e", "д.е.", "ρs/ρd−1"), ("sr", "Sr", "д.е.", "W·ρs/e"),
    ("ip", "Ip", "д.е.", "WL−WP"), ("il", "IL", "д.е.", "(W−WP)/Ip"),
    ("beta", "β", "д.е.", "по типу грунта"),
    ("mv_1_kpa", "mv", "1/кПа", "β/E"),
    ("gamma_kn_m3", "γ", "кН/м³", "ρ·g"),
    ("gamma_s_kn_m3", "γs", "кН/м³", "ρs·g"),
    ("gamma_d_kn_m3", "γd", "кН/м³", "ρd·g"),
    ("gamma_sb_kn_m3", "γsb", "кН/м³", "(γs−γw)/(1+e)"),
)


def _soils_sheet(book: Workbook, result: dict) -> None:
    sheet = _new_sheet(book, "03 Грунты", "Характеристики грунтов",
                       "Каждый грунт приведён отдельной вертикальной карточкой", 5)
    for column, width in {"B": 24, "C": 17, "D": 15, "E": 56}.items():
        sheet.column_dimensions[column].width = width
    row = 6
    soils = list(result.get("soil_calculations", {}).values())
    for soil_index, soil in enumerate(soils):
        if soil_index:
            sheet.row_breaks.append(Break(id=row - 2))
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
        cell = sheet.cell(row, 2, f"Грунт №{soil['number']}: {soil['name']}")
        cell.font = Font(name="Arial", size=12, bold=True, color=WHITE)
        cell.alignment = Alignment(vertical="center")
        for column in range(2, 6):
            sheet.cell(row, column).fill = PatternFill("solid", fgColor=NAVY)
            sheet.cell(row, column).border = TABLE_BORDER
        sheet.row_dimensions[row].height = 25
        row += 1
        row = _row(sheet, row, ("Геологический индекс", soil.get("geological_index", "—"),
                                "Версия", soil.get("version", "—")), 2, fill=PALE)
        row = _section(sheet, row, "Исходные характеристики", 2, 5)
        row = _header(sheet, row, ("Показатель", "Значение", "Единица", "Происхождение"), 2)
        raw = soil.get("raw", {})
        for index, (key, symbol, unit) in enumerate(RAW_FIELDS):
            row = _row(sheet, row, (symbol, _number(raw.get(key)), unit,
                                    f"Таблица грунтов, строка №{soil['number']}"), 2,
                       fill=PALE if index % 2 else None)
        row = _section(sheet, row, "Расчётные и производные характеристики", 2, 5)
        row = _header(sheet, row, ("Показатель", "Значение", "Единица", "Происхождение"), 2)
        derived = soil.get("derived", {})
        for index, (key, symbol, unit, origin) in enumerate(DERIVED_FIELDS):
            row = _row(sheet, row, (symbol, _number(derived.get(key)), unit, origin), 2,
                       fill=PALE if index % 2 else None)
        row = _row(sheet, row, ("Источник записи", _text(soil.get("source")), "—",
                                "снимок каталога проекта"), 2, fill=SECTION)
        warnings = derived.get("warnings", [])
        if warnings:
            row = _row(sheet, row, ("Предупреждения", "; ".join(map(str, warnings)), "—",
                                    "проверка исходных данных"), 2, fill=WARN, height=30)
        row += 2
    _finish(sheet, 5)


def _r_sheet(book: Workbook, result: dict, sections: tuple[str, ...]) -> None:
    sheet = _new_sheet(book, "04 Расчёт R", "Расчёт R и давления",
                       "Формулы, подстановки, коэффициенты и контроль давления", 4)
    for column, width in {"B": 19, "C": 31, "D": 78}.items():
        sheet.column_dimensions[column].width = width
    row = 6
    if "trace" in sections:
        row = _section(sheet, row, "Формулы и подстановки", 2, 4)
        row = _header(sheet, row, ("Величина", "Формула", "Подстановка"), 2)
        formulas = dict(result.get("formulas", {}))
        formulas.setdefault("p0", "p − σzg,0")
        formulas.setdefault("Hc", "граница сжимаемой толщи по принятому критерию")
        substitutions = result.get("substitutions", {})
        for index, key in enumerate(("R", "p", "p0", "Hc", "s")):
            if key not in formulas and key not in substitutions:
                continue
            row = _row(sheet, row, (key, formulas.get(key, "—"), substitutions.get(key, "—")), 2,
                       fill=PALE if index % 2 else None, height=36 if key in ("R", "Hc") else 28)
        row += 1
        row = _section(sheet, row, "Коэффициенты и величины формулы R", 2, 4)
        row = _header(sheet, row, ("Обозначение", "Значение", "Источник и режим"), 2)
        for index, item in enumerate(result.get("inputs", {}).get("R_parameters", [])):
            value = f"{item.get('value', '—')} {item.get('unit', '')}".strip()
            origin = f"{item.get('source', '—')}; {item.get('mode', '—')}"
            row = _row(sheet, row, (item.get("symbol", "—"), value, origin), 2,
                       fill=PALE if index % 2 else None)
        row += 1
    if "pressure" in sections or "results" in sections:
        row = _section(sheet, row, "Результаты и контроль давления", 2, 4)
        row = _header(sheet, row, ("Показатель", "Значение", "Проверка / пояснение"), 2)
        pressure = result.get("pressure", {})
        pressure_rows = (
            ("R, кПа", _quantity(result.get("R")), "расчётное сопротивление"),
            ("p, кПа", _quantity(pressure.get("mean")), "p ≤ R: да" if result.get("mean_pressure_ok") else "p ≤ R: нет"),
            ("p0, кПа", _quantity(result.get("net_pressure")), "дополнительное давление"),
            ("e, м", _quantity(pressure.get("eccentricity")), "эксцентриситет"),
            ("Граница ядра, м", _quantity(pressure.get("kern_limit")), "b/6 для ленточного; размер вдоль M/6 для столбчатого"),
            ("pmin, кПа", _quantity(pressure.get("edge_min")), "минимальное краевое давление"),
            ("pmax, кПа", _quantity(pressure.get("edge_max")), "максимальное краевое давление"),
            ("Отрыв подошвы", "да" if pressure.get("uplift") else "нет", "e превышает границу ядра" if pressure.get("uplift") else "не выявлен"),
        )
        for index, values in enumerate(pressure_rows):
            row = _row(sheet, row, values, 2, fill=PALE if index % 2 else None)
    _finish(sheet, 4)


def _settlement_sheet(book: Workbook, result: dict) -> None:
    settlement = result["settlement"]
    layers = settlement.get("layers", [])
    if layers and "sigma_zg_bottom" not in layers[0]:
        raise ReportError(
            "Снимок расчёта создан предыдущей версией. "
            "Выполните расчёт повторно, чтобы заполнить полную таблицу осадки"
        )
    sheet = _new_sheet(book, "05 Осадка", "Расчёт осадки",
                       "z отсчитывается от подошвы. Напряжения показаны на границах и в среднем по слою", 14)
    for column, width in {
        "B": 24, "C": 9, "D": 9, "E": 11, "F": 9, "G": 13, "H": 14,
        "I": 13, "J": 14, "K": 17, "L": 13, "M": 11, "N": 14,
    }.items():
        sheet.column_dimensions[column].width = width
    row = _section(sheet, 6, "Итоговые параметры", 2, 14)
    summary_header_row = row
    row = _header(sheet, row, ("Показатель", "Значение", "Пояснение"), 2)
    sheet.merge_cells(start_row=summary_header_row, start_column=4, end_row=summary_header_row, end_column=14)
    for column in range(5, 15):
        cell = sheet.cell(summary_header_row, column)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.border = TABLE_BORDER
    summary = (
        ("Hc", _quantity_text(result.get("hc", {}).get("depth") if result.get("hc") else None), "Граница сжимаемой толщи"),
        ("Критерий Hc", f"σzp ≤ {result.get('hc', {}).get('threshold', '—')}·σzg", result.get("hc", {}).get("mode", "—")),
        ("Осадка s", f"{float(settlement['total']['value']) * 1000:.3f} мм", "Σ Δsi"),
    )
    for index, values in enumerate(summary):
        _row(sheet, row, values, 2, fill=PALE if index % 2 else None)
        sheet.merge_cells(start_row=row, start_column=4, end_row=row, end_column=14)
        for column in range(5, 15):
            sheet.cell(row, column).border = TABLE_BORDER
            if index % 2:
                sheet.cell(row, column).fill = PatternFill("solid", fgColor=PALE)
        row += 1
    row += 1
    row = _section(sheet, row, "Таблица послойного суммирования", 2, 14)
    headings = (
        "Вид грунта", "zᵢ, м", "hᵢ, м", "ξ = 2z/b", "α",
        "σzp,i, кПа", "σzp,i ср, кПа", "σzy,i, кПа", "σzy,i ср, кПа",
        "σzp ср − σzy ср, кПа", "σzg,i, кПа", "Eᵢ, МПа", "Δsᵢ, мм",
    )
    header_row = row
    row = _header(sheet, row, headings, 2)
    sheet.row_dimensions[header_row].height = 48
    row = _row(sheet, row, tuple(range(1, 14)), 2, fill=SECTION, bold=True, height=20)
    for column in range(2, 15):
        sheet.cell(row - 1, column).alignment = Alignment(horizontal="center", vertical="center")

    soils = result.get("soil_calculations", {})

    def soil_label(layer: dict) -> str:
        soil_number = layer.get("soil")
        soil = soils.get(str(soil_number), {})
        name = soil.get("name")
        return f"№{soil_number} — {name}" if name else f"Грунт №{soil_number}"

    if layers:
        first = layers[0]
        initial = (
            soil_label(first), _number(first.get("z_top_m", 0)), 0,
            _number(first.get("xi_top")), _number(first.get("alpha_top")),
            _quantity(first.get("sigma_zp_top")), "—",
            _quantity(first.get("sigma_zy_top")), "—", "—",
            _quantity(first.get("sigma_zg_top")), _modulus_mpa(first.get("modulus")), "—",
        )
        row = _row(sheet, row, initial, 2)
        for index, layer in enumerate(layers, 1):
            thickness = Decimal(layer["bottom_m"]) - Decimal(layer["top_m"])
            local_bottom = layer.get("z_bottom_m")
            if local_bottom is None:
                local_bottom = Decimal(layer["bottom_m"]) - Decimal(first["top_m"])
            values = (
                soil_label(layer), _number(local_bottom), _number(thickness),
                _number(layer.get("xi_bottom")), _number(layer.get("alpha_bottom")),
                _quantity(layer.get("sigma_zp_bottom")), _quantity(layer.get("sigma_zp")),
                _quantity(layer.get("sigma_zy_bottom")), _quantity(layer.get("sigma_zy_average")),
                _quantity(layer.get("stress_difference")), _quantity(layer.get("sigma_zg_bottom")),
                _modulus_mpa(layer.get("modulus")), float(layer["settlement"]["value"]) * 1000,
            )
            row = _row(sheet, row, values, 2, fill=PALE if index % 2 == 0 else None)
    total = float(settlement["total"]["value"]) * 1000
    sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=13)
    for column in range(2, 14):
        sheet.cell(row, column).fill = PatternFill("solid", fgColor=GOOD)
        sheet.cell(row, column).border = TABLE_BORDER
    sheet.cell(row, 2, "Итого осадка Σ Δsi").font = Font(name="Arial", size=10, bold=True, color=NAVY)
    sheet.cell(row, 2).alignment = Alignment(horizontal="right", vertical="center")
    value_cell = sheet.cell(row, 14, total)
    value_cell.fill = PatternFill("solid", fgColor=GOOD)
    value_cell.border = TABLE_BORDER
    value_cell.font = Font(name="Arial", size=10, bold=True, color=NAVY)
    value_cell.number_format = "0.###"
    _finish(sheet, 14, orientation="landscape")


def _notes_sheet(book: Workbook, project: Project, result: dict, sections: tuple[str, ...]) -> None:
    sheet = _new_sheet(book, "06 Примечания", "Примечания и источники",
                       "Предупреждения расчёта и происхождение исходных данных", 4)
    for column, width in {"B": 8, "C": 72, "D": 32}.items():
        sheet.column_dimensions[column].width = width
    row = 6
    if "warnings" in sections:
        row = _section(sheet, row, "Предупреждения и допущения", 2, 4)
        row = _header(sheet, row, ("№", "Сообщение", "Статус"), 2)
        warnings = result.get("warnings", [])
        if not warnings:
            row = _row(sheet, row, (1, "Предупреждений нет", "информация"), 2, fill=GOOD)
        else:
            for index, warning in enumerate(warnings, 1):
                row = _row(sheet, row, (index, warning, "проверить допущение"), 2, fill=WARN, height=32)
        row += 1
    if "sources" in sections:
        row = _section(sheet, row, "Источники", 2, 4)
        row = _header(sheet, row, ("№", "Данные", "Источник"), 2)
        for index, (name, source) in enumerate(result.get("sources", {}).items(), 1):
            row = _row(sheet, row, (index, name, source), 2, fill=PALE if index % 2 == 0 else None, height=30)
        row += 1
        row = _section(sheet, row, "Параметры формирования отчёта", 2, 4)
        for index, (label, value) in enumerate((
            ("Проект", project.name), ("Профиль", project.profile_name),
            ("Формат проекта", ".oifproj"), ("Состав листов", "по выбранному пресету отчёта"),
        )):
            sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=4)
            _label_value(sheet, row, label, value, 2, 3, fill=PALE if index % 2 else None)
            sheet.cell(row, 4).border = TABLE_BORDER
            if index % 2:
                sheet.cell(row, 4).fill = PatternFill("solid", fgColor=PALE)
            row += 1
    _finish(sheet, 4)


def export_excel(project: Project, path: str | Path, *, preset: str = "full") -> Path:
    """Сформировать утверждённую шестилистовую инженерную книгу Excel."""
    result = require_snapshot(project)
    sections = included_sections(project, preset)
    book = Workbook()
    book.remove(book.active)
    book.properties.title = f"Расчёт основания — {project.name}"
    book.properties.subject = "Фундамент мелкого заложения"
    book.properties.creator = "OIF Foundations"
    book.properties.description = "Отчёт сформирован из сохранённого снимка расчётного ядра"

    _result_sheet(book, project, result, sections)
    if "input" in sections:
        _input_sheet(book, project, result)
        if result.get("soil_calculations"):
            _soils_sheet(book, result)
    if "trace" in sections or "pressure" in sections or "results" in sections:
        _r_sheet(book, result, sections)
    if "settlement" in sections and result.get("settlement"):
        _settlement_sheet(book, result)
    if "warnings" in sections or "sources" in sections:
        _notes_sheet(book, project, result, sections)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    book.save(target)
    return target
