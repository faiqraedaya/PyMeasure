import csv
import io
import json
from typing import List, Tuple

from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ..core.models import DiagramObject, Point


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


class SetOriginDialog(QDialog):
    """Ask the user what world coordinates a clicked point corresponds to."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Origin Coordinates")

        note = QLabel(
            "What world coordinates does this point correspond to?\n"
            "Leave at (0, 0) for a standard image-relative origin."
        )
        note.setWordWrap(True)

        form = QFormLayout()
        self._wx = QDoubleSpinBox()
        self._wx.setRange(-1e12, 1e12); self._wx.setDecimals(6); self._wx.setValue(0.0)
        self._wy = QDoubleSpinBox()
        self._wy.setRange(-1e12, 1e12); self._wy.setDecimals(6); self._wy.setValue(0.0)
        form.addRow("World X:", self._wx)
        form.addRow("World Y:", self._wy)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> tuple:
        return self._wx.value(), self._wy.value()


class EditObjectDialog(QDialog):
    """Edit the name and world-coordinate vertices of any DiagramObject."""

    _VERTEX_LABELS = {
        "distance": ["P1", "P2"],
        "angle":    ["P1 (arm)", "P2 (vertex)", "P3 (arm)"],
        "polyline": [],   # dynamically numbered
    }

    def __init__(self, kind: str, name: str, world_pts: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {kind.capitalize()}")
        self._kind = kind
        layout = QVBoxLayout()

        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        form.addRow("Name:", self.name_edit)
        layout.addLayout(form)

        if kind == "point":
            wx, wy = world_pts[0] if world_pts else (0.0, 0.0)
            self._wx = QDoubleSpinBox()
            self._wx.setRange(-1e12, 1e12); self._wx.setDecimals(6); self._wx.setValue(wx)
            self._wy = QDoubleSpinBox()
            self._wy.setRange(-1e12, 1e12); self._wy.setDecimals(6); self._wy.setValue(wy)
            pf = QFormLayout()
            pf.addRow("World X:", self._wx)
            pf.addRow("World Y:", self._wy)
            layout.addLayout(pf)
        else:
            self._table = QTableWidget(len(world_pts), 2)
            self._table.setHorizontalHeaderLabels(["World X", "World Y"])
            self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            v_labels = self._VERTEX_LABELS.get(kind, [f"P{i+1}" for i in range(len(world_pts))])
            for i in range(len(world_pts)):
                lbl = v_labels[i] if i < len(v_labels) else f"P{i+1}"
                self._table.setVerticalHeaderItem(i, QTableWidgetItem(lbl))
            for row, (wx, wy) in enumerate(world_pts):
                self._table.setItem(row, 0, QTableWidgetItem(f"{wx:.6f}"))
                self._table.setItem(row, 1, QTableWidgetItem(f"{wy:.6f}"))
            layout.addWidget(QLabel("Vertices (world coordinates):"))
            layout.addWidget(self._table)
            if kind in ("area", "polyline"):
                btn_row = QHBoxLayout()
                add_btn = QPushButton("Add Vertex")
                rem_btn = QPushButton("Remove Last")
                add_btn.clicked.connect(self._add_row)
                rem_btn.clicked.connect(self._remove_row)
                btn_row.addWidget(add_btn); btn_row.addWidget(rem_btn); btn_row.addStretch()
                layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(360, 300 if kind == "point" else 360)

    def _add_row(self):
        n = self._table.rowCount()
        self._table.setRowCount(n + 1)
        self._table.setVerticalHeaderItem(n, QTableWidgetItem(f"P{n+1}"))
        self._table.setItem(n, 0, QTableWidgetItem("0.000000"))
        self._table.setItem(n, 1, QTableWidgetItem("0.000000"))

    def _remove_row(self):
        minimum = 2 if self._kind == "polyline" else 3
        if self._table.rowCount() > minimum:
            self._table.setRowCount(self._table.rowCount() - 1)

    def values(self) -> Tuple[str, list]:
        name = self.name_edit.text()
        if self._kind == "point":
            return name, [(self._wx.value(), self._wy.value())]
        pts = []
        for row in range(self._table.rowCount()):
            try:
                wx = float(self._table.item(row, 0).text())
                wy = float(self._table.item(row, 1).text())
            except (ValueError, AttributeError):
                wx, wy = 0.0, 0.0
            pts.append((wx, wy))
        return name, pts


class ExportDialog(QDialog):
    _FIELDNAMES = ["type", "name", "value", "unit", "timestamp", "points"]

    def __init__(self, objects: List[DiagramObject], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self._rows = [self._obj_to_row(o) for o in objects]

        self.preview = QListWidget()
        for row in self._rows:
            parts = [f"{k}={v}" for k, v in row.items() if v != ""]
            self.preview.addItem("  |  ".join(parts))

        btn_csv   = QPushButton("Export CSV…")
        btn_json  = QPushButton("Export JSON…")
        btn_clip  = QPushButton("Copy to Clipboard")
        btn_close = QPushButton("Close")
        btn_csv.clicked.connect(self._export_csv)
        btn_json.clicked.connect(self._export_json)
        btn_clip.clicked.connect(self._copy_clipboard)
        btn_close.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_csv); btn_row.addWidget(btn_json)
        btn_row.addWidget(btn_clip); btn_row.addStretch(); btn_row.addWidget(btn_close)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Preview:"))
        layout.addWidget(self.preview)
        layout.addLayout(btn_row)
        self.setLayout(layout)
        self.resize(640, 420)

    @staticmethod
    def _obj_to_row(obj: DiagramObject) -> dict:
        pts_str = "; ".join(f"({x:.4f},{y:.4f})" for x, y in obj.points)
        return {
            "type":      obj.kind,
            "name":      obj.name,
            "value":     obj.value if obj.kind != "point" else "",
            "unit":      obj.unit  if obj.kind != "point" else "",
            "timestamp": obj.timestamp,
            "points":    pts_str,
        }

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
