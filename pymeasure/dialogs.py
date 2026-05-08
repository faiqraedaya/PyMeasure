import csv
import io
import json
from typing import List, Tuple

from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QFormLayout,
)

from .models import Measurement, Point


class ScaleDistanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Scale – Known Distance")

        form = QFormLayout()

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(1e-9, 1e12)
        self.distance_spin.setDecimals(6)
        self.distance_spin.setValue(1.0)
        form.addRow("Known distance:", self.distance_spin)

        self.unit_edit = QLineEdit("m")
        form.addRow("Unit:", self.unit_edit)

        presets_layout = QHBoxLayout()
        for unit in ["mm", "cm", "m", "km", "in", "ft"]:
            btn = QPushButton(unit)
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda checked, u=unit: self.unit_edit.setText(u))
            presets_layout.addWidget(btn)
        presets_layout.addStretch()

        preset_widget = QWidget()
        preset_widget.setLayout(presets_layout)
        form.addRow("Presets:", preset_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> Tuple[float, str]:
        return self.distance_spin.value(), self.unit_edit.text().strip() or "px"


class ScaleCoordsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Scale – Known Coordinates")

        form = QFormLayout()
        self._spins = {}
        for name in ("X1", "Y1", "X2", "Y2"):
            spin = QDoubleSpinBox()
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(6)
            form.addRow(f"{name}:", spin)
            self._spins[name] = spin

        self.unit_edit = QLineEdit("m")
        form.addRow("Unit:", self.unit_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> Tuple[Tuple[float, float, float, float], str]:
        coords = tuple(self._spins[k].value() for k in ("X1", "Y1", "X2", "Y2"))
        return coords, self.unit_edit.text().strip() or "px"


class PointLabelDialog(QDialog):
    def __init__(self, default: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Label Point")

        self.edit = QLineEdit(default)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Point label:"))
        layout.addWidget(self.edit)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def label(self) -> str:
        return self.edit.text()


class EditPointDialog(QDialog):
    def __init__(self, label: str, wx: float, wy: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Point")

        form = QFormLayout()

        self.label_edit = QLineEdit(label)
        form.addRow("Label:", self.label_edit)

        self.wx_spin = QDoubleSpinBox()
        self.wx_spin.setRange(-1e12, 1e12)
        self.wx_spin.setDecimals(6)
        self.wx_spin.setValue(wx)
        form.addRow("World X:", self.wx_spin)

        self.wy_spin = QDoubleSpinBox()
        self.wy_spin.setRange(-1e12, 1e12)
        self.wy_spin.setDecimals(6)
        self.wy_spin.setValue(wy)
        form.addRow("World Y:", self.wy_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> Tuple[str, float, float]:
        return self.label_edit.text(), self.wx_spin.value(), self.wy_spin.value()


class ExportDialog(QDialog):
    def __init__(self, measurements: List[Measurement], points: List[Point], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self._rows = self._build_rows(measurements, points)

        self.preview = QListWidget()
        for row in self._rows:
            parts = [f"{k}={v}" for k, v in row.items()]
            self.preview.addItem("  |  ".join(parts))

        btn_csv = QPushButton("Export CSV…")
        btn_json = QPushButton("Export JSON…")
        btn_clip = QPushButton("Copy to Clipboard")
        btn_close = QPushButton("Close")

        btn_csv.clicked.connect(self._export_csv)
        btn_json.clicked.connect(self._export_json)
        btn_clip.clicked.connect(self._copy_clipboard)
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_csv)
        btn_row.addWidget(btn_json)
        btn_row.addWidget(btn_clip)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Preview:"))
        layout.addWidget(self.preview)
        layout.addLayout(btn_row)
        self.setLayout(layout)
        self.resize(600, 400)

    @staticmethod
    def _build_rows(measurements: List[Measurement], points: List[Point]) -> List[dict]:
        rows = []
        for m in measurements:
            rows.append({
                "type": m.kind,
                "value": m.value,
                "unit": m.unit,
                "timestamp": m.timestamp,
                "label": "",
                "x": "",
                "y": "",
            })
        for p in points:
            rows.append({
                "type": "point",
                "value": "",
                "unit": "",
                "timestamp": "",
                "label": p.label,
                "x": p.x,
                "y": p.y,
            })
        return rows

    _FIELDNAMES = ["type", "value", "unit", "timestamp", "label", "x", "y"]

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._FIELDNAMES)
            writer.writeheader()
            writer.writerows(self._rows)
        QMessageBox.information(self, "Export CSV", f"Saved to:\n{path}")

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON Files (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._rows, f, indent=2)
        QMessageBox.information(self, "Export JSON", f"Saved to:\n{path}")

    def _copy_clipboard(self):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self._FIELDNAMES)
        writer.writeheader()
        writer.writerows(self._rows)
        QApplication.clipboard().setText(buf.getvalue())
