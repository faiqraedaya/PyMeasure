import csv
import io
import json
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.models import DiagramObject, Point

# Default palette cycled when adding contour levels / picking object colors.
_CONTOUR_PALETTE = [
    "#ff0000", "#ff8800", "#ffdd00", "#00cc44",
    "#0088ff", "#aa44ff", "#ff44aa", "#00cccc",
]
MAX_CONTOUR_LEVELS = 20
DEFAULT_CONTOUR_WIDTH = 2.0


class ColorButton(QPushButton):
    """A push button that shows the current color as its background and opens a
    color picker when clicked."""

    def __init__(self, color="#ff0000", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setMinimumWidth(90)
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self):
        # Show the color as a small icon swatch (NOT a background stylesheet —
        # a background-color stylesheet would be inherited by the QColorDialog
        # opened as this button's child and tint the whole picker).
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#888888"), 1))
        p.setBrush(QBrush(self._color))
        p.drawRoundedRect(0, 0, 15, 15, 3, 3)
        p.end()
        self.setIcon(QIcon(pm))
        self.setText(self._color.name())

    def _pick(self):
        c = QColorDialog.getColor(self._color, self.window(), "Select Color")
        if c.isValid():
            self._color = c
            self._refresh()

    def color_name(self) -> str:
        return self._color.name()

    def set_color(self, color):
        self._color = QColor(color)
        self._refresh()


# Display label -> stored value for the line-style dropdown.
LINE_STYLES = [("Solid", "solid"), ("Dashed", "dashed"),
               ("Dotted", "dotted"), ("Dash-Dot", "dashdot")]


class LineStyleControls(QWidget):
    """Compact width spin-box + line-style dropdown, shared by the object
    dialogs so any line-based object can set its stroke."""

    def __init__(self, width=0.0, style="solid", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._width = QDoubleSpinBox()
        self._width.setRange(0.5, 30.0)
        self._width.setSingleStep(0.5)
        self._width.setDecimals(1)
        self._width.setValue(width if width and width > 0 else 2.0)

        self._style = QComboBox()
        for label, val in LINE_STYLES:
            self._style.addItem(label, val)
        self.set_style(style)

        lay.addWidget(QLabel("Width:"))
        lay.addWidget(self._width)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Style:"))
        lay.addWidget(self._style)
        lay.addStretch()

    def set_style(self, style: str):
        idx = self._style.findData(style)
        self._style.setCurrentIndex(idx if idx >= 0 else 0)

    def width(self) -> float:
        return self._width.value()

    def style(self) -> str:
        return self._style.currentData()


class ContourLevelsTable(QWidget):
    """Reusable editor for a contour object's levels: a table of
    (reference value, distance, width, color) rows, capped at
    MAX_CONTOUR_LEVELS."""

    def __init__(self, unit="px", levels=None, parent=None):
        super().__init__(parent)
        self._unit = unit
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Reference value", f"Distance ({unit})", "Width", "Color"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self._table)

        row = QHBoxLayout()
        add_btn = QPushButton("Add Level")
        rem_btn = QPushButton("Remove Last")
        add_btn.clicked.connect(lambda: self.add_row())
        rem_btn.clicked.connect(self.remove_last)
        row.addWidget(add_btn)
        row.addWidget(rem_btn)
        row.addStretch()
        v.addLayout(row)

        if levels:
            for lv in levels[:MAX_CONTOUR_LEVELS]:
                self.add_row(lv.get("reference", ""), lv.get("distance", 0.0),
                             lv.get("color"), lv.get("width"))
        else:
            self.add_row()

    def add_row(self, reference="", distance=0.0, color=None, width=None):
        n = self._table.rowCount()
        if n >= MAX_CONTOUR_LEVELS:
            return
        if color is None:
            color = _CONTOUR_PALETTE[n % len(_CONTOUR_PALETTE)]
        self._table.insertRow(n)
        self._table.setItem(n, 0, QTableWidgetItem(str(reference)))
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1e12)
        spin.setDecimals(4)
        spin.setValue(float(distance))
        self._table.setCellWidget(n, 1, spin)
        wspin = QDoubleSpinBox()
        wspin.setRange(0.5, 30.0)
        wspin.setSingleStep(0.5)
        wspin.setDecimals(1)
        wspin.setValue(float(width) if width and float(width) > 0 else DEFAULT_CONTOUR_WIDTH)
        self._table.setCellWidget(n, 2, wspin)
        self._table.setCellWidget(n, 3, ColorButton(color))

    def remove_last(self):
        if self._table.rowCount() > 1:
            self._table.removeRow(self._table.rowCount() - 1)

    def levels(self) -> list:
        out = []
        for r in range(self._table.rowCount()):
            ref_item = self._table.item(r, 0)
            ref = ref_item.text().strip() if ref_item else ""
            spin = self._table.cellWidget(r, 1)
            dist = spin.value() if spin else 0.0
            wspin = self._table.cellWidget(r, 2)
            width = wspin.value() if wspin else DEFAULT_CONTOUR_WIDTH
            cbtn = self._table.cellWidget(r, 3)
            color = cbtn.color_name() if cbtn else "#ff0000"
            out.append({"reference": ref, "distance": dist,
                        "width": width, "color": color})
        return out


def levels_order_warning(levels) -> Optional[str]:
    """Return a warning message if contour distances aren't non-decreasing down
    the rows (each level should reach at least as far as the one above it), or
    None if the ordering is fine. Rows with no distance are ignored."""
    flagged = []
    prev = None
    for lv in levels:
        dist = float(lv.get("distance", 0) or 0)
        if dist <= 0:
            continue
        ref = lv.get("reference", "") or "(unnamed)"
        if prev is not None and dist < prev[1]:
            flagged.append(f"  • '{ref}' ({dist:g}) is closer than '{prev[0]}' ({prev[1]:g})")
        prev = (ref, dist)
    if not flagged:
        return None
    return (
        "Contour distances usually increase as the reference level becomes less "
        "severe (each row should reach at least as far as the row above). "
        "These rows are closer than a preceding row:\n\n"
        + "\n".join(flagged)
        + "\n\nThe contour will still be created."
    )


class ContourLevelsDialog(QDialog):
    """Name + levels editor shown after a contour's geometry is placed."""

    def __init__(self, kind_label="Contour", unit="px", name="", levels=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{kind_label} Levels")

        layout = QVBoxLayout()
        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        form.addRow("Name:", self.name_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel(
            f"Contour levels (distance in {unit}; max {MAX_CONTOUR_LEVELS}):"
        ))
        self._levels = ContourLevelsTable(unit, levels)
        layout.addWidget(self._levels)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(480, 360)

    def accept(self):
        warn = levels_order_warning(self._levels.levels())
        if warn:
            QMessageBox.warning(self, "Contour Levels", warn)
        super().accept()

    def values(self) -> Tuple[str, list]:
        return self.name_edit.text().strip(), self._levels.levels()


class LegendTitleDialog(QDialog):
    """Edit the on-canvas legend title."""

    def __init__(self, title="Legend", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Legend Title")
        self.edit = QLineEdit(title)
        self.edit.selectAll()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Legend title:"))
        layout.addWidget(self.edit)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def title(self) -> str:
        return self.edit.text().strip()


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


_KIND_DISPLAY = {
    "point":    "Point",
    "distance": "Line",
    "angle":    "Angle",
    "polygon":  "Polygon",
    "polyline": "Polyline",
}


class NameDialog(QDialog):
    def __init__(self, kind: str = "point", default: str = "",
                 color: str = "", parent=None):
        super().__init__(parent)
        display = _KIND_DISPLAY.get(kind, kind.capitalize())
        self.setWindowTitle(f"Label {display}")
        self.edit = QLineEdit(default)
        self.edit.selectAll()

        form = QFormLayout()
        form.addRow(f"{display} label:", self.edit)
        self._color_btn = ColorButton(color or "#ffffff")
        form.addRow("Color:", self._color_btn)

        # Line width/style for every line-based object (not plain points).
        self._line = None
        if kind != "point":
            self._line = LineStyleControls()
            form.addRow("Line:", self._line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def label(self) -> str:
        return self.edit.text()

    def color(self) -> str:
        return self._color_btn.color_name()

    def line_width(self) -> float:
        return self._line.width() if self._line else 0.0

    def line_style(self) -> str:
        return self._line.style() if self._line else "solid"


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
    """Edit the name, color, and world-coordinate vertices of a DiagramObject.
    For contour objects, edits the name and contour levels instead."""

    _VERTEX_LABELS = {
        "distance": ["P1", "P2"],
        "angle":    ["P1 (arm)", "P2 (vertex)", "P3 (arm)"],
        "polyline": [],   # dynamically numbered
    }

    def __init__(self, kind: str, name: str, world_pts: list, color: str = "",
                 levels: list = None, unit: str = "px",
                 line_width: float = 0.0, line_style: str = "solid", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {kind.replace('_', ' ').title()}")
        self._kind = kind
        self._is_contour = kind in ("polyline_contour", "point_contour")
        self._world_pts = list(world_pts)
        layout = QVBoxLayout()

        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        form.addRow("Name:", self.name_edit)
        self._color_btn = None
        self._line = None
        if not self._is_contour:
            self._color_btn = ColorButton(color or "#ffffff")
            form.addRow("Color:", self._color_btn)
            if kind != "point":
                self._line = LineStyleControls(line_width, line_style)
                form.addRow("Line:", self._line)
        layout.addLayout(form)

        self._levels = None
        self._table = None
        if self._is_contour:
            layout.addWidget(QLabel(
                f"Contour levels (distance in {unit}; max {MAX_CONTOUR_LEVELS}):"
            ))
            self._levels = ContourLevelsTable(unit, levels)
            layout.addWidget(self._levels)
        elif kind == "point":
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
            if kind in ("polygon", "polyline"):
                btn_row = QHBoxLayout()
                add_btn = QPushButton("Add Vertex")
                rem_btn = QPushButton("Remove Last")
                add_btn.clicked.connect(lambda: self._add_row())
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
        self.resize(420, 300 if kind == "point" else 380)

    def accept(self):
        if self._is_contour:
            warn = levels_order_warning(self._levels.levels())
            if warn:
                QMessageBox.warning(self, "Contour Levels", warn)
        super().accept()

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

    def values(self) -> Tuple[str, list, str, list, float, str]:
        """Return (name, world_pts, color, levels, line_width, line_style)."""
        name = self.name_edit.text()
        color = self._color_btn.color_name() if self._color_btn else ""
        lw = self._line.width() if self._line else 0.0
        ls = self._line.style() if self._line else "solid"

        if self._is_contour:
            return name, self._world_pts, color, self._levels.levels(), lw, ls
        if self._kind == "point":
            return name, [(self._wx.value(), self._wy.value())], color, [], lw, ls
        pts = []
        for row in range(self._table.rowCount()):
            try:
                wx = float(self._table.item(row, 0).text())
                wy = float(self._table.item(row, 1).text())
            except (ValueError, AttributeError):
                wx, wy = 0.0, 0.0
            pts.append((wx, wy))
        return name, pts, color, [], lw, ls


class TextBoxDialog(QDialog):
    """Define a text box: content, font, colors, border line style, and fill."""

    _H_ALIGNS = [("Left", "left"), ("Center", "center"), ("Right", "right")]
    _V_ALIGNS = [("Top", "top"), ("Middle", "middle"), ("Bottom", "bottom")]

    def __init__(self, name="", text="", font_family="", font_size=0,
                 font_color="#ffffff", line_color="#ffffff", fill_color="",
                 line_width=0.0, line_style="solid", bold=False, italic=False,
                 underline=False, h_align="left", v_align="top", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Box")
        layout = QVBoxLayout()

        top = QFormLayout()
        self.name_edit = QLineEdit(name)
        top.addRow("Name:", self.name_edit)
        layout.addLayout(top)

        layout.addWidget(QLabel("Text:"))
        self.text_edit = QPlainTextEdit(text)
        self.text_edit.setMinimumHeight(80)
        layout.addWidget(self.text_edit)

        form = QFormLayout()
        self.font_combo = QFontComboBox()
        if font_family:
            self.font_combo.setCurrentFont(QFont(font_family))
        form.addRow("Font:", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 200)
        self.size_spin.setValue(font_size if font_size and font_size > 0 else 12)
        form.addRow("Font size:", self.size_spin)

        # Bold / Italic / Underline
        style_row = QHBoxLayout()
        self.bold_check = QCheckBox("Bold")
        self.bold_check.setChecked(bool(bold))
        self.italic_check = QCheckBox("Italic")
        self.italic_check.setChecked(bool(italic))
        self.underline_check = QCheckBox("Underline")
        self.underline_check.setChecked(bool(underline))
        style_row.addWidget(self.bold_check)
        style_row.addWidget(self.italic_check)
        style_row.addWidget(self.underline_check)
        style_row.addStretch()
        style_wrap = QWidget()
        style_wrap.setLayout(style_row)
        form.addRow("Style:", style_wrap)

        # Horizontal / vertical alignment
        align_row = QHBoxLayout()
        self.halign_combo = QComboBox()
        for lbl, val in self._H_ALIGNS:
            self.halign_combo.addItem(lbl, val)
        hi = self.halign_combo.findData(h_align)
        self.halign_combo.setCurrentIndex(hi if hi >= 0 else 0)
        self.valign_combo = QComboBox()
        for lbl, val in self._V_ALIGNS:
            self.valign_combo.addItem(lbl, val)
        vi = self.valign_combo.findData(v_align)
        self.valign_combo.setCurrentIndex(vi if vi >= 0 else 0)
        align_row.addWidget(QLabel("Horizontal:"))
        align_row.addWidget(self.halign_combo)
        align_row.addSpacing(8)
        align_row.addWidget(QLabel("Vertical:"))
        align_row.addWidget(self.valign_combo)
        align_row.addStretch()
        align_wrap = QWidget()
        align_wrap.setLayout(align_row)
        form.addRow("Align:", align_wrap)

        self.font_color_btn = ColorButton(font_color or "#ffffff")
        form.addRow("Font color:", self.font_color_btn)

        self.line_color_btn = ColorButton(line_color or "#ffffff")
        form.addRow("Border color:", self.line_color_btn)

        self._line = LineStyleControls(line_width, line_style)
        form.addRow("Border line:", self._line)

        fill_row = QHBoxLayout()
        self.fill_check = QCheckBox("Fill")
        self.fill_color_btn = ColorButton(fill_color or "#ffffcc")
        has_fill = bool(fill_color)
        self.fill_check.setChecked(has_fill)
        self.fill_color_btn.setEnabled(has_fill)
        self.fill_check.toggled.connect(self.fill_color_btn.setEnabled)
        fill_row.addWidget(self.fill_check)
        fill_row.addWidget(self.fill_color_btn)
        fill_row.addStretch()
        fill_wrap = QWidget()
        fill_wrap.setLayout(fill_row)
        form.addRow("Fill:", fill_wrap)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(440, 560)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "text": self.text_edit.toPlainText(),
            "font_family": self.font_combo.currentFont().family(),
            "font_size": self.size_spin.value(),
            "font_color": self.font_color_btn.color_name(),
            "line_color": self.line_color_btn.color_name(),
            "fill_color": (self.fill_color_btn.color_name()
                           if self.fill_check.isChecked() else ""),
            "line_width": self._line.width(),
            "line_style": self._line.style(),
            "bold": self.bold_check.isChecked(),
            "italic": self.italic_check.isChecked(),
            "underline": self.underline_check.isChecked(),
            "h_align": self.halign_combo.currentData(),
            "v_align": self.valign_combo.currentData(),
        }


class ExportDialog(QDialog):
    _FIELDNAMES = ["type", "name", "value", "unit", "measurements", "timestamp",
                   "levels", "world_points", "image_points"]

    def __init__(self, objects: List[DiagramObject], to_world=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self._to_world = to_world or (lambda x, y: (x, y))
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
        self.resize(720, 420)

    def _obj_to_row(self, obj: DiagramObject) -> dict:
        img_str = "; ".join(f"({x:.4f},{y:.4f})" for x, y in obj.points)
        world_str = "; ".join(
            "({:.4f},{:.4f})".format(*self._to_world(x, y)) for x, y in obj.points
        )
        levels_str = "; ".join(
            f"{lv.get('reference','')}@{lv.get('distance',0)}{lv.get('color','')}"
            for lv in obj.levels
        )
        has_value = obj.kind not in ("point", "polyline_contour", "point_contour")
        return {
            "type":         obj.kind,
            "name":         obj.name,
            "value":        obj.value if has_value else "",
            "unit":         obj.unit  if has_value else "",
            "measurements": obj._measure_inline() if has_value else "",
            "timestamp":    obj.timestamp,
            "levels":       levels_str,
            "world_points": world_str,
            "image_points": img_str,
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
