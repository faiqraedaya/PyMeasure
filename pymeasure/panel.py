from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .constants import Tool, TOOL_LABELS, TOOL_SHORTCUTS


class LeftPanel(QWidget):
    tool_selected = Signal(Tool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(230)

        self._tool_buttons: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # Tools group
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

        # Scale & Info group
        info_box = QGroupBox("Scale & Info")
        info_layout = QVBoxLayout(info_box)
        self.origin_lbl = QLabel("Origin: img (0, 0)")
        self.scale_lbl = QLabel("Scale: 1 px/px")
        self.zoom_lbl = QLabel("Zoom: 100%")
        info_layout.addWidget(self.origin_lbl)
        info_layout.addWidget(self.scale_lbl)
        info_layout.addWidget(self.zoom_lbl)
        outer.addWidget(info_box)

        # PDF Navigation group
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

        # Points of Interest group
        pts_box = QGroupBox("Points of Interest")
        pts_layout = QVBoxLayout(pts_box)
        self.points_list = QListWidget()
        self.points_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        pts_layout.addWidget(self.points_list)
        pts_btn_row = QHBoxLayout()
        self.del_point_btn = QPushButton("Delete Selected")
        self.clear_points_btn = QPushButton("Clear All")
        pts_btn_row.addWidget(self.del_point_btn)
        pts_btn_row.addWidget(self.clear_points_btn)
        pts_layout.addLayout(pts_btn_row)
        outer.addWidget(pts_box)

        # Measurements group
        meas_box = QGroupBox("Measurements")
        meas_layout = QVBoxLayout(meas_box)
        self.meas_list = QListWidget()
        meas_layout.addWidget(self.meas_list)
        meas_btn_row = QHBoxLayout()
        self.clear_meas_btn = QPushButton("Clear All")
        self.export_btn = QPushButton("Export…")
        meas_btn_row.addWidget(self.clear_meas_btn)
        meas_btn_row.addWidget(self.export_btn)
        meas_layout.addLayout(meas_btn_row)
        outer.addWidget(meas_box)

        outer.addStretch()

    def select_tool(self, tool: Tool):
        for t, btn in self._tool_buttons.items():
            btn.setChecked(t == tool)
