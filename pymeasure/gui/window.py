import json
import os
import sys

from PySide6.QtCore import Qt, QPointF, QSettings, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QSizePolicy, QSplitter,
)

from ..core.constants import Tool, TOOL_HELP, TOOL_LABELS, TOOL_SHORTCUTS
from ..core.prefs import PREFS
from .dialogs import ExportDialog, PreferencesDialog
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

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.left_panel)
        self._splitter.addWidget(self.viewer)
        self._splitter.addWidget(self.right_panel)
        self._splitter.setSizes([210, 980, 260])
        self.setCentralWidget(self._splitter)

        # Load display preferences before building the UI so labels format right.
        self._load_display_prefs(QSettings("PyMeasure", "PyMeasure"))

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
        self._last_open_dir = ""

        settings = QSettings("PyMeasure", "PyMeasure")
        self._recent_files: list[str] = settings.value("recentFiles", [])
        if isinstance(self._recent_files, str):
            self._recent_files = [self._recent_files]
        self._recent_sessions: list[str] = settings.value("recentSessions", [])
        if isinstance(self._recent_sessions, str):
            self._recent_sessions = [self._recent_sessions]

        # Map: image/pdf file path -> last-attached session path
        raw_map = settings.value("fileSessionMap", "")
        try:
            self._file_session_map: dict[str, str] = (
                json.loads(raw_map) if raw_map else {}
            )
            if not isinstance(self._file_session_map, dict):
                self._file_session_map = {}
        except (json.JSONDecodeError, TypeError):
            self._file_session_map = {}

        self._update_recent_menu()
        self._update_recent_session_menu()
        self._refresh_ui_for_active_tab()
        self._restore_window_state(settings)

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menus(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "&Open…",         "Ctrl+O",        self.open_file)
        self._recent_menu = file_menu.addMenu("Open &Recent")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Session",     "Ctrl+S",       self.save_session)
        self._add_action(file_menu, "Save Session &As…", "Ctrl+Shift+S", self.save_session_as)
        self._add_action(file_menu, "&Load Session…",    "Ctrl+Shift+O", self.load_session)
        self._recent_session_menu = file_menu.addMenu("Load &Recent Session")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Export…",         "Ctrl+E",       self.show_export)
        self._add_action(file_menu, "Export &Image…",   "Ctrl+Shift+E", self.export_image)
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
        edit_menu.addSeparator()
        self._add_action(edit_menu, "&Preferences…",  None,            self.show_preferences)

        # View
        view_menu = mb.addMenu("&View")
        self._add_action(view_menu, "Fit to &Window", "Ctrl+0",        self.viewer.fit_to_window)
        self._add_action(view_menu, "Zoom &In",       "Ctrl+=",
                         lambda: self.viewer.set_zoom(self.viewer.zoom * 1.25))
        self._add_action(view_menu, "Zoom &Out",      "Ctrl+-",
                         lambda: self.viewer.set_zoom(self.viewer.zoom / 1.25))
        view_menu.addSeparator()
        self._show_objects_act = QAction("Show All &Objects", self)
        self._show_objects_act.setCheckable(True)
        self._show_objects_act.setChecked(True)
        self._show_objects_act.setShortcut(QKeySequence("Ctrl+H"))
        self._show_objects_act.toggled.connect(self.viewer.set_objects_visible)
        view_menu.addAction(self._show_objects_act)

        self._scale_bar_act = QAction("Show Scale &Bar", self)
        self._scale_bar_act.setCheckable(True)
        self._scale_bar_act.setChecked(self.viewer.scale_bar_visible)
        self._scale_bar_act.toggled.connect(self.viewer.set_scale_bar_visible)
        view_menu.addAction(self._scale_bar_act)

        self._snap_act = QAction("Snap to &Vertices", self)
        self._snap_act.setCheckable(True)
        self._snap_act.setChecked(self.viewer.vertex_snap_enabled)
        self._snap_act.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self._snap_act.toggled.connect(self.viewer.set_vertex_snap)
        view_menu.addAction(self._snap_act)

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
        act.triggered.connect(lambda checked=False, s=slot: s())
        menu.addAction(act)

    def _update_recent_menu(self):
        self._recent_menu.clear()
        for path in self._recent_files:
            act = QAction(path, self)
            act.triggered.connect(lambda checked, p=path: self._open_recent(p))
            self._recent_menu.addAction(act)
        self._recent_menu.setEnabled(bool(self._recent_files))

    def _open_recent(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Open Recent", f"File not found:\n{path}")
            self._recent_files = [p for p in self._recent_files if p != path]
            self._save_recents()
            self._update_recent_menu()
            return
        self._load_path(path)

    def _load_path(self, path: str):
        """Open `path` as a brand-new tab in the viewer."""
        idx = self.viewer.open_in_new_tab(path)
        if idx < 0:
            QMessageBox.warning(self, "Open File", f"Could not open:\n{path}")
            return

        self._last_open_dir = os.path.dirname(path)
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        self._save_recents()
        self._update_recent_menu()

        # Offer to also load the last-attached session for this file.
        self._maybe_offer_associated_session(path)

        # Refresh dependent UI for the now-active tab.
        self._refresh_ui_for_active_tab()

    def _maybe_offer_associated_session(self, file_path: str):
        norm = os.path.normcase(os.path.abspath(file_path))
        session_path = self._file_session_map.get(norm)
        if not session_path or not os.path.exists(session_path):
            if session_path and not os.path.exists(session_path):
                # Stale association — clean up
                del self._file_session_map[norm]
                self._save_file_session_map()
            return
        reply = QMessageBox.question(
            self, "Open Associated Session",
            f"PyMeasure last opened this file with the session:\n\n"
            f"{session_path}\n\n"
            "Open that session too?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._do_load_session(session_path)

    def _save_recents(self):
        QSettings("PyMeasure", "PyMeasure").setValue("recentFiles", self._recent_files)

    def _update_recent_session_menu(self):
        self._recent_session_menu.clear()
        for path in self._recent_sessions:
            act = QAction(path, self)
            act.triggered.connect(lambda checked, p=path: self._open_recent_session(p))
            self._recent_session_menu.addAction(act)
        self._recent_session_menu.setEnabled(bool(self._recent_sessions))

    def _open_recent_session(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Load Recent Session", f"File not found:\n{path}")
            self._recent_sessions = [p for p in self._recent_sessions if p != path]
            self._save_recent_sessions()
            self._update_recent_session_menu()
            return
        self._do_load_session(path)

    def _do_load_session(self, path: str):
        if self.viewer.current_tab_index < 0:
            QMessageBox.information(
                self, "Load Session",
                "Open an image or PDF first, then load a session into its tab.",
            )
            return

        dlg = QProgressDialog("Loading session…", None, 0, 0, self)
        dlg.setWindowTitle("Load Session")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        dlg.setAutoClose(False)
        dlg.show()
        QApplication.processEvents()

        def on_progress(cur: int, total: int):
            if total > 0 and dlg.maximum() != total:
                dlg.setMaximum(total)
            dlg.setLabelText(f"Loading objects… ({cur} / {total})")
            dlg.setValue(cur)
            QApplication.processEvents()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.viewer.load_session(data, progress=on_progress)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            dlg.close()
            QMessageBox.critical(self, "Load Session", f"Could not load session:\n{e}")
            return
        finally:
            dlg.close()
        self._refresh_ui_for_active_tab()
        self.viewer.set_current_tab_session_path(path)
        self._remember_file_session_link(self.viewer.current_tab_file_path(), path)
        self._status_msg.setText(f"Session loaded from {path}")
        if path in self._recent_sessions:
            self._recent_sessions.remove(path)
        self._recent_sessions.insert(0, path)
        self._recent_sessions = self._recent_sessions[:10]
        self._save_recent_sessions()
        self._update_recent_session_menu()

    def _save_recent_sessions(self):
        QSettings("PyMeasure", "PyMeasure").setValue("recentSessions", self._recent_sessions)

    # ------------------------------------------------------------------
    # File ↔ session association memory
    # ------------------------------------------------------------------

    def _remember_file_session_link(self, file_path: str, session_path: str):
        if not file_path or not session_path:
            return
        norm = os.path.normcase(os.path.abspath(file_path))
        self._file_session_map[norm] = session_path
        self._save_file_session_map()

    def _save_file_session_map(self):
        QSettings("PyMeasure", "PyMeasure").setValue(
            "fileSessionMap", json.dumps(self._file_session_map),
        )

    # ------------------------------------------------------------------
    # Tab events
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_tab_changed(self, idx: int):
        self._refresh_ui_for_active_tab()

    @Slot(int)
    def _on_tab_close_requested(self, idx: int):
        if self.viewer.tab_has_session_state(idx):
            tab_path = self.viewer.tab_file_path(idx) or "Untitled"
            reply = QMessageBox.question(
                self, "Close Tab",
                f"Close “{os.path.basename(tab_path)}”?\n\n"
                "Unsaved measurements in this tab will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.viewer.close_tab(idx)

    def _refresh_ui_for_active_tab(self):
        """Sync all dependent panels (objects list, scale, origin, zoom, title, PDF nav)
        to reflect the current tab — call after a tab switch or session load."""
        self._rebuild_objects_list()

        if self.viewer.current_tab_index < 0:
            self.setWindowTitle("PyMeasure")
            self.left_panel.scale_lbl.setText("Scale: 1 px/px")
            self.left_panel.origin_lbl.setText("Origin: (0.00, 0.00)")
            self.left_panel.zoom_lbl.setText("Zoom: 100%")
            self.left_panel.pdf_box.setVisible(False)
            self._status_zoom.setText("100%")
            self._status_msg.setText("")
            return

        tab_path = self.viewer.current_tab_file_path() or "Untitled"
        self.setWindowTitle(f"PyMeasure — {os.path.basename(tab_path)}")

        si = self.viewer.scale_info
        self.left_panel.scale_lbl.setText(f"1 px = {si.scale_factor:.6g} {si.unit}")

        o  = self.viewer.origin
        ox, oy = self.viewer._origin_world
        self.left_panel.origin_lbl.setText(
            f"Origin: img ({o.x:.1f}, {o.y:.1f})\n  world ({ox:.4g}, {oy:.4g})"
        )

        pct = f"{self.viewer.zoom * 100:.0f}%"
        self.left_panel.zoom_lbl.setText(f"Zoom: {pct}")
        self._status_zoom.setText(pct)

        self._update_pdf_nav()

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
        self.viewer.state_restored.connect(self._refresh_ui_for_active_tab)
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
        self.right_panel.move_up_btn.clicked.connect(self.viewer.move_selected_up)
        self.right_panel.move_down_btn.clicked.connect(self.viewer.move_selected_down)

        self.left_panel.prev_page_btn.clicked.connect(self._go_prev_page)
        self.left_panel.next_page_btn.clicked.connect(self._go_next_page)

        self.viewer.tab_changed.connect(self._on_tab_changed)
        self.viewer.tab_close_requested.connect(self._on_tab_close_requested)

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
        self._status_coords.setText(
            f"x: {PREFS.fmt_coord(wx)}  y: {PREFS.fmt_coord(wy)}"
        )

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
        self._update_totals()

    def _update_totals(self):
        """Refresh the takeoff summary (counts + Σ length / Σ area) in the panel."""
        objs = self.viewer.objects
        if not objs:
            self.right_panel.totals_lbl.setText("No objects")
            return
        unit = self.viewer.scale_info.unit
        counts: dict[str, int] = {}
        total_len = total_area = 0.0
        for o in objs:
            counts[o.kind] = counts.get(o.kind, 0) + 1
            if o.kind in ("distance", "polyline"):
                total_len += o.value
            elif o.kind == "area":
                total_area += o.value
        order = ["point", "distance", "polyline", "angle", "area"]
        parts = [f"{counts[k]} {k}{'s' if counts[k] > 1 else ''}"
                 for k in order if k in counts]
        summary = f"{len(objs)} objects · " + ", ".join(parts)
        if total_len:
            summary += f"\nΣ length: {PREFS.fmt_value(total_len)} {unit}"
        if total_area:
            summary += f"\nΣ area: {PREFS.fmt_value(total_area)} {unit}²"
        self.right_panel.totals_lbl.setText(summary)

    def _object_list_label(self, obj: DiagramObject) -> str:
        # Points show their live world coordinates; every other kind delegates to
        # the model so the list, canvas and export share one formatting source.
        if obj.kind == "point" and obj.points:
            name = obj.name or "Point"
            wx, wy = self.viewer.img_to_world(QPointF(*obj.points[0]))
            return f"●{name}  ({PREFS.fmt_coord(wx)}, {PREFS.fmt_coord(wy)})"
        return obj.list_label()

    # ------------------------------------------------------------------
    # Right-panel list context menu
    # ------------------------------------------------------------------

    def _on_list_context_menu(self, pos):
        item = self.right_panel.objects_list.itemAt(pos)
        menu = QMenu(self)

        if item is not None:
            idx = self.right_panel.objects_list.row(item)
            if idx not in self.viewer._selection:
                self.viewer.set_selection([idx])
                self.selection_changed_via_panel(idx)
            menu.addAction("Edit…", lambda: self.viewer.open_edit_dialog_for(idx))
            menu.addAction("Copy Coordinates", lambda: self._copy_coordinates(idx))
            menu.addSeparator()

        sel = sorted(self.viewer._selection)
        copy_a = menu.addAction("Copy", self.viewer.copy_selection)
        paste_a = menu.addAction("Paste", lambda: self.viewer.paste())
        dup_a = menu.addAction("Duplicate", lambda: self.viewer.duplicate_selection())
        copy_a.setEnabled(bool(sel))
        paste_a.setEnabled(bool(self.viewer._clipboard))
        dup_a.setEnabled(bool(sel))

        if item is not None:
            menu.addSeparator()
            menu.addAction("Delete", lambda: self._delete_single(
                self.right_panel.objects_list.row(item)))

        menu.exec(self.right_panel.objects_list.mapToGlobal(pos))

    def selection_changed_via_panel(self, idx: int):
        """Sync right-panel list selection to a single row (used by context menu)."""
        self._syncing_selection = True
        self.right_panel.objects_list.clearSelection()
        item = self.right_panel.objects_list.item(idx)
        if item:
            item.setSelected(True)
        self._syncing_selection = False
        self.viewer.update()

    def _copy_coordinates(self, idx: int):
        obj = self.viewer.objects[idx]
        lines = ["x\ty"] + [
            "{:.6g}\t{:.6g}".format(*self.viewer.img_to_world(QPointF(x, y)))
            for x, y in obj.points
        ]
        QApplication.clipboard().setText("\n".join(lines))

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
            f"Delete {n} selected object{'s' if n > 1 else ''}?\nThis can be undone with Ctrl+Z.",
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
            self, "Open Image or PDF", self._last_open_dir,
            "Images & PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.pdf);;All Files (*)",
        )
        if path:
            self._load_path(path)

    def _update_pdf_nav(self):
        count = self.viewer.pdf_page_count
        self.left_panel.pdf_box.setVisible(count > 1)
        if count > 1:
            self.left_panel.page_lbl.setText(f"{self.viewer.current_page + 1} / {count}")

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def save_session(self):
        current = self.viewer.current_tab_session_path()
        if current and os.path.exists(current):
            self._do_save_session(current)
        else:
            self.save_session_as()

    def save_session_as(self):
        if self.viewer.current_tab_index < 0:
            QMessageBox.information(
                self, "Save Session", "Open an image or PDF first.",
            )
            return
        start_dir = self.viewer.current_tab_session_path() or ""
        path, _ = QFileDialog.getSaveFileName(self, "Save Session As", start_dir, "JSON Files (*.json)")
        if not path:
            return
        self._do_save_session(path)

    def _do_save_session(self, path: str):
        if self.viewer.current_tab_index < 0:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.viewer.session_data(), f, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "Save Session", f"Could not save session:\n{e}")
            return
        self.viewer.set_current_tab_session_path(path)
        self._remember_file_session_link(self.viewer.current_tab_file_path(), path)
        self._status_msg.setText(f"Session saved to {path}")
        if path in self._recent_sessions:
            self._recent_sessions.remove(path)
        self._recent_sessions.insert(0, path)
        self._recent_sessions = self._recent_sessions[:10]
        self._save_recent_sessions()
        self._update_recent_session_menu()

    def load_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "JSON Files (*.json)")
        if path:
            self._do_load_session(path)

    # ------------------------------------------------------------------
    # Export / About
    # ------------------------------------------------------------------

    def show_export(self):
        to_world = lambda x, y: self.viewer.img_to_world(QPointF(x, y))
        ExportDialog(self.viewer.objects, to_world, self).exec()

    def export_image(self):
        if self.viewer.current_tab_index < 0:
            QMessageBox.information(self, "Export Image", "Open an image or PDF first.")
            return
        img = self.viewer.render_annotated_image()
        if img is None or img.isNull():
            QMessageBox.warning(self, "Export Image", "Nothing to export.")
            return
        base = self.viewer.current_tab_file_path() or ""
        suggested = (os.path.splitext(base)[0] + "_annotated.png") if base else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Annotated Image", suggested,
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)",
        )
        if not path:
            return
        if img.save(path):
            self._status_msg.setText(f"Annotated image saved to {path}")
        else:
            QMessageBox.critical(self, "Export Image", f"Could not save image:\n{path}")

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def show_preferences(self):
        dlg = PreferencesDialog(PREFS, self)
        if dlg.exec() != PreferencesDialog.DialogCode.Accepted:
            return
        PREFS.value_sig_figs, PREFS.coord_decimals, PREFS.angle_in_radians = dlg.values()
        self._save_display_prefs(QSettings("PyMeasure", "PyMeasure"))
        # Re-render everything that shows a formatted number.
        self._rebuild_objects_list()
        self._refresh_ui_for_active_tab()
        self.viewer.update()

    def _load_display_prefs(self, settings: QSettings):
        PREFS.value_sig_figs = int(settings.value("display/valueSigFigs", PREFS.value_sig_figs))
        PREFS.coord_decimals = int(settings.value("display/coordDecimals", PREFS.coord_decimals))
        PREFS.angle_in_radians = settings.value(
            "display/angleRadians", PREFS.angle_in_radians, type=bool
        )

    def _save_display_prefs(self, settings: QSettings):
        settings.setValue("display/valueSigFigs", PREFS.value_sig_figs)
        settings.setValue("display/coordDecimals", PREFS.coord_decimals)
        settings.setValue("display/angleRadians", PREFS.angle_in_radians)

    # ------------------------------------------------------------------
    # Window state persistence
    # ------------------------------------------------------------------

    def _restore_window_state(self, settings: QSettings):
        geom = settings.value("window/geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        split = settings.value("window/splitter")
        if split is not None:
            self._splitter.restoreState(split)
        # View toggles — setChecked fires `toggled`, which applies to the viewer.
        self._show_objects_act.setChecked(settings.value("view/showObjects", True, type=bool))
        self._scale_bar_act.setChecked(settings.value("view/scaleBar", True, type=bool))
        self._snap_act.setChecked(settings.value("view/snapVertices", True, type=bool))

    def _save_window_state(self, settings: QSettings):
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/splitter", self._splitter.saveState())
        settings.setValue("view/showObjects", self._show_objects_act.isChecked())
        settings.setValue("view/scaleBar", self._scale_bar_act.isChecked())
        settings.setValue("view/snapVertices", self._snap_act.isChecked())

    def closeEvent(self, event):
        settings = QSettings("PyMeasure", "PyMeasure")
        self._save_window_state(settings)
        self._save_display_prefs(settings)
        super().closeEvent(event)

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
            "• Shift-lock to cardinal directions · snap to existing vertices<br>"
            "• Double-click to finish area or polyline<br>"
            "• Scale bar overlay · takeoff totals (Σ length / Σ area)<br>"
            "• Configurable display precision and angle units (Preferences)<br>"
            "• Undo / Redo · save and load sessions<br>"
            "• Export CSV / JSON · export annotated image<br><br>"
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
