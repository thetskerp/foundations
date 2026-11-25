"""Печатный PDF и табличный Excel из версионированного справочника."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from ..catalog import Catalog
from ..soil_properties import SoilPropertiesError, calculate_soil_properties


def _short(value, places: int = 5) -> str:
    if value in (None, "", "-"):
        return "—"
    rendered = f"{Decimal(str(value)):.{places}f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _rows(catalog: Catalog, kind: str, keys: set[str] | None, *, compact: bool = False) -> tuple[list[list[str]], list[int]]:
    records = [record for record in catalog.list(kind) if keys is None or record["key"] in keys]
    if kind == "soil":
        if compact:
            rows = [["№", "Грунт / индекс", "По деформациям", "По несущей способности", "Физические", "ρd; e; Sr", "Ip; IL; β; mv", "γ; γs; γd; γsb", "Источник"]]
        else:
            rows = [["№", "Грунт", "Индекс", "ρII, г/см³", "φII, °", "cII, кПа", "ρI, г/см³", "φI, °", "cI, кПа", "E, МПа", "ρs, г/см³", "W", "WL", "WP", "Kф, м/сут", "ρd, г/см³", "e", "Sr", "Ip", "IL", "β", "mv, 1/кПа", "γ, кН/м³", "γs, кН/м³", "γd, кН/м³", "γsb, кН/м³", "Источник"]]
        for record in records:
            d = record["data"]
            try:
                p = calculate_soil_properties(d).as_dict()
            except SoilPropertiesError:
                p = {}
            if compact:
                rows.append([record["key"], f"{d['name']}\n{d['geological_index']}",
                    f"ρII={d['rho_ii_g_cm3']}; φII={d['phi_ii_deg']}; cII={d.get('c_ii_kpa') or '—'}; E={d['e_mpa']}",
                    f"ρI={d.get('rho_i_g_cm3') or '—'}; φI={d.get('phi_i_deg') or '—'}; cI={d.get('c_i_kpa') or '—'}",
                    f"ρs={d['rho_s_g_cm3']}; W={d['w']}; WL={d.get('wl') or '—'}; WP={d.get('wp') or '—'}; Kф={d.get('filtration_m_day') or '—'}",
                    f"{_short(p.get('rho_d_g_cm3'))}; {_short(p.get('e'))}; {_short(p.get('sr'))}", f"{_short(p.get('ip'))}; {_short(p.get('il'))}; {_short(p.get('beta'))}; {_short(p.get('mv_1_kpa'), 8)}",
                    f"{_short(p.get('gamma_kn_m3'), 3)}; {_short(p.get('gamma_s_kn_m3'), 3)}; {_short(p.get('gamma_d_kn_m3'), 3)}; {_short(p.get('gamma_sb_kn_m3'), 3)}",
                    f"v{record['version']}; {record['source']}"])
            else:
                rows.append([record["key"], d["name"], d.get("geological_index"), d.get("rho_ii_g_cm3"), d.get("phi_ii_deg"), d.get("c_ii_kpa"), d.get("rho_i_g_cm3"), d.get("phi_i_deg"), d.get("c_i_kpa"), d.get("e_mpa"), d.get("rho_s_g_cm3"), d.get("w"), d.get("wl"), d.get("wp"), d.get("filtration_m_day"), p.get("rho_d_g_cm3"), p.get("e"), p.get("sr"), p.get("ip"), p.get("il"), p.get("beta"), p.get("mv_1_kpa"), p.get("gamma_kn_m3"), p.get("gamma_s_kn_m3"), p.get("gamma_d_kn_m3"), p.get("gamma_sb_kn_m3"), f"v{record['version']}; {record['source']}"])
        return (rows, [35, 75, 75, 75, 90, 90, 85, 85, 170]) if compact else (rows, [45, 100, 65, *([65] * 23), 260])
    if kind == "load":
        rows = [["Схема:вариант:№:соч.", "N, тс", "M, тс·м", "T, тс", "Источник"]]
        for record in records:
            d = record["data"]
            rows.append([record["key"], d["N"]["value"], d["M"]["value"] if d["M"] else "—", d["T"]["value"] if d["T"] else "—", f"v{record['version']}; {record['source']}"])
        return rows, [130, 60, 80, 60, 445]
    if kind == "scheme":
        rows = [["№", "Название", "Фундаменты", "Источник"]]
        for record in records:
            d = record["data"]
            rows.append([record["key"], d["name"], ", ".join(map(str, d["foundation_numbers"])), f"v{record['version']}; {record['source']}"])
        return rows, [60, 200, 140, 375]
    rows = [["№ / ключ", "Версия", "Данные", "Источник"]]
    for record in records:
        data = record["data"]
        detail = "; ".join(f"{key}={value}" for key, value in data.items() if value is not None and key not in ("number", "scheme", "variant", "foundation", "combination"))
        rows.append([record["key"], str(record["version"]), detail, record["source"]])
    return rows, [60, 50, 460, 205]


def export_catalog_excel(catalog: Catalog, path: str | Path, *, kind: str = "soil", keys: set[str] | None = None) -> Path:
    rows, widths = _rows(catalog, kind, keys)
    book = Workbook()
    sheet = book.active
    sheet.title = "Справочник"
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="203955")
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = min(70, max(12, width // 7))
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    book.save(target)
    return target


def _font_path() -> Path:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Для PDF нужен шрифт с кириллицей: Arial или DejaVu Sans")


def export_catalog_pdf(catalog: Catalog, path: str | Path, *, kind: str = "soil", keys: set[str] | None = None, title: str | None = None) -> Path:
    rows, widths = _rows(catalog, kind, keys, compact=(kind == "soil"))
    font = _font_path()
    pdfmetrics.registerFont(TTFont("OIF-Cyrillic", str(font)))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(target), pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=34, bottomMargin=34)
    normal = ParagraphStyle("OIF normal", fontName="OIF-Cyrillic", fontSize=8, leading=11)
    heading = ParagraphStyle("OIF heading", parent=normal, fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=8)
    column_heading = ParagraphStyle("OIF column", parent=normal, textColor=colors.white)
    names = {"soil": "Грунты", "scheme": "Схемы", "load": "Нагрузки"}
    story = [Paragraph(title or f"Справочник: {names.get(kind, kind)}", heading),
             Paragraph(f"Редакция источника: СП 22.13330.2016 и задание на КР; экспорт {datetime.now().strftime('%d.%m.%Y')}; записей: {len(rows)-1}", normal), Spacer(1, 10)]
    safe_rows = [[Paragraph(str(cell).replace("&", "&amp;").replace("<", "&lt;"), column_heading if index == 0 else normal) for cell in row] for index, row in enumerate(rows)]
    table = Table(safe_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#203955")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9D9D9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    document.build(story)
    return target
