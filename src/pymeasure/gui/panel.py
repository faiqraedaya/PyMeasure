from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QVBoxLayout, QWidget,
)

from ..core.constants import Tool, TOOL_LABELS, TOOL_SHORTCUTS


class LeftPanel(QWidget):
    """Left column: tool buttons and image/scale info."""
    tool_selected = Signal(Tool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self._tool_buttons: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # Tools
        tools_box = QGroupBox("Tools")
        tools_layout = QVBoxLayout(tools_box)
        tools_layout.setSpacing(2)
        for tool in Tool:
            label = f"{TOOL_LABELS[tool]}  [{TOOL_SHORTCUTS[tool]}]"
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tool: self.tool_selected.emit(t))
            tools_layout.addWidget(btn)
            self._tool_buttons[tool] = btn
        outer.addWidget(tools_box)

        # Image Info
        info_box = QGroupBox("Image Info")
        info_layout = QVBoxLayout(info_box)
        self.origin_lbl = QLabel("Origin: (0.00, 0.00)")
        self.scale_lbl  = QLabel("Scale: 1 px/px")
        self.zoom_lbl   = QLabel("Zoom: 100%")
        info_layout.addWidget(self.origin_lbl)
        info_layout.addWidget(self.scale_lbl)
        info_layout.addWidget(self.zoom_lbl)
        outer.addWidget(info_box)

        # PDF Navigation
        self.pdf_box = QGroupBox("PDF Navigation")
        pdf_layout = QHBoxLayout(self.pdf_box)
        self.prev_page_btn = QPushButton("◄")
        self.prev_page_btn.setFixedWidth(30)
        self.page_lbl = QLabel("1 / 1")
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_page_btn = QPushButton("►")
        self.next_page_btn.setFixedWidth(30)
        pdf_layout.addWidget(self.prev_page_btn)
        pdf_layout.addWidget(self.page_lbl)
        pdf_layout.addWidget(self.next_page_btn)
        self.pdf_box.setVisible(False)
        outer.addWidget(self.pdf_box)

        outer.addStretch()

    def select_tool(self, tool: Tool):
        for t, btn in self._tool_buttons.items():
            btn.setChecked(t == tool)


class RightPanel(QWidget):
    """Right column: unified objects list with selection and context menu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        obj_box = QGroupBox("Objects")
        obj_layout = QVBoxLayout(obj_box)

        self.objects_list = QListWidget()
        self.objects_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.objects_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.objects_list.setToolTip(
            "Click to select · Ctrl+click to toggle · Shift+click for range\n"
            "Double-click to edit · Right-click for context menu"
        )
        obj_layout.addWidget(self.objects_list, 1)

        move_row = QHBoxLayout()
        self.move_up_btn   = QPushButton("Move Up")
        self.move_down_btn = QPushButton("Move Down")
        move_row.addWidget(self.move_up_btn)
        move_row.addWidget(self.move_down_btn)
        obj_layout.addLayout(move_row)

        del_row = QHBoxLayout()
        self.del_obj_btn   = QPushButton("Delete Selected")
        self.clear_all_btn = QPushButton("Delete All")
        del_row.addWidget(self.del_obj_btn)
        del_row.addWidget(self.clear_all_btn)
        obj_layout.addLayout(del_row)

        self.export_btn = QPushButton("Export…")
        obj_layout.addWidget(self.export_btn)

        outer.addWidget(obj_box, 1)
