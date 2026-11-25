"""Сценарий расчёта фундамента мелкого заложения без зависимостей от GUI."""

from dataclasses import dataclass
from decimal import Decimal

from .catalog import Catalog
from .domain import FoundationKind, Project
from .hc import HcResult, HcSearchMode, StressLayer, find_hc, geostatic_stress
from .settlement import SettlementResult, SettlementSoilLayer, calculate_settlement
from .soil_properties import calculate_soil_properties
from .standards.resistance import PressureResult, ResistanceInputs, base_pressure, basement_reduced_depth, m_coefficients, resistance
from .standards.working_conditions import WorkingConditions, select_working_conditions
from .units import Quantity, unit_weight_from_density


class ShallowInputError(ValueError):
    pass


@dataclass(frozen=True)
class ShallowOptions:
    combination: int
    rigid_scheme: bool | None
    length_height_ratio: Decimal | None
    sand_moisture: str | None
    loose_sand: bool
    strength_from_tests: bool | None
    moment_at_base: Quantity
    moment_basis: str
    foundation_unit_weight: Quantity
    gamma_below_base: Quantity | None
    groundwater_absent: bool
    submerged_gamma_by_soil: dict[int, Quantity]
    basement_depth: Quantity = Quantity.of(0, "m")
    basement_soil_height: Quantity | None = None
    basement_floor_thickness: Quantity | None = None
    basement_floor_unit_weight: Quantity | None = None
    hc_mode: HcSearchMode = HcSearchMode.FIRST_GRID_POINT
    hc_step_fraction: Decimal = Decimal("0.2")
    weak_layer_selected: bool = False


@dataclass(frozen=True)
class ShallowResult:
    foundation_number: int
    combination: int
    load_key: str
    resistance: Quantity
    pressure: PressureResult
    net_pressure: Quantity
    mean_pressure_ok: bool
    working_conditions: WorkingConditions
    hc: HcResult | None
    settlement: SettlementResult | None
    warnings: tuple[str, ...]
    sources: dict[str, str]
    inputs: dict
    substitutions: dict[str, str]
    soil_calculations: dict

    def as_snapshot(self) -> dict:
        def q(value: Quantity | None):
            return value.as_dict() if value is not None else None
        return {
            "foundation_number": self.foundation_number,
            "combination": self.combination,
            "load_key": self.load_key,
            "R": q(self.resistance),
            "pressure": {"mean": q(self.pressure.mean), "eccentricity": q(self.pressure.eccentricity), "edge_min": q(self.pressure.edge_min), "edge_max": q(self.pressure.edge_max), "uplift": self.pressure.uplift, "edge_limit_ok": self.pressure.edge_limit_ok, "kern_dimension": q(self.pressure.kern_dimension), "kern_limit": q(self.pressure.kern_limit)},
            "net_pressure": q(self.net_pressure),
            "mean_pressure_ok": self.mean_pressure_ok,
            "working_conditions": {"gamma_c1": str(self.working_conditions.gamma_c1), "gamma_c2": str(self.working_conditions.gamma_c2), "category": self.working_conditions.category},
            "hc": None if self.hc is None else {"depth": q(self.hc.depth), "threshold": str(self.hc.threshold), "mode": self.hc.mode.value, "points": [{"z_m": str(p.z_below_base_m), "sigma_zp_kpa": str(p.sigma_zp_kpa), "sigma_zg_kpa": str(p.sigma_zg_kpa)} for p in self.hc.points]},
            "settlement": None if self.settlement is None else {
                "total": q(self.settlement.total),
                "layers": [{
                    "soil": x.soil_number,
                    "top_m": str(x.top_m), "bottom_m": str(x.bottom_m),
                    "z_top_m": str(x.z_top_m), "z_bottom_m": str(x.z_bottom_m),
                    "xi_top": str(x.xi_top), "xi_bottom": str(x.xi_bottom),
                    "alpha_top": str(x.alpha_top), "alpha_bottom": str(x.alpha_bottom),
                    "alpha": str(x.alpha_value),
                    "sigma_zp_top": q(x.sigma_zp_top),
                    "sigma_zp_bottom": q(x.sigma_zp_bottom),
                    "sigma_zp": q(x.sigma_zp),
                    "sigma_zg_top": q(x.sigma_zg_top),
                    "sigma_zg_bottom": q(x.sigma_zg_bottom),
                    "sigma_zy_top": q(x.sigma_zy_top),
                    "sigma_zy_bottom": q(x.sigma_zy_bottom),
                    "sigma_zy_average": q(x.sigma_zy_average),
                    "stress_difference": q(x.stress_difference),
                    "modulus": q(x.modulus), "settlement": q(x.settlement),
                } for x in self.settlement.layers],
            },
            "warnings": list(self.warnings),
            "sources": self.sources,
            "inputs": self.inputs,
            "substitutions": self.substitutions,
            "soil_calculations": self.soil_calculations,
            "formulas": {"R": "γc1·γc2/k·(Mγ·kz·b·γII + Mq·d1·γ′II + (Mq−1)·db·γ′II + Mc·cII)", "p": "(N+γf·d·b·l)/(b·l)", "s": "Σ 0,8·σzp,i·hi/Ei"},
        }


class ShallowFoundationCalculator:
    id = "shallow"
    name = "Фундаменты мелкого заложения"
    input_schema = "Project + ShallowOptions"
    result_schema = "ShallowResult"
    screens = ("Геометрия", "Расчётное сопротивление", "Осадка", "Проверки", "Результат")
    report_sections = ("input", "R", "pressure", "settlement", "checks", "trace")

    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    def calculate(self, project: Project, foundation_number: int, options: ShallowOptions) -> ShallowResult:
        if len({foundation.number for foundation in project.foundations}) != len(project.foundations):
            raise ShallowInputError("Номера фундаментов в проекте повторяются")
        if len(set(project.selected_soils)) != len(project.selected_soils):
            raise ShallowInputError("Номера выбранных грунтов повторяются")
        foundation = next((f for f in project.foundations if f.number == foundation_number), None)
        if foundation is None or foundation.width is None or foundation.length is None or foundation.depth is None:
            raise ShallowInputError(
                "Для фундамента укажите тип, ширину подошвы (b), длину подошвы (l) и глубину заложения (d)"
            )
        b = foundation.width.to("m").value
        l = foundation.length.to("m").value
        d = foundation.depth.to("m").value
        if b <= 0 or l <= 0 or d < 0:
            raise ShallowInputError("Некорректная геометрия подошвы")
        if options.strength_from_tests is None:
            raise ShallowInputError(
                "Укажите происхождение характеристик прочности: угла внутреннего трения (φII) и удельного сцепления (cII)"
            )
        if options.rigid_scheme is None:
            raise ShallowInputError("Укажите конструктивную схему здания: гибкая или жёсткая")
        if not options.moment_basis.strip():
            raise ShallowInputError("Укажите обоснование изгибающего момента на уровне подошвы (M)")
        if project.groundwater_m is None and not options.groundwater_absent:
            raise ShallowInputError(
                "Уровень грунтовых вод (УГВ) неизвестен: задайте его глубину или подтвердите отсутствие воды"
            )
        if project.groundwater_m is not None and options.groundwater_absent:
            raise ShallowInputError("УГВ задан и одновременно отмечен отсутствующим")
        key = f"{project.scheme_number}:{project.scheme_variant}:{foundation_number}:{options.combination}"
        load = self.catalog.get("load", key)
        if load is None:
            raise ShallowInputError(f"Нет сочетания нагрузок {key}")
        layers = sorted(project.layers, key=lambda x: x.top_m)
        if not layers or layers[0].top_m != 0:
            raise ShallowInputError("Геология должна начинаться от поверхности")
        for left, right in zip(layers, layers[1:]):
            if left.bottom_m != right.top_m:
                raise ShallowInputError("В геологическом разрезе есть разрыв или пересечение")
        base_layers = [x for x in layers if x.top_m <= d < x.bottom_m]
        if len(base_layers) != 1:
            raise ShallowInputError("Подошва не привязана к единственному слою")
        soil_records = {}
        soil_calculations = {}
        stress_layers = []
        settlement_layers = []
        for layer in layers:
            if layer.soil_number not in project.selected_soils:
                raise ShallowInputError(f"Грунт №{layer.soil_number} в разрезе не включён в выбранные грунты")
            record = self.catalog.get("soil", str(layer.soil_number))
            if record is None:
                raise ShallowInputError(f"Грунта №{layer.soil_number} нет в каталоге")
            soil_records[layer.soil_number] = record
            data = record["data"]
            is_rock = data.get("material_class") == "rock"
            derived = None if is_rock else calculate_soil_properties(data, project.unit_conversions)
            soil_calculations[str(layer.soil_number)] = {
                "number": layer.soil_number,
                "name": data["name"],
                "geological_index": data["geological_index"],
                "raw": {key: data.get(key) for key in (
                    "rho_ii_g_cm3", "phi_ii_deg", "c_ii_kpa", "rho_i_g_cm3", "phi_i_deg", "c_i_kpa",
                    "e_mpa", "rho_s_g_cm3", "w", "wl", "wp", "filtration_m_day", "rc_mpa")},
                "derived": {} if derived is None else derived.as_dict(),
                "source": record["source"],
                "version": record["version"],
            }
            gamma = unit_weight_from_density(
                Quantity.of(data["rho_ii_g_cm3"], "g/cm3"),
                conversions=project.unit_conversions,
            )
            submerged = options.submerged_gamma_by_soil.get(
                layer.soil_number,
                None if derived is None else Quantity.of(derived.submerged_unit_weight_kn_m3, "kN/m3"),
            )
            modulus = None if data.get("e_mpa") is None else Quantity.of(data["e_mpa"], "MPa")
            stress_layers.append(StressLayer(layer.soil_number, layer.top_m, layer.bottom_m, gamma, submerged, modulus))
            if modulus is not None:
                settlement_layers.append(SettlementSoilLayer(layer.soil_number, layer.top_m, layer.bottom_m, modulus))
        data = soil_records[base_layers[0].soil_number]["data"]
        if data.get("material_class") == "rock":
            raise ShallowInputError(
                f"Подошва находится на скальном грунте №{base_layers[0].soil_number}. "
                "Формула (5.7) для дисперсных грунтов здесь неприменима; нужен отдельный расчёт по скальному основанию."
            )
        if data.get("c_ii_kpa") is None:
            raise ShallowInputError(
                f"Для грунта №{base_layers[0].soil_number} отсутствует расчётное удельное сцепление (cII); ноль не подставляется"
            )
        name = data["name"]
        wl, wp = data.get("wl"), data.get("wp")
        if wl is not None and wp is not None and Decimal(wl) == Decimal(wp):
            raise ShallowInputError(
                f"Для грунта №{base_layers[0].soil_number} влажность на границе текучести (WL) равна "
                "влажности на границе раскатывания (WP); показатель текучести (IL) не определён"
            )
        il = None if wl is None or wp is None else (Decimal(data["w"]) - Decimal(wp)) / (Decimal(wl) - Decimal(wp))
        conditions = select_working_conditions(soil_name=name, liquidity_index=il, sand_moisture=options.sand_moisture, rigid_scheme=options.rigid_scheme, length_height_ratio=options.length_height_ratio, loose_sand=options.loose_sand)
        sigma_base = geostatic_stress(foundation.depth, stress_layers, project.groundwater_m)
        gamma_above = Quantity(sigma_base.value / d, "kN/m3") if d else stress_layers[0].gamma_above_water
        averaging_depth = b / 2 if b < 10 else Decimal(4) + Decimal("0.1") * b
        sigma_below_limit = geostatic_stress(Quantity(d + averaging_depth, "m"), stress_layers, project.groundwater_m)
        automatic_gamma_below = Quantity((sigma_below_limit.value - sigma_base.value) / averaging_depth, "kN/m3")
        gamma_below = options.gamma_below_base or automatic_gamma_below
        if options.basement_depth.to("m").value:
            if any(item is None for item in (options.basement_soil_height, options.basement_floor_thickness, options.basement_floor_unit_weight)):
                raise ShallowInputError(
                    "Для подвала укажите толщину слоя грунта над подошвой (hs), толщину пола (hcf) "
                    "и удельный вес конструкции пола (γcf) по формуле (5.8)"
                )
            d1, db = basement_reduced_depth(
                base_depth=foundation.depth, floor_depth=options.basement_depth,
                soil_height=options.basement_soil_height, floor_thickness=options.basement_floor_thickness,
                floor_unit_weight=options.basement_floor_unit_weight, gamma_above=gamma_above)
        else:
            d1, db = foundation.depth, Quantity.of(0, "m")
        r = resistance(ResistanceInputs(
            phi_ii=Quantity.of(data["phi_ii_deg"], "deg"), cohesion_ii=Quantity.of(data["c_ii_kpa"], "kPa"),
            width=foundation.width, gamma_below=gamma_below, gamma_above=gamma_above,
            d1=d1, basement_depth=db,
            gamma_c1=conditions.gamma_c1, gamma_c2=conditions.gamma_c2,
            k=Decimal(1) if options.strength_from_tests else Decimal("1.1")))
        vertical_source = Quantity.from_dict(load["data"]["N"])
        vertical = vertical_source.to("kN", project.unit_conversions)
        moment = options.moment_at_base.to("kN*m", project.unit_conversions)
        m_gamma, m_q, m_c = m_coefficients(Quantity.of(data["phi_ii_deg"], "deg"))
        k = Decimal(1) if options.strength_from_tests else Decimal("1.1")
        kz = Decimal(1) if b < 10 else Decimal(8) / b + Decimal("0.2")
        pressure = base_pressure(vertical, moment, foundation.width, foundation.length,
            foundation.depth, options.foundation_unit_weight, r, kind=foundation.kind)
        net = Quantity(pressure.mean.value - sigma_base.value, "kPa")
        warnings = [
            f"Нагрузка в тс преобразована в кН по 1 тс = "
            f"{project.unit_conversions.tf_to_kn} кН (настройка проекта)"
        ]
        if options.gamma_below_base is None:
            warnings.append(f"γII ниже подошвы вычислен автоматически как средневзвешенный на глубине {averaging_depth} м по п. 5.6.10")
        else:
            warnings.append("γII ниже подошвы задан вручную и заменяет автоматическое средневзвешенное значение")
        if options.basement_depth.to("m").value:
            warnings.append("Подвал: γ фундамента и засыпки принимается введённым эквивалентным средним весом с учётом пустоты подвала")
        if load["data"].get("verification", "").startswith("извлечено"):
            warnings.append(f"Нагрузка {key} извлечена из цифрового текста задания и не сверена визуально")
        warnings.extend(load["data"].get("warnings", []))
        for number, record in soil_records.items():
            verification = record["data"].get("verification", "пользовательская запись")
            if verification.startswith("извлечено"):
                warnings.append(f"Грунт №{number} извлечён из цифрового текста задания; строка не сверена визуально")
            warnings.extend(f"Грунт №{number}: {warning}" for warning in soil_calculations[str(number)]["derived"].get("warnings", []))
            if record["data"].get("material_class") == "rock":
                warnings.append(
                    f"Грунт №{number} — скальный; в табл. 1 заданы плотность и Rc, но не E. "
                    "Он учитывается как граница разреза и не включается в сумму осадки."
                )
        if pressure.uplift:
            limit_symbol = "b" if foundation.kind == FoundationKind.STRIP else "l"
            warnings.append(f"Отрыв подошвы: e>{limit_symbol}/6. Увеличьте подошву автоматически или вручную до исчезновения отрыва")
        if pressure.edge_limit_ok is False:
            warnings.append("Диагностический флаг: pкрай>1,2R; результат расчёта не меняется")
        if pressure.mean.value > r.value:
            warnings.append("Среднее давление p>R")
        hc_result = None
        settlement = None
        if not pressure.uplift and net.value > 0:
            hc_result = find_hc(profile=project.profile, mode=options.hc_mode, kind=foundation.kind,
                width=foundation.width, length=foundation.length if foundation.kind == FoundationKind.PAD else None,
                pressure=net, base_depth=foundation.depth, layers=stress_layers,
                groundwater_m=project.groundwater_m, grid_step=Quantity(b * options.hc_step_fraction, "m"),
                weak_layer_selected=options.weak_layer_selected)
            settlement = calculate_settlement(kind=foundation.kind, width=foundation.width,
                length=foundation.length if foundation.kind == FoundationKind.PAD else None,
                pressure=net, base_depth=foundation.depth, h_c=hc_result.depth,
                soils=settlement_layers, groundwater_m=project.groundwater_m,
                step_fraction=options.hc_step_fraction,
                geostatic_stress_at=lambda depth: geostatic_stress(
                    depth, stress_layers, project.groundwater_m))
        elif net.value <= 0:
            warnings.append("Дополнительное давление p0≤0: осадка по выбранной формуле не вычислена")
        fmt = lambda value: f"{Decimal(value):.3f}"
        substitutions = {
            "R": f"({conditions.gamma_c1}·{conditions.gamma_c2}/{k})·({m_gamma}·{kz}·{b}·{fmt(gamma_below.value)} + {m_q}·{fmt(d1.value)}·{fmt(gamma_above.value)} + ({m_q}−1)·{fmt(db.value)}·{fmt(gamma_above.value)} + {m_c}·{data['c_ii_kpa']}) = {fmt(r.value)} кПа",
            "p": f"({fmt(vertical.value)} + {fmt(options.foundation_unit_weight.to('kN/m3').value)}·{d}·{b}·{l})/({b}·{l}) = {fmt(pressure.mean.value)} кПа",
            "p0": f"{fmt(pressure.mean.value)} - {fmt(sigma_base.value)} = {fmt(net.value)} кПа",
        }
        if hc_result is not None:
            substitutions["Hc"] = f"Последняя проверенная отметка: z={fmt(hc_result.points[-1].z_below_base_m)} м, σzp={fmt(hc_result.points[-1].sigma_zp_kpa)} кПа, σzg={fmt(hc_result.points[-1].sigma_zg_kpa)} кПа; Hc={fmt(hc_result.depth.value)} м"
        if settlement is not None:
            substitutions["s"] = f"Σ Δsi = {settlement.total.value:.5f} м по {len(settlement.layers)} элементарным слоям"
        return ShallowResult(foundation_number, options.combination, key, r, pressure, net,
            pressure.mean.value <= r.value, conditions, hc_result, settlement, tuple(warnings),
            {"soils": "; ".join(f"№{n} v{record['version']}: {record['source']}" for n, record in soil_records.items()),
             "loads": load["source"], "R": "СП 22.13330.2016, формула (5.7), табл. 5.4–5.5",
             "Hc": "Лекция №5, PDF с. 4" if project.profile.value == "lecture_hc_02" else "СП 22.13330.2016, п. 5.6.41",
             "settlement": "Лекция №5, PDF с. 6; формула с Ei",
             **({"basement": "СП 22.13330.2016, п. 5.6.7, формула (5.8), печ. с. 35"} if options.basement_depth.to("m").value else {})},
            {"moment_at_base": options.moment_at_base.as_dict(), "moment_basis": options.moment_basis,
             "foundation_unit_weight": options.foundation_unit_weight.as_dict(),
             "unit_conversions": project.unit_conversions.as_dict(),
             "gamma_below_base": gamma_below.as_dict(),
             "gamma_below_base_mode": "вручную" if options.gamma_below_base is not None else "автоматически, средневзвешенное по п. 5.6.10",
             "gamma_below_averaging_depth": Quantity(averaging_depth, "m").as_dict(),
             "R_parameters": [
                 {"symbol": "γc1", "value": str(conditions.gamma_c1), "unit": "—", "source": f"таблица 5.4; {conditions.category}", "mode": "автоматически"},
                 {"symbol": "γc2", "value": str(conditions.gamma_c2), "unit": "—", "source": "таблица 5.4; схема здания и L/H", "mode": "автоматически"},
                 {"symbol": "k", "value": str(k), "unit": "—", "source": "источник φII и cII", "mode": "по выбору пользователя"},
                 {"symbol": "Mγ", "value": str(m_gamma), "unit": "—", "source": f"таблица 5.5 по φII={data['phi_ii_deg']}°", "mode": "автоматически"},
                 {"symbol": "Mq", "value": str(m_q), "unit": "—", "source": f"таблица 5.5 по φII={data['phi_ii_deg']}°", "mode": "автоматически"},
                 {"symbol": "Mc", "value": str(m_c), "unit": "—", "source": f"таблица 5.5 по φII={data['phi_ii_deg']}°", "mode": "автоматически"},
                 {"symbol": "kz", "value": str(kz), "unit": "—", "source": "1 при b<10 м; 8/b+0,2 при b≥10 м", "mode": "автоматически"},
                 {"symbol": "b", "value": str(b), "unit": "м", "source": "таблица фундаментов", "mode": "автоматически"},
                 {"symbol": "γII", "value": fmt(gamma_below.value), "unit": "кН/м³", "source": f"средневзвешенное ниже подошвы на {averaging_depth} м", "mode": "вручную" if options.gamma_below_base is not None else "автоматически"},
                 {"symbol": "d1", "value": fmt(d1.value), "unit": "м", "source": "глубина подошвы или формула (5.8) при подвале", "mode": "автоматически"},
                 {"symbol": "γ′II", "value": fmt(gamma_above.value), "unit": "кН/м³", "source": "средневзвешенное выше подошвы", "mode": "автоматически"},
                 {"symbol": "db", "value": fmt(db.value), "unit": "м", "source": "глубина подвала, не более 2 м", "mode": "автоматически"},
                 {"symbol": "cII", "value": str(data["c_ii_kpa"]), "unit": "кПа", "source": f"таблица грунтов, грунт №{base_layers[0].soil_number}", "mode": "автоматически"},
             ],
             "strength_from_tests": options.strength_from_tests,
             "rigid_scheme": options.rigid_scheme,
             "length_height_ratio": None if options.length_height_ratio is None else str(options.length_height_ratio),
             "groundwater_absent": options.groundwater_absent,
             "basement_floor_depth": options.basement_depth.as_dict(),
             "basement_soil_height": None if options.basement_soil_height is None else options.basement_soil_height.as_dict(),
             "basement_floor_thickness": None if options.basement_floor_thickness is None else options.basement_floor_thickness.as_dict(),
             "basement_floor_unit_weight": None if options.basement_floor_unit_weight is None else options.basement_floor_unit_weight.as_dict(),
             "d1": d1.as_dict(), "db": db.as_dict(),
             "submerged_gamma_by_soil": {str(n): q.as_dict() for n, q in options.submerged_gamma_by_soil.items()},
             "weak_layer_selected": options.weak_layer_selected}, substitutions, soil_calculations)
