"""Переносимый .oifproj с проверкой целостности и без выполнения кода из архива."""

import hashlib
import json
import os
import re
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from .domain import FoundationInput, FoundationKind, GeologyLayer, Profile, Project
from .units import Quantity, UnitConversions

SCHEMA_VERSION = 6
MAX_MEMBER_BYTES = 25_000_000
MEMBERS = ("project.json", "catalog_snapshot.json", "calculation_snapshot.json", "report_settings.json")


class ProjectFormatError(ValueError):
    pass


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_path_component(value: str, fallback: str = "Проект") -> str:
    """Имя папки, допустимое в Windows, macOS и Linux."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(". ")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:120].rstrip(". ")


def project_workspace_paths(parent: str | Path, object_name: str, profile_name: str) -> tuple[Path, Path]:
    """Вернуть папку проекта и путь .oifproj, не изменяя файловую систему."""
    parts = [safe_path_component(object_name)]
    if profile_name.strip():
        parts.append(safe_path_component(profile_name, "Основной"))
    folder_name = " — ".join(parts)
    folder = Path(parent).expanduser() / folder_name
    return folder, folder / f"{folder_name}.oifproj"


def _encode(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_encode(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    return value


def _json_bytes(value) -> bytes:
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def input_fingerprint(project: Project, calculation_settings_override: dict | None = None) -> str:
    data = {name: getattr(project, name) for name in ("profile", "scheme_number", "scheme_variant", "selected_soils", "foundations", "layers", "geology_coordinate_mode", "surface_elevation_m", "groundwater_m", "basement_enabled", "basement_height_m", "calculation_settings", "unit_conversions")}
    if calculation_settings_override is not None:
        data["calculation_settings"] = calculation_settings_override
    return hashlib.sha256(_json_bytes(data)).hexdigest()


def save_project(project: Project, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    project_data = _encode(project)
    for key in ("catalog_snapshot", "calculation_snapshot", "report_settings"):
        project_data.pop(key)
    bodies = {
        "project.json": _json_bytes(project_data),
        "catalog_snapshot.json": _json_bytes(project.catalog_snapshot),
        "calculation_snapshot.json": _json_bytes(project.calculation_snapshot),
        "report_settings.json": _json_bytes(project.report_settings),
    }
    manifest = {
        "format": "oifproj",
        "schema_version": SCHEMA_VERSION,
        "application_version": "0.3.0",
        "members": {name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)} for name, body in bodies.items()},
    }
    with NamedTemporaryFile(prefix="oif-", suffix=".tmp", dir=target.parent, delete=False) as temp:
        temporary_path = Path(temp.name)
    try:
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json_bytes(manifest))
            for name, body in bodies.items():
                archive.writestr(name, body)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_project(path: str | Path) -> Project:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if set(names) != {"manifest.json", *MEMBERS} or len(names) != 5:
            raise ProjectFormatError("Неожиданный состав проекта")
        if any(archive.getinfo(name).file_size > MAX_MEMBER_BYTES for name in names):
            raise ProjectFormatError("Слишком большой файл внутри проекта")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "oifproj" or manifest.get("schema_version") not in (1, 2, 3, 4, 5, SCHEMA_VERSION):
            raise ProjectFormatError("Неподдерживаемая версия проекта")
        bodies = {}
        for name in MEMBERS:
            body = archive.read(name)
            expected = manifest.get("members", {}).get(name, {})
            if len(body) != expected.get("bytes") or hashlib.sha256(body).hexdigest() != expected.get("sha256"):
                raise ProjectFormatError(f"Нарушена целостность: {name}")
            bodies[name] = json.loads(body)
    data = bodies["project.json"]
    return Project(
        id=data["id"], name=data["name"], profile_name=data.get("profile_name", "Основной"), profile=Profile(data["profile"]),
        scheme_number=data.get("scheme_number"), scheme_variant=data.get("scheme_variant"),
        selected_soils=[int(x) for x in data.get("selected_soils", [])],
        foundations=[FoundationInput(
            number=int(f["number"]), kind=FoundationKind(f["kind"]),
            width=Quantity.from_dict(f["width"]) if f.get("width") else None,
            length=Quantity.from_dict(f["length"]) if f.get("length") else None,
            depth=Quantity.from_dict(f["depth"]) if f.get("depth") else None,
            auto_size=bool(f.get("auto_size", True)),
        ) for f in data.get("foundations", [])],
        layers=[GeologyLayer(x["id"], int(x["soil_number"]), Decimal(x["top_m"]), Decimal(x["bottom_m"])) for x in data.get("layers", [])],
        geology_coordinate_mode=data.get("geology_coordinate_mode", "depth"),
        surface_elevation_m=Decimal(data["surface_elevation_m"]) if data.get("surface_elevation_m") is not None else None,
        groundwater_m=Decimal(data["groundwater_m"]) if data.get("groundwater_m") is not None else None,
        basement_enabled=bool(data.get("basement_enabled", False)),
        basement_height_m=Decimal(data["basement_height_m"]) if data.get("basement_height_m") is not None else None,
        catalog_snapshot=bodies["catalog_snapshot.json"],
        calculation_snapshot=bodies["calculation_snapshot.json"],
        calculation_runs=data.get("calculation_runs", {}),
        calculation_settings=data.get("calculation_settings", {}),
        report_settings=bodies["report_settings.json"],
        unit_conversions=UnitConversions.from_dict(data.get("unit_conversions")),
        created_at=data["created_at"],
    )
