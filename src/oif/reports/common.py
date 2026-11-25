"""Общие данные отчёта; вычислений инженерных величин здесь нет."""

from ..domain import Project
from ..project_io import input_fingerprint


class ReportError(ValueError):
    pass


SECTION_ORDER = ("input", "results", "pressure", "settlement", "trace", "warnings", "sources")
SECTION_DEPENDENCIES = {
    "results": ("input",),
    "pressure": ("results",),
    "settlement": ("results",),
    "trace": ("input", "results"),
}
PRESETS = {
    "brief": ("input", "results", "warnings", "sources"),
    "standard": ("input", "results", "pressure", "settlement", "warnings", "sources"),
    "full": SECTION_ORDER,
}


def included_sections(project: Project, preset: str = "full") -> tuple[str, ...]:
    if preset == "custom":
        selected = project.report_settings.get("sections", [])
        unknown = set(selected) - set(SECTION_ORDER)
        if unknown:
            raise ReportError(f"Неизвестные разделы отчёта: {sorted(unknown)}")
        missing = {
            section: [parent for parent in SECTION_DEPENDENCIES.get(section, ()) if parent not in selected]
            for section in selected
        }
        missing = {section: parents for section, parents in missing.items() if parents}
        if missing:
            detail = "; ".join(f"{section}: {', '.join(parents)}" for section, parents in missing.items())
            raise ReportError(f"Выбраны зависимые разделы без родительских: {detail}")
        return tuple(section for section in SECTION_ORDER if section in selected)
    if preset not in PRESETS:
        raise ReportError(f"Неизвестный пресет отчёта: {preset}")
    return PRESETS[preset]


def require_snapshot(project: Project) -> dict:
    snapshot = project.calculation_snapshot
    if not snapshot or not snapshot.get("R") or not snapshot.get("pressure"):
        raise ReportError("Сначала выполните расчёт и сохраните его снимок")
    if snapshot.get("input_hash") != input_fingerprint(project):
        raise ReportError("Исходные данные изменились после расчёта; выполните расчёт повторно")
    return snapshot


def display_quantity(value: dict | None, places: int = 3) -> str:
    if value is None:
        return "—"
    return f"{float(value['value']):.{places}f} {value['unit']}"


def geology_text(project: Project) -> str:
    if project.geology_coordinate_mode == "elevation" and project.surface_elevation_m is not None:
        return "; ".join(
            f"№{layer.soil_number}: {project.surface_elevation_m - layer.top_m}–{project.surface_elevation_m - layer.bottom_m} м (абс. отм.)"
            for layer in project.layers
        )
    return "; ".join(f"№{layer.soil_number}: {layer.top_m}–{layer.bottom_m} м (глубина)" for layer in project.layers)
