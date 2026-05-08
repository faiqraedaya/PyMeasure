import json
import os
import sys

from PySide6.QtCore import Qt, QPointF, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QSplitter,
)

from ..core.constants import Tool, TOOL_HELP, TOOL_LABELS, TOOL_SHORTCUTS
from .dialogs import ExportDialog
from ..core.models import DiagramObject, Point, ScaleInfo
from .panel import LeftPanel, RightPanel
from .viewer import ImageViewer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyMeasure")
        self.resize(1400, 800)

        self.left_panel  = LeftPanel()
        self.viewer      = ImageViewer()
        self.right_panel = RightPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([210, 980, 260])
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
        self._syncing_selection = False

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menus(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "&Open…",         "Ctrl+O",        self.open_file)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Session…", "Ctrl+S",        self.save_session)
        self._add_action(file_menu, "&Load Session…", "Ctrl+Shift+O",  self.load_session)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Export…",       "Ctrl+E",        self.show_export)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit",          "Ctrl+Q",        self.close)

        # Edit
        edit_menu = mb.addMenu("&Edit")
        self._add_action(edit_menu, "&Undo",          "Ctrl+Z",        self.viewer.undo)
        self._add_action(edit_menu, "&Redo",          "Ctrl+Y",        self.viewer.redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Cu&t",           "Ctrl+X",        self.viewer.cut_selection)
        self._add_action(edit_menu, "&Copy",          "Ctrl+C",        self.viewer.copy_selection)
        self._add_action(edit_menu, "&Paste",         "Ctrl+V",        self.viewer.paste)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Select &All",    "Ctrl+A",        self.viewer.select_all)
        self._add_action(edit_menu, "&Delete Selected", "Del",         self._on_delete_selected)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Clear &All",     None,            self._on_clear_all)

        # View
        view_menu = mb.addMenu("&View")
        self._add_action(view_menu, "Fit to &Window", "Ctrl+0",        self.viewer.fit_to_window)
        self._add_action(view_menu, "Zoom &In",       "Ctrl+=",
                         lambda: self.viewer.set_zoom(self.viewer.zoom * 1.25))
        self._add_action(view_menu, "Zoom &Out",      "Ctrl+-",
                         lambda: self.viewer.set_zoom(self.viewer.zoom / 1.25))

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

        self._status_live   = QLabel("")
        self._status_coords = QLabel("x: —  y: —")
        self._status_zoom   = QLabel("100%")

        sb.addPermanentWidget(self._status_live)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_coords)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_zoom)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.left_panel.tool_selected.connect(self._set_tool)

        self.viewer.scale_set.connect(self._on_scale_set)
        self.viewer.origin_set.connect(self._on_origin_set)
        self.viewer.mouse_world_pos.connect(self._on_mouse_pos)
        self.viewer.zoom_changed.connect(self._on_zoom_changed)
        self.viewer.live_measure.connect(self._status_live.setText)
        self.viewer.state_restored.connect(self._rebuild_objects_list)
        self.viewer.tool_change_requested.connect(self._set_tool)
        self.viewer.objects_changed.connect(self._rebuild_objects_list)
        self.viewer.selection_changed.connect(self._on_viewer_selection_changed)
        self.viewer.delete_requested.connect(self._on_delete_selected)

        self.right_panel.objects_list.itemSelectionChanged.connect(self._on_panel_selection_changed)
        self.right_panel.objects_list.itemDoubleClicked.connect(self._on_object_double_clicked)
        self.right_panel.objects_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self.right_panel.del_obj_btn.clicked.connect(self._on_delete_selected)
        self.right_panel.clear_all_btn.clicked.connect(self._on_clear_all)
        self.right_panel.export_btn.clicked.connect(self.show_export)

        self.left_panel.prev_page_btn.clicked.connect(self._go_prev_page)
        self.left_panel.next_page_btn.clicked.connect(self._go_next_page)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(Tool)
    def _set_tool(self, tool: Tool):
        self.viewer.set_tool(tool)
        self.left_panel.select_tool(tool)
        self._status_msg.setText(TOOL_HELP[tool])

    @Slot(ScaleInfo)
    def _on_scale_set(self, si: ScaleInfo):
        text = f"1 px = {si.scale_factor:.6g} {si.unit}"
        self.left_panel.scale_lbl.setText(text)
        self._status_msg.setText(f"Scale set: {text}")
        self._rebuild_objects_list()

    @Slot(Point)
    def _on_origin_set(self, pt: Point):
        ox, oy = self.viewer._origin_world
        self.left_panel.origin_lbl.setText(
            f"Origin: img ({pt.x:.1f}, {pt.y:.1f})\n"
            f"  world ({ox:.4g}, {oy:.4g})"
        )
        self._status_msg.setText(
            f"Origin set at img ({pt.x:.1f}, {pt.y:.1f}) = world ({ox:.4g}, {oy:.4g})"
        )
        self._rebuild_objects_list()

    @Slot(float, float)
    def _on_mouse_pos(self, wx: float, wy: float):
        self._status_coords.setText(f"x: {wx:.4f}  y: {wy:.4f}")

    @Slot(float)
    def _on_zoom_changed(self, zoom: float):
        pct = f"{zoom * 100:.0f}%"
        self._status_zoom.setText(pct)
        self.left_panel.zoom_lbl.setText(f"Zoom: {pct}")

    # ------------------------------------------------------------------
    # Objects list (unified)
    # ------------------------------------------------------------------

    def _rebuild_objects_list(self):
        self._syncing_selection = True
        self.right_panel.objects_list.clear()
        for obj in self.viewer.objects:
            label = self._object_list_label(obj)
            self.right_panel.objects_list.addItem(label)
        for i in self.viewer._selection:
            item = self.right_panel.objects_list.item(i)
            if item:
                item.setSelected(True)
        self._syncing_selection = False

    def _object_list_label(self, obj: DiagramObject) -> str:
        icons = {"point": "●", "distance": "─ ", "angle": "∠ ", "area": "▣ ", "polyline": "〜 "}
        icon = icons.get(obj.kind, "? ")
        name = obj.name if obj.name else obj.kind.capitalize()
        if obj.kind == "point" and obj.points:
            wx, wy = self.viewer.img_to_world(QPointF(*obj.points[0]))
            return f"{icon}{name}  ({wx:.4f}, {wy:.4f})"
        if obj.kind in ("distance", "polyline"):
            return f"{icon}{name}: {obj.value:.4g} {obj.unit}"
        if obj.kind == "angle":
            return f"{icon}{name}: {obj.value:.2f}°"
        if obj.kind == "area":
            return f"{icon}{name}: {obj.value:.4g} {obj.unit}²"
        return f"{icon}{name}"

    # ------------------------------------------------------------------
    # Right-panel list context menu
    # ------------------------------------------------------------------

    def _on_list_context_menu(self, pos):
        item = self.right_panel.objects_list.itemAt(pos)
        if item is None:
            return
        idx = self.right_panel.objects_list.row(item)
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self.viewer.open_edit_dialog_for(idx))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_single(idx))
        menu.exec(self.right_panel.objects_list.mapToGlobal(pos))

    def _delete_single(self, idx: int):
        reply = QMessageBox.question(
            self, "Delete Object", "Delete this object?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.viewer.set_selection([idx])
            self.viewer.delete_selected()

    # ------------------------------------------------------------------
    # Selection sync (two-way, guarded by _syncing_selection)
    # ------------------------------------------------------------------

    @Slot(list)
    def _on_viewer_selection_changed(self, indices: list):
        if self._syncing_selection:
            return
        self._syncing_selection = True
        self.right_panel.objects_list.clearSelection()
        for i in indices:
            item = self.right_panel.objects_list.item(i)
            if item:
                item.setSelected(True)
        self._syncing_selection = False

    def _on_panel_selection_changed(self):
        if self._syncing_selection:
            return
        rows = [self.right_panel.objects_list.row(item)
                for item in self.right_panel.objects_list.selectedItems()]
        self._syncing_selection = True
        self.viewer.set_selection(rows)
        self._syncing_selection = False
        self.viewer.update()

    def _on_object_double_clicked(self, item):
        idx = self.right_panel.objects_list.row(item)
        self.viewer.open_edit_dialog_for(idx)

    # ------------------------------------------------------------------
    # Delete / Clear
    # ------------------------------------------------------------------

    def _on_delete_selected(self):
        n = len(self.viewer._selection)
        if n == 0:
            return
        reply = QMessageBox.question(
            self, "Delete Objects",
            f"Delete {n} selected object{'s' if n > 1 else ''}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.viewer.delete_selected()

    def _on_clear_all(self):
        n = len(self.viewer.objects)
        if n == 0:
            return
        reply = QMessageBox.question(
            self, "Clear All",
            f"Delete all {n} object{'s' if n > 1 else ''}?\nThis can be undone with Ctrl+Z.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.viewer.clear_all_objects()

    # ------------------------------------------------------------------
    # Page navigation
    # ------------------------------------------------------------------

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
            self, "Open Image or PDF", "",
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
        self.left_panel.pdf_box.setVisible(count > 1)
        if count > 1:
            self.left_panel.page_lbl.setText(f"{self.viewer.current_page + 1} / {count}")

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
        self._rebuild_objects_list()
        si = self.viewer.scale_info
        self.left_panel.scale_lbl.setText(f"1 px = {si.scale_factor:.6g} {si.unit}")
        o  = self.viewer.origin
        ox, oy = self.viewer._origin_world
        self.left_panel.origin_lbl.setText(
            f"Origin: img ({o.x:.1f}, {o.y:.1f})\n  world ({ox:.4g}, {oy:.4g})"
        )
        self._status_msg.setText(f"Session loaded from {path}")

    # ------------------------------------------------------------------
    # Export / About
    # ------------------------------------------------------------------

    def show_export(self):
        ExportDialog(self.viewer.objects, self).exec()

    def show_about(self):
        QMessageBox.about(
            self, "About PyMeasure",
            "<b>PyMeasure v2.0</b><br><br>"
            "Features:<br>"
            "• Open images (PNG, JPEG, BMP, TIFF) and multi-page PDFs<br>"
            "• Pan and zoom · middle-click or scroll · Zoom Rectangle (Z)<br>"
            "• Set origin and scale (by distance or coordinates)<br>"
            "• Add labelled points, lines, angles, areas, and polylines<br>"
            "• Annotations persist on canvas with labels<br>"
            "• Select, move, cut, copy, paste objects in Pan/Zoom mode<br>"
            "• Drag vertex handles directly when an object is selected<br>"
            "• Right-click a vertex to delete it · right-click an edge to insert<br>"
            "• Shift-lock to cardinal directions while measuring<br>"
            "• Double-click to finish area or polyline<br>"
            "• Undo / Redo · save and load sessions · export CSV/JSON<br><br>"
            "Built with PySide6 and PyMuPDF.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyMeasure")
    app.setApplicationVersion("2.0")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
