"""Быстрая проверка запуска и ключевых связей интерфейса без записи в каталог пользователя."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from oif.ui.main_window import MainWindow
from oif.project_io import load_project


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="oif-ui-smoke-") as directory:
        window = MainWindow(Path(directory) / "catalog.sqlite")
        assert "Грунты, разрез и УГВ" in window._screens
        assert "Выбранные грунты" not in window._screens
        flags = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive
        assert not window.nav.findItems("Расчётное сопротивление", flags, 0)
        assert not window.nav.findItems("Осадка", flags, 0)
        window.geology_mode_combo.setCurrentIndex(window.geology_mode_combo.findData("elevation"))
        window.surface_elevation_edit.setText("130")
        window.water_edit.setText("124.5")
        window.layers_table.setRowCount(0)
        for row in (("29", "130", "124"), ("40", "124", "118"), ("81", "118", "110")):
            window._add_layer_row(*row)
        window._forms_to_project()
        assert [(str(layer.top_m), str(layer.bottom_m)) for layer in window.project.layers] == [
            ("0", "6"), ("6", "12"), ("12", "20")]
        assert str(window.project.groundwater_m) == "5.5"

        window.foundations_table.setRowCount(0)
        window._add_foundation_row("3", "pad", "2", "", "")
        window.pages.setCurrentIndex(window._screens["Исходные параметры фундаментов"])
        window.show()
        app.processEvents()
        window.foundations_table.cellWidget(0, 5).click()
        assert window.foundations_table.rowCount() == 0
        assert "Таблицы R₀" in window._screens
        labels = {label.text() for label in window.findChildren(QLabel)}
        assert "Глубина заложения фундамента (d), м" in labels
        assert "Изгибающий момент на уровне подошвы (M), тс·м" in labels
        assert "Удельный вес грунта ниже подошвы (γII), кН/м³" in labels
        assert "Толщина конструкции пола подвала (hcf), м" in labels
        assert "Способ определения границы сжимаемой толщи (Hc)" in labels
        assert "Расчёт для случая" in labels
        assert "Название" in labels
        assert "Состав" in labels
        assert window.foundations_table.horizontalHeaderItem(3).text() == "Ширина подошвы (b), м"
        assert window.report_name_edit.placeholderText() == "Например: Расчёт фундамента 5"
        window.project_path = Path(directory) / "feedback.oifproj"
        window._save()
        assert window.project_status.text().startswith("✓ Проект успешно сохранён")
        assert window.project_status.property("status") == "success"
        window.report_name_edit.setText("Фундамент: 3/проверка")
        report_target = window._report_target("xlsx")
        assert report_target.name == "Фундамент_ 3_проверка.xlsx"
        assert window.project.report_settings["filename"] == "Фундамент_ 3_проверка"
        assert load_project(window.project_path).report_settings["filename"] == "Фундамент_ 3_проверка"
        window.close()
    print("UI smoke: OK")


if __name__ == "__main__":
    main()
