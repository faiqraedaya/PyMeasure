import json
import os
import sys

from PySide6.QtCore import Qt, QPointF, QSettings, QSize, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QSizePolicy, QSplitter, QToolBar,
)

from ..core.constants import Tool, TOOL_HELP, TOOL_LABELS, TOOL_SHORTCUTS
from . import icons
from .dialogs import ExportDialog
from ..core.models import DiagramObject, Point, ScaleInfo
from .panel import RightPanel
from .viewer import ImageViewer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyMeasure")
        self.resize(1400, 800)

        self.viewer      = ImageViewer()
        self.right_panel = RightPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([1140, 260])
        splitter.setStretchFactor(0, 1)
        self.setCentralWidget(splitter)

        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._connect_signals()

        self.setStyleSheet("""
            QGroupBox { font-weight: bold; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
            QPushButton:checked { background-color: #0066cc; color: white; }
            QListWidget { font-size: 11px; }
            QToolBar { spacing: 1px; padding: 2px; border: none; }
            QToolBar::separator { width: 1px; background: #555; margin: 3px 5px; }
            QToolButton { padding: 3px; border-radius: 3px; }
            QToolButton:hover { background-color: #3a3a3a; }
            QToolButton:checked { background-color: #0066cc; }
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

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menus(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        self._add_action(file_menu, "&New",            "Ctrl+N",        self.new_document)
        self._add_action(file_menu, "&Open…",         "Ctrl+O",        self.open_file)
        self._recent_menu = file_menu.addMenu("Open &Recent")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Session",     "Ctrl+S",       self.save_session)
        self._add_action(file_menu, "Save Session &As…", "Ctrl+Shift+S", self.save_session_as)
        self._add_action(file_menu, "&Load Session…",    "Ctrl+Shift+O", self.load_session)
        self._recent_session_menu = file_menu.addMenu("Load &Recent Session")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Export Data…",  "Ctrl+E",        self.show_export)
        self._add_action(file_menu, "Export &View as Image…", "Ctrl+Shift+E", self.export_view_image)
        self._add_action(file_menu, "Snapshot View to &Clipboard", "Ctrl+Shift+C", self.snapshot_view_to_clipboard)
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
        view_menu.addSeparator()
        self._show_objects_act = QAction("Show All &Objects", self)
        self._show_objects_act.setCheckable(True)
        self._show_objects_act.setChecked(True)
        self._show_objects_act.setShortcut(QKeySequence("Ctrl+H"))
        self._show_objects_act.toggled.connect(self.viewer.set_objects_visible)
        view_menu.addAction(self._show_objects_act)

        self._show_labels_act = QAction("Show &Labels", self)
        self._show_labels_act.setCheckable(True)
        self._show_labels_act.setChecked(True)
        self._show_labels_act.setShortcut(QKeySequence("Ctrl+L"))
        self._show_labels_act.toggled.connect(self.viewer.set_labels_visible)
        view_menu.addAction(self._show_labels_act)

        view_menu.addSeparator()
        self._show_legend_act = QAction("Show Le&gend", self)
        self._show_legend_act.setCheckable(True)
        self._show_legend_act.setChecked(True)
        self._show_legend_act.toggled.connect(self.viewer.set_legend_visible)
        view_menu.addAction(self._show_legend_act)
        self._add_action(view_menu, "Edit Legend &Title…", None,
                         self.viewer.edit_legend_title)

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

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self._toolbar = tb

        # File / document actions
        new_act = tb.addAction(icons.action_icon("new"), "New")
        new_act.setToolTip("New — unload the current drawing  (Ctrl+N)")
        new_act.triggered.connect(self.new_document)
        open_act = tb.addAction(icons.action_icon("open"), "Open")
        open_act.setToolTip("Open image or PDF  (Ctrl+O)")
        open_act.triggered.connect(self.open_file)
        save_act = tb.addAction(icons.action_icon("save"), "Save Session")
        save_act.setToolTip("Save session  (Ctrl+S)")
        save_act.triggered.connect(self.save_session)
        export_act = tb.addAction(icons.action_icon("export"), "Export")
        export_act.setToolTip("Export data  (Ctrl+E)")
        export_act.triggered.connect(self.show_export)
        tb.addSeparator()

        # Tool actions — checkable and mutually exclusive
        self._tool_actions: dict[Tool, QAction] = {}
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)

        groups = [
            [Tool.PAN, Tool.SELECT, Tool.ZOOM_RECT],
            [Tool.SET_ORIGIN, Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS],
            [Tool.ADD_POINT, Tool.ADD_LINE, Tool.ADD_ANGLE, Tool.ADD_POLYGON,
             Tool.ADD_POLYLINE, Tool.ADD_ELLIPSE, Tool.ADD_TEXTBOX],
            [Tool.ADD_POINT_CONTOUR, Tool.ADD_POLYLINE_CONTOUR],
        ]
        for gi, group in enumerate(groups):
            for tool in group:
                act = QAction(icons.tool_icon(tool), TOOL_LABELS[tool], self)
                act.setCheckable(True)
                act.setToolTip(f"{TOOL_LABELS[tool]}  ({TOOL_SHORTCUTS[tool]})")
                act.triggered.connect(lambda checked, t=tool: self._set_tool(t))
                self._tool_group.addAction(act)
                tb.addAction(act)
                self._tool_actions[tool] = act
            if gi < len(groups) - 1:
                tb.addSeparator()

        # PDF navigation — hidden unless a multi-page PDF is active
        self._pdf_sep = tb.addSeparator()
        self._pdf_prev_act = tb.addAction(icons.action_icon("prev"), "Previous Page")
        self._pdf_prev_act.triggered.connect(self._go_prev_page)
        self._pdf_page_lbl = QLabel("1 / 1")
        self._pdf_page_lbl.setStyleSheet("padding: 0 6px;")
        self._pdf_page_lbl_act = tb.addWidget(self._pdf_page_lbl)
        self._pdf_next_act = tb.addAction(icons.action_icon("next"), "Next Page")
        self._pdf_next_act.triggered.connect(self._go_next_page)
        for a in (self._pdf_sep, self._pdf_prev_act,
                  self._pdf_page_lbl_act, self._pdf_next_act):
            a.setVisible(False)

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
            self._status_scale.setText("Scale: 1 px = 1 px")
            self._status_origin.setText("Origin: (0, 0)")
            self._status_zoom.setText("100%")
            self._status_msg.setText("")
            self._update_pdf_nav()
            return

        tab_path = self.viewer.current_tab_file_path() or "Untitled"
        self.setWindowTitle(f"PyMeasure — {os.path.basename(tab_path)}")

        si = self.viewer.scale_info
        self._status_scale.setText(f"Scale: 1 px = {si.scale_factor:.6g} {si.unit}")

        ox, oy = self.viewer._origin_world
        self._status_origin.setText(f"Origin: ({ox:.4g}, {oy:.4g})")

        pct = f"{self.viewer.zoom * 100:.0f}%"
        self._status_zoom.setText(pct)

        self._show_legend_act.blockSignals(True)
        self._show_legend_act.setChecked(self.viewer.legend_visible)
        self._show_legend_act.blockSignals(False)

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
        self._status_scale  = QLabel("Scale: 1 px = 1 px")
        self._status_origin = QLabel("Origin: (0, 0)")
        self._status_coords = QLabel("x: —  y: —")
        self._status_zoom   = QLabel("100%")

        sb.addPermanentWidget(self._status_live)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_scale)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_origin)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_coords)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_zoom)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
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

        self.viewer.tab_changed.connect(self._on_tab_changed)
        self.viewer.tab_close_requested.connect(self._on_tab_close_requested)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(Tool)
    def _set_tool(self, tool: Tool):
        self.viewer.set_tool(tool)
        act = self._tool_actions.get(tool)
        if act is not None and not act.isChecked():
            act.setChecked(True)
        self._status_msg.setText(TOOL_HELP[tool])

    @Slot(ScaleInfo)
    def _on_scale_set(self, si: ScaleInfo):
        text = f"1 px = {si.scale_factor:.6g} {si.unit}"
        self._status_scale.setText(f"Scale: {text}")
        self._status_msg.setText(f"Scale set: {text}")
        self._rebuild_objects_list()

    @Slot(Point)
    def _on_origin_set(self, pt: Point):
        ox, oy = self.viewer._origin_world
        self._status_origin.setText(f"Origin: ({ox:.4g}, {oy:.4g})")
        self._status_msg.setText(
            f"Origin set at img ({pt.x:.1f}, {pt.y:.1f}) = world ({ox:.4g}, {oy:.4g})"
        )
        self._rebuild_objects_list()

    @Slot(float, float)
    def _on_mouse_pos(self, wx: float, wy: float):
        self._status_coords.setText(f"x: {wx:.4f}  y: {wy:.4f}")

    @Slot(float)
    def _on_zoom_changed(self, zoom: float):
        self._status_zoom.setText(f"{zoom * 100:.0f}%")

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
        # Points show their world coordinates; everything else uses the model's
        # own label (which already lists all of an object's measurements).
        if obj.kind == "point" and obj.points:
            icon = obj._ICONS.get("point", "● ")
            name = obj.name if obj.name else "Point"
            wx, wy = self.viewer.img_to_world(QPointF(*obj.points[0]))
            return f"{icon}{name}  ({wx:.4f}, {wy:.4f})"
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
            menu.addAction("Copy Coordinates", lambda: self.viewer._copy_coordinates(idx))
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

    def new_document(self):
        """Unload the current drawing + session (fresh start)."""
        idx = self.viewer.current_tab_index
        if idx < 0:
            return
        if self.viewer.tab_has_session_state(idx):
            reply = QMessageBox.question(
                self, "New",
                "Start a new document?\n\nThe current drawing and its measurements "
                "will be unloaded. Save the session first if you want to keep them.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.viewer.close_tab(idx)
        self._refresh_ui_for_active_tab()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image or PDF", self._last_open_dir,
            "Images & PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.pdf);;All Files (*)",
        )
        if path:
            self._load_path(path)

    def _update_pdf_nav(self):
        count = self.viewer.pdf_page_count
        multi = count > 1
        for a in (self._pdf_sep, self._pdf_prev_act,
                  self._pdf_page_lbl_act, self._pdf_next_act):
            a.setVisible(multi)
        if multi:
            self._pdf_page_lbl.setText(f"{self.viewer.current_page + 1} / {count}")

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

    def export_view_image(self):
        if self.viewer.current_tab_index < 0:
            QMessageBox.information(self, "Export View", "Open an image or PDF first.")
            return
        tab_path = self.viewer.current_tab_file_path()
        base = os.path.splitext(os.path.basename(tab_path))[0] if tab_path else "view"
        start = os.path.join(self._last_open_dir, f"{base}.png") if self._last_open_dir else f"{base}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export View as Image", start,
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)",
        )
        if not path:
            return
        pixmap = self.viewer.grab_canvas()
        if pixmap.isNull() or not pixmap.save(path):
            QMessageBox.critical(self, "Export View", f"Could not save image to:\n{path}")
            return
        self._status_msg.setText(f"View exported to {path}")

    def snapshot_view_to_clipboard(self):
        if self.viewer.current_tab_index < 0:
            QMessageBox.information(self, "Snapshot View", "Open an image or PDF first.")
            return
        pixmap = self.viewer.grab_canvas()
        if pixmap.isNull():
            QMessageBox.critical(self, "Snapshot View", "Could not capture the current view.")
            return
        QApplication.clipboard().setPixmap(pixmap)
        self._status_msg.setText("View copied to clipboard")

    def show_about(self):
        QMessageBox.about(
            self, "About PyMeasure",
            "<b>PyMeasure v2.0</b><br><br>"
            "Features:<br>"
            "• Open images (PNG, JPEG, BMP, TIFF) and multi-page PDFs<br>"
            "• Pan and zoom · middle-click or scroll · Zoom Rectangle (Z)<br>"
            "• Set origin and scale (by distance or coordinates)<br>"
            "• Add labelled points, lines, angles, polygons, polylines, ellipses, text<br>"
            "• Draw polyline / point risk contours with merged same-label levels<br>"
            "• On-canvas legend (editable title) · toggle labels · per-object colors<br>"
            "• Annotations persist on canvas with labels<br>"
            "• Select, move, cut, copy, paste objects in Pan/Zoom mode<br>"
            "• Drag vertex handles directly when an object is selected<br>"
            "• Right-click a vertex to delete it · right-click an edge to insert<br>"
            "• Shift-lock to cardinal directions while measuring<br>"
            "• Double-click to finish polygon or polyline<br>"
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
