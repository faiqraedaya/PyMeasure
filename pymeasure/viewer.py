import math
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, Slot
from PySide6.QtGui import (
    QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import QDialog, QMenu, QSizePolicy, QWidget

from .constants import Tool
from .dialogs import EditPointDialog, PointLabelDialog, ScaleCoordsDialog, ScaleDistanceDialog
from .models import Measurement, Point, ScaleInfo

_HIT_R = 8  # hit-test radius in screen pixels


# ---------------------------------------------------------------------------
# Geometry helpers (module-level, no state)
# ---------------------------------------------------------------------------

def _dist_pt_to_seg(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _point_in_polygon(px, py, poly) -> bool:
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _snap_cardinal(base: QPointF, pos: QPointF) -> QPointF:
    dx = pos.x() - base.x()
    dy = pos.y() - base.y()
    angle = math.atan2(dy, dx)
    snapped = round(angle / (math.pi / 2)) * (math.pi / 2)
    dist = math.hypot(dx, dy)
    return QPointF(base.x() + dist * math.cos(snapped), base.y() + dist * math.sin(snapped))


# ---------------------------------------------------------------------------
# ImageViewer
# ---------------------------------------------------------------------------

class ImageViewer(QWidget):
    point_added = Signal(Point)
    scale_set = Signal(ScaleInfo)
    origin_set = Signal(Point)
    measurement_done = Signal(Measurement)
    mouse_world_pos = Signal(float, float)
    zoom_changed = Signal(float)
    state_restored = Signal()
    tool_change_requested = Signal(Tool)  # emitted when Esc cancels to PAN
    points_changed = Signal()            # emitted after any point list mutation
    measurements_changed = Signal()      # emitted after any measurement mutation

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pixmap: Optional[QPixmap] = None
        self._pdf_doc: Optional[fitz.Document] = None
        self._pdf_page_index: int = 0
        self._pdf_dpi: int = 150

        self._zoom: float = 1.0
        self._pan: QPointF = QPointF(0.0, 0.0)
        self._panning: bool = False
        self._pan_start_screen: QPointF = QPointF()
        self._pan_start_pan: QPointF = QPointF()

        self.origin: Point = Point(0.0, 0.0)
        self.scale_info: ScaleInfo = ScaleInfo(1.0, 1.0, "px")
        self.current_tool: Tool = Tool.PAN

        self._temp: List[Point] = []
        self.points_of_interest: List[Point] = []
        self.measurements: List[Measurement] = []

        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []

        # Live mouse position for preview line
        self._mouse_img: Optional[QPointF] = None
        self._shift_held: bool = False

        # Drag state  ("" | "point_move" | "meas_move" | "meas_edit")
        self._drag_mode: str = ""
        self._drag_idx: int = -1    # index into points_of_interest or measurements
        self._drag_vtx: int = -1    # vertex index (meas_edit only)
        self._drag_active: bool = False
        self._drag_start_img: QPointF = QPointF()
        self._drag_start_pts: list = []   # position backup for cancel / undo
        self._drag_start_snap: dict = {}  # full state snapshot before drag

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def current_page(self) -> int:
        return self._pdf_page_index

    @property
    def pdf_page_count(self) -> int:
        return len(self._pdf_doc) if self._pdf_doc is not None else 0

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _img_to_screen(self, img_pt: QPointF) -> QPointF:
        cx, cy = self.width() / 2, self.height() / 2
        return QPointF(
            (img_pt.x() - self._pan.x()) * self._zoom + cx,
            (img_pt.y() - self._pan.y()) * self._zoom + cy,
        )

    def _screen_to_img(self, screen_pt: QPointF) -> QPointF:
        cx, cy = self.width() / 2, self.height() / 2
        return QPointF(
            (screen_pt.x() - cx) / self._zoom + self._pan.x(),
            (screen_pt.y() - cy) / self._zoom + self._pan.y(),
        )

    def img_to_world(self, img_pt: QPointF) -> Tuple[float, float]:
        sf = self.scale_info.scale_factor
        return (img_pt.x() - self.origin.x) * sf, -(img_pt.y() - self.origin.y) * sf

    def _world_to_img(self, wx: float, wy: float) -> QPointF:
        sf = self.scale_info.scale_factor
        if sf == 0:
            return QPointF(self.origin.x, self.origin.y)
        return QPointF(wx / sf + self.origin.x, -wy / sf + self.origin.y)

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def load_file(self, path: str) -> bool:
        ok = self._load_pdf(path) if path.lower().endswith(".pdf") else self._load_image(path)
        if ok:
            self.fit_to_window()
        return ok

    def _load_image(self, path: str) -> bool:
        px = QPixmap(path)
        if px.isNull():
            return False
        if self._pdf_doc is not None:
            self._pdf_doc.close()
            self._pdf_doc = None
        self._pixmap = px
        return True

    def _load_pdf(self, path: str) -> bool:
        try:
            doc = fitz.open(path)
        except Exception:
            return False
        if self._pdf_doc is not None:
            self._pdf_doc.close()
        self._pdf_doc = doc
        self._pdf_page_index = 0
        return self._render_pdf_page()

    def _render_pdf_page(self) -> bool:
        if self._pdf_doc is None:
            return False
        page = self._pdf_doc[self._pdf_page_index]
        mat = fitz.Matrix(self._pdf_dpi / 72, self._pdf_dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        qimg = QImage.fromData(pix.tobytes("png"))
        if qimg.isNull():
            return False
        self._pixmap = QPixmap.fromImage(qimg)
        return True

    def go_to_page(self, index: int):
        if self._pdf_doc is None:
            return
        clamped = max(0, min(index, len(self._pdf_doc) - 1))
        if clamped == self._pdf_page_index:
            return
        self._pdf_page_index = clamped
        if self._render_pdf_page():
            self.update()

    def set_pdf_dpi(self, dpi: int):
        self._pdf_dpi = max(72, min(600, dpi))
        if self._pdf_doc is not None:
            self._render_pdf_page()
            self.update()

    # ------------------------------------------------------------------
    # View helpers
    # ------------------------------------------------------------------

    def fit_to_window(self):
        if self._pixmap is None:
            return
        img_w, img_h = self._pixmap.width(), self._pixmap.height()
        if img_w == 0 or img_h == 0:
            return
        w = self.width() or 800
        h = self.height() or 600
        self._zoom = min(w / img_w, h / img_h) * 0.95
        self._pan = QPointF(img_w / 2, img_h / 2)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_zoom(self, zoom: float):
        self._zoom = max(0.05, min(20.0, zoom))
        self.zoom_changed.emit(self._zoom)
        self.update()

    # ------------------------------------------------------------------
    # Cursor helper
    # ------------------------------------------------------------------

    def _update_cursor(self):
        if self._drag_mode == "meas_edit":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._drag_mode:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif self.current_tool == Tool.PAN:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2b2b2b"))

        if self._pixmap is None:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Open an image or PDF to get started",
            )
            return

        img_w, img_h = self._pixmap.width(), self._pixmap.height()
        cx, cy = self.width() / 2, self.height() / 2
        x0 = cx - self._pan.x() * self._zoom
        y0 = cy - self._pan.y() * self._zoom
        dest = QRectF(x0, y0, img_w * self._zoom, img_h * self._zoom)
        painter.drawPixmap(dest, self._pixmap, QRectF(self._pixmap.rect()))

        self._paint_origin(painter)
        self._paint_measurements(painter)
        self._paint_points(painter)
        self._paint_temp(painter)

    def _paint_origin(self, painter: QPainter):
        sp = self._img_to_screen(QPointF(self.origin.x, self.origin.y))
        painter.setPen(QPen(QColor("#ff4444"), 2))
        x, y = int(sp.x()), int(sp.y())
        painter.drawLine(x - 12, y, x + 12, y)
        painter.drawLine(x, y - 12, x, y + 12)

    def _paint_points(self, painter: QPainter):
        for pt in self.points_of_interest:
            sp = self._img_to_screen(QPointF(pt.x, pt.y))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#4488ff")))
            painter.drawEllipse(sp, 5.0, 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if pt.label:
                painter.setPen(QColor("white"))
                painter.drawText(QPointF(sp.x() + 9, sp.y() - 7), pt.label)
                wx, wy = self.img_to_world(QPointF(pt.x, pt.y))
                painter.setPen(QColor("#aaaaaa"))
                painter.drawText(QPointF(sp.x() + 9, sp.y() + 6), f"({wx:.2f}, {wy:.2f})")

    def _paint_measurements(self, painter: QPainter):
        for i, m in enumerate(self.measurements):
            if not m.points:
                continue
            in_edit = self._drag_mode == "meas_edit" and self._drag_idx == i

            if m.kind == "distance" and len(m.points) == 2:
                sp0 = self._img_to_screen(QPointF(*m.points[0]))
                sp1 = self._img_to_screen(QPointF(*m.points[1]))
                painter.setPen(QPen(QColor("#ffdd00"), 2))
                painter.drawLine(sp0, sp1)
                mid = QPointF((sp0.x() + sp1.x()) / 2, (sp0.y() + sp1.y()) / 2)
                painter.setPen(QColor("white"))
                painter.drawText(QPointF(mid.x() + 5, mid.y() - 5), m.display_short())
                if in_edit:
                    self._paint_vertex_handles(painter, m.points)

            elif m.kind == "angle" and len(m.points) == 3:
                sp = [self._img_to_screen(QPointF(*p)) for p in m.points]
                painter.setPen(QPen(QColor("#ff8800"), 2))
                painter.drawLine(sp[0], sp[1])
                painter.drawLine(sp[2], sp[1])
                painter.setPen(QColor("white"))
                painter.drawText(QPointF(sp[1].x() + 5, sp[1].y() - 5), m.display_short())
                if in_edit:
                    self._paint_vertex_handles(painter, m.points)

            elif m.kind == "area" and len(m.points) >= 3:
                sps = [self._img_to_screen(QPointF(*p)) for p in m.points]
                fill = QColor("#ff6699")
                fill.setAlpha(40)
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(QColor("#ff6699"), 2))
                painter.drawPolygon(QPolygonF(sps))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                cx = sum(s.x() for s in sps) / len(sps)
                cy = sum(s.y() for s in sps) / len(sps)
                painter.setPen(QColor("white"))
                painter.drawText(QPointF(cx + 5, cy), m.display_short())
                if in_edit:
                    self._paint_vertex_handles(painter, m.points)

    def _paint_vertex_handles(self, painter: QPainter, points: list):
        painter.setPen(QPen(QColor("#00ff88"), 1))
        painter.setBrush(QBrush(QColor("#00ff88")))
        for px, py in points:
            sp = self._img_to_screen(QPointF(px, py))
            painter.drawEllipse(sp, 6.0, 6.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_temp(self, painter: QPainter):
        if not self._temp:
            return

        pts_screen = [self._img_to_screen(QPointF(p.x, p.y)) for p in self._temp]

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#00cc66")))
        for sp in pts_screen:
            painter.drawEllipse(sp, 5.0, 5.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        tool = self.current_tool
        preview_pt = self._preview_screen_pt()

        if tool == Tool.MEASURE_DISTANCE:
            if len(pts_screen) == 1 and preview_pt:
                painter.setPen(QPen(QColor("#ffdd00"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], preview_pt)

        elif tool == Tool.MEASURE_ANGLE:
            painter.setPen(QPen(QColor("#ff8800"), 2))
            for i in range(len(pts_screen) - 1):
                painter.drawLine(pts_screen[i], pts_screen[i + 1])
            if preview_pt:
                painter.setPen(QPen(QColor("#ff8800"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[-1], preview_pt)

        elif tool in (Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS):
            if len(pts_screen) == 2:
                painter.setPen(QPen(QColor("#cc66ff"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], pts_screen[1])
            elif len(pts_screen) == 1 and preview_pt:
                painter.setPen(QPen(QColor("#cc66ff"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], preview_pt)

        elif tool == Tool.MEASURE_AREA:
            all_pts = pts_screen + ([preview_pt] if preview_pt else [])
            painter.setPen(QPen(QColor("#ff6699"), 2))
            fill = QColor("#ff6699")
            fill.setAlpha(30)
            painter.setBrush(QBrush(fill))
            if len(all_pts) >= 2:
                painter.drawPolygon(QPolygonF(all_pts))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("white"))
            for i, sp in enumerate(pts_screen):
                painter.drawText(QPointF(sp.x() + 7, sp.y() - 4), str(i + 1))

    def _preview_screen_pt(self) -> Optional[QPointF]:
        if self._mouse_img is None or not self._temp:
            return None
        img = self._apply_snap(self._mouse_img)
        return self._img_to_screen(img)

    def _apply_snap(self, img_pos: QPointF) -> QPointF:
        if self._shift_held and self._temp:
            return _snap_cardinal(QPointF(self._temp[-1].x, self._temp[-1].y), img_pos)
        return img_pos

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    def set_tool(self, tool: Tool):
        if self._drag_mode:
            self._cancel_drag()
        self.current_tool = tool
        self._temp.clear()
        self._update_cursor()
        self.update()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        pos = QPointF(event.position())
        btn = event.button()

        # Drag mode takes priority
        if self._drag_mode:
            if btn == Qt.MouseButton.RightButton:
                self._cancel_drag()
            elif btn == Qt.MouseButton.LeftButton and not self._drag_active:
                self._begin_drag(pos)
            return

        is_pan = btn == Qt.MouseButton.MiddleButton or (
            btn == Qt.MouseButton.LeftButton and self.current_tool == Tool.PAN
        )
        if is_pan:
            self._panning = True
            self._pan_start_screen = pos
            self._pan_start_pan = QPointF(self._pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif btn == Qt.MouseButton.LeftButton:
            self._left_click(pos)
        elif btn == Qt.MouseButton.RightButton:
            self._right_click(pos)

    def mouseMoveEvent(self, event):
        pos = QPointF(event.position())

        if self._panning:
            delta = pos - self._pan_start_screen
            self._pan = QPointF(
                self._pan_start_pan.x() - delta.x() / self._zoom,
                self._pan_start_pan.y() - delta.y() / self._zoom,
            )
            self.update()

        if self._pixmap is not None:
            img_pos = self._screen_to_img(pos)
            self._mouse_img = img_pos
            wx, wy = self.img_to_world(img_pos)
            self.mouse_world_pos.emit(wx, wy)

        if self._drag_active:
            img_pos = self._screen_to_img(pos)
            dx = img_pos.x() - self._drag_start_img.x()
            dy = img_pos.y() - self._drag_start_img.y()

            if self._drag_mode == "point_move":
                pt = self.points_of_interest[self._drag_idx]
                ox, oy = self._drag_start_pts[0]
                pt.x = ox + dx
                pt.y = oy + dy

            elif self._drag_mode == "meas_move":
                m = self.measurements[self._drag_idx]
                m.points = [[ox + dx, oy + dy] for ox, oy in self._drag_start_pts]

            elif self._drag_mode == "meas_edit":
                m = self.measurements[self._drag_idx]
                ox, oy = self._drag_start_pts[self._drag_vtx]
                m.points[self._drag_vtx] = [ox + dx, oy + dy]
                self._recalculate_measurement(m)

        self.update()

    def mouseReleaseEvent(self, event):
        btn = event.button()

        if self._panning and btn in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._panning = False
            self._update_cursor()
            return

        if self._drag_active and btn == Qt.MouseButton.LeftButton:
            # Commit: push pre-drag snapshot so Ctrl+Z reverts
            self._undo_stack.append(self._drag_start_snap)
            self._redo_stack.clear()
            self._drag_active = False
            self._drag_start_pts = []

            if self._drag_mode == "meas_edit":
                self._recalculate_measurement(self.measurements[self._drag_idx])
                self._drag_vtx = -1
                # Stay in meas_edit so user can drag more vertices
                self.measurements_changed.emit()
            else:
                self._exit_drag_mode()
            self.update()

    def wheelEvent(self, event):
        pos = QPointF(event.position())
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        mouse_img = self._screen_to_img(pos)
        self._zoom = max(0.05, min(20.0, self._zoom * factor))
        cx, cy = self.width() / 2, self.height() / 2
        self._pan = QPointF(
            mouse_img.x() - (pos.x() - cx) / self._zoom,
            mouse_img.y() - (pos.y() - cy) / self._zoom,
        )
        self.zoom_changed.emit(self._zoom)
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._drag_mode:
                self._cancel_drag()
            elif self.current_tool != Tool.PAN:
                self._temp.clear()
                self.tool_change_requested.emit(Tool.PAN)
                self.set_tool(Tool.PAN)
            else:
                self._temp.clear()
            self.update()
        elif key == Qt.Key.Key_Shift:
            self._shift_held = True
            self.update()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self._shift_held = False
            self.update()
        else:
            super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------

    def _left_click(self, screen_pos: QPointF):
        img_pos = self._screen_to_img(screen_pos)
        tool = self.current_tool

        # Apply shift snap when we have an anchor point
        snapping_tools = {
            Tool.MEASURE_DISTANCE, Tool.MEASURE_ANGLE, Tool.MEASURE_AREA,
            Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS,
        }
        if self._shift_held and self._temp and tool in snapping_tools:
            img_pos = self._apply_snap(img_pos)

        img_pt = Point(img_pos.x(), img_pos.y())

        if tool == Tool.SET_ORIGIN:
            self._push_undo()
            self.origin = img_pt
            self.origin_set.emit(img_pt)
            self.update()

        elif tool in (Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS):
            self._temp.append(img_pt)
            if len(self._temp) == 2:
                self._finish_scale()
            self.update()

        elif tool == Tool.ADD_POINT:
            default_label = f"P{len(self.points_of_interest) + 1}"
            dlg = PointLabelDialog(default_label, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._push_undo()
                labeled_pt = Point(img_pt.x, img_pt.y, dlg.label())
                self.points_of_interest.append(labeled_pt)
                self.point_added.emit(labeled_pt)
                self.update()

        elif tool == Tool.MEASURE_DISTANCE:
            self._temp.append(img_pt)
            if len(self._temp) == 2:
                self._finish_distance()
            self.update()

        elif tool == Tool.MEASURE_ANGLE:
            self._temp.append(img_pt)
            if len(self._temp) == 3:
                self._finish_angle()
            self.update()

        elif tool == Tool.MEASURE_AREA:
            self._temp.append(img_pt)
            self.update()

    def _right_click(self, screen_pos: QPointF):
        tool = self.current_tool

        # Exit vertex-edit mode
        if self._drag_mode == "meas_edit":
            self._exit_drag_mode()
            return

        # Close area polygon or undo last temp point
        if tool == Tool.MEASURE_AREA and len(self._temp) >= 3:
            self._finish_area()
            return
        if self._temp:
            self._temp.pop()
            self.update()
            return

        # Context menu hit-testing
        pt_idx = self._hit_point(screen_pos)
        if pt_idx >= 0:
            self._show_point_menu(pt_idx, screen_pos)
            return

        meas_idx = self._hit_measurement(screen_pos)
        if meas_idx >= 0:
            self._show_meas_menu(meas_idx, screen_pos)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_point(self, screen_pos: QPointF) -> int:
        for i, pt in enumerate(self.points_of_interest):
            sp = self._img_to_screen(QPointF(pt.x, pt.y))
            if math.hypot(sp.x() - screen_pos.x(), sp.y() - screen_pos.y()) <= _HIT_R:
                return i
        return -1

    def _hit_measurement(self, screen_pos: QPointF) -> int:
        img_pos = self._screen_to_img(screen_pos)
        px, py = img_pos.x(), img_pos.y()

        for i, m in enumerate(self.measurements):
            if not m.points:
                continue

            if m.kind == "distance" and len(m.points) == 2:
                sp0 = self._img_to_screen(QPointF(*m.points[0]))
                sp1 = self._img_to_screen(QPointF(*m.points[1]))
                d = _dist_pt_to_seg(
                    screen_pos.x(), screen_pos.y(),
                    sp0.x(), sp0.y(), sp1.x(), sp1.y(),
                )
                if d <= _HIT_R:
                    return i

            elif m.kind == "angle" and len(m.points) == 3:
                sp = [self._img_to_screen(QPointF(*p)) for p in m.points]
                d1 = _dist_pt_to_seg(
                    screen_pos.x(), screen_pos.y(),
                    sp[0].x(), sp[0].y(), sp[1].x(), sp[1].y(),
                )
                d2 = _dist_pt_to_seg(
                    screen_pos.x(), screen_pos.y(),
                    sp[2].x(), sp[2].y(), sp[1].x(), sp[1].y(),
                )
                if min(d1, d2) <= _HIT_R:
                    return i

            elif m.kind == "area" and len(m.points) >= 3:
                if _point_in_polygon(px, py, m.points):
                    return i
                n = len(m.points)
                for j in range(n):
                    sp_a = self._img_to_screen(QPointF(*m.points[j]))
                    sp_b = self._img_to_screen(QPointF(*m.points[(j + 1) % n]))
                    d = _dist_pt_to_seg(
                        screen_pos.x(), screen_pos.y(),
                        sp_a.x(), sp_a.y(), sp_b.x(), sp_b.y(),
                    )
                    if d <= _HIT_R:
                        return i

        return -1

    def _hit_meas_vertex(self, meas_idx: int, screen_pos: QPointF) -> int:
        m = self.measurements[meas_idx]
        for vi, (vx, vy) in enumerate(m.points):
            sp = self._img_to_screen(QPointF(vx, vy))
            if math.hypot(sp.x() - screen_pos.x(), sp.y() - screen_pos.y()) <= _HIT_R:
                return vi
        return -1

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    def _show_point_menu(self, idx: int, screen_pos: QPointF):
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self._edit_point(idx))
        menu.addAction("Move", lambda: self._start_point_move(idx))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_point_ctx(idx))
        menu.exec(self.mapToGlobal(screen_pos.toPoint()))

    def _show_meas_menu(self, idx: int, screen_pos: QPointF):
        menu = QMenu(self)
        menu.addAction("Edit Vertices", lambda: self._start_meas_edit(idx))
        menu.addAction("Move", lambda: self._start_meas_move(idx))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_meas_ctx(idx))
        menu.exec(self.mapToGlobal(screen_pos.toPoint()))

    def _edit_point(self, idx: int):
        pt = self.points_of_interest[idx]
        wx, wy = self.img_to_world(QPointF(pt.x, pt.y))
        dlg = EditPointDialog(pt.label, wx, wy, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_label, new_wx, new_wy = dlg.values()
        img_pt = self._world_to_img(new_wx, new_wy)
        self._push_undo()
        pt.label = new_label
        pt.x = img_pt.x()
        pt.y = img_pt.y()
        self.points_changed.emit()
        self.update()

    def _delete_point_ctx(self, idx: int):
        self._push_undo()
        del self.points_of_interest[idx]
        self.points_changed.emit()
        self.update()

    def _start_point_move(self, idx: int):
        self._drag_mode = "point_move"
        self._drag_idx = idx
        self._update_cursor()

    def _start_meas_move(self, idx: int):
        self._drag_mode = "meas_move"
        self._drag_idx = idx
        self._update_cursor()

    def _start_meas_edit(self, idx: int):
        self._drag_mode = "meas_edit"
        self._drag_idx = idx
        self._update_cursor()
        self.update()

    def _delete_meas_ctx(self, idx: int):
        self._push_undo()
        del self.measurements[idx]
        self.measurements_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # Drag helpers
    # ------------------------------------------------------------------

    def _begin_drag(self, screen_pos: QPointF):
        img_pos = self._screen_to_img(screen_pos)

        if self._drag_mode == "meas_edit":
            vtx = self._hit_meas_vertex(self._drag_idx, screen_pos)
            if vtx < 0:
                return
            m = self.measurements[self._drag_idx]
            self._drag_start_snap = self._snapshot()
            self._drag_start_pts = [list(p) for p in m.points]
            self._drag_vtx = vtx
            self._drag_active = True
            self._drag_start_img = img_pos

        elif self._drag_mode == "point_move":
            if not (0 <= self._drag_idx < len(self.points_of_interest)):
                return
            pt = self.points_of_interest[self._drag_idx]
            self._drag_start_snap = self._snapshot()
            self._drag_start_pts = [(pt.x, pt.y)]
            self._drag_active = True
            self._drag_start_img = img_pos

        elif self._drag_mode == "meas_move":
            if not (0 <= self._drag_idx < len(self.measurements)):
                return
            m = self.measurements[self._drag_idx]
            self._drag_start_snap = self._snapshot()
            self._drag_start_pts = [list(p) for p in m.points]
            self._drag_active = True
            self._drag_start_img = img_pos

    def _cancel_drag(self):
        if self._drag_active and self._drag_start_pts:
            if self._drag_mode == "point_move" and 0 <= self._drag_idx < len(self.points_of_interest):
                pt = self.points_of_interest[self._drag_idx]
                pt.x, pt.y = self._drag_start_pts[0]
            elif self._drag_mode in ("meas_move", "meas_edit") and 0 <= self._drag_idx < len(self.measurements):
                m = self.measurements[self._drag_idx]
                m.points = [list(p) for p in self._drag_start_pts]
                self._recalculate_measurement(m)
        self._drag_active = False
        self._drag_start_pts = []
        self._exit_drag_mode(emit_signal=False)

    def _exit_drag_mode(self, emit_signal: bool = True):
        mode = self._drag_mode
        self._drag_mode = ""
        self._drag_idx = -1
        self._drag_vtx = -1
        self._drag_active = False
        self._drag_start_pts = []
        self._update_cursor()
        if emit_signal:
            if mode == "point_move":
                self.points_changed.emit()
            elif mode in ("meas_move", "meas_edit"):
                self.measurements_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # Measurement recalculation (after vertex moves)
    # ------------------------------------------------------------------

    def _recalculate_measurement(self, m: Measurement):
        pts = [Point(x, y) for x, y in m.points]
        if m.kind == "distance" and len(pts) == 2:
            m.value = pts[0].distance_to(pts[1]) * self.scale_info.scale_factor
        elif m.kind == "angle" and len(pts) == 3:
            p1, vertex, p2 = pts
            v1x, v1y = p1.x - vertex.x, p1.y - vertex.y
            v2x, v2y = p2.x - vertex.x, p2.y - vertex.y
            dot = v1x * v2x + v1y * v2y
            mag = math.hypot(v1x, v1y) * math.hypot(v2x, v2y)
            m.value = math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))) if mag > 0 else 0.0
        elif m.kind == "area" and len(pts) >= 3:
            n = len(pts)
            area = sum(
                pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y
                for i in range(n)
            )
            m.value = abs(area) / 2.0 * (self.scale_info.scale_factor ** 2)

    # ------------------------------------------------------------------
    # Finish helpers
    # ------------------------------------------------------------------

    def _finish_scale(self):
        pixel_dist = self._temp[0].distance_to(self._temp[1])
        tool = self.current_tool

        if tool == Tool.SET_SCALE_DISTANCE:
            dlg = ScaleDistanceDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                real_dist, unit = dlg.values()
                self._push_undo()
                self.scale_info = ScaleInfo(pixel_dist, real_dist, unit)
                self.scale_set.emit(self.scale_info)

        elif tool == Tool.SET_SCALE_COORDS:
            dlg = ScaleCoordsDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                (x1, y1, x2, y2), unit = dlg.values()
                real_dist = math.hypot(x2 - x1, y2 - y1)
                self._push_undo()
                self.scale_info = ScaleInfo(pixel_dist, real_dist, unit)
                self.scale_set.emit(self.scale_info)

        self._temp.clear()
        self.update()

    def _finish_distance(self):
        p0, p1 = self._temp[0], self._temp[1]
        pixel_dist = p0.distance_to(p1)
        real_dist = pixel_dist * self.scale_info.scale_factor
        m = Measurement(
            "distance", real_dist, self.scale_info.unit,
            points=[[p0.x, p0.y], [p1.x, p1.y]],
        )
        self._push_undo()
        self.measurements.append(m)
        self.measurement_done.emit(m)
        self._temp.clear()
        self.update()

    def _finish_angle(self):
        p1, vertex, p2 = self._temp
        v1x, v1y = p1.x - vertex.x, p1.y - vertex.y
        v2x, v2y = p2.x - vertex.x, p2.y - vertex.y
        dot = v1x * v2x + v1y * v2y
        mag = math.hypot(v1x, v1y) * math.hypot(v2x, v2y)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))) if mag > 0 else 0.0
        m = Measurement(
            "angle", angle, "°",
            points=[[p.x, p.y] for p in self._temp],
        )
        self._push_undo()
        self.measurements.append(m)
        self.measurement_done.emit(m)
        self._temp.clear()
        self.update()

    def _finish_area(self):
        pts = self._temp
        n = len(pts)
        area = sum(
            pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y
            for i in range(n)
        )
        pixel_area = abs(area) / 2.0
        real_area = pixel_area * (self.scale_info.scale_factor ** 2)
        m = Measurement(
            "area", real_area, self.scale_info.unit,
            points=[[p.x, p.y] for p in pts],
        )
        self._push_undo()
        self.measurements.append(m)
        self.measurement_done.emit(m)
        self._temp.clear()
        self.update()

    # ------------------------------------------------------------------
    # Public state-mutation (encapsulate undo for callers)
    # ------------------------------------------------------------------

    def clear_points(self):
        if not self.points_of_interest:
            return
        self._push_undo()
        self.points_of_interest.clear()
        self.update()

    def clear_measurements(self):
        if not self.measurements:
            return
        self._push_undo()
        self.measurements.clear()
        self.update()

    def clear_all(self):
        self._push_undo()
        self.points_of_interest.clear()
        self.measurements.clear()
        self.update()

    def delete_point(self, index: int):
        if index < 0 or index >= len(self.points_of_interest):
            return
        self._push_undo()
        del self.points_of_interest[index]
        self.update()

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        return {
            "origin": (self.origin.x, self.origin.y),
            "scale_info": (
                self.scale_info.pixel_distance,
                self.scale_info.real_distance,
                self.scale_info.unit,
            ),
            "points": [(p.x, p.y, p.label) for p in self.points_of_interest],
            "measurements": [
                (m.kind, m.value, m.unit, m.timestamp, [list(p) for p in m.points])
                for m in self.measurements
            ],
        }

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()

    def _restore(self, snap: dict):
        self.origin = Point(snap["origin"][0], snap["origin"][1])
        self.scale_info = ScaleInfo(*snap["scale_info"])
        self.points_of_interest = [Point(x, y, lbl) for x, y, lbl in snap["points"]]
        self.measurements = [
            Measurement(k, v, u, t, pts)
            for k, v, u, t, pts in snap["measurements"]
        ]
        self._temp.clear()
        self.state_restored.emit()
        self.update()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def session_data(self) -> dict:
        return {
            "scale_info": self.scale_info.to_dict(),
            "origin": self.origin.to_dict(),
            "points": [p.to_dict() for p in self.points_of_interest],
            "measurements": [m.to_dict() for m in self.measurements],
        }

    def load_session(self, data: dict):
        self.scale_info = ScaleInfo.from_dict(data["scale_info"])
        self.origin = Point.from_dict(data["origin"])
        self.points_of_interest = [Point.from_dict(p) for p in data.get("points", [])]
        self.measurements = [Measurement.from_dict(m) for m in data.get("measurements", [])]
        self._temp.clear()
        self.update()
