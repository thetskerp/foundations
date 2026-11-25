"""Сценарии приложения: интерфейс вызывает их, не вычисляет формулы сам."""

from dataclasses import dataclass
import os
from pathlib import Path

from .catalog import Catalog
from .domain import Project
from .seed import install_pilot_catalog
from .standards.r0 import R0SelectionError, preliminary_area, select_r0
from .units import Quantity


def user_catalog_path() -> Path:
    override = os.environ.get("OIF_DATA_DIR")
    if override:
        return Path(override).expanduser() / "catalog.sqlite"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "OIF Foundations" / "catalog.sqlite"
    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OIF Foundations" / "catalog.sqlite"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "oif-foundations" / "catalog.sqlite"


def open_pilot_catalog(path: str | Path | None = None) -> Catalog:
    catalog = Catalog(path or user_catalog_path())
    install_pilot_catalog(catalog)
    return catalog


@dataclass(frozen=True)
class PreliminaryResult:
    soil_number: int
    load_key: str
    r0: Quantity | None
    area: Quantity | None
    message: str
    r0_table: str = ""
    r0_parameters: dict[str, str] | None = None
    r0_explanation: str = ""


def preliminary_for_foundation(project: Project, catalog: Catalog, foundation_number: int, combination: int = 1, *, mean_unit_weight: Quantity | None = None, sand_density: str | None = None, sand_moisture: str | None = None) -> PreliminaryResult:
    if mean_unit_weight is None:
        return PreliminaryResult(0, "", None, None, "Укажите средний удельный вес фундамента и засыпки")
    if not project.scheme_number or not project.scheme_variant:
        return PreliminaryResult(0, "", None, None, "Сначала выберите схему и вариант")
    foundation = next((f for f in project.foundations if f.number == foundation_number), None)
    if foundation is None or foundation.depth is None:
        return PreliminaryResult(0, "", None, None, "Укажите фундамент и глубину заложения")
    if not project.layers:
        return PreliminaryResult(0, "", None, None, "Задайте геологические слои и слой под подошвой")
    depth = foundation.depth.to("m").value
    matching = [layer for layer in project.layers if layer.top_m <= depth < layer.bottom_m]
    if len(matching) != 1:
        return PreliminaryResult(0, "", None, None, "Подошва не привязана однозначно к геологическому слою")
    soil_number = matching[0].soil_number
    soil = catalog.get("soil", str(soil_number))
    if soil is None:
        return PreliminaryResult(soil_number, "", None, None, "Грунт под подошвой отсутствует в справочнике")
    key = f"{project.scheme_number}:{project.scheme_variant}:{foundation_number}:{combination}"
    load = catalog.get("load", key)
    if load is None:
        return PreliminaryResult(soil_number, key, None, None, "Для фундамента нет выбранного сочетания нагрузок")
    try:
        selection = select_r0(soil["data"], sand_density=sand_density, sand_moisture=sand_moisture)
        r0 = selection.value
        vertical = Quantity.from_dict(load["data"]["N"]).to("kN", project.unit_conversions)
        area = preliminary_area(vertical, r0, foundation.depth, mean_unit_weight)
        warning = "; запись грунта извлечена из цифрового текста задания и не сверена визуально" if soil["data"].get("verification", "").startswith("извлечено") else ""
        if load["data"].get("verification", "").startswith("извлечено"):
            warning += "; нагрузка извлечена из цифрового текста задания и не сверена визуально"
        return PreliminaryResult(soil_number, key, r0, area, "Предварительная площадь по R0; окончательная проверка по R ещё не выполнена" + warning,
            selection.table, selection.parameters, selection.explanation)
    except R0SelectionError as exc:
        return PreliminaryResult(soil_number, key, None, None, str(exc))
