"""Боковая навигация, исходные данные и предварительный подбор."""

from decimal import Decimal, InvalidOperation
from dataclasses import replace
from html import escape
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QFrame, QGridLayout, QGroupBox, QHeaderView, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..application import open_pilot_catalog, preliminary_for_foundation
from ..domain import FoundationInput, FoundationKind, GeologyLayer, Profile, Project, normalize_geology_layers
from ..project_io import input_fingerprint, load_project, project_workspace_paths, safe_path_component, save_project
from ..shallow import ShallowFoundationCalculator, ShallowOptions
from ..hc import HcSearchMode
from ..reports.common import SECTION_DEPENDENCIES, SECTION_ORDER
from ..reports.word import export_word
from ..reports.excel import export_excel
from ..reports.catalog_export import export_catalog_excel, export_catalog_pdf
from ..sizing import auto_size_area, preliminary_geometry
from ..catalog_snapshot import ProjectCatalog
from ..catalog_io import export_catalog, import_catalog, preview_catalog_import
from ..standards.resistance import M_TABLE
from ..standards.working_conditions import WORKING_CONDITIONS_TABLE
from ..standards.r0 import CLAY_B3, SAND_B2
from ..soil_properties import SoilPropertiesError, calculate_soil_properties
from ..units import Quantity, UnitConversions


def _item(value: str) -> QTableWidgetItem:
    return QTableWidgetItem(value)


def _form_row(form: QFormLayout, text: str, field: QWidget, help_text: str = "") -> None:
    """Добавить поле с единообразной подписью и пояснением происхождения величины."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setMinimumWidth(260)
    label.setMaximumWidth(310)
    if help_text:
        label.setToolTip(help_text)
        field.setToolTip(help_text)
    form.addRow(label, field)


SP_R_HELP = "СП 22.13330.2016, формула (5.7), таблицы 5.4 и 5.5."
SP_BASEMENT_HELP = "СП 22.13330.2016, формула (5.8): приведённая глубина заложения при наличии подвала."
LECTURE_SETTLEMENT_HELP = "Лекция №5: метод послойного суммирования и определение нижней границы сжимаемой толщи."
LECTURE_SIZING_HELP = "Лекция №6: предварительное определение площади и размеров подошвы фундамента."
R_PARAMETER_NAMES = {
    "γc1": "Коэффициент условий работы грунта (γc1)",
    "γc2": "Коэффициент условий работы сооружения с основанием (γc2)",
    "k": "Коэффициент способа определения характеристик грунта (k)",
    "Mγ": "Безразмерный коэффициент при члене ширины подошвы (Mγ)",
    "Mq": "Безразмерный коэффициент при члене глубины заложения (Mq)",
    "Mc": "Безразмерный коэффициент при сцеплении (Mc)",
    "kz": "Коэффициент зависимости от ширины подошвы (kz)",
    "b": "Ширина подошвы фундамента (b)",
    "γII": "Осреднённый удельный вес грунта ниже подошвы (γII)",
    "d1": "Приведённая глубина заложения фундамента (d1)",
    "γ′II": "Осреднённый удельный вес грунта выше подошвы (γ′II)",
    "db": "Учитываемая глубина подвала (db)",
    "cII": "Расчётное удельное сцепление грунта под подошвой (cII)",
}


APP_STYLE = """
QMainWindow, QWidget { background: #F3F6FA; color: #172033; font-family: Inter, "Segoe UI", Arial; font-size: 13px; }
QTreeWidget#Navigation { background: #14243A; color: #DCE7F5; border: 0; padding: 18px 10px; outline: 0; }
QTreeWidget#Navigation::item { min-height: 34px; border-radius: 7px; padding: 3px 8px; }
QTreeWidget#Navigation::item:hover { background: #203A5C; }
QTreeWidget#Navigation::item:selected { background: #2F6FED; color: white; }
QWidget#Page { background: white; border: 1px solid #E2E8F0; border-radius: 14px; }
QLabel#PageTitle { color: #14243A; font-size: 24px; font-weight: 700; }
QLabel#Hint { color: #607089; background: #F6F9FD; border: 1px solid #DDE7F3; border-radius: 8px; padding: 10px; }
QLabel#Breadcrumb { color: #64748B; padding: 4px 2px 8px 2px; }
QLabel#InlineStatus { font-size: 12px; font-weight: 600; border-radius: 6px; padding: 5px 8px; }
QLabel#InlineStatus[status="success"] { color: #166534; background: #F0FDF4; }
QLabel#InlineStatus[status="error"] { color: #B42318; background: #FFF1F0; }
QLabel#InlineStatus[status="busy"] { color: #1D4ED8; background: #EFF6FF; }
QLabel#InlineStatus[status="info"] { color: #475569; background: #F8FAFC; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #CBD5E1; border-radius: 7px; padding: 7px 9px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #2F6FED; }
QPushButton { background: #2F6FED; color: white; border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #245ED0; }
QPushButton:disabled { background: #B9C5D6; }
QPushButton#RemoveRow { background: transparent; color: #B42318; border: 1px solid #F0B8B4; border-radius: 6px; padding: 0; font-size: 18px; font-weight: 700; }
QPushButton#RemoveRow:hover { background: #FFF0EF; border-color: #D92D20; }
QTableWidget, QTextBrowser { background: white; border: 1px solid #DCE3EC; border-radius: 9px; alternate-background-color: #F8FAFD; selection-background-color: #DCE9FF; selection-color: #14243A; }
QHeaderView::section { background: #EDF3FA; color: #334155; border: 0; border-bottom: 1px solid #D6DFEA; padding: 8px; font-weight: 650; }
QGroupBox { background: #FAFCFF; border: 1px solid #DDE6F0; border-radius: 10px; margin-top: 12px; padding: 15px 10px 10px 10px; font-weight: 650; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #334155; }
QCheckBox { spacing: 8px; }
QStatusBar { background: white; border-top: 1px solid #E2E8F0; color: #475569; }
"""


class MainWindow(QMainWindow):
    def __init__(self, catalog_path: str | Path | None = None):
        super().__init__()
        self.setWindowTitle("Основания и фундаменты — опытная версия")
        self.resize(1220, 780)
        self.catalog = open_pilot_catalog(catalog_path)
        self.project = Project("Новый проект")
        self.project_path: Path | None = None
        self._screens: dict[str, int] = {}
        self._syncing_foundations = False
        self._loading_forms = False
        self._build_ui()
        self.setStyleSheet(APP_STYLE)
        self._load_project_into_forms()
        self.nav.setCurrentItem(self.nav.topLevelItem(0))

    def _active_catalog(self) -> ProjectCatalog:
        return ProjectCatalog(self.project, self.catalog)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.nav = QTreeWidget()
        self.nav.setObjectName("Navigation")
        self.nav.setHeaderHidden(True)
        self.nav.setMinimumWidth(280)
        self.nav.setMaximumWidth(350)
        row.addWidget(self.nav)
        right = QVBoxLayout()
        right.setContentsMargins(24, 18, 24, 22)
        row.addLayout(right, 1)
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("Breadcrumb")
        right.addWidget(self.breadcrumb)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)
        self._add_page("Проект", self._project_page())
        inputs = self._tree("Исходные данные")
        self._tree("Объект и профиль", inputs)
        self._screens["Объект и профиль"] = self._screens["Проект"]
        self._add_page("Грунты, разрез и УГВ", self._ground_conditions_page(), inputs)
        self._add_page("Схема и нагрузки", self._scheme_page(), inputs)
        calc = self._tree("Расчёты")
        shallow = self._tree("Фундаменты мелкого заложения", calc)
        self._add_page("Исходные параметры фундаментов", self._foundations_page(), shallow)
        self._add_page("Предварительный подбор", self._preliminary_page(), shallow)
        self._add_page("Расчёт R и осадки", self._calculation_page(), shallow)
        self._add_page("Свайные фундаменты", self._pending_page("Отдельный модуль следующих этапов."), calc)
        self._add_page("Сводные результаты", self._summary_page())
        self._add_page("Отчёты", self._reports_page())
        refs = self._tree("Справочники")
        self._add_page("Грунты", self._catalog_soils_page(), refs)
        self._add_page("Схемы и нагрузки", self._catalog_schemes_page(), refs)
        self._add_page("Таблицы R₀", self._r0_reference_page(), refs)
        self._add_page("Нормативные коэффициенты", self._coefficients_page(), refs)
        self._add_page("Экспорт справочника", self._catalog_export_page(), refs)
        self._add_page("Настройки", self._settings_page())
        self.nav.expandAll()
        self.nav.currentItemChanged.connect(self._navigate)

    def _tree(self, text: str, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        if parent is None:
            self.nav.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _add_page(self, name: str, widget: QWidget, parent: QTreeWidgetItem | None = None):
        item = self._tree(name, parent)
        self._screens[name] = self.pages.addWidget(widget)
        return item

    def _navigate(self, item, _previous):
        if item is None:
            return
        labels = []
        current = item
        while current:
            labels.insert(0, current.text(0))
            current = current.parent()
        self.breadcrumb.setText(" → ".join(labels))
        index = self._screens.get(item.text(0))
        if index is not None:
            self.pages.setCurrentIndex(index)
        if item.text(0) == "Сводные результаты":
            self._refresh_summary()

    def _open_screen(self, name: str):
        matches = self.nav.findItems(name, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive, 0)
        if matches:
            self.nav.setCurrentItem(matches[0])

    def _page(self, heading: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        title = QLabel(heading)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        return page, layout

    def _inline_status(self) -> QLabel:
        label = QLabel()
        label.setObjectName("InlineStatus")
        label.setWordWrap(True)
        label.setVisible(False)
        return label

    def _set_inline_status(self, label: QLabel, text: str, status: str = "info", tooltip: str = "") -> None:
        label.setText(text)
        label.setToolTip(tooltip)
        label.setProperty("status", status)
        label.style().unpolish(label)
        label.style().polish(label)
        label.setVisible(bool(text))
        if status == "busy":
            QApplication.processEvents()

    def _project_page(self) -> QWidget:
        page, layout = self._page("Проект")
        form = QFormLayout()
        layout.addLayout(form)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Монтажный цех")
        self.name_edit.textChanged.connect(self._update_project_path_preview)
        _form_row(form, "Название объекта", self.name_edit, "Название используется для папки проекта и заголовков отчётов.")
        self.project_profile_edit = QLineEdit()
        self.project_profile_edit.setPlaceholderText("Например: вариант 22 / Рената")
        self.project_profile_edit.textChanged.connect(self._update_project_path_preview)
        _form_row(form, "Название профиля проекта", self.project_profile_edit, "Например, номер варианта или фамилия исполнителя.")
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Учебный: Hc по 0,2·σzg", Profile.LECTURE_HC_02)
        self.profile_combo.addItem("Критерий СП: Hc по 0,5·σzg; осадка по лекции", Profile.SP_HC_05_LECTURE_SETTLEMENT)
        _form_row(form, "Метод определения границы сжимаемой толщи (Hc)", self.profile_combo, LECTURE_SETTLEMENT_HELP)
        path_widget = QWidget()
        path_row = QHBoxLayout(path_widget)
        path_row.setContentsMargins(0, 0, 0, 0)
        self.project_parent_edit = QLineEdit()
        self.project_parent_edit.setPlaceholderText("Выберите или введите пут")
        self.project_parent_edit.textChanged.connect(self._update_project_path_preview)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._select_project_parent)
        path_row.addWidget(self.project_parent_edit, 1)
        path_row.addWidget(browse)
        _form_row(form, "Родительская папка проекта", path_widget)
        self.project_path_preview = QLabel()
        self.project_path_preview.setObjectName("Hint")
        self.project_path_preview.setWordWrap(True)
        _form_row(form, "Итоговая папка проекта", self.project_path_preview)
        note = QLabel("Формула осадки в обоих вариантах — из лекции № 5. Предельная осадка по типу здания не проверяется.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        for label, callback in (("Новый", self._new), ("Открыть…", self._open), ("Сохранить", self._save), ("Сохранить как…", self._save_as)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.project_status = self._inline_status()
        layout.addWidget(self.project_status)
        layout.addStretch()
        return page

    def _soils_page(self) -> QWidget:
        page, layout = self._page("Выбранные грунты")
        form = QFormLayout()
        self.soils_edit = QLineEdit()
        self.soils_edit.setPlaceholderText("Например: 29, 40, 81")
        _form_row(form, "Номера грунтов (№ грунта)", self.soils_edit, "Номера строк таблицы 1 из задания на курсовую работу.")
        layout.addLayout(form)
        layout.addWidget(QLabel("Встроены 83 строки табл. 1 задания и служебный грунт №0 «Песок». Грунты №29, 40, 81, 104 и 105 сверены визуально; остальные извлечены из цифрового текста PDF и помечаются предупреждением до ручной сверки."))
        layout.addStretch()
        return page

    def _ground_conditions_page(self) -> QWidget:
        page, outer = self._page("Грунты и инженерно-геологические условия")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(content)

        soils_box = QGroupBox("Выбранные грунты")
        soils_layout = QVBoxLayout(soils_box)
        soils_form = QFormLayout()
        self.soils_edit = QLineEdit()
        self.soils_edit.setPlaceholderText("Например: 29, 40, 81")
        _form_row(soils_form, "Номера грунтов (№ грунта)", self.soils_edit, "Номера строк таблицы 1 из задания на курсовую работу.")
        soils_layout.addLayout(soils_form)
        soils_note = QLabel("Номера должны соответствовать грунтам, использованным ниже в геологическом разрезе.")
        soils_note.setObjectName("Hint")
        soils_note.setWordWrap(True)
        soils_layout.addWidget(soils_note)
        layout.addWidget(soils_box)

        geology_box = QGroupBox("Геологический разрез")
        geology_layout = QVBoxLayout(geology_box)
        coordinate_form = QFormLayout()
        self.geology_mode_combo = QComboBox()
        self.geology_mode_combo.addItem("Глубины от поверхности", "depth")
        self.geology_mode_combo.addItem("Абсолютные отметки", "elevation")
        self.geology_mode_combo.currentIndexChanged.connect(self._update_geology_mode)
        _form_row(coordinate_form, "Система координат геологического разреза", self.geology_mode_combo)
        self.surface_elevation_edit = QLineEdit()
        self.surface_elevation_edit.setPlaceholderText("например 130,0; пусто — взять максимальную верхнюю отметку")
        self.surface_elevation_label = QLabel("Абсолютная отметка поверхности земли, м")
        self.surface_elevation_label.setToolTip("Отметка кровли верхнего слоя на инженерно-геологическом разрезе.")
        self.surface_elevation_edit.setToolTip("Отметка кровли верхнего слоя на инженерно-геологическом разрезе.")
        coordinate_form.addRow(self.surface_elevation_label, self.surface_elevation_edit)
        geology_layout.addLayout(coordinate_form)
        self.geology_hint = QLabel()
        self.geology_hint.setWordWrap(True)
        self.geology_hint.setObjectName("Hint")
        geology_layout.addWidget(self.geology_hint)
        self.layers_table = QTableWidget(0, 4)
        self.layers_table.setHorizontalHeaderLabels(["Номер грунта", "Глубина кровли слоя, м", "Глубина подошвы слоя, м", ""])
        self.layers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.layers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.layers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.layers_table.setColumnWidth(3, 42)
        self.layers_table.verticalHeader().setDefaultSectionSize(38)
        self.layers_table.setMinimumHeight(280)
        geology_layout.addWidget(self.layers_table)
        add = QPushButton("Добавить слой")
        add.clicked.connect(lambda: self._add_layer_row("", "", ""))
        geology_layout.addWidget(add)
        layout.addWidget(geology_box)

        water_box = QGroupBox("Уровень грунтовых вод")
        water_form = QFormLayout(water_box)
        self.water_edit = QLineEdit()
        self.water_edit.setPlaceholderText("Глубина УГВ от поверхности, м; пусто — неизвестно")
        self.water_label = QLabel("Глубина уровня грунтовых вод (УГВ), м")
        water_form.addRow(self.water_label, self.water_edit)
        self.calc_water_absent = QCheckBox("Подтверждено отсутствие УГВ в расчётной толще")
        _form_row(water_form, "Отсутствие уровня грунтовых вод (УГВ)", self.calc_water_absent,
                  "Отмечайте только при подтверждённом отсутствии воды во всей расчётной толще.")
        self.calc_submerged = QLineEdit()
        self.calc_submerged.setPlaceholderText("необязательно: 29:10.5, 40:9.8; пусто — расчёт из ρs и e")
        _form_row(water_form, "Удельный вес грунта с учётом взвешивания (γsb), кН/м³", self.calc_submerged,
                  "Необязательная замена по номерам грунтов. Пустое поле — автоматический расчёт из ρs и e.")
        layout.addWidget(water_box)
        layout.addStretch()
        self._update_geology_mode()
        return page

    def _scheme_page(self) -> QWidget:
        page, layout = self._page("Схема здания и нагрузки")
        form = QFormLayout()
        self.scheme_spin = QSpinBox()
        self.scheme_spin.setRange(1, 999)
        self.scheme_spin.setValue(18)
        self.variant_combo = QComboBox()
        self.variant_combo.addItem("Чётный", "even")
        self.variant_combo.addItem("Нечётный", "odd")
        _form_row(form, "Номер схемы здания", self.scheme_spin, "Номер схемы из таблицы 2 задания на курсовую работу.")
        _form_row(form, "Вариант исходных нагрузок", self.variant_combo, "Чётный или нечётный вариант таблицы 2 задания.")
        layout.addLayout(form)
        hint = QLabel("Выберите фундаменты прямо на схеме. Они автоматически появятся в разделе исходных параметров.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        content = QHBoxLayout()
        content.setSpacing(16)
        self.scheme_image = QLabel("Чертёж схемы")
        self.scheme_image.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scheme_image.setMinimumWidth(360)
        content.addWidget(self.scheme_image, 1)
        right = QVBoxLayout()
        self.loads_view = QTextBrowser()
        self.loads_view.setMinimumHeight(210)
        right.addWidget(self.loads_view, 1)

        foundation_box = QGroupBox("Фундаменты для расчёта")
        foundation_layout = QVBoxLayout(foundation_box)
        self.scheme_foundations_table = QTableWidget(0, 3)
        self.scheme_foundations_table.setHorizontalHeaderLabels(["Включить в расчёт", "Номер фундамента", "Тип фундамента"])
        self.scheme_foundations_table.verticalHeader().setVisible(False)
        self.scheme_foundations_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.scheme_foundations_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.scheme_foundations_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.scheme_foundations_table.setMaximumHeight(230)
        self.scheme_foundations_table.verticalHeader().setDefaultSectionSize(38)
        self.scheme_foundations_table.itemChanged.connect(self._scheme_foundations_changed)
        foundation_layout.addWidget(self.scheme_foundations_table)
        common_form = QFormLayout()
        self.common_depth_edit = QLineEdit()
        self.common_depth_edit.setPlaceholderText("одинаковая для всех выбранных фундаментов")
        self.common_depth_edit.editingFinished.connect(self._scheme_foundations_changed)
        _form_row(common_form, "Глубина заложения фундамента (d), м", self.common_depth_edit,
                  "Расстояние от уровня планировки до подошвы фундамента. Лекция №6.")
        self.basement_check = QCheckBox("В здании есть подвал")
        self.basement_check.toggled.connect(self._toggle_basement)
        _form_row(common_form, "Наличие подвала", self.basement_check, SP_BASEMENT_HELP)
        self.basement_height_edit = QLineEdit()
        self.basement_height_edit.setPlaceholderText("глубина пола подвала от планировочной отметки")
        self.basement_height_edit.editingFinished.connect(self._scheme_foundations_changed)
        _form_row(common_form, "Глубина пола подвала от планировочной отметки (db,факт), м", self.basement_height_edit,
                  "Геометрическая глубина пола подвала. В формуле R учитываемая величина db ограничивается 2 м.")
        foundation_layout.addLayout(common_form)
        right.addWidget(foundation_box)
        content.addLayout(right, 1)
        layout.addLayout(content, 1)
        button = QPushButton("Обновить схему и нагрузки")
        button.clicked.connect(self._show_loads)
        layout.addWidget(button)
        self.scheme_spin.valueChanged.connect(self._show_loads)
        self.variant_combo.currentIndexChanged.connect(self._show_loads)
        return page

    def _geology_page(self) -> QWidget:
        page, layout = self._page("Геологический разрез")
        coordinate_form = QFormLayout()
        self.geology_mode_combo = QComboBox()
        self.geology_mode_combo.addItem("Глубины от поверхности", "depth")
        self.geology_mode_combo.addItem("Абсолютные отметки", "elevation")
        self.geology_mode_combo.currentIndexChanged.connect(self._update_geology_mode)
        _form_row(coordinate_form, "Система координат геологического разреза", self.geology_mode_combo)
        self.surface_elevation_edit = QLineEdit()
        self.surface_elevation_edit.setPlaceholderText("например 130,0; пусто — взять максимальную верхнюю отметку")
        _form_row(coordinate_form, "Абсолютная отметка поверхности земли, м", self.surface_elevation_edit)
        layout.addLayout(coordinate_form)
        self.geology_hint = QLabel()
        self.geology_hint.setWordWrap(True)
        self.geology_hint.setObjectName("Hint")
        layout.addWidget(self.geology_hint)
        self.layers_table = QTableWidget(0, 4)
        self.layers_table.setHorizontalHeaderLabels(["Номер грунта", "Глубина кровли слоя, м", "Глубина подошвы слоя, м", ""])
        self.layers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.layers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.layers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.layers_table.setColumnWidth(3, 42)
        self.layers_table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.layers_table, 1)
        add = QPushButton("Добавить слой")
        add.clicked.connect(lambda: self._add_layer_row("", "", ""))
        layout.addWidget(add)
        self._update_geology_mode()
        return page

    def _update_geology_mode(self, *_):
        if not hasattr(self, "geology_mode_combo"):
            return
        elevations = self.geology_mode_combo.currentData() == "elevation"
        self.surface_elevation_edit.setEnabled(elevations)
        if elevations:
            self.layers_table.setHorizontalHeaderLabels(["Номер грунта", "Абсолютная отметка кровли слоя, м", "Абсолютная отметка подошвы слоя, м", ""])
            self.geology_hint.setText("Для абсолютных отметок верхняя граница больше нижней: например 130→124→118 м. Отметка поверхности — это кровля верхнего слоя, а не отметка подошвы фундамента; её можно оставить пустой для автоматического выбора.")
            if hasattr(self, "surface_elevation_label"):
                self.surface_elevation_label.setText("Абсолютная отметка поверхности земли, м")
            if hasattr(self, "water_label"):
                self.water_label.setText("Абсолютная отметка уровня грунтовых вод (УГВ), м")
                self.water_edit.setPlaceholderText("например 124,5; пусто — неизвестно")
        else:
            self.layers_table.setHorizontalHeaderLabels(["Номер грунта", "Глубина кровли слоя, м", "Глубина подошвы слоя, м", ""])
            self.geology_hint.setText("Глубины отсчитываются от поверхности вниз: верхняя граница меньше нижней, например 0→6→12 м.")
            if hasattr(self, "surface_elevation_label"):
                self.surface_elevation_label.setText("Абсолютная отметка поверхности земли, м")
            if hasattr(self, "water_label"):
                self.water_label.setText("Глубина уровня грунтовых вод (УГВ), м")
                self.water_edit.setPlaceholderText("например 1,5; пусто — неизвестно")

    def _water_page(self) -> QWidget:
        page, layout = self._page("Уровень грунтовых вод")
        form = QFormLayout()
        self.water_edit = QLineEdit()
        self.water_edit.setPlaceholderText("Глубина УГВ от поверхности, м; пусто — неизвестно")
        _form_row(form, "Глубина уровня грунтовых вод (УГВ), м", self.water_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("Неизвестный УГВ не подменяется отсутствием воды при окончательном расчёте."))
        layout.addStretch()
        return page

    def _foundations_page(self) -> QWidget:
        page, layout = self._page("Фундаменты мелкого заложения")
        hint = QLabel("Выбранные на схеме фундаменты синхронизируются с этой таблицей. Для ленточного фундамента расчётная длина фиксируется: l=1 м.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.foundations_table = QTableWidget(0, 6)
        self.foundations_table.setHorizontalHeaderLabels([
            "Номер", "Тип фундамента", "Глубина заложения (d), м",
            "Ширина подошвы (b), м", "Длина подошвы (l), м", "",
        ])
        self.foundations_table.setAlternatingRowColors(True)
        self.foundations_table.verticalHeader().setDefaultSectionSize(38)
        self.foundations_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3, 4):
            self.foundations_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.foundations_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.foundations_table.setColumnWidth(5, 42)
        layout.addWidget(self.foundations_table, 1)
        add = QPushButton("Добавить фундамент")
        add.clicked.connect(lambda: self._add_foundation_row("", "столбчатый", "", "", ""))
        layout.addWidget(add)
        return page

    def _preliminary_page(self) -> QWidget:
        page, layout = self._page("Предварительный подбор по R₀")
        form = QFormLayout()
        self.prelim_foundation = QSpinBox()
        self.prelim_foundation.setRange(1, 999)
        self.prelim_foundation.setValue(3)
        self.prelim_combination = QComboBox()
        self.prelim_combination.addItem("1-е сочетание", 1)
        self.prelim_combination.addItem("2-е сочетание", 2)
        self.sand_density = QComboBox()
        self.sand_density.addItem("Не указана", None)
        self.sand_density.addItem("Плотный", "dense")
        self.sand_density.addItem("Средней плотности", "medium")
        self.sand_moisture = QComboBox()
        self.sand_moisture.addItem("Не указано", None)
        self.sand_moisture.addItem("Маловлажный", "low")
        self.sand_moisture.addItem("Влажный", "wet")
        self.sand_moisture.addItem("Водонасыщенный", "saturated")
        _form_row(form, "Номер рассчитываемого фундамента", self.prelim_foundation)
        _form_row(form, "Сочетание нагрузок", self.prelim_combination, "Первое или второе сочетание из таблицы 2 задания.")
        _form_row(form, "Плотность сложения песка", self.sand_density, "Признак для выбора R₀ по таблице Б.2 СП 22.13330.2016.")
        _form_row(form, "Состояние песка по влажности", self.sand_moisture, "Признак для выбора R₀ по таблице Б.2 СП 22.13330.2016.")
        self.prelim_gamma_f = QLineEdit(); self.prelim_gamma_f.setPlaceholderText("кН/м³; из конструкции фундамента и засыпки")
        _form_row(form, "Средний удельный вес фундамента и засыпки (γf), кН/м³", self.prelim_gamma_f,
                  LECTURE_SIZING_HELP + " Используется при учёте собственного веса фундамента и грунта на уступах.")
        layout.addLayout(form)
        note = QLabel(
            "Как считается R₀: 1) по глубине подошвы программа находит несущий слой; "
            "2) для песка выбирает значение из таблицы Б.2, для глинистого грунта вычисляет e, Ip, IL и интерполирует таблицу Б.3; "
            "3) по нагрузке из выбранного сочетания вычисляет A=N/(R₀−γмd). "
            "Вводить R₀ вручную не нужно. Плотность сложения и состояние по влажности нужны только для песков."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        button = QPushButton("Рассчитать предварительную площадь")
        button.clicked.connect(self._calculate_preliminary)
        layout.addWidget(button)
        apply_button = QPushButton("Применить предварительные размеры к фундаменту")
        apply_button.clicked.connect(self._apply_preliminary)
        layout.addWidget(apply_button)
        self.preliminary_status = self._inline_status()
        layout.addWidget(self.preliminary_status)
        tables_button = QPushButton("Открыть таблицы R₀ и условия выбора")
        tables_button.clicked.connect(lambda: self._open_screen("Таблицы R₀"))
        layout.addWidget(tables_button)
        self.preliminary_result = QTextBrowser()
        layout.addWidget(self.preliminary_result, 1)
        return page

    def _catalog_soils_page(self) -> QWidget:
        page, layout = self._page("Справочник грунтов")
        hint = QLabel("Слева — каталог, справа — полные исходные и вычисленные характеристики выбранного грунта. Расчёт повторяет лист «Грунты» исходной книги.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        content = QHBoxLayout()
        self.soils_catalog_table = QTableWidget(0, 8)
        self.soils_catalog_table.setHorizontalHeaderLabels([
            "Номер", "Наименование грунта", "Геологический индекс",
            "Плотность (ρII), г/см³", "Угол трения (φII), °",
            "Сцепление (cII), кПа", "Модуль (E), МПа", "",
        ])
        self.soils_catalog_table.setAlternatingRowColors(True)
        self.soils_catalog_table.verticalHeader().setVisible(False)
        self.soils_catalog_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.soils_catalog_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.soils_catalog_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((2, 135), (3, 155), (4, 145), (5, 145), (6, 125)):
            self.soils_catalog_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.soils_catalog_table.setColumnWidth(column, width)
        self.soils_catalog_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.soils_catalog_table.setColumnWidth(7, 42)
        self.soils_catalog_table.verticalHeader().setDefaultSectionSize(38)
        self.soils_catalog_table.itemSelectionChanged.connect(self._show_soil_details)
        content.addWidget(self.soils_catalog_table, 3)
        self.soil_details = QTextBrowser()
        self.soil_details.setOpenExternalLinks(False)
        content.addWidget(self.soil_details, 4)
        layout.addLayout(content, 1)
        add = QPushButton("Добавить свой грунт…")
        add.clicked.connect(self._add_custom_soil)
        layout.addWidget(add)
        self._refresh_soil_catalog()
        return page

    def _refresh_soil_catalog(self):
        table = self.soils_catalog_table
        table.setRowCount(0)
        for record in self.catalog.list("soil"):
            d = record["data"]
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate((record["key"], d["name"], d.get("geological_index"), d.get("rho_ii_g_cm3"), d.get("phi_ii_deg"), d.get("c_ii_kpa"), d.get("e_mpa"))):
                table.setItem(row, column, _item("—" if value in (None, "", "-") else str(value)))
            if not record["builtin"]:
                self._set_remove_button(table, row, lambda _button, key=record["key"]: self._delete_custom_soil(key))
        if table.rowCount():
            table.selectRow(0)

    def _show_soil_details(self):
        if not hasattr(self, "soil_details"):
            return
        row = self.soils_catalog_table.currentRow()
        if row < 0:
            self.soil_details.clear()
            return
        number = self._table_text(self.soils_catalog_table, row, 0)
        record = self.catalog.get("soil", number)
        if record is None:
            self.soil_details.setPlainText("Запись не найдена")
            return
        data = record["data"]
        if data.get("material_class") == "rock":
            derived = {}
            calculation_error = ""
            calculation_note = (
                "Для скального грунта в задании приведены плотность и Rc. Производные характеристики "
                "дисперсных грунтов (e, IL, mv и другие) к этой записи не применяются."
            )
        else:
            calculation_note = ""
            try:
                derived = calculate_soil_properties(data, self.project.unit_conversions).as_dict()
            except SoilPropertiesError as exc:
                derived = {}
                calculation_error = str(exc)
            else:
                calculation_error = ""

        def value(key: str, unit: str = "") -> str:
            raw = data.get(key)
            return "—" if raw in (None, "", "-") else f"{escape(str(raw))}{(' ' + unit) if unit else ''}"

        def dvalue(key: str, unit: str = "", digits: int = 5) -> str:
            raw = derived.get(key)
            if raw is None:
                return "—"
            shown = f"{Decimal(raw):.{digits}f}".rstrip("0").rstrip(".")
            return f"{shown}{(' ' + unit) if unit else ''}"

        raw_rows = (
            ("Расчётная плотность по II группе (ρII)", value("rho_ii_g_cm3", "г/см³")),
            ("Расчётный угол внутреннего трения по II группе (φII)", value("phi_ii_deg", "°")),
            ("Расчётное удельное сцепление по II группе (cII)", value("c_ii_kpa", "кПа")),
            ("Расчётная плотность по I группе (ρI)", value("rho_i_g_cm3", "г/см³")),
            ("Расчётный угол внутреннего трения по I группе (φI)", value("phi_i_deg", "°")),
            ("Расчётное удельное сцепление по I группе (cI)", value("c_i_kpa", "кПа")),
            ("Модуль деформации (E)", value("e_mpa", "МПа")),
            ("Плотность частиц грунта (ρs)", value("rho_s_g_cm3", "г/см³")),
            ("Природная влажность (W)", value("w")),
            ("Влажность на границе текучести (WL)", value("wl")),
            ("Влажность на границе раскатывания (WP)", value("wp")),
            ("Коэффициент фильтрации (Kф)", value("filtration_m_day", "м/сут")),
            ("Расчётное сопротивление сжатию (Rc)", value("rc_mpa", "МПа")),
        )
        derived_rows = (
            ("Плотность сухого грунта (ρd)", dvalue("rho_d_g_cm3", "г/см³"), "ρII/(1+W)"),
            ("Коэффициент пористости (e)", dvalue("e"), "(ρs−ρd)/ρd"),
            ("Степень водонасыщения (Sr)", dvalue("sr"), "W·ρs/e"),
            ("Число пластичности (Ip)", dvalue("ip"), "WL−WP"),
            ("Показатель текучести (IL)", dvalue("il"), "(W−WP)/Ip"),
            ("Коэффициент для осадки (β)", dvalue("beta"), "по виду грунта"),
            ("Коэффициент относительной сжимаемости (mv)", dvalue("mv_1_kpa", "1/кПа", 8), "β/E"),
            ("Удельный вес грунта (γ)", dvalue("gamma_kn_m3", "кН/м³"), "ρ·g"),
            ("Удельный вес частиц грунта (γs)", dvalue("gamma_s_kn_m3", "кН/м³"), "ρs·g"),
            ("Удельный вес сухого грунта (γd)", dvalue("gamma_d_kn_m3", "кН/м³"), "ρd·g"),
            ("Удельный вес грунта с учётом взвешивания (γsb)", dvalue("gamma_sb_kn_m3", "кН/м³"), "(ρs−ρw)·g/(1+e)"),
        )
        table = lambda rows, third=False: "<table width='100%' cellspacing='0' cellpadding='6'>" + "".join(
            f"<tr><td><b>{escape(str(a))}</b></td><td>{b}</td>{f'<td style=\"color:#64748B\">{escape(str(c))}</td>' if third else ''}</tr>"
            for a, b, *tail in rows for c in ([tail[0]] if third else [""])) + "</table>"
        warnings = "".join(f"<li>{escape(item)}</li>" for item in derived.get("warnings", []))
        error = f"<p style='color:#B42318'><b>Расчёт не выполнен:</b> {escape(calculation_error)}</p>" if calculation_error else ""
        note = f"<p style='color:#1D4ED8'><b>Примечание:</b> {escape(calculation_note)}</p>" if calculation_note else ""
        self.soil_details.setHtml(f"""
            <h2 style='color:#14243A'>Грунт №{escape(number)} · {escape(data['name'])}</h2>
            <p><b>Геологический индекс:</b> {escape(str(data.get('geological_index') or '—'))}</p>
            {f"<p style='color:#1D4ED8'><b>Назначение:</b> {escape(data['usage_note'])}</p>" if data.get('usage_note') else ''}
            <h3>Исходные характеристики</h3>{table(raw_rows)}
            <h3>Расчётные характеристики</h3>{table(derived_rows, True)}
            {note}{error}{f'<ul style="color:#B54708">{warnings}</ul>' if warnings else ''}
            <p style='color:#64748B'><b>Источник:</b> {escape(record['source'])}<br>
            <b>Формулы:</b> ЗАДАНИЕ на КР, печ. с. 54. Принято g={self.project.unit_conversions.gravity_m_s2} м/с².</p>
        """)

    def _calculation_page(self) -> QWidget:
        page, layout = self._page("Расчёт R, давлений и осадки")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        note = QLabel(
            "Программа автоматически находит грунт под подошвой и вычисляет коэффициенты формулы R. "
            "Пользователь задаёт только признаки, которых нет в таблицах: конструктивную схему, происхождение φII и cII, "
            "момент и параметры конструкции фундамента. Удельный вес грунта ниже подошвы (γII) и значения с учётом "
            "взвешивания ниже УГВ (γsb) рассчитываются автоматически; соответствующие поля нужны только для обоснованной замены."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        layout.addLayout(form)
        self.calc_foundation = QSpinBox(); self.calc_foundation.setRange(1, 999); self.calc_foundation.setValue(3)
        self.calc_combination = QComboBox(); self.calc_combination.addItem("1-е сочетание", 1); self.calc_combination.addItem("2-е сочетание", 2)
        _form_row(form, "Номер рассчитываемого фундамента", self.calc_foundation)
        _form_row(form, "Сочетание нагрузок", self.calc_combination, "Первое или второе сочетание из таблицы 2 задания.")
        self.calc_rigid = QComboBox()
        self.calc_rigid.addItem("Не указана — расчёт блокируется", None)
        self.calc_rigid.addItem("Гибкая конструктивная схема", False)
        self.calc_rigid.addItem("Жёсткая конструктивная схема", True)
        _form_row(form, "Конструктивная схема здания", self.calc_rigid,
                  "Гибкая или жёсткая схема нужна для выбора коэффициента условий работы γc2 по таблице 5.4 СП.")
        self.calc_ratio = QLineEdit(); self.calc_ratio.setPlaceholderText("L/H; только для жёсткой схемы")
        _form_row(form, "Отношение длины здания к высоте (L/H)", self.calc_ratio,
                  "Для жёсткой конструктивной схемы используется при выборе или интерполяции γc2.")
        self.calc_moisture = QComboBox()
        for label, data in (("Не указана", None), ("Маловлажный", "low"), ("Влажный", "wet"), ("Водонасыщенный", "saturated")):
            self.calc_moisture.addItem(label, data)
        _form_row(form, "Состояние песка по влажности", self.calc_moisture,
                  "Учитывается при классификации песчаного грунта по таблице 5.4 СП.")
        self.calc_loose = QCheckBox("Рыхлый песок")
        _form_row(form, "Рыхлое сложение песка", self.calc_loose,
                  "Признак применяется только для песчаного грунта под подошвой.")
        self.calc_strength_tests = QComboBox()
        self.calc_strength_tests.addItem("Не указан — расчёт блокируется", None)
        self.calc_strength_tests.addItem("Непосредственные испытания; k=1", True)
        self.calc_strength_tests.addItem("Таблица приложения А СП; k=1,1", False)
        _form_row(form, "Происхождение характеристик прочности (φII, cII)", self.calc_strength_tests,
                  "Определяет коэффициент k в формуле (5.7): k=1 по непосредственным испытаниям; k=1,1 по таблицам приложения А.")
        self.calc_moment = QLineEdit(); self.calc_moment.setPlaceholderText("тс·м, со знаком; момент на уровне подошвы")
        _form_row(form, "Изгибающий момент на уровне подошвы (M), тс·м", self.calc_moment,
                  "Момент относительно центра подошвы со знаком. Источник — таблица нагрузок или перенос поперечной силы T на уровень подошвы.")
        self.calc_moment_basis = QLineEdit(); self.calc_moment_basis.setPlaceholderText("Например: M + T·h, h=… м")
        _form_row(form, "Обоснование момента на уровне подошвы (M)", self.calc_moment_basis,
                  "Запишите, взят ли M непосредственно из задания или вычислен, например M=MII+TII·h.")
        self.calc_gamma_f = QLineEdit(); self.calc_gamma_f.setPlaceholderText("кН/м³; при подвале — эквивалентный средний вес")
        _form_row(form, "Средний удельный вес фундамента и засыпки (γf), кН/м³", self.calc_gamma_f,
                  "Используется для собственного веса фундамента и грунта на его уступах при расчёте давления p.")
        self.calc_gamma_below = QLineEdit(); self.calc_gamma_below.setPlaceholderText("необязательно; пусто — средневзвешенное по разрезу")
        _form_row(form, "Удельный вес грунта ниже подошвы (γII), кН/м³", self.calc_gamma_below,
                  "СП 22.13330.2016, п. 5.6.10. Пустое поле — автоматическое средневзвешенное значение с учётом УГВ.")
        self.calc_basement_depth = QLineEdit(); self.calc_basement_depth.setPlaceholderText("м; глубина пола подвала от поверхности, 0 — без подвала")
        self.calc_basement_hs = QLineEdit(); self.calc_basement_hs.setPlaceholderText("м; слой грунта над подошвой со стороны подвала")
        self.calc_basement_hcf = QLineEdit(); self.calc_basement_hcf.setPlaceholderText("м; толщина пола подвала")
        self.calc_basement_gamma_cf = QLineEdit(); self.calc_basement_gamma_cf.setPlaceholderText("кН/м³; удельный вес конструкции пола")
        _form_row(form, "Фактическая глубина пола подвала (db,факт), м", self.calc_basement_depth,
                  "Расстояние от уровня планировки до пола подвала; учитываемая в формуле величина db не превышает 2 м.")
        _form_row(form, "Толщина слоя грунта над подошвой со стороны подвала (hs), м", self.calc_basement_hs, SP_BASEMENT_HELP)
        _form_row(form, "Толщина конструкции пола подвала (hcf), м", self.calc_basement_hcf, SP_BASEMENT_HELP)
        _form_row(form, "Удельный вес конструкции пола подвала (γcf), кН/м³", self.calc_basement_gamma_cf, SP_BASEMENT_HELP)
        self.calc_weak = QCheckBox("Применить специальное правило СП")
        _form_row(form, "Учёт слабого слоя (E≤7 МПа)", self.calc_weak,
                  "Включает специальную проверку нижней границы сжимаемой толщи по СП.")
        self.calc_hc_mode = QComboBox()
        self.calc_hc_mode.addItem("Первая расчётная отметка по сетке", HcSearchMode.FIRST_GRID_POINT.value)
        self.calc_hc_mode.addItem("Линейное пересечение между отметками", HcSearchMode.LINEAR_CROSSING.value)
        _form_row(form, "Способ определения границы сжимаемой толщи (Hc)", self.calc_hc_mode,
                  LECTURE_SETTLEMENT_HELP + " Первая отметка следует расчётной сетке; линейное пересечение уточняет положение между узлами.")
        self.calc_step = QLineEdit("0.2")
        _form_row(form, "Относительная толщина слоя (hi/b≤0,4)", self.calc_step,
                  "Лекция №5: толщина каждого элементарного слоя hi должна удовлетворять hi ≤ 0,4·b.")
        formula = QLabel(
            "<b>Расчётное сопротивление грунта основания (R):</b> "
            "R = γc1·γc2/k · [Mγ·kz·b·γII + Mq·d1·γ′II + (Mq−1)·db·γ′II + Mc·cII]"
        )
        formula.setObjectName("Hint")
        formula.setWordWrap(True)
        layout.addWidget(formula)
        button = QPushButton("Рассчитать")
        button.clicked.connect(self._calculate_shallow)
        layout.addWidget(button)
        auto = QPushButton("Подобрать подошву с шагом площади 0,1 м²")
        auto.clicked.connect(self._auto_size)
        layout.addWidget(auto)
        self.calculation_status = self._inline_status()
        layout.addWidget(self.calculation_status)
        tables = QPushButton("Открыть таблицы коэффициентов и пояснения")
        tables.clicked.connect(lambda: self._open_screen("Нормативные коэффициенты"))
        layout.addWidget(tables)
        coefficient_box = QGroupBox("Что программа подставляет в формулу R")
        coefficient_layout = QVBoxLayout(coefficient_box)
        self.r_coeff_table = QTableWidget(0, 5)
        self.r_coeff_table.setHorizontalHeaderLabels([
            "Коэффициент или величина (символ)", "Значение", "Единица измерения", "Источник значения", "Способ получения",
        ])
        self.r_coeff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.r_coeff_table.setAlternatingRowColors(True)
        self.r_coeff_table.verticalHeader().setVisible(False)
        for column in (0, 1, 2):
            self.r_coeff_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.r_coeff_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.r_coeff_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.r_coeff_table.setMinimumHeight(300)
        coefficient_layout.addWidget(self.r_coeff_table)
        layout.addWidget(coefficient_box)
        self.calc_result = QTextBrowser()
        self.calc_result.setMinimumHeight(260)
        layout.addWidget(self.calc_result, 1)
        return page

    def _catalog_schemes_page(self) -> QWidget:
        page, layout = self._page("Справочник схем и нагрузок")
        view = QTextBrowser()
        lines = []
        for record in self.catalog.list("scheme"):
            data = record["data"]
            lines.append(f"Схема {record['key']} — {data['name']}; фундаменты {', '.join(map(str, data['foundation_numbers']))}; источник: {record['source']}")
        view.setPlainText("\n\n".join(lines) or "Схемы ещё не загружены")
        layout.addWidget(view)
        return page

    def _summary_page(self) -> QWidget:
        page, layout = self._page("Сводные результаты")
        self.summary_view = QTextBrowser()
        layout.addWidget(self.summary_view)
        button = QPushButton("Обновить сводку")
        button.clicked.connect(self._refresh_summary)
        layout.addWidget(button)
        return page

    def _refresh_summary(self):
        try:
            self._forms_to_project()
        except ValueError as exc:
            self.summary_view.setPlainText(str(exc))
            return
        runs = self.project.calculation_runs
        if not runs and self.project.calculation_snapshot:
            runs = {self.project.calculation_snapshot.get("load_key", "последний"): {"snapshot": self.project.calculation_snapshot, "settings": self.project.calculation_settings}}
        if not runs:
            self.summary_view.setPlainText("Расчёт ещё не выполнен")
            return
        lines = []
        for key, run in sorted(runs.items()):
            data = run["snapshot"]
            stale = data.get("input_hash") != input_fingerprint(self.project, run.get("settings", {}))
            lines.extend((f"{key}: {'требуется пересчёт' if stale else 'актуально'}",
                f"Расчётное сопротивление (R)={data['R']['value']} кПа; "
                f"среднее давление под подошвой (p)={data['pressure']['mean']['value']} кПа; "
                f"условие p≤R: {'да' if data['mean_pressure_ok'] else 'нет'}; "
                f"отрыв подошвы: {'да' if data['pressure']['uplift'] else 'нет'}"))
            if data.get("settlement"):
                lines.append(
                    f"Глубина сжимаемой толщи (Hc)={data['hc']['depth']['value']} м; "
                    f"осадка фундамента (s)={data['settlement']['total']['value']} м"
                )
            lines.extend(data.get("warnings", []))
            lines.append("")
        self.summary_view.setPlainText("\n".join(lines))

    def _refresh_report_runs(self):
        selected = self.report_run_combo.currentData()
        self.report_run_combo.clear()
        for key in sorted(self.project.calculation_runs):
            self.report_run_combo.addItem(key, key)
        if not self.project.calculation_runs and self.project.calculation_snapshot:
            self.report_run_combo.addItem(self.project.calculation_snapshot.get("load_key", "последний"), "__last__")
        index = self.report_run_combo.findData(selected)
        if index >= 0:
            self.report_run_combo.setCurrentIndex(index)

    def _project_for_report(self) -> Project:
        selected = self.report_run_combo.currentData()
        if selected in self.project.calculation_runs:
            run = self.project.calculation_runs[selected]
            return replace(self.project, calculation_snapshot=run["snapshot"], calculation_settings=run["settings"])
        return self.project

    def _coefficients_page(self) -> QWidget:
        page, outer = self._page("Нормативные коэффициенты")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        note = QLabel(
            "Лекция №3 даёт сокращённую запись формулы R, а лекция №6 требует уточнить R по СП 22.13330.2016. "
            "В расчёте используется полная формула (5.7), включая kz и член для подвала. Таблицы ниже показывают, "
            "какие признаки вводит пользователь и какие значения программа получает автоматически."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        mapping = QTableWidget(0, 3)
        mapping.setHorizontalHeaderLabels(["Название и обозначение величины", "Необходимые исходные данные", "Способ получения значения"])
        mapping_rows = (
            (R_PARAMETER_NAMES["γc1"], "Тип и состояние грунта под подошвой", "Выбор по таблице 5.4"),
            (R_PARAMETER_NAMES["γc2"], "Гибкая/жёсткая схема; для жёсткой L/H", "Выбор или интерполяция по таблице 5.4"),
            (R_PARAMETER_NAMES["k"], "Способ определения φII и cII", "1,0 для испытаний; 1,1 для таблиц приложения А"),
            ("Безразмерные коэффициенты формулы R (Mγ, Mq, Mc)", "φII грунта под подошвой", "Выбор по таблице 5.5"),
            (R_PARAMETER_NAMES["kz"], "Ширина подошвы (b)", "1 при b<10 м; 8/b+0,2 при b≥10 м"),
            (R_PARAMETER_NAMES["b"], "Таблица фундаментов", "Подстановка ширины подошвы"),
            (R_PARAMETER_NAMES["γII"], "Геологический разрез и УГВ", "Средневзвешенное ниже подошвы по п. 5.6.10"),
            (R_PARAMETER_NAMES["d1"], "d; при подвале hs, hcf и γcf", "Глубина или формула (5.8)"),
            (R_PARAMETER_NAMES["γ′II"], "Геологический разрез выше подошвы", "Средневзвешенное по собственному весу слоёв"),
            (R_PARAMETER_NAMES["db"], "Фактическая глубина пола подвала", "0 без подвала; при подвале не более 2 м"),
            (R_PARAMETER_NAMES["cII"], "Таблица грунтов", "Значение грунта непосредственно под подошвой"),
        )
        for values in mapping_rows:
            row = mapping.rowCount(); mapping.insertRow(row)
            for column, value in enumerate(values):
                mapping.setItem(row, column, _item(value))
        mapping.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        mapping.verticalHeader().setVisible(False)
        mapping.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        mapping.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        mapping.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        mapping.setMinimumHeight(390)
        layout.addWidget(mapping)

        table54_box = QGroupBox("Таблица 5.4 — коэффициенты условий работы (γc1, γc2)")
        table54_layout = QVBoxLayout(table54_box)
        table54 = QTableWidget(0, 4)
        table54.setHorizontalHeaderLabels([
            "Грунт и его состояние", "Коэффициент грунта (γc1)",
            "Коэффициент сооружения (γc2), L/H≥4", "Коэффициент сооружения (γc2), L/H≤1,5",
        ])
        for values in WORKING_CONDITIONS_TABLE:
            row = table54.rowCount(); table54.insertRow(row)
            for column, value in enumerate(values):
                table54.setItem(row, column, _item(value))
        table54.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table54.verticalHeader().setVisible(False)
        table54.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            table54.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        table54.setMinimumHeight(285)
        table54_layout.addWidget(table54)
        layout.addWidget(table54_box)

        table55_box = QGroupBox("Таблица 5.5 — безразмерные коэффициенты формулы R (Mγ, Mq, Mc)")
        table55_layout = QVBoxLayout(table55_box)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels([
            "Угол внутреннего трения (φII), °", "Коэффициент (Mγ)", "Коэффициент (Mq)", "Коэффициент (Mc)",
        ])
        for phi, values in M_TABLE.items():
            row = table.rowCount(); table.insertRow(row)
            for col, value in enumerate((phi, *values)):
                table.setItem(row, col, _item(str(value)))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(520)
        table55_layout.addWidget(table)
        layout.addWidget(table55_box)
        return page

    def _r0_reference_page(self) -> QWidget:
        page, layout = self._page("Условное расчётное сопротивление R₀")
        note = QLabel(
            "R₀ используется только для предварительного подбора подошвы. После подбора нужно выполнить окончательную проверку по R. "
            "Программа не экстраполирует значения за границы таблиц. Источник: СП 22.13330.2016, приложение Б, таблицы Б.2–Б.3."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        sand_box = QGroupBox("Таблица Б.2 — пески, R₀ в кПа")
        sand_layout = QVBoxLayout(sand_box)
        sand_table = QTableWidget(0, 4)
        sand_table.setHorizontalHeaderLabels(["Вид песка", "Плотность сложения", "Состояние по влажности", "Условное сопротивление (R₀), кПа"])
        density_names = {"dense": "плотный", "medium": "средней плотности"}
        moisture_names = {"low": "маловлажный", "wet": "влажный", "saturated": "насыщенный водой"}
        for soil_name, densities in SAND_B2.items():
            for density, values in densities.items():
                states = values.items() if isinstance(values, dict) else [("—", values)]
                for moisture, value in states:
                    row = sand_table.rowCount(); sand_table.insertRow(row)
                    for column, text in enumerate((soil_name, density_names[density], moisture_names.get(moisture, "не учитывается",), str(value))):
                        cell = _item(text); cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        sand_table.setItem(row, column, cell)
        sand_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sand_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        sand_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        sand_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        sand_table.setMinimumHeight(260)
        sand_layout.addWidget(sand_table)
        layout.addWidget(sand_box)

        clay_box = QGroupBox("Таблица Б.3 — глинистые непросадочные грунты, R₀ в кПа")
        clay_layout = QVBoxLayout(clay_box)
        clay_table = QTableWidget(0, 4)
        clay_table.setHorizontalHeaderLabels([
            "Вид глинистого грунта", "Коэффициент пористости (e)",
            "Условное сопротивление (R₀) при IL=0, кПа", "Условное сопротивление (R₀) при IL=1, кПа",
        ])
        for soil_name, rows in CLAY_B3.items():
            for void_ratio, r0_il0, r0_il1 in rows:
                row = clay_table.rowCount(); clay_table.insertRow(row)
                for column, text in enumerate((soil_name, void_ratio, r0_il0, r0_il1)):
                    cell = _item(text); cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    clay_table.setItem(row, column, cell)
        clay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            clay_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        clay_table.setColumnWidth(1, 90)
        clay_table.setColumnWidth(2, 160)
        clay_table.setColumnWidth(3, 160)
        clay_table.setMinimumHeight(260)
        clay_layout.addWidget(clay_table)
        layout.addWidget(clay_box)
        return page

    def _settings_page(self) -> QWidget:
        page, layout = self._page("Настройки")
        layout.addWidget(QLabel("Версия приложения: 0.3.1"))
        layout.addWidget(QLabel("Редакция нормативного документа: СП 22.13330.2016 из материалов проекта"))
        layout.addWidget(QLabel(f"Личный справочник: {self.catalog.path}"))
        layout.addWidget(QLabel("Переносимый проект содержит снимки использованных записей справочника."))
        units_box = QGroupBox("Коэффициенты перевода единиц для этого проекта")
        units_form = QFormLayout(units_box)
        self.unit_tf_to_kn = QLineEdit()
        self.unit_gravity = QLineEdit()
        self.unit_mm_to_m = QLineEdit()
        self.unit_mpa_to_kpa = QLineEdit()
        self.unit_density = QLineEdit()
        _form_row(units_form, "Тонна-сила в килоньютонах, кН/тс", self.unit_tf_to_kn,
                  "Коэффициент перевода нагрузок из таблицы задания. Допустимо учебное округление 9,8 или 10.")
        _form_row(units_form, "Ускорение свободного падения (g), м/с²", self.unit_gravity,
                  "Используется для перехода от плотности ρ к удельному весу γ.")
        _form_row(units_form, "Миллиметры в метры, м/мм", self.unit_mm_to_m)
        _form_row(units_form, "Мегапаскали в килопаскали, кПа/МПа", self.unit_mpa_to_kpa)
        _form_row(units_form, "Плотность: г/см³ → кг/м³", self.unit_density)
        reset_units = QPushButton("Вернуть точные значения SI")
        reset_units.clicked.connect(self._reset_unit_conversions)
        units_form.addRow(reset_units)
        unit_note = QLabel("Для учебного округления можно задать 1 тс = 9,8 кН или 10 кН. Выбранные значения сохраняются в .oifproj и попадают в трассировку расчёта.")
        unit_note.setWordWrap(True)
        units_form.addRow(unit_note)
        layout.addWidget(units_box)
        layout.addStretch()
        return page

    def _reports_page(self) -> QWidget:
        page, layout = self._page("Отчёты из снимка расчёта")
        report_form = QFormLayout()
        layout.addLayout(report_form)
        self.report_run_combo = QComboBox()
        _form_row(report_form, "Расчёт для случая", self.report_run_combo)
        self.report_name_edit = QLineEdit()
        self.report_name_edit.setPlaceholderText("Например: Расчёт фундамента 5")
        _form_row(
            report_form, "Название", self.report_name_edit,
            "Одно название используется для файлов Word и Excel; расширение программа добавит сама.",
        )
        self.report_preset = QComboBox()
        for label, value in (("Краткий", "brief"), ("Стандартный", "standard"), ("Полный", "full"), ("Выбранные разделы", "custom")):
            self.report_preset.addItem(label, value)
        self.report_preset.setCurrentIndex(2)
        _form_row(report_form, "Состав", self.report_preset)
        self.report_sections = {}
        names = {"input": "Исходные данные", "results": "Результаты", "pressure": "Давление и эксцентриситет", "settlement": "Осадка по слоям", "trace": "Формулы и коэффициенты", "warnings": "Предупреждения", "sources": "Источники"}
        for key in SECTION_ORDER:
            checkbox = QCheckBox(names[key]); checkbox.setChecked(True)
            checkbox.toggled.connect(self._update_report_section_dependencies)
            self.report_sections[key] = checkbox
            layout.addWidget(checkbox)
        self._update_report_section_dependencies()
        row = QHBoxLayout()
        word = QPushButton("Сохранить Word"); word.clicked.connect(self._export_word)
        excel = QPushButton("Сохранить Excel"); excel.clicked.connect(self._export_excel)
        row.addWidget(word); row.addWidget(excel)
        layout.addLayout(row)
        self.report_status = self._inline_status()
        layout.addWidget(self.report_status)
        layout.addWidget(QLabel("Экспорт доступен после расчёта. При изменении исходных данных программа потребует повторный расчёт."))
        layout.addStretch()
        return page

    def _update_report_section_dependencies(self, *_):
        if not hasattr(self, "report_sections"):
            return
        for section in SECTION_ORDER:
            checkbox = self.report_sections.get(section)
            if checkbox is None:
                continue
            parents = SECTION_DEPENDENCIES.get(section, ())
            available = all(self.report_sections[parent].isChecked() and self.report_sections[parent].isEnabled()
                            for parent in parents)
            if parents and not available:
                checkbox.setChecked(False)
            checkbox.setEnabled(available)

    def _catalog_export_page(self) -> QWidget:
        page, layout = self._page("Экспорт справочника")
        export_form = QFormLayout()
        layout.addLayout(export_form)
        self.catalog_kind = QComboBox()
        for label, value in (("Грунты", "soil"), ("Схемы", "scheme"), ("Нагрузки", "load")):
            self.catalog_kind.addItem(label, value)
        _form_row(export_form, "Тип справочных данных", self.catalog_kind)
        self.catalog_selected_only = QCheckBox("Только грунты выбранного проекта")
        _form_row(export_form, "Объём экспортируемых данных", self.catalog_selected_only)
        row = QHBoxLayout()
        excel = QPushButton("Экспорт Excel…"); excel.clicked.connect(lambda: self._export_catalog("xlsx"))
        pdf = QPushButton("Экспорт PDF…"); pdf.clicked.connect(lambda: self._export_catalog("pdf"))
        row.addWidget(excel); row.addWidget(pdf)
        layout.addLayout(row)
        transfer = QHBoxLayout()
        archive_out = QPushButton("Сохранить .oifcatalog…"); archive_out.clicked.connect(self._export_catalog_archive)
        archive_in = QPushButton("Импортировать .oifcatalog…"); archive_in.clicked.connect(self._import_catalog_archive)
        transfer.addWidget(archive_out); transfer.addWidget(archive_in)
        layout.addLayout(transfer)
        layout.addStretch()
        return page

    def _pending_page(self, message: str) -> QWidget:
        page, layout = self._page("Раздел в разработке")
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
        return page

    def _table_text(self, table: QTableWidget, row: int, column: int) -> str:
        widget = table.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            return str(widget.currentData())
        cell = table.item(row, column)
        return cell.text().strip() if cell else ""

    def _add_layer_row(self, soil: str, top: str, bottom: str):
        row = self.layers_table.rowCount()
        self.layers_table.insertRow(row)
        for column, value in enumerate((soil, top, bottom)):
            self.layers_table.setItem(row, column, _item(value))
        self._set_remove_button(self.layers_table, row, self._remove_layer_row)

    def _add_foundation_row(self, number: str, kind: str, depth: str, width: str, length: str):
        row = self.foundations_table.rowCount()
        self.foundations_table.insertRow(row)
        self.foundations_table.setItem(row, 0, _item(number))
        combo = QComboBox()
        combo.setFixedHeight(30)
        combo.addItem("Столбчатый", FoundationKind.PAD.value)
        combo.addItem("Ленточный", FoundationKind.STRIP.value)
        normalized = FoundationKind.PAD.value if kind in ("столбчатый", FoundationKind.PAD.value) else FoundationKind.STRIP.value
        combo.setCurrentIndex(combo.findData(normalized))
        combo.currentIndexChanged.connect(lambda _index, box=combo: self._foundation_kind_changed(box))
        self.foundations_table.setCellWidget(row, 1, combo)
        for column, value in ((2, depth), (3, width), (4, "1" if normalized == FoundationKind.STRIP.value else length)):
            self.foundations_table.setItem(row, column, _item(value))
        self._set_remove_button(self.foundations_table, row, self._remove_foundation_row)
        self._normalize_foundation_row(row)

    def _set_remove_button(self, table: QTableWidget, row: int, handler):
        button = QPushButton("×")
        button.setObjectName("RemoveRow")
        button.setToolTip("Удалить строку")
        button.setFixedSize(28, 28)
        button.clicked.connect(lambda _checked=False, widget=button: handler(widget))
        table.setCellWidget(row, table.columnCount() - 1, button)

    def _remove_layer_row(self, button: QPushButton):
        row = self.layers_table.indexAt(button.pos()).row()
        if row >= 0:
            self.layers_table.removeRow(row)

    def _remove_foundation_row(self, button: QPushButton):
        row = self.foundations_table.indexAt(button.pos()).row()
        if row < 0:
            return
        number = self._table_text(self.foundations_table, row, 0)
        self.foundations_table.removeRow(row)
        if not number:
            return
        self._syncing_foundations = True
        try:
            for scheme_row in range(self.scheme_foundations_table.rowCount()):
                if self._table_text(self.scheme_foundations_table, scheme_row, 1) == number:
                    self.scheme_foundations_table.item(scheme_row, 0).setCheckState(Qt.CheckState.Unchecked)
                    break
        finally:
            self._syncing_foundations = False

    def _foundation_kind_changed(self, combo: QComboBox):
        row = self.foundations_table.indexAt(combo.pos()).row()
        if row >= 0:
            self._normalize_foundation_row(row)
            if not self._syncing_foundations:
                self._sync_scheme_type_from_foundation(row)

    def _normalize_foundation_row(self, row: int):
        kind = self._table_text(self.foundations_table, row, 1)
        length_cell = self.foundations_table.item(row, 4)
        if length_cell is None:
            length_cell = _item("")
            self.foundations_table.setItem(row, 4, length_cell)
        if kind == FoundationKind.STRIP.value:
            length_cell.setText("1")
            length_cell.setFlags(length_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            length_cell.setToolTip("Для ленты рассматривается участок длиной 1 м")
        else:
            length_cell.setFlags(length_cell.flags() | Qt.ItemFlag.ItemIsEditable)
            length_cell.setToolTip("")

    def _sync_scheme_type_from_foundation(self, row: int):
        number = self._table_text(self.foundations_table, row, 0)
        kind = self._table_text(self.foundations_table, row, 1)
        for scheme_row in range(self.scheme_foundations_table.rowCount()):
            if self._table_text(self.scheme_foundations_table, scheme_row, 1) == number:
                combo = self.scheme_foundations_table.cellWidget(scheme_row, 2)
                if isinstance(combo, QComboBox):
                    combo.setCurrentIndex(combo.findData(kind))
                break

    def _refresh_scheme_foundation_choices(self, scheme_record: dict | None):
        if not hasattr(self, "scheme_foundations_table"):
            return
        available = [] if scheme_record is None else scheme_record["data"].get("foundation_numbers", [])
        selected = {}
        for row in range(self.foundations_table.rowCount()):
            number = self._table_text(self.foundations_table, row, 0)
            if number:
                selected[int(number)] = self._table_text(self.foundations_table, row, 1)
        self._syncing_foundations = True
        try:
            self.scheme_foundations_table.setRowCount(0)
            for number in available:
                row = self.scheme_foundations_table.rowCount()
                self.scheme_foundations_table.insertRow(row)
                checked = _item("")
                checked.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                checked.setCheckState(Qt.CheckState.Checked if number in selected else Qt.CheckState.Unchecked)
                self.scheme_foundations_table.setItem(row, 0, checked)
                number_item = _item(str(number))
                number_item.setFlags(number_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.scheme_foundations_table.setItem(row, 1, number_item)
                combo = QComboBox()
                combo.setFixedHeight(30)
                combo.addItem("Столбчатый", FoundationKind.PAD.value)
                combo.addItem("Ленточный", FoundationKind.STRIP.value)
                combo.setCurrentIndex(combo.findData(selected.get(number, FoundationKind.PAD.value)))
                combo.currentIndexChanged.connect(self._scheme_foundations_changed)
                self.scheme_foundations_table.setCellWidget(row, 2, combo)
        finally:
            self._syncing_foundations = False

    def _scheme_foundations_changed(self, *_):
        if self._syncing_foundations or self._loading_forms:
            return
        self._sync_foundations_from_scheme()
        if self.basement_check.isChecked() and self.basement_height_edit.text().strip() and hasattr(self, "calc_basement_depth"):
            self.calc_basement_depth.setText(self.basement_height_edit.text().strip())

    def _sync_foundations_from_scheme(self):
        existing = {}
        for row in range(self.foundations_table.rowCount()):
            number = self._table_text(self.foundations_table, row, 0)
            if number:
                existing[int(number)] = {
                    "width": self._table_text(self.foundations_table, row, 3),
                    "length": self._table_text(self.foundations_table, row, 4),
                }
        depth = self.common_depth_edit.text().strip()
        chosen = []
        for row in range(self.scheme_foundations_table.rowCount()):
            check = self.scheme_foundations_table.item(row, 0)
            if check and check.checkState() == Qt.CheckState.Checked:
                number = int(self._table_text(self.scheme_foundations_table, row, 1))
                combo = self.scheme_foundations_table.cellWidget(row, 2)
                chosen.append((number, combo.currentData() if isinstance(combo, QComboBox) else FoundationKind.PAD.value))
        self._syncing_foundations = True
        try:
            self.foundations_table.setRowCount(0)
            for number, kind in chosen:
                old = existing.get(number, {})
                self._add_foundation_row(str(number), str(kind), depth, old.get("width", ""), old.get("length", ""))
        finally:
            self._syncing_foundations = False

    def _toggle_basement(self, enabled: bool):
        if hasattr(self, "basement_height_edit"):
            self.basement_height_edit.setEnabled(enabled)
            if not enabled:
                self.basement_height_edit.clear()
        for name in ("calc_basement_depth", "calc_basement_hs", "calc_basement_hcf", "calc_basement_gamma_cf"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(enabled)
        if enabled and hasattr(self, "calc_basement_depth") and self.basement_height_edit.text().strip():
            self.calc_basement_depth.setText(self.basement_height_edit.text().strip())

    def _forms_to_project(self):
        try:
            self.project.name = self.name_edit.text().strip() or "Новый проект"
            self.project.profile_name = self.project_profile_edit.text().strip() or "Основной"
            self.project.profile = Profile(self.profile_combo.currentData())
            number = lambda widget: Decimal(widget.text().strip().replace(",", "."))
            self.project.unit_conversions = UnitConversions(
                tf_to_kn=number(self.unit_tf_to_kn),
                gravity_m_s2=number(self.unit_gravity),
                mm_to_m=number(self.unit_mm_to_m),
                mpa_to_kpa=number(self.unit_mpa_to_kpa),
                g_cm3_to_kg_m3=number(self.unit_density),
            )
            self.project.scheme_number = self.scheme_spin.value()
            self.project.scheme_variant = self.variant_combo.currentData()
            self.project.selected_soils = [int(x.strip()) for x in self.soils_edit.text().split(",") if x.strip()]
            self.project.basement_enabled = self.basement_check.isChecked()
            self.project.basement_height_m = (Decimal(self.basement_height_edit.text().replace(",", "."))
                if self.project.basement_enabled and self.basement_height_edit.text().strip() else None)
            if self.project.basement_enabled and self.project.basement_height_m is None:
                raise ValueError("Для подвала укажите глубину пола подвала от планировочной отметки (db,факт)")
            raw_layers = []
            for row in range(self.layers_table.rowCount()):
                if not any(self._table_text(self.layers_table, row, col) for col in range(3)):
                    continue
                raw_layers.append((f"layer-{row+1}", int(self._table_text(self.layers_table, row, 0)),
                    Decimal(self._table_text(self.layers_table, row, 1).replace(",", ".")),
                    Decimal(self._table_text(self.layers_table, row, 2).replace(",", "."))))
            self.project.geology_coordinate_mode = self.geology_mode_combo.currentData()
            surface_text = self.surface_elevation_edit.text().strip().replace(",", ".")
            requested_surface = Decimal(surface_text) if surface_text and self.project.geology_coordinate_mode == "elevation" else None
            layers, surface = normalize_geology_layers(raw_layers, self.project.geology_coordinate_mode, requested_surface)
            if self.project.geology_coordinate_mode == "elevation" and not surface_text and raw_layers:
                self.surface_elevation_edit.setText(str(surface))
            self.project.surface_elevation_m = surface
            self.project.layers = layers
            water_text = self.water_edit.text().strip().replace(",", ".")
            if not water_text:
                self.project.groundwater_m = None
            elif self.project.geology_coordinate_mode == "elevation":
                water_elevation = Decimal(water_text)
                if surface is None:
                    raise ValueError("Для абсолютной отметки уровня грунтовых вод (УГВ) нужна отметка поверхности земли")
                if water_elevation > surface:
                    raise ValueError(
                        f"Отметка УГВ {water_elevation} м выше поверхности земли {surface} м. "
                        "Проверьте отметки или задайте расчётный уровень после водопонижения."
                    )
                self.project.groundwater_m = surface - water_elevation
            else:
                groundwater_depth = Decimal(water_text)
                if groundwater_depth < 0:
                    raise ValueError("Глубина уровня грунтовых вод (УГВ) от поверхности не может быть отрицательной")
                self.project.groundwater_m = groundwater_depth
            foundations = []
            common_depth = self.common_depth_edit.text().strip()
            for row in range(self.foundations_table.rowCount()):
                if not any(self._table_text(self.foundations_table, row, col) for col in range(5)):
                    continue
                kind = self._table_text(self.foundations_table, row, 1).lower()
                kind = FoundationKind.PAD if kind == "столбчатый" else FoundationKind.STRIP if kind == "ленточный" else FoundationKind(kind)
                def length(col):
                    value = common_depth if col == 2 and common_depth else self._table_text(self.foundations_table, row, col)
                    return Quantity.of(value.replace(",", "."), "m") if value else None
                foundation_length = Quantity.of(1, "m") if kind == FoundationKind.STRIP else length(4)
                foundations.append(FoundationInput(int(self._table_text(self.foundations_table, row, 0)), kind, length(3), foundation_length, length(2)))
            depths = {foundation.depth.to("m").value for foundation in foundations if foundation.depth is not None}
            if len(depths) > 1:
                raise ValueError("Глубина заложения (d) должна быть одинаковой для всех выбранных фундаментов")
            if self.project.basement_enabled and depths and self.project.basement_height_m >= next(iter(depths)):
                raise ValueError("Глубина пола подвала (db,факт) должна быть меньше глубины заложения подошвы (d)")
            self.project.foundations = foundations
            if self.project.basement_enabled:
                self.calc_basement_depth.setText(str(self.project.basement_height_m))
            else:
                self.calc_basement_depth.clear()
            self.project.calculation_settings = self._read_calculation_settings()
            self.project.report_settings = {
                "sections": [key for key, box in self.report_sections.items() if box.isChecked()],
                "filename": self.report_name_edit.text().strip(),
            }
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"Проверьте исходные данные: {exc}") from exc

    def _read_calculation_settings(self) -> dict:
        return {
            "foundation": self.calc_foundation.value(), "combination": self.calc_combination.currentData(),
            "rigid": self.calc_rigid.currentData(), "ratio": self.calc_ratio.text().strip(),
            "moisture": self.calc_moisture.currentData(), "loose": self.calc_loose.isChecked(),
            "strength_tests": self.calc_strength_tests.currentData(),
            "moment": self.calc_moment.text().strip(), "moment_basis": self.calc_moment_basis.text().strip(),
            "gamma_f": self.calc_gamma_f.text().strip(), "gamma_below": self.calc_gamma_below.text().strip(),
            "basement_depth": self.calc_basement_depth.text().strip(),
            "basement_hs": self.calc_basement_hs.text().strip(),
            "basement_hcf": self.calc_basement_hcf.text().strip(),
            "basement_gamma_cf": self.calc_basement_gamma_cf.text().strip(),
            "water_absent": self.calc_water_absent.isChecked(), "submerged": self.calc_submerged.text().strip(),
            "weak": self.calc_weak.isChecked(), "hc_mode": self.calc_hc_mode.currentData(),
            "step": self.calc_step.text().strip(),
            "prelim_gamma_f": self.prelim_gamma_f.text().strip(),
            "sand_density": self.sand_density.currentData(),
            "prelim_sand_moisture": self.sand_moisture.currentData(),
        }

    def _load_project_into_forms(self):
        self._loading_forms = True
        p = self.project
        self.name_edit.setText(p.name)
        self.project_profile_edit.setText(p.profile_name)
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(p.profile))
        self.scheme_spin.setValue(p.scheme_number or 18)
        self.variant_combo.setCurrentIndex(max(0, self.variant_combo.findData(p.scheme_variant)))
        self.soils_edit.setText(", ".join(map(str, p.selected_soils)))
        self.geology_mode_combo.setCurrentIndex(max(0, self.geology_mode_combo.findData(p.geology_coordinate_mode)))
        self.surface_elevation_edit.setText("" if p.surface_elevation_m is None else str(p.surface_elevation_m))
        self._update_geology_mode()
        if p.groundwater_m is None:
            self.water_edit.clear()
        elif p.geology_coordinate_mode == "elevation" and p.surface_elevation_m is not None:
            self.water_edit.setText(str(p.surface_elevation_m - p.groundwater_m))
        else:
            self.water_edit.setText(str(p.groundwater_m))
        self.layers_table.setRowCount(0)
        for layer in p.layers:
            if p.geology_coordinate_mode == "elevation" and p.surface_elevation_m is not None:
                top, bottom = p.surface_elevation_m - layer.top_m, p.surface_elevation_m - layer.bottom_m
            else:
                top, bottom = layer.top_m, layer.bottom_m
            self._add_layer_row(str(layer.soil_number), str(top), str(bottom))
        self.foundations_table.setRowCount(0)
        for foundation in p.foundations:
            text = lambda q: "" if q is None else str(q.to("m").value)
            self._add_foundation_row(str(foundation.number), "столбчатый" if foundation.kind == FoundationKind.PAD else "ленточный", text(foundation.depth), text(foundation.width), text(foundation.length))
        depths = {str(foundation.depth.to("m").value) for foundation in p.foundations if foundation.depth is not None}
        self.common_depth_edit.setText(next(iter(depths)) if len(depths) == 1 else "")
        self.basement_check.setChecked(p.basement_enabled)
        self.basement_height_edit.setText("" if p.basement_height_m is None else str(p.basement_height_m))
        settings = p.calculation_settings
        self.calc_foundation.setValue(settings.get("foundation", 3))
        self.calc_combination.setCurrentIndex(max(0, self.calc_combination.findData(settings.get("combination", 1))))
        self.calc_rigid.setCurrentIndex(max(0, self.calc_rigid.findData(settings.get("rigid"))))
        self.calc_ratio.setText(settings.get("ratio", ""))
        self.calc_moisture.setCurrentIndex(max(0, self.calc_moisture.findData(settings.get("moisture"))))
        self.calc_loose.setChecked(settings.get("loose", False))
        self.calc_strength_tests.setCurrentIndex(max(0, self.calc_strength_tests.findData(settings.get("strength_tests"))))
        for name, key in (("calc_moment", "moment"), ("calc_moment_basis", "moment_basis"), ("calc_gamma_f", "gamma_f"), ("calc_gamma_below", "gamma_below"), ("calc_basement_depth", "basement_depth"), ("calc_basement_hs", "basement_hs"), ("calc_basement_hcf", "basement_hcf"), ("calc_basement_gamma_cf", "basement_gamma_cf"), ("calc_submerged", "submerged"), ("calc_step", "step")):
            getattr(self, name).setText(settings.get(key, "0.2" if key == "step" else ""))
        self.calc_water_absent.setChecked(settings.get("water_absent", False))
        self.calc_weak.setChecked(settings.get("weak", False))
        self.calc_hc_mode.setCurrentIndex(max(0, self.calc_hc_mode.findData(settings.get("hc_mode", HcSearchMode.FIRST_GRID_POINT.value))))
        self.prelim_gamma_f.setText(settings.get("prelim_gamma_f", ""))
        self.sand_density.setCurrentIndex(max(0, self.sand_density.findData(settings.get("sand_density"))))
        self.sand_moisture.setCurrentIndex(max(0, self.sand_moisture.findData(settings.get("prelim_sand_moisture"))))
        conversions = p.unit_conversions
        self.unit_tf_to_kn.setText(str(conversions.tf_to_kn))
        self.unit_gravity.setText(str(conversions.gravity_m_s2))
        self.unit_mm_to_m.setText(str(conversions.mm_to_m))
        self.unit_mpa_to_kpa.setText(str(conversions.mpa_to_kpa))
        self.unit_density.setText(str(conversions.g_cm3_to_kg_m3))
        self.report_name_edit.setText(p.report_settings.get("filename") or p.name)
        report_sections = p.report_settings.get("sections", SECTION_ORDER)
        for key, checkbox in self.report_sections.items():
            checkbox.setChecked(key in report_sections)
        self._loading_forms = False
        self._show_loads()
        self._toggle_basement(p.basement_enabled)
        self._refresh_report_runs()
        calculation_snapshot = p.calculation_snapshot or {}
        self._show_r_parameters(calculation_snapshot.get("inputs", {}).get("R_parameters", []))
        for name in ("project_status", "preliminary_status", "calculation_status", "report_status"):
            if hasattr(self, name):
                getattr(self, name).setVisible(False)

    def _show_loads(self, *_):
        scheme = self.scheme_spin.value()
        variant = self.variant_combo.currentData()
        scheme_record = self._active_catalog().get("scheme", str(scheme))
        scheme_name = scheme_record["data"]["name"] if scheme_record else "нет в справочнике"
        lines = [f"Схема {scheme} — {scheme_name}; {'чётный' if variant == 'even' else 'нечётный'} вариант", "Источник: ЗАДАНИЕ на КР, табл. 2. Исходные единицы: тс и тс·м.", ""]
        figure = files("oif").joinpath(f"data/schemes/{scheme}.png")
        pixmap = QPixmap()
        if figure.is_file() and pixmap.loadFromData(figure.read_bytes()):
            self.scheme_image.setPixmap(pixmap.scaled(460, 570, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.scheme_image.setPixmap(QPixmap())
            self.scheme_image.setText("Для этой схемы нет чертежа")
        foundation_numbers = scheme_record["data"].get("foundation_numbers", []) if scheme_record else []
        for foundation in foundation_numbers:
            entries = []
            for combination in (1, 2):
                record = self._active_catalog().get("load", f"{scheme}:{variant}:{foundation}:{combination}")
                if record:
                    d = record["data"]
                    entries.append(
                        f"{combination}-е сочетание: вертикальная нагрузка (NII)={d['N']['value']} тс; "
                        f"изгибающий момент (MII)={d['M']['value'] if d['M'] else '—'} тс·м; "
                        f"поперечная сила (TII)={d['T']['value'] if d['T'] else '—'} тс"
                    )
            if entries:
                lines.append(f"Фундамент №{foundation}: " + "  |  ".join(entries))
        if len(lines) == 3:
            lines.append("Для выбранной схемы данные ещё не оцифрованы.")
        self.loads_view.setPlainText("\n".join(lines))
        self._refresh_scheme_foundation_choices(scheme_record)

    def _preliminary_calculation(self):
        self._forms_to_project()
        gamma = Quantity.of(Decimal(self.prelim_gamma_f.text().replace(",", ".")), "kN/m3") if self.prelim_gamma_f.text().strip() else None
        return preliminary_for_foundation(self.project, self._active_catalog(), self.prelim_foundation.value(), self.prelim_combination.currentData(), mean_unit_weight=gamma, sand_density=self.sand_density.currentData(), sand_moisture=self.sand_moisture.currentData())

    def _calculate_preliminary(self):
        self._set_inline_status(self.preliminary_status, "Выполняю предварительный расчёт…", "busy")
        try:
            result = self._preliminary_calculation()
            lines = [result.message]
            if result.r0 and result.area:
                parameters = ", ".join(f"{key}={value}" for key, value in (result.r0_parameters or {}).items())
                lines.extend((f"Грунт под подошвой: №{result.soil_number}", f"Нагрузка: {result.load_key}",
                    f"Таблица для R₀: {result.r0_table}", f"Параметры выбора R₀: {parameters}", result.r0_explanation,
                    f"Условное расчётное сопротивление (R₀) = {result.r0.value:.3f} кПа",
                    f"Требуемая предварительная площадь подошвы (A) = {result.area.value:.3f} м²",
                    "Площадь ещё не округлена и не проверена по окончательному R."))
            self.preliminary_result.setPlainText("\n".join(lines))
            self._set_inline_status(self.preliminary_status, "✓ Предварительный расчёт выполнен", "success")
        except ValueError as exc:
            self._set_inline_status(self.preliminary_status, f"Расчёт не выполнен: {exc}", "error")
            QMessageBox.warning(self, "Исходные данные", str(exc))

    def _apply_preliminary(self):
        self._set_inline_status(self.preliminary_status, "Применяю предварительные размеры…", "busy")
        try:
            result = self._preliminary_calculation()
            if result.area is None:
                raise ValueError(result.message)
            foundation = next(f for f in self.project.foundations if f.number == self.prelim_foundation.value())
            geometry = preliminary_geometry(result.area, foundation.kind, width=foundation.width, length=foundation.length)
            for row in range(self.foundations_table.rowCount()):
                if self._table_text(self.foundations_table, row, 0) == str(foundation.number):
                    self.foundations_table.setItem(row, 3, _item(str(geometry.width.value)))
                    self.foundations_table.setItem(row, 4, _item(str(geometry.length.value)))
                    break
            self.preliminary_result.setPlainText(
                f"{result.message}\n{result.r0_table}\n"
                f"{', '.join(f'{key}={value}' for key, value in (result.r0_parameters or {}).items())}\n"
                f"Условное расчётное сопротивление (R₀)={result.r0.value:.3f} кПа; "
                f"требуемая площадь подошвы (Aтреб)={result.area.value:.3f} м²\n"
                f"Предложено: ширина подошвы (b)={geometry.width.value} м, "
                f"длина подошвы (l)={geometry.length.value} м, площадь подошвы (A)={geometry.area.value} м². "
                f"{geometry.rule}. Выполните окончательную проверку по R."
            )
            self._set_inline_status(self.preliminary_status, "✓ Размеры применены к фундаменту", "success")
        except (ValueError, StopIteration) as exc:
            self._set_inline_status(self.preliminary_status, f"Размеры не применены: {exc}", "error")
            QMessageBox.warning(self, "Предварительный подбор", str(exc))

    def _calculate_shallow(self):
        self._set_inline_status(self.calculation_status, "Выполняю расчёт…", "busy")
        try:
            self._forms_to_project()
            raw = self.project.calculation_settings
            number = lambda value: Decimal(value.replace(",", "."))
            submerged = {}
            for piece in raw["submerged"].split(","):
                if piece.strip():
                    key, value = piece.split(":", 1)
                    submerged[int(key.strip())] = Quantity.of(number(value.strip()), "kN/m3")
            options = ShallowOptions(
                combination=raw["combination"], rigid_scheme=raw["rigid"],
                length_height_ratio=number(raw["ratio"]) if raw["ratio"] else None,
                sand_moisture=raw["moisture"], loose_sand=raw["loose"],
                strength_from_tests=raw["strength_tests"],
                moment_at_base=Quantity.of(number(raw["moment"]), "tf*m"),
                moment_basis=raw["moment_basis"],
                foundation_unit_weight=Quantity.of(number(raw["gamma_f"]), "kN/m3"),
                gamma_below_base=Quantity.of(number(raw["gamma_below"]), "kN/m3") if raw["gamma_below"] else None,
                groundwater_absent=raw["water_absent"], submerged_gamma_by_soil=submerged,
                basement_depth=Quantity.of(number(raw["basement_depth"]), "m") if raw["basement_depth"] else Quantity.of(0, "m"),
                basement_soil_height=Quantity.of(number(raw["basement_hs"]), "m") if raw["basement_hs"] else None,
                basement_floor_thickness=Quantity.of(number(raw["basement_hcf"]), "m") if raw["basement_hcf"] else None,
                basement_floor_unit_weight=Quantity.of(number(raw["basement_gamma_cf"]), "kN/m3") if raw["basement_gamma_cf"] else None,
                hc_mode=HcSearchMode(raw["hc_mode"]), hc_step_fraction=number(raw["step"]),
                weak_layer_selected=raw["weak"])
            result = ShallowFoundationCalculator(self._active_catalog()).calculate(self.project, raw["foundation"], options)
            self._last_options = options
            snapshot = result.as_snapshot()
            self._show_r_parameters(snapshot.get("inputs", {}).get("R_parameters", []))
            snapshot["input_hash"] = input_fingerprint(self.project)
            self.project.calculation_snapshot = snapshot
            self.project.calculation_runs[result.load_key] = {"snapshot": snapshot, "settings": dict(raw)}
            self._refresh_report_runs()
            active = self._active_catalog()
            used_soils = {str(layer.soil_number): active.get("soil", str(layer.soil_number)) for layer in self.project.layers}
            scheme = active.get("scheme", str(self.project.scheme_number))
            loads = {}
            for foundation in self.project.foundations:
                for combination in (1, 2):
                    key = f"{self.project.scheme_number}:{self.project.scheme_variant}:{foundation.number}:{combination}"
                    record = active.get("load", key)
                    if record:
                        loads[key] = record
            self.project.catalog_snapshot = {"soils": used_soils, "loads": loads, "scheme": scheme}
            p = result.pressure
            lines = [f"Фундамент №{result.foundation_number}; сочетание нагрузок {result.combination}",
                     f"Расчётное сопротивление (R) = {result.resistance.value:.3f} кПа; "
                     f"среднее давление под подошвой (p) = {p.mean.value:.3f} кПа; условие p≤R: {'да' if result.mean_pressure_ok else 'нет'}",
                     f"Эксцентриситет нагрузки (e) = {p.eccentricity.value:.4f} м; "
                     f"граница ядра сечения = {p.kern_limit.value:.4f} м ({'b/6' if next(f for f in self.project.foundations if f.number == result.foundation_number).kind == FoundationKind.STRIP else 'l/6'}); "
                     f"отрыв подошвы: {'да' if p.uplift else 'нет'}",
                     f"Коэффициент условий работы грунта (γc1)={result.working_conditions.gamma_c1}; "
                     f"коэффициент условий работы сооружения (γc2)={result.working_conditions.gamma_c2}: {result.working_conditions.category}",
                     f"Дополнительное давление на основание (p0) = {result.net_pressure.value:.3f} кПа"]
            if options.basement_depth.to("m").value:
                lines.append(
                    f"Подвал: приведённая глубина заложения (d1)={result.inputs['d1']['value']} м; "
                    f"учитываемая глубина подвала (db)={result.inputs['db']['value']} м по формуле (5.8)"
                )
            if p.edge_max:
                lines.append(
                    f"Минимальное краевое давление (pmin)={p.edge_min.value:.3f} кПа; "
                    f"максимальное краевое давление (pmax)={p.edge_max.value:.3f} кПа; "
                    f"условие pкрай≤1,2R: {'да' if p.edge_limit_ok else 'нет'}"
                )
            if result.hc and result.settlement:
                lines.append(
                    f"Глубина сжимаемой толщи (Hc)={result.hc.depth.value:.3f} м по условию "
                    f"σzp≤{result.hc.threshold}·σzg; осадка фундамента (s)={result.settlement.total.to('mm').value:.2f} мм"
                )
                lines.append(f"Элементарных слоёв: {len(result.settlement.layers)}")
            lines.extend(("", "Формулы и источники:"))
            lines.extend(f"{key}: {formula}" for key, formula in snapshot["formulas"].items())
            lines.extend(f"{key}: {source}" for key, source in result.sources.items())
            if result.warnings:
                lines.extend(("", "Предупреждения:", *result.warnings))
            self.calc_result.setPlainText("\n".join(lines))
            self.statusBar().showMessage("Расчёт выполнен; сохраните проект для переноса снимка", 8000)
            self._set_inline_status(
                self.calculation_status,
                "✓ Расчёт выполнен. Сохраните проект, чтобы записать результат.",
                "success",
            )
            return True
        except (ValueError, KeyError, ArithmeticError) as exc:
            self._set_inline_status(self.calculation_status, f"Расчёт не выполнен: {exc}", "error")
            QMessageBox.warning(self, "Расчёт не выполнен", str(exc))
            return False

    def _show_r_parameters(self, parameters):
        if not hasattr(self, "r_coeff_table"):
            return
        self.r_coeff_table.setRowCount(0)
        for parameter in parameters:
            row = self.r_coeff_table.rowCount()
            self.r_coeff_table.insertRow(row)
            symbol = parameter.get("symbol", "")
            values = (
                R_PARAMETER_NAMES.get(symbol, symbol), parameter.get("value", ""), parameter.get("unit", ""),
                parameter.get("source", ""), parameter.get("mode", ""),
            )
            for column, value in enumerate(values):
                self.r_coeff_table.setItem(row, column, _item(str(value)))

    def _auto_size(self):
        self._set_inline_status(self.calculation_status, "Подбираю размеры подошвы…", "busy")
        try:
            self._forms_to_project()
            snapshot = self.project.calculation_snapshot
            if snapshot is None or snapshot.get("input_hash") != input_fingerprint(self.project) or not hasattr(self, "_last_options"):
                raise ValueError("Сначала выполните расчёт с текущими исходными данными")
            if not snapshot["pressure"]["uplift"] and Decimal(snapshot["pressure"]["mean"]["value"]) <= Decimal(snapshot["R"]["value"]):
                raise ValueError("Отрыва подошвы нет и p≤R; увеличение площади не требуется")
            number = self.calc_foundation.value()
            foundation = next(f for f in self.project.foundations if f.number == number)
            load = self._active_catalog().get("load", snapshot["load_key"])
            result = auto_size_area(
                vertical=Quantity.from_dict(load["data"]["N"]).to("kN", self.project.unit_conversions),
                moment_at_base=self._last_options.moment_at_base.to("kN*m", self.project.unit_conversions), width=foundation.width,
                initial_length=foundation.length, depth=foundation.depth,
                foundation_unit_weight=self._last_options.foundation_unit_weight,
                resistance=Quantity.from_dict(snapshot["R"]), kind=foundation.kind)
            for row in range(self.foundations_table.rowCount()):
                if self._table_text(self.foundations_table, row, 0) == str(number):
                    self.foundations_table.setItem(row, 3, _item(str(result.width.value)))
                    self.foundations_table.setItem(row, 4, _item(str(result.length.value)))
                    self._normalize_foundation_row(row)
                    break
            if not self._calculate_shallow():
                return
            self.calc_result.append(f"\nАвтоматический подбор: A={result.area.value} м², b={result.width.value} м, l={result.length.value} м. {result.rule}")
            self._set_inline_status(self.calculation_status, "✓ Подбор подошвы выполнен, расчёт обновлён", "success")
        except (ValueError, KeyError, StopIteration) as exc:
            self._set_inline_status(self.calculation_status, f"Подбор не выполнен: {exc}", "error")
            QMessageBox.warning(self, "Подбор площади", str(exc))

    def _report_target(self, extension: str) -> Path | None:
        self._forms_to_project()
        entered = self.report_name_edit.text().strip()
        if not entered:
            raise ValueError("Введите название отчёта")
        filename = safe_path_component(entered, "Отчёт")
        if filename != entered:
            self.report_name_edit.setText(filename)
            self.project.report_settings["filename"] = filename
            self._set_inline_status(
                self.report_status,
                f"Недопустимые символы заменены. Имя файлов: {filename}",
                "info",
            )
        if self.project_path is None:
            self._set_inline_status(
                self.report_status,
                "Сначала выберите папку проекта — отчёты будут сохранены в неё.",
                "info",
            )
            self._save_as()
            if self.project_path is None:
                self._set_inline_status(self.report_status, "Сохранение отчёта отменено", "info")
                return None
        save_project(self.project, self.project_path)
        target = self.project_path.parent / f"{filename}.{extension}"
        if target.exists():
            answer = QMessageBox.question(
                self,
                "Отчёт уже существует",
                f"Файл {target.name} уже существует. Заменить его?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._set_inline_status(self.report_status, "Сохранение отчёта отменено", "info")
                return None
        return target

    def _export_word(self):
        try:
            self._set_inline_status(self.report_status, "Сохраняю отчёт Word…", "busy")
            path = self._report_target("docx")
            if path is None:
                return
            self._set_inline_status(self.report_status, "Сохраняю отчёт Word…", "busy")
            export_word(self._project_for_report(), path, preset=self.report_preset.currentData())
            self.statusBar().showMessage(f"Word сохранён: {path}", 8000)
            self._set_inline_status(
                self.report_status, f"✓ Отчёт Word сохранён: {path.name}", "success", str(path)
            )
        except Exception as exc:
            self._set_inline_status(self.report_status, f"Отчёт Word не сохранён: {exc}", "error")
            QMessageBox.warning(self, "Не удалось создать Word", str(exc))

    def _export_excel(self):
        try:
            self._set_inline_status(self.report_status, "Сохраняю отчёт Excel…", "busy")
            path = self._report_target("xlsx")
            if path is None:
                return
            self._set_inline_status(self.report_status, "Сохраняю отчёт Excel…", "busy")
            export_excel(self._project_for_report(), path, preset=self.report_preset.currentData())
            self.statusBar().showMessage(f"Excel сохранён: {path}", 8000)
            self._set_inline_status(
                self.report_status, f"✓ Отчёт Excel сохранён: {path.name}", "success", str(path)
            )
        except Exception as exc:
            self._set_inline_status(self.report_status, f"Отчёт Excel не сохранён: {exc}", "error")
            QMessageBox.warning(self, "Не удалось создать Excel", str(exc))

    def _export_catalog(self, extension: str):
        kind = self.catalog_kind.currentData()
        if self.catalog_selected_only.isChecked() and kind != "soil":
            QMessageBox.warning(self, "Экспорт справочника", "Выбор записей проекта доступен только для грунтов")
            return
        keys = {str(number) for number in self.project.selected_soils} if self.catalog_selected_only.isChecked() else None
        default = self.project_path.parent / f"справочник_{kind}.{extension}" if self.project_path else Path(f"справочник_{kind}.{extension}")
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт справочника", str(default), f"{extension.upper()} (*.{extension})")
        if path:
            try:
                if extension == "xlsx":
                    export_catalog_excel(self.catalog, path, kind=kind, keys=keys)
                else:
                    export_catalog_pdf(self.catalog, path, kind=kind, keys=keys)
                self.statusBar().showMessage(f"Справочник сохранён: {path}", 8000)
            except Exception as exc:
                QMessageBox.warning(self, "Не удалось экспортировать справочник", str(exc))

    def _add_custom_soil(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Новый грунт в личном справочнике")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        fields = {}
        labels = (("key", "Номер грунта"), ("name", "Наименование грунта"),
                  ("geological_index", "Геологический индекс"),
                  ("rho_ii_g_cm3", "Расчётная плотность по II группе (ρII), г/см³"),
                  ("phi_ii_deg", "Расчётный угол внутреннего трения по II группе (φII), °"),
                  ("c_ii_kpa", "Расчётное удельное сцепление по II группе (cII), кПа"),
                  ("e_mpa", "Модуль деформации (E), МПа"),
                  ("rho_i_g_cm3", "Расчётная плотность по I группе (ρI), г/см³"),
                  ("phi_i_deg", "Расчётный угол внутреннего трения по I группе (φI), °"),
                  ("c_i_kpa", "Расчётное удельное сцепление по I группе (cI), кПа"),
                  ("rho_s_g_cm3", "Плотность частиц грунта (ρs), г/см³"),
                  ("w", "Природная влажность (W), доля единицы"),
                  ("wl", "Влажность на границе текучести (WL), доля единицы"),
                  ("wp", "Влажность на границе раскатывания (WP), доля единицы"),
                  ("filtration_m_day", "Коэффициент фильтрации (Kф), м/сут"),
                  ("source", "Источник и страница"))
        for key, label in labels:
            edit = QLineEdit()
            fields[key] = edit
            form.addRow(label, edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            raw = {key: edit.text().strip() for key, edit in fields.items()}
            key = str(int(raw.pop("key")))
            source = raw.pop("source")
            if not source or not raw["name"] or not raw["geological_index"]:
                raise ValueError("Нужны название, индекс и источник")
            for field in ("rho_ii_g_cm3", "phi_ii_deg", "c_ii_kpa", "e_mpa", "rho_i_g_cm3", "phi_i_deg", "c_i_kpa", "rho_s_g_cm3", "w", "wl", "wp", "filtration_m_day"):
                value = raw[field].replace(",", ".")
                raw[field] = str(Decimal(value)) if value else None
            required = ("rho_ii_g_cm3", "phi_ii_deg", "c_ii_kpa", "e_mpa", "rho_s_g_cm3", "w")
            if any(raw[field] is None for field in required):
                raise ValueError("Не заполнены обязательные расчётные характеристики")
            if Decimal(raw["rho_ii_g_cm3"]) <= 0 or Decimal(raw["e_mpa"]) <= 0:
                raise ValueError("Расчётная плотность (ρII) и модуль деформации (E) должны быть положительными")
            if (raw["wl"] is None) != (raw["wp"] is None):
                raise ValueError(
                    "Влажность на границе текучести (WL) и влажность на границе раскатывания (WP) задаются вместе"
                )
            self.catalog.put("soil", key, 1, raw, source, builtin=False)
            self._refresh_soil_catalog()
            self.statusBar().showMessage(f"Грунт №{key} добавлен", 6000)
        except Exception as exc:
            QMessageBox.warning(self, "Грунт не добавлен", str(exc))

    def _delete_custom_soil(self, key: str):
        answer = QMessageBox.question(
            self, "Удаление грунта",
            f"Удалить пользовательский грунт №{key} и все его версии? Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.catalog.delete_user_record("soil", key)
            selected = [part.strip() for part in self.soils_edit.text().split(",") if part.strip() and part.strip() != key]
            self.soils_edit.setText(", ".join(selected))
            self.project.selected_soils = [number for number in self.project.selected_soils if str(number) != key]
            self._refresh_soil_catalog()
            self.statusBar().showMessage(f"Пользовательский грунт №{key} удалён", 6000)
        except Exception as exc:
            QMessageBox.warning(self, "Грунт не удалён", str(exc))

    def _export_catalog_archive(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить справочник", "личный_справочник.oifcatalog", "Каталог ОИФ (*.oifcatalog)")
        if path:
            try:
                export_catalog(self.catalog, path, author="пользователь")
                self.statusBar().showMessage(f"Каталог сохранён: {path}", 6000)
            except Exception as exc:
                QMessageBox.warning(self, "Не удалось сохранить каталог", str(exc))

    def _import_catalog_archive(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импортировать справочник", "", "Каталог ОИФ (*.oifcatalog)")
        if path:
            try:
                preview = preview_catalog_import(path, self.catalog)
                if preview["conflicts"]:
                    raise ValueError(f"Конфликт версий: {preview['conflicts']}")
                result = import_catalog(path, self.catalog)
                self._refresh_soil_catalog()
                self.statusBar().showMessage(f"Импортировано записей: {result['added']}", 8000)
            except Exception as exc:
                QMessageBox.warning(self, "Не удалось импортировать каталог", str(exc))

    def _reset_unit_conversions(self):
        defaults = UnitConversions()
        self.unit_tf_to_kn.setText(str(defaults.tf_to_kn))
        self.unit_gravity.setText(str(defaults.gravity_m_s2))
        self.unit_mm_to_m.setText(str(defaults.mm_to_m))
        self.unit_mpa_to_kpa.setText(str(defaults.mpa_to_kpa))
        self.unit_density.setText(str(defaults.g_cm3_to_kg_m3))

    def _select_project_parent(self):
        initial = self.project_parent_edit.text().strip() or str(Path.home() / "Documents")
        path = QFileDialog.getExistingDirectory(self, "Выберите родительскую папку для проекта", initial)
        if path:
            self.project_parent_edit.setText(path)

    def _update_project_path_preview(self, *_):
        if not hasattr(self, "project_path_preview"):
            return
        parent = self.project_parent_edit.text().strip() if hasattr(self, "project_parent_edit") else ""
        if not parent:
            self.project_path_preview.setText("При первом сохранении программа предложит выбрать родительскую папку.")
            return
        folder, project_file = project_workspace_paths(
            parent, self.name_edit.text().strip() or "Новый проект",
            self.project_profile_edit.text().strip() or "Основной",
        )
        self.project_path_preview.setText(f"{folder}\nФайл проекта: {project_file.name}")

    def _new(self):
        self.project = Project("Новый проект")
        self.project_path = None
        self.project_parent_edit.clear()
        self._load_project_into_forms()

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "", "Проекты (*.oifproj)")
        if path:
            try:
                self.project = load_project(path)
                self.project_path = Path(path)
                self.project_parent_edit.setText(str(self.project_path.parent.parent))
                self._load_project_into_forms()
            except Exception as exc:
                QMessageBox.critical(self, "Не удалось открыть проект", str(exc))

    def _save(self):
        if self.project_path is None:
            self._save_as()
            return
        self._set_inline_status(self.project_status, "Сохраняю проект…", "busy")
        try:
            self._forms_to_project()
            save_project(self.project, self.project_path)
            self.statusBar().showMessage(f"Сохранено: {self.project_path}", 5000)
            self._set_inline_status(
                self.project_status,
                f"✓ Проект успешно сохранён: {self.project_path.name}",
                "success",
                str(self.project_path),
            )
        except Exception as exc:
            self._set_inline_status(self.project_status, f"Проект не сохранён: {exc}", "error")
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))

    def _save_as(self):
        self._set_inline_status(self.project_status, "Создаю папку и сохраняю проект…", "busy")
        try:
            self._forms_to_project()
            parent = self.project_parent_edit.text().strip()
            if not parent:
                parent = QFileDialog.getExistingDirectory(
                    self, "Выерите папку, внутри которой создать папку проекта",
                    str(Path.home() / "Documents"),
                )
                if not parent:
                    self._set_inline_status(self.project_status, "Сохранение проекта отменено", "info")
                    return
                self.project_parent_edit.setText(parent)
            _, path = project_workspace_paths(parent, self.project.name, self.project.profile_name)
            if path.exists():
                answer = QMessageBox.question(
                    self, "Проект уже существует",
                    f"Файл {path} уже существует. Заменить его?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._set_inline_status(self.project_status, "Сохранение проекта отменено", "info")
                    return
            save_project(self.project, path)
            self.project_path = path
            self.statusBar().showMessage(f"Проект создан в папке: {path.parent}", 8000)
            self._set_inline_status(
                self.project_status,
                f"✓ Проект успешно сохранён: {path.name}",
                "success",
                str(path),
            )
        except Exception as exc:
            self._set_inline_status(self.project_status, f"Проект не сохранён: {exc}", "error")
            QMessageBox.warning(self, "Не удалось создать папку проекта", str(exc))


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
