"""Programmatically-drawn toolbar icons (QPainter on a transparent pixmap), so
the toolbar needs no external image assets. Measurement tools echo the on-canvas
colors; navigation/setup/file actions use a neutral stroke that follows the
active palette (see _fg) so they read on both light and dark toolbars.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import QApplication

from ..core.constants import Tool

_SIZE = 32
_RED = QColor("#ff5555")
_YELLOW = QColor("#ffcc44")


def _fg() -> QColor:
    """Neutral stroke color that follows the active palette (so icons read on
    both light and dark toolbars)."""
    app = QApplication.instance()
    if app is not None:
        return app.palette().color(QPalette.ColorRole.ButtonText)
    return QColor("#d4d4d4")

# Echo the viewer's per-kind colors.
_C_POINT = QColor("#4488ff")
_C_LINE = QColor("#ffdd00")
_C_ANGLE = QColor("#ff8800")
_C_AREA = QColor("#ff6699")
_C_POLY = QColor("#44ddaa")
_C_CONTOUR = QColor("#bbbbbb")


def _new():
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pm, p


def _pen(p, color, w=2.4, style=Qt.PenStyle.SolidLine):
    pen = QPen(color, w)
    pen.setStyle(style)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _line(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _poly(pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _finish(pm, p) -> QIcon:
    p.end()
    return QIcon(pm)


# --- Navigation / view -----------------------------------------------------

def _draw_pan(p):
    _pen(p, _fg())
    c, L, a = 16, 10, 4
    _line(p, c, c - L, c, c + L)
    _line(p, c - L, c, c + L, c)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        tx, ty = c + dx * L, c + dy * L
        px, py = -dy, dx
        _line(p, tx, ty, tx - dx * a + px * a, ty - dy * a + py * a)
        _line(p, tx, ty, tx - dx * a - px * a, ty - dy * a - py * a)


def _draw_select(p):
    p.setPen(QPen(_fg(), 1.4))
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(_poly([(9, 5), (9, 24), (14, 19), (17, 26), (20, 25),
                         (16, 18), (22, 18)]))


def _draw_zoom(p):
    _pen(p, _fg())
    p.drawEllipse(QPointF(14, 14), 7, 7)
    _line(p, 19, 19, 26, 26)
    _line(p, 14, 11, 14, 17)
    _line(p, 11, 14, 17, 14)


# --- Setup -----------------------------------------------------------------

def _draw_origin(p):
    _pen(p, _RED)
    p.drawEllipse(QPointF(16, 16), 6, 6)
    _line(p, 16, 3, 16, 29)
    _line(p, 3, 16, 29, 16)


def _draw_scale(p):
    _pen(p, _fg(), 2.0)
    p.drawRect(QRectF(5, 13, 22, 7))
    for i, x in enumerate((9, 13, 17, 21, 25)):
        _line(p, x, 13, x, 13 + (6 if i % 2 == 0 else 3))


def _draw_coords(p):
    _pen(p, _fg())
    _line(p, 8, 24, 27, 24)
    _line(p, 8, 24, 8, 5)
    _line(p, 27, 24, 23, 21)
    _line(p, 27, 24, 23, 27)
    _line(p, 8, 5, 5, 9)
    _line(p, 8, 5, 11, 9)


# --- Add / measure ---------------------------------------------------------

def _draw_point(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_POINT))
    p.drawEllipse(QPointF(16, 16), 5.5, 5.5)


def _draw_line(p):
    _pen(p, _C_LINE)
    _line(p, 7, 25, 25, 7)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_LINE))
    p.drawEllipse(QPointF(7, 25), 2.6, 2.6)
    p.drawEllipse(QPointF(25, 7), 2.6, 2.6)


def _draw_angle(p):
    _pen(p, _C_ANGLE)
    _line(p, 8, 24, 27, 24)
    _line(p, 8, 24, 26, 8)
    p.drawArc(QRectF(8 - 9, 24 - 9, 18, 18), 0, 42 * 16)


def _draw_area(p):
    fill = QColor(_C_AREA)
    fill.setAlpha(70)
    p.setPen(QPen(_C_AREA, 2.2))
    p.setBrush(QBrush(fill))
    p.drawPolygon(_poly([(7, 10), (24, 6), (27, 22), (12, 26)]))


def _draw_polyline(p):
    _pen(p, _C_POLY)
    pts = [(6, 22), (13, 10), (19, 21), (26, 8)]
    for i in range(len(pts) - 1):
        _line(p, *pts[i], *pts[i + 1])


def _draw_polyline_contour(p):
    _pen(p, _RED, 1.5, Qt.PenStyle.DashLine)
    p.drawRoundedRect(QRectF(4, 7, 24, 18), 9, 9)
    _pen(p, _C_CONTOUR, 2.2)
    pts = [(9, 20), (16, 12), (23, 20)]
    for i in range(len(pts) - 1):
        _line(p, *pts[i], *pts[i + 1])


def _draw_point_contour(p):
    _pen(p, _YELLOW, 1.5)
    p.drawEllipse(QPointF(16, 16), 11, 11)
    _pen(p, _RED, 1.5)
    p.drawEllipse(QPointF(16, 16), 7, 7)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_C_CONTOUR))
    p.drawEllipse(QPointF(16, 16), 3, 3)


# --- File / document actions ----------------------------------------------

def _draw_open(p):
    _pen(p, _fg(), 2.0)
    p.drawPolyline(_poly([(5, 11), (5, 8), (12, 8), (14, 11)]))
    p.drawRect(QRectF(5, 11, 21, 14))


def _draw_save(p):
    _pen(p, _fg(), 2.0)
    p.drawRect(QRectF(6, 6, 20, 20))
    p.drawRect(QRectF(11, 16, 10, 9))
    p.drawRect(QRectF(11, 8, 7, 5))


def _draw_export(p):
    _pen(p, _fg(), 2.0)
    p.drawPolyline(_poly([(6, 19), (6, 26), (26, 26), (26, 19)]))
    _line(p, 16, 22, 16, 7)
    _line(p, 16, 7, 11, 12)
    _line(p, 16, 7, 21, 12)


def _draw_prev(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(_poly([(20, 8), (20, 24), (10, 16)]))


def _draw_next(p):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_fg()))
    p.drawPolygon(_poly([(12, 8), (12, 24), (22, 16)]))


_TOOL_DRAW = {
    Tool.PAN: _draw_pan,
    Tool.SELECT: _draw_select,
    Tool.ZOOM_RECT: _draw_zoom,
    Tool.SET_ORIGIN: _draw_origin,
    Tool.SET_SCALE_DISTANCE: _draw_scale,
    Tool.SET_SCALE_COORDS: _draw_coords,
    Tool.ADD_POINT: _draw_point,
    Tool.ADD_LINE: _draw_line,
    Tool.ADD_ANGLE: _draw_angle,
    Tool.ADD_AREA: _draw_area,
    Tool.ADD_POLYLINE: _draw_polyline,
    Tool.ADD_POLYLINE_CONTOUR: _draw_polyline_contour,
    Tool.ADD_POINT_CONTOUR: _draw_point_contour,
}

_ACTION_DRAW = {
    "open": _draw_open,
    "save": _draw_save,
    "export": _draw_export,
    "prev": _draw_prev,
    "next": _draw_next,
}


def tool_icon(tool: Tool) -> QIcon:
    pm, p = _new()
    _TOOL_DRAW[tool](p)
    return _finish(pm, p)


def action_icon(name: str) -> QIcon:
    pm, p = _new()
    _ACTION_DRAW[name](p)
    return _finish(pm, p)
