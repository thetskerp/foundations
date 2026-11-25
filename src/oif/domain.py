"""Предметные модели с явным происхождением величин."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from .units import Quantity, UnitConversions


class Profile(StrEnum):
    LECTURE_HC_02 = "lecture_hc_02"
    SP_HC_05_LECTURE_SETTLEMENT = "sp_hc_05_lecture_settlement"


class FoundationKind(StrEnum):
    PAD = "pad"
    STRIP = "strip"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Origin(StrEnum):
    USER = "user"
    SOIL_CATALOG = "soil_catalog"
    SCHEME = "scheme"
    LOAD_TABLE = "load_table"
    STANDARD = "standard"
    INTERPOLATION = "interpolation"
    CALCULATED = "calculated"
    OVERRIDE = "override"


@dataclass(frozen=True)
class SourceRef:
    document: str
    edition: str
    location: str
    sha256: str | None = None


@dataclass(frozen=True)
class Override:
    original: Quantity
    replacement: Quantity
    reason: str
    changed_at: str
    author: str | None = None


@dataclass(frozen=True)
class ValueNode:
    id: str
    name: str
    symbol: str
    quantity: Quantity
    origin: Origin
    source: SourceRef | None = None
    formula: str | None = None
    substitution: str | None = None
    dependencies: tuple[str, ...] = ()
    applicability: str | None = None
    warnings: tuple[str, ...] = ()
    override: Override | None = None


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class Soil:
    number: int
    name: str
    geological_index: str
    rho_ii: Quantity
    phi_ii: Quantity
    c_ii: Quantity | None
    elastic_modulus: Quantity
    particle_density: Quantity
    water_content: Decimal
    liquid_limit: Decimal | None
    plastic_limit: Decimal | None
    source: SourceRef
    version: int = 1


@dataclass(frozen=True)
class LoadCase:
    scheme_number: int
    variant: str
    foundation_number: int
    combination: int
    vertical: Quantity
    moment: Quantity | None
    horizontal: Quantity | None
    source: SourceRef


@dataclass(frozen=True)
class GeologyLayer:
    id: str
    soil_number: int
    top_m: Decimal
    bottom_m: Decimal

    def __post_init__(self) -> None:
        if self.top_m >= self.bottom_m:
            raise ValueError("Глубина подошвы слоя должна быть больше глубины его кровли")


def normalize_geology_layers(rows: list[tuple[str, int, Decimal, Decimal]], coordinate_mode: str,
                             surface_elevation_m: Decimal | None = None) -> tuple[list[GeologyLayer], Decimal | None]:
    """Преобразовать ввод в единую внутреннюю систему глубин от поверхности."""
    if coordinate_mode == "depth":
        return [GeologyLayer(layer_id, soil_number, top, bottom)
                for layer_id, soil_number, top, bottom in rows], None
    if coordinate_mode != "elevation":
        raise ValueError("Неизвестная система координат геологического разреза")
    max_top = max((top for _, _, top, _ in rows), default=Decimal(0))
    surface = surface_elevation_m if surface_elevation_m is not None else max_top
    if rows and surface < max_top:
        raise ValueError(
            f"Отметка поверхности земли {surface} м ниже кровли верхнего слоя {max_top} м. "
            f"Для этого разреза укажите {max_top} м или оставьте поле пустым; отметка подошвы задаётся глубиной фундамента."
        )
    if rows and surface > max_top:
        raise ValueError(
            f"Между поверхностью {surface} м и верхним слоем {max_top} м нет грунта. "
            f"Добавьте недостающий слой либо укажите отметку поверхности {max_top} м."
        )
    layers = []
    for layer_id, soil_number, top, bottom in rows:
        if top <= bottom:
            raise ValueError(
                "При абсолютных отметках отметка кровли слоя должна быть больше отметки его подошвы"
            )
        layers.append(GeologyLayer(layer_id, soil_number, surface - top, surface - bottom))
    return layers, surface


@dataclass(frozen=True)
class FoundationInput:
    number: int
    kind: FoundationKind
    width: Quantity | None = None
    length: Quantity | None = None
    depth: Quantity | None = None
    auto_size: bool = True


@dataclass
class Project:
    name: str
    profile_name: str = "Основной"
    profile: Profile = Profile.LECTURE_HC_02
    id: str = field(default_factory=lambda: str(uuid4()))
    scheme_number: int | None = None
    scheme_variant: str | None = None
    selected_soils: list[int] = field(default_factory=list)
    foundations: list[FoundationInput] = field(default_factory=list)
    layers: list[GeologyLayer] = field(default_factory=list)
    geology_coordinate_mode: str = "depth"
    surface_elevation_m: Decimal | None = None
    groundwater_m: Decimal | None = None
    basement_enabled: bool = False
    basement_height_m: Decimal | None = None
    catalog_snapshot: dict = field(default_factory=dict)
    calculation_snapshot: dict | None = None
    calculation_runs: dict = field(default_factory=dict)
    calculation_settings: dict = field(default_factory=dict)
    report_settings: dict = field(default_factory=dict)
    unit_conversions: UnitConversions = field(default_factory=UnitConversions)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_ready_for_calculation(self) -> bool:
        basement_ready = not self.basement_enabled or self.basement_height_m is not None
        return bool(self.scheme_number and self.scheme_variant and self.selected_soils and self.foundations and self.layers and basement_ready)
