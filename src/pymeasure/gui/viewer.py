import math
from copy import deepcopy
from datetime import datetime
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSizePolicy, QWidget

from ..core.constants import Tool
from .dialogs import (
    EditObjectDialog, NameDialog, ScaleCoordsDialog, ScaleDistanceDialog, SetOriginDialog,
)
from ..core.models import DiagramObject, Point, ScaleInfo

_HIT_R      = 8   # hit-test radius in screen pixels
_DRAG_THRESH = 4  # pixels before a press becomes a drag

_KIND_COLOR = {
    "point":    QColor("#4488ff"),
    "distance": QColor("#ffdd00"),
    "angle":    QColor("#ff8800"),
    "area":     QColor("#ff6699"),
    "polyline": QColor("#44ddaa"),
}
_SEL_COLOR   = QColor("#00ddff")
_LABEL_COLOR = QColor("#dd0000")
_PREVIEW_COLOR = QColor("#dd0000")


# ---------------------------------------------------------------------------
# Geometry helpers
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


def _seg_insert_point(screen_pos: QPointF, sa: QPointF, sb: QPointF) -> QPointF:
    """Project screen_pos onto segment sa→sb and return the closest screen point."""
    ax, ay = sa.x(), sa.y()
    bx, by = sb.x(), sb.y()
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((screen_pos.x() - ax) * dx + (screen_pos.y() - ay) * dy) / denom)) if denom else 0.0
    return QPointF(ax + t * dx, ay + t * dy)


# ---------------------------------------------------------------------------
# ImageViewer
# ---------------------------------------------------------------------------

class ImageViewer(QWidget):
    # Informational
    scale_set          = Signal(ScaleInfo)
    origin_set         = Signal(Point)
    mouse_world_pos    = Signal(float, float)
    zoom_changed       = Signal(float)
    live_measure       = Signal(str)

    # State changes
    state_restored        = Signal()
    tool_change_requested = Signal(Tool)
    objects_changed       = Signal()
    selection_changed     = Signal(list)
    delete_requested      = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pixmap: Optional[QPixmap] = None
        self._pdf_doc = None
        self._pdf_page_index = 0
        self._pdf_dpi = 150

        self._zoom = 1.0
        self._pan  = QPointF(0.0, 0.0)
        self._panning      = False
        self._pan_start_screen = QPointF()
        self._pan_start_pan    = QPointF()
        self._pan_moved        = False

        self.origin        = Point(0.0, 0.0)
        self._origin_world = (0.0, 0.0)
        self.scale_info    = ScaleInfo(1.0, 1.0, "px")
        self.current_tool  = Tool.PAN

        self._temp: List[Point] = []
        self.objects: List[DiagramObject] = []
        self._clipboard: List[DiagramObject] = []
        self._selection: set = set()

        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []

        self._mouse_img: Optional[QPointF] = None
        self._shift_held = False

        # Vertex drag (in PAN mode, on selected object)
        self._vtx_drag_obj    = -1
        self._vtx_drag_vtx    = -1
        self._vtx_drag_active = False
        self._vtx_drag_start_img  = QPointF()
        self._vtx_drag_start_pts: list = []
        self._vtx_drag_snap: dict = {}

        # Selection drag (PAN mode, moving whole objects)
        self._sel_press_obj = -1
        self._sel_press_pos: Optional[QPointF] = None
        self._sel_drag_active   = False
        self._sel_drag_start    = QPointF()
        self._sel_drag_start_pts: dict = {}
        self._sel_drag_snap: dict = {}

        # Zoom-rect tool
        self._zoom_rect_start: Optional[QPointF] = None   # screen coords

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ------------------------------------------------------------------
    # Properties
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
        ox, oy = self._origin_world
        return (img_pt.x() - self.origin.x) * sf + ox, -(img_pt.y() - self.origin.y) * sf + oy

    def _world_to_img(self, wx: float, wy: float) -> QPointF:
        sf = self.scale_info.scale_factor
        if sf == 0:
            return QPointF(self.origin.x, self.origin.y)
        ox, oy = self._origin_world
        return QPointF(
            (wx - ox) / sf + self.origin.x,
            -(wy - oy) / sf + self.origin.y,
        )

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
        iw, ih = self._pixmap.width(), self._pixmap.height()
        if iw == 0 or ih == 0:
            return
        w = self.width() or 800
        h = self.height() or 600
        self._zoom = min(w / iw, h / ih) * 0.95
        self._pan  = QPointF(iw / 2, ih / 2)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_zoom(self, zoom: float):
        self._zoom = max(0.05, min(20.0, zoom))
        self.zoom_changed.emit(self._zoom)
        self.update()

    def _update_cursor_for_pos(self, screen_pos: Optional[QPointF] = None):
        """Set cursor based on tool and what is under screen_pos."""
        if self.current_tool == Tool.ZOOM_RECT:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if self.current_tool != Tool.PAN:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if self._panning or self._vtx_drag_active or self._sel_drag_active:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if screen_pos is not None:
            # Vertex handle on a selected object?
            for i in self._selection:
                obj = self.objects[i]
                if obj.kind == "point":
                    continue
                for vx, vy in obj.points:
                    sp = self._img_to_screen(QPointF(vx, vy))
                    if math.hypot(sp.x() - screen_pos.x(), sp.y() - screen_pos.y()) <= _HIT_R:
                        self.setCursor(Qt.CursorShape.PointingHandCursor)
                        return
            # Hovering over any object?
            if self._hit_object(screen_pos) >= 0:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2b2b2b"))

        if self._pixmap is None:
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Open an image or PDF to get started")
            return

        iw, ih = self._pixmap.width(), self._pixmap.height()
        cx, cy = self.width() / 2, self.height() / 2
        x0 = cx - self._pan.x() * self._zoom
        y0 = cy - self._pan.y() * self._zoom
        dest = QRectF(x0, y0, iw * self._zoom, ih * self._zoom)
        painter.drawPixmap(dest, self._pixmap, QRectF(self._pixmap.rect()))

        self._paint_origin(painter)
        self._paint_objects(painter)
        self._paint_temp(painter)
        self._paint_zoom_rect(painter)

    def _paint_origin(self, painter: QPainter):
        sp = self._img_to_screen(QPointF(self.origin.x, self.origin.y))
        painter.setPen(QPen(QColor("#ff4444"), 2))
        x, y = int(sp.x()), int(sp.y())
        painter.drawLine(x - 12, y, x + 12, y)
        painter.drawLine(x, y - 12, x, y + 12)

    def _paint_objects(self, painter: QPainter):
        for i, obj in enumerate(self.objects):
            selected = i in self._selection
            color    = _KIND_COLOR.get(obj.kind, QColor("white"))

            if obj.kind == "point":
                self._paint_point(painter, obj, i, selected)
            elif obj.kind == "distance":
                self._paint_distance(painter, obj, color, selected)
                if selected:
                    self._paint_vertex_handles(painter, obj.points)
            elif obj.kind == "angle":
                self._paint_angle(painter, obj, color, selected)
                if selected:
                    self._paint_vertex_handles(painter, obj.points)
            elif obj.kind == "area":
                self._paint_area(painter, obj, color, selected)
                if selected:
                    self._paint_vertex_handles(painter, obj.points)
            elif obj.kind == "polyline":
                self._paint_polyline(painter, obj, color, selected)
                if selected:
                    self._paint_vertex_handles(painter, obj.points)

    def _paint_point(self, painter, obj, idx, selected):
        if not obj.points:
            return
        sp = self._img_to_screen(QPointF(*obj.points[0]))
        color = _KIND_COLOR["point"]
        if selected:
            painter.setPen(QPen(_SEL_COLOR, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(sp, 9.0, 9.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(sp, 5.0, 5.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        label = obj.name or f"P{idx + 1}"
        painter.setPen(_LABEL_COLOR)
        painter.drawText(QPointF(sp.x() + 9, sp.y() - 7), label)
        wx, wy = self.img_to_world(QPointF(*obj.points[0]))
        painter.setPen(_LABEL_COLOR)
        painter.drawText(QPointF(sp.x() + 9, sp.y() + 6), f"({wx:.2f}, {wy:.2f})")

    def _paint_distance(self, painter, obj, color, selected):
        if len(obj.points) < 2:
            return
        sp0 = self._img_to_screen(QPointF(*obj.points[0]))
        sp1 = self._img_to_screen(QPointF(*obj.points[1]))
        if selected:
            painter.setPen(QPen(_SEL_COLOR, 4))
            painter.drawLine(sp0, sp1)
        painter.setPen(QPen(color, 2))
        painter.drawLine(sp0, sp1)
        mid = QPointF((sp0.x() + sp1.x()) / 2, (sp0.y() + sp1.y()) / 2)
        painter.setPen(_LABEL_COLOR)
        label = obj.name or "Line"
        painter.drawText(QPointF(mid.x() + 5, mid.y() - 5), f"{label}: {obj.display_short()}")

    def _paint_angle(self, painter, obj, color, selected):
        if len(obj.points) < 3:
            return
        sp = [self._img_to_screen(QPointF(*p)) for p in obj.points]
        if selected:
            painter.setPen(QPen(_SEL_COLOR, 4))
            painter.drawLine(sp[0], sp[1])
            painter.drawLine(sp[2], sp[1])
        painter.setPen(QPen(color, 2))
        painter.drawLine(sp[0], sp[1])
        painter.drawLine(sp[2], sp[1])
        painter.setPen(_LABEL_COLOR)
        label = obj.name or "Angle"
        painter.drawText(QPointF(sp[1].x() + 5, sp[1].y() - 5), f"{label}: {obj.display_short()}")

    def _paint_area(self, painter, obj, color, selected):
        if len(obj.points) < 3:
            return
        sps = [self._img_to_screen(QPointF(*p)) for p in obj.points]
        if selected:
            painter.setPen(QPen(_SEL_COLOR, 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QPolygonF(sps))
        fill = QColor(color)
        fill.setAlpha(40)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(color, 2))
        painter.drawPolygon(QPolygonF(sps))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx = sum(s.x() for s in sps) / len(sps)
        cy = sum(s.y() for s in sps) / len(sps)
        painter.setPen(_LABEL_COLOR)
        label = obj.name or "Area"
        painter.drawText(QPointF(cx + 5, cy), f"{label}: {obj.display_short()}")

    def _paint_polyline(self, painter, obj, color, selected):
        if len(obj.points) < 2:
            return
        sps = [self._img_to_screen(QPointF(*p)) for p in obj.points]
        if selected:
            painter.setPen(QPen(_SEL_COLOR, 4))
            for i in range(len(sps) - 1):
                painter.drawLine(sps[i], sps[i + 1])
        painter.setPen(QPen(color, 2))
        for i in range(len(sps) - 1):
            painter.drawLine(sps[i], sps[i + 1])
        mid = sps[len(sps) // 2]
        painter.setPen(_LABEL_COLOR)
        label = obj.name or "Polyline"
        painter.drawText(QPointF(mid.x() + 5, mid.y() - 5), f"{label}: {obj.display_short()}")

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

        tool    = self.current_tool
        preview = self._preview_screen_pt()

        if tool == Tool.ADD_LINE:
            if len(pts_screen) == 1 and preview:
                painter.setPen(QPen(_PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], preview)

        elif tool == Tool.ADD_ANGLE:
            painter.setPen(QPen(QColor("#ff8800"), 2))
            for i in range(len(pts_screen) - 1):
                painter.drawLine(pts_screen[i], pts_screen[i + 1])
            if preview:
                painter.setPen(QPen(QColor("#ff8800"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[-1], preview)

        elif tool in (Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS):
            if len(pts_screen) == 2:
                painter.setPen(QPen(QColor("#cc66ff"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], pts_screen[1])
            elif len(pts_screen) == 1 and preview:
                painter.setPen(QPen(QColor("#cc66ff"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[0], preview)

        elif tool == Tool.ADD_AREA:
            all_pts = pts_screen + ([preview] if preview else [])
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

        elif tool == Tool.ADD_POLYLINE:
            painter.setPen(QPen(QColor("#44ddaa"), 2))
            for i in range(len(pts_screen) - 1):
                painter.drawLine(pts_screen[i], pts_screen[i + 1])
            if preview and pts_screen:
                painter.setPen(QPen(_PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
                painter.drawLine(pts_screen[-1], preview)
            painter.setPen(QColor("white"))
            for i, sp in enumerate(pts_screen):
                painter.drawText(QPointF(sp.x() + 7, sp.y() - 4), str(i + 1))

    def _paint_zoom_rect(self, painter: QPainter):
        if self.current_tool != Tool.ZOOM_RECT or self._zoom_rect_start is None:
            return
        if self._mouse_img is None:
            return
        s0 = self._zoom_rect_start
        s1 = self._img_to_screen(self._mouse_img)
        rect = QRectF(s0, s1).normalized()
        painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
        fill = QColor("#ffffff")
        fill.setAlpha(20)
        painter.setBrush(QBrush(fill))
        painter.drawRect(rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _preview_screen_pt(self) -> Optional[QPointF]:
        if self._mouse_img is None or not self._temp:
            return None
        return self._img_to_screen(self._apply_snap(self._mouse_img))

    def _apply_snap(self, img_pos: QPointF) -> QPointF:
        if self._shift_held and self._temp:
            return _snap_cardinal(QPointF(self._temp[-1].x, self._temp[-1].y), img_pos)
        return img_pos

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    def set_tool(self, tool: Tool):
        self._vtx_drag_active = False
        self._vtx_drag_obj    = -1
        self._vtx_drag_vtx    = -1
        self._sel_drag_active = False
        self._sel_press_obj   = -1
        self._zoom_rect_start = None
        self.current_tool = tool
        self._temp.clear()
        self._update_cursor_for_pos()
        self.update()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        pos = QPointF(event.position())
        btn = event.button()

        if btn == Qt.MouseButton.MiddleButton:
            self._start_pan(pos)
            return

        if btn == Qt.MouseButton.LeftButton:
            if self.current_tool == Tool.ZOOM_RECT:
                self._zoom_rect_start = pos
                return

            if self.current_tool == Tool.PAN:
                # Vertex drag on selected object?
                vtx_obj, vtx_idx = self._hit_selected_vertex(pos)
                if vtx_obj >= 0:
                    self._begin_vtx_drag(vtx_obj, vtx_idx, pos)
                    return
                hit = self._hit_object(pos)
                if hit >= 0:
                    self._sel_press_obj = hit
                    self._sel_press_pos = pos
                else:
                    self._start_pan(pos)
            else:
                self._left_click(pos)

        elif btn == Qt.MouseButton.RightButton:
            self._right_click(pos)

    def mouseMoveEvent(self, event):
        pos = QPointF(event.position())

        if self._pixmap is not None:
            self._mouse_img = self._screen_to_img(pos)
            wx, wy = self.img_to_world(self._mouse_img)
            self.mouse_world_pos.emit(wx, wy)
            self._emit_live_measure()

        if self._panning:
            delta = pos - self._pan_start_screen
            if math.hypot(delta.x(), delta.y()) > _DRAG_THRESH:
                self._pan_moved = True
            self._pan = QPointF(
                self._pan_start_pan.x() - delta.x() / self._zoom,
                self._pan_start_pan.y() - delta.y() / self._zoom,
            )
            self.update()
            return

        if self._vtx_drag_active:
            img_pos = self._screen_to_img(pos)
            dx = img_pos.x() - self._vtx_drag_start_img.x()
            dy = img_pos.y() - self._vtx_drag_start_img.y()
            obj = self.objects[self._vtx_drag_obj]
            ox, oy = self._vtx_drag_start_pts[self._vtx_drag_vtx]
            obj.points[self._vtx_drag_vtx] = [ox + dx, oy + dy]
            self._recalculate_object(obj)
            self.update()
            return

        if self._sel_press_obj >= 0 and self._sel_press_pos is not None:
            delta = pos - self._sel_press_pos
            if not self._sel_drag_active and math.hypot(delta.x(), delta.y()) > _DRAG_THRESH:
                if self._sel_press_obj not in self._selection:
                    self._selection = {self._sel_press_obj}
                    self.selection_changed.emit(sorted(self._selection))
                self._sel_drag_snap = self._snapshot()
                self._sel_drag_start = self._screen_to_img(self._sel_press_pos)
                self._sel_drag_start_pts = {
                    i: [list(p) for p in self.objects[i].points]
                    for i in self._selection
                }
                self._sel_drag_active = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

            if self._sel_drag_active:
                img_pos = self._screen_to_img(pos)
                dx = img_pos.x() - self._sel_drag_start.x()
                dy = img_pos.y() - self._sel_drag_start.y()
                for i in self._selection:
                    orig = self._sel_drag_start_pts[i]
                    self.objects[i].points = [[x + dx, y + dy] for x, y in orig]
                    if self.objects[i].kind != "point":
                        self._recalculate_object(self.objects[i])
                self.update()
                return

        if self.current_tool == Tool.ZOOM_RECT and self._zoom_rect_start is not None:
            self.update()
            return

        # Update hover cursor
        self._update_cursor_for_pos(pos)
        self.update()

    def mouseReleaseEvent(self, event):
        btn = event.button()

        if self._panning and btn in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._panning = False
            if not self._pan_moved:
                self._selection.clear()
                self.selection_changed.emit([])
            self._update_cursor_for_pos(QPointF(event.position()))
            return

        if self._vtx_drag_active and btn == Qt.MouseButton.LeftButton:
            self._undo_stack.append(self._vtx_drag_snap)
            self._redo_stack.clear()
            self._recalculate_object(self.objects[self._vtx_drag_obj])
            self._vtx_drag_active = False
            self._vtx_drag_vtx    = -1
            self._vtx_drag_start_pts = []
            self.objects_changed.emit()
            self._update_cursor_for_pos(QPointF(event.position()))
            self.update()
            return

        if btn == Qt.MouseButton.LeftButton and self.current_tool == Tool.PAN:
            if self._sel_drag_active:
                self._undo_stack.append(self._sel_drag_snap)
                self._redo_stack.clear()
                self._sel_drag_active = False
                self._sel_press_obj   = -1
                self._sel_press_pos   = None
                self.objects_changed.emit()
                self._update_cursor_for_pos(QPointF(event.position()))
                self.update()
            elif self._sel_press_obj >= 0:
                self._handle_selection_click(self._sel_press_obj, event.modifiers())
                self._sel_press_obj = -1
                self._sel_press_pos = None

        if btn == Qt.MouseButton.LeftButton and self.current_tool == Tool.ZOOM_RECT:
            self._finish_zoom_rect(QPointF(event.position()))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fit_to_window()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool = self.current_tool
        # The first click of the double-click already added a point via mousePressEvent.
        # Finish with that point included.
        if tool == Tool.ADD_AREA and len(self._temp) >= 3:
            self._finish_area()
        elif tool == Tool.ADD_POLYLINE and len(self._temp) >= 2:
            self._finish_polyline()

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
        key  = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            if self._vtx_drag_active:
                self._cancel_vtx_drag()
            elif self._selection:
                self._selection.clear()
                self.selection_changed.emit([])
                self.update()
            elif self.current_tool != Tool.PAN:
                self._temp.clear()
                self.tool_change_requested.emit(Tool.PAN)
                self.set_tool(Tool.PAN)
            else:
                self._temp.clear()
                self.update()

        elif key == Qt.Key.Key_Delete and self.current_tool == Tool.PAN and self._selection:
            self.delete_requested.emit()

        elif key == Qt.Key.Key_Shift:
            self._shift_held = True
            self.update()

        elif mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self.copy_selection()
            elif key == Qt.Key.Key_X:
                self.cut_selection()
            elif key == Qt.Key.Key_V:
                self.paste()
            elif key == Qt.Key.Key_A:
                self.select_all()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self._shift_held = False
            self.update()
        else:
            super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Pan helper
    # ------------------------------------------------------------------

    def _start_pan(self, pos: QPointF):
        self._panning = True
        self._pan_moved = False
        self._pan_start_screen = pos
        self._pan_start_pan    = QPointF(self._pan)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _handle_selection_click(self, idx: int, mods):
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if ctrl:
            if idx in self._selection:
                self._selection.discard(idx)
            else:
                self._selection.add(idx)
        else:
            self._selection = {idx}
        self.selection_changed.emit(sorted(self._selection))
        self.update()

    def set_selection(self, indices: list):
        self._selection = set(indices)
        self.update()

    def select_all(self):
        self._selection = set(range(len(self.objects)))
        self.selection_changed.emit(sorted(self._selection))
        self.update()

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def copy_selection(self):
        if not self._selection:
            return
        self._clipboard = [deepcopy(self.objects[i]) for i in sorted(self._selection)]

    def cut_selection(self):
        if not self._selection:
            return
        self.copy_selection()
        self._push_undo()
        for i in sorted(self._selection, reverse=True):
            del self.objects[i]
        self._selection.clear()
        self.selection_changed.emit([])
        self.objects_changed.emit()
        self.update()

    def paste(self, screen_pos: Optional[QPointF] = None):
        if not self._clipboard:
            return
        all_pts = [p for obj in self._clipboard for p in obj.points]
        if screen_pos is not None and all_pts:
            img_pos = self._screen_to_img(screen_pos)
            cx = sum(p[0] for p in all_pts) / len(all_pts)
            cy = sum(p[1] for p in all_pts) / len(all_pts)
            off_x = img_pos.x() - cx
            off_y = img_pos.y() - cy
        else:
            off_x = off_y = 20.0

        self._push_undo()
        base = len(self.objects)
        for obj in self._clipboard:
            new_obj = deepcopy(obj)
            new_obj.points = [[x + off_x, y + off_y] for x, y in new_obj.points]
            new_obj.timestamp = datetime.now().strftime("%H:%M:%S")
            self.objects.append(new_obj)

        self._selection = set(range(base, len(self.objects)))
        self.selection_changed.emit(sorted(self._selection))
        self.objects_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_selected(self):
        if not self._selection:
            return
        self._push_undo()
        for i in sorted(self._selection, reverse=True):
            del self.objects[i]
        self._selection.clear()
        self.selection_changed.emit([])
        self.objects_changed.emit()
        self.update()

    def clear_all_objects(self):
        if not self.objects:
            return
        self._push_undo()
        self.objects.clear()
        self._selection.clear()
        self.selection_changed.emit([])
        self.objects_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------

    def _left_click(self, screen_pos: QPointF):
        img_pos = self._screen_to_img(screen_pos)
        tool    = self.current_tool

        snapping_tools = {
            Tool.ADD_LINE, Tool.ADD_ANGLE, Tool.ADD_AREA, Tool.ADD_POLYLINE,
            Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS,
        }
        if self._shift_held and self._temp and tool in snapping_tools:
            img_pos = self._apply_snap(img_pos)

        img_pt = Point(img_pos.x(), img_pos.y())

        if tool == Tool.SET_ORIGIN:
            dlg = SetOriginDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                wx, wy = dlg.values()
                self._push_undo()
                self.origin = img_pt
                self._origin_world = (wx, wy)
                self.origin_set.emit(img_pt)
                self.update()

        elif tool in (Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS):
            self._temp.append(img_pt)
            if len(self._temp) == 2:
                self._finish_scale()
            self.update()

        elif tool == Tool.ADD_POINT:
            name = self._ask_object_name("point")
            if name is None:
                return
            self._push_undo()
            obj = DiagramObject(
                kind="point", name=name,
                points=[[img_pt.x, img_pt.y]],
            )
            self.objects.append(obj)
            self.objects_changed.emit()
            self.update()

        elif tool == Tool.ADD_LINE:
            self._temp.append(img_pt)
            if len(self._temp) == 2:
                self._finish_distance()
            self.update()

        elif tool == Tool.ADD_ANGLE:
            self._temp.append(img_pt)
            if len(self._temp) == 3:
                self._finish_angle()
            self.update()

        elif tool in (Tool.ADD_AREA, Tool.ADD_POLYLINE):
            self._temp.append(img_pt)
            self.update()

    def _right_click(self, screen_pos: QPointF):
        tool = self.current_tool

        if tool == Tool.PAN:
            self._show_pan_context_menu(screen_pos)
            return

        # Close area / finish polyline, or pop last temp point
        if tool == Tool.ADD_AREA and len(self._temp) >= 3:
            self._finish_area()
            return
        if tool == Tool.ADD_POLYLINE and len(self._temp) >= 2:
            self._finish_polyline()
            return
        if self._temp:
            self._temp.pop()
            self.update()

    # ------------------------------------------------------------------
    # Zoom rect
    # ------------------------------------------------------------------

    def _finish_zoom_rect(self, end_screen: QPointF):
        if self._zoom_rect_start is None:
            return
        start = self._zoom_rect_start
        self._zoom_rect_start = None

        rect = QRectF(start, end_screen).normalized()
        if rect.width() < 4 or rect.height() < 4:
            self.update()
            return

        # Convert rect corners to image coords
        img_tl = self._screen_to_img(rect.topLeft())
        img_br = self._screen_to_img(rect.bottomRight())
        img_w  = abs(img_br.x() - img_tl.x())
        img_h  = abs(img_br.y() - img_tl.y())
        if img_w < 1 or img_h < 1:
            self.update()
            return

        # Zoom so the rect fills 95% of the viewport
        vw = self.width() or 800
        vh = self.height() or 600
        new_zoom = min(vw / img_w, vh / img_h) * 0.95
        new_zoom = max(0.05, min(20.0, new_zoom))

        # Pan so rect centre is at viewport centre
        cx_img = (img_tl.x() + img_br.x()) / 2
        cy_img = (img_tl.y() + img_br.y()) / 2
        self._zoom = new_zoom
        self._pan  = QPointF(cx_img, cy_img)
        self.zoom_changed.emit(self._zoom)
        self.update()

    # ------------------------------------------------------------------
    # PAN-mode context menu
    # ------------------------------------------------------------------

    def _show_pan_context_menu(self, screen_pos: QPointF):
        # --- vertex hit on a selected object? → delete-vertex or insert-vertex menu
        vtx_obj, vtx_idx = self._hit_selected_vertex(screen_pos)
        if vtx_obj >= 0:
            obj = self.objects[vtx_obj]
            min_verts = 3 if obj.kind == "area" else 2
            if len(obj.points) > min_verts:
                menu = QMenu(self)
                menu.addAction("Delete Vertex", lambda: self._delete_vertex(vtx_obj, vtx_idx))
                menu.exec(self.mapToGlobal(screen_pos.toPoint()))
            return

        # --- edge hit on a selected area or polyline? → insert vertex
        edge_obj, edge_idx, insert_pt = self._hit_selected_edge(screen_pos)
        if edge_obj >= 0:
            menu = QMenu(self)
            menu.addAction("Insert Vertex Here",
                           lambda: self._insert_vertex(edge_obj, edge_idx, insert_pt))
            menu.exec(self.mapToGlobal(screen_pos.toPoint()))
            return

        # --- regular object / empty context menu
        hit = self._hit_object(screen_pos)
        if hit >= 0 and hit not in self._selection:
            self._selection = {hit}
            self.selection_changed.emit(sorted(self._selection))
            self.update()

        menu = QMenu(self)
        sel  = sorted(self._selection)

        if len(sel) == 1:
            menu.addAction("Edit…", lambda: self._open_edit_dialog(sel[0]))
            menu.addAction("Copy Coordinates", lambda: self._copy_coordinates(sel[0]))
            menu.addSeparator()

        cut_a   = menu.addAction("Cut",   self.cut_selection)
        copy_a  = menu.addAction("Copy",  self.copy_selection)
        paste_a = menu.addAction("Paste", lambda: self.paste(screen_pos))
        cut_a.setEnabled(bool(sel))
        copy_a.setEnabled(bool(sel))
        paste_a.setEnabled(bool(self._clipboard))

        if sel:
            menu.addSeparator()
            menu.addAction("Delete", self.delete_requested.emit)

        img_pt = self._screen_to_img(screen_pos)
        wx, wy = self.img_to_world(img_pt)
        menu.addSeparator()
        menu.addAction(
            f"Copy Cursor Coordinates  ({wx:.6g}, {wy:.6g})",
            lambda: QApplication.clipboard().setText(f"{wx:.6g}\t{wy:.6g}"),
        )

        menu.exec(self.mapToGlobal(screen_pos.toPoint()))

    def _copy_coordinates(self, idx: int):
        obj = self.objects[idx]
        lines = ["x\ty"] + [
            "{:.6g}\t{:.6g}".format(*self.img_to_world(QPointF(x, y)))
            for x, y in obj.points
        ]
        QApplication.clipboard().setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Vertex operations (delete / insert)
    # ------------------------------------------------------------------

    def _delete_vertex(self, obj_idx: int, vtx_idx: int):
        obj = self.objects[obj_idx]
        min_verts = 3 if obj.kind == "area" else 2
        if len(obj.points) <= min_verts:
            return
        self._push_undo()
        del obj.points[vtx_idx]
        self._recalculate_object(obj)
        self.objects_changed.emit()
        self.update()

    def _insert_vertex(self, obj_idx: int, edge_idx: int, img_pt: QPointF):
        obj = self.objects[obj_idx]
        self._push_undo()
        obj.points.insert(edge_idx + 1, [img_pt.x(), img_pt.y()])
        self._recalculate_object(obj)
        self.objects_changed.emit()
        self.update()

    # ------------------------------------------------------------------
    # Edit dialog
    # ------------------------------------------------------------------

    def _open_edit_dialog(self, idx: int):
        obj = self.objects[idx]
        world_pts = [self.img_to_world(QPointF(*p)) for p in obj.points]
        dlg = EditObjectDialog(obj.kind, obj.name, world_pts, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, new_world_pts = dlg.values()
        self._push_undo()
        obj.name   = new_name
        obj.points = [[*(self._world_to_img(wx, wy).toTuple())] for wx, wy in new_world_pts]
        if obj.kind != "point":
            self._recalculate_object(obj)
        self.objects_changed.emit()
        self.update()

    def open_edit_dialog_for(self, idx: int):
        self._open_edit_dialog(idx)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_object(self, screen_pos: QPointF) -> int:
        for i in range(len(self.objects) - 1, -1, -1):
            if self._obj_hit(self.objects[i], screen_pos):
                return i
        return -1

    def _obj_hit(self, obj: DiagramObject, sp: QPointF) -> bool:
        if not obj.points:
            return False
        img = self._screen_to_img(sp)
        px, py = img.x(), img.y()

        if obj.kind == "point":
            spt = self._img_to_screen(QPointF(*obj.points[0]))
            return math.hypot(spt.x() - sp.x(), spt.y() - sp.y()) <= _HIT_R

        if obj.kind == "distance" and len(obj.points) == 2:
            s0 = self._img_to_screen(QPointF(*obj.points[0]))
            s1 = self._img_to_screen(QPointF(*obj.points[1]))
            return _dist_pt_to_seg(sp.x(), sp.y(), s0.x(), s0.y(), s1.x(), s1.y()) <= _HIT_R

        if obj.kind == "angle" and len(obj.points) == 3:
            s = [self._img_to_screen(QPointF(*p)) for p in obj.points]
            d1 = _dist_pt_to_seg(sp.x(), sp.y(), s[0].x(), s[0].y(), s[1].x(), s[1].y())
            d2 = _dist_pt_to_seg(sp.x(), sp.y(), s[2].x(), s[2].y(), s[1].x(), s[1].y())
            return min(d1, d2) <= _HIT_R

        if obj.kind == "area" and len(obj.points) >= 3:
            if _point_in_polygon(px, py, obj.points):
                return True
            n = len(obj.points)
            for j in range(n):
                sa = self._img_to_screen(QPointF(*obj.points[j]))
                sb = self._img_to_screen(QPointF(*obj.points[(j + 1) % n]))
                if _dist_pt_to_seg(sp.x(), sp.y(), sa.x(), sa.y(), sb.x(), sb.y()) <= _HIT_R:
                    return True

        if obj.kind == "polyline" and len(obj.points) >= 2:
            n = len(obj.points)
            for j in range(n - 1):
                sa = self._img_to_screen(QPointF(*obj.points[j]))
                sb = self._img_to_screen(QPointF(*obj.points[j + 1]))
                if _dist_pt_to_seg(sp.x(), sp.y(), sa.x(), sa.y(), sb.x(), sb.y()) <= _HIT_R:
                    return True

        return False

    def _hit_selected_vertex(self, screen_pos: QPointF) -> Tuple[int, int]:
        """Return (obj_idx, vtx_idx) for the first vertex handle hit among selected non-point objects."""
        for i in self._selection:
            obj = self.objects[i]
            if obj.kind == "point":
                continue
            for vi, (vx, vy) in enumerate(obj.points):
                sp = self._img_to_screen(QPointF(vx, vy))
                if math.hypot(sp.x() - screen_pos.x(), sp.y() - screen_pos.y()) <= _HIT_R:
                    return i, vi
        return -1, -1

    def _hit_selected_edge(self, screen_pos: QPointF) -> Tuple[int, int, QPointF]:
        """Return (obj_idx, edge_start_idx, img_insert_pt) for first edge hit among selected area/polyline objects."""
        for i in self._selection:
            obj = self.objects[i]
            if obj.kind not in ("area", "polyline"):
                continue
            n = len(obj.points)
            segs = range(n) if obj.kind == "area" else range(n - 1)
            for j in segs:
                sa = self._img_to_screen(QPointF(*obj.points[j]))
                sb = self._img_to_screen(QPointF(*obj.points[(j + 1) % n]))
                d = _dist_pt_to_seg(screen_pos.x(), screen_pos.y(),
                                    sa.x(), sa.y(), sb.x(), sb.y())
                if d <= _HIT_R:
                    img_sp = _seg_insert_point(screen_pos, sa, sb)
                    return i, j, self._screen_to_img(img_sp)
        return -1, -1, QPointF()

    # ------------------------------------------------------------------
    # Vertex drag (PAN mode, on selected objects)
    # ------------------------------------------------------------------

    def _begin_vtx_drag(self, obj_idx: int, vtx_idx: int, screen_pos: QPointF):
        obj = self.objects[obj_idx]
        self._vtx_drag_snap      = self._snapshot()
        self._vtx_drag_start_pts = [list(p) for p in obj.points]
        self._vtx_drag_obj       = obj_idx
        self._vtx_drag_vtx       = vtx_idx
        self._vtx_drag_active    = True
        self._vtx_drag_start_img = self._screen_to_img(screen_pos)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _cancel_vtx_drag(self):
        if self._vtx_drag_active and self._vtx_drag_start_pts and self._vtx_drag_obj >= 0:
            obj = self.objects[self._vtx_drag_obj]
            obj.points = [list(p) for p in self._vtx_drag_start_pts]
            self._recalculate_object(obj)
        self._vtx_drag_active = False
        self._vtx_drag_obj    = -1
        self._vtx_drag_vtx    = -1
        self._vtx_drag_start_pts = []
        self._update_cursor_for_pos()
        self.update()

    # ------------------------------------------------------------------
    # Measurement recalculation
    # ------------------------------------------------------------------

    def _recalculate_object(self, obj: DiagramObject):
        pts = [Point(x, y) for x, y in obj.points]
        sf  = self.scale_info.scale_factor
        if obj.kind == "distance" and len(pts) == 2:
            obj.value = pts[0].distance_to(pts[1]) * sf
        elif obj.kind == "polyline" and len(pts) >= 2:
            obj.value = sum(pts[i].distance_to(pts[i + 1]) for i in range(len(pts) - 1)) * sf
        elif obj.kind == "angle" and len(pts) == 3:
            p1, v, p2 = pts
            v1x, v1y = p1.x - v.x, p1.y - v.y
            v2x, v2y = p2.x - v.x, p2.y - v.y
            dot = v1x * v2x + v1y * v2y
            mag = math.hypot(v1x, v1y) * math.hypot(v2x, v2y)
            obj.value = math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))) if mag > 0 else 0.0
        elif obj.kind == "area" and len(pts) >= 3:
            n = len(pts)
            area = sum(pts[i].x * pts[(i+1)%n].y - pts[(i+1)%n].x * pts[i].y for i in range(n))
            obj.value = abs(area) / 2.0 * (sf ** 2)

    def _recalculate_all(self):
        for obj in self.objects:
            if obj.kind != "point":
                self._recalculate_object(obj)

    # ------------------------------------------------------------------
    # Live measure status
    # ------------------------------------------------------------------

    def _emit_live_measure(self):
        measure_tools = {
            Tool.ADD_LINE, Tool.ADD_ANGLE, Tool.ADD_AREA, Tool.ADD_POLYLINE,
            Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS,
        }
        if not self._temp or self.current_tool not in measure_tools or self._mouse_img is None:
            self.live_measure.emit("")
            return

        tool = self.current_tool
        last = self._temp[-1]
        cur  = self._apply_snap(self._mouse_img)
        sf   = self.scale_info.scale_factor
        unit = self.scale_info.unit

        if tool in (Tool.SET_SCALE_DISTANCE, Tool.SET_SCALE_COORDS):
            d_px = math.hypot(cur.x() - last.x, cur.y() - last.y)
            self.live_measure.emit(f"Dist: {d_px:.1f} px")

        elif tool == Tool.ADD_LINE:
            d_px = math.hypot(cur.x() - last.x, cur.y() - last.y)
            self.live_measure.emit(f"Dist: {d_px * sf:.4g} {unit}")

        elif tool == Tool.ADD_ANGLE:
            if len(self._temp) == 2:
                p1, vertex = self._temp[0], self._temp[1]
                v1x, v1y = p1.x - vertex.x, p1.y - vertex.y
                v2x, v2y = cur.x() - vertex.x, cur.y() - vertex.y
                dot = v1x * v2x + v1y * v2y
                mag = math.hypot(v1x, v1y) * math.hypot(v2x, v2y)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / mag)))) if mag > 0 else 0.0
                self.live_measure.emit(f"Angle: {angle:.2f}°")
            else:
                d_px = math.hypot(cur.x() - last.x, cur.y() - last.y)
                self.live_measure.emit(f"Dist: {d_px * sf:.4g} {unit}")

        elif tool == Tool.ADD_AREA:
            if len(self._temp) >= 2:
                pts = [[p.x, p.y] for p in self._temp] + [[cur.x(), cur.y()]]
                n = len(pts)
                area = sum(pts[i][0] * pts[(i+1)%n][1] - pts[(i+1)%n][0] * pts[i][1]
                           for i in range(n))
                self.live_measure.emit(f"Area: {abs(area)/2.0 * (sf**2):.4g} {unit}²")
            else:
                d_px = math.hypot(cur.x() - last.x, cur.y() - last.y)
                self.live_measure.emit(f"Dist: {d_px * sf:.4g} {unit}")

        elif tool == Tool.ADD_POLYLINE:
            all_pts = [[p.x, p.y] for p in self._temp] + [[cur.x(), cur.y()]]
            total = sum(
                math.hypot(all_pts[i+1][0] - all_pts[i][0], all_pts[i+1][1] - all_pts[i][1])
                for i in range(len(all_pts) - 1)
            )
            self.live_measure.emit(f"Length: {total * sf:.4g} {unit}")

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
                self._recalculate_all()
                self.scale_set.emit(self.scale_info)
                self.objects_changed.emit()

        elif tool == Tool.SET_SCALE_COORDS:
            dlg = ScaleCoordsDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                import math as _m
                (x1, y1, x2, y2), unit = dlg.values()
                real_dist = _m.hypot(x2 - x1, y2 - y1)
                self._push_undo()
                self.scale_info = ScaleInfo(pixel_dist, real_dist, unit)
                self._recalculate_all()
                self.scale_set.emit(self.scale_info)
                self.objects_changed.emit()

        self._temp.clear()
        self.update()

    def _default_object_name(self, kind: str) -> str:
        prefix = {
            "point": "P", "distance": "L", "angle": "A",
            "area": "Area", "polyline": "PL",
        }.get(kind, kind.capitalize())
        count = sum(1 for o in self.objects if o.kind == kind) + 1
        return f"{prefix}{count}"

    def _ask_object_name(self, kind: str) -> Optional[str]:
        dlg = NameDialog(kind, self._default_object_name(kind), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._temp.clear()
            self.update()
            return None
        return dlg.label()

    def _finish_distance(self):
        name = self._ask_object_name("distance")
        if name is None:
            return
        p0, p1 = self._temp[0], self._temp[1]
        obj = DiagramObject(
            kind="distance", name=name,
            points=[[p0.x, p0.y], [p1.x, p1.y]],
            unit=self.scale_info.unit,
        )
        self._recalculate_object(obj)
        self._push_undo()
        self.objects.append(obj)
        self.objects_changed.emit()
        self._temp.clear()
        self.update()

    def _finish_angle(self):
        name = self._ask_object_name("angle")
        if name is None:
            return
        obj = DiagramObject(
            kind="angle", name=name,
            points=[[p.x, p.y] for p in self._temp],
            unit="°",
        )
        self._recalculate_object(obj)
        self._push_undo()
        self.objects.append(obj)
        self.objects_changed.emit()
        self._temp.clear()
        self.update()

    def _finish_area(self):
        name = self._ask_object_name("area")
        if name is None:
            return
        obj = DiagramObject(
            kind="area", name=name,
            points=[[p.x, p.y] for p in self._temp],
            unit=self.scale_info.unit,
        )
        self._recalculate_object(obj)
        self._push_undo()
        self.objects.append(obj)
        self.objects_changed.emit()
        self._temp.clear()
        self.update()

    def _finish_polyline(self):
        name = self._ask_object_name("polyline")
        if name is None:
            return
        obj = DiagramObject(
            kind="polyline", name=name,
            points=[[p.x, p.y] for p in self._temp],
            unit=self.scale_info.unit,
        )
        self._recalculate_object(obj)
        self._push_undo()
        self.objects.append(obj)
        self.objects_changed.emit()
        self._temp.clear()
        self.update()

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        return {
            "origin":       (self.origin.x, self.origin.y),
            "origin_world": self._origin_world,
            "scale_info":   (self.scale_info.pixel_distance,
                             self.scale_info.real_distance,
                             self.scale_info.unit),
            "objects": [
                (o.kind, o.name, [list(p) for p in o.points], o.unit, o.value, o.timestamp)
                for o in self.objects
            ],
        }

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()

    def _restore(self, snap: dict):
        self.origin        = Point(*snap["origin"])
        self._origin_world = snap.get("origin_world", (0.0, 0.0))
        self.scale_info    = ScaleInfo(*snap["scale_info"])
        self.objects       = [
            DiagramObject(kind, name, pts, unit, value, ts)
            for kind, name, pts, unit, value, ts in snap["objects"]
        ]
        self._temp.clear()
        self._selection.clear()
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
            "scale_info":   self.scale_info.to_dict(),
            "origin":       self.origin.to_dict(),
            "origin_world": list(self._origin_world),
            "objects":      [o.to_dict() for o in self.objects],
        }

    def load_session(self, data: dict):
        self.scale_info    = ScaleInfo.from_dict(data["scale_info"])
        self.origin        = Point.from_dict(data["origin"])
        ow                 = data.get("origin_world", [0.0, 0.0])
        self._origin_world = (float(ow[0]), float(ow[1]))

        if "objects" in data:
            self.objects = [DiagramObject.from_dict(o) for o in data["objects"]]
        else:
            self.objects = []
            for p in data.get("points", []):
                self.objects.append(DiagramObject(
                    kind="point", name=p.get("label", ""),
                    points=[[p["x"], p["y"]]],
                ))
            for m in data.get("measurements", []):
                self.objects.append(DiagramObject.from_dict(m))

        self._temp.clear()
        self._selection.clear()
        self.update()
