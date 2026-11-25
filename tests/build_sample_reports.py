"""Создание контрольных файлов экспорта для визуальной проверки."""

from decimal import Decimal
from pathlib import Path

from oif.catalog import Catalog
from oif.domain import FoundationInput, FoundationKind, GeologyLayer, Project
from oif.project_io import input_fingerprint
from oif.reports.catalog_export import export_catalog_pdf
from oif.reports.excel import export_excel
from oif.reports.word import export_word
from oif.seed import install_pilot_catalog
from oif.shallow import ShallowFoundationCalculator, ShallowOptions
from oif.units import Quantity


def main() -> None:
    directory = Path("tmp/report-qa")
    directory.mkdir(parents=True, exist_ok=True)
    catalog = Catalog(directory / "catalog.sqlite")
    install_pilot_catalog(catalog)
    project = Project("Монтажный цех: контрольный пример", scheme_number=18, scheme_variant="even", selected_soils=[29],
        foundations=[FoundationInput(3, FoundationKind.PAD, Quantity.of(3, "m"), Quantity.of(3, "m"), Quantity.of(2, "m"))],
        layers=[GeologyLayer("layer-1", 29, Decimal(0), Decimal(20))],
        calculation_settings={"source": "контрольный пример"})
    options = ShallowOptions(combination=1, rigid_scheme=False, length_height_ratio=None,
        sand_moisture=None, loose_sand=False, strength_from_tests=True,
        moment_at_base=Quantity.of(63, "tf*m"), moment_basis="Момент из задания, без переноса T",
        foundation_unit_weight=Quantity.of(24, "kN/m3"), gamma_below_base=Quantity.of(20, "kN/m3"),
        groundwater_absent=True, submerged_gamma_by_soil={})
    project.calculation_snapshot = ShallowFoundationCalculator(catalog).calculate(project, 3, options).as_snapshot()
    project.calculation_snapshot["input_hash"] = input_fingerprint(project)
    export_word(project, directory / "Контрольный_отчёт.docx")
    export_excel(project, directory / "Контрольная_книга.xlsx")
    export_catalog_pdf(catalog, directory / "Справочник_грунтов.pdf")
    print(directory)


if __name__ == "__main__":
    main()
