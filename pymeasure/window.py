import json
import os
import sys

from PySide6.QtCore import Qt, QPointF, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QSizePolicy, QSplitter,
)

from .constants import Tool, TOOL_HELP, TOOL_LABELS, TOOL_SHORTCUTS
from .dialogs import ExportDialog
from .models import Measurement, Point, ScaleInfo
from .panel import LeftPanel
from .viewer import ImageViewer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyMeasure")
        self.resize(1280, 780)

        self.panel = LeftPanel()
        self.viewer = ImageViewer()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.panel)
        splitter.addWidget(self.viewer)
        splitter.setSizes([230, 1050])
        self.setCentralWidget(splitter)

        self._build_menus()
        self._build_status_bar()
        self._connect_signals()

        self.setStyleSheet("""
            QGroupBox { font-weight: bold; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
            QPushButton:checked { background-color: #0066cc; color: white; }
            QListWidget { font-size: 11px; }
        """)

        self._set_tool(Tool.PAN)

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menus(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "&Open…", "Ctrl+O", self.open_file)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Session…", "Ctrl+S", self.save_session)
        self._add_action(file_menu, "&Load Session…", "Ctrl+Shift+O", self.load_session)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Export…", "Ctrl+E", self.show_export)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit", "Ctrl+Q", self.close)

        # Edit
        edit_menu = mb.addMenu("&Edit")
        self._add_action(edit_menu, "&Undo", "Ctrl+Z", self.viewer.undo)
        self._add_action(edit_menu, "&Redo", "Ctrl+Y", self.viewer.redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Clear &Points", None, self.clear_points)
        self._add_action(edit_menu, "Clear &Measurements", None, self.clear_measurements)
        self._add_action(edit_menu, "Clear &All", None, self.clear_all)

        # View
        view_menu = mb.addMenu("&View")
        self._add_action(view_menu, "Fit to &Window", "Ctrl+0", self.viewer.fit_to_window)
        self._add_action(
            view_menu, "Zoom &In", "Ctrl+=",
            lambda: self.viewer.set_zoom(self.viewer.zoom * 1.25),
        )
        self._add_action(
            view_menu, "Zoom &Out", "Ctrl+-",
            lambda: self.viewer.set_zoom(self.viewer.zoom / 1.25),
        )

        # Tools
        tools_menu = mb.addMenu("&Tools")
        for tool in Tool:
            act = QAction(TOOL_LABELS[tool], self)
            act.setShortcut(QKeySequence(TOOL_SHORTCUTS[tool]))
            act.triggered.connect(lambda checked, t=tool: self._set_tool(t))
            tools_menu.addAction(act)

        # Help
        help_menu = mb.addMenu("&Help")
        self._add_action(help_menu, "&About", None, self.show_about)

    def _add_action(self, menu, label: str, shortcut, slot):
        act = QAction(label, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self):
        sb = self.statusBar()

        self._status_msg = QLabel("")
        self._status_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sb.addWidget(self._status_msg, 1)

        self._status_coords = QLabel("x: —  y: —")
        self._status_zoom = QLabel("100%")
        sb.addPermanentWidget(self._status_coords)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_zoom)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.panel.tool_selected.connect(self._set_tool)
        self.viewer.point_added.connect(self._on_point_added)
        self.viewer.scale_set.connect(self._on_scale_set)
        self.viewer.origin_set.connect(self._on_origin_set)
        self.viewer.measurement_done.connect(self._on_measurement)
        self.viewer.mouse_world_pos.connect(self._on_mouse_pos)
        self.viewer.zoom_changed.connect(self._on_zoom_changed)
        self.viewer.state_restored.connect(self._sync_panel_lists)
        self.viewer.tool_change_requested.connect(self._set_tool)
        self.viewer.points_changed.connect(self._sync_panel_lists)
        self.viewer.measurements_changed.connect(self._sync_meas_list)

        self.panel.del_point_btn.clicked.connect(self._delete_selected_point)
        self.panel.clear_points_btn.clicked.connect(self.clear_points)
        self.panel.clear_meas_btn.clicked.connect(self.clear_measurements)
        self.panel.export_btn.clicked.connect(self.show_export)
        self.panel.prev_page_btn.clicked.connect(self._go_prev_page)
        self.panel.next_page_btn.clicked.connect(self._go_next_page)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(Tool)
    def _set_tool(self, tool: Tool):
        self.viewer.set_tool(tool)
        self.panel.select_tool(tool)
        self._status_msg.setText(TOOL_HELP[tool])

    @Slot(Point)
    def _on_point_added(self, pt: Point):
        wx, wy = self.viewer.img_to_world(QPointF(pt.x, pt.y))
        self.panel.points_list.addItem(f"{pt.label}: ({wx:.4f}, {wy:.4f})")

    @Slot(ScaleInfo)
    def _on_scale_set(self, si: ScaleInfo):
        text = f"1 px = {si.scale_factor:.6g} {si.unit}"
        self.panel.scale_lbl.setText(text)
        self._status_msg.setText(f"Scale set: {text}")

    @Slot(Point)
    def _on_origin_set(self, pt: Point):
        self.panel.origin_lbl.setText(f"Origin: img ({pt.x:.1f}, {pt.y:.1f})")
        self._status_msg.setText(f"Origin set at img ({pt.x:.1f}, {pt.y:.1f})")

    @Slot(Measurement)
    def _on_measurement(self, m: Measurement):
        self.panel.meas_list.addItem(m.display())
        self._status_msg.setText(m.display())

    @Slot(float, float)
    def _on_mouse_pos(self, wx: float, wy: float):
        self._status_coords.setText(f"x: {wx:.4f}  y: {wy:.4f}")

    @Slot(float)
    def _on_zoom_changed(self, zoom: float):
        pct = f"{zoom * 100:.0f}%"
        self._status_zoom.setText(pct)
        self.panel.zoom_lbl.setText(f"Zoom: {pct}")

    def _delete_selected_point(self):
        row = self.panel.points_list.currentRow()
        if row < 0:
            return
        self.viewer.delete_point(row)
        self.panel.points_list.takeItem(row)

    def _go_prev_page(self):
        self.viewer.go_to_page(self.viewer.current_page - 1)
        self._update_pdf_nav()

    def _go_next_page(self):
        self.viewer.go_to_page(self.viewer.current_page + 1)
        self._update_pdf_nav()

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image or PDF",
            "",
            "Images & PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.pdf);;All Files (*)",
        )
        if not path:
            return
        if self.viewer.load_file(path):
            self.setWindowTitle(f"PyMeasure — {os.path.basename(path)}")
            self._update_pdf_nav()
        else:
            QMessageBox.warning(self, "Open File", f"Could not open:\n{path}")

    def _update_pdf_nav(self):
        count = self.viewer.pdf_page_count
        self.panel.pdf_box.setVisible(count > 1)
        if count > 1:
            self.panel.page_lbl.setText(f"{self.viewer.current_page + 1} / {count}")

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def save_session(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Session", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.viewer.session_data(), f, indent=2)
            self._status_msg.setText(f"Session saved to {path}")
        except OSError as e:
            QMessageBox.critical(self, "Save Session", f"Could not save session:\n{e}")

    def load_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.viewer.load_session(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            QMessageBox.critical(self, "Load Session", f"Could not load session:\n{e}")
            return
        self._sync_panel_lists()
        self._status_msg.setText(f"Session loaded from {path}")

    def _sync_panel_lists(self):
        self.panel.points_list.clear()
        for pt in self.viewer.points_of_interest:
            wx, wy = self.viewer.img_to_world(QPointF(pt.x, pt.y))
            self.panel.points_list.addItem(f"{pt.label}: ({wx:.4f}, {wy:.4f})")

        self.panel.meas_list.clear()
        for m in self.viewer.measurements:
            self.panel.meas_list.addItem(m.display())

        si = self.viewer.scale_info
        self.panel.scale_lbl.setText(f"1 px = {si.scale_factor:.6g} {si.unit}")
        o = self.viewer.origin
        self.panel.origin_lbl.setText(f"Origin: img ({o.x:.1f}, {o.y:.1f})")

    def _sync_meas_list(self):
        self.panel.meas_list.clear()
        for m in self.viewer.measurements:
            self.panel.meas_list.addItem(m.display())

    # ------------------------------------------------------------------
    # Clear / Export
    # ------------------------------------------------------------------

    def clear_points(self):
        self.viewer.clear_points()
        self.panel.points_list.clear()

    def clear_measurements(self):
        self.viewer.clear_measurements()
        self.panel.meas_list.clear()

    def clear_all(self):
        self.viewer.clear_all()
        self.panel.points_list.clear()
        self.panel.meas_list.clear()
        self.panel.scale_lbl.setText("Scale: not set")
        self.panel.origin_lbl.setText("Origin: not set")

    def show_export(self):
        ExportDialog(self.viewer.measurements, self.viewer.points_of_interest, self).exec()

    def show_about(self):
        QMessageBox.about(
            self,
            "About PyMeasure",
            "<b>PyMeasure v1.0</b><br><br>"
            "Features:<br>"
            "• Open images (PNG, JPEG, BMP, TIFF) and multi-page PDFs<br>"
            "• Pan and zoom with mouse<br>"
            "• Set a real-world origin and scale (by distance or coordinates)<br>"
            "• Add labelled points of interest<br>"
            "• Measure distances, angles, and polygon areas<br>"
            "• Undo / Redo support<br>"
            "• Export data as CSV, JSON, or clipboard<br>"
            "• Save and load sessions<br><br>"
            "Built with PySide6 and PyMuPDF.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyMeasure")
    app.setApplicationVersion("1.0")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
