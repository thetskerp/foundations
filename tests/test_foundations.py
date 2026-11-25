import tempfile
import json
import unittest
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from oif.catalog import Catalog, CatalogError
from oif.catalog_io import export_catalog, import_catalog
from oif.domain import FoundationInput, FoundationKind, GeologyLayer, Profile, Project, normalize_geology_layers
from oif.project_io import ProjectFormatError, input_fingerprint, load_project, project_workspace_paths, save_project
from oif.seed import SOILS, SCHEMES, LOADS, install_pilot_catalog
from oif.application import preliminary_for_foundation
from oif.standards.r0 import R0SelectionError, preliminary_area, r0_for_clay, r0_from_soil_record
from oif.standards.resistance import ResistanceInputs, base_pressure, basement_reduced_depth, m_coefficients, resistance
from oif.standards.working_conditions import select_working_conditions, WorkingConditionsError
from oif.standards.alpha import AlphaSelectionError, alpha
from oif.settlement import SettlementSoilLayer, calculate_settlement
from oif.hc import HcSearchMode, StressLayer, find_hc
from oif.shallow import ShallowFoundationCalculator, ShallowOptions, ShallowInputError
from oif.sizing import auto_size_area, preliminary_geometry, SizingError
from oif.catalog_snapshot import ProjectCatalog
from oif.reports.excel import export_excel
from oif.reports.word import export_word
from oif.reports.common import ReportError, included_sections
from oif.soil_properties import calculate_soil_properties
from oif.units import Quantity, UnitConversions, UnitError, unit_weight_from_density


class UnitsTests(unittest.TestCase):
    def test_conversions_and_rejection(self):
        self.assertEqual(Quantity.of(1, "MPa").to("kPa").value, 1000)
        self.assertEqual(Quantity.of(1, "tf").to("kN").value, Decimal("9.80665"))
        self.assertEqual(unit_weight_from_density(Quantity.of("2", "g/cm3")).value, Decimal("19.61330"))
        rounded = UnitConversions(tf_to_kn=Decimal(10), gravity_m_s2=Decimal(10))
        self.assertEqual(Quantity.of(1, "tf").to("kN", rounded).value, Decimal(10))
        self.assertEqual(Quantity.of(2, "tf*m").to("kN*m", rounded).value, Decimal(20))
        self.assertEqual(unit_weight_from_density(Quantity.of("2", "g/cm3"), conversions=rounded).value, Decimal(20))
        with self.assertRaises(UnitError):
            Quantity.of(1, "m").to("kPa")
        with self.assertRaises(UnitError):
            Quantity.of(1, "unknown")


class StorageTests(unittest.TestCase):
    def test_project_workspace_is_named_by_object_and_profile(self):
        folder, project_file = project_workspace_paths("/tmp", "Цех: 18", "Рената/2")
        self.assertEqual(folder.name, "Цех_ 18 — Рената_2")
        self.assertEqual(project_file.parent, folder)
        self.assertEqual(project_file.suffix, ".oifproj")

    def test_absolute_elevations_are_converted_to_depths(self):
        layers, surface = normalize_geology_layers([
            ("layer-1", 29, Decimal("130"), Decimal("124")),
            ("layer-2", 40, Decimal("124"), Decimal("118")),
            ("layer-3", 81, Decimal("118"), Decimal("110")),
        ], "elevation")
        self.assertEqual(surface, Decimal("130"))
        self.assertEqual([(layer.top_m, layer.bottom_m) for layer in layers], [
            (Decimal("0"), Decimal("6")),
            (Decimal("6"), Decimal("12")),
            (Decimal("12"), Decimal("20")),
        ])
        with self.assertRaisesRegex(ValueError, "абсолютных отмет"):
            normalize_geology_layers([("layer-1", 29, Decimal("124"), Decimal("130"))], "elevation")
        with self.assertRaisesRegex(ValueError, "укажите 126"):
            normalize_geology_layers([("layer-1", 39, Decimal("126"), Decimal("122"))], "elevation", Decimal("123.5"))

    def test_custom_report_sections_require_parents(self):
        project = Project("Отчёт", report_settings={"sections": ["pressure"]})
        with self.assertRaises(ReportError):
            included_sections(project, "custom")
        project.report_settings = {"sections": ["input", "results", "pressure"]}
        self.assertEqual(included_sections(project, "custom"), ("input", "results", "pressure"))

    def test_v1_project_migrates_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.oifproj"
            old = Path(directory) / "v1.oifproj"
            save_project(Project("Миграция", calculation_settings={"step": "0.2"}), path)
            with ZipFile(path) as archive:
                bodies = {name: archive.read(name) for name in archive.namelist()}
            manifest = json.loads(bodies["manifest.json"])
            manifest["schema_version"] = 1
            project = json.loads(bodies["project.json"])
            project.pop("calculation_settings")
            project.pop("calculation_runs")
            bodies["project.json"] = json.dumps(project, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            import hashlib
            manifest["members"]["project.json"] = {"sha256": hashlib.sha256(bodies["project.json"]).hexdigest(), "bytes": len(bodies["project.json"])}
            bodies["manifest.json"] = json.dumps(manifest).encode()
            with ZipFile(old, "w", ZIP_DEFLATED) as archive:
                for name, body in bodies.items():
                    archive.writestr(name, body)
            self.assertEqual(load_project(old).calculation_settings, {})
            self.assertEqual(load_project(path).calculation_settings, {"step": "0.2"})

    def test_project_round_trip_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Пример.oifproj"
            project = Project("Схема 18", profile_name="Рената", profile=Profile.LECTURE_HC_02, scheme_number=18, scheme_variant="even", selected_soils=[29, 40, 81], foundations=[FoundationInput(3, FoundationKind.PAD, Quantity.of("2.5", "m"), Quantity.of("2.5", "m"), Quantity.of("2", "m"))], layers=[GeologyLayer("a", 29, Decimal(0), Decimal(3))], geology_coordinate_mode="elevation", surface_elevation_m=Decimal("130"), basement_enabled=True, basement_height_m=Decimal("1.5"), unit_conversions=UnitConversions(tf_to_kn=Decimal(10)))
            save_project(project, path)
            restored = load_project(path)
            self.assertEqual(restored.foundations[0].width.value, Decimal("2.5"))
            self.assertTrue(restored.basement_enabled)
            self.assertEqual(restored.basement_height_m, Decimal("1.5"))
            self.assertEqual(restored.geology_coordinate_mode, "elevation")
            self.assertEqual(restored.surface_elevation_m, Decimal("130"))
            self.assertEqual(restored.profile_name, "Рената")
            self.assertEqual(restored.unit_conversions.tf_to_kn, Decimal(10))
            self.assertTrue(restored.is_ready_for_calculation)
            with ZipFile(path, "a") as archive:
                archive.writestr("unexpected.txt", "bad")
            with self.assertRaises(ProjectFormatError):
                load_project(path)

    def test_catalog_immutability_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / "catalog.sqlite")
            install_pilot_catalog(catalog)
            load = catalog.get("load", "18:even:3:1")
            self.assertEqual(load["data"]["N"]["value"], "235")
            self.assertEqual(len(catalog.list("load")), 516)
            self.assertEqual(len(catalog.list("scheme")), 25)
            self.assertEqual(catalog.get("scheme", "18")["data"]["name"], "Монтажный цех")
            self.assertEqual(catalog.get("soil", "104")["data"]["name"], "Песчаник")
            self.assertEqual(catalog.get("soil", "104")["data"]["rc_mpa"], "10")
            self.assertEqual(catalog.get("soil", "105")["data"]["rc_mpa"], "12")
            service_sand = catalog.get("soil", "0")
            self.assertEqual(service_sand["data"]["name"], "Песок")
            self.assertEqual(service_sand["data"]["reference_soil_number"], 62)
            self.assertEqual(service_sand["data"]["e_mpa"], "40")
            self.assertEqual(catalog.get("load", "8:odd:4:2")["data"]["N"]["value"], LOADS["8:odd:4:2"]["N"]["value"])
            self.assertTrue(all(files("oif").joinpath(f"data/schemes/{number}.png").is_file() for number in range(1, 26)))
            catalog.refresh_builtin("scheme", "18", 1, {"name": "устаревшее"}, "старый каталог")
            catalog.refresh_builtin("soil", "29", 1, SOILS[29], "старый источник")
            install_pilot_catalog(catalog)
            self.assertEqual(catalog.get("scheme", "18")["data"]["name"], "Монтажный цех")
            self.assertNotEqual(catalog.get("soil", "29")["source"], "старый источник")
            with self.assertRaises(CatalogError):
                catalog.put("soil", "29", 2, {"name": "changed"}, "test")
            catalog.put("soil", "900", 1, SOILS[29], "пользовательский грунт")
            self.assertEqual(catalog.delete_user_record("soil", "900"), 1)
            self.assertIsNone(catalog.get("soil", "900"))
            with self.assertRaises(CatalogError):
                catalog.delete_user_record("soil", "29")
            archive = Path(directory) / "pilot.oifcatalog"
            export_catalog(catalog, archive, author="test")
            other = Catalog(Path(directory) / "other.sqlite")
            self.assertEqual(import_catalog(archive, other)["added"], len(SOILS) + len(SCHEMES) + len(LOADS))
            self.assertEqual(other.get("soil", "81")["data"]["e_mpa"], "14")


class PreliminaryTests(unittest.TestCase):
    def test_preliminary_geometry_rounds_up_and_preserves_fixed_side(self):
        square = preliminary_geometry(Quantity.of("5.13", "m2"), FoundationKind.PAD)
        self.assertEqual((square.width.value, square.length.value), (Decimal("2.3"), Decimal("2.3")))
        pad = preliminary_geometry(Quantity.of("5.13", "m2"), FoundationKind.PAD, width=Quantity.of(2, "m"))
        self.assertEqual((pad.width.value, pad.length.value), (Decimal(2), Decimal("2.6")))
        strip = preliminary_geometry(Quantity.of("5.13", "m2"), FoundationKind.STRIP, length=Quantity.of(4, "m"))
        self.assertEqual((strip.width.value, strip.length.value), (Decimal("5.2"), Decimal(1)))
        self.assertTrue(all(result.area.value >= Decimal("5.13") for result in (square, pad, strip)))

    def test_full_soil_calculation_matches_control_sheet(self):
        properties = calculate_soil_properties(SOILS[29])
        self.assertAlmostEqual(float(properties.dry_density_g_cm3), 1.62601626, places=7)
        self.assertAlmostEqual(float(properties.void_ratio), 0.66665, places=5)
        self.assertEqual(properties.plasticity_index, Decimal("0.15"))
        self.assertEqual(properties.liquidity_index, Decimal("0.2"))
        self.assertEqual(properties.beta, Decimal("0.57"))

    def test_table_selection_and_no_extrapolation(self):
        self.assertEqual(r0_for_clay("Суглинок", Decimal("0.5"), Decimal(0)).value, 350)
        self.assertEqual(r0_for_clay("Суглинок", Decimal("0.7"), Decimal(1)).value, 180)
        self.assertEqual(r0_for_clay("Суглинок", Decimal("0.6"), Decimal("0.5")).value, Decimal("257.5"))
        with self.assertRaises(R0SelectionError):
            r0_for_clay("Суглинок", Decimal("1.2"), Decimal("0.5"))
        with self.assertRaises(R0SelectionError):
            r0_from_soil_record({"name": "Песок пылеватый"})
        self.assertEqual(r0_from_soil_record({"name": "Песок крупный"}, sand_density="dense").value, 600)
        self.assertEqual(r0_from_soil_record({"name": "Песок средней крупности"}, sand_density="medium").value, 400)
        with self.assertRaises(R0SelectionError):
            r0_from_soil_record({"name": "Песок"}, sand_density="dense", sand_moisture="low")
        self.assertEqual(preliminary_area(Quantity.of(235, "tf"), Quantity.of(20, "tf/m2"),
                                          Quantity.of(2, "m"), Quantity.of(2, "tf/m3")).value, Decimal("14.6875"))

    def test_scheme_18_preliminary_area(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / "catalog.sqlite")
            install_pilot_catalog(catalog)
            project = Project("Контроль", scheme_number=18, scheme_variant="even", selected_soils=[29], foundations=[FoundationInput(3, FoundationKind.PAD, depth=Quantity.of(2, "m"))], layers=[GeologyLayer("layer-1", 29, Decimal(0), Decimal(3))])
            result = preliminary_for_foundation(project, catalog, 3, mean_unit_weight=Quantity.of(24, "kN/m3"))
            self.assertEqual(result.soil_number, 29)
            self.assertEqual(result.load_key, "18:even:3:1")
            self.assertIsNotNone(result.area)
            self.assertGreater(result.area.value, 0)


class ResistanceTests(unittest.TestCase):
    def test_basement_reduced_depth_and_db_cap(self):
        d1, db = basement_reduced_depth(base_depth=Quantity.of("3.5", "m"), floor_depth=Quantity.of("3", "m"),
            soil_height=Quantity.of("0.3", "m"), floor_thickness=Quantity.of("0.2", "m"),
            floor_unit_weight=Quantity.of(20, "kN/m3"), gamma_above=Quantity.of(20, "kN/m3"))
        self.assertEqual((d1.value, db.value), (Decimal("0.5"), Decimal(2)))
        with self.assertRaisesRegex(ValueError, "d ="):
            basement_reduced_depth(base_depth=Quantity.of(3, "m"), floor_depth=Quantity.of(2, "m"),
                soil_height=Quantity.of("0.3", "m"), floor_thickness=Quantity.of("0.2", "m"),
                floor_unit_weight=Quantity.of(20, "kN/m3"), gamma_above=Quantity.of(20, "kN/m3"))

    def test_working_conditions_table_54(self):
        clay = select_working_conditions(soil_name="Суглинок", liquidity_index=Decimal("0.2"), sand_moisture=None, rigid_scheme=True, length_height_ratio=Decimal("2.75"))
        self.assertEqual((clay.gamma_c1, clay.gamma_c2), (Decimal("1.25"), Decimal("1.05")))
        flexible = select_working_conditions(soil_name="Суглинок", liquidity_index=Decimal("0.2"), sand_moisture=None, rigid_scheme=False)
        self.assertEqual(flexible.gamma_c2, 1)
        with self.assertRaises(WorkingConditionsError):
            select_working_conditions(soil_name="Песок пылеватый", liquidity_index=None, sand_moisture=None, rigid_scheme=False)

    def test_formula_and_table_node(self):
        self.assertEqual(m_coefficients(Quantity.of(19, "deg")), (Decimal("0.47"), Decimal("2.89"), Decimal("5.48")))
        result = resistance(ResistanceInputs(
            phi_ii=Quantity.of(19, "deg"), cohesion_ii=Quantity.of(30, "kPa"),
            width=Quantity.of(2, "m"), gamma_below=Quantity.of(20, "kN/m3"),
            gamma_above=Quantity.of(20, "kN/m3"), d1=Quantity.of("0.5", "m"),
            basement_depth=Quantity.of("1.5", "m"), gamma_c1=Decimal("1.25"),
            gamma_c2=Decimal(1), k=Decimal(1)))
        self.assertEqual(result.value, Decimal("336.00000"))
        workbook = resistance(ResistanceInputs(
            phi_ii=Quantity.of(19, "deg"), cohesion_ii=Quantity.of(30, "kPa"),
            width=Quantity.of("3.832427429", "m"), gamma_below=Quantity.of(20, "kN/m3"),
            gamma_above=Quantity.of(20, "kN/m3"), d1=Quantity.of("0.5", "m"),
            basement_depth=Quantity.of("1.5", "m"), gamma_c1=Decimal("1.25"),
            gamma_c2=Decimal(1), k=Decimal(1)))
        self.assertAlmostEqual(float(workbook.value), 357.5310223, places=7)

    def test_edge_pressure_and_uplift(self):
        p = base_pressure(Quantity.of(1000, "kN"), Quantity.of(0, "kN*m"), Quantity.of(2, "m"), Quantity.of(3, "m"), Quantity.of(2, "m"), Quantity.of(20, "kN/m3"), r=Quantity.of(300, "kPa"))
        self.assertEqual(p.edge_min.value, p.edge_max.value)
        self.assertFalse(p.uplift)
        p2 = base_pressure(Quantity.of(1000, "kN"), Quantity.of(1000, "kN*m"), Quantity.of(2, "m"), Quantity.of(3, "m"), Quantity.of(2, "m"), Quantity.of(20, "kN/m3"))
        self.assertTrue(p2.uplift)
        self.assertIsNone(p2.edge_max)

    def test_strip_uses_width_for_kern_and_section_modulus(self):
        p = base_pressure(Quantity.of(1000, "kN"), Quantity.of(200, "kN*m"), Quantity.of(2, "m"),
            Quantity.of(1, "m"), Quantity.of(1, "m"), Quantity.of(20, "kN/m3"), kind=FoundationKind.STRIP)
        self.assertEqual(p.kern_dimension.value, Decimal(2))
        self.assertEqual(p.kern_limit.value, Decimal(2) / 6)
        self.assertFalse(p.uplift)
        with self.assertRaisesRegex(ValueError, "длина должна быть 1"):
            base_pressure(Quantity.of(1000, "kN"), Quantity.of(0, "kN*m"), Quantity.of(2, "m"),
                Quantity.of(2, "m"), Quantity.of(1, "m"), Quantity.of(20, "kN/m3"), kind=FoundationKind.STRIP)

    def test_auto_area_step_and_checks(self):
        result = auto_size_area(vertical=Quantity.of(1000, "kN"), moment_at_base=Quantity.of(1000, "kN*m"),
            width=Quantity.of(2, "m"), initial_length=Quantity.of(2, "m"), depth=Quantity.of(2, "m"),
            foundation_unit_weight=Quantity.of(20, "kN/m3"), resistance=Quantity.of(400, "kPa"))
        self.assertEqual(result.area.value * 10, (result.area.value * 10).to_integral_value())
        self.assertFalse(result.pressure.uplift)
        self.assertLessEqual(result.pressure.mean.value, 400)

    def test_complete_shallow_run_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / "catalog.sqlite")
            install_pilot_catalog(catalog)
            project = Project("Расчёт", scheme_number=18, scheme_variant="even", selected_soils=[29],
                foundations=[FoundationInput(3, FoundationKind.PAD, Quantity.of(3, "m"), Quantity.of(3, "m"), Quantity.of(2, "m"))],
                layers=[GeologyLayer("layer-1", 29, Decimal(0), Decimal(20))])
            options = ShallowOptions(combination=1, rigid_scheme=False, length_height_ratio=None,
                sand_moisture=None, loose_sand=False, strength_from_tests=True,
                moment_at_base=Quantity.of(63, "tf*m"), moment_basis="M из задания; T не переносили",
                foundation_unit_weight=Quantity.of(24, "kN/m3"), gamma_below_base=Quantity.of(20, "kN/m3"),
                groundwater_absent=True, submerged_gamma_by_soil={})
            result = ShallowFoundationCalculator(catalog).calculate(project, 3, options)
            self.assertGreater(result.resistance.value, 0)
            self.assertGreater(result.settlement.total.value, 0)
            rounded_project = Project("Расчёт 10", scheme_number=18, scheme_variant="even", selected_soils=[29],
                foundations=list(project.foundations), layers=list(project.layers),
                unit_conversions=UnitConversions(tf_to_kn=Decimal(10)))
            rounded_result = ShallowFoundationCalculator(catalog).calculate(rounded_project, 3, options)
            self.assertGreater(rounded_result.pressure.mean.value, result.pressure.mean.value)
            self.assertIn("1 тс = 10 кН", rounded_result.warnings[0])
            self.assertEqual(result.as_snapshot()["formulas"]["s"], "Σ 0,8·σzp,i·hi/Ei")
            self.assertIn("moment_basis", result.as_snapshot()["inputs"])
            automatic = ShallowFoundationCalculator(catalog).calculate(
                project, 3, ShallowOptions(**{**options.__dict__, "gamma_below_base": None}))
            self.assertEqual(Decimal(automatic.inputs["gamma_below_base"]["value"]), Decimal("19.6133"))
            self.assertEqual(automatic.inputs["gamma_below_base_mode"], "автоматически, средневзвешенное по п. 5.6.10")
            self.assertEqual(len(automatic.inputs["R_parameters"]), 13)
            self.assertEqual(automatic.inputs["R_parameters"][0]["symbol"], "γc1")
            basement = ShallowOptions(**{**options.__dict__, "basement_depth": Quantity.of("1.5", "m"),
                "basement_soil_height": Quantity.of("0.3", "m"),
                "basement_floor_thickness": Quantity.of("0.2", "m"),
                "basement_floor_unit_weight": Quantity.of(20, "kN/m3")})
            basement_result = ShallowFoundationCalculator(catalog).calculate(project, 3, basement)
            self.assertEqual(basement_result.inputs["db"]["value"], "1.5")
            self.assertNotEqual(basement_result.resistance.value, result.resistance.value)
            with self.assertRaisesRegex(ShallowInputError, "толщину слоя грунта над подошвой.*hs"):
                ShallowFoundationCalculator(catalog).calculate(project, 3, ShallowOptions(**{**options.__dict__, "basement_depth": Quantity.of("1.5", "m")}))
            with self.assertRaisesRegex(ShallowInputError, "Уровень грунтовых вод.*УГВ.*неизвестен"):
                ShallowFoundationCalculator(catalog).calculate(project, 3, ShallowOptions(**{**options.__dict__, "groundwater_absent": False}))
            with self.assertRaisesRegex(ShallowInputError, "происхождение характеристик прочности"):
                ShallowFoundationCalculator(catalog).calculate(project, 3, ShallowOptions(**{**options.__dict__, "strength_from_tests": None}))
            with self.assertRaisesRegex(ShallowInputError, "конструктивную схему"):
                ShallowFoundationCalculator(catalog).calculate(project, 3, ShallowOptions(**{**options.__dict__, "rigid_scheme": None}))
            project.catalog_snapshot = {"soils": {"29": catalog.get("soil", "29")}, "loads": {"18:even:3:1": catalog.get("load", "18:even:3:1")}, "scheme": catalog.get("scheme", "18")}
            path = Path(directory) / "portable.oifproj"
            project.calculation_snapshot = result.as_snapshot()
            project.calculation_snapshot["input_hash"] = input_fingerprint(project)
            save_project(project, path)
            restored = load_project(path)
            empty = Catalog(Path(directory) / "empty.sqlite")
            rerun = ShallowFoundationCalculator(ProjectCatalog(restored, empty)).calculate(restored, 3, options)
            self.assertEqual(rerun.resistance.value, result.resistance.value)
            docx = Path(directory) / "report.docx"
            xlsx = Path(directory) / "report.xlsx"
            export_word(restored, docx)
            export_excel(restored, xlsx)
            from openpyxl import load_workbook
            from docx import Document
            workbook = load_workbook(xlsx, read_only=True)
            self.assertEqual(workbook.sheetnames, ["01 Результат", "02 Исходные данные", "03 Грунты", "04 Расчёт R", "05 Осадка", "06 Примечания"])
            self.assertAlmostEqual(workbook["01 Результат"]["B8"].value, float(result.resistance.value))
            self.assertLessEqual(workbook["03 Грунты"].max_column, 5)
            self.assertLessEqual(workbook["04 Расчёт R"].max_column, 4)
            r_values = [workbook["04 Расчёт R"].cell(row, 2).value for row in range(1, workbook["04 Расчёт R"].max_row + 1)]
            self.assertIn("Формулы и подстановки", r_values)
            self.assertIn("Коэффициенты и величины формулы R", r_values)
            settlement_sheet = workbook["05 Осадка"]
            settlement_rows = [
                [settlement_sheet.cell(row, column).value for column in range(2, 15)]
                for row in range(1, settlement_sheet.max_row + 1)
            ]
            settlement_header = next(values for values in settlement_rows if values[0] == "Вид грунта")
            self.assertEqual(settlement_header[1:6], ["zᵢ, м", "hᵢ, м", "ξ = 2z/b", "α", "σzp,i, кПа"])
            self.assertEqual(settlement_header[-3:], ["σzg,i, кПа", "Eᵢ, МПа", "Δsᵢ, мм"])
            self.assertTrue(any(isinstance(values[10], (int, float)) for values in settlement_rows))
            document_text = "\n".join(p.text for p in Document(docx).paragraphs) + "\n".join(c.text for t in Document(docx).tables for row in t.rows for c in row.cells)
            self.assertIn("382.456", document_text)
            self.assertIn("Коэффициенты и величины формулы R", document_text)
            self.assertIn("Формула или источник", document_text)
            self.assertIn("ρd = ρII / (1 + W)", document_text)
            self.assertIn("Δsᵢ = 0,8·σzp,i·hᵢ/Eᵢ", document_text)
            restored.report_settings = {"sections": ["input"]}
            brief_docx = Path(directory) / "input-only.docx"
            brief_xlsx = Path(directory) / "input-only.xlsx"
            export_word(restored, brief_docx, preset="custom")
            export_excel(restored, brief_xlsx, preset="custom")
            brief_book = load_workbook(brief_xlsx, read_only=True)
            self.assertEqual(brief_book["01 Результат"]["B8"].value, "—")
            self.assertNotIn("04 Расчёт R", brief_book.sheetnames)
            self.assertNotIn("Результаты", "\n".join(p.text for p in Document(brief_docx).paragraphs))
            self.assertIn("Ширина подошвы", "\n".join(c.text for t in Document(brief_docx).tables for row in t.rows for c in row.cells))
            restored.foundations = [FoundationInput(3, FoundationKind.PAD, Quantity.of(4, "m"), Quantity.of(3, "m"), Quantity.of(2, "m"))]
            with self.assertRaises(ReportError):
                export_excel(restored, xlsx)


class SettlementTests(unittest.TestCase):
    def test_alpha_nodes_and_no_extrapolation(self):
        self.assertEqual(alpha(Decimal("0.4"), FoundationKind.PAD, eta=Decimal(1)), Decimal("0.960"))
        self.assertEqual(alpha(Decimal("0.4"), FoundationKind.STRIP), Decimal("0.977"))
        between = alpha(Decimal("0.6"), FoundationKind.PAD, eta=Decimal("1.2"))
        self.assertGreater(between, Decimal("0.8"))
        self.assertLess(between, Decimal("0.96"))
        with self.assertRaises(AlphaSelectionError):
            alpha(Decimal("12.1"), FoundationKind.STRIP)

    def test_split_at_geology_and_groundwater(self):
        result = calculate_settlement(
            kind=FoundationKind.PAD, width=Quantity.of(2, "m"), length=Quantity.of(2, "m"),
            pressure=Quantity.of(200, "kPa"), base_depth=Quantity.of(1, "m"), h_c=Quantity.of(2, "m"),
            soils=[SettlementSoilLayer(29, Decimal(0), Decimal("2.1"), Quantity.of(10, "MPa")), SettlementSoilLayer(40, Decimal("2.1"), Decimal(4), Quantity.of(11, "MPa"))],
            groundwater_m=Decimal("1.6"), step_fraction=Decimal("0.4"))
        self.assertGreater(result.total.value, 0)
        self.assertEqual(result.layers[0].bottom_m, Decimal("1.6"))
        self.assertIn(Decimal("2.1"), [layer.bottom_m for layer in result.layers])
        self.assertEqual(result.layers[-1].bottom_m, Decimal(3))
        self.assertTrue(all(layer.bottom_m - layer.top_m <= Decimal("0.8") for layer in result.layers))

    def test_layer_stress_is_average_at_top_and_bottom(self):
        result = calculate_settlement(
            kind=FoundationKind.PAD, width=Quantity.of(2, "m"), length=Quantity.of(2, "m"),
            pressure=Quantity.of(200, "kPa"), base_depth=Quantity.of(1, "m"), h_c=Quantity.of("0.8", "m"),
            soils=[SettlementSoilLayer(29, Decimal(0), Decimal(5), Quantity.of(10, "MPa"))],
            step_fraction=Decimal("0.4"),
            geostatic_stress_at=lambda depth: Quantity(depth.to("m").value * Decimal(20), "kPa"))
        layer = result.layers[0]
        expected_alpha = (alpha(Decimal(0), FoundationKind.PAD, eta=Decimal(1))
                          + alpha(Decimal("0.8"), FoundationKind.PAD, eta=Decimal(1))) / 2
        self.assertEqual(layer.alpha_value, expected_alpha)
        self.assertEqual(layer.sigma_zp.value, expected_alpha * Decimal(200))
        self.assertEqual(layer.sigma_zg_top.value, Decimal(20))
        self.assertEqual(layer.sigma_zg_bottom.value, Decimal(36))
        self.assertEqual(layer.sigma_zy_top.value, Decimal(20))
        self.assertEqual(layer.sigma_zy_bottom.value,
                         alpha(Decimal("0.8"), FoundationKind.PAD, eta=Decimal(1)) * Decimal(36))
        self.assertEqual(layer.stress_difference.value,
                         layer.sigma_zp.value - layer.sigma_zy_average.value)
        self.assertEqual(layer.settlement.value,
                         Decimal("0.8") * expected_alpha * Decimal(200) * Decimal("0.8") / Decimal(10000))

    def test_hc_profile_and_explicit_search_mode(self):
        args = dict(kind=FoundationKind.PAD, width=Quantity.of(2, "m"), length=Quantity.of(2, "m"), pressure=Quantity.of(200, "kPa"), base_depth=Quantity.of(1, "m"), layers=[StressLayer(29, Decimal(0), Decimal(20), Quantity.of(20, "kN/m3"))], groundwater_m=None, grid_step=Quantity.of("0.4", "m"))
        study = find_hc(profile=Profile.LECTURE_HC_02, mode=HcSearchMode.FIRST_GRID_POINT, **args)
        sp = find_hc(profile=Profile.SP_HC_05_LECTURE_SETTLEMENT, mode=HcSearchMode.FIRST_GRID_POINT, **args)
        crossing = find_hc(profile=Profile.LECTURE_HC_02, mode=HcSearchMode.LINEAR_CROSSING, **args)
        self.assertGreater(study.depth.value, sp.depth.value)
        self.assertLessEqual(crossing.depth.value, study.depth.value)
        self.assertEqual(study.threshold, Decimal("0.2"))

    def test_weak_layer_requires_verified_modulus(self):
        args = dict(profile=Profile.SP_HC_05_LECTURE_SETTLEMENT, mode=HcSearchMode.FIRST_GRID_POINT, kind=FoundationKind.PAD, width=Quantity.of(2, "m"), length=Quantity.of(2, "m"), pressure=Quantity.of(200, "kPa"), base_depth=Quantity.of(1, "m"), groundwater_m=None, grid_step=Quantity.of("0.4", "m"), weak_layer_selected=True)
        with self.assertRaisesRegex(ValueError, "E≤7"):
            find_hc(layers=[StressLayer(29, Decimal(0), Decimal(20), Quantity.of(20, "kN/m3"), modulus=Quantity.of(10, "MPa"))], **args)
        result = find_hc(layers=[StressLayer(29, Decimal(0), Decimal(3), Quantity.of(20, "kN/m3"), modulus=Quantity.of(10, "MPa")), StressLayer(40, Decimal(3), Decimal(5), Quantity.of(20, "kN/m3"), modulus=Quantity.of(5, "MPa")), StressLayer(81, Decimal(5), Decimal(20), Quantity.of(20, "kN/m3"), modulus=Quantity.of(10, "MPa"))], **args)
        self.assertGreaterEqual(result.depth.value, Decimal(4))
        self.assertEqual(result.threshold, Decimal("0.2"))


if __name__ == "__main__":
    unittest.main()
