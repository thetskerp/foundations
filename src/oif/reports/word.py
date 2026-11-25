"""Word отчёт из сохранённого снимка; формулы только отображаются."""

from pathlib import Path
from decimal import Decimal

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from ..domain import Project
from .common import display_quantity, geology_text, included_sections, require_snapshot


def _table(document: Document, headings: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    table = document.add_table(rows=1, cols=len(headings))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, value in zip(table.rows[0].cells, headings):
        cell.text = value
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), "203955")
        cell._tc.get_or_add_tcPr().append(shading)
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
    header_properties = table.rows[0]._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    header_properties.append(repeat)
    for row in rows:
        table_row = table.add_row()
        no_split = OxmlElement("w:cantSplit")
        table_row._tr.get_or_add_trPr().append(no_split)
        for cell, value in zip(table_row.cells, row):
            cell.text = str(value)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)


def _short(value, places: int = 5) -> str:
    if value in (None, "", "-"):
        return "—"
    rendered = f"{Decimal(str(value)):.{places}f}".rstrip("0").rstrip(".")
    return rendered or "0"


SOIL_FORMULAS = {
    "Геологический индекс": "Исходное значение из таблицы грунтов",
    "ρII, г/см³": "Исходное значение из табицы грунтов",
    "φII, °": "Исходное значение из таблицы грунтов",
    "cII, кПа": "Исходное значение из таблицы грунтов",
    "ρI, г/см³": "Исходное значение из таблицы грунтов",
    "φI, °": "Исходное значение из таблицы грунтов",
    "cI, кПа": "Исходное значение из таблицы грунтов",
    "E, МПа": "Исходное значение из таблицы грунтов",
    "ρs, г/см³": "Исходное значение из таблицы грунтов",
    "W": "Исходное значение из таблицы грунтов",
    "WL": "Исходное значение из таблицы грунтов",
    "WP": "Исходное значение из таблицы грунтов",
    "Kф, м/сут": "Исходное значение из таблицы грунтов",
    "Rc, МПа": "Исходное значение из таблицы грунтов",
    "ρd, г/см³": "ρd = ρII / (1 + W)",
    "e": "e = (ρs − ρd) / ρd",
    "Sr": "Sr = W·ρs / e  (ρw = 1 г/см³)",
    "Ip": "Ip = WL − WP",
    "IL": "IL = (W − WP) / Ip",
    "β": "По таблице задания в зависимости от вида грунта",
    "mv, 1/кПа": "mv = β / E  (E в кПа)",
    "γ, кН/м³": "γ = ρII·g",
    "γs, кН/м³": "γs = ρs·g",
    "γd, кН/м³": "γd = ρd·g",
    "γsb, кН/м³": "γsb = (ρs − ρw)·g / (1 + e)",
    "Источник": "Запись каталога грунтов",
}


INPUT_FORMULAS = {
    "Схема": "Задано в проекте",
    "Нагрузка": "Выбранные схема, фундамент и сочетание",
    "Грунты": "Заданы в проекте",
    "УГВ": "Исходная глубина от поверхности",
    "1 тс, кН": "N[кН] = N[тс]·kтс→кН",
    "g, м/с²": "Коэффициент настройки проекта",
    "1 мм, м": "L[м] = L[мм]·kмм→м",
    "1 МПа, кПа": "σ[кПа] = σ[МПа]·kМПа→кПа",
    "1 г/см³, кг/м³": "ρ[кг/м³] = ρ[г/см³]·kρ",
    "Тип фундамента": "Задано в таблице фундаментов",
    "Ширина подошвы": "Исходный размер b",
    "Длина подошвы": "Исходный размер l",
    "Глубина подошвы": "Исходная глубина d",
    "Геология": "Заданные границы ИГЭ",
    "Нагрузка по заданию": "Исходные N, M, T для выбранного сочетания",
}


def export_word(project: Project, path: str | Path, *, preset: str = "full") -> Path:
    snapshot = require_snapshot(project)
    sections = included_sections(project, preset)
    document = Document()
    main = document.sections[0]
    main.page_width = Inches(8.5)
    main.page_height = Inches(11)
    main.top_margin = main.bottom_margin = Inches(0.8)
    main.left_margin = main.right_margin = Inches(0.9)
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    title_style = document.styles["Title"]
    title_style.font.name = "Arial"
    title_style.font.size = Pt(26)
    title_style.font.color.rgb = RGBColor(0, 0, 0)
    title_properties = title_style.element.get_or_add_pPr()
    title_border = title_properties.find(qn("w:pBdr"))
    if title_border is not None:
        title_properties.remove(title_border)
    for style_name in ("Heading 1", "Heading 2"):
        style = document.styles[style_name]
        style.font.name = "Arial"
        style.font.color.rgb = RGBColor(0, 0, 0)
    section_number = 0
    def section(title: str):
        nonlocal section_number
        section_number += 1
        document.add_heading(f"{section_number}. {title}", 1)
    document.add_paragraph("Расчёт основания фундамента мелкого заложения", style="Title")
    document.add_paragraph(project.name)
    document.add_paragraph(f"Профиль проекта: {project.profile_name}")
    document.add_paragraph(f"Фундамент №{snapshot['foundation_number']}; сочетание нагрузок {snapshot['combination']}")
    profile_name = "учебный, Hc по 0,2σzg" if project.profile.value == "lecture_hc_02" else "Hc по критерию СП, 0,5σzg"
    document.add_paragraph(f"Вариант: {profile_name}. Осадка вычислена по лекции №5, по формуле с Ei.")
    if "input" in sections:
        section("Исходные данные")
        inputs = snapshot.get("inputs", {})
        labels = {"moment_at_base": "Момент на уровне подошвы", "moment_basis": "Происхождение момента", "foundation_unit_weight": "Средний удельный вес фундамента и засыпки", "gamma_below_base": "Удельный вес грунта ниже подошвы", "strength_from_tests": "Прочность по испытаниям (k=1)", "rigid_scheme": "Жёсткая конструктивная схема", "length_height_ratio": "Отношение L/H", "weak_layer_selected": "Особое правило слабого слоя", "basement_floor_depth": "Глубина пола подвала", "basement_soil_height": "hs", "basement_floor_thickness": "hcf", "basement_floor_unit_weight": "γcf", "d1": "Приведённая глубина d1", "db": "Учитываемая глубина подвала db"}
        rows = [("Схема", f"{project.scheme_number}, {project.scheme_variant}", INPUT_FORMULAS["Схема"]),
                ("Нагрузка", snapshot["load_key"], INPUT_FORMULAS["Нагрузка"]),
                ("Грунты", ", ".join(str(x) for x in project.selected_soils), INPUT_FORMULAS["Грунты"]),
                ("УГВ", "отсутствует" if snapshot.get("inputs", {}).get("groundwater_absent") else f"{project.groundwater_m} м", INPUT_FORMULAS["УГВ"])]
        conversions = inputs.get("unit_conversions", project.unit_conversions.as_dict())
        rows.extend((("Перевод 1 тс в кН", conversions["tf_to_kn"], INPUT_FORMULAS["1 тс, кН"]),
                     ("Ускорение свободного падения (g), м/с²", conversions["gravity_m_s2"], INPUT_FORMULAS["g, м/с²"]),
                     ("Перевод 1 мм в м", conversions["mm_to_m"], INPUT_FORMULAS["1 мм, м"]),
                     ("Перевод 1 МПа в кПа", conversions["mpa_to_kpa"], INPUT_FORMULAS["1 МПа, кПа"]),
                     ("Перевод 1 г/см³ в кг/м³", conversions["g_cm3_to_kg_m3"], INPUT_FORMULAS["1 г/см³, кг/м³"])))
        foundation = next((item for item in project.foundations if item.number == snapshot["foundation_number"]), None)
        if foundation is not None:
            rows.extend((("Тип фундамента", "столбчатый" if foundation.kind.value == "pad" else "ленточный", INPUT_FORMULAS["Тип фундамента"]),
                         ("Ширина подошвы (b)", display_quantity(foundation.width.as_dict()), INPUT_FORMULAS["Ширина подошвы"]),
                         ("Длина подошвы (l)", display_quantity(foundation.length.as_dict()), INPUT_FORMULAS["Длина подошвы"]),
                         ("Глубина заложения (d)", display_quantity(foundation.depth.as_dict()), INPUT_FORMULAS["Глубина подошвы"])))
        rows.append(("Геологический разрез", geology_text(project), INPUT_FORMULAS["Геология"]))
        load = project.catalog_snapshot.get("loads", {}).get(snapshot["load_key"])
        if load:
            data = load["data"]
            rows.append(("Нагрузка по заданию", ", ".join(f"{key}={display_quantity(data[key])}" for key in ("N", "M", "T") if data.get(key)), INPUT_FORMULAS["Нагрузка по заданию"]))
        for key, label in labels.items():
            value = inputs.get(key)
            if value is None:
                continue
            display = display_quantity(value) if isinstance(value, dict) and "unit" in value else "да" if value is True else "нет" if value is False else str(value)
            source = {
                "moment_at_base": "Задано на уровне подошвы; e = M/NΣ",
                "moment_basis": "Текстовое обоснование пользователя",
                "foundation_unit_weight": "Исходное γf; входит в NΣ = N + γf·d·b·l",
                "gamma_below_base": "γII = Σ(γi·hi) / Σhi или введено вручную",
                "strength_from_tests": "k = 1 для испытаний; k = 1,1 для табличных характеристик",
                "rigid_scheme": "Определяет выбор γc2 по таблице 5.4",
                "length_height_ratio": "L/H",
                "weak_layer_selected": "Условие E ≤ 7 МПа для границы Hc",
                "basement_floor_depth": "db = min(db,факт; 2 м)",
                "basement_soil_height": "Исходная толщина hs",
                "basement_floor_thickness": "Исходная толщина hcf",
                "basement_floor_unit_weight": "Исходное γcf",
                "d1": "d1 = d; при подвале d1 = hs + hcf·γcf/γ′II",
                "db": "db = min(db,факт; 2 м)",
            }.get(key, "Исходное значение или настройка расчёта")
            rows.append((label, display, source))
        _table(document, ("Параметр", "Значение", "Формула или источник"), rows)
        for soil in snapshot.get("soil_calculations", {}).values():
            document.add_heading(f"Грунт №{soil['number']}: {soil['name']}", 2)
            raw, derived = soil["raw"], soil["derived"]
            soil_rows = [
                ("Геологический индекс", soil["geological_index"]),
                ("ρII, г/см³", raw.get("rho_ii_g_cm3")), ("φII, °", raw.get("phi_ii_deg")), ("cII, кПа", raw.get("c_ii_kpa")),
                ("ρI, г/см³", raw.get("rho_i_g_cm3")), ("φI, °", raw.get("phi_i_deg")), ("cI, кПа", raw.get("c_i_kpa")),
                ("E, МПа", raw.get("e_mpa")), ("ρs, г/см³", raw.get("rho_s_g_cm3")), ("W", raw.get("w")),
                ("WL", raw.get("wl")), ("WP", raw.get("wp")), ("Kф, м/сут", raw.get("filtration_m_day")),
                ("Rc, МПа", raw.get("rc_mpa")),
                ("ρd, г/см³", _short(derived.get("rho_d_g_cm3"))), ("e", _short(derived.get("e"))), ("Sr", _short(derived.get("sr"))),
                ("Ip", _short(derived.get("ip"))), ("IL", _short(derived.get("il"))), ("β", _short(derived.get("beta"))),
                ("mv, 1/кПа", _short(derived.get("mv_1_kpa"), 8)), ("γ, кН/м³", _short(derived.get("gamma_kn_m3"), 3)),
                ("γs, кН/м³", _short(derived.get("gamma_s_kn_m3"), 3)), ("γd, кН/м³", _short(derived.get("gamma_d_kn_m3"), 3)),
                ("γsb, кН/м³", _short(derived.get("gamma_sb_kn_m3"), 3)), ("Источник", soil.get("source")),
            ]
            _table(document, ("Характеристика", "Значение", "Формула или источник"), [
                (name, "—" if value is None else value, SOIL_FORMULAS.get(name, "Исходное значение"))
                for name, value in soil_rows
            ])
    if "results" in sections:
        if "input" in sections:
            document.add_page_break()
        section("Результаты")
        _table(document, ("Показатель", "Результат", "Формула"), [
            ("Расчётное сопротивление (R)", display_quantity(snapshot["R"]), snapshot.get("formulas", {}).get("R", "—")),
            ("Среднее давление (p)", display_quantity(snapshot["pressure"]["mean"]), snapshot.get("formulas", {}).get("p", "—")),
            ("Условие p ≤ R", "выполнено" if snapshot["mean_pressure_ok"] else "не выполнено", "p ≤ R"),
            ("Глубина сжимаемой толщи (Hc)", display_quantity(snapshot["hc"]["depth"]) if snapshot.get("hc") else "не определено", f"σzp ≤ {snapshot['hc']['threshold']}·σzg" if snapshot.get("hc") else "—"),
            ("Осадка (s)", display_quantity(snapshot["settlement"]["total"], 4) if snapshot.get("settlement") else "не определена", snapshot.get("formulas", {}).get("s", "—")),
        ])
    if "pressure" in sections:
        section("Давление и эксцентриситет")
        p = snapshot["pressure"]
        _table(document, ("Показатель", "Значение", "Формула"), [
            ("Эксцентриситет (e)", display_quantity(p["eccentricity"], 4), "e = M/NΣ"),
            ("Размер вдоль действия момента (a)", display_quantity(p.get("kern_dimension")), "a = l для столбчатого; a = b для ленточного"),
            ("Граница ядра", display_quantity(p.get("kern_limit")), "a/6"),
            ("Отрыв подошвы", "да" if p["uplift"] else "нет", "e > a/6"),
            ("Минимальное краевое давление (pmin)", display_quantity(p["edge_min"]), "pmin = p − M/W"),
            ("Максимальное краевое давление (pmax)", display_quantity(p["edge_max"]), "pmax = p + M/W"),
            ("Условие pmax ≤ 1,2R", "не проверялось" if p["edge_limit_ok"] is None else "выполнено" if p["edge_limit_ok"] else "не выполнено", "pmax ≤ 1,2R"),
        ])
    if "settlement" in sections and snapshot.get("settlement"):
        section("Послойный расчёт осадки")
        document.add_paragraph(
            f"Hc = {display_quantity(snapshot['hc']['depth'])}; "
            f"граница по условию σzp ≤ {snapshot['hc']['threshold']}·σzg."
        )
        rows = []
        for index, layer in enumerate(snapshot["settlement"]["layers"], 1):
            height = Decimal(layer["bottom_m"]) - Decimal(layer["top_m"])
            rows.append((
                str(index),
                str(layer["soil"]),
                f"{layer['top_m']}–{layer['bottom_m']} м\nhᵢ = {height} м\nhᵢ = zниз − zверх",
                f"αᵢ = {layer['alpha']}\nαᵢ = (αверх + αниз)/2\nξ = 2z/b",
                f"{display_quantity(layer['sigma_zp'])}\nσzp,i = (σzp,верх + σzp,низ)/2\nσzp = α·p0",
                f"{display_quantity(layer['modulus'])}\nиз таблицы грунта",
                f"{display_quantity(layer['settlement'], 5)}\nΔsᵢ = 0,8·σzp,i·hᵢ/Eᵢ",
            ))
        _table(document, ("№", "Грунт", "Слой и hᵢ", "αᵢ и ξ", "σzp,i", "Eᵢ", "Δsᵢ"), rows)
    if "trace" in sections:
        section("Формулы и подстановки")
        parameters = snapshot.get("inputs", {}).get("R_parameters", [])
        if parameters:
            document.add_heading("Коэффициенты и величины формулы R", 2)
            _table(document, ("Обозначение", "Значение", "Ед.", "Откуда взято", "Режим"), [
                (item.get("symbol", ""), item.get("value", ""), item.get("unit", ""), item.get("source", ""), item.get("mode", ""))
                for item in parameters
            ])
        for key, formula in snapshot.get("formulas", {}).items():
            document.add_paragraph(f"{key} = {formula}")
            if key in snapshot.get("substitutions", {}):
                document.add_paragraph(f"Подстановка: {snapshot['substitutions'][key]}")
        for key in ("p0", "Hc"):
            if key in snapshot.get("substitutions", {}):
                document.add_paragraph(f"{key}: {snapshot['substitutions'][key]}")
        conditions = snapshot.get("working_conditions", {})
        document.add_paragraph(f"γc1={conditions.get('gamma_c1')}; γc2={conditions.get('gamma_c2')}; {conditions.get('category')}.")
    if "warnings" in sections and snapshot.get("warnings"):
        section("Предупреждения")
        for warning in snapshot["warnings"]:
            document.add_paragraph(warning, style="List Bullet")
    if "sources" in sections:
        section("Источники")
        for name, source in snapshot.get("sources", {}).items():
            document.add_paragraph(f"{name}: {source}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(target)
    return target
