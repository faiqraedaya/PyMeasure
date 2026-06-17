from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QListWidget,
    QPushButton, QVBoxLayout, QWidget,
)


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
